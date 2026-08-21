"""Typed resource contribution registry shared by tools and future plugins."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .migrations import MigrationRegistry, build_default_migration_registry
from .resources import (
    BACKGROUND_RESOURCE_TYPE,
    CURVE_RESOURCE_TYPE,
    PATTERN_RESOURCE_TYPE,
    RESOURCE_SCHEMA_VERSION,
    SCENE_RESOURCE_SCHEMA_VERSION,
    SCENE_RESOURCE_TYPE,
    UI_RESOURCE_TYPE,
    GenericResourceDocument,
    ResourceDocumentError,
)


ResourceLoader = Callable[[Mapping[str, Any]], Any]
ResourceValidator = Callable[[Any], None]
Contribution = Callable[..., Any]


@dataclass(frozen=True)
class ResourceTypeSpec:
    type_name: str
    display_name: str
    asset_kind: str
    current_version: int = RESOURCE_SCHEMA_VERSION
    loader: ResourceLoader | None = None
    validator: ResourceValidator | None = None
    editor_factory: Contribution | None = None
    compiler: Contribution | None = None
    preview_handler: Contribution | None = None

    def validate(self) -> None:
        if not self.type_name or not self.display_name or not self.asset_kind:
            raise ValueError("resource type, display name, and asset kind are required")
        if self.current_version <= 0:
            raise ValueError("resource current_version must be positive")


class ResourceTypeRegistry(Mapping[str, ResourceTypeSpec]):
    def __init__(self, migrations: MigrationRegistry | None = None) -> None:
        self.migrations = migrations or MigrationRegistry()
        self._types: dict[str, ResourceTypeSpec] = {}

    def register(self, spec: ResourceTypeSpec) -> ResourceTypeSpec:
        spec.validate()
        if spec.type_name in self._types:
            raise ValueError(f"Duplicate resource type: {spec.type_name}")
        self.migrations.register_type(spec.type_name, spec.current_version)
        self._types[spec.type_name] = spec
        return spec

    def unregister(self, type_name: str) -> ResourceTypeSpec:
        """Remove one plugin-owned type and its migration declaration."""
        try:
            spec = self._types.pop(type_name)
        except KeyError as exc:
            raise KeyError(type_name) from exc
        unregister = getattr(self.migrations, "unregister_type", None)
        if callable(unregister):
            unregister(type_name)
        return spec

    def __getitem__(self, key: str) -> ResourceTypeSpec:
        try:
            return self._types[key]
        except KeyError as exc:
            raise KeyError(f"Unknown resource type: {key}") from exc

    def __iter__(self) -> Iterator[str]:
        return iter(self._types)

    def __len__(self) -> int:
        return len(self._types)

    def spec_for_payload(self, data: Mapping[str, Any]) -> ResourceTypeSpec:
        resource_type = str(data.get("type") or "")
        if not resource_type:
            raise ResourceDocumentError("resource.type is required")
        try:
            return self[resource_type]
        except KeyError as exc:
            raise ResourceDocumentError(str(exc)) from exc

    def load(
        self,
        data: Mapping[str, Any],
        *,
        expected_type: str | None = None,
    ) -> Any:
        migrated = self.migrations.migrate(data, expected_type=expected_type)
        spec = self.spec_for_payload(migrated)
        loader = spec.loader or (
            lambda payload: GenericResourceDocument.from_dict(
                payload,
                expected_type=spec.type_name,
                current_version=spec.current_version,
            )
        )
        document = loader(migrated)
        if spec.validator is not None:
            spec.validator(document)
        elif isinstance(document, GenericResourceDocument):
            document.validate(current_version=spec.current_version)
        elif hasattr(document, "validate"):
            document.validate()
        return document

    def asset_kind_for_payload(self, data: Mapping[str, Any]) -> str:
        return self.spec_for_payload(data).asset_kind


#: Editor (Qt) factories contributed by :mod:`src.editor` via contribution
#: inversion.  Authoring owns the slot and resolves factories lazily; it never
#: imports Qt or the editor itself.  ``src.editor`` populates this on import.
_EDITOR_FACTORIES: dict[str, Contribution] = {}


def register_editor_factory(type_name: str, factory: Contribution) -> None:
    """Register the Qt editor factory for ``type_name`` (called by the editor).

    This is the authoring-side hook of the editor -> authoring contribution
    inversion (EDITOR_ARCHITECTURE.md §6/§8): the editor layer registers its Qt
    workspaces here, so the headless registry can advertise a callable
    ``editor_factory`` without importing Qt.
    """

    _EDITOR_FACTORIES[type_name] = factory


def _editor_factory_for(type_name: str) -> Contribution:
    """Return a stable, Qt-free indirection to the registered editor factory.

    The returned callable resolves the concrete factory lazily when invoked, so
    a resource type that supports a Qt editor always advertises a callable
    ``editor_factory`` even before :mod:`src.editor` is imported; calling it
    without a registered factory raises a clear error.
    """

    def _make_editor(*args: Any, **kwargs: Any) -> Any:
        factory = _EDITOR_FACTORIES.get(type_name)
        if factory is None:
            raise ResourceDocumentError(
                f"no editor factory registered for resource type {type_name!r}; "
                "import src.editor to install the Qt editor contributions"
            )
        return factory(*args, **kwargs)

    return _make_editor


def build_default_resource_type_registry() -> ResourceTypeRegistry:
    registry = ResourceTypeRegistry(build_default_migration_registry())
    for type_name, display_name, asset_kind in (
        (SCENE_RESOURCE_TYPE, "Scene", "scene"),
        (PATTERN_RESOURCE_TYPE, "Pattern", "pattern"),
        (UI_RESOURCE_TYPE, "UI", "ui"),
        (BACKGROUND_RESOURCE_TYPE, "Background", "background"),
        (CURVE_RESOURCE_TYPE, "Curve", "curve"),
    ):
        if type_name == SCENE_RESOURCE_TYPE:
            from src.authoring.scene.document import SceneDocument

            def load_scene(payload):
                # The common envelope contract also permits header-only/generic
                # Scene resources in low-level tooling.  Only a payload with the
                # formal Scene body is promoted to the editor SceneDocument.
                if "root" in payload:
                    return SceneDocument.from_dict(dict(payload))
                return GenericResourceDocument.from_dict(
                    payload,
                    expected_type=SCENE_RESOURCE_TYPE,
                    current_version=SCENE_RESOURCE_SCHEMA_VERSION,
                )

            def compile_scene(document, *, project=None, **kwargs):
                if project is None:
                    raise ResourceDocumentError(
                        "a ProjectContext is required to compile a SceneDocument"
                    )
                from src.compiler import compile_stage

                return compile_stage(project, document, **kwargs)

            registry.register(
                ResourceTypeSpec(
                    type_name=type_name,
                    display_name=display_name,
                    asset_kind=asset_kind,
                    loader=load_scene,
                    compiler=compile_scene,
                    current_version=SCENE_RESOURCE_SCHEMA_VERSION,
                )
            )
        elif type_name == PATTERN_RESOURCE_TYPE:
            # Local import keeps the common registry independent of domain
            # modules while still providing typed loading and compilation.
            from src.pattern import PatternDocument, compile_pattern

            registry.register(
                ResourceTypeSpec(
                    type_name=type_name,
                    display_name=display_name,
                    asset_kind=asset_kind,
                    loader=PatternDocument.from_dict,
                    compiler=compile_pattern,
                )
            )
        elif type_name == CURVE_RESOURCE_TYPE:
            from src.pattern.curves import CurveDocument

            registry.register(
                ResourceTypeSpec(
                    type_name=type_name,
                    display_name=display_name,
                    asset_kind=asset_kind,
                    loader=CurveDocument.from_dict,
                )
            )
        elif type_name == UI_RESOURCE_TYPE:
            from src.ui.document import UIDocument

            def compile_ui(document, *, viewport_width=384, viewport_height=448, **kwargs):
                document.validate()
                return document.get_render_elements(
                    viewport_width=viewport_width,
                    viewport_height=viewport_height,
                    **kwargs,
                )

            def preview_ui(compiled, renderer=None, **kwargs):
                elements = (
                    compiled.get_render_elements(**kwargs)
                    if isinstance(compiled, UIDocument)
                    else compiled
                )
                if renderer is not None:
                    render_hud = getattr(renderer, "render_hud", None)
                    if callable(render_hud):
                        class _CompiledHUD:
                            def get_render_elements(self):
                                return elements

                        render_hud(_CompiledHUD())
                        return elements
                    for element in elements:
                        record = dict(element)
                        kind = record.pop("type")
                        position = record.pop("position", (0.0, 0.0))
                        if kind == "text":
                            record["x"], record["y"] = position
                            record["font_name"] = record.pop("font", "default")
                        else:
                            record["x"], record["y"] = position
                        method = getattr(renderer, f"render_{kind}", None)
                        if callable(method):
                            method(**record)
                return elements

            def load_ui(payload):
                if "root" in payload:
                    return UIDocument.from_dict(payload)
                return GenericResourceDocument.from_dict(
                    payload,
                    expected_type=UI_RESOURCE_TYPE,
                    current_version=RESOURCE_SCHEMA_VERSION,
                )

            registry.register(
                ResourceTypeSpec(
                    type_name=type_name,
                    display_name=display_name,
                    asset_kind=asset_kind,
                    loader=load_ui,
                    editor_factory=_editor_factory_for(UI_RESOURCE_TYPE),
                    compiler=compile_ui,
                    preview_handler=preview_ui,
                )
            )
        elif type_name == BACKGROUND_RESOURCE_TYPE:
            from src.game.background_render.document import BackgroundDocument

            def compile_background(document, **_kwargs):
                """Return the typed document consumed by the formal renderer."""
                if not isinstance(document, BackgroundDocument):
                    raise ResourceDocumentError(
                        "background compiler expects a BackgroundDocument"
                    )
                document.validate()
                return document

            def preview_background(
                compiled,
                renderer=None,
                *,
                base_dir="",
                project=None,
                frame=0,
                time=None,
                **_kwargs,
            ):
                """Render a background through ``DataDrivenBackground``.

                Without a renderer this returns the evaluated, serializable
                payload for transport.  With one, it follows the same
                DataDrivenBackground path used by gameplay and returns its
                generated quads; no Qt diagnostic drawing is substituted.
                """
                if isinstance(compiled, BackgroundDocument):
                    document = compiled
                elif isinstance(compiled, Mapping):
                    document = BackgroundDocument.from_dict(compiled)
                else:
                    raise ResourceDocumentError(
                        "background preview payload must be an object"
                    )
                payload = document.evaluate_bindings(frame=frame, time=time)
                if renderer is None:
                    return payload
                from src.game.background_render.data_driven_background import (
                    DataDrivenBackground,
                )

                if not base_dir and project is not None:
                    base_dir = str(project.root / "assets" / "images" / "background")
                background = DataDrivenBackground(renderer)
                if not background.load_from_dict(
                    payload, str(base_dir or ""), announce=False,
                    frame=frame, time=time,
                ):
                    raise ResourceDocumentError("formal background preview failed to load")
                background.render()
                return background.get_render_quads()

            def load_background(payload):
                if any(
                    key in payload
                    for key in ("layers", "camera", "textures")
                ):
                    return BackgroundDocument.from_dict(payload)
                return GenericResourceDocument.from_dict(
                    payload,
                    expected_type=BACKGROUND_RESOURCE_TYPE,
                    current_version=RESOURCE_SCHEMA_VERSION,
                )

            registry.register(
                ResourceTypeSpec(
                    type_name=type_name,
                    display_name=display_name,
                    asset_kind=asset_kind,
                    loader=load_background,
                    editor_factory=_editor_factory_for(BACKGROUND_RESOURCE_TYPE),
                    compiler=compile_background,
                    preview_handler=preview_background,
                )
            )
        else:
            registry.register(
                ResourceTypeSpec(
                    type_name=type_name,
                    display_name=display_name,
                    asset_kind=asset_kind,
                )
            )
    return registry

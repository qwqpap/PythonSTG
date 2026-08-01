"""Typed resource contribution registry shared by tools and future plugins."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .migrations import MigrationRegistry, build_default_migration_registry
from .resources import (
    BACKGROUND_RESOURCE_TYPE,
    PATTERN_RESOURCE_TYPE,
    RESOURCE_SCHEMA_VERSION,
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
        elif hasattr(document, "validate"):
            document.validate()
        return document

    def asset_kind_for_payload(self, data: Mapping[str, Any]) -> str:
        return self.spec_for_payload(data).asset_kind


def build_default_resource_type_registry() -> ResourceTypeRegistry:
    registry = ResourceTypeRegistry(build_default_migration_registry())
    for type_name, display_name, asset_kind in (
        (SCENE_RESOURCE_TYPE, "Scene", "scene"),
        (PATTERN_RESOURCE_TYPE, "Pattern", "pattern"),
        (UI_RESOURCE_TYPE, "UI", "ui"),
        (BACKGROUND_RESOURCE_TYPE, "Background", "background"),
    ):
        if type_name == SCENE_RESOURCE_TYPE:
            from src.editor.document import SceneDocument

            def load_scene(payload):
                # The common envelope contract also permits header-only/generic
                # Scene resources in low-level tooling.  Only a payload with the
                # formal Scene body is promoted to the editor SceneDocument.
                if "root" in payload:
                    return SceneDocument.from_dict(dict(payload))
                return GenericResourceDocument.from_dict(
                    payload,
                    expected_type=SCENE_RESOURCE_TYPE,
                    current_version=RESOURCE_SCHEMA_VERSION,
                )

            registry.register(
                ResourceTypeSpec(
                    type_name=type_name,
                    display_name=display_name,
                    asset_kind=asset_kind,
                    loader=load_scene,
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
        else:
            registry.register(
                ResourceTypeSpec(
                    type_name=type_name,
                    display_name=display_name,
                    asset_kind=asset_kind,
                )
            )
    return registry

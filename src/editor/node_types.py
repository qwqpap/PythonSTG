"""Extensible node/property contracts shared by editor views and compilers."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .document import EditorNode


NodeValidator = Callable[[EditorNode], None]
NodeCompiler = Callable[[EditorNode, Any], Any]
EditorFactory = Callable[..., Any]


@dataclass(frozen=True)
class PropertySpec:
    key: str
    label: str
    value_type: type
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple[Any, ...] = ()
    resource_types: tuple[str, ...] = ()
    unit: str | None = None
    group: str = "General"
    curve_capable: bool = False
    binding_capable: bool = False
    visible_when: tuple[str, Any] | None = None
    editor_hint: str | None = None

    def validate(self) -> None:
        if not self.key or not self.label:
            raise ValueError("property key and label are required")
        if not isinstance(self.value_type, type):
            raise ValueError(f"property {self.key!r} value_type must be a type")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError(f"property {self.key!r} has an invalid range")
        if self.choices and self.default not in self.choices:
            raise ValueError(f"property {self.key!r} default is not in its choices")


@dataclass(frozen=True)
class ViewportSpec:
    shape: str = "box"
    label: str = "NODE"
    preview_property: str | None = None
    movable: bool = True

    def validate(self) -> None:
        if self.shape not in {"none", "box", "circle", "diamond"}:
            raise ValueError(f"unsupported viewport shape: {self.shape}")


@dataclass(frozen=True)
class NodeTypeSpec:
    type_name: str
    display_name: str
    color: str
    properties: tuple[PropertySpec, ...]
    viewport: ViewportSpec = ViewportSpec()
    allowed_parents: tuple[str, ...] | None = None
    allowed_children: tuple[str, ...] | None = None
    validator: NodeValidator | None = None
    editor_factory: EditorFactory | None = None
    runtime_compiler: NodeCompiler | None = None

    @property
    def viewport_item(self) -> bool:
        return self.viewport.shape != "none"

    def validate(self) -> None:
        if not self.type_name or not self.display_name:
            raise ValueError("node type and display name are required")
        self.viewport.validate()
        keys: set[str] = set()
        for prop in self.properties:
            prop.validate()
            if prop.key in keys:
                raise ValueError(
                    f"node type {self.type_name!r} repeats property {prop.key!r}"
                )
            keys.add(prop.key)


class NodeTypeRegistry(Mapping[str, NodeTypeSpec]):
    def __init__(self) -> None:
        self._types: dict[str, NodeTypeSpec] = {}

    def register(self, spec: NodeTypeSpec) -> NodeTypeSpec:
        spec.validate()
        if spec.type_name in self._types:
            raise ValueError(f"Duplicate node type: {spec.type_name}")
        self._types[spec.type_name] = spec
        return spec

    def __getitem__(self, key: str) -> NodeTypeSpec:
        try:
            return self._types[key]
        except KeyError as exc:
            raise KeyError(f"Unknown node type: {key}") from exc

    def __iter__(self) -> Iterator[str]:
        return iter(self._types)

    def __len__(self) -> int:
        return len(self._types)

    def can_parent(self, parent_type: str, child_type: str) -> bool:
        parent = self[parent_type]
        child = self[child_type]
        if parent.allowed_children is not None and child_type not in parent.allowed_children:
            return False
        if child.allowed_parents is not None and parent_type not in child.allowed_parents:
            return False
        return True

    def validate_node(self, node: EditorNode) -> None:
        spec = self[node.type]
        known_properties = {prop.key for prop in spec.properties}
        unknown = set(node.properties).difference(known_properties)
        if unknown:
            raise ValueError(
                f"Node {node.name!r} ({node.type}) has unknown properties: "
                + ", ".join(sorted(unknown))
            )
        if spec.validator is not None:
            spec.validator(node)

    def validate_tree(self, root: EditorNode) -> None:
        self.validate_node(root)
        for parent in root.walk():
            for child in parent.children:
                self.validate_node(child)
                if not self.can_parent(parent.type, child.type):
                    raise ValueError(
                        f"Node type {child.type!r} cannot be a child of {parent.type!r}"
                    )

    def compile_node(self, node: EditorNode, context: Any = None) -> Any:
        spec = self[node.type]
        if spec.runtime_compiler is None:
            raise ValueError(f"Node type {node.type!r} has no runtime compiler")
        return spec.runtime_compiler(node, context)


POSITION_PROPERTIES = (
    PropertySpec("x", "X", float, 192.0, -4096.0, 4096.0, 1.0, unit="px", group="Transform"),
    PropertySpec("y", "Y", float, 224.0, -4096.0, 4096.0, 1.0, unit="px", group="Transform"),
)


def build_default_node_type_registry() -> NodeTypeRegistry:
    registry = NodeTypeRegistry()

    legacy_scene_children = (
        "Stage",
        "Sprite",
        "EnemySpawner",
        "SpellCard",
        "Boss",
        "Spell",
        "Emitter",
        "PatternInstance",
    )
    registry.register(
        NodeTypeSpec(
            type_name="SceneRoot",
            display_name="Scene Root",
            color="#8aa1c1",
            viewport=ViewportSpec(shape="none"),
            allowed_parents=(),
            allowed_children=legacy_scene_children,
            properties=(
                PropertySpec("width", "Canvas Width", int, 384, 64, 8192, 1, unit="px", group="Canvas"),
                PropertySpec("height", "Canvas Height", int, 448, 64, 8192, 1, unit="px", group="Canvas"),
                PropertySpec("grid_size", "Grid Size", int, 16, 1, 256, 1, unit="px", group="Canvas"),
                PropertySpec("background", "Background", str, "#171a24", group="Canvas", editor_hint="color"),
            ),
        )
    )
    registry.register(
        NodeTypeSpec(
            type_name="Stage",
            display_name="Stage",
            color="#8aa1c1",
            viewport=ViewportSpec(shape="none"),
            allowed_parents=("SceneRoot",),
            allowed_children=("Sprite", "Boss", "Spell", "Emitter", "PatternInstance"),
            properties=(
                PropertySpec("width", "Canvas Width", int, 384, 64, 8192, 1, unit="px", group="Canvas"),
                PropertySpec("height", "Canvas Height", int, 448, 64, 8192, 1, unit="px", group="Canvas"),
                PropertySpec("tick_rate", "Tick Rate", int, 60, 1, 1000, 1, unit="fps", group="Timing"),
                PropertySpec("background", "Background", str, "", resource_types=("pystg.background",), group="Resources", editor_hint="resource"),
            ),
        )
    )
    registry.register(
        NodeTypeSpec(
            type_name="Sprite",
            display_name="Sprite",
            color="#59c2ff",
            viewport=ViewportSpec(shape="box", label="SPR", preview_property="texture"),
            allowed_parents=("SceneRoot", "Stage", "Sprite"),
            allowed_children=legacy_scene_children,
            properties=POSITION_PROPERTIES
            + (
                PropertySpec("texture", "Texture", str, "", resource_types=("image", "sprite"), group="Resources", editor_hint="resource"),
                PropertySpec("scale", "Scale", float, 1.0, 0.01, 100.0, 0.05, group="Transform", curve_capable=True),
                PropertySpec("rotation", "Rotation", float, 0.0, -3600.0, 3600.0, 1.0, unit="deg", group="Transform", curve_capable=True),
                PropertySpec("visible", "Visible", bool, True, group="Rendering", binding_capable=True),
            ),
        )
    )
    registry.register(
        NodeTypeSpec(
            type_name="EnemySpawner",
            display_name="Enemy Spawner",
            color="#ff9f5b",
            viewport=ViewportSpec(shape="circle", label="+"),
            allowed_parents=("SceneRoot", "Stage", "Sprite"),
            allowed_children=legacy_scene_children,
            properties=POSITION_PROPERTIES
            + (
                PropertySpec("enemy_script", "Enemy Script", str, "", resource_types=("script",), group="Resources", editor_hint="resource"),
                PropertySpec("start_frame", "Start Frame", int, 0, 0, 10_000_000, 1, unit="frame", group="Timing"),
                PropertySpec("interval", "Interval", int, 60, 1, 1_000_000, 1, unit="frame", group="Timing"),
                PropertySpec("count", "Count", int, 1, 1, 1_000_000, 1, group="Emission"),
            ),
        )
    )
    registry.register(
        NodeTypeSpec(
            type_name="SpellCard",
            display_name="Spell Card",
            color="#d98cff",
            viewport=ViewportSpec(shape="diamond", label="SC"),
            allowed_parents=("SceneRoot", "Stage", "Sprite"),
            allowed_children=legacy_scene_children,
            properties=POSITION_PROPERTIES
            + (
                PropertySpec("script", "Script", str, "", resource_types=("script",), group="Resources", editor_hint="resource"),
                PropertySpec("class_name", "Class", str, "", group="Script"),
                PropertySpec("duration", "Duration", int, 3600, 1, 10_000_000, 1, unit="frame", group="Timing"),
                PropertySpec("boss_x", "Boss X", float, 0.0, -2.0, 2.0, 0.01, group="Legacy Runtime"),
                PropertySpec("boss_y", "Boss Y", float, 0.55, -2.0, 2.0, 0.01, group="Legacy Runtime"),
            ),
        )
    )
    registry.register(
        NodeTypeSpec(
            type_name="Boss",
            display_name="Boss",
            color="#ef8fc6",
            viewport=ViewportSpec(shape="circle", label="BOSS"),
            allowed_parents=("SceneRoot", "Stage"),
            allowed_children=("Spell", "Emitter", "PatternInstance", "Sprite"),
            properties=POSITION_PROPERTIES
            + (
                PropertySpec("texture", "Texture", str, "", resource_types=("image", "sprite"), group="Resources", editor_hint="resource"),
                PropertySpec("visible", "Visible", bool, True, group="Rendering", binding_capable=True),
            ),
        )
    )
    registry.register(
        NodeTypeSpec(
            type_name="Spell",
            display_name="Spell",
            color="#d98cff",
            viewport=ViewportSpec(shape="diamond", label="SPELL"),
            allowed_parents=("SceneRoot", "Stage", "Boss"),
            allowed_children=("Emitter", "PatternInstance", "Sprite"),
            properties=(
                PropertySpec("duration_frames", "Duration", int, 3600, 1, 10_000_000, 1, unit="frame", group="Timing"),
                PropertySpec("script", "Script", str, "", resource_types=("script",), group="Advanced", editor_hint="resource"),
            ),
        )
    )
    registry.register(
        NodeTypeSpec(
            type_name="Emitter",
            display_name="Emitter",
            color="#ffb45e",
            viewport=ViewportSpec(shape="circle", label="EMIT"),
            allowed_parents=("SceneRoot", "Stage", "Boss", "Spell"),
            allowed_children=("PatternInstance",),
            properties=POSITION_PROPERTIES
            + (
                PropertySpec("rotation", "Rotation", float, 0.0, -3600.0, 3600.0, 1.0, unit="deg", group="Transform", curve_capable=True),
                PropertySpec("enabled", "Enabled", bool, True, group="Behavior", binding_capable=True),
            ),
        )
    )
    registry.register(
        NodeTypeSpec(
            type_name="PatternInstance",
            display_name="Pattern Instance",
            color="#8f9cff",
            viewport=ViewportSpec(shape="box", label="PAT"),
            allowed_parents=("SceneRoot", "Stage", "Boss", "Spell", "Emitter"),
            allowed_children=(),
            properties=(
                PropertySpec("pattern", "Pattern", str, "", resource_types=("pystg.pattern",), group="Resources", editor_hint="resource"),
                PropertySpec("start_frame", "Start Frame", int, 0, 0, 10_000_000, 1, unit="frame", group="Timing"),
                PropertySpec("enabled", "Enabled", bool, True, group="Behavior", binding_capable=True),
            ),
        )
    )
    return registry


NODE_TYPE_REGISTRY = build_default_node_type_registry()
# Backwards-compatible Mapping name used by the current editor shell.
NODE_TYPES: Mapping[str, NodeTypeSpec] = NODE_TYPE_REGISTRY


def make_node(type_name: str, *, name: str | None = None) -> EditorNode:
    try:
        spec = NODE_TYPE_REGISTRY[type_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported editor node type: {type_name}") from exc
    return EditorNode(
        type=type_name,
        name=name or spec.display_name,
        properties={prop.key: prop.default for prop in spec.properties},
    )


def make_default_root(name: str = "Scene") -> EditorNode:
    return make_node("SceneRoot", name=name)


def property_specs(node_type: str) -> tuple[PropertySpec, ...]:
    spec = NODE_TYPE_REGISTRY.get(node_type)
    return spec.properties if spec is not None else ()

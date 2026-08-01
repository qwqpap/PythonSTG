"""Node definitions shared by the scene editor UI and document commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .document import EditorNode


@dataclass(frozen=True)
class PropertySpec:
    key: str
    label: str
    value_type: type
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None


@dataclass(frozen=True)
class NodeTypeSpec:
    type_name: str
    display_name: str
    color: str
    properties: tuple[PropertySpec, ...]
    viewport_item: bool = True


POSITION_PROPERTIES = (
    PropertySpec("x", "X", float, 384.0, -4096.0, 4096.0, 1.0),
    PropertySpec("y", "Y", float, 448.0, -4096.0, 4096.0, 1.0),
)

NODE_TYPES: dict[str, NodeTypeSpec] = {
    "SceneRoot": NodeTypeSpec(
        type_name="SceneRoot",
        display_name="Scene Root",
        color="#8aa1c1",
        viewport_item=False,
        properties=(
            PropertySpec("width", "Canvas Width", int, 768, 64, 8192, 1),
            PropertySpec("height", "Canvas Height", int, 896, 64, 8192, 1),
            PropertySpec("grid_size", "Grid Size", int, 16, 1, 256, 1),
            PropertySpec("background", "Background", str, "#171a24"),
        ),
    ),
    "Sprite": NodeTypeSpec(
        type_name="Sprite",
        display_name="Sprite",
        color="#59c2ff",
        properties=POSITION_PROPERTIES + (
            PropertySpec("texture", "Texture", str, ""),
            PropertySpec("scale", "Scale", float, 1.0, 0.01, 100.0, 0.05),
            PropertySpec("rotation", "Rotation", float, 0.0, -3600.0, 3600.0, 1.0),
            PropertySpec("visible", "Visible", bool, True),
        ),
    ),
    "EnemySpawner": NodeTypeSpec(
        type_name="EnemySpawner",
        display_name="Enemy Spawner",
        color="#ff9f5b",
        properties=POSITION_PROPERTIES + (
            PropertySpec("enemy_script", "Enemy Script", str, ""),
            PropertySpec("start_frame", "Start Frame", int, 0, 0, 10_000_000, 1),
            PropertySpec("interval", "Interval", int, 60, 1, 1_000_000, 1),
            PropertySpec("count", "Count", int, 1, 1, 1_000_000, 1),
        ),
    ),
    "SpellCard": NodeTypeSpec(
        type_name="SpellCard",
        display_name="Spell Card",
        color="#d98cff",
        properties=POSITION_PROPERTIES + (
            PropertySpec("script", "Script", str, ""),
            PropertySpec("class_name", "Class", str, ""),
            PropertySpec("duration", "Duration", int, 3600, 1, 10_000_000, 1),
            PropertySpec("boss_x", "Boss X", float, 0.0, -2.0, 2.0, 0.01),
            PropertySpec("boss_y", "Boss Y", float, 0.55, -2.0, 2.0, 0.01),
        ),
    ),
}


def make_node(type_name: str, *, name: str | None = None) -> EditorNode:
    try:
        spec = NODE_TYPES[type_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported editor node type: {type_name}") from exc
    return EditorNode(
        type=type_name,
        name=name or spec.display_name,
        properties={
            prop.key: prop.default
            for prop in spec.properties
        },
    )


def make_default_root(name: str = "Scene") -> EditorNode:
    return make_node("SceneRoot", name=name)


def property_specs(node_type: str) -> tuple[PropertySpec, ...]:
    spec = NODE_TYPES.get(node_type)
    if spec is None:
        return ()
    return spec.properties

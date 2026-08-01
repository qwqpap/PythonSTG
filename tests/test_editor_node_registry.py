import pytest

from src.editor.document import EditorNode
from src.editor.node_types import (
    NODE_TYPE_REGISTRY,
    NodeTypeRegistry,
    NodeTypeSpec,
    PropertySpec,
    ViewportSpec,
    make_node,
)


def test_default_registry_contains_semantic_m0_node_types():
    assert {"Stage", "Boss", "Spell", "Emitter", "PatternInstance"}.issubset(
        NODE_TYPE_REGISTRY
    )
    pattern = NODE_TYPE_REGISTRY["PatternInstance"]
    pattern_property = next(prop for prop in pattern.properties if prop.key == "pattern")
    assert pattern_property.resource_types == ("pystg.pattern",)
    assert pattern_property.editor_hint == "resource"
    assert NODE_TYPE_REGISTRY.can_parent("Spell", "Emitter")
    assert NODE_TYPE_REGISTRY.can_parent("Emitter", "PatternInstance")
    assert not NODE_TYPE_REGISTRY.can_parent("PatternInstance", "Emitter")


def test_registered_node_supplies_schema_viewport_validation_and_runtime_compiler():
    registry = NodeTypeRegistry()
    compiled = object()
    validated = []
    spec = NodeTypeSpec(
        type_name="Custom",
        display_name="Custom Node",
        color="#ffffff",
        properties=(
            PropertySpec(
                "speed",
                "Speed",
                float,
                2.0,
                0.0,
                30.0,
                0.1,
                unit="game units/s",
                group="Motion",
                curve_capable=True,
                binding_capable=True,
            ),
        ),
        viewport=ViewportSpec(shape="circle", label="C"),
        allowed_parents=(),
        allowed_children=(),
        validator=lambda node: validated.append(node.name),
        editor_factory=lambda: "editor",
        runtime_compiler=lambda node, context: compiled,
    )
    registry.register(spec)
    node = EditorNode(type="Custom", name="Example", properties={"speed": 3.0})

    registry.validate_node(node)
    assert validated == ["Example"]
    assert registry["Custom"].viewport.shape == "circle"
    assert registry["Custom"].editor_factory() == "editor"
    assert registry.compile_node(node) is compiled
    with pytest.raises(ValueError, match="Duplicate"):
        registry.register(spec)
    with pytest.raises(KeyError, match="Unknown"):
        registry["Missing"]


def test_registry_rejects_invalid_relationships_and_unknown_properties():
    root = make_node("SceneRoot")
    boss = make_node("Boss")
    pattern = make_node("PatternInstance")
    root.children.append(boss)
    boss.children.append(pattern)
    NODE_TYPE_REGISTRY.validate_tree(root)

    pattern.children.append(make_node("Emitter"))
    with pytest.raises(ValueError, match="cannot be a child"):
        NODE_TYPE_REGISTRY.validate_tree(root)

    bad = make_node("Emitter")
    bad.properties["mystery"] = 1
    with pytest.raises(ValueError, match="unknown properties"):
        NODE_TYPE_REGISTRY.validate_node(bad)

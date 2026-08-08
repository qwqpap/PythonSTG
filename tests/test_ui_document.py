"""E6.1 frozen acceptance: typed UI documents, anchors, containers, bindings.

These tests are the completion gate for the UI document half of E6.1 and must
pass exactly as written. Do not edit, skip, or xfail them; implement the
contracts in ``docs/EDITOR_ROADMAP_TODO.md`` (M6 frozen contracts) instead.

Contract summary:
- ``src/ui/document.py`` exposes ``UIDocument``, ``UIDocumentNode``,
  ``UICompileError``, and ``ANIMATABLE_PROPERTIES``.
- Node types: node, text, rect, bar, image, panel, container_h,
  container_v, container_grid. Every node has a stable UUID ``id``.
- Legacy UINode trees without a typed header load via ``from_dict`` with an
  auto-generated envelope.
- ``calculate_layout(viewport_width, viewport_height)`` computes absolute
  rectangles per the anchor/container rules in the roadmap.
"""

import json
from dataclasses import replace

import pytest

from src.authoring import ResourceStore, build_default_resource_type_registry
from src.core.project_context import ProjectContext
from src.ui.document import (
    ANIMATABLE_PROPERTIES,
    UICompileError,
    UIDocument,
    UIDocumentNode,
)
from src.ui.components import UINode, TextNode


def _document():
    return UIDocument.new("HUD")


def _text(name="label", x=0.0, y=0.0, **kwargs):
    values = {
        "node_type": "text",
        "name": name,
        "x": x,
        "y": y,
        "width": 100.0,
        "height": 30.0,
        "text": "Hello",
    }
    values.update(kwargs)
    return UIDocumentNode(**values)


# --------------------------------------------------------------------------
# Envelope and round-trip
# --------------------------------------------------------------------------


def test_ui_document_has_typed_envelope():
    document = _document()

    assert document.type == "pystg.ui"
    assert document.schema_version >= 1
    assert document.id
    assert document.name == "HUD"

    payload = json.loads(json.dumps(document.to_dict()))
    reloaded = UIDocument.from_dict(payload)
    assert reloaded.id == document.id
    assert reloaded.type == "pystg.ui"
    assert reloaded.root is not None


def test_ui_nodes_round_trip_with_stable_uuids():
    document = _document()
    root = UIDocumentNode(node_type="panel", name="root")
    child = _text("label")
    root.add_child(child)
    document.root = root

    reloaded = UIDocument.from_dict(
        json.loads(json.dumps(document.to_dict()))
    )

    assert reloaded.root.id == root.id
    assert reloaded.root.children[0].id == child.id
    assert reloaded.root.children[0].name == "label"
    assert reloaded.root.children[0].node_type == "text"


def test_legacy_ui_tree_json_imports_with_generated_header():
    legacy = TextNode(name="legacy", text="Hi", x=5.0, y=6.0)
    legacy.add_child(UINode(name="box", width=40.0, height=20.0))
    payload = json.loads(json.dumps(legacy.to_dict()))

    document = UIDocument.from_dict(payload)

    assert document.type == "pystg.ui"
    assert document.id
    assert document.root.name == "legacy"
    assert document.root.node_type == "text"
    assert document.root.children[0].name == "box"
    round_trip = UIDocument.from_dict(
        json.loads(json.dumps(document.to_dict()))
    )
    assert round_trip.id == document.id
    assert round_trip.root.id == document.root.id


def test_ui_document_loads_through_the_typed_registry(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    project = ProjectContext(tmp_path)
    document = _document()
    ResourceStore(project).save(document, "game_content/ui/hud.pystg.json")

    loaded = ResourceStore(project).load("game_content/ui/hud.pystg.json")
    assert isinstance(loaded, UIDocument)
    assert loaded.id == document.id

    registry = build_default_resource_type_registry()
    typed = registry.load(document.to_dict())
    assert isinstance(typed, UIDocument)


def test_ui_document_rejects_unknown_node_types():
    document = _document()
    document.root = UIDocumentNode(node_type="mystery", name="bad")

    with pytest.raises(UICompileError) as caught:
        document.validate()

    assert caught.value.diagnostics[0].code == "unknown_ui_node_type"
    assert "mystery" in caught.value.diagnostics[0].message


def test_ui_document_rejects_duplicate_node_ids():
    document = _document()
    root = UIDocumentNode(node_type="panel", name="root")
    first = _text("a")
    second = UIDocumentNode(
        node_type="text", name="b", text="x", id=first.id
    )
    root.add_child(first)
    root.add_child(second)
    document.root = root

    with pytest.raises(UICompileError):
        document.validate()


# --------------------------------------------------------------------------
# Anchors and margins
# --------------------------------------------------------------------------


def test_default_anchors_keep_legacy_absolute_positions():
    document = _document()
    root = UIDocumentNode(node_type="panel", name="root")
    child = _text("t", x=10.0, y=20.0)
    root.add_child(child)
    document.root = root

    layout = document.calculate_layout(384, 448)

    assert layout[child.id] == (10.0, 20.0, 100.0, 30.0)


def test_margins_shift_top_left_anchored_nodes():
    document = _document()
    root = UIDocumentNode(node_type="panel", name="root")
    child = _text("t", x=0.0, y=0.0, margins=(5.0, 0.0, 8.0, 0.0))
    root.add_child(child)
    document.root = root

    layout = document.calculate_layout(384, 448)

    assert layout[child.id][:2] == (5.0, 8.0)


def test_right_anchor_binds_to_parent_width():
    document = _document()
    root = UIDocumentNode(node_type="panel", name="root")
    child = _text(
        "t",
        x=0.0,
        y=0.0,
        width=50.0,
        anchors=(False, True, True, False),
        margins=(0.0, 10.0, 0.0, 0.0),
    )
    root.add_child(child)
    document.root = root

    layout = document.calculate_layout(384, 448)

    assert layout[child.id][0] == 384.0 - 50.0 - 10.0


def test_bottom_anchor_binds_to_parent_height():
    document = _document()
    root = UIDocumentNode(node_type="panel", name="root")
    child = _text(
        "t",
        x=0.0,
        y=0.0,
        height=20.0,
        anchors=(True, False, False, True),
        margins=(0.0, 0.0, 0.0, 4.0),
    )
    root.add_child(child)
    document.root = root

    layout = document.calculate_layout(384, 448)

    assert layout[child.id][1] == 448.0 - 20.0 - 4.0


def test_horizontal_stretch_when_both_h_anchors_set():
    document = _document()
    root = UIDocumentNode(node_type="panel", name="root")
    child = _text(
        "t",
        width=10.0,
        anchors=(True, True, True, False),
        margins=(4.0, 6.0, 6.0, 0.0),
    )
    root.add_child(child)
    document.root = root

    layout = document.calculate_layout(384, 448)

    assert layout[child.id] == (4.0, 6.0, 384.0 - 4.0 - 6.0, 30.0)


def test_vertical_stretch_when_both_v_anchors_set():
    document = _document()
    root = UIDocumentNode(node_type="panel", name="root")
    child = _text(
        "t",
        height=10.0,
        anchors=(True, False, True, True),
        margins=(0.0, 0.0, 2.0, 3.0),
    )
    root.add_child(child)
    document.root = root

    layout = document.calculate_layout(384, 448)

    assert layout[child.id] == (0.0, 2.0, 100.0, 448.0 - 2.0 - 3.0)


# --------------------------------------------------------------------------
# Containers
# --------------------------------------------------------------------------


def test_horizontal_container_stacks_children_with_gap():
    document = _document()
    container = UIDocumentNode(
        node_type="container_h",
        name="row",
        padding=5.0,
        gap=10.0,
    )
    container.add_child(_text("a", width=20.0))
    container.add_child(_text("b", width=30.0))
    container.add_child(_text("c", width=40.0))
    document.root = container

    layout = document.calculate_layout(384, 448)

    a, b, c = [layout[child.id][0] for child in container.children]
    assert (a, b, c) == (5.0, 35.0, 75.0)


def test_vertical_container_stacks_children_with_gap():
    document = _document()
    container = UIDocumentNode(
        node_type="container_v",
        name="col",
        padding=5.0,
        gap=4.0,
    )
    container.add_child(_text("a", height=10.0))
    container.add_child(_text("b", height=10.0))
    document.root = container

    layout = document.calculate_layout(384, 448)

    a_y, b_y = [layout[child.id][1] for child in container.children]
    assert (a_y, b_y) == (5.0, 19.0)


def test_grid_container_fills_rows_with_fixed_columns():
    document = _document()
    grid = UIDocumentNode(
        node_type="container_grid",
        name="grid",
        padding=5.0,
        gap=5.0,
        columns=2,
    )
    grid.add_child(_text("a", width=10.0, height=10.0))
    grid.add_child(_text("b", width=10.0, height=10.0))
    grid.add_child(_text("c", width=10.0, height=10.0))
    document.root = grid

    layout = document.calculate_layout(384, 448)

    positions = [layout[child.id][:2] for child in grid.children]
    assert positions == [(5.0, 5.0), (20.0, 5.0), (5.0, 20.0)]


# --------------------------------------------------------------------------
# Bindings, styles, and animatable properties
# --------------------------------------------------------------------------


def test_binding_expression_is_evaluated_at_render_time():
    document = _document()
    root = UIDocumentNode(node_type="panel", name="root")
    child = _text("t", bindings={"alpha": "value"})
    root.add_child(child)
    document.root = root

    elements = document.get_render_elements(value=0.5)

    assert elements[0]["alpha"] == pytest.approx(0.5)


def test_invalid_binding_expression_raises_structured_diagnostic():
    document = _document()
    root = UIDocumentNode(node_type="panel", name="root")
    child = _text("t", bindings={"alpha": "frame + __import__('os')"})
    root.add_child(child)
    document.root = root

    with pytest.raises(UICompileError) as caught:
        document.get_render_elements()

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "invalid_binding"
    assert "alpha" in diagnostic.path


def test_style_reference_is_preserved_and_validated():
    document = _document()
    root = UIDocumentNode(
        node_type="panel", name="root", style="res://game_content/ui/theme.pystg.json"
    )
    document.root = root

    reloaded = UIDocument.from_dict(
        json.loads(json.dumps(document.to_dict()))
    )
    assert reloaded.root.style == "res://game_content/ui/theme.pystg.json"


def test_every_node_type_has_animatable_properties():
    node_types = {
        "node",
        "text",
        "rect",
        "bar",
        "image",
        "panel",
        "container_h",
        "container_v",
        "container_grid",
    }
    assert set(ANIMATABLE_PROPERTIES) == node_types
    for node_type, properties in ANIMATABLE_PROPERTIES.items():
        assert properties, f"{node_type} needs at least one animatable property"
        assert "alpha" in properties, f"{node_type} alpha must be animatable"
    assert "value" in ANIMATABLE_PROPERTIES["bar"]
    assert "text" in ANIMATABLE_PROPERTIES["text"]

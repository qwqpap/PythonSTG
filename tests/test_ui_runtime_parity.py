"""Formal renderer regression behavior for every UI node.

These tests lock the renderer protocol consumed by ``UIRenderer.render_hud``
(text / rect / bar / textured_rect records) and the parity between the typed
UIDocument and the legacy ``UITree.get_render_list`` output.
"""

import pytest

from src.ui.components import BarNode, ImageNode, PanelNode, RectNode, TextNode, UINode
from src.ui.document import UIDocument, UIDocumentNode
from src.ui.ui_tree import UITree


class RecordingUIRenderer:
    """Fake renderer recording render_hud protocol calls."""

    def __init__(self):
        self.calls = []

    def render_text(self, **kwargs):
        self.calls.append(("text", kwargs))

    def render_rect(self, **kwargs):
        self.calls.append(("rect", kwargs))

    def render_bar(self, **kwargs):
        self.calls.append(("bar", kwargs))

    def render_textured_rect(self, **kwargs):
        self.calls.append(("textured_rect", kwargs))


def _legacy_tree():
    root = PanelNode(name="root", width=384.0, height=448.0)
    root.add_child(TextNode(name="title", x=8.0, y=8.0, text="T", scale=2.0))
    root.add_child(RectNode(name="box", x=8.0, y=40.0, width=64.0, height=16.0))
    root.add_child(
        BarNode(name="hp", x=8.0, y=64.0, width=128.0, height=8.0, value=0.6)
    )
    root.add_child(ImageNode(name="icon", x=8.0, y=80.0, width=16.0, height=16.0, texture="assets/images/icon.png"))
    return UITree(root)


def _typed_document_from(tree):
    document = UIDocument.new("HUD")
    document.root = _convert(tree.root)
    return document


def _convert(node):
    mapping = {
        "node": "node",
        "text": "text",
        "rect": "rect",
        "bar": "bar",
        "image": "image",
        "panel": "panel",
    }
    converted = UIDocumentNode(
        node_type=mapping[node.node_type],
        name=node.name,
        x=node.x,
        y=node.y,
        width=node.width,
        height=node.height,
        visible=node.visible,
    )
    if isinstance(node, TextNode):
        converted.text = node.text
        converted.font = node.font
        converted.color = list(node.color)
        converted.scale = node.scale
        converted.alpha = node.alpha
        converted.align = node.align
    elif isinstance(node, RectNode):
        converted.color = list(node.color)
        converted.alpha = node.alpha
        converted.border = node.border
    elif isinstance(node, BarNode):
        converted.value = node.value
        converted.color_bg = list(node.color_bg)
        converted.color_fill = list(node.color_fill)
        converted.alpha = node.alpha
    elif isinstance(node, ImageNode):
        converted.texture = node.texture
        converted.uv = list(node.uv)
        converted.alpha = node.alpha
    elif isinstance(node, PanelNode):
        converted.padding = node.padding
        converted.gap = node.gap
        converted.bg_color = list(node.bg_color)
        converted.bg_alpha = node.bg_alpha
    for child in node.children:
        converted.add_child(_convert(child))
    return converted


def test_typed_document_parity_with_legacy_render_list():
    legacy = _legacy_tree()
    document = _typed_document_from(legacy)

    legacy_elements = legacy.get_render_list()
    typed_elements = document.get_render_elements()

    assert len(typed_elements) == len(legacy_elements)
    for typed, legacy in zip(typed_elements, legacy_elements):
        assert typed["type"] == legacy["type"]
        assert typed["position"] == legacy["position"]
        if "width" in legacy:
            assert typed["width"] == legacy["width"]
        if "height" in legacy:
            assert typed["height"] == legacy["height"]


def test_every_node_type_produces_a_render_record():
    cases = [
        ("node", {}, ["text"]),
        ("text", {}, []),
        ("rect", {"width": 10.0, "height": 10.0}, []),
        ("bar", {"width": 10.0, "height": 10.0, "value": 0.5}, []),
        ("image", {"width": 10.0, "height": 10.0, "texture": "assets/x.png"}, []),
        ("panel", {"width": 10.0, "height": 10.0, "bg_alpha": 0.5}, []),
        ("container_h", {"width": 10.0, "height": 10.0}, ["text"]),
        ("container_v", {"width": 10.0, "height": 10.0}, ["text"]),
        ("container_grid", {"width": 10.0, "height": 10.0, "columns": 2}, ["text"]),
    ]
    for node_type, extra, child_types in cases:
        document = UIDocument.new("X")
        node = UIDocumentNode(node_type=node_type, name="n", **extra)
        for child_type in child_types:
            node.add_child(
                UIDocumentNode(node_type=child_type, name="c", text="c")
            )
        document.root = node
        elements = document.get_render_elements()
        assert elements, f"{node_type} must emit render records"


def test_image_maps_to_textured_rect_with_texture_path():
    document = UIDocument.new("X")
    node = UIDocumentNode(
        node_type="image",
        name="icon",
        width=16.0,
        height=16.0,
        texture="assets/images/icon.png",
    )
    document.root = node

    elements = document.get_render_elements()

    assert elements[0]["type"] == "textured_rect"
    assert elements[0]["texture_path"] == "assets/images/icon.png"
    assert elements[0]["width"] == 16.0
    assert elements[0]["height"] == 16.0


def test_panel_emits_background_rect_when_bg_alpha_positive():
    document = UIDocument.new("X")
    node = UIDocumentNode(
        node_type="panel",
        name="p",
        width=100.0,
        height=50.0,
        bg_alpha=0.8,
        bg_color=(1, 2, 3),
    )
    document.root = node

    elements = document.get_render_elements()

    assert elements[0]["type"] == "rect"
    assert elements[0]["alpha"] == pytest.approx(0.8)


def test_container_layout_positions_children_in_render_output():
    document = UIDocument.new("X")
    row = UIDocumentNode(node_type="container_h", name="row", padding=5.0, gap=10.0)
    row.add_child(UIDocumentNode(node_type="text", name="a", width=20.0, text="a"))
    row.add_child(UIDocumentNode(node_type="text", name="b", width=30.0, text="b"))
    document.root = row

    elements = document.get_render_elements()

    assert elements[0]["position"][0] == pytest.approx(5.0)
    assert elements[1]["position"][0] == pytest.approx(35.0)


def test_renderer_consumes_typed_document_output():
    document = _typed_document_from(_legacy_tree())
    renderer = RecordingUIRenderer()

    for element in document.get_render_elements():
        record = dict(element)
        element_type = record.pop("type")
        if element_type == "text":
            renderer.render_text(**record)
        elif element_type == "rect":
            renderer.render_rect(**record)
        elif element_type == "bar":
            renderer.render_bar(**record)
        elif element_type == "textured_rect":
            renderer.render_textured_rect(**record)

    kinds = [kind for kind, _ in renderer.calls]
    assert "text" in kinds
    assert "rect" in kinds
    assert "bar" in kinds
    assert "textured_rect" in kinds


def test_hidden_nodes_are_excluded_from_render_output():
    document = UIDocument.new("X")
    root = UIDocumentNode(node_type="panel", name="root")
    root.add_child(UIDocumentNode(node_type="text", name="shown", text="s"))
    hidden = UIDocumentNode(node_type="text", name="hidden", text="h", visible=False)
    root.add_child(hidden)
    document.root = root

    elements = document.get_render_elements()

    assert [element.get("text") for element in elements] == ["s"]

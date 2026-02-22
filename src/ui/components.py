"""
Unified UI component tree model

All UI elements are described as a tree of UINode instances.
The tree can be serialized to/from JSON, enabling visual editor workflows.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any


@dataclass
class UINode:
    """Base UI node."""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    visible: bool = True
    children: List['UINode'] = field(default_factory=list)
    parent: Optional['UINode'] = field(default=None, repr=False)
    node_type: str = "node"
    name: str = ""

    def add_child(self, child: 'UINode'):
        child.parent = self
        self.children.append(child)

    def remove_child(self, child: 'UINode'):
        if child in self.children:
            child.parent = None
            self.children.remove(child)

    def walk(self):
        """Depth-first traversal yielding (node, depth)."""
        stack = [(self, 0)]
        while stack:
            node, depth = stack.pop()
            yield node, depth
            for child in reversed(node.children):
                stack.append((child, depth + 1))

    def to_dict(self) -> dict:
        d: Dict[str, Any] = {
            "type": self.node_type,
            "name": self.name,
            "x": self.x, "y": self.y,
            "width": self.width, "height": self.height,
            "visible": self.visible,
        }
        self._serialize_extra(d)
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d

    def _serialize_extra(self, d: dict):
        pass

    @classmethod
    def from_dict(cls, d: dict) -> 'UINode':
        node_type = d.get("type", "node")
        factory = _NODE_REGISTRY.get(node_type, UINode)
        node = factory.__new__(factory)
        node.x = d.get("x", 0.0)
        node.y = d.get("y", 0.0)
        node.width = d.get("width", 0.0)
        node.height = d.get("height", 0.0)
        node.visible = d.get("visible", True)
        node.name = d.get("name", "")
        node.node_type = node_type
        node.parent = None
        node.children = []
        node._deserialize_extra(d)
        for cd in d.get("children", []):
            child = UINode.from_dict(cd)
            node.add_child(child)
        return node

    def _deserialize_extra(self, d: dict):
        pass


@dataclass
class TextNode(UINode):
    text: str = ""
    font: str = "default"
    color: Tuple[int, int, int] = (255, 255, 255)
    scale: float = 1.0
    alpha: float = 1.0
    align: str = "left"
    node_type: str = field(default="text", init=False)

    def _serialize_extra(self, d: dict):
        d.update(text=self.text, font=self.font, color=list(self.color),
                 scale=self.scale, alpha=self.alpha, align=self.align)

    def _deserialize_extra(self, d: dict):
        self.text = d.get("text", "")
        self.font = d.get("font", "default")
        self.color = tuple(d.get("color", [255, 255, 255]))
        self.scale = d.get("scale", 1.0)
        self.alpha = d.get("alpha", 1.0)
        self.align = d.get("align", "left")


@dataclass
class RectNode(UINode):
    color: Tuple[int, int, int] = (0, 0, 0)
    alpha: float = 1.0
    border: int = 0
    node_type: str = field(default="rect", init=False)

    def _serialize_extra(self, d: dict):
        d.update(color=list(self.color), alpha=self.alpha, border=self.border)

    def _deserialize_extra(self, d: dict):
        self.color = tuple(d.get("color", [0, 0, 0]))
        self.alpha = d.get("alpha", 1.0)
        self.border = d.get("border", 0)


@dataclass
class BarNode(UINode):
    value: float = 0.0
    color_bg: Tuple[int, int, int] = (32, 32, 32)
    color_fill: Tuple[int, int, int] = (255, 255, 255)
    alpha: float = 1.0
    node_type: str = field(default="bar", init=False)

    def _serialize_extra(self, d: dict):
        d.update(value=self.value, color_bg=list(self.color_bg),
                 color_fill=list(self.color_fill), alpha=self.alpha)

    def _deserialize_extra(self, d: dict):
        self.value = d.get("value", 0.0)
        self.color_bg = tuple(d.get("color_bg", [32, 32, 32]))
        self.color_fill = tuple(d.get("color_fill", [255, 255, 255]))
        self.alpha = d.get("alpha", 1.0)


@dataclass
class ImageNode(UINode):
    texture: str = ""
    uv: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    alpha: float = 1.0
    node_type: str = field(default="image", init=False)

    def _serialize_extra(self, d: dict):
        d.update(texture=self.texture, uv=list(self.uv), alpha=self.alpha)

    def _deserialize_extra(self, d: dict):
        self.texture = d.get("texture", "")
        self.uv = tuple(d.get("uv", [0, 0, 1, 1]))
        self.alpha = d.get("alpha", 1.0)


@dataclass
class PanelNode(UINode):
    padding: float = 0.0
    gap: float = 0.0
    bg_color: Tuple[int, int, int] = (0, 0, 0)
    bg_alpha: float = 0.0
    node_type: str = field(default="panel", init=False)

    def _serialize_extra(self, d: dict):
        d.update(padding=self.padding, gap=self.gap,
                 bg_color=list(self.bg_color), bg_alpha=self.bg_alpha)

    def _deserialize_extra(self, d: dict):
        self.padding = d.get("padding", 0.0)
        self.gap = d.get("gap", 0.0)
        self.bg_color = tuple(d.get("bg_color", [0, 0, 0]))
        self.bg_alpha = d.get("bg_alpha", 0.0)


# Registry for deserialization
_NODE_REGISTRY: Dict[str, type] = {
    "node": UINode,
    "text": TextNode,
    "rect": RectNode,
    "bar": BarNode,
    "image": ImageNode,
    "panel": PanelNode,
}

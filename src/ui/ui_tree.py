"""
UI tree manager

Manages a root UINode tree. Supports:
- Recursive traversal for rendering
- JSON serialization / deserialization
"""

import json
from typing import Optional, List, Callable
from .components import UINode


class UITree:
    """Manages a tree of UINode instances."""

    def __init__(self, root: Optional[UINode] = None):
        self.root = root or UINode(name="root")

    def walk(self):
        """Depth-first iterator yielding (node, depth)."""
        if self.root:
            yield from self.root.walk()

    def find(self, name: str) -> Optional[UINode]:
        """Find first node with given name."""
        for node, _ in self.walk():
            if node.name == name:
                return node
        return None

    def find_all(self, node_type: str) -> List[UINode]:
        """Find all nodes of given type."""
        return [n for n, _ in self.walk() if n.node_type == node_type]

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.root.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'UITree':
        d = json.loads(json_str)
        return cls(root=UINode.from_dict(d))

    def save(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> 'UITree':
        with open(path, 'r', encoding='utf-8') as f:
            return cls.from_json(f.read())

    def get_render_list(self) -> list:
        """
        Flatten visible nodes into a render-order list of dicts
        compatible with UIRenderer.render_hud().
        """
        result = []
        if not self.root:
            return result

        self._flatten_node(self.root, 0.0, 0.0, result)
        return result

    def _flatten_node(self, node: UINode, offset_x: float, offset_y: float, out: list):
        if not node.visible:
            return

        abs_x = offset_x + node.x
        abs_y = offset_y + node.y

        if node.node_type == "text":
            out.append({
                'type': 'text',
                'text': node.text,
                'position': (abs_x, abs_y),
                'font': node.font,
                'scale': node.scale,
                'color': node.color,
                'alpha': node.alpha,
                'align': node.align,
            })
        elif node.node_type == "rect":
            out.append({
                'type': 'rect',
                'position': (abs_x, abs_y),
                'width': node.width,
                'height': node.height,
                'color': node.color,
                'alpha': node.alpha,
            })
        elif node.node_type == "bar":
            out.append({
                'type': 'bar',
                'position': (abs_x, abs_y),
                'width': node.width,
                'height': node.height,
                'value': node.value,
                'color_bg': node.color_bg,
                'color_fill': node.color_fill,
                'alpha': node.alpha,
            })
        elif node.node_type == "panel":
            if node.bg_alpha > 0:
                out.append({
                    'type': 'rect',
                    'position': (abs_x, abs_y),
                    'width': node.width,
                    'height': node.height,
                    'color': node.bg_color,
                    'alpha': node.bg_alpha,
                })

        for child in node.children:
            self._flatten_node(child, abs_x, abs_y, out)

"""Typed UI authoring documents with anchors, containers, and bindings.

Established UI authoring contract:

- ``UIDocument`` carries the typed ``pystg.ui`` envelope plus a ``root`` tree
  of ``UIDocumentNode`` values with stable UUIDs.
- Node types: node, text, rect, bar, image, panel, container_h,
  container_v, container_grid.
- Legacy UINode trees without a typed header import via ``from_dict`` with an
  auto-generated envelope.
- ``calculate_layout`` applies the anchor/margin/container rules; the layout
  result feeds ``get_render_elements`` which emits the formal renderer
  protocol consumed by ``UIRenderer.render_hud``.
- Bindings are restricted expressions (M5 whitelist) evaluated with a context
  of ``frame``, ``time``, and the document variable ``value``.
"""

from __future__ import annotations

import copy
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

from src.authoring.resources import (
    RESOURCE_SCHEMA_VERSION,
    UI_RESOURCE_TYPE,
    ResourceDocumentError,
    ResourceHeader,
    new_resource_id,
)
from src.pattern.expressions import ExpressionError, compile_expression

UI_NODE_TYPES = (
    "node",
    "text",
    "rect",
    "bar",
    "image",
    "panel",
    "container_h",
    "container_v",
    "container_grid",
)

#: Variables available to UI binding expressions beyond the pattern set.
UI_BINDING_VARIABLES = frozenset({"value"})

_KNOWN_FIELDS = {
    "id",
    "type",
    "name",
    "x",
    "y",
    "width",
    "height",
    "visible",
    "anchors",
    "margins",
    "style",
    "bindings",
    "animatable",
    "children",
    "text",
    "font",
    "color",
    "scale",
    "alpha",
    "align",
    "border",
    "value",
    "color_bg",
    "color_fill",
    "texture",
    "uv",
    "padding",
    "gap",
    "bg_color",
    "bg_alpha",
    "columns",
}


class UICompileError(ValueError):
    """Structured UI document validation/compile failure."""

    def __init__(self, diagnostics: tuple["UIDiagnostic", ...]):
        self.diagnostics = diagnostics
        super().__init__(
            "; ".join(
                f"{item.path}: {item.message}" for item in diagnostics
            )
            or "ui compilation failed"
        )


@dataclass(frozen=True)
class UIDiagnostic:
    severity: str
    code: str
    path: str
    message: str


def _diagnostic(code: str, path: str, message: str) -> UIDiagnostic:
    return UIDiagnostic(severity="error", code=code, path=path, message=message)


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UICompileError((_diagnostic("invalid_ui_property", path, "must be a number"),))
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise UICompileError(
            (_diagnostic("invalid_ui_property", path, "must be a finite number"),)
        ) from exc
    if not math.isfinite(result):
        raise UICompileError((_diagnostic("invalid_ui_property", path, "must be finite"),))
    return result


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise UICompileError((_diagnostic("invalid_ui_property", path, "must be a boolean"),))
    return value


def _sequence(value: Any, path: str, length: int) -> list[Any] | tuple[Any, ...]:
    """Read a fixed-size JSON array without coercing malformed values."""
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise UICompileError(
            (_diagnostic("invalid_ui_property", path, f"must contain {length} values"),)
        )
    return value


def _bool_sequence(value: Any, path: str, length: int) -> tuple[bool, ...]:
    values = _sequence(value, path, length)
    if any(not isinstance(item, bool) for item in values):
        raise UICompileError(
            (_diagnostic("invalid_ui_property", path, "must contain booleans"),)
        )
    return tuple(values)


def _number_sequence(value: Any, path: str, length: int) -> tuple[float, ...]:
    values = _sequence(value, path, length)
    return tuple(_number(item, f"{path}[{index}]") for index, item in enumerate(values))


def _color(value: Any, path: str) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)) or len(value) not in {3, 4}:
        raise UICompileError(
            (_diagnostic("invalid_ui_property", path, "must contain three or four channels"),)
        )
    channels: list[int] = []
    for index, channel in enumerate(value):
        if (
            isinstance(channel, bool)
            or not isinstance(channel, int)
            or not 0 <= channel <= 255
        ):
            raise UICompileError(
                (
                    _diagnostic(
                        "invalid_ui_property",
                        f"{path}[{index}]",
                        "must be an integer in 0..255",
                    ),
                )
            )
        channels.append(channel)
    return tuple(channels)


def _integer(value: Any, path: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UICompileError((_diagnostic("invalid_ui_property", path, "must be an integer"),))
    if minimum is not None and value < minimum:
        raise UICompileError(
            (_diagnostic("invalid_ui_property", path, f"must be >= {minimum}"),)
        )
    return value


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


@dataclass
class UIDocumentNode:
    """One UI node in the authoring tree."""

    node_type: str = "node"
    name: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    visible: bool = True
    anchors: tuple[bool, bool, bool, bool] = (True, False, True, False)
    margins: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    style: str | None = None
    bindings: dict[str, str] = field(default_factory=dict)
    animatable: bool = False
    children: list["UIDocumentNode"] = field(default_factory=list)
    parent: "UIDocumentNode | None" = field(default=None, repr=False)

    # text
    text: str = ""
    font: str = "default"
    color: tuple[int, int, int] = (255, 255, 255)
    scale: float = 1.0
    alpha: float = 1.0
    align: str = "left"

    # rect / panel
    border: int = 0
    bg_color: tuple[int, int, int] = (0, 0, 0)
    bg_alpha: float = 0.0

    # bar
    value: float = 0.0
    color_bg: tuple[int, int, int] = (32, 32, 32)
    color_fill: tuple[int, int, int] = (255, 255, 255)

    # image
    texture: str = ""
    uv: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

    # panel / containers
    padding: float = 0.0
    gap: float = 0.0
    columns: int = 1

    def add_child(self, child: "UIDocumentNode") -> None:
        child.parent = self
        self.children.append(child)

    def remove_child(self, child: "UIDocumentNode") -> None:
        if child in self.children:
            child.parent = None
            self.children.remove(child)

    def walk(self):
        stack = [(self, 0)]
        while stack:
            node, depth = stack.pop()
            yield node, depth
            for child in reversed(node.children):
                stack.append((child, depth + 1))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.node_type,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "visible": self.visible,
            "anchors": list(self.anchors),
            "margins": list(self.margins),
            "animatable": self.animatable,
        }
        if self.style is not None:
            payload["style"] = self.style
        if self.bindings:
            payload["bindings"] = dict(self.bindings)
        if self.node_type == "text":
            payload.update(
                text=self.text,
                font=self.font,
                color=list(self.color),
                scale=self.scale,
                alpha=self.alpha,
                align=self.align,
            )
        elif self.node_type == "rect":
            payload.update(
                color=list(self.color), alpha=self.alpha, border=self.border
            )
        elif self.node_type == "bar":
            payload.update(
                value=self.value,
                color_bg=list(self.color_bg),
                color_fill=list(self.color_fill),
                alpha=self.alpha,
            )
        elif self.node_type == "image":
            payload.update(
                texture=self.texture, uv=list(self.uv), alpha=self.alpha
            )
        elif self.node_type == "panel":
            payload.update(
                padding=self.padding,
                gap=self.gap,
                bg_color=list(self.bg_color),
                bg_alpha=self.bg_alpha,
            )
        elif self.node_type in {"container_h", "container_v"}:
            payload.update(padding=self.padding, gap=self.gap)
        elif self.node_type == "container_grid":
            payload.update(padding=self.padding, gap=self.gap, columns=self.columns)
        if self.children:
            payload["children"] = [child.to_dict() for child in self.children]
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "UIDocumentNode":
        """Decode one node and normalize malformed input to UICompileError."""
        try:
            return cls._from_dict_impl(value)
        except UICompileError:
            raise
        except (TypeError, ValueError, KeyError, IndexError, OverflowError) as exc:
            name = value.get("name", "") if isinstance(value, Mapping) else ""
            raise UICompileError(
                (_diagnostic("invalid_ui_node", f"ui:{name}", str(exc)),)
            ) from exc

    @classmethod
    def _from_dict_impl(cls, value: Mapping[str, Any]) -> "UIDocumentNode":
        if not isinstance(value, Mapping):
            raise UICompileError((_diagnostic("invalid_ui_node", "ui", "must be an object"),))
        unknown = set(value).difference(_KNOWN_FIELDS)
        if unknown:
            raise UICompileError(
                (
                    _diagnostic(
                        "unknown_ui_field",
                        f"ui:{value.get('name', '')}",
                        "unknown fields: " + ", ".join(sorted(unknown)),
                    ),
                )
            )
        raw_node_type = value.get("type", "node")
        if not isinstance(raw_node_type, str) or not raw_node_type.strip():
            raise UICompileError(
                (_diagnostic("invalid_ui_node", "ui.type", "must be a non-empty string"),)
            )
        node_type = raw_node_type
        node = cls(node_type=node_type)
        raw_id = value.get("id")
        if raw_id is not None and not isinstance(raw_id, str):
            raise UICompileError(
                (_diagnostic("invalid_ui_property", "ui.id", "must be a UUID string"),)
            )
        node.id = raw_id or node.id
        raw_name = value.get("name", "")
        if not isinstance(raw_name, str):
            raise UICompileError(
                (_diagnostic("invalid_ui_property", "ui.name", "must be text"),)
            )
        node.name = raw_name
        node.x = _number(value.get("x", 0.0), "ui.x")
        node.y = _number(value.get("y", 0.0), "ui.y")
        node.width = _number(value.get("width", 0.0), "ui.width")
        node.height = _number(value.get("height", 0.0), "ui.height")
        node.visible = _boolean(value.get("visible", True), "ui.visible")
        raw_anchors = value.get("anchors")
        if raw_anchors is not None:
            node.anchors = _bool_sequence(raw_anchors, "ui.anchors", 4)
        raw_margins = value.get("margins")
        if raw_margins is not None:
            node.margins = _number_sequence(raw_margins, "ui.margins", 4)
        raw_style = value.get("style")
        if raw_style is not None and not isinstance(raw_style, str):
            raise UICompileError(
                (_diagnostic("invalid_ui_property", "ui.style", "must be text"),)
            )
        node.style = raw_style
        raw_bindings = value.get("bindings", {})
        if not isinstance(raw_bindings, Mapping):
            raise UICompileError(
                (_diagnostic("invalid_ui_property", "ui.bindings", "must be an object"),)
            )
        if any(not isinstance(key, str) or not isinstance(item, str)
               for key, item in raw_bindings.items()):
            raise UICompileError(
                (_diagnostic("invalid_ui_property", "ui.bindings", "keys and expressions must be text"),)
            )
        node.bindings = dict(raw_bindings)
        node.animatable = _boolean(
            value.get("animatable", False), "ui.animatable"
        )
        if node_type == "text":
            node.text = value.get("text", "")
            node.font = value.get("font", "default")
            if not isinstance(node.text, str) or not isinstance(node.font, str):
                raise UICompileError(
                    (_diagnostic("invalid_ui_property", "ui.text", "text and font must be text"),)
                )
            node.color = _color(value.get("color", [255, 255, 255]), "ui.color")
            node.scale = _number(value.get("scale", 1.0), "ui.scale")
            node.alpha = _number(value.get("alpha", 1.0), "ui.alpha")
            node.align = value.get("align", "left")
            if not isinstance(node.align, str):
                raise UICompileError(
                    (_diagnostic("invalid_ui_property", "ui.align", "must be text"),)
                )
        elif node_type == "rect":
            node.color = _color(value.get("color", [0, 0, 0]), "ui.color")
            node.alpha = _number(value.get("alpha", 1.0), "ui.alpha")
            node.border = _integer(value.get("border", 0), "ui.border", minimum=0)
        elif node_type == "bar":
            node.value = _number(value.get("value", 0.0), "ui.value")
            node.color_bg = _color(value.get("color_bg", [32, 32, 32]), "ui.color_bg")
            node.color_fill = _color(value.get("color_fill", [255, 255, 255]), "ui.color_fill")
            node.alpha = _number(value.get("alpha", 1.0), "ui.alpha")
        elif node_type == "image":
            node.texture = value.get("texture", "")
            if not isinstance(node.texture, str):
                raise UICompileError(
                    (_diagnostic("invalid_ui_property", "ui.texture", "must be text"),)
                )
            node.uv = _number_sequence(value.get("uv", [0.0, 0.0, 1.0, 1.0]), "ui.uv", 4)
            node.alpha = _number(value.get("alpha", 1.0), "ui.alpha")
        elif node_type == "panel":
            node.padding = _number(value.get("padding", 0.0), "ui.padding")
            node.gap = _number(value.get("gap", 0.0), "ui.gap")
            node.bg_color = _color(value.get("bg_color", [0, 0, 0]), "ui.bg_color")
            node.bg_alpha = _number(value.get("bg_alpha", 0.0), "ui.bg_alpha")
        elif node_type in {"container_h", "container_v"}:
            node.padding = _number(value.get("padding", 0.0), "ui.padding")
            node.gap = _number(value.get("gap", 0.0), "ui.gap")
        elif node_type == "container_grid":
            node.padding = _number(value.get("padding", 0.0), "ui.padding")
            node.gap = _number(value.get("gap", 0.0), "ui.gap")
            node.columns = _integer(value.get("columns", 1), "ui.columns", minimum=1)
        raw_children = value.get("children", [])
        if not isinstance(raw_children, list):
            raise UICompileError(
                (_diagnostic("invalid_ui_property", "ui.children", "must be an array"),)
            )
        for child_value in raw_children:
            node.add_child(UIDocumentNode.from_dict(child_value))
        return node


ANIMATABLE_PROPERTIES: dict[str, tuple[str, ...]] = {
    "node": ("alpha",),
    "text": ("x", "y", "width", "height", "alpha", "scale", "text"),
    "rect": ("x", "y", "width", "height", "alpha", "color"),
    "bar": ("x", "y", "width", "height", "alpha", "value", "color_fill"),
    "image": ("x", "y", "width", "height", "alpha"),
    "panel": ("x", "y", "width", "height", "alpha", "bg_alpha"),
    "container_h": ("x", "y", "width", "height", "alpha", "gap", "padding"),
    "container_v": ("x", "y", "width", "height", "alpha", "gap", "padding"),
    "container_grid": ("x", "y", "width", "height", "alpha", "gap", "padding", "columns"),
}


def _anchors_text(left: bool, right: bool, top: bool, bottom: bool) -> str:
    return f"l{int(left)}r{int(right)}t{int(top)}b{int(bottom)}"


class UIDocument:
    """Typed UI authoring document."""

    def __init__(self, header: ResourceHeader, root: UIDocumentNode | None = None):
        self.header = header
        self.root = root or UIDocumentNode(node_type="node", name="root")

    @property
    def id(self) -> str:
        return self.header.id

    @property
    def name(self) -> str:
        return self.header.name

    @property
    def type(self) -> str:
        return self.header.type

    @property
    def schema_version(self) -> int:
        return self.header.schema_version

    @classmethod
    def new(cls, name: str = "New UI") -> "UIDocument":
        document = cls(
            header=ResourceHeader(type=UI_RESOURCE_TYPE, name=name, id=new_resource_id()),
            root=UIDocumentNode(node_type="node", name="root"),
        )
        return document

    def validate(self) -> None:
        issues: list[UIDiagnostic] = []
        seen: set[str] = set()
        try:
            self.header.validate(
                expected_type=UI_RESOURCE_TYPE,
                current_version=RESOURCE_SCHEMA_VERSION,
            )
        except ResourceDocumentError as exc:
            issues.append(_diagnostic("invalid_ui_header", "header", str(exc)))
        active: set[int] = set()
        visited_objects: set[int] = set()

        def add_property_issue(path: str, message: str) -> None:
            issues.append(_diagnostic("invalid_ui_property", path, message))

        def visit(node: UIDocumentNode, parent: UIDocumentNode | None) -> None:
            object_id = id(node)
            if object_id in active:
                issues.append(_diagnostic("ui_tree_cycle", f"ui:{node.name}", "child tree contains a cycle"))
                return
            if object_id in visited_objects:
                issues.append(_diagnostic("ui_tree_ownership", f"ui:{node.name}", "node is attached more than once"))
                return
            visited_objects.add(object_id)
            active.add(object_id)
            if node.node_type not in UI_NODE_TYPES:
                issues.append(
                    _diagnostic(
                        "unknown_ui_node_type",
                        f"ui:{node.name}",
                        f"unknown UI node type {node.node_type!r}",
                    )
                )
            if node.id in seen:
                issues.append(
                    _diagnostic(
                        "duplicate_ui_node_id",
                        f"ui:{node.name}",
                        f"duplicate node id {node.id}",
                    )
                )
            seen.add(node.id)
            try:
                uuid.UUID(str(node.id))
            except (ValueError, AttributeError, TypeError):
                add_property_issue(f"ui:{node.name}.id", "must be a UUID")
            if node.parent is not parent:
                add_property_issue(f"ui:{node.name}.parent", "parent ownership is inconsistent")
            if not isinstance(node.name, str) or not node.name.strip():
                add_property_issue(f"ui:{node.name}.name", "must be non-empty text")
            if not isinstance(node.anchors, tuple) or len(node.anchors) != 4 or any(
                not isinstance(item, bool) for item in node.anchors
            ):
                add_property_issue(f"ui:{node.name}.anchors", "must contain four booleans")
            if not isinstance(node.margins, tuple) or len(node.margins) != 4:
                add_property_issue(f"ui:{node.name}.margins", "must contain four numbers")
            else:
                for index, item in enumerate(node.margins):
                    if not _is_finite_number(item):
                        add_property_issue(f"ui:{node.name}.margins[{index}]", "must be finite")
            geometry_values: dict[str, float] = {}
            for property_name, value in (
                ("x", node.x), ("y", node.y), ("width", node.width), ("height", node.height)
            ):
                if not _is_finite_number(value):
                    add_property_issue(f"ui:{node.name}.{property_name}", "must be finite")
                else:
                    geometry_values[property_name] = float(value)
            if geometry_values.get("width", 0.0) < 0 or geometry_values.get("height", 0.0) < 0:
                add_property_issue(f"ui:{node.name}.geometry", "width and height must be non-negative")
            if not isinstance(node.visible, bool):
                add_property_issue(f"ui:{node.name}.visible", "must be a boolean")
            if not isinstance(node.animatable, bool):
                add_property_issue(f"ui:{node.name}.animatable", "must be a boolean")

            def check_color(property_name: str, value: Any) -> None:
                if not isinstance(value, (tuple, list)) or len(value) not in {3, 4}:
                    add_property_issue(
                        f"ui:{node.name}.{property_name}",
                        "must contain three or four color channels",
                    )
                    return
                for channel in value:
                    if (
                        isinstance(channel, bool)
                        or not isinstance(channel, int)
                        or not 0 <= channel <= 255
                    ):
                        add_property_issue(
                            f"ui:{node.name}.{property_name}",
                            "color channels must be integers in 0..255",
                        )
                        break

            if node.node_type in {"text", "rect"}:
                check_color("color", node.color)
            if node.node_type == "bar":
                check_color("color_bg", node.color_bg)
                check_color("color_fill", node.color_fill)
            if node.node_type == "panel":
                check_color("bg_color", node.bg_color)
            if node.node_type == "image":
                if not isinstance(node.texture, str):
                    add_property_issue(f"ui:{node.name}.texture", "must be text")
                if not isinstance(node.uv, (tuple, list)) or len(node.uv) != 4:
                    add_property_issue(f"ui:{node.name}.uv", "must contain four numbers")
                else:
                    for uv in node.uv:
                        if not _is_finite_number(uv):
                            add_property_issue(f"ui:{node.name}.uv", "must contain finite numbers")
                            break
            for property_name in ("alpha", "bg_alpha"):
                if hasattr(node, property_name):
                    value = getattr(node, property_name)
                    if (
                        not _is_finite_number(value)
                        or not 0.0 <= float(value) <= 1.0
                    ):
                        add_property_issue(
                            f"ui:{node.name}.{property_name}",
                            "must be finite and within 0..1",
                        )
            if hasattr(node, "scale") and (
                not _is_finite_number(node.scale)
                or float(node.scale) <= 0
            ):
                add_property_issue(f"ui:{node.name}.scale", "must be finite and positive")
            if node.node_type == "bar" and (
                not _is_finite_number(node.value)
                or not 0.0 <= float(node.value) <= 1.0
            ):
                add_property_issue(f"ui:{node.name}.value", "must be finite and within 0..1")
            if node.node_type == "text" and node.align not in {"left", "center", "right"}:
                add_property_issue(f"ui:{node.name}.align", "must be left/center/right")
            if node.style is not None and (
                not isinstance(node.style, str) or not node.style.startswith("res://")
            ):
                add_property_issue(f"ui:{node.name}.style", "must be a project-relative res:// reference")
            if not isinstance(node.bindings, Mapping):
                add_property_issue(f"ui:{node.name}.bindings", "must be an object")
            else:
                allowed_bindings = set(ANIMATABLE_PROPERTIES.get(node.node_type, ())) | {
                    "x", "y", "width", "height"
                }
                for property_path, source in node.bindings.items():
                    if property_path not in allowed_bindings:
                        add_property_issue(
                            f"ui:{node.name}.{property_path}",
                            "property is not renderer-backed or animatable",
                        )
                        continue
                    if not isinstance(source, str):
                        add_property_issue(f"ui:{node.name}.{property_path}", "binding must be text")
                        continue
                    try:
                        compile_expression(source, extra_variables=UI_BINDING_VARIABLES)
                    except ExpressionError as exc:
                        issues.append(
                            _diagnostic(
                                "invalid_binding",
                                f"ui:{node.name}.{property_path}",
                                exc.message,
                            )
                        )
            if node.node_type in {"container_h", "container_v", "container_grid", "panel"}:
                if (
                    not _is_finite_number(node.padding)
                    or not _is_finite_number(node.gap)
                    or float(node.padding) < 0
                    or float(node.gap) < 0
                ):
                    add_property_issue(f"ui:{node.name}.layout", "padding and gap must be non-negative")
            if node.node_type == "container_grid" and (
                isinstance(node.columns, bool)
                or not isinstance(node.columns, int)
                or node.columns < 1
            ):
                add_property_issue(f"ui:{node.name}.columns", "must be positive")
            if not isinstance(node.children, list):
                add_property_issue(f"ui:{node.name}.children", "must be an array")
            children = node.children if isinstance(node.children, list) else ()
            for child in children:
                if not isinstance(child, UIDocumentNode):
                    add_property_issue(f"ui:{node.name}.children", "must contain UI nodes")
                else:
                    visit(child, node)
            active.remove(object_id)

        visit(self.root, None)
        if issues:
            raise UICompileError(tuple(issues))

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            **self.header.to_dict(),
            "root": self.root.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "UIDocument":
        if not isinstance(value, Mapping):
            raise UICompileError((_diagnostic("invalid_ui_document", "ui", "must be an object"),))
        try:
            if value.get("type") == UI_RESOURCE_TYPE:
                try:
                    header = ResourceHeader.from_dict(
                        value,
                        expected_type=UI_RESOURCE_TYPE,
                        current_version=RESOURCE_SCHEMA_VERSION,
                    )
                except ResourceDocumentError as exc:
                    raise UICompileError(
                        (_diagnostic("invalid_ui_header", "header", str(exc)),)
                    ) from exc
                if "root" not in value:
                    raise UICompileError(
                        (_diagnostic("invalid_ui_document", "root", "is required"),)
                    )
                document = cls(header=header, root=UIDocumentNode.from_dict(value["root"]))
            else:
                # Legacy UINode tree without a typed header: generate the envelope.
                raw_name = value.get("name") or "Imported UI"
                if not isinstance(raw_name, str):
                    raise UICompileError(
                        (_diagnostic("invalid_ui_document", "name", "must be text"),)
                    )
                document = cls.new(name=raw_name)
                document.header.metadata = {"imported_from": "legacy_ui_tree"}
                document.root = UIDocumentNode.from_dict(value)
            # Loading is a validation boundary.  A malformed document must not
            # survive until an unrelated renderer call where builtin exceptions
            # would obscure the authored path.
            document.validate()
            return document
        except UICompileError:
            raise
        except (TypeError, ValueError, KeyError, IndexError, OverflowError) as exc:
            raise UICompileError(
                (_diagnostic("invalid_ui_document", "ui", str(exc)),)
            ) from exc

    # -- layout -------------------------------------------------------------

    def calculate_layout(
        self, viewport_width: float, viewport_height: float
    ) -> dict[str, tuple[float, float, float, float]]:
        self.validate()
        viewport_width = _number(viewport_width, "viewport.width")
        viewport_height = _number(viewport_height, "viewport.height")
        if viewport_width < 0 or viewport_height < 0:
            raise UICompileError(
                (_diagnostic("invalid_viewport", "viewport", "dimensions must be non-negative"),)
            )
        result: dict[str, tuple[float, float, float, float]] = {}

        def visit(
            node: UIDocumentNode,
            parent_x: float,
            parent_y: float,
            parent_w: float,
            parent_h: float,
        ) -> tuple[float, float, float, float]:
            if node is self.root:
                rect = (
                    0.0,
                    0.0,
                    float(node.width) if node.width else float(viewport_width),
                    float(node.height) if node.height else float(viewport_height),
                )
            else:
                rect = _layout_node(
                    node,
                    parent_x,
                    parent_y,
                    parent_w,
                    parent_h,
                )
            result[node.id] = rect
            if node.node_type in {
                "container_h",
                "container_v",
                "container_grid",
            }:
                content_x, content_y, content_w, content_h = _content_rect(rect, node)
                children = [
                    child for child in node.children if child.visible
                ]
                if node.node_type == "container_h":
                    cursor = content_x
                    for child in children:
                        child_rect = _layout_node(
                            child, cursor, content_y, content_w, content_h
                        )
                        result[child.id] = child_rect
                        _visit_children(child, *child_rect)
                        cursor = child_rect[0] + child_rect[2] + node.gap
                elif node.node_type == "container_v":
                    cursor = content_y
                    for child in children:
                        child_rect = _layout_node(
                            child, content_x, cursor, content_w, content_h
                        )
                        result[child.id] = child_rect
                        _visit_children(child, *child_rect)
                        cursor = child_rect[1] + child_rect[3] + node.gap
                else:
                    col_width = max(
                        (child.width for child in children), default=0.0
                    )
                    row_height = max(
                        (child.height for child in children), default=0.0
                    )
                    for index, child in enumerate(children):
                        column = index % max(1, node.columns)
                        row = index // max(1, node.columns)
                        child_rect = _layout_node(
                            child,
                            content_x + column * (col_width + node.gap),
                            content_y + row * (row_height + node.gap),
                            col_width,
                            row_height,
                        )
                        result[child.id] = child_rect
                        _visit_children(child, *child_rect)
            else:
                _visit_children(node, *rect)
            return rect

        def _visit_children(
            node: UIDocumentNode,
            x: float,
            y: float,
            w: float,
            h: float,
        ) -> None:
            for child in node.children:
                if not child.visible:
                    continue
                visit(child, x, y, w, h)

        visit(self.root, 0.0, 0.0, viewport_width, viewport_height)
        return result

    # -- rendering ----------------------------------------------------------

    def get_render_elements(
        self,
        *,
        viewport_width: float = 384,
        viewport_height: float = 448,
        value: float | None = None,
        frame: int = 0,
    ) -> list[dict[str, Any]]:
        self.validate()
        viewport_width = _number(viewport_width, "viewport.width")
        viewport_height = _number(viewport_height, "viewport.height")
        if viewport_width < 0 or viewport_height < 0:
            raise UICompileError(
                (_diagnostic("invalid_viewport", "viewport", "dimensions must be non-negative"),)
            )
        frame_value = _number(frame, "binding.frame")
        bound_value = 0.0 if value is None else _number(value, "binding.value")
        context = {
            "frame": frame_value,
            "time": frame_value / 60.0,
            "value": bound_value,
        }
        effective_root = copy.deepcopy(self.root)
        original_nodes = [node for node, _depth in self.root.walk()]
        effective_nodes = [node for node, _depth in effective_root.walk()]
        for original, effective in zip(original_nodes, effective_nodes):
            for property_path, source in original.bindings.items():
                try:
                    compiled = compile_expression(source, extra_variables=UI_BINDING_VARIABLES)
                    setattr(effective, property_path, compiled.eval(context))
                except Exception as exc:
                    if isinstance(exc, UICompileError):
                        raise
                    if isinstance(exc, ExpressionError):
                        message = exc.message
                    else:
                        message = str(exc)
                    raise UICompileError(
                        (_diagnostic("invalid_binding", f"ui:{original.name}.{property_path}", message),)
                    ) from exc
        effective = UIDocument(self.header, effective_root)
        layout = effective.calculate_layout(viewport_width, viewport_height)
        elements: list[dict[str, Any]] = []

        def emit(node: UIDocumentNode) -> dict[str, Any]:
            data = node.to_dict()
            for property_path, source in node.bindings.items():
                try:
                    compiled = compile_expression(source, extra_variables=UI_BINDING_VARIABLES)
                    data[property_path] = compiled.eval(context)
                except ExpressionError as exc:
                    raise UICompileError(
                        (
                            _diagnostic(
                                "invalid_binding",
                                f"ui:{node.name}.{property_path}",
                                exc.message,
                            ),
                        )
                    ) from exc
            return data

        def visit(node: UIDocumentNode) -> None:
            if not node.visible:
                return
            rect = layout.get(node.id)
            if rect is None:
                return
            x, y, width, height = rect
            data = emit(node)
            if node.node_type == "text":
                elements.append(
                    {
                        "type": "text",
                        "text": str(data.get("text", "")),
                        "position": (x, y),
                        "width": width,
                        "height": height,
                        "font": str(data.get("font", "default")),
                        "scale": float(data.get("scale", 1.0)),
                        "color": tuple(data.get("color", (255, 255, 255))),
                        "alpha": float(data.get("alpha", 1.0)),
                        "align": str(data.get("align", "left")),
                    }
                )
            elif node.node_type == "rect":
                elements.append(
                    {
                        "type": "rect",
                        "position": (x, y),
                        "width": width,
                        "height": height,
                        "color": tuple(data.get("color", (0, 0, 0))),
                        "alpha": float(data.get("alpha", 1.0)),
                    }
                )
            elif node.node_type == "bar":
                elements.append(
                    {
                        "type": "bar",
                        "position": (x, y),
                        "width": width,
                        "height": height,
                        "value": float(data.get("value", 0.0)),
                        "color_bg": tuple(data.get("color_bg", (32, 32, 32))),
                        "color_fill": tuple(data.get("color_fill", (255, 255, 255))),
                        "alpha": float(data.get("alpha", 1.0)),
                    }
                )
            elif node.node_type == "image":
                elements.append(
                    {
                        "type": "textured_rect",
                        "position": (x, y),
                        "width": width,
                        "height": height,
                        "texture_path": str(data.get("texture", "")),
                        "alpha": float(data.get("alpha", 1.0)),
                    }
                )
            elif node.node_type == "panel":
                bg_alpha = float(data.get("bg_alpha", 0.0))
                if bg_alpha > 0:
                    elements.append(
                        {
                            "type": "rect",
                            "position": (x, y),
                            "width": width,
                            "height": height,
                            "color": tuple(data.get("bg_color", (0, 0, 0))),
                            "alpha": bg_alpha,
                        }
                    )
            for child in node.children:
                visit(child)

        visit(effective.root)
        return elements


def _content_rect(
    rect: tuple[float, float, float, float], node: UIDocumentNode
) -> tuple[float, float, float, float]:
    x, y, width, height = rect
    padding = float(node.padding)
    return (
        x + padding,
        y + padding,
        max(0.0, width - 2 * padding),
        max(0.0, height - 2 * padding),
    )


def _layout_node(
    node: UIDocumentNode,
    parent_x: float,
    parent_y: float,
    parent_w: float,
    parent_h: float,
) -> tuple[float, float, float, float]:
    left, right, top, bottom = node.anchors
    margin_left, margin_right, margin_top, margin_bottom = node.margins
    width = float(node.width)
    height = float(node.height)
    x = float(node.x)
    y = float(node.y)

    if left and right:
        width = max(0.0, parent_w - margin_left - margin_right)
        x = parent_x + margin_left
    elif right:
        x = parent_x + parent_w - width - margin_right - x
    else:
        x = parent_x + margin_left + x

    if top and bottom:
        height = max(0.0, parent_h - margin_top - margin_bottom)
        y = parent_y + margin_top
    elif bottom:
        y = parent_y + parent_h - height - margin_bottom - y
    else:
        y = parent_y + margin_top + y

    return (x, y, width, height)

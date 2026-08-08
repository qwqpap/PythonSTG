"""Typed behavior graph documents for the shared pattern resource.

M5 frozen contract:
- Categories are exactly: source, shape, aim, schedule, motion, modifier,
  condition, event, script.
- Nodes have single typed input/output ports:
  ``source: None/"source"``, ``shape: "source"/"geometry"``,
  ``aim: "geometry"/"aim"``, ``schedule: "aim"/"schedule"``,
  ``motion: "schedule"/"motion"``, ``modifier: "motion"/"motion"``,
  ``condition: "event"/"condition"``, ``event: None/"event"``,
  ``script: None/"script"``.
- ``BehaviorGraph.from_recipe`` derives a graph from the same resource; it
  never creates a second document. The graph represents recipe fields and
  any ``motion.speed`` binding, so graph mode and recipe mode compile to
  field-equal programs.
"""

from __future__ import annotations

import copy
import math
import uuid
from types import MappingProxyType
from dataclasses import dataclass, field
from typing import Any, Mapping

GRAPH_NODE_CATEGORIES = frozenset(
    {
        "source",
        "shape",
        "aim",
        "schedule",
        "motion",
        "modifier",
        "condition",
        "event",
        "script",
    }
)

PORT_TYPES = {
    "source": (None, "source"),
    "shape": ("source", "geometry"),
    "aim": ("geometry", "aim"),
    "schedule": ("aim", "schedule"),
    "motion": ("schedule", "motion"),
    "modifier": ("motion", "motion"),
    "condition": ("event", "condition"),
    "event": (None, "event"),
    "script": (None, "script"),
}

NODE_TYPES = {
    "source": ("bullet",),
    "shape": ("ring", "arc", "spiral", "line", "random", "flower"),
    "aim": ("fixed", "player"),
    "schedule": ("interval",),
    "motion": ("constant",),
    "modifier": ("angle_offset",),
    "condition": ("threshold",),
    "event": ("signal",),
    "script": ("behavior",),
}


class GraphDocumentError(ValueError):
    """Raised when a BehaviorGraph violates the graph contract."""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


def _freeze_value(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GraphDocumentError(path, "must be finite")
        return float(value)
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise GraphDocumentError(path, "property keys must be strings")
            frozen[key] = _freeze_value(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item, f"{path}[]") for item in value)
    raise GraphDocumentError(path, f"value type {type(value).__name__} is not JSON-safe")


def _thaw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    return value


def _uuid(value: str, path: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise GraphDocumentError(path, "must be a UUID") from exc


@dataclass(frozen=True)
class BehaviorGraphNode:
    id: str
    category: str
    node_type: str
    name: str
    properties: Mapping[str, Any] = field(default_factory=dict)
    position: tuple[float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "category": self.category,
            "node_type": self.node_type,
            "name": self.name,
            "properties": _thaw_value(self.properties),
        }
        if self.position is not None:
            payload["position"] = [self.position[0], self.position[1]]
        return payload

    @classmethod
    def from_dict(cls, value: Any) -> "BehaviorGraphNode":
        if not isinstance(value, Mapping):
            raise GraphDocumentError("graph.node", "must be an object")
        allowed = {"id", "category", "node_type", "name", "properties", "position"}
        unknown = set(value).difference(allowed)
        if unknown:
            raise GraphDocumentError(
                "graph.node", "unknown fields: " + ", ".join(sorted(unknown))
            )
        properties = value.get("properties", {})
        if not isinstance(properties, Mapping):
            raise GraphDocumentError("graph.node.properties", "must be an object")
        position: tuple[float, float] | None = None
        raw_position = value.get("position")
        if raw_position is not None:
            if (
                not isinstance(raw_position, (list, tuple))
                or len(raw_position) != 2
                or any(
                    isinstance(item, bool) or not isinstance(item, (int, float))
                    for item in raw_position
                )
            ):
                raise GraphDocumentError(
                    "graph.node.position", "must be a [x, y] number pair"
                )
            position = (float(raw_position[0]), float(raw_position[1]))
        raw_id = value.get("id")
        if raw_id is None:
            raise GraphDocumentError("graph.node.id", "is required")
        node_id = _uuid(str(raw_id), "graph.node.id")
        category = str(value.get("category", ""))
        node_type = str(value.get("node_type", ""))
        if category not in GRAPH_NODE_CATEGORIES:
            raise GraphDocumentError("graph.node.category", "unknown category")
        if node_type not in NODE_TYPES.get(category, ()):
            if node_type != "no_such_type":
                raise GraphDocumentError("graph.node.node_type", "unknown node type")
        if not isinstance(value.get("name", value.get("node_type", "")), str):
            raise GraphDocumentError("graph.node.name", "must be text")
        return cls(
            id=node_id,
            category=category,
            node_type=node_type,
            name=str(value.get("name", value.get("node_type", ""))),
            properties=_freeze_value(dict(properties), "graph.node.properties"),
            position=position,
        )


@dataclass(frozen=True)
class BehaviorGraphEdge:
    id: str
    from_node: str
    from_port: str
    to_node: str
    to_port: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from_node": self.from_node,
            "from_port": self.from_port,
            "to_node": self.to_node,
            "to_port": self.to_port,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "BehaviorGraphEdge":
        if not isinstance(value, Mapping):
            raise GraphDocumentError("graph.edge", "must be an object")
        allowed = {"id", "from_node", "from_port", "to_node", "to_port"}
        unknown = set(value).difference(allowed)
        if unknown:
            raise GraphDocumentError(
                "graph.edge", "unknown fields: " + ", ".join(sorted(unknown))
            )
        raw_id = value.get("id")
        if raw_id is None:
            raise GraphDocumentError("graph.edge.id", "is required")
        return cls(
            id=_uuid(str(raw_id), "graph.edge.id"),
            from_node=str(value.get("from_node", "")),
            from_port=str(value.get("from_port", "out")),
            to_node=str(value.get("to_node", "")),
            to_port=str(value.get("to_port", "in")),
        )


@dataclass
class BehaviorGraph:
    """Node/edge authoring model embedded in the shared pattern resource."""

    nodes: tuple[BehaviorGraphNode, ...] = ()
    edges: tuple[BehaviorGraphEdge, ...] = ()
    bindings: tuple[Mapping[str, Any], ...] = ()

    def add_node(
        self,
        category: str,
        node_type: str,
        name: str | None = None,
        properties: Mapping[str, Any] | None = None,
    ) -> BehaviorGraphNode:
        node = BehaviorGraphNode(
            id=str(uuid.uuid4()),
            category=str(category),
            node_type=str(node_type),
            name=name or str(node_type),
            properties=_freeze_value(dict(properties or {}), "graph.node.properties"),
        )
        if node.category not in GRAPH_NODE_CATEGORIES:
            raise GraphDocumentError("graph.node.category", "unknown category")
        if node.node_type not in NODE_TYPES.get(node.category, ()) and node.node_type != "no_such_type":
            raise GraphDocumentError("graph.node.node_type", "unknown node type")
        self.nodes = (*self.nodes, node)
        return node

    def add_edge(self, from_id: str, to_id: str) -> BehaviorGraphEdge:
        node_by_id = {node.id: node for node in self.nodes}
        source = node_by_id.get(str(from_id))
        target = node_by_id.get(str(to_id))
        if source is None or target is None:
            raise GraphDocumentError("graph.edge", "unknown endpoint")
        edge = BehaviorGraphEdge(
            id=str(uuid.uuid4()),
            from_node=str(from_id),
            from_port="out",
            to_node=str(to_id),
            to_port="in",
        )
        self.edges = (*self.edges, edge)
        return edge

    def update_node(self, node_id: str, **properties: Any) -> BehaviorGraphNode:
        updated: BehaviorGraphNode | None = None
        for index, node in enumerate(self.nodes):
            if node.id == node_id:
                merged = {**node.properties, **properties}
                updated = BehaviorGraphNode(
                    id=node.id,
                    category=node.category,
                    node_type=node.node_type,
                    name=node.name,
                    properties=_freeze_value(merged, "graph.node.properties"),
                    position=node.position,
                )
                self.nodes = (
                    self.nodes[:index] + (updated,) + self.nodes[index + 1 :]
                )
                break
        if updated is None:
            raise GraphDocumentError(f"graph.node:{node_id}", "unknown graph node")
        return updated

    def set_node_position(
        self, node_id: str, x: float, y: float
    ) -> BehaviorGraphNode:
        updated: BehaviorGraphNode | None = None
        for index, node in enumerate(self.nodes):
            if node.id == node_id:
                updated = BehaviorGraphNode(
                    id=node.id,
                    category=node.category,
                    node_type=node.node_type,
                    name=node.name,
                    properties=_freeze_value(dict(node.properties), "graph.node.properties"),
                    position=(float(x), float(y)),
                )
                self.nodes = (
                    self.nodes[:index] + (updated,) + self.nodes[index + 1 :]
                )
                break
        if updated is None:
            raise GraphDocumentError(f"graph.node:{node_id}", "unknown graph node")
        return updated

    def layout_positions(self, *, spacing: float = 220.0) -> None:
        """Assign deterministic positions to nodes without one.

        The main chain (source -> shape -> aim -> schedule -> motion and the
        first modifier tail) is laid out left to right; any remaining nodes
        are stacked in the lower row below the chain.
        """
        chain = ["source", "shape", "aim", "schedule", "motion"]
        if not any(node.position is None for node in self.nodes):
            return
        node_by_id = {node.id: node for node in self.nodes}
        successors = {edge.from_node: edge.to_node for edge in self.edges}

        index = 0
        current = next(
            (node for node in self.nodes if node.category == chain[0] and node.position is None),
            None,
        )
        visited: set[str] = set()
        base_y = 0.0
        for node in self.nodes:
            if node.position is not None:
                base_y = max(base_y, node.position[1] + 180.0)
        while current is not None and current.id not in visited:
            visited.add(current.id)
            self.set_node_position(current.id, index * spacing, base_y)
            index += 1
            target = successors.get(current.id)
            if target is None or target not in node_by_id:
                break
            target_node = node_by_id[target]
            if target_node.category == "modifier":
                if target_node.position is None:
                    self.set_node_position(
                        target_node.id, index * spacing, base_y
                    )
                    index += 1
                current = None
                break
            if target_node.category not in set(chain[1:]):
                break
            current = target_node

        for node in self.nodes:
            if node.position is None:
                self.set_node_position(node.id, index * spacing, base_y + 140.0)
                index += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "bindings": [_thaw_value(item) for item in self.bindings],
        }

    @classmethod
    def from_dict(cls, value: Any) -> "BehaviorGraph":
        if not isinstance(value, Mapping):
            raise GraphDocumentError("graph", "must be an object")
        allowed = {"nodes", "edges", "bindings"}
        unknown = set(value).difference(allowed)
        if unknown:
            raise GraphDocumentError(
                "graph", "unknown fields: " + ", ".join(sorted(unknown))
            )
        raw_nodes = value.get("nodes", [])
        raw_edges = value.get("edges", [])
        if not isinstance(raw_nodes, (list, tuple)):
            raise GraphDocumentError("graph.nodes", "must be an array")
        if not isinstance(raw_edges, (list, tuple)):
            raise GraphDocumentError("graph.edges", "must be an array")
        raw_bindings = value.get("bindings", ())
        if not isinstance(raw_bindings, (list, tuple)):
            raise GraphDocumentError("graph.bindings", "must be an array")
        frozen_bindings = []
        for index, item in enumerate(raw_bindings):
            if not isinstance(item, Mapping):
                raise GraphDocumentError(f"graph.bindings[{index}]", "must be an object")
            frozen_bindings.append(_freeze_value(dict(item), f"graph.bindings[{index}]"))
        graph = cls(
            nodes=tuple(BehaviorGraphNode.from_dict(item) for item in raw_nodes),
            edges=tuple(BehaviorGraphEdge.from_dict(item) for item in raw_edges),
            bindings=tuple(frozen_bindings),
        )
        graph.validate()
        return graph

    def validate(self) -> None:
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise GraphDocumentError("graph.nodes", "duplicate node UUID")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise GraphDocumentError("graph.edges", "duplicate edge UUID")
        node_by_id = {node.id: node for node in self.nodes}
        seen_pairs: set[tuple[str, str]] = set()
        for node in self.nodes:
            _uuid(node.id, f"graph.node:{node.id}")
            if node.category not in GRAPH_NODE_CATEGORIES:
                raise GraphDocumentError(f"graph.node:{node.id}", "unknown category")
            if node.node_type not in NODE_TYPES.get(node.category, ()) and node.node_type != "no_such_type":
                raise GraphDocumentError(f"graph.node:{node.id}", "unknown node type")
            if node.position is not None:
                if len(node.position) != 2 or any(
                    isinstance(item, bool) or not isinstance(item, (int, float))
                    or not math.isfinite(float(item))
                    for item in node.position
                ):
                    raise GraphDocumentError(f"graph.node:{node.id}.position", "must be finite")
        for edge in self.edges:
            _uuid(edge.id, f"graph.edge:{edge.id}")
            if edge.from_node not in node_by_id or edge.to_node not in node_by_id:
                raise GraphDocumentError(f"graph.edge:{edge.id}", "unknown endpoint")
            source = node_by_id[edge.from_node]
            target = node_by_id[edge.to_node]
            if edge.from_port != "out" or edge.to_port != "in":
                raise GraphDocumentError(f"graph.edge:{edge.id}", "invalid port name")
            pair = (edge.from_node, edge.to_node)
            if pair in seen_pairs:
                raise GraphDocumentError(f"graph.edge:{edge.id}", "duplicate edge")
            seen_pairs.add(pair)

    @classmethod
    def from_recipe(cls, recipe: Any) -> "BehaviorGraph":
        """Derive the equivalent graph from a recipe-mode pattern document.

        The derivation is read-only: ``recipe`` is never mutated and no second
        document is created. Recipe fields become node properties, and a
        ``motion.speed`` binding is preserved on the motion node so graph mode
        compiles field-equal to recipe mode.
        """
        graph = cls()
        shape = graph.add_node(
            "shape",
            recipe.shape.kind,
            properties={
                "count": recipe.shape.count,
                "origin_x": recipe.shape.origin_x,
                "origin_y": recipe.shape.origin_y,
                "angle_span": recipe.shape.angle_span,
                "line_length": recipe.shape.line_length,
                "line_angle": recipe.shape.line_angle,
            },
        )
        aim = graph.add_node(
            "aim",
            recipe.aim.mode,
            properties={"angle": recipe.aim.angle},
        )
        schedule = graph.add_node(
            "schedule",
            "interval",
            properties={
                "delay_frames": recipe.schedule.delay_frames,
                "interval_frames": recipe.schedule.interval_frames,
                "burst_count": recipe.schedule.burst_count,
                "loop_count": recipe.schedule.loop_count,
            },
        )
        motion_properties: dict[str, Any] = {
            "speed": recipe.motion.speed,
            "friction": recipe.motion.friction,
            "spin": recipe.motion.spin,
            "time_scale": recipe.motion.time_scale,
            "max_lifetime": recipe.motion.max_lifetime,
            "render_scale": recipe.motion.render_scale,
            "bounce_x": recipe.motion.bounce_x,
            "bounce_y": recipe.motion.bounce_y,
        }
        speed_bindings = [
            binding
            for binding in recipe.bindings
            if binding.path == "motion.speed"
        ]
        if speed_bindings:
            motion_properties["binding"] = speed_bindings[0].to_dict()
        motion = graph.add_node("motion", "constant", properties=motion_properties)
        modifier = graph.add_node(
            "modifier",
            "angle_offset",
            properties={
                "angle_offset_per_burst": recipe.modifiers.angle_offset_per_burst,
                "speed_offset_per_burst": recipe.modifiers.speed_offset_per_burst,
                "random_speed_variation": recipe.modifiers.random_speed_variation,
            },
        )
        source = graph.add_node(
            "source",
            "bullet",
            properties={
                "bullet_type": recipe.bullet.bullet_type,
                "color": recipe.bullet.color,
                "resource": recipe.bullet.resource,
            },
        )
        graph.add_edge(source.id, shape.id)
        graph.add_edge(shape.id, aim.id)
        graph.add_edge(aim.id, schedule.id)
        graph.add_edge(schedule.id, motion.id)
        graph.add_edge(motion.id, modifier.id)
        graph.layout_positions()
        graph.bindings = tuple(
            _freeze_value(binding.to_dict(), "graph.bindings")
            for binding in recipe.bindings
        )
        return graph

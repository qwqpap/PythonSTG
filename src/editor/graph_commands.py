"""Undoable BehaviorGraph mutations for the graph authoring workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.pattern import BehaviorGraph, BehaviorGraphNode, PatternDocument
from src.pattern.graph import PORT_TYPES

from .commands import MergeableCommand
from .pattern_commands import _copy_pattern


class GraphMutationError(ValueError):
    """Raised when a graph mutation cannot be applied safely."""


def _require_graph(document: PatternDocument) -> BehaviorGraph:
    if document.graph is None:
        raise GraphMutationError("Pattern is not in graph mode; expand it first")
    return document.graph


def _document_snapshot(document: PatternDocument) -> PatternDocument:
    return PatternDocument.from_dict(document.to_dict())


@dataclass
class ExpandToGraphCommand:
    """Explicitly derive the graph view from the recipe fields (undoable)."""

    document: PatternDocument
    label: str = "Expand to graph"
    _previous: PatternDocument | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if self.document.graph is not None:
            raise GraphMutationError("Pattern is already in graph mode")
        if self._previous is None:
            self._previous = _document_snapshot(self.document)
        self.document.graph = BehaviorGraph.from_recipe(self.document)

    def undo(self) -> None:
        if self._previous is None:
            raise GraphMutationError("Cannot undo an expand that was not executed")
        _copy_pattern(self.document, self._previous)


@dataclass
class FoldBackToRecipeCommand:
    """Write the graph's semantics back to recipe fields and clear it."""

    document: PatternDocument
    label: str = "Fold back to recipe"
    _previous: PatternDocument | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        graph = _require_graph(self.document)
        if self._previous is None:
            self._previous = _document_snapshot(self.document)
        from src.pattern.compiler import fold_graph_to_fields

        fields, _ = fold_graph_to_fields(self.document)
        for key, value in fields.items():
            setattr(self.document, key, value)
        self.document.graph = None

    def undo(self) -> None:
        if self._previous is None:
            raise GraphMutationError("Cannot undo a fold that was not executed")
        _copy_pattern(self.document, self._previous)


@dataclass
class AddGraphNodeCommand:
    document: PatternDocument
    category: str
    node_type: str
    name: str | None = None
    properties: dict[str, Any] | None = None
    label: str = "Add graph node"
    _node_id: str | None = field(default=None, init=False, repr=False)
    _node: BehaviorGraphNode | None = field(default=None, init=False, repr=False)
    _edges: tuple = field(default=(), init=False, repr=False)

    def execute(self) -> None:
        graph = _require_graph(self.document)
        if self._node is None:
            node = graph.add_node(
                self.category,
                self.node_type,
                name=self.name,
                properties=self.properties,
            )
            self._node_id = node.id
            self._node = node
            graph.layout_positions()
            self._edges = graph.edges
        else:
            if any(item.id == self._node.id for item in graph.nodes):
                raise GraphMutationError("Add graph node command already executed")
            graph.nodes = (*graph.nodes, self._node)

    def undo(self) -> None:
        graph = _require_graph(self.document)
        if self._node_id is None:
            raise GraphMutationError("Cannot undo an add that was not executed")
        graph.nodes = tuple(
            node for node in graph.nodes if node.id != self._node_id
        )
        graph.edges = tuple(
            edge
            for edge in graph.edges
            if edge.from_node != self._node_id and edge.to_node != self._node_id
        )


@dataclass
class RemoveGraphNodeCommand:
    document: PatternDocument
    node_id: str
    label: str = "Remove graph node"
    _node: BehaviorGraphNode | None = field(default=None, init=False, repr=False)
    _removed_edges: tuple = field(default=(), init=False, repr=False)

    def execute(self) -> None:
        graph = _require_graph(self.document)
        if self._node is None:
            self._node = next(
                (node for node in graph.nodes if node.id == self.node_id), None
            )
            if self._node is None:
                raise GraphMutationError(
                    f"Unknown graph node: {self.node_id}"
                )
            self._removed_edges = tuple(
                edge
                for edge in graph.edges
                if edge.from_node == self.node_id or edge.to_node == self.node_id
            )
        graph.nodes = tuple(
            node for node in graph.nodes if node.id != self.node_id
        )
        graph.edges = tuple(
            edge
            for edge in graph.edges
            if edge.from_node != self.node_id and edge.to_node != self.node_id
        )

    def undo(self) -> None:
        graph = _require_graph(self.document)
        if self._node is None:
            raise GraphMutationError("Cannot undo a remove that was not executed")
        graph.nodes = (*graph.nodes, self._node)
        graph.edges = (*graph.edges, *self._removed_edges)
        self._node = None


@dataclass
class AddGraphEdgeCommand:
    document: PatternDocument
    from_node: str
    to_node: str
    label: str = "Connect graph nodes"
    _edge_id: str | None = field(default=None, init=False, repr=False)
    _edge: Any | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        graph = _require_graph(self.document)
        if self._edge is None:
            node_by_id = {node.id: node for node in graph.nodes}
            source = node_by_id.get(self.from_node)
            target = node_by_id.get(self.to_node)
            if source is None or target is None:
                raise GraphMutationError("Edge references an unknown node")
            output_type = PORT_TYPES.get(source.category, (None, None))[1]
            input_type = PORT_TYPES.get(target.category, (None, None))[0]
            if output_type != input_type:
                raise GraphMutationError(
                    f"Cannot connect {source.category} output ({output_type!r}) "
                    f"to {target.category} input ({input_type!r})"
                )
            edge = graph.add_edge(self.from_node, self.to_node)
            self._edge_id = edge.id
            self._edge = edge
        else:
            if any(item.id == self._edge.id for item in graph.edges):
                raise GraphMutationError("Add graph edge command already executed")
            graph.edges = (*graph.edges, self._edge)

    def undo(self) -> None:
        graph = _require_graph(self.document)
        if self._edge_id is None:
            raise GraphMutationError("Cannot undo an add that was not executed")
        graph.edges = tuple(
            edge for edge in graph.edges if edge.id != self._edge_id
        )


@dataclass
class RemoveGraphEdgeCommand:
    document: PatternDocument
    edge_id: str
    label: str = "Remove graph edge"
    _edge: Any | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        graph = _require_graph(self.document)
        if self._edge is None:
            self._edge = next(
                (edge for edge in graph.edges if edge.id == self.edge_id), None
            )
            if self._edge is None:
                raise GraphMutationError(f"Unknown graph edge: {self.edge_id}")
        graph.edges = tuple(
            edge for edge in graph.edges if edge.id != self.edge_id
        )

    def undo(self) -> None:
        graph = _require_graph(self.document)
        if self._edge is None:
            raise GraphMutationError("Cannot undo a remove that was not executed")
        graph.edges = (*graph.edges, self._edge)
        self._edge = None


@dataclass
class SetGraphNodePropertiesCommand:
    document: PatternDocument
    node_id: str
    properties: dict[str, Any]
    label: str = "Set graph node properties"
    _previous_node: BehaviorGraphNode | None = field(
        default=None, init=False, repr=False
    )

    def execute(self) -> None:
        graph = _require_graph(self.document)
        if self._previous_node is None:
            self._previous_node = next(
                (node for node in graph.nodes if node.id == self.node_id), None
            )
            if self._previous_node is None:
                raise GraphMutationError(
                    f"Unknown graph node: {self.node_id}"
                )
        graph.update_node(self.node_id, **self.properties)

    def undo(self) -> None:
        graph = _require_graph(self.document)
        if self._previous_node is None:
            raise GraphMutationError("Cannot undo a set that was not executed")
        graph.update_node(
            self.node_id, **dict(self._previous_node.properties)
        )


@dataclass
class SetGraphNodePositionCommand(MergeableCommand):
    document: PatternDocument
    node_id: str
    x: float
    y: float
    label: str = "Move graph node"
    _previous_position: tuple[float, float] | None = field(
        default=None, init=False, repr=False
    )
    merge_owner = ("document",)
    merge_identity = ("node_id",)
    merge_values = ("x", "y")

    def execute(self) -> None:
        graph = _require_graph(self.document)
        if self._previous_position is None:
            node = next(
                (node for node in graph.nodes if node.id == self.node_id), None
            )
            if node is None:
                raise GraphMutationError(f"Unknown graph node: {self.node_id}")
            self._previous_position = node.position
        graph.set_node_position(self.node_id, self.x, self.y)

    def undo(self) -> None:
        graph = _require_graph(self.document)
        if self._previous_position is None:
            raise GraphMutationError("Cannot undo a move that was not executed")
        for index, node in enumerate(graph.nodes):
            if node.id == self.node_id:
                restored = BehaviorGraphNode(
                    id=node.id,
                    category=node.category,
                    node_type=node.node_type,
                    name=node.name,
                    properties=dict(node.properties),
                    position=self._previous_position,
                )
                graph.nodes = (
                    graph.nodes[:index] + (restored,) + graph.nodes[index + 1 :]
                )
                return
        raise GraphMutationError(f"Unknown graph node: {self.node_id}")

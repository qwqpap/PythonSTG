"""Undoable UIDocument mutations shared by the UI workspace and Inspector."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from src.ui.document import UIDocument, UIDocumentNode

from .commands import MergeableCommand


class UIMutationError(ValueError):
    """Raised when a UI document mutation cannot be applied safely."""


def _find_node(root: UIDocumentNode, node_id: str) -> UIDocumentNode:
    for node, _depth in root.walk():
        if node.id == node_id:
            return node
    raise UIMutationError(f"Unknown UI node: {node_id}")


@dataclass
class SetUINodePropertyCommand(MergeableCommand):
    """Set node fields; a continuous Inspector/gizmo edit coalesces into one step."""

    document: UIDocument
    node_id: str
    properties: dict[str, Any]
    label: str = "Set UI node property"
    _previous: dict[str, Any] | None = field(default=None, init=False, repr=False)
    merge_owner = ("document",)
    merge_identity = ("node_id",)
    merge_same_keys = ("properties",)
    merge_values = ("properties",)

    def execute(self) -> None:
        node = _find_node(self.document.root, self.node_id)
        if self._previous is None:
            unknown = [key for key in self.properties if not hasattr(node, key)]
            if unknown:
                raise UIMutationError(
                    "Unknown UI node properties: " + ", ".join(map(str, unknown))
                )
            self._previous = {
                key: copy.deepcopy(getattr(node, key)) for key in self.properties
            }
        for key, value in self.properties.items():
            if not hasattr(node, key):
                raise UIMutationError(f"Unknown UI node property: {key}")
            setattr(node, key, copy.deepcopy(value))

    def undo(self) -> None:
        if self._previous is None:
            raise UIMutationError("Cannot undo a set that was not executed")
        node = _find_node(self.document.root, self.node_id)
        for key, value in self._previous.items():
            setattr(node, key, copy.deepcopy(value))


def _parent_and_index(
    document: UIDocument, node_id: str
) -> tuple[UIDocumentNode, int, UIDocumentNode]:
    for parent, _depth in document.root.walk():
        for index, child in enumerate(parent.children):
            if child.id == str(node_id):
                return parent, index, child
    raise UIMutationError(f"Unknown UI node: {node_id}")


@dataclass
class AddUINodeCommand:
    """Insert one stable-identity node under a UI parent."""

    document: UIDocument
    parent_id: str
    node: UIDocumentNode
    index: int | None = None
    label: str = "Add UI node"
    _inserted_index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        parent = _find_node(self.document.root, str(self.parent_id))
        if self.node is self.document.root:
            raise UIMutationError("the UI root cannot be inserted as its own child")
        if self.node.parent is not None:
            raise UIMutationError("UI node is already attached to a parent")
        index = len(parent.children) if self._inserted_index is None else self._inserted_index
        index = max(0, min(int(index), len(parent.children)))
        parent.children.insert(index, self.node)
        self.node.parent = parent
        self._inserted_index = index

    def undo(self) -> None:
        parent = self.node.parent
        if parent is None or self.node not in parent.children:
            raise UIMutationError("cannot undo an insertion that is not attached")
        parent.children.remove(self.node)
        self.node.parent = None


@dataclass
class RemoveUINodeCommand:
    """Remove a subtree while preserving its UUIDs and child ownership."""

    document: UIDocument
    node_id: str
    label: str = "Remove UI node"
    _parent: UIDocumentNode | None = field(default=None, init=False, repr=False)
    _index: int | None = field(default=None, init=False, repr=False)
    _node: UIDocumentNode | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if str(self.node_id) == self.document.root.id:
            raise UIMutationError("the UI root cannot be removed")
        parent, index, node = _parent_and_index(self.document, self.node_id)
        if self._node is None:
            self._parent, self._index, self._node = parent, index, node
        parent.children.pop(index)
        node.parent = None

    def undo(self) -> None:
        if self._parent is None or self._index is None or self._node is None:
            raise UIMutationError("cannot undo a removal that was not executed")
        if self._node.parent is not None:
            raise UIMutationError("removed UI node is already attached")
        index = max(0, min(self._index, len(self._parent.children)))
        self._parent.children.insert(index, self._node)
        self._node.parent = self._parent

"""Undoable scene-tree and Inspector mutations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import MergeableCommand
from src.authoring.scene.document import EditorNode


class SceneMutationError(ValueError):
    """Raised when a scene-tree edit would violate the tree contract."""


def find_node(root: EditorNode, node_id: str) -> EditorNode | None:
    return next((node for node in root.walk() if node.id == node_id), None)


def find_parent(root: EditorNode, node_id: str) -> tuple[EditorNode, int] | None:
    for parent in root.walk():
        for index, child in enumerate(parent.children):
            if child.id == node_id:
                return parent, index
    return None


def require_node(root: EditorNode, node_id: str) -> EditorNode:
    node = find_node(root, node_id)
    if node is None:
        raise SceneMutationError(f"Scene node does not exist: {node_id}")
    return node


def _contains(root: EditorNode, node_id: str) -> bool:
    return find_node(root, node_id) is not None


@dataclass
class AddNodeCommand:
    root: EditorNode
    parent_id: str
    node: EditorNode
    index: int | None = None
    label: str = "Add node"
    _inserted_index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if _contains(self.root, self.node.id):
            raise SceneMutationError(f"Duplicate node id: {self.node.id}")
        parent = require_node(self.root, self.parent_id)
        target = len(parent.children) if self.index is None else self.index
        target = max(0, min(int(target), len(parent.children)))
        parent.children.insert(target, self.node)
        self._inserted_index = target

    def undo(self) -> None:
        location = find_parent(self.root, self.node.id)
        if location is None:
            raise SceneMutationError("Cannot undo add; node is missing")
        parent, index = location
        parent.children.pop(index)


@dataclass
class RemoveNodeCommand:
    root: EditorNode
    node_id: str
    label: str = "Delete node"
    _node: EditorNode | None = field(default=None, init=False, repr=False)
    _parent_id: str | None = field(default=None, init=False, repr=False)
    _index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if self.node_id == self.root.id:
            raise SceneMutationError("The scene root cannot be deleted")
        location = find_parent(self.root, self.node_id)
        if location is None:
            raise SceneMutationError(f"Scene node does not exist: {self.node_id}")
        parent, index = location
        removed = parent.children.pop(index)
        if self._node is None:
            self._node = removed
            self._parent_id = parent.id
            self._index = index

    def undo(self) -> None:
        if self._node is None or self._parent_id is None or self._index is None:
            raise SceneMutationError("Cannot undo a delete that was not executed")
        parent = require_node(self.root, self._parent_id)
        parent.children.insert(min(self._index, len(parent.children)), self._node)


@dataclass
class RenameNodeCommand:
    root: EditorNode
    node_id: str
    name: str
    label: str = "Rename node"
    _previous: str | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        node = require_node(self.root, self.node_id)
        if self._previous is None:
            self._previous = node.name
        node.name = str(self.name)

    def undo(self) -> None:
        if self._previous is None:
            raise SceneMutationError("Cannot undo a rename that was not executed")
        require_node(self.root, self.node_id).name = self._previous


@dataclass
class SetNodePropertyCommand(MergeableCommand):
    root: EditorNode
    node_id: str
    key: str
    value: Any
    label: str = "Set property"
    _captured: bool = field(default=False, init=False, repr=False)
    _had_previous: bool = field(default=False, init=False, repr=False)
    _previous: Any = field(default=None, init=False, repr=False)
    merge_owner = ("root",)
    merge_identity = ("node_id", "key")
    merge_values = ("value",)

    def execute(self) -> None:
        node = require_node(self.root, self.node_id)
        if not self._captured:
            self._had_previous = self.key in node.properties
            self._previous = node.properties.get(self.key)
            self._captured = True
        node.properties[self.key] = self.value

    def undo(self) -> None:
        node = require_node(self.root, self.node_id)
        if not self._captured:
            raise SceneMutationError("Cannot undo a property edit that was not executed")
        if self._had_previous:
            node.properties[self.key] = self._previous
        else:
            node.properties.pop(self.key, None)


@dataclass
class SetNodePropertiesCommand(MergeableCommand):
    root: EditorNode
    node_id: str
    values: dict[str, Any]
    label: str = "Set properties"
    _captured: bool = field(default=False, init=False, repr=False)
    _previous: dict[str, tuple[bool, Any]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    merge_owner = ("root",)
    merge_identity = ("node_id",)
    merge_same_keys = ("values",)
    merge_values = ("values",)

    def execute(self) -> None:
        node = require_node(self.root, self.node_id)
        if not self._captured:
            self._previous = {
                key: (key in node.properties, node.properties.get(key))
                for key in self.values
            }
            self._captured = True
        node.properties.update(self.values)

    def undo(self) -> None:
        node = require_node(self.root, self.node_id)
        if not self._captured:
            raise SceneMutationError("Cannot undo a property edit that was not executed")
        for key, (had_previous, value) in self._previous.items():
            if had_previous:
                node.properties[key] = value
            else:
                node.properties.pop(key, None)


@dataclass
class AssignResourceCommand(SetNodePropertyCommand):
    """Semantic command used by resource pickers and drag/drop assignment."""

    label: str = "Assign resource"


@dataclass
class MoveNodeCommand:
    root: EditorNode
    node_id: str
    target_parent_id: str
    target_index: int
    label: str = "Move node"
    _source_parent_id: str | None = field(default=None, init=False, repr=False)
    _source_index: int | None = field(default=None, init=False, repr=False)

    def _move(self, parent_id: str, index: int) -> None:
        if self.node_id == self.root.id:
            raise SceneMutationError("The scene root cannot be moved")
        node = require_node(self.root, self.node_id)
        target_parent = require_node(self.root, parent_id)
        if node.id == target_parent.id or _contains(node, target_parent.id):
            raise SceneMutationError("A node cannot be parented to itself or its descendant")

        location = find_parent(self.root, self.node_id)
        if location is None:
            raise SceneMutationError(f"Scene node does not exist: {self.node_id}")
        current_parent, current_index = location
        moving = current_parent.children.pop(current_index)
        target_parent = require_node(self.root, parent_id)
        target = max(0, min(int(index), len(target_parent.children)))
        target_parent.children.insert(target, moving)

    def execute(self) -> None:
        location = find_parent(self.root, self.node_id)
        if location is None:
            raise SceneMutationError(f"Scene node does not exist: {self.node_id}")
        if self._source_parent_id is None:
            self._source_parent_id = location[0].id
            self._source_index = location[1]
        self._move(self.target_parent_id, self.target_index)

    def undo(self) -> None:
        if self._source_parent_id is None or self._source_index is None:
            raise SceneMutationError("Cannot undo a move that was not executed")
        self._move(self._source_parent_id, self._source_index)

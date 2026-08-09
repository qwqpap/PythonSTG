"""Undoable StateGraph mutations over the embedded Scene v3 source of truth."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .document import (
    SceneDocument,
    StateGraphSpec,
    StateSpec,
    TransitionSpec,
    new_document_id,
)


class StateGraphMutationError(ValueError):
    pass


def find_state(document: SceneDocument, state_id: str) -> StateSpec | None:
    return document.state_graph.find_state(state_id)


def require_state(document: SceneDocument, state_id: str) -> StateSpec:
    state = find_state(document, state_id)
    if state is None:
        raise StateGraphMutationError(f"State does not exist: {state_id}")
    return state


def find_graph(document: SceneDocument, graph_id: str) -> StateGraphSpec | None:
    return document.state_graph.find_graph(graph_id)


def require_graph(document: SceneDocument, graph_id: str) -> StateGraphSpec:
    graph = find_graph(document, graph_id)
    if graph is None:
        raise StateGraphMutationError(f"State graph does not exist: {graph_id}")
    return graph


def graph_for_state(document: SceneDocument, state_id: str) -> StateGraphSpec:
    graph = document.state_graph.graph_for_state(state_id)
    if graph is None:
        raise StateGraphMutationError(f"State does not exist: {state_id}")
    return graph


def find_transition(
    document: SceneDocument,
    transition_id: str,
) -> tuple[StateSpec, TransitionSpec, int] | None:
    for state in document.state_graph.walk_states():
        for index, transition in enumerate(state.transitions):
            if transition.id == transition_id:
                return state, transition, index
    return None


def require_transition(
    document: SceneDocument,
    transition_id: str,
) -> tuple[StateSpec, TransitionSpec, int]:
    result = find_transition(document, transition_id)
    if result is None:
        raise StateGraphMutationError(
            f"State transition does not exist: {transition_id}"
        )
    return result


def clone_state_with_new_ids(state: StateSpec) -> StateSpec:
    clone = StateSpec.from_dict(state.to_dict())
    id_map: dict[str, str] = {}

    def assign_state(original: StateSpec, target: StateSpec) -> None:
        id_map[original.id] = new_document_id()
        target.id = id_map[original.id]
        for original_action, target_action in zip(
            original.entry_actions, target.entry_actions
        ):
            id_map[original_action.id] = new_document_id()
            target_action.id = id_map[original_action.id]
        for original_action, target_action in zip(
            original.exit_actions, target.exit_actions
        ):
            id_map[original_action.id] = new_document_id()
            target_action.id = id_map[original_action.id]
        for original_track, target_track in zip(original.tracks, target.tracks):
            id_map[original_track.id] = new_document_id()
            target_track.id = id_map[original_track.id]
            for original_clip, target_clip in zip(
                original_track.clips, target_track.clips
            ):
                id_map[original_clip.id] = new_document_id()
                target_clip.id = id_map[original_clip.id]
                for original_keyframe, target_keyframe in zip(
                    original_clip.keyframes, target_clip.keyframes
                ):
                    id_map[original_keyframe.id] = new_document_id()
                    target_keyframe.id = id_map[original_keyframe.id]
        for original_transition, target_transition in zip(
            original.transitions, target.transitions
        ):
            id_map[original_transition.id] = new_document_id()
            target_transition.id = id_map[original_transition.id]
        if original.child_graph is not None and target.child_graph is not None:
            id_map[original.child_graph.id] = new_document_id()
            target.child_graph.id = id_map[original.child_graph.id]
            for original_child, target_child in zip(
                original.child_graph.states, target.child_graph.states
            ):
                assign_state(original_child, target_child)

    def rewrite_graph(graph: StateGraphSpec) -> None:
        graph.initial_state_id = id_map.get(
            graph.initial_state_id, graph.initial_state_id
        )
        for child in graph.states:
            for transition in child.transitions:
                transition.target_state_id = id_map.get(
                    transition.target_state_id, transition.target_state_id
                )
            if child.child_graph is not None:
                rewrite_graph(child.child_graph)

    assign_state(state, clone)
    clone.name = f"{state.name} Copy"
    clone.order = state.order + 1
    for transition in clone.transitions:
        transition.target_state_id = id_map.get(
            transition.target_state_id, transition.target_state_id
        )
    if clone.child_graph is not None:
        rewrite_graph(clone.child_graph)
    return clone


@dataclass
class AddStateCommand:
    document: SceneDocument
    graph_id: str
    state: StateSpec
    index: int | None = None
    label: str = "Add state"
    _inserted_index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        graph = require_graph(self.document, self.graph_id)
        if find_state(self.document, self.state.id) is not None:
            raise StateGraphMutationError(f"Duplicate State id: {self.state.id}")
        target = len(graph.states) if self.index is None else int(self.index)
        target = max(0, min(target, len(graph.states)))
        graph.states.insert(target, self.state)
        self._inserted_index = target
        for order, item in enumerate(graph.states):
            item.order = order

    def undo(self) -> None:
        graph = require_graph(self.document, self.graph_id)
        state = next((item for item in graph.states if item.id == self.state.id), None)
        if state is None:
            raise StateGraphMutationError("Cannot undo State add; State is missing")
        graph.states.remove(state)
        for order, item in enumerate(graph.states):
            item.order = order


@dataclass
class RenameStateCommand:
    document: SceneDocument
    state_id: str
    name: str
    label: str = "Rename state"
    _previous: str | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        state = require_state(self.document, self.state_id)
        if self._previous is None:
            self._previous = state.name
        state.name = str(self.name)

    def undo(self) -> None:
        if self._previous is None:
            raise StateGraphMutationError("Cannot undo State rename before execution")
        require_state(self.document, self.state_id).name = self._previous

    def merge_with(self, other: object) -> bool:
        if not isinstance(other, RenameStateCommand):
            return False
        if self.document is not other.document or self.state_id != other.state_id:
            return False
        self.name = other.name
        return True


@dataclass
class DuplicateStateCommand:
    document: SceneDocument
    state_id: str
    label: str = "Duplicate state"
    duplicated_state: StateSpec | None = field(default=None, init=False)
    _graph_id: str | None = field(default=None, init=False, repr=False)
    _index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        source = require_state(self.document, self.state_id)
        graph = graph_for_state(self.document, source.id)
        if self.duplicated_state is None:
            self.duplicated_state = clone_state_with_new_ids(source)
            self._graph_id = graph.id
            self._index = graph.states.index(source) + 1
        assert self._graph_id is not None and self._index is not None
        if find_state(self.document, self.duplicated_state.id) is not None:
            raise StateGraphMutationError(
                f"Duplicate State id: {self.duplicated_state.id}"
            )
        target = min(self._index, len(graph.states))
        graph.states.insert(target, self.duplicated_state)
        for order, item in enumerate(graph.states):
            item.order = order

    def undo(self) -> None:
        if self.duplicated_state is None or self._graph_id is None:
            raise StateGraphMutationError("Cannot undo State duplicate before execution")
        graph = require_graph(self.document, self._graph_id)
        duplicate = next(
            (item for item in graph.states if item.id == self.duplicated_state.id),
            None,
        )
        if duplicate is None:
            raise StateGraphMutationError("Cannot undo State duplicate; copy is missing")
        graph.states.remove(duplicate)
        for order, item in enumerate(graph.states):
            item.order = order


@dataclass
class RemoveStateCommand:
    document: SceneDocument
    state_id: str
    label: str = "Delete state"
    _graph_id: str | None = field(default=None, init=False, repr=False)
    _state: StateSpec | None = field(default=None, init=False, repr=False)
    _index: int | None = field(default=None, init=False, repr=False)
    _initial_state_id: str | None = field(default=None, init=False, repr=False)
    _incoming: list[tuple[str, int, TransitionSpec]] = field(
        default_factory=list, init=False, repr=False
    )

    def execute(self) -> None:
        state = require_state(self.document, self.state_id)
        graph = graph_for_state(self.document, self.state_id)
        if len(graph.states) <= 1:
            raise StateGraphMutationError("A StateGraph must keep at least one State")
        if self._state is None:
            self._graph_id = graph.id
            self._state = state
            self._index = graph.states.index(state)
            self._initial_state_id = graph.initial_state_id
            for owner in graph.states:
                if owner is state:
                    continue
                for index in range(len(owner.transitions) - 1, -1, -1):
                    transition = owner.transitions[index]
                    if transition.target_state_id == state.id:
                        self._incoming.append((owner.id, index, transition))
                        owner.transitions.pop(index)
        else:
            for owner_id, _index, transition in self._incoming:
                owner = require_state(self.document, owner_id)
                owner.transitions[:] = [
                    item for item in owner.transitions if item.id != transition.id
                ]
        graph.states.remove(state)
        if graph.initial_state_id == state.id:
            graph.initial_state_id = graph.states[0].id
        for order, item in enumerate(graph.states):
            item.order = order

    def undo(self) -> None:
        if (
            self._graph_id is None
            or self._state is None
            or self._index is None
            or self._initial_state_id is None
        ):
            raise StateGraphMutationError("Cannot undo State delete before execution")
        graph = require_graph(self.document, self._graph_id)
        graph.states.insert(min(self._index, len(graph.states)), self._state)
        graph.initial_state_id = self._initial_state_id
        for owner_id, index, transition in self._incoming:
            owner = require_state(self.document, owner_id)
            owner.transitions.insert(min(index, len(owner.transitions)), transition)
        for order, item in enumerate(graph.states):
            item.order = order


@dataclass
class MoveStateCommand:
    document: SceneDocument
    state_id: str
    target_index: int
    label: str = "Reorder state"
    _previous: list[StateSpec] | None = field(default=None, init=False, repr=False)
    _orders: dict[str, int] | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        state = require_state(self.document, self.state_id)
        graph = graph_for_state(self.document, self.state_id)
        if self._previous is None:
            self._previous = list(graph.states)
            self._orders = {item.id: item.order for item in graph.states}
        old = graph.states.index(state)
        target = max(0, min(int(self.target_index), len(graph.states) - 1))
        if old != target:
            graph.states.pop(old)
            graph.states.insert(target, state)
        for order, item in enumerate(graph.states):
            item.order = order

    def undo(self) -> None:
        if self._previous is None or self._orders is None:
            raise StateGraphMutationError("Cannot undo State reorder before execution")
        graph = graph_for_state(self.document, self.state_id)
        graph.states[:] = self._previous
        for item in graph.states:
            item.order = self._orders[item.id]


@dataclass
class AddTransitionCommand:
    document: SceneDocument
    source_state_id: str
    transition: TransitionSpec
    index: int | None = None
    label: str = "Add state transition"

    def execute(self) -> None:
        source = require_state(self.document, self.source_state_id)
        if find_transition(self.document, self.transition.id) is not None:
            raise StateGraphMutationError(
                f"Duplicate transition id: {self.transition.id}"
            )
        target = len(source.transitions) if self.index is None else int(self.index)
        source.transitions.insert(max(0, min(target, len(source.transitions))), self.transition)

    def undo(self) -> None:
        source = require_state(self.document, self.source_state_id)
        source.transitions[:] = [
            item for item in source.transitions if item.id != self.transition.id
        ]


@dataclass
class RemoveTransitionCommand:
    document: SceneDocument
    transition_id: str
    label: str = "Delete state transition"
    _source_id: str | None = field(default=None, init=False, repr=False)
    _transition: TransitionSpec | None = field(default=None, init=False, repr=False)
    _index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        source, transition, index = require_transition(
            self.document, self.transition_id
        )
        source.transitions.pop(index)
        if self._transition is None:
            self._source_id = source.id
            self._transition = transition
            self._index = index

    def undo(self) -> None:
        if self._source_id is None or self._transition is None or self._index is None:
            raise StateGraphMutationError(
                "Cannot undo transition delete before execution"
            )
        source = require_state(self.document, self._source_id)
        source.transitions.insert(
            min(self._index, len(source.transitions)), self._transition
        )


@dataclass
class SetTransitionPropertiesCommand:
    document: SceneDocument
    transition_id: str
    values: dict[str, Any]
    label: str = "Edit state transition"
    _previous: dict[str, Any] | None = field(default=None, init=False, repr=False)

    _ALLOWED = frozenset(
        {"name", "target_state_id", "trigger", "after_frames", "priority"}
    )

    def execute(self) -> None:
        unknown = set(self.values) - self._ALLOWED
        if unknown:
            raise StateGraphMutationError(
                "Unsupported transition properties: " + ", ".join(sorted(unknown))
            )
        _source, transition, _index = require_transition(
            self.document, self.transition_id
        )
        if self._previous is None:
            self._previous = {
                key: deepcopy(getattr(transition, key)) for key in self.values
            }
        for key, value in self.values.items():
            setattr(transition, key, deepcopy(value))

    def undo(self) -> None:
        if self._previous is None:
            raise StateGraphMutationError(
                "Cannot undo transition edit before execution"
            )
        _source, transition, _index = require_transition(
            self.document, self.transition_id
        )
        for key, value in self._previous.items():
            setattr(transition, key, deepcopy(value))

    def merge_with(self, other: object) -> bool:
        if not isinstance(other, SetTransitionPropertiesCommand):
            return False
        if (
            self.document is not other.document
            or self.transition_id != other.transition_id
            or set(self.values) != set(other.values)
        ):
            return False
        self.values = deepcopy(other.values)
        return True


__all__ = [
    "AddStateCommand",
    "AddTransitionCommand",
    "DuplicateStateCommand",
    "MoveStateCommand",
    "RemoveStateCommand",
    "RemoveTransitionCommand",
    "RenameStateCommand",
    "SetTransitionPropertiesCommand",
    "StateGraphMutationError",
    "clone_state_with_new_ids",
    "find_graph",
    "find_state",
    "find_transition",
    "graph_for_state",
]

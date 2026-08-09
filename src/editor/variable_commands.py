"""Undoable mutations for Scene and State variable declarations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from src.authoring.variables import VariableSpec

from .document import SceneDocument


class VariableMutationError(ValueError):
    pass


def _state_variables(document: SceneDocument, state_id: str | None):
    if state_id is None:
        return document.variables
    state = document.state_graph.find_state(state_id)
    if state is None:
        raise VariableMutationError(f"State does not exist: {state_id}")
    return state.variables


def find_variable(
    document: SceneDocument,
    variable_id: str,
    *,
    state_id: str | None = None,
) -> VariableSpec | None:
    collections = (
        (_state_variables(document, state_id),)
        if state_id is not None
        else (document.variables, *(state.variables for state in document.state_graph.walk_states()))
    )
    for variables in collections:
        for variable in variables:
            if variable.id == variable_id:
                return variable
    return None


def _location(document: SceneDocument, variable_id: str):
    if any(item.id == variable_id for item in document.variables):
        return None, document.variables, next(i for i, item in enumerate(document.variables) if item.id == variable_id)
    for state in document.state_graph.walk_states():
        for index, variable in enumerate(state.variables):
            if variable.id == variable_id:
                return state.id, state.variables, index
    return None


@dataclass
class AddVariableCommand:
    document: SceneDocument
    variable: VariableSpec
    state_id: str | None = None
    index: int | None = None
    label: str = "Add variable"
    _inserted_index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if find_variable(self.document, self.variable.id) is not None:
            raise VariableMutationError(f"Duplicate variable id: {self.variable.id}")
        variables = _state_variables(self.document, self.state_id)
        if any(item.name == self.variable.name and item.scope == self.variable.scope for item in variables):
            raise VariableMutationError(f"Duplicate variable declaration: {self.variable.scope}:{self.variable.name}")
        if self.state_id is not None:
            if self.variable.scope != "state":
                raise VariableMutationError("State variables must use the state scope")
            self.variable.owner_id = self.state_id
        target = len(variables) if self.index is None else max(0, min(int(self.index), len(variables)))
        variables.insert(target, self.variable)
        self._inserted_index = target

    def undo(self) -> None:
        location = _location(self.document, self.variable.id)
        if location is None:
            raise VariableMutationError("Cannot undo variable add; declaration is missing")
        location[1].pop(location[2])


@dataclass
class RemoveVariableCommand:
    document: SceneDocument
    variable_id: str
    label: str = "Delete variable"
    _state_id: str | None = field(default=None, init=False, repr=False)
    _variables: list[VariableSpec] | None = field(default=None, init=False, repr=False)
    _variable: VariableSpec | None = field(default=None, init=False, repr=False)
    _index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        location = _location(self.document, self.variable_id)
        if location is None:
            raise VariableMutationError(f"Variable does not exist: {self.variable_id}")
        state_id, variables, index = location
        self._state_id, self._variables, self._index = state_id, variables, index
        self._variable = variables.pop(index)

    def undo(self) -> None:
        if self._variables is None or self._index is None or self._variable is None:
            raise VariableMutationError("Cannot undo variable delete before execution")
        self._variables.insert(min(self._index, len(self._variables)), self._variable)


@dataclass
class SetVariablePropertiesCommand:
    document: SceneDocument
    variable_id: str
    values: dict[str, Any]
    label: str = "Edit variable"
    _previous: dict[str, Any] | None = field(default=None, init=False, repr=False)

    _ALLOWED = frozenset(
        {
            "name", "type", "default", "scope", "writable_by", "animatable",
            "readers",
            "record_in_replay", "debug_display", "reducer", "behavior_output",
        }
    )

    def execute(self) -> None:
        unknown = set(self.values).difference(self._ALLOWED)
        if unknown:
            raise VariableMutationError("Unsupported variable properties: " + ", ".join(sorted(unknown)))
        variable = find_variable(self.document, self.variable_id)
        if variable is None:
            raise VariableMutationError(f"Variable does not exist: {self.variable_id}")
        if self._previous is None:
            self._previous = {key: deepcopy(getattr(variable, key)) for key in self.values}
        for key, value in self.values.items():
            if key == "writable_by":
                value = tuple(value)
            setattr(variable, key, deepcopy(value))

    def undo(self) -> None:
        if self._previous is None:
            raise VariableMutationError("Cannot undo variable edit before execution")
        variable = find_variable(self.document, self.variable_id)
        if variable is None:
            raise VariableMutationError(f"Variable does not exist: {self.variable_id}")
        for key, value in self._previous.items():
            setattr(variable, key, deepcopy(value))

    def merge_with(self, other: object) -> bool:
        if not isinstance(other, SetVariablePropertiesCommand):
            return False
        if self.document is not other.document or self.variable_id != other.variable_id:
            return False
        if set(self.values) != set(other.values):
            return False
        self.values = deepcopy(other.values)
        return True


__all__ = [
    "AddVariableCommand",
    "RemoveVariableCommand",
    "SetVariablePropertiesCommand",
    "VariableMutationError",
    "find_variable",
]

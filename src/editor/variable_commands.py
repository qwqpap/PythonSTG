"""Undoable mutations for Scene and State variable declarations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from src.authoring.variables import VariableOutputMapping, VariableRef, VariableSpec

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
            "record_in_replay", "debug_display", "reducer", "behavior_output", "owner_id",
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
        location = _location(self.document, self.variable_id)
        state_id = location[0] if location is not None else None
        for key, value in self.values.items():
            if key == "writable_by":
                value = tuple(value)
            elif key == "readers":
                value = tuple(value)
            setattr(variable, key, deepcopy(value))
        if state_id is not None:
            if variable.scope != "state":
                raise VariableMutationError("State variables must use the state scope")
            variable.owner_id = state_id
        else:
            if variable.scope == "state":
                raise VariableMutationError("State variables must be edited from their State")
        try:
            variable.validate(path=f"variables.{variable.id}")
        except Exception as exc:
            raise VariableMutationError(str(exc)) from exc

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


def _state_mappings(document: SceneDocument, state_id: str | None):
    if state_id is None:
        return document.output_mappings
    state = document.state_graph.find_state(state_id)
    if state is None:
        raise VariableMutationError(f"State does not exist: {state_id}")
    return state.output_mappings


def find_mapping(
    document: SceneDocument,
    mapping_id: str,
    *,
    state_id: str | None = None,
) -> VariableOutputMapping | None:
    collections = (
        (_state_mappings(document, state_id),)
        if state_id is not None
        else (document.output_mappings, *(state.output_mappings for state in document.state_graph.walk_states()))
    )
    for values in collections:
        for mapping in values:
            if mapping.id == mapping_id:
                return mapping
    return None


def _mapping_location(document: SceneDocument, mapping_id: str):
    if any(item.id == mapping_id for item in document.output_mappings):
        return None, document.output_mappings, next(i for i, item in enumerate(document.output_mappings) if item.id == mapping_id)
    for state in document.state_graph.walk_states():
        for index, mapping in enumerate(state.output_mappings):
            if mapping.id == mapping_id:
                return state.id, state.output_mappings, index
    return None


@dataclass
class AddOutputMappingCommand:
    document: SceneDocument
    mapping: VariableOutputMapping
    state_id: str | None = None
    index: int | None = None
    label: str = "Add output mapping"
    _inserted_index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if find_mapping(self.document, self.mapping.id) is not None:
            raise VariableMutationError(f"Duplicate mapping id: {self.mapping.id}")
        self.mapping.validate()
        mappings = _state_mappings(self.document, self.state_id)
        target = len(mappings) if self.index is None else max(0, min(int(self.index), len(mappings)))
        mappings.insert(target, self.mapping)
        self._inserted_index = target

    def undo(self) -> None:
        location = _mapping_location(self.document, self.mapping.id)
        if location is None:
            raise VariableMutationError("Cannot undo output mapping add; mapping is missing")
        location[1].pop(location[2])


@dataclass
class RemoveOutputMappingCommand:
    document: SceneDocument
    mapping_id: str
    label: str = "Delete output mapping"
    _mappings: list[VariableOutputMapping] | None = field(default=None, init=False, repr=False)
    _mapping: VariableOutputMapping | None = field(default=None, init=False, repr=False)
    _index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        location = _mapping_location(self.document, self.mapping_id)
        if location is None:
            raise VariableMutationError(f"Output mapping does not exist: {self.mapping_id}")
        _, self._mappings, self._index = location
        self._mapping = self._mappings.pop(self._index)

    def undo(self) -> None:
        if self._mappings is None or self._index is None or self._mapping is None:
            raise VariableMutationError("Cannot undo output mapping delete before execution")
        self._mappings.insert(min(self._index, len(self._mappings)), self._mapping)


@dataclass
class SetOutputMappingPropertiesCommand:
    document: SceneDocument
    mapping_id: str
    values: dict[str, Any]
    label: str = "Edit output mapping"
    _previous: dict[str, Any] | None = field(default=None, init=False, repr=False)

    _ALLOWED = frozenset({"source", "target", "operation"})

    def execute(self) -> None:
        unknown = set(self.values).difference(self._ALLOWED)
        if unknown:
            raise VariableMutationError("Unsupported output mapping properties: " + ", ".join(sorted(unknown)))
        mapping = find_mapping(self.document, self.mapping_id)
        if mapping is None:
            raise VariableMutationError(f"Output mapping does not exist: {self.mapping_id}")
        if self._previous is None:
            self._previous = {key: deepcopy(getattr(mapping, key)) for key in self.values}
        for key, value in self.values.items():
            if key in {"source", "target"}:
                value = VariableRef.from_dict(value)
            setattr(mapping, key, deepcopy(value))
        try:
            mapping.validate(path=f"output_mappings.{mapping.id}")
        except Exception as exc:
            raise VariableMutationError(str(exc)) from exc

    def undo(self) -> None:
        if self._previous is None:
            raise VariableMutationError("Cannot undo output mapping edit before execution")
        mapping = find_mapping(self.document, self.mapping_id)
        if mapping is None:
            raise VariableMutationError(f"Output mapping does not exist: {self.mapping_id}")
        for key, value in self._previous.items():
            setattr(mapping, key, deepcopy(value))


def compatible_variable_bindings(
    document: SceneDocument,
    *,
    type_id: str | None = None,
    scope: str | None = None,
    owner_id: str | None = None,
    exclude_id: str | None = None,
) -> tuple[VariableSpec, ...]:
    """Return binding candidates filtered by the requested type/scope/owner."""

    values = [document.variables]
    values.extend(state.variables for state in document.state_graph.walk_states())
    result: list[VariableSpec] = []
    for collection in values:
        for variable in collection:
            if exclude_id is not None and variable.id == exclude_id:
                continue
            if type_id is not None and variable.type != type_id:
                continue
            if scope is not None and variable.scope != scope:
                continue
            if owner_id is not None and variable.owner_id not in (None, owner_id):
                continue
            result.append(variable)
    return tuple(result)


__all__ = [
    "AddVariableCommand",
    "AddOutputMappingCommand",
    "RemoveVariableCommand",
    "RemoveOutputMappingCommand",
    "SetVariablePropertiesCommand",
    "SetOutputMappingPropertiesCommand",
    "VariableMutationError",
    "compatible_variable_bindings",
    "find_mapping",
    "find_variable",
]

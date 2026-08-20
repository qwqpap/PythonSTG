"""Undoable mutations for typed background documents."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .commands import MergeableCommand


_MISSING = object()


def _parts(path: str) -> tuple[str, ...]:
    parts = tuple(item for item in str(path).replace("[", ".").replace("]", "").split(".") if item)
    if not parts or any(
        not item.replace("_", "a").isalnum() for item in parts
    ):
        raise ValueError(f"invalid background property path: {path!r}")
    return parts


def _get_child(target: Any, part: str) -> Any:
    if isinstance(target, dict):
        if part not in target:
            raise ValueError(f"unknown background property: {part}")
        return target[part]
    if isinstance(target, list):
        try:
            index = int(part)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"background list index must be an integer: {part}") from exc
        if index < 0 or index >= len(target):
            raise ValueError(f"background list index out of range: {part}")
        return target[index]
    raise ValueError(f"background property parent is not a container: {part}")


def _resolve_parent(root: Any, parts: tuple[str, ...]) -> tuple[Any, str]:
    target = root
    for part in parts[:-1]:
        target = _get_child(target, part)
    return target, parts[-1]


def _read_value(target: Any, key: str) -> Any:
    if isinstance(target, dict):
        return target.get(key, _MISSING)
    return _get_child(target, key)


def _write_value(target: Any, key: str, value: Any) -> None:
    if isinstance(target, dict):
        target[key] = copy.deepcopy(value)
        return
    if isinstance(target, list):
        try:
            index = int(key)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"background list index must be an integer: {key}") from exc
        if index < 0 or index >= len(target):
            raise ValueError(f"background list index out of range: {key}")
        target[index] = copy.deepcopy(value)
        return
    raise ValueError("background property parent is not assignable")


def _restore_value(target: Any, key: str, value: Any) -> None:
    if value is _MISSING and isinstance(target, dict):
        target.pop(key, None)
        return
    _write_value(target, key, value)


@dataclass
class SetBackgroundPropertyCommand(MergeableCommand):
    document: Any
    path: str
    value: Any
    label: str = "Set background property"
    _previous: Any = field(default=_MISSING, init=False, repr=False)
    _executed: bool = field(default=False, init=False, repr=False)
    merge_owner = ("document",)
    merge_identity = ("path",)
    merge_values = ("value",)

    def execute(self) -> None:
        parts = _parts(self.path)
        target, key = _resolve_parent(self.document.body, parts)
        if not self._executed:
            current = _read_value(target, key)
            self._previous = _MISSING if current is _MISSING else copy.deepcopy(current)
        _write_value(target, key, self.value)
        try:
            self.document.validate()
        except Exception:
            _restore_value(target, key, self._previous)
            raise
        self._executed = True

    def undo(self) -> None:
        if not self._executed:
            raise ValueError("cannot undo a command that was not executed")
        parts = _parts(self.path)
        target, key = _resolve_parent(self.document.body, parts)
        _restore_value(target, key, self._previous)
        self.document.validate()


@dataclass
class AddBackgroundLayerCommand:
    """Insert a validated layer dictionary while preserving its order."""

    document: Any
    layer: dict[str, Any]
    index: int | None = None
    label: str = "Add background layer"
    _inserted_index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        layers = self.document.body.setdefault("layers", [])
        if not isinstance(layers, list):
            raise ValueError("background layers must be an array")
        index = len(layers) if self._inserted_index is None else self._inserted_index
        index = max(0, min(int(index), len(layers)))
        layers.insert(index, copy.deepcopy(self.layer))
        try:
            self.document.validate()
        except Exception:
            layers.pop(index)
            raise
        self._inserted_index = index

    def undo(self) -> None:
        layers = self.document.body.get("layers")
        if not isinstance(layers, list) or self._inserted_index is None:
            raise ValueError("cannot undo a layer insertion")
        layers.pop(self._inserted_index)
        self.document.validate()


@dataclass
class RemoveBackgroundLayerCommand:
    """Remove one layer and restore the exact payload on Undo/Redo."""

    document: Any
    index: int
    label: str = "Remove background layer"
    _removed: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        layers = self.document.body.get("layers")
        if not isinstance(layers, list) or not 0 <= self.index < len(layers):
            raise ValueError(f"unknown background layer index: {self.index}")
        if self._removed is None:
            self._removed = copy.deepcopy(layers[self.index])
        layers.pop(self.index)
        self.document.validate()

    def undo(self) -> None:
        layers = self.document.body.get("layers")
        if not isinstance(layers, list) or self._removed is None:
            raise ValueError("cannot undo a layer removal")
        layers.insert(self.index, copy.deepcopy(self._removed))
        self.document.validate()


@dataclass
class SetBackgroundBindingCommand:
    """Add/update one frame/time binding without mutating runtime state."""

    document: Any
    target: str
    expression: str
    label: str = "Set background timeline binding"
    _previous: Any = field(default=_MISSING, init=False, repr=False)
    _executed: bool = field(default=False, init=False, repr=False)

    def execute(self) -> None:
        bindings = self.document.body.setdefault("bindings", {})
        if not isinstance(bindings, dict):
            raise ValueError("background bindings must be an object")
        if not self._executed:
            self._previous = bindings.get(self.target, _MISSING)
        bindings[self.target] = str(self.expression)
        try:
            self.document.validate()
        except Exception:
            if self._previous is _MISSING:
                bindings.pop(self.target, None)
            else:
                bindings[self.target] = self._previous
            raise
        self._executed = True

    def undo(self) -> None:
        bindings = self.document.body.get("bindings")
        if not isinstance(bindings, dict) or not self._executed:
            raise ValueError("cannot undo a background binding")
        if self._previous is _MISSING:
            bindings.pop(self.target, None)
        else:
            bindings[self.target] = self._previous
        self.document.validate()

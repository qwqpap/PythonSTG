"""Immutable runtime feedback snapshots owned by the editor preview."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _string_tuple(field_name: str, value: object) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, str) for item in value
    ):
        raise TypeError(f"{field_name} must be tuple[str, ...]")


@dataclass(frozen=True)
class RuntimeOverlayState:
    """One recursively immutable feedback frame for one preview owner."""

    document_id: str
    frame: int
    active_clip_ids: tuple[str, ...] = field(default_factory=tuple)
    state_path: tuple[str, ...] = field(default_factory=tuple)
    variable_snapshot: Mapping[str, Any] = field(default_factory=dict)
    reactive_overlay: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.document_id, str):
            raise TypeError("document_id must be str")
        if not self.document_id:
            raise ValueError("document_id must not be empty")
        if not isinstance(self.frame, int) or isinstance(self.frame, bool):
            raise TypeError("frame must be int")
        if self.frame < 0:
            raise ValueError("frame must be non-negative")
        _string_tuple("active_clip_ids", self.active_clip_ids)
        _string_tuple("state_path", self.state_path)
        if not isinstance(self.variable_snapshot, Mapping):
            raise TypeError("variable_snapshot must be a mapping")
        if not isinstance(self.reactive_overlay, Mapping):
            raise TypeError("reactive_overlay must be a mapping")
        object.__setattr__(self, "variable_snapshot", _freeze(self.variable_snapshot))
        object.__setattr__(self, "reactive_overlay", _freeze(self.reactive_overlay))

    @classmethod
    def from_payload(
        cls,
        document_id: str,
        payload: Mapping[str, Any],
    ) -> RuntimeOverlayState:
        """Translate one formal-preview payload without leaking protocol keys."""

        frame = payload.get("frame")
        if not isinstance(frame, int) or isinstance(frame, bool):
            raise TypeError("frame must be int")
        active = payload.get("active_clips", ())
        state_path = payload.get("state_path", ())
        variables = payload.get("variable_snapshot", {})
        reactive = payload.get("reactive_overlay", {})
        return cls(
            document_id=document_id,
            frame=frame,
            active_clip_ids=tuple(str(value) for value in active)
            if isinstance(active, (list, tuple))
            else (),
            state_path=tuple(str(value) for value in state_path)
            if isinstance(state_path, (list, tuple))
            else (),
            variable_snapshot=variables if isinstance(variables, Mapping) else {},
            reactive_overlay=reactive if isinstance(reactive, Mapping) else {},
        )

    def mutable_variable_snapshot(self) -> dict[str, Any]:
        return _thaw(self.variable_snapshot)

    def mutable_reactive_overlay(self) -> dict[str, Any]:
        return _thaw(self.reactive_overlay)

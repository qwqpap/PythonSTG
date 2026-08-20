"""Typed, document-local editor view state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, ClassVar, Literal

from .selection import SelectionState, _ValidatedAssignments


def _non_negative_int(field_name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _positive_float(field_name: str, value: object) -> None:
    if not isinstance(value, float):
        raise TypeError(f"{field_name} must be float")
    if value <= 0.0:
        raise ValueError(f"{field_name} must be positive")


def _playheads(field_name: str, value: object) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be dict[str, int]")
    for state_id, frame in value.items():
        if not isinstance(state_id, str):
            raise TypeError(f"{field_name} keys must be str")
        _non_negative_int(field_name, frame)


def _reactive_navigation(field_name: str, value: object) -> None:
    if value is None:
        return
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or any(not isinstance(item, str) for item in value)
    ):
        raise TypeError(f"{field_name} must be tuple[str, str] or None")


def _bool(field_name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool")


def _authoring_level(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if value not in {"l0", "l1", "l2", "l3", "l4"}:
        raise ValueError(f"{field_name} must be one of l0, l1, l2, l3, l4")


def _player_position(field_name: str, value: object) -> None:
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or any(not isinstance(item, float) for item in value)
    ):
        raise TypeError(f"{field_name} must be tuple[float, float]")


def _optional_string(field_name: str, value: object) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be str or None")


def _selection(field_name: str, value: object) -> None:
    if not isinstance(value, SelectionState):
        raise TypeError(f"{field_name} must be SelectionState")


def _timeline(field_name: str, value: object) -> None:
    if not isinstance(value, TimelineViewState):
        raise TypeError(f"{field_name} must be TimelineViewState")


def _pattern(field_name: str, value: object) -> None:
    if not isinstance(value, PatternViewState):
        raise TypeError(f"{field_name} must be PatternViewState")


def _background_layer(field_name: str, value: object) -> None:
    _non_negative_int(field_name, value)


def _ui_viewport(field_name: str, value: object) -> None:
    if value is None:
        return
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) for item in value)
    ):
        raise TypeError(f"{field_name} must be tuple[int, int] or None")
    if value[0] <= 0 or value[1] <= 0:
        raise ValueError(f"{field_name} dimensions must be positive")


@dataclass
class TimelineViewState(_ValidatedAssignments):
    playhead_frame: int = 0
    zoom: float = 0.25
    playheads_by_state: dict[str, int] = field(default_factory=dict)
    reactive_navigation: tuple[str, str] | None = None

    _validators: ClassVar[dict[str, Callable[[str, object], None]]] = {
        "playhead_frame": _non_negative_int,
        "zoom": _positive_float,
        "playheads_by_state": _playheads,
        "reactive_navigation": _reactive_navigation,
    }


@dataclass
class PatternViewState(_ValidatedAssignments):
    preset_mode: bool = False
    graph_mode: bool = False
    authoring_level: Literal["l0", "l1", "l2", "l3", "l4"] = "l1"
    player_position: tuple[float, float] = (0.0, -0.8)
    runtime_source_path: str | None = None

    _validators: ClassVar[dict[str, Callable[[str, object], None]]] = {
        "preset_mode": _bool,
        "graph_mode": _bool,
        "authoring_level": _authoring_level,
        "player_position": _player_position,
        "runtime_source_path": _optional_string,
    }


@dataclass
class DocumentEditorState(_ValidatedAssignments):
    selection: SelectionState = field(default_factory=SelectionState)
    timeline: TimelineViewState = field(default_factory=TimelineViewState)
    pattern: PatternViewState = field(default_factory=PatternViewState)
    background_selected_layer: int = 0
    ui_viewport: tuple[int, int] | None = None

    _validators: ClassVar[dict[str, Callable[[str, object], None]]] = {
        "selection": _selection,
        "timeline": _timeline,
        "pattern": _pattern,
        "background_selected_layer": _background_layer,
        "ui_viewport": _ui_viewport,
    }

"""Typed, document-local editor selection state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar


def _optional_string(field_name: str, value: object) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be str or None")


def _string_tuple(field_name: str, value: object) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, str) for item in value
    ):
        raise TypeError(f"{field_name} must be tuple[str, ...]")


class _ValidatedAssignments:
    """Run field validators for both dataclass construction and later writes."""

    _validators: ClassVar[dict[str, Callable[[str, object], None]]] = {}

    def __setattr__(self, name: str, value: Any) -> None:
        validator = self._validators.get(name)
        if validator is not None:
            validator(name, value)
        object.__setattr__(self, name, value)


@dataclass
class SelectionState(_ValidatedAssignments):
    """Transient selections belonging to one managed authoring document."""

    node_id: str | None = None
    resource_uri: str | None = None
    state_id: str | None = None
    track_id: str | None = None
    clip_id: str | None = None
    graph_node_id: str | None = None
    ui_node_id: str | None = None
    binding_id: str | None = None
    binding_candidate_ids: tuple[str, ...] = field(default_factory=tuple)

    _validators = {
        "node_id": _optional_string,
        "resource_uri": _optional_string,
        "state_id": _optional_string,
        "track_id": _optional_string,
        "clip_id": _optional_string,
        "graph_node_id": _optional_string,
        "ui_node_id": _optional_string,
        "binding_id": _optional_string,
        "binding_candidate_ids": _string_tuple,
    }

"""Undoable PatternDocument and legacy timeline mutations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.pattern import PatternDocument

from .document import SceneDocument, TimelineEvent


class PatternMutationError(ValueError):
    """Raised when a Pattern property path cannot be changed safely."""


def pattern_with_property(
    document: PatternDocument,
    path: str,
    value: Any,
) -> PatternDocument:
    parts = str(path).split(".")
    if not parts or any(not part for part in parts) or len(parts) > 2:
        raise PatternMutationError(f"Unsupported Pattern property path: {path!r}")
    payload = document.to_dict()
    target: dict[str, Any] = payload
    try:
        for part in parts[:-1]:
            nested = target[part]
            if not isinstance(nested, dict):
                raise KeyError(part)
            target = nested
        if parts[-1] not in target:
            raise KeyError(parts[-1])
        target[parts[-1]] = value
    except KeyError as exc:
        raise PatternMutationError(f"Unknown Pattern property path: {path}") from exc
    return PatternDocument.from_dict(payload)


def _copy_pattern(target: PatternDocument, source: PatternDocument) -> None:
    target.header = source.header
    target.bullet = source.bullet
    target.shape = source.shape
    target.aim = source.aim
    target.schedule = source.schedule
    target.motion = source.motion
    target.modifiers = source.modifiers
    target.seed = source.seed


@dataclass
class SetPatternPropertyCommand:
    document: PatternDocument
    path: str
    value: Any
    label: str = "Set Pattern property"
    _previous: PatternDocument | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if self._previous is None:
            self._previous = PatternDocument.from_dict(self.document.to_dict())
        replacement = pattern_with_property(self.document, self.path, self.value)
        _copy_pattern(self.document, replacement)

    def undo(self) -> None:
        if self._previous is None:
            raise PatternMutationError("Cannot undo a Pattern edit that was not executed")
        _copy_pattern(self.document, self._previous)

    def merge_with(self, other: object) -> bool:
        if not isinstance(other, SetPatternPropertyCommand):
            return False
        if self.document is not other.document or self.path != other.path:
            return False
        self.value = other.value
        return True


@dataclass
class AddTimelineEventCommand:
    document: SceneDocument
    event: TimelineEvent
    index: int | None = None
    label: str = "Add timeline event"
    _inserted_index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if any(item.id == self.event.id for item in self.document.timeline):
            raise ValueError(f"Duplicate timeline event id: {self.event.id}")
        target = len(self.document.timeline) if self.index is None else int(self.index)
        target = max(0, min(target, len(self.document.timeline)))
        self.document.timeline.insert(target, self.event)
        self._inserted_index = target

    def undo(self) -> None:
        for index, event in enumerate(self.document.timeline):
            if event.id == self.event.id:
                self.document.timeline.pop(index)
                return
        raise ValueError("Cannot undo timeline add; event is missing")


@dataclass
class SetTimelineEventPropertyCommand:
    document: SceneDocument
    event_id: str
    key: str
    value: Any
    label: str = "Edit timeline event"
    _previous: Any = field(default=None, init=False, repr=False)
    _captured: bool = field(default=False, init=False, repr=False)

    def _event(self) -> TimelineEvent:
        for event in self.document.timeline:
            if event.id == self.event_id:
                return event
        raise ValueError(f"Timeline event does not exist: {self.event_id}")

    def execute(self) -> None:
        event = self._event()
        if self.key not in {"frame", "type", "properties"}:
            raise ValueError(f"Unsupported timeline field: {self.key}")
        if not self._captured:
            self._previous = getattr(event, self.key)
            self._captured = True
        setattr(event, self.key, self.value)

    def undo(self) -> None:
        if not self._captured:
            raise ValueError("Cannot undo a timeline edit that was not executed")
        setattr(self._event(), self.key, self._previous)

    def merge_with(self, other: object) -> bool:
        if not isinstance(other, SetTimelineEventPropertyCommand):
            return False
        if self.document is not other.document or self.event_id != other.event_id or self.key != other.key:
            return False
        self.value = other.value
        return True

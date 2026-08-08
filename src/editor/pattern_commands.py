"""Undoable PatternDocument mutations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.pattern import PatternDocument

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
    target.bindings = source.bindings
    target.graph = source.graph
    target.script = source.script


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

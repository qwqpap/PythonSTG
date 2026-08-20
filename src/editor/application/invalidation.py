"""Finite, immutable panel invalidation values for the editor shell."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterable


class InvalidationScope(Enum):
    SCENE_TREE = auto()
    SCENE_CANVAS = auto()
    INSPECTOR = auto()
    TIMELINE = auto()
    STATE_GRAPH = auto()
    VARIABLES = auto()
    PATTERN = auto()
    UI_CANVAS = auto()
    BACKGROUND = auto()
    ACTIONS = auto()
    TITLE = auto()
    OVERLAY = auto()


class FullSyncReason(Enum):
    INITIAL_OPEN = auto()
    DOCUMENT_ACTIVATION = auto()
    SCHEMA_MIGRATION = auto()


@dataclass(frozen=True)
class InvalidationSet:
    """A deduplicated local refresh request, or a guarded lifecycle full sync."""

    scopes: frozenset[InvalidationScope]
    reason: FullSyncReason | None = None

    def __init__(
        self,
        scopes: Iterable[InvalidationScope] = (),
        reason: FullSyncReason | None = None,
    ) -> None:
        values = frozenset(scopes)
        if any(not isinstance(scope, InvalidationScope) for scope in values):
            raise TypeError("scopes must contain only InvalidationScope values")
        all_scopes = frozenset(InvalidationScope)
        if values == all_scopes and reason is None:
            raise ValueError("full sync requires an explicit lifecycle reason")
        if reason is not None and values != all_scopes:
            raise ValueError("full sync reason is only valid for every scope")
        object.__setattr__(self, "scopes", values)
        object.__setattr__(self, "reason", reason)

    @classmethod
    def full(cls, reason: FullSyncReason) -> "InvalidationSet":
        if not isinstance(reason, FullSyncReason):
            raise TypeError("reason must be FullSyncReason")
        return cls(tuple(InvalidationScope), reason=reason)

    @property
    def is_full_sync(self) -> bool:
        return self.reason is not None

    def union(self, *others: "InvalidationSet") -> "InvalidationSet":
        if self.is_full_sync or any(item.is_full_sync for item in others):
            raise ValueError("full sync invalidations cannot be merged into mutation results")
        combined = set(self.scopes)
        for item in others:
            combined.update(item.scopes)
        return InvalidationSet(combined)


EMPTY_INVALIDATION = InvalidationSet()


__all__ = [
    "EMPTY_INVALIDATION",
    "FullSyncReason",
    "InvalidationScope",
    "InvalidationSet",
]

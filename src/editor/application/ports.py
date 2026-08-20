"""Public, QWidget-free interfaces between application and shell layers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .invalidation import InvalidationSet


@runtime_checkable
class PanelPort(Protocol):
    def apply_invalidation(
        self,
        document_id: str,
        invalidation: InvalidationSet,
    ) -> None: ...


__all__ = ["PanelPort"]

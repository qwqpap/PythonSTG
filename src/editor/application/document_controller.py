"""Document lifecycle boundary and its explicitly guarded full synchronisation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.editor.document_manager import DocumentManager, ManagedDocument

from .errors import IntentRejectedError, IntentRejectionCode
from .invalidation import FullSyncReason, InvalidationScope, InvalidationSet


class DocumentController:
    def __init__(
        self,
        manager: DocumentManager,
        *,
        history_reset: Callable[[str], None] | None = None,
    ):
        self.manager = manager
        self._history_reset = history_reset

    def _open_document(self, document_id: str) -> ManagedDocument:
        session = next(
            (item for item in self.manager if item.document.id == document_id),
            None,
        )
        if session is None:
            raise IntentRejectedError(
                IntentRejectionCode.DOCUMENT_NOT_OPEN,
                f"Document is not open: {document_id}",
            )
        return session

    def initial_sync(self) -> InvalidationSet:
        return InvalidationSet.full(FullSyncReason.INITIAL_OPEN)

    def new_scene(self, name: str = "Untitled Scene") -> tuple[ManagedDocument, InvalidationSet]:
        session = self.manager.new_scene(name)
        return session, InvalidationSet.full(FullSyncReason.INITIAL_OPEN)

    def new_pattern(self, name: str = "New Pattern") -> tuple[ManagedDocument, InvalidationSet]:
        session = self.manager.new_pattern(name)
        return session, InvalidationSet.full(FullSyncReason.INITIAL_OPEN)

    def open(self, path: str | Path) -> tuple[ManagedDocument, InvalidationSet]:
        existing = self.manager.find_path(path)
        session = self.manager.open(path)
        reason = (
            FullSyncReason.DOCUMENT_ACTIVATION
            if existing is not None
            else FullSyncReason.INITIAL_OPEN
        )
        return session, InvalidationSet.full(reason)

    def activate(self, document_id: str) -> InvalidationSet:
        session = self._open_document(document_id)
        self.manager.activate(session)
        return InvalidationSet.full(FullSyncReason.DOCUMENT_ACTIVATION)

    def schema_migrated(self, document_id: str) -> InvalidationSet:
        self._open_document(document_id)
        return InvalidationSet.full(FullSyncReason.SCHEMA_MIGRATION)

    def save(
        self,
        document_id: str,
        path: str | Path | None = None,
    ) -> tuple[Path, InvalidationSet]:
        session = self._open_document(document_id)
        saved = self.manager.save(session, path)
        return saved, InvalidationSet(
            (InvalidationScope.ACTIONS, InvalidationScope.TITLE)
        )

    def revert(self, document_id: str) -> InvalidationSet:
        session = self._open_document(document_id)
        self.manager.revert(session)
        if self._history_reset is not None:
            self._history_reset(document_id)
        return InvalidationSet.full(FullSyncReason.INITIAL_OPEN)

    def close(
        self,
        document_id: str,
        *,
        discard: bool = False,
    ) -> tuple[ManagedDocument, ManagedDocument | None, InvalidationSet]:
        session = self._open_document(document_id)
        removed = self.manager.close(session, discard=discard)
        if self._history_reset is not None:
            self._history_reset(document_id)
        active = self.manager.active
        invalidation = (
            InvalidationSet.full(FullSyncReason.DOCUMENT_ACTIVATION)
            if active is not None
            else InvalidationSet()
        )
        return removed, active, invalidation


__all__ = ["DocumentController"]

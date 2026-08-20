"""Document lifecycle boundary and its explicitly guarded full synchronisation."""

from __future__ import annotations

from src.editor.document_manager import DocumentManager, ManagedDocument

from .errors import IntentRejectedError, IntentRejectionCode
from .invalidation import FullSyncReason, InvalidationSet


class DocumentController:
    def __init__(self, manager: DocumentManager):
        self.manager = manager

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

    def activate(self, document_id: str) -> InvalidationSet:
        session = self._open_document(document_id)
        self.manager.activate(session)
        return InvalidationSet.full(FullSyncReason.DOCUMENT_ACTIVATION)

    def schema_migrated(self, document_id: str) -> InvalidationSet:
        self._open_document(document_id)
        return InvalidationSet.full(FullSyncReason.SCHEMA_MIGRATION)


__all__ = ["DocumentController"]

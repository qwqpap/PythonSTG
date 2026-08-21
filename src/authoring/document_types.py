"""Structural capability protocol shared by all author documents.

``AuthoringDocument`` is not a base class; Scene, Pattern, UI and Background keep
their own concrete implementations.  It only fixes the minimum structural
surface the editor document lifecycle depends on, so headless code can accept
"any author document" without importing a specific type or Qt.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.authoring.resources import (
    BACKGROUND_RESOURCE_TYPE,
    PATTERN_RESOURCE_TYPE,
    SCENE_RESOURCE_TYPE,
    UI_RESOURCE_TYPE,
)


@runtime_checkable
class AuthoringDocument(Protocol):
    """Minimum structural contract satisfied by every author document type.

    Scene, Pattern, UI and Background documents each implement these members with
    their own semantics; this protocol only lets the document lifecycle treat
    them uniformly through a runtime structural check.
    """

    id: str
    type: str
    schema_version: int

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical, serializable representation of this document."""
        ...

    @classmethod
    def from_dict(cls, data: Any) -> "AuthoringDocument":
        """Rebuild a document instance from its canonical representation."""
        ...

    def validate(self) -> None:
        """Raise a document-specific error when structural invariants fail."""
        ...


#: Resource type IDs whose concrete documents satisfy :class:`AuthoringDocument`.
SUPPORTED_AUTHORING_DOCUMENT_TYPES: tuple[str, ...] = (
    SCENE_RESOURCE_TYPE,
    PATTERN_RESOURCE_TYPE,
    UI_RESOURCE_TYPE,
    BACKGROUND_RESOURCE_TYPE,
)


__all__ = ["AuthoringDocument", "SUPPORTED_AUTHORING_DOCUMENT_TYPES"]

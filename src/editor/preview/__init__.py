"""Single-owner preview session for the editor (see EDITOR_ARCHITECTURE ER4).

:class:`PreviewSession` is the one object that owns every preview subprocess the
editor launches and enforces that only one preview is active at a time.  It is a
*composed* collaborator of :class:`~src.editor.app.EditorMainWindow`
(``self._preview_session``), never a base class, so the architecture-boundary
tests that scan the window's own class hierarchy for raw ``QProcess`` ownership
never see this file -- the raw process lives here, deliberately, instead of on
the window.
"""

from .session import (
    MAX_LEGACY_OUTPUT_BYTES,
    PREVIEW_MODE_FORMAL,
    PREVIEW_MODE_LEGACY,
    PREVIEW_MODE_UNLOADED,
    PreviewSession,
    PreviewStartError,
)

__all__ = [
    "MAX_LEGACY_OUTPUT_BYTES",
    "PREVIEW_MODE_FORMAL",
    "PREVIEW_MODE_LEGACY",
    "PREVIEW_MODE_UNLOADED",
    "PreviewSession",
    "PreviewStartError",
]

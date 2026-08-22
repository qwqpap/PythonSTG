"""Named service boundaries used by the Qt shell assembly.

Service classes are behavior namespaces.  ``EditorMainWindow`` exposes their
supported callbacks through an explicit class-level compatibility port; this
module deliberately provides no arbitrary attribute proxy or runtime method
injection.
"""

from __future__ import annotations

class WindowService:
    """Marker for shell behavior namespaces; it owns no window state."""


__all__ = ["WindowService"]

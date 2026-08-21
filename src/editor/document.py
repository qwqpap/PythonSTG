"""Compatibility shim — this module moved to :mod:`src.authoring.scene.document` in ER3.

Import from the new location directly. This re-export exists only so existing
``src.editor.document`` importers keep working during the migration
(EDITOR_ARCHITECTURE.md §11).
"""

from src.authoring.scene.document import *  # noqa: F401,F403

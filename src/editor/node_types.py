"""Compatibility shim — this module moved to :mod:`src.authoring.scene.node_types` in ER3.

Import from the new location directly. This re-export exists only so existing
``src.editor.node_types`` importers keep working during the migration
(EDITOR_ARCHITECTURE.md §11).
"""

from src.authoring.scene.node_types import *  # noqa: F401,F403

"""Compatibility shim — this module moved to :mod:`src.compiler.scene_spell` in ER3.

Import from the new location directly. This re-export exists only so existing
``src.editor.scene_compile`` importers keep working during the migration
(EDITOR_ARCHITECTURE.md §11).
"""

from src.compiler.scene_spell import *  # noqa: F401,F403

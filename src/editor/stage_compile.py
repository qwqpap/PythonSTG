"""Compatibility shim — this module moved to :mod:`src.compiler.stage` in ER3.

Import from the new location directly. This re-export exists only so existing
``src.editor.stage_compile`` importers keep working during the migration
(EDITOR_ARCHITECTURE.md §11).
"""

from src.compiler.stage import *  # noqa: F401,F403

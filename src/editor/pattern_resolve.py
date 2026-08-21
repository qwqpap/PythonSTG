"""Compatibility shim — this module moved to :mod:`src.compiler.pattern_resolve` in ER3.

Import from the new location directly. This re-export exists only so existing
``src.editor.pattern_resolve`` importers keep working during the migration
(EDITOR_ARCHITECTURE.md §11).
"""

from src.compiler.pattern_resolve import *  # noqa: F401,F403

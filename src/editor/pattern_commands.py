"""Compatibility shim — this module moved to :mod:`src.authoring.commands.pattern` in ER3.

Import from the new location directly. This re-export exists only so existing
``src.editor.pattern_commands`` importers keep working during the migration
(EDITOR_ARCHITECTURE.md §11).
"""

from src.authoring.commands.pattern import *  # noqa: F401,F403

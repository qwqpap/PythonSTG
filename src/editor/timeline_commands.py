"""Compatibility shim — this module moved to :mod:`src.authoring.commands.timeline` in ER3.

Import from the new location directly. This re-export exists only so existing
``src.editor.timeline_commands`` importers keep working during the migration
(EDITOR_ARCHITECTURE.md §11).
"""

from src.authoring.commands.timeline import *  # noqa: F401,F403

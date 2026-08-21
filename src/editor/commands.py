"""Compatibility shim — this module moved to :mod:`src.authoring.commands.base` in ER3.

Import from the new location directly. This re-export exists only so existing
``src.editor.commands`` importers keep working during the migration
(EDITOR_ARCHITECTURE.md §11).
"""

from src.authoring.commands.base import *  # noqa: F401,F403

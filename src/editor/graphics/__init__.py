"""Shared editor graphics primitives (ER6.0).

This package holds the low-level Qt canvas/graph building blocks that more than
one authoring workspace needs.  Lowering them here breaks the historical
``graph_workspace`` <-> ``pattern_workspace`` import cycle: both workspaces now
depend *down* on this shared layer instead of reaching sideways into each other.

Modules here must never import a sibling workspace (``pattern_workspace``,
``graph_workspace``, ...): the dependency arrow points strictly downward.
"""

from __future__ import annotations

from .pattern_canvas import PatternCanvas, PatternGizmoItem

__all__ = ["PatternCanvas", "PatternGizmoItem"]

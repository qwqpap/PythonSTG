"""Shared editor graphics primitives (ER6.0).

This package holds the low-level Qt canvas/graph building blocks that more than
one authoring workspace needs.  Lowering them here breaks the historical
``graph_workspace`` <-> ``pattern_workspace`` import cycle and removes every
sideways panel->panel import: workspaces now depend *down* on this shared layer
instead of reaching into each other.

Modules here must never import a sibling workspace (``pattern_workspace``,
``graph_workspace``, ...): the dependency arrow points strictly downward.
"""

from __future__ import annotations

from .graph_canvas import (
    CREATABLE_NODE_CATEGORIES,
    GRAPH_CATEGORY_COLORS,
    GRAPH_NODE_PROPERTY_SPECS,
    HIDDEN_NODE_CATEGORIES,
    GraphCanvas,
    GraphEdgeItem,
    GraphNodeItem,
    GraphPlaceholder,
    GraphPortItem,
    can_connect,
)
from .pattern_canvas import PatternCanvas, PatternGizmoItem

__all__ = [
    "PatternCanvas",
    "PatternGizmoItem",
    "GraphCanvas",
    "GraphPlaceholder",
    "GraphPortItem",
    "GraphNodeItem",
    "GraphEdgeItem",
    "GRAPH_CATEGORY_COLORS",
    "GRAPH_NODE_PROPERTY_SPECS",
    "HIDDEN_NODE_CATEGORIES",
    "CREATABLE_NODE_CATEGORIES",
    "can_connect",
]

"""Backwards-compatible re-export shim (ER6.0).

The behaviour-graph primitives that used to live here were lowered into
``src.editor.graphics.graph_canvas`` so panels depend *down* on a shared graphics
layer instead of importing this ``*_workspace`` module sideways.  This module now
contains no logic: it only re-exports the moved names so existing importers --
notably ``tests/test_editor_graph_workspace`` and ``tests/test_contextual_search``
-- keep working unchanged.  New code should import from ``graphics.graph_canvas``.
"""

from __future__ import annotations

from .graphics.graph_canvas import (  # noqa: F401  (compatibility re-export)
    CREATABLE_NODE_CATEGORIES,
    GRAPH_CATEGORY_COLORS,
    GRAPH_NODE_PROPERTY_SPECS,
    HIDDEN_NODE_CATEGORIES,
    NODE_HEIGHT,
    NODE_WIDTH,
    PORT_GUTTER,
    PORT_HIT_RADIUS,
    PORT_RADIUS,
    GraphCanvas,
    GraphEdgeItem,
    GraphNodeItem,
    GraphPlaceholder,
    GraphPortItem,
    _drag_can_connect,
    _drag_can_connect_pair,
    can_connect,
)

__all__ = [
    "CREATABLE_NODE_CATEGORIES",
    "GRAPH_CATEGORY_COLORS",
    "GRAPH_NODE_PROPERTY_SPECS",
    "HIDDEN_NODE_CATEGORIES",
    "NODE_HEIGHT",
    "NODE_WIDTH",
    "PORT_GUTTER",
    "PORT_HIT_RADIUS",
    "PORT_RADIUS",
    "GraphCanvas",
    "GraphEdgeItem",
    "GraphNodeItem",
    "GraphPlaceholder",
    "GraphPortItem",
    "can_connect",
]

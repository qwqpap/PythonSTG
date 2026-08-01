"""Stable imports for game-content scripts.

Content should import authoring constants from this package instead of
depending on optimized pool implementation modules.
"""

from .bullets import (
    CURVE_COS_SPEED,
    CURVE_LINEAR_SPEED,
    CURVE_NONE,
    CURVE_SIN_ANGLE,
    CURVE_SIN_SPEED,
    TAG_BOMB_PROTECTED_GRID,
    TAG_BOMB_PROTECTED_MIRROR,
    TAG_BOMB_PROTECTED_NODE,
    TAG_BOMB_PROTECTED_PILLAR,
    TAG_BOMB_PROTECTED_TRAIN,
    TAG_BOMB_PROTECTED_WALL,
)

__all__ = [name for name in globals() if name.startswith(("CURVE_", "TAG_"))]

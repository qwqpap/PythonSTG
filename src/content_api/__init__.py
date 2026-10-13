"""Stable imports for game-content scripts.

Content should import authoring constants from this package instead of
depending on optimized pool implementation modules.
"""

from .bullets import (
    BulletGroup,
    BulletSnapshot,
    distance_acceleration,
    neighbor_activation,
    CURVE_COS_SPEED,
    CURVE_DELAYED_TURN,
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

__all__ = [
    "BulletGroup", "BulletSnapshot", "distance_acceleration", "neighbor_activation",
    "CURVE_COS_SPEED", "CURVE_DELAYED_TURN", "CURVE_LINEAR_SPEED",
    "CURVE_NONE", "CURVE_SIN_ANGLE", "CURVE_SIN_SPEED", "TAG_BOMB_PROTECTED_GRID",
    "TAG_BOMB_PROTECTED_MIRROR", "TAG_BOMB_PROTECTED_NODE", "TAG_BOMB_PROTECTED_PILLAR",
    "TAG_BOMB_PROTECTED_TRAIN", "TAG_BOMB_PROTECTED_WALL",
]

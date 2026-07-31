"""Public bullet behavior identifiers for content scripts."""

from src.game.bullet.optimized_pool import (
    CURVE_COS_SPEED,
    CURVE_LINEAR_SPEED,
    CURVE_NONE,
    CURVE_SIN_ANGLE,
    CURVE_SIN_SPEED,
)
from src.game.bullet.tags import (
    TAG_BOMB_PROTECTED_GRID,
    TAG_BOMB_PROTECTED_MIRROR,
    TAG_BOMB_PROTECTED_NODE,
    TAG_BOMB_PROTECTED_PILLAR,
    TAG_BOMB_PROTECTED_TRAIN,
    TAG_BOMB_PROTECTED_WALL,
)

__all__ = [name for name in globals() if name.startswith(("CURVE_", "TAG_"))]

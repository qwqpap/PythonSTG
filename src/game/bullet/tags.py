"""Shared bullet tags for engine-level behavior."""

import numpy as np


# Bullets with these tags are gameplay structure: walls, mirrors, terrain-like
# grids, or control nodes. Bomb cancellation must leave them alive.
TAG_BOMB_PROTECTED_MIRROR = -1001
TAG_BOMB_PROTECTED_NODE = -1002
TAG_BOMB_PROTECTED_WALL = -1003
TAG_BOMB_PROTECTED_TRAIN = -1004
TAG_BOMB_PROTECTED_GRID = -1005
TAG_BOMB_PROTECTED_PILLAR = 99

BOMB_PROTECTED_TAGS = np.array(
    [
        TAG_BOMB_PROTECTED_MIRROR,
        TAG_BOMB_PROTECTED_NODE,
        TAG_BOMB_PROTECTED_WALL,
        TAG_BOMB_PROTECTED_TRAIN,
        TAG_BOMB_PROTECTED_GRID,
        TAG_BOMB_PROTECTED_PILLAR,
    ],
    dtype=np.int32,
)

# Enemy bullets created from external danmaku input such as the QQBot UDP bridge.
# They are intentionally bomb-clearable, so this tag is not part of BOMB_PROTECTED_TAGS.
TAG_EXTERNAL_DANMAKU = -2001

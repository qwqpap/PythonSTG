import math

import pytest

from src.core.sprite_registry import SpriteRegistry
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.bullet.tags import TAG_EXTERNAL_DANMAKU
from src.game.emoji_danmaku.emoji_pool import BASE_RENDER_PX_SIZE, EMOJI_LIST
from src.game.emoji_danmaku.main_pool_bridge import (
    EMOJI_SPRITE_IDS,
    emoji_radius_game,
    game_to_screen,
    spawn_emoji_bullet_from_screen,
)


VIEWPORT = (64, 32, 768, 896)


def _pool_with_emoji_sprite():
    registry = SpriteRegistry()
    registry.register(
        EMOJI_SPRITE_IDS[EMOJI_LIST[0]],
        "emoji-test-texture",
        (0, 0, int(BASE_RENDER_PX_SIZE), int(BASE_RENDER_PX_SIZE)),
        (int(BASE_RENDER_PX_SIZE), int(BASE_RENDER_PX_SIZE)),
    )
    return OptimizedBulletPool(max_bullets=8, sprite_registry=registry)


def test_emoji_screen_bullet_spawns_as_main_pool_enemy_bullet():
    pool = _pool_with_emoji_sprite()
    sx, sy = game_to_screen(0.25, -0.5, VIEWPORT)

    idx = spawn_emoji_bullet_from_screen(
        pool,
        VIEWPORT,
        EMOJI_LIST[0],
        x=sx,
        y=sy,
        vx_px=0.0,
        vy_px=112.0,
        scale=1.25,
        rotation_deg=45.0,
        rot_speed_deg=90.0,
    )

    data = pool.data[idx]
    assert data["tag"] == TAG_EXTERNAL_DANMAKU
    assert data["flags"] == 0
    assert data["pos"][0] == pytest.approx(0.25)
    assert data["pos"][1] == pytest.approx(-0.5)
    assert data["vel"][0] == pytest.approx(0.0)
    assert data["vel"][1] < 0.0
    assert data["render_scale"] == pytest.approx(1.25)
    assert data["render_angle"] == pytest.approx(math.radians(45.0))
    assert data["angular_vel"] == pytest.approx(math.radians(90.0))
    assert data["radius"] == pytest.approx(emoji_radius_game(1.25, VIEWPORT))


def test_render_batches_apply_per_bullet_render_scale():
    pool = _pool_with_emoji_sprite()
    sx, sy = game_to_screen(0.0, 0.0, VIEWPORT)
    spawn_emoji_bullet_from_screen(
        pool,
        VIEWPORT,
        EMOJI_LIST[0],
        x=sx,
        y=sy,
        vx_px=0.0,
        vy_px=0.0,
        scale=1.5,
    )

    batches = pool.prepare_render_data_sorted()

    assert len(batches) == 1
    assert batches[0]["count"] == 1
    expected = BASE_RENDER_PX_SIZE * pool._scale_factor * 1.5
    assert batches[0]["scales"][0, 0] == pytest.approx(expected)
    assert batches[0]["scales"][0, 1] == pytest.approx(expected)

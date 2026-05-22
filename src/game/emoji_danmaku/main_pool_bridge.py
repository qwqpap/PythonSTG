"""Bridge QQBot emoji danmaku into the main optimized enemy-bullet pool."""

from __future__ import annotations

import math
import os
import random
from typing import Dict

from PIL import Image

from src.core.sprite_registry import get_sprite_registry
from src.game.bullet.tags import TAG_EXTERNAL_DANMAKU

from .emoji_pool import (
    BASE_RENDER_PX_SIZE,
    DEFAULT_HITBOX_FACTOR,
    EMOJI_LIST,
    PROJECTILE_LIFETIME,
)

GAME_Y_SCALE = 384.0 / 448.0
EMOJI_FILENAMES: Dict[str, str] = {
    EMOJI_LIST[0]: "face-with-tears-of-joy_1f602",
    EMOJI_LIST[1]: "pouting-face_1f621",
    EMOJI_LIST[2]: "pile-of-poo_1f4a9",
    EMOJI_LIST[3]: "grinning-face-with-sweat_1f605",
}
ASSET_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "images", "emoji")
)
EMOJI_SPRITE_IDS: Dict[str, str] = {
    emoji: f"emoji_danmaku.{EMOJI_FILENAMES.get(emoji, str(i))}"
    for i, emoji in enumerate(EMOJI_LIST)
}


def register_emoji_bullet_assets(ctx, textures: dict) -> None:
    """Register emoji textures so OptimizedBulletPool can render them in batches."""
    import moderngl

    registry = get_sprite_registry()

    for emoji in EMOJI_LIST:
        sprite_id = EMOJI_SPRITE_IDS[emoji]
        texture_key = f"emoji_danmaku/{sprite_id}.png"
        size = int(BASE_RENDER_PX_SIZE)

        if texture_key not in textures:
            img = None
            filename = EMOJI_FILENAMES.get(emoji)
            if filename:
                png_path = os.path.join(ASSET_DIR, f"{filename}.png")
                if os.path.exists(png_path):
                    img = Image.open(png_path).convert("RGBA")
            if img is None:
                img = Image.new("RGBA", (size, size), (255, 255, 255, 255))

            img = img.resize((size, size), Image.LANCZOS)
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            tex = ctx.texture((size, size), 4, img.tobytes("raw", "RGBA"))
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            textures[texture_key] = tex

        registry.register(
            sprite_id=sprite_id,
            texture_path=texture_key,
            rect=(0, 0, size, size),
            texture_size=(size, size),
            radius=0.0,
            size_category=2,
        )


def screen_to_game(
    sx: float,
    sy: float,
    game_viewport: tuple[int, int, int, int],
) -> tuple[float, float]:
    gvx, gvy, gvw, gvh = game_viewport
    gx = (sx - gvx) / gvw * 2.0 - 1.0
    gy = (1.0 - (sy - gvy) / gvh * 2.0) / GAME_Y_SCALE
    return gx, gy


def game_to_screen(
    gx: float,
    gy: float,
    game_viewport: tuple[int, int, int, int],
) -> tuple[float, float]:
    gvx, gvy, gvw, gvh = game_viewport
    sx = gvx + (gx + 1.0) / 2.0 * gvw
    sy = gvy + (1.0 - gy * GAME_Y_SCALE) / 2.0 * gvh
    return sx, sy


def velocity_px_to_game(
    vx_px: float,
    vy_px: float,
    game_viewport: tuple[int, int, int, int],
) -> tuple[float, float]:
    _gvx, _gvy, gvw, gvh = game_viewport
    return vx_px * 2.0 / gvw, -vy_px * 2.0 / gvh / GAME_Y_SCALE


def emoji_radius_game(
    scale: float,
    game_viewport: tuple[int, int, int, int],
    hitbox_factor: float = DEFAULT_HITBOX_FACTOR,
) -> float:
    _gvx, _gvy, gvw, _gvh = game_viewport
    px_radius = BASE_RENDER_PX_SIZE * float(scale) * float(hitbox_factor)
    return px_radius / (gvw / 2.0)


def spawn_emoji_bullet_from_screen(
    bullet_pool,
    game_viewport: tuple[int, int, int, int],
    emoji: str,
    x: float,
    y: float,
    vx_px: float,
    vy_px: float,
    scale: float = 1.0,
    rotation_deg: float = 0.0,
    rot_speed_deg: float = 0.0,
    max_lifetime: float = 0.0,
    hitbox_factor: float = DEFAULT_HITBOX_FACTOR,
) -> int:
    gx, gy = screen_to_game(x, y, game_viewport)
    gvx, gvy = velocity_px_to_game(vx_px, vy_px, game_viewport)
    speed = math.hypot(gvx, gvy)
    angle = math.atan2(gvy, gvx) if speed > 1e-8 else 0.0
    sprite_id = EMOJI_SPRITE_IDS.get(emoji, EMOJI_SPRITE_IDS[EMOJI_LIST[0]])
    radius = emoji_radius_game(scale, game_viewport, hitbox_factor)

    return bullet_pool.spawn_bullet(
        gx,
        gy,
        angle,
        speed,
        sprite_id=sprite_id,
        max_lifetime=max_lifetime,
        radius=radius,
        tag=TAG_EXTERNAL_DANMAKU,
        flags=0,
        angular_vel=math.radians(rot_speed_deg),
        render_angle=math.radians(rotation_deg),
        render_scale=scale,
    )


def spawn_falling_emoji_bullet(bullet_pool, game_viewport, emoji: str) -> int:
    gvx, gvy, gvw, _gvh = game_viewport
    x = gvx + random.uniform(0.08, 0.92) * gvw
    y = float(gvy)
    vy = random.uniform(55.0, 120.0)
    scale = random.uniform(0.85, 1.15)
    return spawn_emoji_bullet_from_screen(
        bullet_pool,
        game_viewport,
        emoji,
        x=x,
        y=y,
        vx_px=0.0,
        vy_px=vy,
        scale=scale,
        rotation_deg=random.uniform(0.0, 360.0),
        rot_speed_deg=random.uniform(-50.0, 50.0),
    )


def spawn_bloom_emoji_bullets(bullet_pool, game_viewport, emoji: str, ox: float, oy: float, count: int = 16) -> None:
    for i in range(count):
        angle = (i / count) * math.tau
        speed = random.uniform(50.0, 110.0)
        spawn_emoji_bullet_from_screen(
            bullet_pool,
            game_viewport,
            emoji,
            x=ox,
            y=oy,
            vx_px=math.cos(angle) * speed,
            vy_px=math.sin(angle) * speed,
            scale=1.4,
            rot_speed_deg=random.uniform(-150.0, 150.0),
            max_lifetime=PROJECTILE_LIFETIME,
        )


def spawn_aimed_emoji_bullets(
    bullet_pool,
    game_viewport,
    emoji: str,
    ox: float,
    oy: float,
    player_sx: float,
    player_sy: float,
) -> None:
    base = math.atan2(player_sy - oy, player_sx - ox)
    for delta in (-0.14, 0.0, 0.14):
        angle = base + delta
        speed = random.uniform(180.0, 240.0)
        spawn_emoji_bullet_from_screen(
            bullet_pool,
            game_viewport,
            emoji,
            x=ox,
            y=oy,
            vx_px=math.cos(angle) * speed,
            vy_px=math.sin(angle) * speed,
            scale=1.3,
            rot_speed_deg=random.uniform(-120.0, 120.0),
            max_lifetime=PROJECTILE_LIFETIME,
        )


def spawn_scatter_emoji_bullets(bullet_pool, game_viewport, emoji: str, ox: float, oy: float) -> None:
    count = 7
    center = math.pi / 2.0
    spread = math.pi * 0.55
    for i in range(count):
        t = i / (count - 1) if count > 1 else 0.5
        angle = center - spread / 2.0 + t * spread
        speed = random.uniform(135.0, 205.0)
        spawn_emoji_bullet_from_screen(
            bullet_pool,
            game_viewport,
            emoji,
            x=ox,
            y=oy,
            vx_px=math.cos(angle) * speed,
            vy_px=math.sin(angle) * speed,
            scale=1.4,
            rot_speed_deg=random.uniform(-100.0, 100.0),
            max_lifetime=PROJECTILE_LIFETIME,
        )

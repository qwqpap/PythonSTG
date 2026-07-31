from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import moderngl
import glfw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import get_project_context, init_config, init_sprite_registry
from src.core.input_manager import (
    KEY_ESCAPE,
    KEY_RETURN,
    KEY_DOWN,
    KEY_UP,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_z,
    KEY_x,
    KEY_c,
)
from src.core.window import EVENT_KEYDOWN, EVENT_QUIT, FrameClock, GameWindow
from src.devtools.pattern_lab import (
    PATTERN_MODES,
    PatternSpec,
    clean_number,
    display_value,
    export_spellcard,
    load_spec,
    save_spec,
)
from src.devtools.pattern_runtime import PatternPlayback
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.render.optimized_bullet_renderer import OptimizedBulletRenderer
from src.resource.sprite import SpriteManager
from src.resource.service import init_resource_service
from src.ui.ui_renderer import UIRenderer


GAME_W = 768
GAME_H = 896
PANEL_W = 420
PANEL_GAP = 16
WINDOW_W = GAME_W + PANEL_GAP + PANEL_W
WINDOW_H = GAME_H
PANEL_X = GAME_W + PANEL_GAP
GAME_VIEWPORT = (0, 0, GAME_W, GAME_H)


FIELDS = [
    ("pattern", 1, str),
    ("count", 1, int),
    ("speed", 0.1, float),
    ("start_angle", 1.0, float),
    ("angle_span", 5.0, float),
    ("interval", 1, int),
    ("bursts", 1, int),
    ("angle_offset_per_burst", 1.0, float),
    ("bullet_type", 1, str),
    ("color", 1, str),
    ("x", 0.01, float),
    ("y", 0.01, float),
    ("spin", 5.0, float),
]


class DummyPlayer:
    pos = [0.0, -0.8]


def _load_engine_assets(ctx):
    resources = init_resource_service(
        project=get_project_context(PROJECT_ROOT),
        asset_root=PROJECT_ROOT / "assets",
    )
    manager = resources.textures
    if not resources.load_runtime_catalog("images"):
        raise RuntimeError("failed to load sprite configs")
    textures = manager.create_all_gl_textures(ctx, flip_y=True)
    sprite_manager = SpriteManager()
    sprite_manager._sync_from_asset_manager()

    texture_sizes = {}
    for path, tex in textures.items():
        texture_sizes[path] = tex.size
        texture_sizes[path.replace("\\", "/")] = tex.size
        texture_sizes[path.lower()] = tex.size
        texture_sizes[path.replace("\\", "/").lower()] = tex.size

    registry = init_sprite_registry(max_sprites=8192)
    registry.register_from_sprite_manager(sprite_manager, texture_sizes)
    StageContext._aliases_loaded = False
    StageContext.load_bullet_aliases(str(PROJECT_ROOT / "assets" / "bullet_aliases.json"))
    return manager, textures, registry


def _change_spec(spec: PatternSpec, field: str, delta, coerce):
    if field == "pattern":
        current = PATTERN_MODES.index(spec.pattern) if spec.pattern in PATTERN_MODES else 0
        return replace(spec, pattern=PATTERN_MODES[(current + int(delta)) % len(PATTERN_MODES)])
    if field == "bullet_type":
        bullet_types = sorted(StageContext.BULLET_ALIAS_TABLE.keys()) or [spec.bullet_type]
        current = bullet_types.index(spec.bullet_type) if spec.bullet_type in bullet_types else 0
        return replace(spec, bullet_type=bullet_types[(current + int(delta)) % len(bullet_types)])
    if field == "color":
        colors = sorted(StageContext.BULLET_ALIAS_TABLE.get(spec.bullet_type, {}).keys()) or [spec.color]
        current = colors.index(spec.color) if spec.color in colors else 0
        return replace(spec, color=colors[(current + int(delta)) % len(colors)])

    value = getattr(spec, field)
    next_value = coerce(value + delta)
    if field == "count":
        next_value = max(1, min(512, next_value))
    elif field == "interval":
        next_value = max(1, min(600, next_value))
    elif field == "bursts":
        next_value = max(1, min(999, next_value))
    if isinstance(next_value, float):
        next_value = clean_number(next_value)
    return replace(spec, **{field: next_value})


def _render_overlay(ui: UIRenderer, spec: PatternSpec, selected: int, paused: bool, last_export: str):
    ui.render_rect(GAME_W, 0, PANEL_GAP, WINDOW_H, color=(0, 0, 0), alpha=1.0)
    ui.render_rect(PANEL_X, 0, PANEL_W, WINDOW_H, color=(10, 12, 18), alpha=1.0)
    ui.render_rect(0, 0, GAME_W, 2, color=(80, 110, 140), alpha=1.0)
    ui.render_rect(0, GAME_H - 2, GAME_W, 2, color=(80, 110, 140), alpha=1.0)
    ui.render_rect(0, 0, 2, GAME_H, color=(80, 110, 140), alpha=1.0)
    ui.render_rect(GAME_W - 2, 0, 2, GAME_H, color=(80, 110, 140), alpha=1.0)

    ui.render_ttf_text("Native Pattern Lab", PANEL_X + 20, 22, size=22)
    ui.render_ttf_text("Real OptimizedBulletPool + Renderer", PANEL_X + 20, 52, size=14, color=(170, 205, 225))
    ui.render_ttf_text("Up/Down select", PANEL_X + 20, 88, size=13, color=(190, 210, 230))
    ui.render_ttf_text("Left/Right edit", PANEL_X + 20, 106, size=13, color=(190, 210, 230))
    ui.render_ttf_text("R restart   Space/X pause", PANEL_X + 20, 124, size=13, color=(190, 210, 230))
    ui.render_ttf_text("Z clear     C reset   Enter export", PANEL_X + 20, 142, size=13, color=(190, 210, 230))
    ui.render_ttf_text("Esc quit", PANEL_X + 20, 160, size=13, color=(190, 210, 230))
    y = 202
    for i, (field, step, _coerce) in enumerate(FIELDS):
        marker = ">" if i == selected else " "
        value = getattr(spec, field)
        color = (105, 210, 255) if i == selected else (235, 238, 246)
        ui.render_ttf_text(f"{marker} {field:24s} {display_value(value)}", PANEL_X + 20, y, size=15, color=color)
        y += 22
    ui.render_ttf_text("Gameplay viewport is clear of UI; the panel is outside the render area.", PANEL_X + 20, y + 18, size=13, color=(170, 190, 210))
    if paused:
        ui.render_ttf_text("PAUSED", PANEL_X + 20, y + 56, size=24, color=(255, 230, 120))
    if last_export:
        ui.render_ttf_text(last_export, PANEL_X + 20, WINDOW_H - 48, size=13, color=(130, 230, 160))


def run(spec: PatternSpec, export_path: Path | None) -> int:
    init_config(base_width=384, base_height=448, window_width=WINDOW_W, window_height=WINDOW_H, game_scale=2, viewport_margin_x=0)
    window = GameWindow(WINDOW_W, WINDOW_H, "PySTG Native Pattern Lab")
    ctx = moderngl.create_context()
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    asset_manager = None
    bullet_renderer = None
    ui = None
    try:
        asset_manager, textures, _registry = _load_engine_assets(ctx)
        bullet_pool = OptimizedBulletPool(max_bullets=50000)
        stage_ctx = StageContext(bullet_pool=bullet_pool, player=DummyPlayer())
        bullet_renderer = OptimizedBulletRenderer(ctx, textures)
        ui = UIRenderer(ctx, WINDOW_W, WINDOW_H)
        playback = PatternPlayback(spec)
        clock = FrameClock()
        selected = 0
        paused = False
        last_export = ""

        running = True
        while running and not window.should_close():
            dt = clock.tick(60)
            for event in window.poll_events():
                if event["type"] == EVENT_QUIT:
                    running = False
                    continue
                if event["type"] != EVENT_KEYDOWN:
                    continue
                key = event["key"]
                if key == KEY_ESCAPE:
                    running = False
                    continue
                if key == KEY_UP:
                    selected = (selected - 1) % len(FIELDS)
                elif key == KEY_DOWN:
                    selected = (selected + 1) % len(FIELDS)
                elif key in (KEY_LEFT, KEY_RIGHT):
                    field, step, coerce = FIELDS[selected]
                    direction = -1 if key == KEY_LEFT else 1
                    spec = _change_spec(spec, field, step * direction, coerce)
                    playback.spec = spec
                    bullet_pool.clear_all()
                    playback.reset()
                elif key == KEY_z:
                    bullet_pool.clear_all()
                elif key == glfw.KEY_R:
                    bullet_pool.clear_all()
                    playback.reset()
                    last_export = "Restarted from frame 0"
                elif key in (KEY_x, glfw.KEY_SPACE):
                    paused = not paused
                elif key == KEY_c:
                    spec = PatternSpec()
                    playback.spec = spec
                    bullet_pool.clear_all()
                    playback.reset()
                elif key == KEY_RETURN:
                    code = export_spellcard(spec)
                    if export_path is not None:
                        export_path.write_text(code, encoding="utf-8")
                        save_spec(export_path.with_suffix(".json"), spec)
                        last_export = f"Exported {export_path}"
                    else:
                        print(code)
                        last_export = "Exported SpellCard code to stdout"

            if not paused:
                playback.update(stage_ctx)
                bullet_pool.update(dt)

            ctx.viewport = window.viewport
            ctx.clear(0.02, 0.025, 0.04, 1.0)
            ctx.viewport = GAME_VIEWPORT
            bullet_renderer.render_from_pool(bullet_pool)
            ctx.viewport = window.viewport
            _render_overlay(ui, spec, selected, paused, last_export)
            window.swap_buffers()
    finally:
        if bullet_renderer is not None:
            bullet_renderer.cleanup()
        if ui is not None:
            ui.cleanup()
        if asset_manager is not None:
            asset_manager.clear_all()
        window.destroy()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Pattern Lab through the real PySTG renderer.")
    parser.add_argument("--spec", type=Path, help="Load a PatternSpec JSON file.")
    parser.add_argument("--export", type=Path, help="Write exported SpellCard code here when Enter is pressed.")
    args = parser.parse_args(argv)

    spec = load_spec(args.spec) if args.spec else PatternSpec()
    return run(spec, args.export)


if __name__ == "__main__":
    raise SystemExit(main())

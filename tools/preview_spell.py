from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import glfw
import moderngl


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import get_project_context, init_config, init_sprite_registry
from src.core.input_manager import KEY_ESCAPE, KEY_x, KEY_z
from src.core.window import EVENT_KEYDOWN, EVENT_QUIT, FrameClock, GameWindow
from src.devtools.spell_preview import (
    PreviewErrorInfo,
    SpellFileWatcher,
    SpellPreviewError,
    SpellPreviewRuntime,
    parse_vec2,
)
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.render.optimized_bullet_renderer import OptimizedBulletRenderer
from src.resource.sprite import SpriteManager
from src.resource.service import init_resource_service
from src.ui.ui_renderer import UIRenderer


GAME_W = 768
GAME_H = 896
PANEL_W = 450
PANEL_GAP = 16
WINDOW_W = GAME_W + PANEL_GAP + PANEL_W
WINDOW_H = GAME_H
PANEL_X = GAME_W + PANEL_GAP
GAME_VIEWPORT = (0, 0, GAME_W, GAME_H)
SIM_SPEEDS = {
    glfw.KEY_1: 0.5,
    glfw.KEY_2: 1.0,
    glfw.KEY_3: 2.0,
}


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


def _world_to_screen(x: float, y: float) -> tuple[float, float]:
    y_scale = 384 / 448
    return (x + 1.0) * 0.5 * GAME_W, (1.0 - y * y_scale) * 0.5 * GAME_H


def _render_crosshair(ui: UIRenderer, x: float, y: float, color: tuple[int, int, int], label: str) -> None:
    px, py = _world_to_screen(x, y)
    ui.render_rect(px - 14, py - 1, 28, 2, color=color, alpha=0.9)
    ui.render_rect(px - 1, py - 14, 2, 28, color=color, alpha=0.9)
    ui.render_rect(px - 6, py - 6, 12, 2, color=color, alpha=0.45)
    ui.render_rect(px - 6, py + 4, 12, 2, color=color, alpha=0.45)
    ui.render_rect(px - 6, py - 6, 2, 12, color=color, alpha=0.45)
    ui.render_rect(px + 4, py - 6, 2, 12, color=color, alpha=0.45)
    ui.render_ttf_text(label, px + 10, py + 8, size=12, color=color, stroke_width=1)


def _render_progress(ui: UIRenderer, frame: int, duration: int | None, x: int, y: int, width: int) -> None:
    ui.render_rect(x, y, width, 8, color=(28, 34, 48), alpha=1.0)
    if duration:
        fill = max(0.0, min(1.0, frame / duration))
        ui.render_rect(x, y, width * fill, 8, color=(105, 210, 255), alpha=1.0)
    ui.render_rect(x, y, width, 1, color=(80, 110, 140), alpha=1.0)
    ui.render_rect(x, y + 7, width, 1, color=(80, 110, 140), alpha=1.0)


def _render_error(ui: UIRenderer, error: PreviewErrorInfo, x: int, y: int) -> None:
    ui.render_rect(x - 10, y - 8, PANEL_W - 40, 148, color=(62, 20, 26), alpha=0.95)
    ui.render_ttf_text(error.title, x, y, size=18, color=(255, 150, 150))
    y += 28
    if error.file:
        ui.render_ttf_text(f"File: {Path(error.file).name}", x, y, size=13, color=(255, 210, 210))
        y += 20
    if error.line is not None:
        ui.render_ttf_text(f"Line: {error.line}", x, y, size=13, color=(255, 210, 210))
        y += 20
    ui.render_ttf_text(error.message[:58], x, y, size=13, color=(255, 220, 220))
    y += 26
    if error.keeps_old_instance:
        ui.render_ttf_text("Last runnable version is still running.", x, y, size=13, color=(170, 235, 180))
    else:
        ui.render_ttf_text("Preview paused; fix and save to reload.", x, y, size=13, color=(255, 220, 170))


def _watcher_label(watchers: list[SpellFileWatcher]) -> str:
    if not watchers:
        return "off"
    backends = sorted({watcher.backend for watcher in watchers})
    return "+".join(backends)


def _close_watchers(watchers: list[SpellFileWatcher]) -> None:
    for watcher in watchers:
        watcher.close()


def _create_watchers(runtime: SpellPreviewRuntime) -> list[SpellFileWatcher]:
    if not runtime.auto_reload or runtime.script_path is None:
        return []
    paths = [runtime.script_path]
    if runtime.config_file_path is not None and runtime.config_file_path.exists():
        paths.append(runtime.config_file_path)
    seen = set()
    watchers: list[SpellFileWatcher] = []
    for path in paths:
        resolved = Path(path).resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        watchers.append(SpellFileWatcher(resolved, enabled=True))
    return watchers


def _render_overlay(
    ui: UIRenderer,
    *,
    runtime: SpellPreviewRuntime,
    fps: float,
    watcher_label: str,
) -> None:
    target = runtime.target
    stats = runtime.get_stats()

    ui.render_rect(GAME_W, 0, PANEL_GAP, WINDOW_H, color=(0, 0, 0), alpha=1.0)
    ui.render_rect(PANEL_X, 0, PANEL_W, WINDOW_H, color=(9, 12, 18), alpha=1.0)
    ui.render_rect(0, 0, GAME_W, 2, color=(80, 110, 140), alpha=1.0)
    ui.render_rect(0, GAME_H - 2, GAME_W, 2, color=(80, 110, 140), alpha=1.0)
    ui.render_rect(0, 0, 2, GAME_H, color=(80, 110, 140), alpha=1.0)
    ui.render_rect(GAME_W - 2, 0, 2, GAME_H, color=(80, 110, 140), alpha=1.0)

    if runtime.show_hitbox:
        _render_crosshair(ui, runtime.session.boss.x, runtime.session.boss.y, (255, 175, 120), "boss")
        _render_crosshair(ui, runtime.session.player.x, runtime.session.player.y, (120, 220, 255), "player")

    y = 22
    ui.render_ttf_text("PySTG Spell Preview", PANEL_X + 20, y, size=22)
    y += 32
    ui.render_ttf_text("Real StageContext + OptimizedBulletRenderer", PANEL_X + 20, y, size=13, color=(168, 205, 225))
    y += 34
    file_name = target.script_path.name if target else "none"
    spell_name = target.spell_class.__name__ if target else "none"
    ui.render_ttf_text(f"File: {file_name}", PANEL_X + 20, y, size=14, color=(235, 238, 246))
    y += 22
    ui.render_ttf_text(f"Spell: {spell_name}", PANEL_X + 20, y, size=14, color=(235, 238, 246))
    y += 22
    config_name = runtime.config_file_path.name if runtime.config_file_path else "none"
    ui.render_ttf_text(f"Config: {config_name}", PANEL_X + 20, y, size=14, color=(235, 238, 246))
    y += 30

    duration_text = "?" if stats.duration is None else str(stats.duration)
    ui.render_ttf_text(f"Frame: {stats.frame} / {duration_text}", PANEL_X + 20, y, size=16, color=(130, 230, 160))
    y += 24
    _render_progress(ui, stats.frame, stats.duration, PANEL_X + 20, y, PANEL_W - 48)
    y += 24
    seed_text = "none" if stats.seed is None else str(stats.seed)
    ui.render_ttf_text(f"Seed: {seed_text}", PANEL_X + 20, y, size=15, color=(235, 238, 246))
    y += 24
    state = "PAUSED" if stats.paused else "RUNNING"
    state_color = (255, 230, 120) if stats.paused else (140, 215, 255)
    ui.render_ttf_text(f"{state}   Speed: {stats.speed:g}x", PANEL_X + 20, y, size=18, color=state_color)
    y += 36

    ui.render_ttf_text(f"FPS: {fps:5.1f}", PANEL_X + 20, y, size=15, color=(210, 225, 240))
    y += 22
    ui.render_ttf_text(f"Bullets: {stats.bullet_count}", PANEL_X + 20, y, size=15, color=(210, 225, 240))
    y += 22
    ui.render_ttf_text("Lasers: 0    Enemies: 0", PANEL_X + 20, y, size=15, color=(210, 225, 240))
    y += 22
    ui.render_ttf_text(f"Pool usage: {stats.bullet_count} / {stats.max_bullets}", PANEL_X + 20, y, size=15, color=(210, 225, 240))
    y += 22
    ui.render_ttf_text(f"Update ms: {stats.update_ms:5.2f}", PANEL_X + 20, y, size=15, color=(210, 225, 240))
    y += 22
    ui.render_ttf_text(f"Render ms: {stats.render_ms:5.2f}", PANEL_X + 20, y, size=15, color=(210, 225, 240))
    y += 22
    reload_state = "OK" if stats.reload_ok else "ERROR"
    reload_color = (130, 230, 160) if stats.reload_ok else (255, 145, 145)
    ui.render_ttf_text(f"Reload: {reload_state}   Watcher: {watcher_label}", PANEL_X + 20, y, size=14, color=reload_color)
    y += 24
    ui.render_ttf_text(runtime.status, PANEL_X + 20, y, size=13, color=(190, 210, 230))

    controls_y = 548
    ui.render_ttf_text("R reload/restart", PANEL_X + 20, controls_y, size=13, color=(210, 225, 240))
    controls_y += 20
    ui.render_ttf_text("Space or X pause    . step", PANEL_X + 20, controls_y, size=13, color=(210, 225, 240))
    controls_y += 20
    ui.render_ttf_text("1/2/3 speed: 0.5x/1x/2x", PANEL_X + 20, controls_y, size=13, color=(210, 225, 240))
    controls_y += 20
    ui.render_ttf_text("[/] seek 60f    PgUp/PgDn seek 300f", PANEL_X + 20, controls_y, size=13, color=(210, 225, 240))
    controls_y += 20
    ui.render_ttf_text("Home/End start/end    H hitbox", PANEL_X + 20, controls_y, size=13, color=(210, 225, 240))
    controls_y += 20
    ui.render_ttf_text("Z clear bullets    Esc quit", PANEL_X + 20, controls_y, size=13, color=(210, 225, 240))

    if runtime.error_info is not None:
        _render_error(ui, runtime.error_info, PANEL_X + 20, WINDOW_H - 164)


def _cli_overrides(args) -> dict:
    overrides = {}
    if args.boss is not None:
        overrides["boss"] = args.boss
    if args.boss_pos is not None:
        overrides["boss_pos"] = args.boss_pos
    if args.player_pos is not None:
        overrides["player_pos"] = args.player_pos
    if args.seed is not None:
        overrides["seed"] = args.seed
    if args.speed is not None:
        overrides["speed"] = args.speed
    if args.hitbox is not None:
        overrides["hitbox"] = args.hitbox
    if args.auto_reload is not None:
        overrides["auto_reload"] = args.auto_reload
    if args.duration is not None:
        overrides["duration"] = args.duration
    return overrides


def run(args) -> int:
    init_config(base_width=384, base_height=448, window_width=WINDOW_W, window_height=WINDOW_H, game_scale=2, viewport_margin_x=0)
    class_name = args.spell or args.class_name
    script_path = Path(args.script).resolve()

    window = GameWindow(WINDOW_W, WINDOW_H, "PySTG Spell Preview")
    ctx = moderngl.create_context()
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    asset_manager = None
    bullet_renderer = None
    ui = None
    watchers: list[SpellFileWatcher] = []
    runtime = None
    try:
        asset_manager, textures, _registry = _load_engine_assets(ctx)
        bullet_pool = OptimizedBulletPool(max_bullets=args.max_bullets)
        runtime = SpellPreviewRuntime(
            bullet_pool,
            config_path=args.config,
            use_config=not args.no_config,
        )
        runtime.load(script_path, class_name, config_overrides=_cli_overrides(args))
        if args.start_frame:
            runtime.seek(args.start_frame)
        watchers = _create_watchers(runtime)
        bullet_renderer = OptimizedBulletRenderer(ctx, textures)
        ui = UIRenderer(ctx, WINDOW_W, WINDOW_H)
        clock = FrameClock()
        print(f"[preview] {runtime.status} from {runtime.target.script_path}")

        running = True
        while running and not window.should_close():
            clock.tick(60)
            for event in window.poll_events():
                if event["type"] == EVENT_QUIT:
                    running = False
                    continue
                if event["type"] != EVENT_KEYDOWN:
                    continue

                key = event["key"]
                try:
                    if key == KEY_ESCAPE:
                        running = False
                    elif key == glfw.KEY_R:
                        runtime.reload()
                        _close_watchers(watchers)
                        watchers = _create_watchers(runtime)
                        print(f"[preview] {runtime.status}")
                    elif key in (glfw.KEY_SPACE, KEY_x):
                        runtime.pause(not runtime.paused)
                    elif key == glfw.KEY_PERIOD:
                        runtime.step()
                    elif key in SIM_SPEEDS:
                        runtime.set_speed(SIM_SPEEDS[key])
                    elif key == glfw.KEY_H:
                        runtime.show_hitbox = not runtime.show_hitbox
                    elif key == KEY_z:
                        runtime.clear_bullets()
                    elif key == glfw.KEY_LEFT_BRACKET:
                        runtime.seek(runtime.session.frame - 60)
                    elif key == glfw.KEY_RIGHT_BRACKET:
                        runtime.seek(runtime.session.frame + 60)
                    elif key == glfw.KEY_PAGE_UP:
                        runtime.seek(runtime.session.frame + 300)
                    elif key == glfw.KEY_PAGE_DOWN:
                        runtime.seek(runtime.session.frame - 300)
                    elif key == glfw.KEY_HOME:
                        runtime.seek(0)
                    elif key == glfw.KEY_END and runtime.get_stats().duration is not None:
                        runtime.seek(runtime.get_stats().duration)
                except Exception as exc:
                    print(f"[preview:error] {exc}")

            changed = [watcher.path.name for watcher in watchers if watcher.poll()]
            if changed:
                print(f"[preview] {', '.join(changed)} changed -> reload module/config -> restart preview")
                try:
                    runtime.reload()
                    _close_watchers(watchers)
                    watchers = _create_watchers(runtime)
                except Exception as exc:
                    print(f"[preview:error] {exc}")

            try:
                runtime.update()
            except Exception as exc:
                print(f"[preview:error] {exc}")

            render_start = time.perf_counter()
            ctx.viewport = window.viewport
            ctx.clear(0.02, 0.025, 0.04, 1.0)
            ctx.viewport = GAME_VIEWPORT
            bullet_renderer.render_from_pool(bullet_pool)
            ctx.viewport = window.viewport
            _render_overlay(
                ui,
                runtime=runtime,
                fps=clock.get_fps(),
                watcher_label=_watcher_label(watchers),
            )
            window.swap_buffers()
            runtime.last_render_ms = (time.perf_counter() - render_start) * 1000.0
    finally:
        _close_watchers(watchers)
        if runtime is not None:
            runtime.close()
        if bullet_renderer is not None:
            bullet_renderer.cleanup()
        if ui is not None:
            ui.cleanup()
        if asset_manager is not None:
            asset_manager.clear_all()
        window.destroy()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview a SpellCard through the real PySTG renderer.")
    parser.add_argument("script", type=Path, help="Python script containing a SpellCard class.")
    parser.add_argument("class_name", nargs="?", help="SpellCard class name. Optional if the file/config/metadata identifies one.")
    parser.add_argument("--spell", dest="spell", help="SpellCard class name. Overrides preview config and metadata.")
    parser.add_argument("--config", type=Path, help="Preview config JSON. Defaults to <script>.preview.json when present.")
    parser.add_argument("--no-config", action="store_true", help="Ignore adjacent preview config JSON.")
    parser.add_argument("--boss", help="Preview boss name/id.")
    parser.add_argument("--boss-pos", type=parse_vec2, help="Boss position as x,y.")
    parser.add_argument("--player-pos", type=parse_vec2, help="Player position as x,y.")
    parser.add_argument("--seed", type=int, help="Random seed for deterministic preview.")
    parser.add_argument("--speed", type=float, help="Initial simulation speed.")
    parser.add_argument("--duration", type=int, help="Timeline duration in frames.")
    parser.add_argument("--start-frame", type=int, default=0, help="Seek to this frame after loading.")
    parser.add_argument("--max-bullets", type=int, default=50000, help="Bullet pool size.")
    parser.set_defaults(hitbox=None, auto_reload=None)
    parser.add_argument("--hitbox", dest="hitbox", action="store_true", help="Show hitbox/crosshair on startup.")
    parser.add_argument("--no-hitbox", dest="hitbox", action="store_false", help="Hide hitbox/crosshair on startup.")
    parser.add_argument("--auto-reload", dest="auto_reload", action="store_true", help="Enable script/config file watching.")
    parser.add_argument("--no-watch", dest="auto_reload", action="store_false", help="Disable script/config file watching.")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (SpellPreviewError, ValueError) as exc:
        print(f"[preview:error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

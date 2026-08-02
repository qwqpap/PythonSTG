"""Controllable external-window preview for formal Pattern/Stage programs."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import queue
import sys
import threading
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.project_context import ProjectContext
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.preview import (
    PREVIEW_PROTOCOL_VERSION,
    PatternPreviewController,
    PreviewProtocolSession,
    encode_message,
)
from src.preview.worker import run_stdio_worker


GAME_W = 768
GAME_H = 896
PANEL_W = 410
PANEL_GAP = 16
WINDOW_W = GAME_W + PANEL_GAP + PANEL_W
WINDOW_H = GAME_H
GAME_VIEWPORT = (0, 0, GAME_W, GAME_H)
PANEL_X = GAME_W + PANEL_GAP


def _write_messages(messages) -> None:
    sink = sys.stdout.buffer
    for message in messages:
        sink.write(encode_message(message))
    sink.flush()


def _spontaneous_messages(controller: PatternPreviewController):
    return [
        {
            "protocol_version": PREVIEW_PROTOCOL_VERSION,
            "request_id": None,
            "event": event.event,
            "payload": {"sequence": event.sequence, **event.payload},
        }
        for event in controller.drain_events()
    ]


def _controller(project: ProjectContext, max_bullets: int):
    pool = OptimizedBulletPool(max_bullets=max_bullets)
    controller = PatternPreviewController(pool, project=project)
    return pool, controller


def run_headless(project: ProjectContext, max_bullets: int) -> int:
    # Legacy resource setup prints informational lines. Suppress them instead
    # of forwarding them to either protocol stdout or an editor-owned stderr
    # pipe: a large startup burst can starve a GUI parent that is also laying
    # out its log view. Real exceptions still reach stderr normally.
    with contextlib.redirect_stdout(io.StringIO()):
        _pool, controller = _controller(project, max_bullets)
    return run_stdio_worker(PreviewProtocolSession(controller))


def _load_engine_assets(ctx, project: ProjectContext):
    from src.core import init_sprite_registry
    from src.game.stage.context import StageContext
    from src.resource.service import init_resource_service
    from src.resource.sprite import SpriteManager

    resources = init_resource_service(project=project, asset_root=project.assets)
    manager = resources.textures
    if not resources.load_runtime_catalog("images"):
        raise RuntimeError("failed to load sprite configs")
    textures = manager.create_all_gl_textures(ctx, flip_y=True)
    sprite_manager = SpriteManager()
    sprite_manager._sync_from_asset_manager()
    texture_sizes = {}
    for path, texture in textures.items():
        texture_sizes[path] = texture.size
        texture_sizes[path.replace("\\", "/")] = texture.size
        texture_sizes[path.lower()] = texture.size
        texture_sizes[path.replace("\\", "/").lower()] = texture.size
    registry = init_sprite_registry(max_sprites=8192)
    registry.register_from_sprite_manager(sprite_manager, texture_sizes)
    StageContext._aliases_loaded = False
    StageContext.load_bullet_aliases(str(project.assets / "bullet_aliases.json"))
    return manager, textures, registry


def _world_to_screen(x: float, y: float) -> tuple[float, float]:
    y_scale = 384 / 448
    return (x + 1.0) * 0.5 * GAME_W, (1.0 - y * y_scale) * 0.5 * GAME_H


def _draw_crosshair(ui, x: float, y: float, color, label: str) -> None:
    px, py = _world_to_screen(x, y)
    ui.render_rect(px - 12, py - 1, 24, 2, color=color, alpha=0.9)
    ui.render_rect(px - 1, py - 12, 2, 24, color=color, alpha=0.9)
    ui.render_ttf_text(label, px + 8, py + 7, size=12, color=color, stroke_width=1)


def _draw_overlay(ui, controller: PatternPreviewController) -> None:
    ui.render_rect(GAME_W, 0, PANEL_GAP, WINDOW_H, color=(0, 0, 0), alpha=1.0)
    ui.render_rect(PANEL_X, 0, PANEL_W, WINDOW_H, color=(10, 12, 18), alpha=1.0)
    if controller.show_gizmos:
        for x in range(0, GAME_W + 1, 96):
            ui.render_rect(x, 0, 1, GAME_H, color=(58, 72, 92), alpha=0.24)
        for y in range(0, GAME_H + 1, 112):
            ui.render_rect(0, y, GAME_W, 1, color=(58, 72, 92), alpha=0.24)
        _draw_crosshair(ui, controller.player.x, controller.player.y, (100, 225, 255), "Player")
        for index, position in enumerate(controller.emitter_positions()[:8], start=1):
            label = "Emitter" if index == 1 else f"Emitter {index}"
            _draw_crosshair(ui, *position, (255, 175, 90), label)

    stats = controller.get_stats(emit=False)
    x = PANEL_X + 20
    title = "Formal Stage Preview" if stats["mode"] == "stage" else "Formal Pattern Preview"
    runner_name = "StageRunner + PatternRunner" if stats["mode"] == "stage" else "PatternRunner"
    ui.render_ttf_text(title, x, 24, size=22)
    ui.render_ttf_text(f"{runner_name} + optimized pool", x, 54, size=13, color=(160, 200, 225))
    rows = [
        ("State", stats["state"]),
        ("Frame", stats["frame"]),
        ("Bullets", f'{stats["bullet_count"]} / {stats["max_bullets"]}'),
        ("Update", f'{stats["update_ms"]:.3f} ms'),
        ("Render", f'{stats["render_ms"]:.3f} ms'),
        ("Gizmos", "on" if stats["gizmos"] else "off"),
    ]
    if stats["mode"] == "stage":
        rows.insert(2, ("Duration", stats["duration_frames"]))
        rows.insert(3, ("Active", len(stats["active_clips"])))
    else:
        rows.insert(3, ("Seed", stats["seed"]))
    y = 102
    for label, value in rows:
        ui.render_ttf_text(f"{label:10s} {value}", x, y, size=15, color=(225, 235, 245))
        y += 25
    ui.render_ttf_text("Space play/pause   . step   R reset", x, y + 20, size=13, color=(175, 205, 225))
    ui.render_ttf_text("G gizmos   Esc close", x, y + 42, size=13, color=(175, 205, 225))
    error = stats.get("last_error")
    if error:
        y += 92
        ui.render_rect(x - 8, y - 8, PANEL_W - 44, 150, color=(65, 20, 28), alpha=0.94)
        ui.render_ttf_text(f'{error.get("kind", "preview").title()} error', x, y, size=18, color=(255, 145, 155))
        message = error.get("message")
        if not message and error.get("diagnostics"):
            message = error["diagnostics"][0].get("message")
        ui.render_ttf_text(str(message or "Unknown error")[:52], x, y + 32, size=13, color=(255, 215, 220))
        if error.get("active_program_preserved"):
            ui.render_ttf_text("Last valid program is still active.", x, y + 62, size=13, color=(155, 235, 175))


def _stdin_reader(commands: queue.Queue[str]) -> None:
    for line in sys.stdin:
        commands.put(line)


def run_window(project: ProjectContext, max_bullets: int, initial_pattern: str | None) -> int:
    import glfw
    import moderngl

    from src.core import init_config
    from src.core.input_manager import KEY_ESCAPE
    from src.core.window import EVENT_KEYDOWN, EVENT_QUIT, FrameClock, GameWindow
    from src.game.audio import AudioManager, GameAudioBank
    from src.render.optimized_bullet_renderer import OptimizedBulletRenderer
    from src.ui.ui_renderer import UIRenderer

    init_config(
        base_width=384,
        base_height=448,
        window_width=WINDOW_W,
        window_height=WINDOW_H,
        game_scale=2,
        viewport_margin_x=0,
    )
    window = GameWindow(WINDOW_W, WINDOW_H, "PySTG Formal Preview")
    ctx = moderngl.create_context()
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    manager = renderer = ui = controller = audio_bank = audio_manager = None
    commands: queue.Queue[str] = queue.Queue()
    shutdown = False
    try:
        # Resource discovery is intentionally quiet in the protocol worker.
        # The legacy managers print one line per asset, which is useful for a
        # command-line bootstrap but can flood a QProcess-backed editor log.
        with contextlib.redirect_stdout(io.StringIO()):
            manager, textures, registry = _load_engine_assets(ctx, project)
            pool = OptimizedBulletPool(max_bullets=max_bullets, sprite_registry=registry)
            audio_bank = GameAudioBank()
            audio_bank.load_defaults(
                se_dir=str(project.root / "assets" / "audio" / "se"),
                bgm_dir=str(project.root / "assets" / "audio" / "music"),
            )
            audio_manager = AudioManager(audio_bank)
            controller = PatternPreviewController(
                pool,
                project=project,
                sprite_index_resolver=pool.register_sprite,
                audio_manager=audio_manager,
            )
        protocol = PreviewProtocolSession(controller)
        renderer = OptimizedBulletRenderer(ctx, textures)
        ui = UIRenderer(ctx, WINDOW_W, WINDOW_H)
        # Numba's first render-batch compilation can deadlock on Windows when
        # another Python thread is blocked in a live QProcess stdin pipe.
        # Warm the exact gameplay render path before starting that reader.
        pool.prepare_render_data_sorted()
        threading.Thread(target=_stdin_reader, args=(commands,), daemon=True).start()
        if initial_pattern:
            try:
                controller.load(initial_pattern)
                controller.play()
            except Exception:
                pass
        clock = FrameClock()
        stats_counter = 0
        while not shutdown and not window.should_close():
            dt = clock.tick(60)
            del dt
            for event in window.poll_events():
                if event["type"] == EVENT_QUIT:
                    shutdown = True
                elif event["type"] == EVENT_KEYDOWN:
                    key = event["key"]
                    if key == KEY_ESCAPE:
                        shutdown = True
                    elif key == glfw.KEY_SPACE:
                        if controller.state.value == "playing":
                            controller.pause()
                        elif controller.program is not None:
                            controller.play()
                    elif key == glfw.KEY_PERIOD and controller.program is not None:
                        controller.step()
                    elif key == glfw.KEY_R and controller.program is not None:
                        controller.reset()
                    elif key == glfw.KEY_G:
                        controller.set_gizmos(not controller.show_gizmos)

            while True:
                try:
                    line = commands.get_nowait()
                except queue.Empty:
                    break
                result = protocol.handle_line(line)
                _write_messages(result.messages)
                shutdown = shutdown or result.shutdown

            try:
                controller.update()
            except Exception:
                pass
            spontaneous = _spontaneous_messages(controller)
            if spontaneous:
                _write_messages(spontaneous)

            render_start = time.perf_counter()
            ctx.viewport = window.viewport
            ctx.clear(0.02, 0.025, 0.04, 1.0)
            ctx.viewport = GAME_VIEWPORT
            renderer.render_from_pool(pool)
            ctx.viewport = window.viewport
            _draw_overlay(ui, controller)
            controller.record_render_ms((time.perf_counter() - render_start) * 1000.0)
            window.swap_buffers()

            stats_counter += 1
            if stats_counter >= 15:
                stats_counter = 0
                _write_messages(
                    [
                        {
                            "protocol_version": PREVIEW_PROTOCOL_VERSION,
                            "request_id": None,
                            "event": "statistics",
                            "payload": controller.get_stats(emit=False),
                        }
                    ]
                )
    finally:
        if controller is not None:
            controller.close()
        if audio_manager is not None:
            audio_manager.stop_bgm()
        if audio_bank is not None:
            audio_bank.clear()
        if renderer is not None:
            renderer.cleanup()
        if ui is not None:
            ui.cleanup()
        if manager is not None:
            manager.clear_all()
        window.destroy()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--resource", help="Initial res:// Pattern or Scene path")
    parser.add_argument("--pattern", help="Deprecated alias for --resource")
    parser.add_argument("--max-bullets", type=int, default=50000)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)
    project = ProjectContext(args.project)
    project.activate()
    if args.headless:
        return run_headless(project, args.max_bullets)
    return run_window(project, args.max_bullets, args.resource or args.pattern)


if __name__ == "__main__":
    raise SystemExit(main())

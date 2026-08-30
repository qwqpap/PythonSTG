"""The game window must follow external resizes (editor embedding) and the
play-field viewport must be recomputable for any framebuffer size."""

from __future__ import annotations

import glfw
import pytest

from main import compute_game_viewport_fb
from src.core.window import GameWindow


def test_framebuffer_poll_tracks_external_resize():
    """set_window_size (the editor's MoveWindow equivalent) must be picked up."""

    window = GameWindow(320, 240, "resize-test")
    try:
        assert window.framebuffer_size == (320, 240)
        assert window.viewport == (0, 0, 320, 240)

        glfw.set_window_size(window._window, 200, 150)
        window.poll_events()

        assert window.framebuffer_size == (200, 150)
        assert window.viewport == (0, 0, 200, 150)

        glfw.set_window_size(window._window, 480, 360)
        window.poll_events()

        assert window.framebuffer_size == (480, 360)
        assert window.viewport == (0, 0, 480, 360)
    finally:
        window.destroy()


def test_compute_game_viewport_fb_scales_with_framebuffer():
    game_viewport = (64, 32, 768, 896)
    screen = (1280, 960)

    # 1:1 framebuffer keeps the logical rect unchanged.
    assert compute_game_viewport_fb(game_viewport, screen, (1280, 960)) == (
        64, 32, 768, 896,
    )

    # Editor embeds at half size: the play field shrinks with it.
    assert compute_game_viewport_fb(game_viewport, screen, (640, 480)) == (
        32, 16, 384, 448,
    )

    # Degenerate framebuffer never produces a zero rect.
    scaled = compute_game_viewport_fb(game_viewport, screen, (1, 1))
    assert all(value >= 0 for value in scaled)


def test_poll_is_stable_when_size_does_not_change():
    game_window = GameWindow(320, 240, "stable-test")
    try:
        game_window.poll_events()
        assert game_window.framebuffer_size == (320, 240)
        game_window.poll_events()
        assert game_window.framebuffer_size == (320, 240)
        assert game_window.viewport == (0, 0, 320, 240)
    finally:
        game_window.destroy()

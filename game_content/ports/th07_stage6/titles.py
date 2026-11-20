"""Literal stage-6 title choreography on existing sparse animation handles.

The six std6txt sprites are original local assets, not regenerated text. This
is ordinary content: no ANM instructions are executed at runtime. Coordinates
below are source screen pixels; the playfield begins at (32, 16).
"""

from __future__ import annotations

from src.game.tasks import wait_frames

from .common import px, py


def _ramp(age, start, duration):
    return min(1.0, max(0.0, (age - start) / duration))


async def stage_titles(ctx):
    """Gui::OnAdded starts std6txt scripts 0-3 together, without blocking play."""
    specifications = (
        (5, 224.0, 240.0, 0.0, 160, 140, 630, 140),
        (0, 224.0, 223.5, -90.0, 430, 120, 730, 100),
        (1, 128.0, 160.0, 0.0, 500, 60, 750, 60),
        (2, 326.0, 288.0, 0.0, 500, 60, 850, 60),
    )
    handles = [ctx.play_animation(f'th07_std6txt_e0_s{sprite}',
                                  px(x - 32), py(y - 16),
                                  alpha=0, rotation=rotation)
               for sprite, x, y, rotation, *_ in specifications]
    age = 0.0
    try:
        while age < 910:
            for index, (handle, spec) in enumerate(zip(handles, specifications)):
                _, x, y, _, fade_start, fade_in, fade_end, fade_out = spec
                alpha = _ramp(age, fade_start, fade_in) * (1 - _ramp(age, fade_end, fade_out))
                if index == 2:
                    x += 32 * _ramp(age, 500, 180)
                elif index == 3:
                    x -= 70 * _ramp(age, 500, 180)
                handle.position = (px(x - 32), py(y - 16))
                handle.set_visual(alpha=alpha)
            await wait_frames(1, clock='control')
            age += ctx.get_simulation_rate('effects')
    finally:
        for handle in handles:
            handle.stop()


async def music_title(ctx, index):
    """Music caption uses script4 at stage start, script5 for stage6 MSG music.

    The final resurrection track has no extra source title sprite, so index2
    intentionally does not invent one. MSG itself is still separately unported.
    """
    if index not in (0, 1):
        return
    start, fade_end = (500, 700) if index == 0 else (100, 300)
    handle = ctx.play_animation(f'th07_std6txt_e0_s{3 + index}',
                                px(403.5 - 32), py(623.5 - 16),
                                alpha=0, rotation=-90)
    age = 0.0
    try:
        while age < fade_end + 60:
            t = _ramp(age, start, 120)
            y = 623.5 - 384.0 * (1 - (1 - t) ** 2)
            handle.position = (px(403.5 - 32), py(y - 16))
            handle.set_visual(alpha=_ramp(age, start, 60) *
                              (1 - _ramp(age, fade_end, 60)))
            await wait_frames(1, clock='control')
            age += ctx.get_simulation_rate('effects')
    finally:
        handle.stop()

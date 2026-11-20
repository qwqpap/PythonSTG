"""Ordinary sparse-animation translation of the original std5txt title art."""

from __future__ import annotations

from src.game.tasks import wait_frames

from ..th07_stage6.common import px, py


def _ramp(age, start, duration):
    return min(1.0, max(0.0, (age - start) / duration))


async def stage_titles(ctx):
    """Original std5txt scripts0–3, without blocking the gameplay task."""
    specifications = (
        (5, 256.0, 288.0, 0.0, 200, 140, 540, 140),
        (0, 175.5, 223.5, -90.0, 370, 160, 570, 140),
        (1, 128.0, 48.0, 0.0, 110, 60, 510, 60),
        (2, 368.0, 288.0, 0.0, 140, 60, 540, 60),
    )
    handles = [ctx.play_animation(f"th07_std5txt_e0_s{sprite}",
                                  px(x - 32), py(y - 16), alpha=0, rotation=rotation)
               for sprite, x, y, rotation, *_ in specifications]
    age = 0.0
    try:
        while age < 710:
            for index, (handle, specification) in enumerate(zip(handles, specifications)):
                _, x, y, _, fade_start, fade_in, fade_end, fade_out = specification
                alpha = _ramp(age, fade_start, fade_in) * (1 - _ramp(age, fade_end, fade_out))
                if index == 2:
                    y += 112 * _ramp(age, 110, 120)
                elif index == 3:
                    x -= 112 * _ramp(age, 140, 120)
                handle.position = px(x - 32), py(y - 16)
                handle.set_visual(alpha=alpha)
            await wait_frames(1, clock="control")
            age += ctx.get_simulation_rate("effects")
    finally:
        for handle in handles:
            handle.stop()


async def music_title(ctx, index):
    """Gui MSG_MUSIC reuses script4, replacing its sprite with 3+musicIdx."""
    if index not in (0, 1):
        raise ValueError("TH07 stage 5 music title index must be 0 or 1")
    handle = ctx.play_animation(f"th07_std5txt_e0_s{3 + index}",
                                px(403.5 - 32), py(623.5 - 16), alpha=0, rotation=-90)
    age = 0.0
    try:
        while age < 460:
            t = _ramp(age, 200, 120)
            y = 623.5 - 384 * (1 - (1 - t) ** 2)
            handle.position = px(403.5 - 32), py(y - 16)
            handle.set_visual(alpha=_ramp(age, 200, 60) * (1 - _ramp(age, 400, 60)))
            await wait_frames(1, clock="control")
            age += ctx.get_simulation_rate("effects")
    finally:
        handle.stop()

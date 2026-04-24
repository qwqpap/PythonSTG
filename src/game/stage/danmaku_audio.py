"""Shared danmaku sound heuristics."""

from typing import Tuple


def resolve_fire_sound(
    count: int = 1,
    speed: float = 2.0,
    bullet_type: str = "ball_m",
) -> Tuple[str, float, float, int]:
    """
    Pick a restrained firing sound profile.

    Returns:
        (sound_name, volume, min_interval_seconds, local_cooldown_frames)
    """
    bullet_key = str(bullet_type or "ball_m").lower()
    volley_size = max(1, int(count))
    bullet_speed = max(0.0, float(speed))

    if "laser" in bullet_key:
        return "lazer", 0.16, 0.28, 24

    if volley_size >= 12 or bullet_speed >= 4.2:
        return "enemy_shot_heavy", 0.09, 0.24, 18

    if volley_size >= 5 or bullet_speed >= 2.8:
        return "enemy_shot_mid", 0.08, 0.22, 16

    return "enemy_shot_soft", 0.06, 0.20, 14

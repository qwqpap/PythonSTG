"""Create editable examples from ordinary DSL units, not a saved preset model."""

from __future__ import annotations

from collections.abc import Collection

from src.authoring import dsl
from src.authoring.program import LogicalUnit, Ref


STARTER_PATTERNS = (("circle", "环形散射"), ("fan", "扇形弹幕"), ("aimed", "自机狙"))


def _available_id(used: set[str], base: str) -> str:
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def make_starter_wave(
    used_ids: Collection[str], pattern: str = "circle"
) -> tuple[LogicalUnit, LogicalUnit]:
    """Return an Enemy and its Wave; all steps remain directly editable."""

    used = set(used_ids)
    enemy_id = _available_id(used, "opening_enemy")
    wave_id = _available_id(used, "opening_wave")
    if pattern == "circle":
        emission = dsl.FireCircle(count=24, speed=1.5)
        name = "环形散射"
    elif pattern == "fan":
        emission = dsl.FireArc(count=7, speed=1.5, arc_angle=60.0)
        name = "扇形弹幕"
    elif pattern == "aimed":
        emission = dsl.FireAtPlayer(speed=1.5)
        name = "自机狙"
    else:
        raise ValueError(f"unknown starter pattern: {pattern}")
    enemy = dsl.Enemy(
        enemy_id, f"{name}敌人", hp=300,
        body=[dsl.Wait(30), dsl.Repeat(12, [emission, dsl.Wait(30)]), dsl.Kill()],
    )
    wave = dsl.Wave(
        wave_id, f"{name}出场", body=[dsl.SpawnEnemy(Ref(enemy_id), y=0.65), dsl.Wait(420)]
    )
    return enemy, wave


__all__ = ["STARTER_PATTERNS", "make_starter_wave"]

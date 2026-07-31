"""Runtime helpers for rendering Pattern Lab specs through the real engine."""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.devtools.pattern_lab import PatternSpec, bullet_parameters
from src.game.stage.context import StageContext


@dataclass
class PatternPlayback:
    spec: PatternSpec
    frame: int = 0
    burst_index: int = 0

    def reset(self) -> None:
        self.frame = 0
        self.burst_index = 0

    def update(self, ctx: StageContext) -> int:
        """Advance playback by one frame and spawn bullets when due."""
        self.spec.validate()
        spawned = 0
        if self.frame % self.spec.interval == 0:
            spawned = spawn_pattern_burst(ctx, self.spec, self.burst_index)
            self.burst_index = (self.burst_index + 1) % self.spec.bursts
        self.frame += 1
        return spawned


def spawn_pattern_burst(ctx: StageContext, spec: PatternSpec, burst_index: int = 0) -> int:
    """Spawn one burst with StageContext so sprite resolution matches gameplay."""
    spec.validate()
    spawned = 0
    for angle, speed in bullet_parameters(spec, burst_index):
        idx = ctx.create_bullet(
            x=spec.x,
            y=spec.y,
            angle=angle,
            speed=speed,
            bullet_type=spec.bullet_type,
            color=spec.color,
            spin=spec.spin,
        )
        if idx >= 0:
            spawned += 1
    return spawned


def _arc_start(center_angle: float, angle_span: float) -> float:
    if abs(angle_span) >= 360.0:
        return center_angle
    return center_angle - angle_span / 2.0


def _arc_step(count: int, angle_span: float) -> float:
    if count <= 1:
        return 0.0
    if abs(angle_span) >= 360.0:
        return angle_span / count
    return angle_span / (count - 1)


def preview_positions(spec: PatternSpec, age_seconds: float, burst_index: int = 0) -> list[tuple[float, float]]:
    """Geometry helper used by tests and non-rendering previews."""
    spec.validate()
    points = []
    for angle_degrees, speed in bullet_parameters(spec, burst_index):
        angle = math.radians(angle_degrees)
        points.append(
            (
                spec.x + math.cos(angle) * speed * age_seconds,
                spec.y + math.sin(angle) * speed * age_seconds,
            )
        )
    return points

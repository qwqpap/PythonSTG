"""Immutable intermediate representation consumed by the pattern runtime."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BurstTemplate:
    """Precomputed per-bullet values for one burst within a schedule loop."""

    position_offsets: tuple[tuple[float, float], ...]
    angle_offsets: tuple[float, ...]
    speeds: tuple[float, ...]

    @property
    def count(self) -> int:
        return len(self.angle_offsets)

    @property
    def angles(self) -> tuple[float, ...]:
        return self.angle_offsets


@dataclass(frozen=True)
class PatternProgram:
    """Compiled, immutable pattern data with no authoring-model dependency."""

    resource_id: str
    schema_version: int
    content_hash: str
    name: str
    seed: int
    origin: tuple[float, float]
    aim_mode: str
    aim_angle: float
    delay_frames: int
    interval_frames: int
    burst_count: int
    loop_count: int | None
    bullet_type: str
    color: str
    resource_uri: str | None
    sprite_id: str
    sprite_index: int
    friction: float
    spin: float
    time_scale: float
    max_lifetime: float
    render_scale: float
    bounce_x: bool
    bounce_y: bool
    templates: tuple[BurstTemplate, ...]

    @property
    def total_emissions(self) -> int | None:
        if self.loop_count is None:
            return None
        return self.burst_count * self.loop_count

    def template_for_emission(self, emission_index: int) -> BurstTemplate:
        return self.templates[emission_index % self.burst_count]

"""Fixed-tick execution of immutable PatternProgram objects."""

from __future__ import annotations

import math
import itertools
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .ir import PatternProgram


class PatternRunnerState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    ERROR = "error"


class PatternRuntimeError(RuntimeError):
    def __init__(self, resource_id: str, frame: int, message: str):
        self.resource_id = resource_id
        self.frame = frame
        self.path = "runtime"
        self.detail = message
        super().__init__(f"{resource_id} at frame {frame}: {message}")


@dataclass(frozen=True)
class PatternSpawnEvent:
    frame: int
    burst_index: int
    loop_index: int
    owner_tag: int
    positions: tuple[tuple[float, float], ...]
    angles: tuple[float, ...]
    speeds: tuple[float, ...]
    indices: tuple[int, ...]

    @property
    def requested_count(self) -> int:
        return len(self.angles)

    @property
    def spawned_count(self) -> int:
        return len(self.indices)


@dataclass(frozen=True)
class PatternTickResult:
    frame: int
    state: PatternRunnerState
    event: PatternSpawnEvent | None = None

    @property
    def spawned_count(self) -> int:
        return self.event.spawned_count if self.event is not None else 0


_OWNER_TAGS = itertools.count(100_000)


def _next_owner_tag() -> int:
    """Allocate a process-unique tag in the author-owned positive namespace."""
    tag = next(_OWNER_TAGS)
    if tag > 2_147_483_647:
        raise RuntimeError("pattern owner tag namespace exhausted")
    return tag


class PatternRunner:
    """One deterministic runtime instance of a compiled pattern.

    The runner schedules bursts only. Bullet motion remains in the formal
    NumPy/Numba pool and no per-bullet Python update callbacks are installed.
    """

    def __init__(
        self,
        program: PatternProgram,
        *,
        instance_id: str | None = None,
        owner_tag: int | None = None,
    ) -> None:
        self.program = program
        self.instance_id = instance_id or str(uuid.uuid4())
        self.owner_tag = int(owner_tag) if owner_tag is not None else _next_owner_tag()
        if self.owner_tag < 100:
            raise ValueError("owner_tag must be at least 100 (0..99 are engine-reserved)")
        self.state = PatternRunnerState.STOPPED
        self.frame = 0
        self.emission_count = 0
        self.last_event: PatternSpawnEvent | None = None
        self.last_error: PatternRuntimeError | None = None

    def start(
        self,
        context: Any | None = None,
        *,
        reset: bool = True,
        clear_owned: bool = True,
    ) -> None:
        if reset:
            self.reset(context, clear_owned=clear_owned)
        self.state = PatternRunnerState.RUNNING

    def pause(self) -> None:
        if self.state == PatternRunnerState.RUNNING:
            self.state = PatternRunnerState.PAUSED

    def resume(self) -> None:
        if self.state == PatternRunnerState.PAUSED:
            self.state = PatternRunnerState.RUNNING

    def reset(self, context: Any | None = None, *, clear_owned: bool = True) -> None:
        if clear_owned and context is not None:
            self.clear_owned(context)
        self.state = PatternRunnerState.STOPPED
        self.frame = 0
        self.emission_count = 0
        self.last_event = None
        self.last_error = None

    def stop(self, context: Any | None = None, *, clear_owned: bool = True) -> None:
        self.reset(context, clear_owned=clear_owned)

    def clear_owned(self, context: Any) -> None:
        context.clear_bullets_by_tag(self.owner_tag)

    def set_owned_time_scale(self, context: Any, scale: float) -> None:
        if not math.isfinite(scale) or scale < 0:
            raise ValueError("time scale must be finite and non-negative")
        context.set_time_scale(scale, tag=self.owner_tag)

    def translate_owned(self, context: Any, dx: float, dy: float) -> int:
        if not math.isfinite(dx) or not math.isfinite(dy):
            raise ValueError("translation must be finite")
        return int(context.translate_bullets_by_tag(self.owner_tag, dx, dy))

    def tick(self, context: Any) -> PatternTickResult:
        current_frame = self.frame
        if self.state != PatternRunnerState.RUNNING:
            return PatternTickResult(current_frame, self.state)

        event = None
        if self._emission_due(current_frame):
            try:
                event = self._spawn(context, current_frame)
            except Exception as exc:
                error = PatternRuntimeError(
                    self.program.resource_id,
                    current_frame,
                    str(exc),
                )
                self.last_error = error
                self.state = PatternRunnerState.ERROR
                raise error from exc
            self.last_event = event
            self.emission_count += 1
            total = self.program.total_emissions
            if total is not None and self.emission_count >= total:
                self.state = PatternRunnerState.FINISHED

        self.frame += 1
        return PatternTickResult(current_frame, self.state, event)

    def advance(self, context: Any, frames: int) -> tuple[PatternTickResult, ...]:
        if isinstance(frames, bool) or not isinstance(frames, int) or frames < 0:
            raise ValueError("frames must be a non-negative integer")
        return tuple(self.tick(context) for _ in range(frames))

    def _emission_due(self, frame: int) -> bool:
        total = self.program.total_emissions
        if total is not None and self.emission_count >= total:
            return False
        if frame < self.program.delay_frames:
            return False
        return (frame - self.program.delay_frames) % self.program.interval_frames == 0

    def _spawn(self, context: Any, frame: int) -> PatternSpawnEvent:
        burst_index = self.emission_count % self.program.burst_count
        loop_index = self.emission_count // self.program.burst_count
        template = self.program.template_for_emission(self.emission_count)
        origin_x, origin_y = self.program.origin
        base_angle = self.program.aim_angle
        if self.program.aim_mode == "player":
            player = context.get_player()
            if player is None:
                raise RuntimeError("player aim requires an active player")
            base_angle = math.degrees(
                math.atan2(player.y - origin_y, player.x - origin_x)
            )
        positions = tuple(
            (origin_x + x, origin_y + y)
            for x, y in template.position_offsets
        )
        angles = tuple(base_angle + value for value in template.angle_offsets)
        indices = context.create_bullets_batch(
            positions=positions,
            angles=angles,
            speeds=template.speeds,
            bullet_type=self.program.bullet_type,
            color=self.program.color,
            sprite_id=self.program.sprite_id or None,
            sprite_idx=self.program.sprite_index,
            tag=self.owner_tag,
            friction=self.program.friction,
            time_scale=self.program.time_scale,
            spin=self.program.spin,
            max_lifetime=self.program.max_lifetime,
            render_scale=self.program.render_scale,
            bounce_x=self.program.bounce_x,
            bounce_y=self.program.bounce_y,
        )
        return PatternSpawnEvent(
            frame=frame,
            burst_index=burst_index,
            loop_index=loop_index,
            owner_tag=self.owner_tag,
            positions=positions,
            angles=angles,
            speeds=template.speeds,
            indices=tuple(int(index) for index in indices),
        )

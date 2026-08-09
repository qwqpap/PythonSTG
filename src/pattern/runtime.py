"""Fixed-tick execution of immutable PatternProgram objects."""

from __future__ import annotations

import math
import itertools
import random
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .compiler import BINDABLE_TARGETS, build_burst_template
from .bindings import CompiledBinding
from .document import ModifierSpec, MotionSpec, ShapeSpec
from .expressions import ExpressionError, evaluate_node
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


def _eval_curve(binding: CompiledBinding, frame: float) -> float:
    """Sample compiled curve data with the curve resource semantics."""
    if not binding.curve_frames:
        return float(binding.curve_default)
    if frame < binding.curve_frames[0]:
        return float(binding.curve_default)
    if frame >= binding.curve_frames[-1]:
        return float(binding.curve_values[-1])
    if binding.curve_interpolation == "step":
        value = binding.curve_values[0]
        for keyframe, key_value in zip(
            binding.curve_frames, binding.curve_values
        ):
            if keyframe <= frame:
                value = key_value
            else:
                break
        return float(value)
    for index in range(len(binding.curve_frames) - 1):
        start = binding.curve_frames[index]
        end = binding.curve_frames[index + 1]
        if start <= frame < end:
            span = float(end - start)
            t = (frame - float(start)) / span
            left = binding.curve_values[index]
            right = binding.curve_values[index + 1]
            if binding.curve_interpolation == "linear":
                return float(left + (right - left) * t)
            if binding.curve_interpolation == "cubic":
                p0 = (
                    binding.curve_values[index - 1]
                    if index > 0
                    else binding.curve_values[index]
                )
                p1 = left
                p2 = right
                p3 = (
                    binding.curve_values[index + 2]
                    if index + 2 < len(binding.curve_frames)
                    else p2
                )
                return float(
                    0.5
                    * (
                        2 * p1
                        + (-p0 + p2) * t
                        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                        + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t
                    )
                )
            raise PatternRuntimeError("binding", 0, "unsupported curve interpolation")
    return float(binding.curve_values[-1])


def _binding_value(
    program: PatternProgram,
    binding: CompiledBinding,
    frame: int,
    burst_index: int,
    context: Any,
) -> float:
    if binding.mode == "constant":
        return binding.value
    if binding.mode == "variable":
        name = str(binding.value)
        if name == "random":
            rng = _binding_rng(program, frame, burst_index)
            return float(rng.random())
        variables = _binding_variables(program, frame, burst_index, context)
        if name in variables:
            return float(variables[name])
        hook = getattr(context, "get_variable", None)
        if callable(hook):
            try:
                return float(hook(name))
            except Exception as exc:  # noqa: BLE001 - formal runtime wraps the path
                raise PatternRuntimeError(
                    program.resource_id,
                    frame,
                    f"variable binding {name!r} could not be read: {exc}",
                ) from exc
        return 0.0
    if binding.mode == "curve":
        return _eval_curve(binding, float(frame))
    if binding.mode == "expression":
        variables = _binding_variables(program, frame, burst_index, context)
        try:
            return evaluate_node(binding.expression_node, variables)
        except ExpressionError as exc:
            raise PatternRuntimeError(
                program.resource_id, frame, exc.message
            ) from exc
    raise PatternRuntimeError(
        program.resource_id, frame, f"unknown binding mode {binding.mode!r}"
    )


def _binding_for(program: PatternProgram, path: str) -> CompiledBinding | None:
    return next(
        (binding for binding in program.bindings if binding.target_path == path),
        None,
    )


def _coerce_runtime_binding(
    program: PatternProgram,
    path: str,
    value: Any,
    frame: int,
) -> Any:
    """Apply the same typed property boundary at the runtime emission edge."""
    target = BINDABLE_TARGETS[path]
    if target == "bool":
        if not isinstance(value, bool):
            raise PatternRuntimeError(program.resource_id, frame, f"{path} requires a boolean")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PatternRuntimeError(program.resource_id, frame, f"{path} requires a number")
    number = float(value)
    if not math.isfinite(number):
        raise PatternRuntimeError(program.resource_id, frame, f"{path} must be finite")
    if target == "int":
        if not number.is_integer():
            raise PatternRuntimeError(program.resource_id, frame, f"{path} requires an integer")
        number = int(number)
        if path == "shape.count" and not 1 <= number <= 4096:
            raise PatternRuntimeError(program.resource_id, frame, f"{path} must be in 1..4096")
        if path == "schedule.delay_frames" and number < 0:
            raise PatternRuntimeError(program.resource_id, frame, f"{path} must be non-negative")
        if path in {"schedule.interval_frames", "schedule.burst_count"} and number < 1:
            raise PatternRuntimeError(program.resource_id, frame, f"{path} must be positive")
        if path == "schedule.loop_count" and number < 1:
            raise PatternRuntimeError(program.resource_id, frame, f"{path} must be positive")
        return number
    if path == "motion.speed" and number < 0:
        raise PatternRuntimeError(program.resource_id, frame, f"{path} must be non-negative")
    if path in {"motion.friction", "motion.time_scale", "motion.max_lifetime"} and number < 0:
        raise PatternRuntimeError(program.resource_id, frame, f"{path} must be non-negative")
    if path == "motion.render_scale" and number <= 0:
        raise PatternRuntimeError(program.resource_id, frame, f"{path} must be positive")
    if path == "modifiers.random_speed_variation" and not 0 <= number <= 1:
        raise PatternRuntimeError(program.resource_id, frame, f"{path} must be in 0..1")
    return number


def _runtime_parameters(
    program: PatternProgram,
    frame: int,
    burst_index: int,
    context: Any,
) -> dict[str, Any]:
    """Resolve all declared bindings once for one fixed-tick emission."""
    params: dict[str, Any] = {
        "shape.count": program.shape_count,
        "shape.origin_x": program.origin[0],
        "shape.origin_y": program.origin[1],
        "shape.angle_span": program.shape_angle_span,
        "shape.line_length": program.shape_line_length,
        "shape.line_angle": program.shape_line_angle,
        "aim.angle": program.aim_angle,
        "schedule.delay_frames": program.delay_frames,
        "schedule.interval_frames": program.interval_frames,
        "schedule.burst_count": program.burst_count,
        "schedule.loop_count": program.loop_count,
        "motion.speed": program.speed,
        "motion.friction": program.friction,
        "motion.spin": program.spin,
        "motion.time_scale": program.time_scale,
        "motion.max_lifetime": program.max_lifetime,
        "motion.render_scale": program.render_scale,
        "motion.bounce_x": program.bounce_x,
        "motion.bounce_y": program.bounce_y,
        "modifiers.angle_offset_per_burst": program.angle_offset_per_burst,
        "modifiers.speed_offset_per_burst": program.speed_offset_per_burst,
        "modifiers.random_speed_variation": program.random_speed_variation,
    }
    for path, binding in ((item.target_path, item) for item in program.bindings):
        params[path] = _coerce_runtime_binding(
            program,
            path,
            _binding_value(program, binding, frame, burst_index, context),
            frame,
        )
    return params


def _binding_rng(program: PatternProgram, frame: int, burst_index: int) -> random.Random:
    seed = (program.seed + frame * 2654435761 + burst_index * 0x9E3779B97F4A7C15) & 0x7FFF_FFFF_FFFF_FFFF
    return random.Random(seed)


def _binding_variables(
    program: PatternProgram,
    frame: int,
    burst_index: int,
    context: Any,
) -> dict[str, Any]:
    player_x = 0.0
    player_y = 0.0
    if context is not None and hasattr(context, "get_player"):
        player = context.get_player()
        if player is not None:
            player_x = float(getattr(player, "x", 0.0))
            player_y = float(getattr(player, "y", 0.0))
    return {
        "frame": float(frame),
        "time": float(frame) / 60.0,
        "burst_index": float(burst_index),
        "player_x": player_x,
        "player_y": player_y,
        "boss_x": 0.0,
        "boss_y": 0.0,
        "rng": _binding_rng(program, frame, burst_index),
    }


class _ScriptHost:
    """Lazy, explicit script module host. Never installs per-bullet callbacks."""

    def __init__(self, program: PatternProgram) -> None:
        data = program.script
        if data is None:
            raise PatternRuntimeError(program.resource_id, 0, "no script in program")
        import importlib.util

        module_name = f"pystg_script_{abs(hash(data.script_path))}"
        spec = importlib.util.spec_from_file_location(
            module_name, data.script_path
        )
        if spec is None or spec.loader is None:
            raise PatternRuntimeError(
                program.resource_id, 0, f"cannot load script {data.script_path}"
            )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._module = module

    def _call(self, hook: str, *args: Any) -> None:
        callback = getattr(self._module, hook, None)
        if callback is not None:
            callback(*args)

    def start(self, context: Any) -> None:
        self._call("load", context)
        self._call("start", context)

    def update(self, context: Any, frame: int) -> None:
        self._call("update", context, frame)

    def on_event(self, context: Any, event_type: str, data: Any) -> None:
        self._call("on_event", context, event_type, data)

    def stop(self, context: Any) -> None:
        self._call("stop", context)


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
        self.spawn_trace: list[PatternSpawnEvent] = []
        self.replay_identity: dict[str, Any] = {
            "program_hash": program.content_hash,
            "seed": program.seed,
            "instance_id": self.instance_id,
        }
        self.last_error: PatternRuntimeError | None = None
        self._script_host: _ScriptHost | None = None

    def start(
        self,
        context: Any | None = None,
        *,
        reset: bool = True,
        clear_owned: bool = True,
    ) -> None:
        # Starting an already-running instance is always idempotent.  Callers
        # that need a restart must reset/stop explicitly before starting; a
        # repeated start may never invoke script load/start twice.
        if self.state == PatternRunnerState.RUNNING:
            return
        if reset:
            self.reset(context, clear_owned=clear_owned)
        try:
            if self.program.script is not None and context is not None:
                if self._script_host is None:
                    self._script_host = _ScriptHost(self.program)
                self._script_host.start(context)
        except PatternRuntimeError:
            self.state = PatternRunnerState.ERROR
            raise
        except Exception as exc:
            error = PatternRuntimeError(self.program.resource_id, self.frame, str(exc))
            self.last_error = error
            self.state = PatternRunnerState.ERROR
            raise error from exc
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
        self.spawn_trace.clear()
        self.last_error = None
        self.replay_identity = {
            "program_hash": self.program.content_hash,
            "seed": self.program.seed,
            "instance_id": self.instance_id,
        }

    def stop(self, context: Any | None = None, *, clear_owned: bool = True) -> None:
        if self.state == PatternRunnerState.STOPPED:
            return
        hook_error: PatternRuntimeError | None = None
        try:
            if context is not None and self._script_host is not None:
                self._script_host.stop(context)
        except PatternRuntimeError as exc:
            hook_error = exc
        except Exception as exc:
            hook_error = PatternRuntimeError(self.program.resource_id, self.frame, str(exc))
        finally:
            self.reset(context, clear_owned=clear_owned)
            self.state = PatternRunnerState.STOPPED
        if hook_error is not None:
            self.last_error = hook_error
            raise hook_error

    def notify_event(self, context: Any, event_type: str, data: Any) -> None:
        """Deliver one typed external event to the script's ``on_event`` hook."""
        if self.state != PatternRunnerState.RUNNING:
            return
        if self._script_host is not None:
            try:
                self._script_host.on_event(context, event_type, data)
            except PatternRuntimeError:
                self.state = PatternRunnerState.ERROR
                raise
            except Exception as exc:
                error = PatternRuntimeError(self.program.resource_id, self.frame, str(exc))
                self.last_error = error
                self.state = PatternRunnerState.ERROR
                raise error from exc

    def clear_owned(self, context: Any) -> None:
        try:
            context.clear_bullets_by_tag(self.owner_tag, reason="owner_cancelled")
        except TypeError:
            # Compatibility contexts predating the formal lifecycle reason
            # contract still receive the same owner-scoped clear operation.
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

        if self.state in {
            PatternRunnerState.STOPPED,
            PatternRunnerState.PAUSED,
            PatternRunnerState.ERROR,
        }:
            return PatternTickResult(current_frame, self.state)

        if self._script_host is not None:
            try:
                self._script_host.update(context, current_frame)
            except Exception as exc:
                error = PatternRuntimeError(
                    self.program.resource_id,
                    current_frame,
                    str(exc),
                )
                self.last_error = error
                self.state = PatternRunnerState.ERROR
                raise error from exc

        if self.state == PatternRunnerState.FINISHED:
            self.frame += 1
            return PatternTickResult(current_frame, self.state)

        event = None
        try:
            parameters = _runtime_parameters(
                self.program, current_frame, self.emission_count, context
            )
            if self._emission_due(current_frame, parameters):
                event = self._spawn(context, current_frame, parameters)
                self.last_event = event
                self.spawn_trace.append(event)
                self.emission_count += 1
                total = self._total_emissions(parameters)
                if total is not None and self.emission_count >= total:
                    self.state = PatternRunnerState.FINISHED
        except PatternRuntimeError:
            raise
        except Exception as exc:
            error = PatternRuntimeError(
                self.program.resource_id,
                current_frame,
                str(exc),
            )
            self.last_error = error
            self.state = PatternRunnerState.ERROR
            raise error from exc

        self.frame += 1
        return PatternTickResult(current_frame, self.state, event)

    def advance(self, context: Any, frames: int) -> tuple[PatternTickResult, ...]:
        if isinstance(frames, bool) or not isinstance(frames, int) or frames < 0:
            raise ValueError("frames must be a non-negative integer")
        return tuple(self.tick(context) for _ in range(frames))

    def seek(self, context: Any, frame: int) -> tuple[PatternTickResult, ...]:
        """Reset and replay deterministic fixed ticks to ``frame``."""

        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError("frame must be a non-negative integer")
        self.reset(context)
        self.start(context, reset=False)
        results = tuple(self.tick(context) for _ in range(frame))
        self.pause()
        self.replay_identity["actual_trigger_frames"] = [event.frame for event in self.spawn_trace]
        return results

    def reset_clip(self, context: Any | None = None) -> None:
        """Reset this PatternRunner's owning Clip instance."""

        self.reset(context)

    def seek_clip(self, context: Any, frame: int) -> tuple[PatternTickResult, ...]:
        """Clip-level alias for the deterministic pattern seek contract."""

        return self.seek(context, frame)

    def _total_emissions(self, parameters: dict[str, Any]) -> int | None:
        loop_count = parameters["schedule.loop_count"]
        if loop_count is None:
            return None
        return int(parameters["schedule.burst_count"]) * int(loop_count)

    def _emission_due(self, frame: int, parameters: dict[str, Any]) -> bool:
        total = self._total_emissions(parameters)
        if total is not None and self.emission_count >= total:
            return False
        delay = int(parameters["schedule.delay_frames"])
        interval = int(parameters["schedule.interval_frames"])
        if frame < delay:
            return False
        return (frame - delay) % interval == 0

    def _spawn(
        self,
        context: Any,
        frame: int,
        parameters: dict[str, Any] | None = None,
    ) -> PatternSpawnEvent:
        if parameters is None:
            parameters = _runtime_parameters(
                self.program, frame, self.emission_count, context
            )
        burst_count = int(parameters["schedule.burst_count"])
        burst_index = self.emission_count % burst_count
        loop_index = self.emission_count // burst_count
        shape = ShapeSpec(
            kind=self.program.shape_kind,
            count=int(parameters["shape.count"]),
            origin_x=float(parameters["shape.origin_x"]),
            origin_y=float(parameters["shape.origin_y"]),
            angle_span=float(parameters["shape.angle_span"]),
            line_length=float(parameters["shape.line_length"]),
            line_angle=float(parameters["shape.line_angle"]),
        )
        motion = MotionSpec(
            speed=float(parameters["motion.speed"]),
            friction=float(parameters["motion.friction"]),
            spin=float(parameters["motion.spin"]),
            time_scale=float(parameters["motion.time_scale"]),
            max_lifetime=float(parameters["motion.max_lifetime"]),
            render_scale=float(parameters["motion.render_scale"]),
            bounce_x=bool(parameters["motion.bounce_x"]),
            bounce_y=bool(parameters["motion.bounce_y"]),
        )
        modifiers = ModifierSpec(
            angle_offset_per_burst=float(parameters["modifiers.angle_offset_per_burst"]),
            speed_offset_per_burst=float(parameters["modifiers.speed_offset_per_burst"]),
            random_speed_variation=float(parameters["modifiers.random_speed_variation"]),
        )
        template = build_burst_template(
            shape=shape,
            motion=motion,
            modifiers=modifiers,
            seed=self.program.seed,
            burst_index=burst_index,
        )
        origin_x, origin_y = float(parameters["shape.origin_x"]), float(parameters["shape.origin_y"])
        base_angle = float(parameters["aim.angle"])
        if self.program.aim_mode == "player":
            player = context.get_player()
            if player is None:
                raise RuntimeError("player aim requires an active player")
            base_angle = math.degrees(
                math.atan2(player.y - origin_y, player.x - origin_x)
            )
        speeds = template.speeds
        positions = tuple(
            (origin_x + x, origin_y + y)
            for x, y in template.position_offsets
        )
        angles = tuple(base_angle + value for value in template.angle_offsets)
        indices = context.create_bullets_batch(
            positions=positions,
            angles=angles,
            speeds=speeds,
            bullet_type=self.program.bullet_type,
            color=self.program.color,
            sprite_id=self.program.sprite_id or None,
            sprite_idx=self.program.sprite_index,
            tag=self.owner_tag,
            friction=float(parameters["motion.friction"]),
            time_scale=float(parameters["motion.time_scale"]),
            spin=float(parameters["motion.spin"]),
            max_lifetime=float(parameters["motion.max_lifetime"]),
            render_scale=float(parameters["motion.render_scale"]),
            bounce_x=bool(parameters["motion.bounce_x"]),
            bounce_y=bool(parameters["motion.bounce_y"]),
        )
        return PatternSpawnEvent(
            frame=frame,
            burst_index=burst_index,
            loop_index=loop_index,
            owner_tag=self.owner_tag,
            positions=positions,
            angles=angles,
            speeds=speeds,
            indices=tuple(int(index) for index in indices),
        )

    def _speed_binding(self) -> CompiledBinding | None:
        for binding in self.program.bindings:
            if binding.target_path == "motion.speed":
                return binding
        return None

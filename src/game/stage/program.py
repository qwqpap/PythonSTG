"""Immutable StageProgram data and deterministic fixed-tick execution.

The authoring editor compiles Scene/Timeline resources into these runtime-only
records.  High-density bullets remain owned by ``PatternRunner`` and the
formal bullet pool; a StageProgram only schedules sparse semantic work.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.pattern import PatternProgram, PatternRunner, PatternRunnerState


def _decode_json(value: str) -> Any:
    return json.loads(value)


@dataclass(frozen=True)
class StageNode:
    node_id: str
    node_type: str
    name: str
    properties_json: str

    @property
    def properties(self) -> dict[str, Any]:
        return dict(_decode_json(self.properties_json))


@dataclass(frozen=True)
class StageKeyframe:
    frame: int
    value_json: str
    interpolation: str = "linear"

    @property
    def value(self) -> Any:
        return _decode_json(self.value_json)


@dataclass(frozen=True)
class StageAutomation:
    track_id: str
    clip_id: str
    kind: str
    target_id: str
    channel: str
    property_name: str
    start_frame: int
    duration_frames: int
    loop_count: int
    track_order: int
    clip_order: int
    keyframes: tuple[StageKeyframe, ...]

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.duration_frames * self.loop_count

    @property
    def order_key(self) -> tuple[int, int, str]:
        return (self.track_order, self.clip_order, self.clip_id)


@dataclass(frozen=True)
class StageAction:
    frame: int
    track_id: str
    clip_id: str
    kind: str
    target_id: str | None
    channel: str
    track_order: int
    clip_order: int
    payload_json: str

    @property
    def payload(self) -> dict[str, Any]:
        return dict(_decode_json(self.payload_json))

    @property
    def order_key(self) -> tuple[int, int, str]:
        return (self.track_order, self.clip_order, self.clip_id)


@dataclass(frozen=True)
class PatternSchedule:
    track_id: str
    clip_id: str
    target_id: str | None
    position_target_id: str | None
    channel: str
    start_frame: int
    duration_frames: int
    loop_count: int
    track_order: int
    clip_order: int
    resource_uri: str
    base_origin: tuple[float, float]
    program: PatternProgram

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.duration_frames * self.loop_count

    @property
    def order_key(self) -> tuple[int, int, str]:
        return (self.track_order, self.clip_order, self.clip_id)


@dataclass(frozen=True)
class StageProgram:
    resource_id: str
    schema_version: int
    content_hash: str
    name: str
    tick_rate: int
    duration_frames: int
    nodes: tuple[StageNode, ...]
    patterns: tuple[PatternSchedule, ...]
    automations: tuple[StageAutomation, ...]
    actions: tuple[StageAction, ...]


class StageRunnerState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    ERROR = "error"


class StageRuntimeError(RuntimeError):
    def __init__(
        self,
        resource_id: str,
        frame: int,
        message: str,
        *,
        clip_id: str | None = None,
    ) -> None:
        self.resource_id = resource_id
        self.frame = frame
        self.clip_id = clip_id
        self.path = f"clips.{clip_id}" if clip_id else "runtime"
        self.detail = message
        super().__init__(f"{resource_id} at frame {frame}: {message}")


@dataclass(frozen=True)
class StageTraceEvent:
    frame: int
    kind: str
    track_id: str
    clip_id: str
    target_id: str | None
    channel: str
    value_json: str

    @property
    def value(self) -> Any:
        return _decode_json(self.value_json)


@dataclass(frozen=True)
class StageTickResult:
    frame: int
    state: StageRunnerState
    events: tuple[StageTraceEvent, ...] = ()
    spawned_count: int = 0


@dataclass
class _ActivePattern:
    schedule: PatternSchedule
    loop_index: int
    end_frame: int
    runner: PatternRunner


class _ShiftedPlayer:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _PatternContext:
    """Translate one PatternRunner origin to a timeline-driven node position."""

    def __init__(self, context: Any, stage: "StageRunner", schedule: PatternSchedule):
        self._context = context
        self._stage = stage
        self._schedule = schedule

    def _delta(self) -> tuple[float, float]:
        target_id = self._schedule.position_target_id
        state = self._stage.node_state.get(target_id or "", {})
        x = state.get("x", self._schedule.base_origin[0])
        y = state.get("y", self._schedule.base_origin[1])
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            x = self._schedule.base_origin[0]
        if isinstance(y, bool) or not isinstance(y, (int, float)):
            y = self._schedule.base_origin[1]
        return (
            float(x) - self._schedule.base_origin[0],
            float(y) - self._schedule.base_origin[1],
        )

    def create_bullets_batch(self, **kwargs):
        dx, dy = self._delta()
        kwargs["positions"] = tuple(
            (float(x) + dx, float(y) + dy)
            for x, y in kwargs.get("positions", ())
        )
        return self._context.create_bullets_batch(**kwargs)

    def get_player(self):
        player = self._context.get_player()
        if player is None:
            return None
        dx, dy = self._delta()
        # PatternRunner aims from its immutable base origin. Shifting the
        # player by the inverse delta produces the same vector as aiming from
        # the current timeline-driven emitter position.
        return _ShiftedPlayer(float(player.x) - dx, float(player.y) - dy)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _interpolate(left: Any, right: Any, amount: float) -> Any:
    if _number(left) and _number(right):
        return float(left) + (float(right) - float(left)) * amount
    if isinstance(left, dict) and isinstance(right, dict) and left.keys() == right.keys():
        return {
            key: _interpolate(left[key], right[key], amount)
            for key in left
        }
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [_interpolate(a, b, amount) for a, b in zip(left, right)]
    return left if amount < 1.0 else right


def _ease(mode: str, amount: float) -> float:
    value = max(0.0, min(1.0, amount))
    if mode == "step":
        return 0.0
    if mode == "ease_in":
        return value * value
    if mode == "ease_out":
        return 1.0 - (1.0 - value) * (1.0 - value)
    if mode == "ease_in_out":
        return value * value * (3.0 - 2.0 * value)
    return value


class StageRunner:
    """Execute one immutable StageProgram at a fixed document tick rate."""

    def __init__(self, program: StageProgram) -> None:
        self.program = program
        self.state = StageRunnerState.STOPPED
        self.frame = 0
        self.last_error: StageRuntimeError | None = None
        self.node_state: dict[str, dict[str, Any]] = {}
        self.trace: list[StageTraceEvent] = []
        self.last_events: tuple[StageTraceEvent, ...] = ()
        self._active_patterns: dict[tuple[str, int], _ActivePattern] = {}
        self._automation_values = {
            item.clip_id: tuple(keyframe.value for keyframe in item.keyframes)
            for item in program.automations
        }
        self._restore_node_state()

    @property
    def active_clip_ids(self) -> tuple[str, ...]:
        active = {item.schedule.clip_id for item in self._active_patterns.values()}
        active.update(
            item.clip_id
            for item in self.program.automations
            if item.start_frame <= self.frame < item.end_frame
        )
        return tuple(sorted(active))

    def _restore_node_state(self) -> None:
        self.node_state = {
            item.node_id: item.properties
            for item in self.program.nodes
        }

    def start(
        self,
        context: Any | None = None,
        *,
        reset: bool = True,
        clear_owned: bool = True,
    ) -> None:
        if reset:
            self.reset(context, clear_owned=clear_owned)
        self.state = StageRunnerState.RUNNING

    def pause(self) -> None:
        if self.state == StageRunnerState.RUNNING:
            self.state = StageRunnerState.PAUSED
            for item in self._active_patterns.values():
                item.runner.pause()

    def resume(self) -> None:
        if self.state == StageRunnerState.PAUSED:
            self.state = StageRunnerState.RUNNING
            for item in self._active_patterns.values():
                item.runner.resume()

    def reset(self, context: Any | None = None, *, clear_owned: bool = True) -> None:
        self._stop_all_patterns(context, clear_owned=clear_owned)
        self.frame = 0
        self.state = StageRunnerState.STOPPED
        self.last_error = None
        self.trace.clear()
        self.last_events = ()
        self._restore_node_state()

    def stop(self, context: Any | None = None, *, clear_owned: bool = True) -> None:
        self.reset(context, clear_owned=clear_owned)

    def _stop_all_patterns(self, context: Any | None, *, clear_owned: bool) -> None:
        for item in tuple(self._active_patterns.values()):
            item.runner.stop(context, clear_owned=clear_owned and context is not None)
        self._active_patterns.clear()

    def tick(self, context: Any, *, dispatch_actions: bool = True) -> StageTickResult:
        current = self.frame
        if self.state != StageRunnerState.RUNNING:
            return StageTickResult(current, self.state)
        if current >= self.program.duration_frames:
            self._finish(context)
            return StageTickResult(current, self.state)

        events: list[StageTraceEvent] = []
        spawned_count = 0
        active_clip: str | None = None
        try:
            self._expire_patterns(context, current, events)
            self._apply_automations(context, current, events)
            self._start_patterns(context, current, events)
            self._dispatch_actions(context, current, events, dispatch=dispatch_actions)
            for key in sorted(
                self._active_patterns,
                key=lambda value: self._active_patterns[value].schedule.order_key,
            ):
                item = self._active_patterns[key]
                active_clip = item.schedule.clip_id
                target_state = self.node_state.get(item.schedule.target_id or "", {})
                if target_state.get("enabled", True) is False:
                    continue
                result = item.runner.tick(
                    _PatternContext(context, self, item.schedule)
                )
                if result.event is not None:
                    spawned_count += result.spawned_count
                    event = result.event
                    trace = self._trace_event(
                        current,
                        "pattern_spawn",
                        item.schedule.track_id,
                        item.schedule.clip_id,
                        item.schedule.target_id,
                        item.schedule.channel,
                        {
                            "loop_index": item.loop_index,
                            "pattern_loop_index": event.loop_index,
                            "burst_index": event.burst_index,
                            "requested_count": event.requested_count,
                            "spawned_count": event.spawned_count,
                            "spawn_hash": self._spawn_hash(event),
                        },
                    )
                    events.append(trace)
            self.frame += 1
            if self.frame >= self.program.duration_frames:
                self._finish(context, events=events)
        except Exception as exc:
            error = StageRuntimeError(
                self.program.resource_id,
                current,
                str(exc),
                clip_id=active_clip,
            )
            self.last_error = error
            self.state = StageRunnerState.ERROR
            raise error from exc

        self.trace.extend(events)
        self.last_events = tuple(events)
        return StageTickResult(current, self.state, tuple(events), spawned_count)

    def advance(
        self,
        context: Any,
        frames: int,
        *,
        dispatch_actions: bool = True,
    ) -> tuple[StageTickResult, ...]:
        if isinstance(frames, bool) or not isinstance(frames, int) or frames < 0:
            raise ValueError("frames must be a non-negative integer")
        return tuple(
            self.tick(context, dispatch_actions=dispatch_actions)
            for _ in range(frames)
        )

    def _finish(self, context: Any, *, events: list[StageTraceEvent] | None = None) -> None:
        target = events if events is not None else []
        self._expire_patterns(context, self.program.duration_frames, target, force=True)
        self.state = StageRunnerState.FINISHED

    def _expire_patterns(
        self,
        context: Any,
        frame: int,
        events: list[StageTraceEvent],
        *,
        force: bool = False,
    ) -> None:
        expired = [
            key
            for key, item in self._active_patterns.items()
            if force or item.end_frame <= frame
        ]
        for key in sorted(expired):
            item = self._active_patterns.pop(key)
            item.runner.stop(context, clear_owned=True)
            events.append(
                self._trace_event(
                    frame,
                    "pattern_stop",
                    item.schedule.track_id,
                    item.schedule.clip_id,
                    item.schedule.target_id,
                    item.schedule.channel,
                    {"loop_index": item.loop_index},
                )
            )

    def _start_patterns(
        self,
        context: Any,
        frame: int,
        events: list[StageTraceEvent],
    ) -> None:
        for schedule in self.program.patterns:
            relative = frame - schedule.start_frame
            if relative < 0 or relative % schedule.duration_frames:
                continue
            loop_index = relative // schedule.duration_frames
            if loop_index >= schedule.loop_count:
                continue
            key = (schedule.clip_id, loop_index)
            if key in self._active_patterns:
                continue
            runner = PatternRunner(schedule.program)
            runner.start(
                _PatternContext(context, self, schedule),
                reset=False,
            )
            self._active_patterns[key] = _ActivePattern(
                schedule=schedule,
                loop_index=loop_index,
                end_frame=frame + schedule.duration_frames,
                runner=runner,
            )
            events.append(
                self._trace_event(
                    frame,
                    "pattern_start",
                    schedule.track_id,
                    schedule.clip_id,
                    schedule.target_id,
                    schedule.channel,
                    {
                        "loop_index": loop_index,
                        "pattern_id": schedule.program.resource_id,
                        "resource": schedule.resource_uri,
                    },
                )
            )

    def _apply_automations(
        self,
        context: Any,
        frame: int,
        events: list[StageTraceEvent],
    ) -> None:
        winners: dict[tuple[str, str], tuple[StageAutomation, Any, int]] = {}
        for item in self.program.automations:
            if not item.start_frame <= frame < item.end_frame:
                continue
            local = (frame - item.start_frame) % item.duration_frames
            value = self._automation_value(item, local)
            key = (item.target_id, item.channel)
            previous = winners.get(key)
            conflicts = 1 if previous is None else previous[2] + 1
            if previous is None or previous[0].order_key <= item.order_key:
                winners[key] = (item, value, conflicts)
            else:
                winners[key] = (previous[0], previous[1], conflicts)

        for item, value, conflict_count in sorted(
            winners.values(), key=lambda entry: entry[0].order_key
        ):
            state = self.node_state.setdefault(item.target_id, {})
            if item.kind == "Movement":
                if not isinstance(value, dict) or not _number(value.get("x")) or not _number(value.get("y")):
                    raise ValueError("Movement automation must evaluate to numeric x/y")
                state["x"] = float(value["x"])
                state["y"] = float(value["y"])
                hook = getattr(context, "set_node_position", None)
                if callable(hook):
                    hook(item.target_id, state["x"], state["y"])
            else:
                state[item.property_name] = value
                hook = getattr(context, "set_node_property", None)
                if callable(hook):
                    hook(item.target_id, item.property_name, value)
            events.append(
                self._trace_event(
                    frame,
                    item.kind.lower(),
                    item.track_id,
                    item.clip_id,
                    item.target_id,
                    item.channel,
                    {"value": value, "conflict_count": conflict_count},
                )
            )

    def _automation_value(self, item: StageAutomation, local_frame: int) -> Any:
        frames = item.keyframes
        values = self._automation_values[item.clip_id]
        if len(frames) == 1 or local_frame <= frames[0].frame:
            return values[0]
        if local_frame >= frames[-1].frame:
            return values[-1]
        for index, right in enumerate(frames[1:], start=1):
            if local_frame > right.frame:
                continue
            left = frames[index - 1]
            span = max(1, right.frame - left.frame)
            amount = (local_frame - left.frame) / span
            amount = _ease(left.interpolation, amount)
            return _interpolate(values[index - 1], values[index], amount)
        return values[-1]

    def _dispatch_actions(
        self,
        context: Any,
        frame: int,
        events: list[StageTraceEvent],
        *,
        dispatch: bool,
    ) -> None:
        for item in self.program.actions:
            if item.frame != frame:
                continue
            payload = item.payload
            if dispatch:
                if item.kind == "Audio":
                    self._dispatch_audio(context, item.channel, payload)
                elif item.kind == "Event":
                    hook = getattr(context, "emit_event", None)
                    if callable(hook):
                        hook(str(payload.get("event_type") or ""), payload.get("data", {}))
                elif item.kind == "ScriptEvent":
                    # This is a typed host hook only. StageProgram never imports,
                    # evaluates, or executes arbitrary source text.
                    hook = getattr(context, "handle_script_event", None)
                    if callable(hook):
                        name = str(payload.get("hook") or payload.get("script") or "")
                        hook(name, payload.get("data", payload.get("payload", {})))
            events.append(
                self._trace_event(
                    frame,
                    item.kind.lower(),
                    item.track_id,
                    item.clip_id,
                    item.target_id,
                    item.channel,
                    payload,
                )
            )

    @staticmethod
    def _dispatch_audio(context: Any, channel: str, payload: dict[str, Any]) -> None:
        action = str(payload.get("action", "play"))
        bus = str(payload.get("bus") or channel or "se").lower()
        if action == "play":
            name = str(payload.get("resource") or payload.get("name") or "")
            if bus == "bgm":
                context.play_bgm(
                    name,
                    int(payload.get("loops", -1)),
                    int(payload.get("fade_ms", 0)),
                )
            elif bus == "danmaku_se" and hasattr(context, "play_danmaku_se"):
                context.play_danmaku_se(name, payload.get("volume"))
            else:
                context.play_se(name, payload.get("volume"))
        elif action == "stop":
            context.stop_bgm(int(payload.get("fade_ms", 0)))
        elif action == "pause":
            context.pause_bgm()
        elif action == "resume":
            context.unpause_bgm()

    @staticmethod
    def _trace_event(
        frame: int,
        kind: str,
        track_id: str,
        clip_id: str,
        target_id: str | None,
        channel: str,
        value: Any,
    ) -> StageTraceEvent:
        return StageTraceEvent(
            frame=frame,
            kind=kind,
            track_id=track_id,
            clip_id=clip_id,
            target_id=target_id,
            channel=channel,
            value_json=json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        )

    @staticmethod
    def _spawn_hash(event: Any) -> str:
        payload = json.dumps(
            {
                "positions": event.positions,
                "angles": event.angles,
                "speeds": event.speeds,
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "PatternSchedule",
    "StageAction",
    "StageAutomation",
    "StageKeyframe",
    "StageNode",
    "StageProgram",
    "StageRunner",
    "StageRunnerState",
    "StageRuntimeError",
    "StageTickResult",
    "StageTraceEvent",
]

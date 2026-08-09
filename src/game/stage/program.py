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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.pattern import PatternProgram, PatternRunner


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
    state_id: str
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
    state_id: str
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
    state_id: str
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
class StageTransition:
    transition_id: str
    source_state_id: str
    target_state_id: str
    trigger: str
    after_frames: int | None
    priority: int
    order: int

    @property
    def order_key(self) -> tuple[int, int, str]:
        return (-self.priority, self.order, self.transition_id)


@dataclass(frozen=True)
class StageState:
    state_id: str
    name: str
    duration_frames: int
    entry_actions: tuple[StageAction, ...]
    exit_actions: tuple[StageAction, ...]
    transitions: tuple[StageTransition, ...]
    child_graph: "StageStateGraph | None" = None


@dataclass(frozen=True)
class StageStateGraph:
    graph_id: str
    name: str
    initial_state_id: str
    states: tuple[StageState, ...]

    def state(self, state_id: str) -> StageState:
        try:
            return next(item for item in self.states if item.state_id == state_id)
        except StopIteration as exc:
            raise KeyError(state_id) from exc


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
    state_graph: StageStateGraph


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
        state_id: str | None = None,
        transition_id: str | None = None,
    ) -> None:
        self.resource_id = resource_id
        self.frame = frame
        self.clip_id = clip_id
        self.state_id = state_id
        self.transition_id = transition_id
        if transition_id is not None:
            self.path = f"states.{state_id}.transitions.{transition_id}"
        elif clip_id is not None:
            self.path = f"states.{state_id}.clips.{clip_id}"
        else:
            self.path = "runtime"
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
    state_id: str | None = None
    local_frame: int | None = None
    transition_id: str | None = None

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
    state_id: str
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
    """Execute one immutable, hierarchical StageProgram at a fixed tick rate."""

    def __init__(self, program: StageProgram) -> None:
        self.program = program
        self.state = StageRunnerState.STOPPED
        self.frame = 0
        self.last_error: StageRuntimeError | None = None
        self.node_state: dict[str, dict[str, Any]] = {}
        self.trace: list[StageTraceEvent] = []
        self.last_events: tuple[StageTraceEvent, ...] = ()
        self._active_patterns: dict[tuple[str, str, int], _ActivePattern] = {}
        self._context: Any | None = None
        self._audio_started = False
        self._audio_paused = False
        self._active_audio_clip_id: str | None = None
        self._active_audio_state_id: str | None = None
        self._graphs_by_id: dict[str, StageStateGraph] = {}
        self._states_by_id: dict[str, StageState] = {}
        self._state_graph_by_state: dict[str, StageStateGraph] = {}
        self._index_graph(program.state_graph)
        self._patterns_by_state = self._group_by_state(program.patterns)
        self._automations_by_state = self._group_by_state(program.automations)
        self._actions_by_state = self._group_by_state(program.actions)
        self._automation_values = {
            item.clip_id: tuple(keyframe.value for keyframe in item.keyframes)
            for item in program.automations
        }
        self._active_graphs: list[StageStateGraph] = []
        self._active_states: list[StageState] = []
        self._local_frames: dict[str, int] = {}
        self._completed_children: set[str] = set()
        self._restore_node_state()

    @staticmethod
    def _group_by_state(items):
        grouped: dict[str, list[Any]] = {}
        for item in items:
            grouped.setdefault(item.state_id, []).append(item)
        return {key: tuple(value) for key, value in grouped.items()}

    def _index_graph(self, graph: StageStateGraph) -> None:
        self._graphs_by_id[graph.graph_id] = graph
        for state in graph.states:
            self._states_by_id[state.state_id] = state
            self._state_graph_by_state[state.state_id] = graph
            if state.child_graph is not None:
                self._index_graph(state.child_graph)

    @property
    def current_state_path(self) -> tuple[str, ...]:
        return tuple(item.state_id for item in self._active_states)

    @property
    def current_state_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self._active_states)

    @property
    def active_clip_ids(self) -> tuple[str, ...]:
        active = {item.schedule.clip_id for item in self._active_patterns.values()}
        if self._active_audio_clip_id is not None:
            active.add(self._active_audio_clip_id)
        for state in self._active_states:
            local = self._local_frames.get(state.state_id, 0)
            active.update(
                item.clip_id
                for item in self._automations_by_state.get(state.state_id, ())
                if item.start_frame <= local < item.end_frame
            )
        return tuple(sorted(active))

    def _restore_node_state(self) -> None:
        self.node_state = {item.node_id: item.properties for item in self.program.nodes}

    def start(
        self,
        context: Any | None = None,
        *,
        reset: bool = True,
        clear_owned: bool = True,
        dispatch_actions: bool = True,
    ) -> None:
        if context is not None:
            self._context = context
        if reset:
            self.reset(context, clear_owned=clear_owned)
        self.state = StageRunnerState.RUNNING
        if not self._active_states:
            events: list[StageTraceEvent] = []
            self._enter_state(
                self.program.state_graph,
                self.program.state_graph.initial_state_id,
                events,
                dispatch=dispatch_actions,
            )
            self.trace.extend(events)
            self.last_events = tuple(events)

    def pause(self) -> None:
        if self.state == StageRunnerState.RUNNING:
            self.state = StageRunnerState.PAUSED
            for item in self._active_patterns.values():
                item.runner.pause()
            if self._audio_started and not self._audio_paused:
                hook = getattr(self._context, "pause_bgm", None)
                if callable(hook):
                    hook()
                    self._audio_paused = True

    def resume(self) -> None:
        if self.state == StageRunnerState.PAUSED:
            self.state = StageRunnerState.RUNNING
            for item in self._active_patterns.values():
                item.runner.resume()
            if self._audio_started and self._audio_paused:
                hook = getattr(self._context, "unpause_bgm", None)
                if callable(hook):
                    hook()
                    self._audio_paused = False

    def reset(self, context: Any | None = None, *, clear_owned: bool = True) -> None:
        if context is not None:
            self._context = context
        self._stop_all_patterns(context, clear_owned=clear_owned)
        self._stop_audio()
        clear_state = getattr(self._context, "clear_authored_stage_state", None)
        if callable(clear_state):
            clear_state()
        self._active_graphs.clear()
        self._active_states.clear()
        self._local_frames.clear()
        self._completed_children.clear()
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
        self._context = context
        current = self.frame
        if self.state != StageRunnerState.RUNNING:
            return StageTickResult(current, self.state)
        if current >= self.program.duration_frames:
            events: list[StageTraceEvent] = []
            self._finish(context, events=events, dispatch=dispatch_actions)
            self.trace.extend(events)
            self.last_events = tuple(events)
            return StageTickResult(current, self.state, tuple(events))

        events: list[StageTraceEvent] = []
        spawned_count = 0
        active_clip: str | None = None
        active_state_id: str | None = None
        try:
            active_ids = self.current_state_path
            for state_id in active_ids:
                local = self._local_frames[state_id]
                self._expire_patterns(context, state_id, local, current, events)
                self._apply_automations(context, state_id, local, current, events)
                self._start_patterns(context, state_id, local, current, events)
                self._dispatch_actions(
                    context,
                    self._actions_by_state.get(state_id, ()),
                    local,
                    current,
                    events,
                    dispatch=dispatch_actions,
                )
            depth_order = {state_id: index for index, state_id in enumerate(active_ids)}
            for key in sorted(
                self._active_patterns,
                key=lambda value: (
                    depth_order.get(value[0], 10_000),
                    self._active_patterns[value].schedule.order_key,
                ),
            ):
                item = self._active_patterns[key]
                active_clip = item.schedule.clip_id
                active_state_id = item.state_id
                target_state = self.node_state.get(item.schedule.target_id or "", {})
                if target_state.get("enabled", True) is False:
                    continue
                result = item.runner.tick(_PatternContext(context, self, item.schedule))
                if result.event is not None:
                    spawned_count += result.spawned_count
                    pattern_event = result.event
                    events.append(
                        self._trace_event(
                            current,
                            "pattern_spawn",
                            item.schedule.track_id,
                            item.schedule.clip_id,
                            item.schedule.target_id,
                            item.schedule.channel,
                            {
                                "loop_index": item.loop_index,
                                "pattern_loop_index": pattern_event.loop_index,
                                "burst_index": pattern_event.burst_index,
                                "requested_count": pattern_event.requested_count,
                                "spawned_count": pattern_event.spawned_count,
                                "spawn_hash": self._spawn_hash(pattern_event),
                            },
                            state_id=item.state_id,
                            local_frame=self._local_frames.get(item.state_id, 0),
                        )
                    )
            for state_id in active_ids:
                if state_id in self._local_frames:
                    self._local_frames[state_id] += 1
            self.frame += 1
            self._resolve_state_graph(context, events, dispatch=dispatch_actions)
            if (
                self.state == StageRunnerState.RUNNING
                and self.frame >= self.program.duration_frames
            ):
                self._finish(context, events=events, dispatch=dispatch_actions)
        except Exception as exc:
            error = StageRuntimeError(
                self.program.resource_id,
                current,
                str(exc),
                clip_id=active_clip,
                state_id=active_state_id,
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

    def _enter_state(
        self,
        graph: StageStateGraph,
        state_id: str,
        events: list[StageTraceEvent],
        *,
        dispatch: bool,
    ) -> None:
        state = graph.state(state_id)
        self._active_graphs.append(graph)
        self._active_states.append(state)
        self._local_frames[state.state_id] = 0
        self._completed_children.discard(state.state_id)
        self._dispatch_actions(
            self._context,
            state.entry_actions,
            0,
            self.frame,
            events,
            dispatch=dispatch,
            match_frame=False,
        )
        if state.child_graph is not None:
            self._enter_state(
                state.child_graph,
                state.child_graph.initial_state_id,
                events,
                dispatch=dispatch,
            )

    def _exit_from_depth(
        self,
        context: Any,
        depth: int,
        events: list[StageTraceEvent],
        *,
        dispatch: bool,
    ) -> None:
        for index in range(len(self._active_states) - 1, depth - 1, -1):
            state = self._active_states[index]
            local = self._local_frames.get(state.state_id, 0)
            self._expire_patterns(
                context,
                state.state_id,
                local,
                self.frame,
                events,
                force=True,
            )
            self._dispatch_actions(
                context,
                state.exit_actions,
                local,
                self.frame,
                events,
                dispatch=dispatch,
                match_frame=False,
            )
            if self._active_audio_state_id == state.state_id:
                self._stop_audio()
            self._completed_children.discard(state.state_id)
            self._local_frames.pop(state.state_id, None)
            self._active_states.pop(index)
            self._active_graphs.pop(index)

    def _state_complete(self, state: StageState) -> bool:
        local_done = self._local_frames.get(state.state_id, 0) >= state.duration_frames
        child_done = (
            state.child_graph is None or state.state_id in self._completed_children
        )
        return local_done and child_done

    def _resolve_state_graph(
        self,
        context: Any,
        events: list[StageTraceEvent],
        *,
        dispatch: bool,
    ) -> None:
        depth = len(self._active_states) - 1
        while depth >= 0 and self._active_states:
            if depth >= len(self._active_states):
                depth = len(self._active_states) - 1
            state = self._active_states[depth]
            graph = self._active_graphs[depth]
            local = self._local_frames.get(state.state_id, 0)
            completed = self._state_complete(state)
            eligible = [
                transition
                for transition in state.transitions
                if (
                    transition.trigger == "after"
                    and local >= int(transition.after_frames or 0)
                )
                or (transition.trigger == "complete" and completed)
            ]
            if eligible:
                transition = min(eligible, key=lambda item: item.order_key)
                source_id = state.state_id
                self._exit_from_depth(
                    context,
                    depth,
                    events,
                    dispatch=dispatch,
                )
                events.append(
                    self._trace_event(
                        self.frame,
                        "state_transition",
                        graph.graph_id,
                        transition.transition_id,
                        transition.target_state_id,
                        "state",
                        {
                            "source_state_id": source_id,
                            "target_state_id": transition.target_state_id,
                            "trigger": transition.trigger,
                            "local_frame": local,
                        },
                        state_id=source_id,
                        local_frame=local,
                        transition_id=transition.transition_id,
                    )
                )
                self._enter_state(
                    graph,
                    transition.target_state_id,
                    events,
                    dispatch=dispatch,
                )
                depth -= 1
                continue
            if not state.transitions and completed:
                self._exit_from_depth(
                    context,
                    depth,
                    events,
                    dispatch=dispatch,
                )
                if depth == 0:
                    self._stop_audio()
                    self.state = StageRunnerState.FINISHED
                    return
                parent = self._active_states[depth - 1]
                self._completed_children.add(parent.state_id)
            depth -= 1

    def _finish(
        self,
        context: Any,
        *,
        events: list[StageTraceEvent],
        dispatch: bool,
    ) -> None:
        if self._active_states:
            self._exit_from_depth(context, 0, events, dispatch=dispatch)
        self._stop_audio()
        self.state = StageRunnerState.FINISHED

    def _expire_patterns(
        self,
        context: Any,
        state_id: str,
        local_frame: int,
        global_frame: int,
        events: list[StageTraceEvent],
        *,
        force: bool = False,
    ) -> None:
        expired = [
            key
            for key, item in self._active_patterns.items()
            if item.state_id == state_id and (force or item.end_frame <= local_frame)
        ]
        for key in sorted(expired):
            item = self._active_patterns.pop(key)
            item.runner.stop(context, clear_owned=True)
            events.append(
                self._trace_event(
                    global_frame,
                    "pattern_stop",
                    item.schedule.track_id,
                    item.schedule.clip_id,
                    item.schedule.target_id,
                    item.schedule.channel,
                    {"loop_index": item.loop_index},
                    state_id=state_id,
                    local_frame=local_frame,
                )
            )

    def _start_patterns(
        self,
        context: Any,
        state_id: str,
        local_frame: int,
        global_frame: int,
        events: list[StageTraceEvent],
    ) -> None:
        for schedule in self._patterns_by_state.get(state_id, ()):
            relative = local_frame - schedule.start_frame
            if relative < 0 or relative % schedule.duration_frames:
                continue
            loop_index = relative // schedule.duration_frames
            if loop_index >= schedule.loop_count:
                continue
            key = (state_id, schedule.clip_id, loop_index)
            if key in self._active_patterns:
                continue
            from src.pattern import PatternRunner

            runner = PatternRunner(schedule.program)
            runner.start(_PatternContext(context, self, schedule), reset=False)
            self._active_patterns[key] = _ActivePattern(
                state_id=state_id,
                schedule=schedule,
                loop_index=loop_index,
                end_frame=local_frame + schedule.duration_frames,
                runner=runner,
            )
            events.append(
                self._trace_event(
                    global_frame,
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
                    state_id=state_id,
                    local_frame=local_frame,
                )
            )

    def _apply_automations(
        self,
        context: Any,
        state_id: str,
        local_frame: int,
        global_frame: int,
        events: list[StageTraceEvent],
    ) -> None:
        winners: dict[tuple[str, str], tuple[StageAutomation, Any, int]] = {}
        for item in self._automations_by_state.get(state_id, ()):
            if not item.start_frame <= local_frame < item.end_frame:
                continue
            local = (local_frame - item.start_frame) % item.duration_frames
            if (
                local == item.duration_frames - 1
                and item.keyframes
                and item.keyframes[-1].frame == item.duration_frames
            ):
                local = item.duration_frames
            value = self._automation_value(item, local)
            key = (item.target_id, item.property_name)
            previous = winners.get(key)
            conflicts = 1 if previous is None else previous[2] + 1
            if previous is None or previous[0].order_key <= item.order_key:
                winners[key] = (item, value, conflicts)
            else:
                winners[key] = (previous[0], previous[1], conflicts)

        for item, value, conflict_count in sorted(
            winners.values(), key=lambda entry: entry[0].order_key
        ):
            node = self.node_state.setdefault(item.target_id, {})
            if item.kind == "Movement":
                if (
                    not isinstance(value, dict)
                    or not _number(value.get("x"))
                    or not _number(value.get("y"))
                ):
                    raise ValueError("Movement automation must evaluate to numeric x/y")
                node["x"] = float(value["x"])
                node["y"] = float(value["y"])
                hook = getattr(context, "set_node_position", None)
                if callable(hook):
                    hook(item.target_id, node["x"], node["y"])
            else:
                node[item.property_name] = value
                hook = getattr(context, "set_node_property", None)
                if callable(hook):
                    hook(item.target_id, item.property_name, value)
            events.append(
                self._trace_event(
                    global_frame,
                    item.kind.lower(),
                    item.track_id,
                    item.clip_id,
                    item.target_id,
                    item.channel,
                    {"value": value, "conflict_count": conflict_count},
                    state_id=state_id,
                    local_frame=local_frame,
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
            amount = _ease(left.interpolation, (local_frame - left.frame) / span)
            return _interpolate(values[index - 1], values[index], amount)
        return values[-1]

    def _dispatch_actions(
        self,
        context: Any,
        actions: tuple[StageAction, ...],
        local_frame: int,
        global_frame: int,
        events: list[StageTraceEvent],
        *,
        dispatch: bool,
        match_frame: bool = True,
    ) -> None:
        for item in actions:
            if match_frame and item.frame != local_frame:
                continue
            payload = item.payload
            if dispatch:
                if item.kind == "Audio":
                    self._dispatch_audio(
                        context,
                        item.channel,
                        payload,
                        clip_id=item.clip_id,
                        state_id=item.state_id,
                    )
                elif item.kind == "Event":
                    hook = getattr(context, "emit_event", None)
                    if callable(hook):
                        hook(
                            str(payload.get("event_type") or ""),
                            payload.get("data", {}),
                        )
                elif item.kind == "ScriptEvent":
                    hook = getattr(context, "handle_script_event", None)
                    if callable(hook):
                        name = str(payload.get("hook") or payload.get("script") or "")
                        hook(name, payload.get("data", payload.get("payload", {})))
            events.append(
                self._trace_event(
                    global_frame,
                    item.kind.lower(),
                    item.track_id,
                    item.clip_id,
                    item.target_id,
                    item.channel,
                    payload,
                    state_id=item.state_id,
                    local_frame=local_frame,
                )
            )

    def _dispatch_audio(
        self,
        context: Any,
        channel: str,
        payload: dict[str, Any],
        *,
        clip_id: str | None = None,
        state_id: str | None = None,
    ) -> None:
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
                self._audio_started = True
                self._audio_paused = False
                self._active_audio_clip_id = clip_id
                self._active_audio_state_id = state_id
            elif bus == "danmaku_se" and hasattr(context, "play_danmaku_se"):
                context.play_danmaku_se(name, payload.get("volume"))
            else:
                context.play_se(name, payload.get("volume"))
        elif action == "stop":
            if payload.get("automatic") is True and self._active_audio_clip_id != clip_id:
                return
            context.stop_bgm(int(payload.get("fade_ms", 0)))
            self._audio_started = False
            self._audio_paused = False
            self._active_audio_clip_id = None
            self._active_audio_state_id = None
        elif action == "pause":
            context.pause_bgm()
            if self._audio_started:
                self._audio_paused = True
        elif action == "resume":
            context.unpause_bgm()
            if self._audio_started:
                self._audio_paused = False

    def _stop_audio(self) -> None:
        if self._audio_started:
            hook = getattr(self._context, "stop_bgm", None)
            if callable(hook):
                hook(0)
        self._audio_started = False
        self._audio_paused = False
        self._active_audio_clip_id = None
        self._active_audio_state_id = None

    def restore_audio_state(self, context: Any | None = None) -> None:
        """Reconstruct persistent BGM state from the deterministic Stage trace."""

        if context is not None:
            self._context = context
        self._stop_audio()
        if self.state == StageRunnerState.FINISHED:
            return
        state: tuple[str, dict[str, Any], str, str, str | None] | None = None
        for item in self.trace:
            if item.kind != "audio":
                continue
            payload = dict(item.value)
            bus = str(payload.get("bus") or item.channel or "se").lower()
            if bus != "bgm":
                continue
            action = str(payload.get("action", "play"))
            if action == "play":
                state = ("play", payload, item.channel, item.clip_id, item.state_id)
            elif action == "stop":
                if (
                    payload.get("automatic") is True
                    and state is not None
                    and state[3] != item.clip_id
                ):
                    continue
                state = None
            elif action == "pause" and state is not None:
                state = ("pause", state[1], state[2], state[3], state[4])
            elif action == "resume" and state is not None:
                state = ("play", state[1], state[2], state[3], state[4])
        if state is None or self._context is None:
            return
        mode, payload, channel, clip_id, state_id = state
        self._dispatch_audio(
            self._context,
            channel,
            payload,
            clip_id=clip_id,
            state_id=state_id,
        )
        if mode == "pause":
            hook = getattr(self._context, "pause_bgm", None)
            if callable(hook):
                hook()
                self._audio_paused = True

    @staticmethod
    def _trace_event(
        frame: int,
        kind: str,
        track_id: str,
        clip_id: str,
        target_id: str | None,
        channel: str,
        value: Any,
        *,
        state_id: str | None = None,
        local_frame: int | None = None,
        transition_id: str | None = None,
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
            state_id=state_id,
            local_frame=local_frame,
            transition_id=transition_id,
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
    "StageState",
    "StageStateGraph",
    "StageTickResult",
    "StageTraceEvent",
    "StageTransition",
]

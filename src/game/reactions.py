"""Lifecycle reactions, reactive timeline clips, and structured task scopes.

This module is intentionally runtime-only.  Authoring documents may describe
the same records, but actions are resolved by the formal runtime and never by
Qt widgets or by a producer calling a timeline clip directly.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import Enum
from itertools import count
from typing import Any, Callable, Iterable, Iterator, Mapping

from .events import Event, EventBus, LifecycleEvent


class TaskScopeState(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class TaskTrace:
    frame: int
    scope_id: str
    kind: str
    task_id: str | None = None
    reason: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class TaskWait:
    """Yield from a task to wait a fixed number of frames."""

    frames: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.frames, bool) or not isinstance(self.frames, int) or self.frames < 0:
            raise ValueError("TaskWait.frames must be a non-negative integer")


@dataclass
class _Task:
    task_id: str
    iterator: Iterator[Any]
    ready_frame: int
    state: TaskScopeState = TaskScopeState.RUNNING
    error: Exception | None = None


class CancellationToken:
    def __init__(self) -> None:
        self.cancelled = False
        self.reason: str | None = None

    def cancel(self, reason: str = "cancelled") -> None:
        self.cancelled = True
        self.reason = str(reason)


class TaskScope:
    """A structured owner for sparse cross-frame work.

    A scope may own a handful of generators, subscriptions, or child scopes;
    it must never be instantiated per high-density bullet.  Cancellation is
    idempotent and propagates to all children and tasks.
    """

    _task_ids = count(1)

    def __init__(
        self,
        scope_id: str,
        *,
        owner_id: str | None = None,
        parent: "TaskScope | None" = None,
    ) -> None:
        if not isinstance(scope_id, str) or not scope_id.strip():
            raise ValueError("scope_id must be a non-empty string")
        self.scope_id = scope_id.strip()
        self.owner_id = owner_id.strip() if isinstance(owner_id, str) and owner_id.strip() else None
        self.parent = parent
        self.state = TaskScopeState.RUNNING
        self.cancel_token = CancellationToken()
        self.children: dict[str, TaskScope] = {}
        self._tasks: dict[str, _Task] = {}
        self._trace: list[TaskTrace] = []
        if parent is not None:
            parent.add_child(self)

    @property
    def active(self) -> bool:
        return self.state == TaskScopeState.RUNNING

    @property
    def pending_tasks(self) -> int:
        return sum(task.state == TaskScopeState.RUNNING for task in self._tasks.values())

    @property
    def trace(self) -> tuple[TaskTrace, ...]:
        return tuple(self._trace)

    def add_child(self, child: "TaskScope") -> None:
        if not self.active:
            child.cancel("parent_not_running")
            return
        if child.scope_id in self.children and self.children[child.scope_id] is not child:
            raise ValueError(f"duplicate child scope: {child.scope_id}")
        self.children[child.scope_id] = child

    def start(
        self,
        task: Callable[..., Any] | Iterator[Any] | None,
        *,
        task_id: str | None = None,
        frame: int = 0,
        context: Any = None,
        event: Event | None = None,
    ) -> str | None:
        if not self.active:
            return None
        if task is None:
            return None
        identifier = task_id or f"task-{next(self._task_ids)}"
        if identifier in self._tasks and self._tasks[identifier].state == TaskScopeState.RUNNING:
            raise ValueError(f"task already exists: {identifier}")
        iterator: Any = task
        if callable(task):
            iterator = _invoke_callable(task, context, event, self)
        if iterator is None:
            self._trace.append(TaskTrace(frame, self.scope_id, "task_complete", identifier))
            self.complete(frame)
            return identifier
        if not hasattr(iterator, "__next__"):
            raise TypeError("task action must return an iterator or None")
        self._tasks[identifier] = _Task(identifier, iterator, int(frame))
        self._trace.append(TaskTrace(frame, self.scope_id, "task_start", identifier))
        return identifier

    def wait(self, frames: int = 1) -> TaskWait:
        return TaskWait(frames)

    def tick(self, frame: int) -> None:
        if not self.active:
            return
        for child in tuple(self.children.values()):
            child.tick(frame)
        for task in tuple(self._tasks.values()):
            if task.state != TaskScopeState.RUNNING or frame < task.ready_frame:
                continue
            try:
                yielded = next(task.iterator)
            except StopIteration:
                task.state = TaskScopeState.COMPLETED
                self._trace.append(TaskTrace(frame, self.scope_id, "task_complete", task.task_id))
                continue
            except Exception as exc:  # noqa: BLE001 - task failure is traced
                task.state = TaskScopeState.FAILED
                task.error = exc
                self._trace.append(
                    TaskTrace(frame, self.scope_id, "task_failed", task.task_id, detail=str(exc))
                )
                continue
            if isinstance(yielded, TaskWait):
                task.ready_frame = frame + max(1, yielded.frames)
            elif isinstance(yielded, bool) or not isinstance(yielded, int):
                task.ready_frame = frame + 1
            else:
                task.ready_frame = frame + max(1, yielded)
        if self._tasks and all(task.state != TaskScopeState.RUNNING for task in self._tasks.values()):
            self.state = TaskScopeState.COMPLETED
            self._trace.append(TaskTrace(frame, self.scope_id, "scope_complete"))

    def complete(self, frame: int = 0) -> None:
        if self.state == TaskScopeState.RUNNING:
            self.state = TaskScopeState.COMPLETED
            self._trace.append(TaskTrace(frame, self.scope_id, "scope_complete"))

    def cancel(self, reason: str = "cancelled", frame: int = 0) -> None:
        if self.state in {TaskScopeState.CANCELLED, TaskScopeState.COMPLETED}:
            return
        self.cancel_token.cancel(reason)
        self.state = TaskScopeState.CANCELLED
        for child in tuple(self.children.values()):
            child.cancel(reason, frame=frame)
        for task in self._tasks.values():
            if task.state == TaskScopeState.RUNNING:
                task.state = TaskScopeState.CANCELLED
                close = getattr(task.iterator, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception as exc:  # noqa: BLE001 - cancellation is best effort
                        task.error = exc
                        self._trace.append(
                            TaskTrace(
                                frame,
                                self.scope_id,
                                "task_cancel_error",
                                task.task_id,
                                reason=reason,
                                detail=str(exc),
                            )
                        )
        self._trace.append(TaskTrace(frame, self.scope_id, "scope_cancel", reason=reason))


def _invoke_callable(callback: Callable[..., Any], context: Any, event: Event | None, scope: TaskScope) -> Any:
    """Call an extension using its declared arity without masking body errors."""

    try:
        signature = inspect.signature(callback)
        parameters = list(signature.parameters.values())
    except (TypeError, ValueError):
        return callback(context, event, scope)
    positional = [
        item
        for item in parameters
        if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if any(item.kind == inspect.Parameter.VAR_POSITIONAL for item in parameters):
        return callback(context, event, scope)
    count_args = len(positional)
    if count_args >= 3:
        return callback(context, event, scope)
    if count_args == 2:
        names = [item.name.casefold() for item in positional]
        if "scope" in names[0] or "task" in names[0]:
            return callback(scope, event)
        if "context" in names[0] or names[0] in {"ctx", "runtime"}:
            return callback(context, event)
        return callback(event, scope)
    if count_args == 1:
        name = positional[0].name.casefold()
        return callback(scope if "scope" in name or "task" in name else event)
    return callback()


@dataclass(frozen=True, init=False)
class ReactionSpec:
    """Serializable reaction descriptor with an injected runtime action."""

    reaction_id: str
    event_type: str
    action: Callable[..., Any] | None
    source: str | None
    owner: str | None
    payload_filter: Mapping[str, Any] | Callable[[Any], bool] | None
    guard: Callable[..., bool] | None
    policy: str
    reentry: str
    scope: str
    once_per_scope: bool
    cooldown_frames: int
    max_instances: int
    max_causal_depth: int
    action_id: str | None

    def __init__(
        self,
        reaction_id: str,
        event_type: str | None = None,
        action: Callable[..., Any] | None = None,
        *,
        trigger: str | None = None,
        source: str | None = None,
        owner: str | None = None,
        payload_filter: Mapping[str, Any] | Callable[[Any], bool] | None = None,
        guard: Callable[..., bool] | None = None,
        policy: str = "each",
        reentry: str = "ignore_while_running",
        scope: str = "stage",
        once_per_scope: bool = True,
        cooldown_frames: int = 0,
        max_instances: int = 1,
        max_causal_depth: int = 32,
        action_id: str | None = None,
    ) -> None:
        resolved = event_type or trigger
        if not isinstance(reaction_id, str) or not reaction_id.strip():
            raise ValueError("reaction_id must be a non-empty string")
        if not isinstance(resolved, str) or not resolved.strip():
            raise ValueError("reaction event_type/trigger must be a non-empty string")
        if policy not in {"each", "first_per_frame", "count_per_frame", "debounce"}:
            raise ValueError("unsupported reaction policy")
        if reentry not in {"ignore_while_running", "restart", "parallel"}:
            raise ValueError("unsupported reaction reentry policy")
        if isinstance(cooldown_frames, bool) or not isinstance(cooldown_frames, int) or cooldown_frames < 0:
            raise ValueError("cooldown_frames must be a non-negative integer")
        if isinstance(max_instances, bool) or not isinstance(max_instances, int) or max_instances < 1:
            raise ValueError("max_instances must be a positive integer")
        if isinstance(max_causal_depth, bool) or not isinstance(max_causal_depth, int) or max_causal_depth < 1:
            raise ValueError("max_causal_depth must be a positive integer")
        if reentry == "parallel" and max_instances < 2:
            raise ValueError("parallel reactions need max_instances >= 2")
        object.__setattr__(self, "reaction_id", reaction_id.strip())
        object.__setattr__(self, "event_type", resolved.strip())
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "source", source.strip() if isinstance(source, str) and source.strip() else None)
        object.__setattr__(self, "owner", owner.strip() if isinstance(owner, str) and owner.strip() else None)
        object.__setattr__(self, "payload_filter", payload_filter)
        object.__setattr__(self, "guard", guard)
        object.__setattr__(self, "policy", policy)
        object.__setattr__(self, "reentry", reentry)
        object.__setattr__(self, "scope", scope.strip() if isinstance(scope, str) and scope.strip() else "stage")
        object.__setattr__(self, "once_per_scope", bool(once_per_scope))
        object.__setattr__(self, "cooldown_frames", cooldown_frames)
        object.__setattr__(self, "max_instances", max_instances)
        object.__setattr__(self, "max_causal_depth", max_causal_depth)
        object.__setattr__(self, "action_id", action_id.strip() if isinstance(action_id, str) and action_id.strip() else None)

    @property
    def trigger(self) -> str:
        return self.event_type

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.reaction_id,
            "event_type": self.event_type,
            "source": self.source,
            "owner": self.owner,
            "payload_filter": dict(self.payload_filter) if isinstance(self.payload_filter, Mapping) else None,
            "policy": self.policy,
            "reentry": self.reentry,
            "scope": self.scope,
            "once_per_scope": self.once_per_scope,
            "cooldown_frames": self.cooldown_frames,
            "max_instances": self.max_instances,
            "max_causal_depth": self.max_causal_depth,
            "action": self.action_id,
        }


@dataclass(frozen=True)
class ReactiveClip:
    """A timeline slot that arms a reaction for a state/time window."""

    clip_id: str
    reaction: ReactionSpec
    state_id: str | None = None
    start_frame: int = 0
    end_frame: int | None = None
    owner_id: str | None = None

    def __post_init__(self) -> None:
        if not self.clip_id.strip():
            raise ValueError("clip_id must be a non-empty string")
        if isinstance(self.start_frame, bool) or not isinstance(self.start_frame, int) or self.start_frame < 0:
            raise ValueError("clip start_frame must be non-negative")
        if self.end_frame is not None and (
            isinstance(self.end_frame, bool)
            or not isinstance(self.end_frame, int)
            or self.end_frame <= self.start_frame
        ):
            raise ValueError("clip end_frame must be greater than start_frame")

    def armed(self, frame: int) -> bool:
        return frame >= self.start_frame and (self.end_frame is None or frame < self.end_frame)


@dataclass(frozen=True)
class ReactionTrace:
    frame: int
    reaction_id: str
    kind: str
    event_type: str | None = None
    event_id: str | None = None
    instance_id: str | None = None
    scope_id: str | None = None
    reason: str | None = None
    count: int = 1
    causal_depth: int = 0


@dataclass
class _ReactionInstance:
    instance_id: str
    spec: ReactionSpec
    scope: TaskScope
    started_frame: int
    event: Event


class ReactionScheduler:
    """Deterministic matcher and owner-aware reaction instance scheduler."""

    def __init__(
        self,
        *,
        max_causal_depth: int = 32,
        max_instances_per_frame: int = 4096,
        event_bus: EventBus | None = None,
    ) -> None:
        self.max_causal_depth = max(1, int(max_causal_depth))
        self.max_instances_per_frame = max(1, int(max_instances_per_frame))
        self.specs: dict[str, ReactionSpec] = {}
        self.scopes: dict[str, TaskScope] = {}
        self.instances: dict[str, _ReactionInstance] = {}
        self.trace: list[ReactionTrace] = []
        self.diagnostics: list[dict[str, Any]] = []
        self._serial = count(1)
        self._started: set[tuple[str, str]] = set()
        self._last_start: dict[tuple[str, str], int] = {}
        self._pending_events: list[Event] = []
        self._event_subscription = None
        if event_bus is not None:
            self.bind_event_bus(event_bus)

    def bind_event_bus(self, bus: EventBus | None) -> None:
        if self._event_subscription is not None:
            self._event_subscription.cancel()
            self._event_subscription = None
        if bus is not None:
            self._event_subscription = bus.subscribe("*", self._queue_event)

    def _queue_event(self, event: Event) -> None:
        self._pending_events.append(event)

    def register(self, spec: ReactionSpec) -> None:
        if spec.reaction_id in self.specs:
            raise ValueError(f"duplicate reaction id: {spec.reaction_id}")
        self.specs[spec.reaction_id] = spec

    add = register

    def unregister(self, reaction_id: str) -> None:
        self.specs.pop(reaction_id, None)

    def create_scope(
        self,
        scope_id: str,
        *,
        owner_id: str | None = None,
        parent_id: str | None = None,
    ) -> TaskScope:
        if scope_id in self.scopes and self.scopes[scope_id].active:
            return self.scopes[scope_id]
        parent = self.scopes.get(parent_id) if parent_id else None
        scope = TaskScope(scope_id, owner_id=owner_id, parent=parent)
        self.scopes[scope_id] = scope
        return scope

    def cancel_scope(self, scope_id: str, reason: str = "owner_cancelled", frame: int = 0) -> None:
        scope = self.scopes.get(scope_id)
        if scope is None:
            return
        scope.cancel(reason, frame=frame)
        self._started = {
            key for key in self._started if key[1] != scope_id
        }
        self._last_start = {
            key: value
            for key, value in self._last_start.items()
            if key[1] != scope_id
        }
        for instance_id, instance in tuple(self.instances.items()):
            if instance.scope is scope or not instance.scope.active:
                self.trace.append(
                    ReactionTrace(
                        frame,
                        instance.spec.reaction_id,
                        "cancel",
                        instance.event.type,
                        instance.event.event_id,
                        instance_id,
                        scope_id,
                        reason,
                        count=_event_count(instance.event),
                        causal_depth=len(instance.event.causal_chain),
                    )
                )
                self.instances.pop(instance_id, None)

    def process(
        self,
        events: Iterable[Event],
        frame: int,
        *,
        context: Any = None,
        variables: Any = None,
        scope_id: str = "stage",
        specs: Iterable[ReactionSpec] | None = None,
    ) -> tuple[ReactionTrace, ...]:
        scope = self.create_scope(scope_id, owner_id=scope_id)
        values = tuple(events)
        before = len(self.trace)
        started = 0
        definitions = self.specs.values() if specs is None else tuple(specs)
        for spec in sorted(definitions, key=lambda item: item.reaction_id):
            matched = [event for event in values if self._matches(spec, event, variables, context)]
            if not matched:
                continue
            if spec.policy == "first_per_frame":
                matched = matched[:1]
            elif spec.policy in {"count_per_frame", "debounce"}:
                matched = [_aggregate_events(matched, frame)]
            for event in matched:
                if started >= self.max_instances_per_frame:
                    self._suppress(spec, event, frame, "frame_instance_budget")
                    continue
                if len(event.causal_chain) > min(self.max_causal_depth, spec.max_causal_depth):
                    self._suppress(spec, event, frame, "causal_depth")
                    continue
                key = (spec.reaction_id, scope.scope_id)
                active = [
                    item
                    for item in self.instances.values()
                    if item.spec.reaction_id == spec.reaction_id
                    and item.scope.parent is scope
                ]
                if spec.once_per_scope and key in self._started:
                    self._suppress(spec, event, frame, "once_per_scope")
                    continue
                if spec.cooldown_frames and key in self._last_start and frame - self._last_start[key] < spec.cooldown_frames:
                    self._suppress(spec, event, frame, "cooldown")
                    continue
                if len(active) >= spec.max_instances:
                    if spec.reentry == "restart":
                        for item in tuple(active):
                            item.scope.cancel("replaced", frame=frame)
                            self.instances.pop(item.instance_id, None)
                            self.trace.append(ReactionTrace(frame, spec.reaction_id, "cancel", event.type, event.event_id, item.instance_id, scope.scope_id, "replaced", _event_count(event), len(event.causal_chain)))
                    else:
                        self._suppress(spec, event, frame, "ignore_while_running" if spec.reentry != "parallel" else "max_instances")
                        continue
                instance = self._start(spec, event, frame, scope, context)
                if instance is not None:
                    started += 1
        return tuple(self.trace[before:])

    def process_pending(
        self,
        frame: int,
        *,
        context: Any = None,
        variables: Any = None,
        scope_id: str = "stage",
        specs: Iterable[ReactionSpec] | None = None,
    ) -> tuple[ReactionTrace, ...]:
        events = tuple(self._pending_events)
        self._pending_events.clear()
        return self.process(
            events,
            frame,
            context=context,
            variables=variables,
            scope_id=scope_id,
            specs=specs,
        )

    def reset(self, *, frame: int = 0, clear_trace: bool = True) -> None:
        """Cancel all runtime work and restore deterministic fresh scopes."""

        for scope in tuple(self.scopes.values()):
            scope.cancel("reset", frame=frame)
        self.instances.clear()
        self.scopes.clear()
        self._started.clear()
        self._last_start.clear()
        self._pending_events.clear()
        if clear_trace:
            self.trace.clear()
            self.diagnostics.clear()

    def cancel_owner(self, owner_id: str, reason: str = "owner_cancelled", frame: int = 0) -> int:
        """Cancel every scope belonging to one authoring/runtime owner."""

        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        targets = [
            scope_id
            for scope_id, scope in self.scopes.items()
            if scope.owner_id == owner_id or scope.scope_id == owner_id
        ]
        for scope_id in targets:
            self.cancel_scope(scope_id, reason=reason, frame=frame)
        self._pending_events = [
            event for event in self._pending_events if event.owner != owner_id
        ]
        return len(targets)

    def cancel_reaction(
        self,
        reaction_id: str,
        scope_id: str,
        reason: str = "cancelled",
        *,
        frame: int = 0,
    ) -> int:
        """Cancel active instances for one clip while keeping its state scope."""

        cancelled = 0
        for instance_id, instance in tuple(self.instances.items()):
            parent = instance.scope.parent
            if instance.spec.reaction_id != reaction_id or parent is None:
                continue
            if parent.scope_id != scope_id:
                continue
            instance.scope.cancel(reason, frame=frame)
            self.trace.append(
                ReactionTrace(
                    frame,
                    reaction_id,
                    "cancel",
                    instance.event.type,
                    instance.event.event_id,
                    instance_id,
                    scope_id,
                    reason,
                    count=_event_count(instance.event),
                    causal_depth=len(instance.event.causal_chain),
                )
            )
            self.instances.pop(instance_id, None)
            cancelled += 1
        return cancelled

    def tick(self, frame: int) -> None:
        for instance_id, instance in tuple(self.instances.items()):
            instance.scope.tick(frame)
            if not instance.scope.active:
                self.trace.append(ReactionTrace(frame, instance.spec.reaction_id, "complete", instance.event.type, instance.event.event_id, instance_id, instance.scope.scope_id, causal_depth=len(instance.event.causal_chain), count=_event_count(instance.event)))
                self.instances.pop(instance_id, None)

    def _matches(self, spec: ReactionSpec, event: Event, variables: Any, context: Any) -> bool:
        if event.type != spec.event_type:
            return False
        if spec.source is not None and event.source != spec.source:
            return False
        if spec.owner is not None and event.owner != spec.owner:
            return False
        if spec.payload_filter is not None:
            if callable(spec.payload_filter):
                if not bool(spec.payload_filter(event.payload)):
                    return False
            elif isinstance(event.payload, Mapping) and any(event.payload.get(key) != value for key, value in spec.payload_filter.items()):
                return False
            elif not isinstance(event.payload, Mapping):
                return False
        if spec.guard is not None and not bool(_invoke_guard(spec.guard, event, variables, context)):
            return False
        return True

    def _start(self, spec: ReactionSpec, event: Event, frame: int, scope: TaskScope, context: Any) -> _ReactionInstance | None:
        instance_id = f"{spec.reaction_id}@{scope.scope_id}#{next(self._serial)}"
        child = TaskScope(instance_id, owner_id=instance_id, parent=scope)
        self.scopes[instance_id] = child
        self._started.add((spec.reaction_id, scope.scope_id))
        self._last_start[(spec.reaction_id, scope.scope_id)] = frame
        instance = _ReactionInstance(instance_id, spec, child, frame, event)
        self.instances[instance_id] = instance
        self.trace.append(ReactionTrace(frame, spec.reaction_id, "start", event.type, event.event_id, instance_id, scope.scope_id, count=_event_count(event), causal_depth=len(event.causal_chain)))
        if spec.action is None:
            child.complete(frame)
        else:
            try:
                child.start(spec.action, task_id="action", frame=frame, context=context, event=event)
            except Exception as exc:  # noqa: BLE001 - action failure is diagnosed
                child.state = TaskScopeState.FAILED
                self.diagnostics.append({"kind": "reaction_action_error", "reaction_id": spec.reaction_id, "frame": frame, "detail": str(exc)})
                self.trace.append(ReactionTrace(frame, spec.reaction_id, "error", event.type, event.event_id, instance_id, scope.scope_id, "action_error", _event_count(event), len(event.causal_chain)))
                self.instances.pop(instance_id, None)
                self.scopes.pop(instance_id, None)
                return None
        return instance

    def _suppress(self, spec: ReactionSpec, event: Event, frame: int, reason: str) -> None:
        self.trace.append(ReactionTrace(frame, spec.reaction_id, "suppress", event.type, event.event_id, scope_id=spec.scope, reason=reason, count=_event_count(event), causal_depth=len(event.causal_chain)))
        self.diagnostics.append({"kind": "reaction_suppressed", "reaction_id": spec.reaction_id, "frame": frame, "reason": reason})


def _invoke_guard(guard: Callable[..., bool], event: Event, variables: Any, context: Any) -> bool:
    try:
        signature = inspect.signature(guard)
        count_args = len([
            item for item in signature.parameters.values()
            if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ])
    except (TypeError, ValueError):
        return bool(guard(event, variables, context))
    if count_args >= 3:
        return bool(guard(event, variables, context))
    if count_args == 2:
        return bool(guard(event, variables))
    if count_args == 1:
        return bool(guard(event))
    return bool(guard())


def _event_count(event: Event) -> int:
    return int(event.count) if isinstance(event, LifecycleEvent) else 1


def _aggregate_events(events: list[Event], frame: int) -> LifecycleEvent:
    first = events[0]
    count = sum(_event_count(event) for event in events)
    ids: list[str] = []
    for event in events:
        ids.extend(getattr(event, "representative_ids", ())[:8])
    payload = dict(first.payload) if isinstance(first.payload, Mapping) else {"value": first.payload}
    payload["count"] = count
    return LifecycleEvent(
        type=first.type,
        source=first.source,
        frame=frame,
        payload=payload,
        owner=first.owner,
        reason=getattr(first, "reason", None),
        count=count,
        representative_ids=tuple(ids[:8]),
        causal_chain=first.causal_chain,
        schema_version=first.schema_version,
    )


class ReactiveTimeline:
    """Owns armed ``ReactiveClip`` definitions for one state/timeline."""

    def __init__(self, clips: Iterable[ReactiveClip] = (), *, scheduler: ReactionScheduler | None = None) -> None:
        self.clips = tuple(clips)
        self.scheduler = scheduler or ReactionScheduler()
        for clip in self.clips:
            if clip.reaction.reaction_id not in self.scheduler.specs:
                self.scheduler.register(clip.reaction)
        self._state_scopes: dict[str, str] = {}
        self._armed_by_state: dict[str, set[str]] = {}
        self._generation = 0

    def enter_state(self, state_id: str, frame: int = 0) -> str:
        existing = self._state_scopes.get(state_id)
        if existing is not None:
            scope = self.scheduler.scopes.get(existing)
            if scope is not None and scope.active:
                return existing
        self._generation += 1
        scope_id = f"state:{state_id}#{self._generation}"
        self._state_scopes[state_id] = scope_id
        self.scheduler.create_scope(scope_id, owner_id=state_id)
        self._armed_by_state[state_id] = set()
        return scope_id

    def exit_state(self, state_id: str, frame: int = 0, reason: str = "state_exit") -> None:
        scope_id = self._state_scopes.pop(state_id, None)
        self._armed_by_state.pop(state_id, None)
        if scope_id is not None:
            self.scheduler.cancel_scope(scope_id, reason, frame=frame)

    def reset(self, *, frame: int = 0) -> None:
        """Reset scopes, instances, cooldowns, and traces for replay."""

        self.scheduler.reset(frame=frame)
        self._state_scopes.clear()
        self._armed_by_state.clear()
        self._generation = 0

    def armed_clips(self, state_id: str, frame: int) -> tuple[ReactiveClip, ...]:
        return tuple(
            clip for clip in self.clips
            if clip.state_id in {None, state_id} and clip.armed(frame)
        )

    def tick(
        self,
        state_id: str,
        frame: int,
        events: Iterable[Event] = (),
        *,
        context: Any = None,
        variables: Any = None,
        advance_scheduler: bool = True,
    ) -> tuple[ReactionTrace, ...]:
        scope_id = self._state_scopes.get(state_id) or self.enter_state(state_id, frame)
        active = self.armed_clips(state_id, frame)
        active_ids = {clip.reaction.reaction_id for clip in active}
        previous_ids = self._armed_by_state.setdefault(state_id, set())
        for reaction_id in previous_ids - active_ids:
            self.scheduler.cancel_reaction(
                reaction_id,
                scope_id,
                reason="clip_window_end",
                frame=frame,
            )
        self._armed_by_state[state_id] = active_ids
        traces = self.scheduler.process(
            events,
            frame,
            context=context,
            variables=variables,
            scope_id=scope_id,
            specs=tuple(clip.reaction for clip in active),
        )
        if advance_scheduler:
            self.scheduler.tick(frame)
        return traces


@dataclass(frozen=True)
class BackgroundTransition:
    """A small action adapter for a resource-backed background change."""

    resource: str
    fade_frames: int = 0

    def __call__(self, context: Any, event: Event, scope: TaskScope) -> None:
        if not isinstance(self.resource, str) or not self.resource.strip():
            raise ValueError("background resource must be non-empty")
        request = getattr(context, "request_background_transition", None)
        if callable(request):
            result = request(
                self.resource,
                owner=scope.scope_id,
                fade_frames=self.fade_frames,
            )
            if result is False:
                raise RuntimeError(f"background transition failed: {self.resource}")
        else:
            setter = getattr(context, "set_background", None)
            if not callable(setter) or not setter(self.resource):
                raise RuntimeError(f"background transition failed: {self.resource}")
        scope.complete()


__all__ = [
    "BackgroundTransition",
    "CancellationToken",
    "ReactionScheduler",
    "ReactionSpec",
    "ReactionTrace",
    "ReactiveClip",
    "ReactiveTimeline",
    "TaskScope",
    "TaskScopeState",
    "TaskTrace",
    "TaskWait",
]

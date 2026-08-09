"""Lifecycle reactions, reactive timeline clips, and structured task scopes.

This module is intentionally runtime-only.  Authoring documents may describe
the same records, but actions are resolved by the formal runtime and never by
Qt widgets or by a producer calling a timeline clip directly.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from enum import Enum
from itertools import count
from typing import Any, Callable, Iterable, Iterator, Mapping

from .events import Event, EventBus, LifecycleEvent


_ACTIVATION_KINDS = {"at_frame", "when_variable", "on_event", "on_lifecycle"}
_ACTIVATION_OPERATORS = {"==", "!=", ">", ">=", "<", "<=", "truthy", "falsy"}
_ACTIVATION_EDGES = {"on_rise", "while_true", "on_fall", "on_change"}
_ACTIVATION_SCOPES = {"stage", "state", "clip", "reaction", "behavior"}
_ACTIVATION_FIELDS = {
    "kind",
    "frame",
    "variable",
    "operator",
    "value",
    "edge",
    "event_type",
    "source",
    "owner",
    "payload_filter",
    "reason",
    "delay_frames",
    "scope",
}


def _json_safe(value: Any, *, path: str = "value") -> Any:
    """Detach a value and reject runtime-only objects in authoring records."""

    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must contain JSON values") from exc
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f"{path} object keys must be strings")
        return {str(key): _json_safe(item, path=f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, path=f"{path}[]") for item in value]
    return value


def _non_negative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path} must be a non-negative integer")
    return int(value)


@dataclass(frozen=True, init=False)
class ActivationRule:
    """Serializable rule that decides when a timeline lifecycle is armed.

    Rules contain facts and comparisons only.  They never carry a command or
    callable; the runtime resolves the action attached to the parent reaction.
    """

    kind: str
    frame: int | None
    variable: str | Mapping[str, Any] | None
    operator: str
    value: Any
    edge: str
    event_type: str | None
    source: str | None
    owner: str | None
    payload_filter: Mapping[str, Any] | None
    reason: str | None
    delay_frames: int
    scope: str

    def __init__(
        self,
        kind: str,
        *,
        frame: int | None = None,
        variable: str | Mapping[str, Any] | None = None,
        operator: str = "truthy",
        value: Any = None,
        edge: str = "while_true",
        event_type: str | None = None,
        source: str | None = None,
        owner: str | None = None,
        payload_filter: Mapping[str, Any] | None = None,
        reason: str | None = None,
        delay_frames: int = 0,
        scope: str = "state",
    ) -> None:
        if not isinstance(kind, str) or kind not in _ACTIVATION_KINDS:
            raise ValueError(f"activation kind is unsupported: {kind!r}")
        if kind == "at_frame":
            if frame is None:
                raise ValueError("at_frame activation requires frame")
            frame = _non_negative_int(frame, "activation.frame")
        elif frame is not None:
            frame = _non_negative_int(frame, "activation.frame")
        if kind == "when_variable":
            if not isinstance(variable, (str, Mapping)) or (
                isinstance(variable, str) and not variable.strip()
            ):
                raise ValueError("when_variable activation requires variable")
            if isinstance(variable, Mapping):
                allowed = {"name", "scope", "type", "owner_id"}
                unknown = set(variable).difference(allowed)
                if unknown:
                    raise ValueError(
                        "activation.variable unknown fields: "
                        + ", ".join(sorted(str(item) for item in unknown))
                    )
                if not isinstance(variable.get("name"), str) or not variable["name"].strip():
                    raise ValueError("activation.variable.name must be non-empty")
                variable = dict(variable)
            if operator not in _ACTIVATION_OPERATORS:
                raise ValueError(f"activation.operator is unsupported: {operator!r}")
            if edge not in _ACTIVATION_EDGES:
                raise ValueError(f"activation.edge is unsupported: {edge!r}")
            value = _json_safe(value, path="activation.value")
        else:
            variable = None
            operator = "truthy"
            edge = "while_true"
            value = _json_safe(value, path="activation.value")
        if kind in {"on_event", "on_lifecycle"}:
            if not isinstance(event_type, str) or not event_type.strip():
                raise ValueError(f"{kind} activation requires event_type")
            event_type = event_type.strip()
        elif event_type is not None:
            if not isinstance(event_type, str) or not event_type.strip():
                raise ValueError("activation.event_type must be a non-empty string")
            event_type = event_type.strip()
        for name, raw in (("source", source), ("owner", owner), ("reason", reason)):
            if raw is not None and (not isinstance(raw, str) or not raw.strip()):
                raise ValueError(f"activation.{name} must be a non-empty string or null")
        if payload_filter is not None:
            if not isinstance(payload_filter, Mapping):
                raise ValueError("activation.payload_filter must be an object")
            payload_filter = _json_safe(dict(payload_filter), path="activation.payload_filter")
        delay_frames = _non_negative_int(delay_frames, "activation.delay_frames")
        if scope not in _ACTIVATION_SCOPES:
            raise ValueError(f"activation.scope is unsupported: {scope!r}")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "frame", frame)
        object.__setattr__(self, "variable", variable.strip() if isinstance(variable, str) else variable)
        object.__setattr__(self, "operator", operator)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "edge", edge)
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "source", source.strip() if isinstance(source, str) else None)
        object.__setattr__(self, "owner", owner.strip() if isinstance(owner, str) else None)
        object.__setattr__(self, "payload_filter", payload_filter)
        object.__setattr__(self, "reason", reason.strip() if isinstance(reason, str) else None)
        object.__setattr__(self, "delay_frames", delay_frames)
        object.__setattr__(self, "scope", scope)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActivationRule":
        if not isinstance(data, Mapping):
            raise ValueError("activation rule must be an object")
        unknown = set(data).difference(_ACTIVATION_FIELDS)
        if unknown:
            raise ValueError(
                "activation rule unknown fields: "
                + ", ".join(sorted(str(item) for item in unknown))
            )
        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind}
        if self.frame is not None:
            payload["frame"] = self.frame
        if self.variable is not None:
            payload["variable"] = (
                dict(self.variable) if isinstance(self.variable, Mapping) else self.variable
            )
            payload["operator"] = self.operator
            payload["value"] = _json_safe(self.value, path="activation.value")
            payload["edge"] = self.edge
        if self.event_type is not None:
            payload["event_type"] = self.event_type
        if self.source is not None:
            payload["source"] = self.source
        if self.owner is not None:
            payload["owner"] = self.owner
        if self.payload_filter is not None:
            payload["payload_filter"] = dict(self.payload_filter)
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.delay_frames:
            payload["delay_frames"] = self.delay_frames
        if self.scope != "state":
            payload["scope"] = self.scope
        return payload

    @property
    def variable_name(self) -> str | None:
        if isinstance(self.variable, Mapping):
            return str(self.variable.get("name"))
        return self.variable

    def match_event(self, event: Event) -> bool:
        if self.kind not in {"on_event", "on_lifecycle"}:
            return False
        if self.kind == "on_lifecycle" and not isinstance(event, LifecycleEvent):
            return False
        if event.type != self.event_type:
            return False
        if self.source is not None and event.source != self.source:
            return False
        if self.owner is not None and event.owner != self.owner:
            return False
        if self.reason is not None and getattr(event, "reason", None) != self.reason:
            return False
        if self.payload_filter is not None:
            payload = event.payload
            if not isinstance(payload, Mapping):
                return False
            if any(payload.get(key) != value for key, value in self.payload_filter.items()):
                return False
        return True

    def match_variable(self, raw_value: Any, memory: dict[str, Any]) -> bool:
        if self.kind != "when_variable":
            return False
        previous_exists = "value" in memory
        previous = memory.get("value")
        memory["value"] = _json_safe(raw_value, path="activation.variable_value")
        current = _compare_value(raw_value, self.operator, self.value)
        previous_match = _compare_value(previous, self.operator, self.value) if previous_exists else False
        if self.edge == "while_true":
            return bool(current)
        if self.edge == "on_rise":
            return bool(current) and not previous_match
        if self.edge == "on_fall":
            return previous_exists and previous_match and not current
        return previous_exists and memory["value"] != previous

    def matches_frame(self, frame: int) -> bool:
        return self.kind == "at_frame" and self.frame == frame


def _compare_value(left: Any, operator: str, right: Any) -> bool:
    if operator == "truthy":
        return bool(left)
    if operator == "falsy":
        return not bool(left)
    try:
        if operator == "==":
            return left == right
        if operator == "!=":
            return left != right
        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right
        if operator == "<":
            return left < right
        if operator == "<=":
            return left <= right
    except (TypeError, ValueError):
        return False
    return False


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
        if not isinstance(scope, str) or scope.strip() not in _ACTIVATION_SCOPES:
            raise ValueError("unsupported reaction scope")
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

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        action_resolver: Callable[[str], Callable[..., Any] | None] | None = None,
    ) -> "ReactionSpec":
        if not isinstance(data, Mapping):
            raise ValueError("reaction must be an object")
        allowed = {
            "id", "reaction_id", "event_type", "trigger", "source", "owner",
            "payload_filter", "policy", "reentry", "scope", "once_per_scope",
            "cooldown_frames", "max_instances", "max_causal_depth", "action", "action_id",
        }
        unknown = set(data).difference(allowed)
        if unknown:
            raise ValueError(
                "reaction unknown fields: "
                + ", ".join(sorted(str(item) for item in unknown))
            )
        action_id = data.get("action_id", data.get("action"))
        action = None
        if action_resolver is not None and isinstance(action_id, str) and action_id.strip():
            action = action_resolver(action_id.strip())
        return cls(
            str(data.get("id", data.get("reaction_id", ""))),
            data.get("event_type"),
            action,
            trigger=data.get("trigger"),
            source=data.get("source"),
            owner=data.get("owner"),
            payload_filter=data.get("payload_filter"),
            policy=data.get("policy", "each"),
            reentry=data.get("reentry", "ignore_while_running"),
            scope=data.get("scope", "stage"),
            once_per_scope=data.get("once_per_scope", True),
            cooldown_frames=data.get("cooldown_frames", 0),
            max_instances=data.get("max_instances", 1),
            max_causal_depth=data.get("max_causal_depth", 32),
            action_id=action_id,
        )


@dataclass(frozen=True)
class ReactiveClip:
    """A timeline slot that arms a reaction for a state/time window."""

    clip_id: str
    reaction: ReactionSpec
    state_id: str | None = None
    start_frame: int = 0
    end_frame: int | None = None
    owner_id: str | None = None
    activation: ActivationRule | None = None
    scope: str = "state"

    def __post_init__(self) -> None:
        if not isinstance(self.clip_id, str) or not self.clip_id.strip():
            raise ValueError("clip_id must be a non-empty string")
        if not isinstance(self.reaction, ReactionSpec):
            raise TypeError("clip reaction must be a ReactionSpec")
        if isinstance(self.start_frame, bool) or not isinstance(self.start_frame, int) or self.start_frame < 0:
            raise ValueError("clip start_frame must be non-negative")
        if self.end_frame is not None and (
            isinstance(self.end_frame, bool)
            or not isinstance(self.end_frame, int)
            or self.end_frame <= self.start_frame
        ):
            raise ValueError("clip end_frame must be greater than start_frame")
        if self.owner_id is not None and (
            not isinstance(self.owner_id, str) or not self.owner_id.strip()
        ):
            raise ValueError("clip owner_id must be a non-empty string or null")
        if self.activation is not None and not isinstance(self.activation, ActivationRule):
            raise TypeError("clip activation must be an ActivationRule or null")
        if self.scope not in _ACTIVATION_SCOPES:
            raise ValueError("clip scope is unsupported")
        if isinstance(self.owner_id, str):
            object.__setattr__(self, "owner_id", self.owner_id.strip() or None)

    @property
    def effective_activation(self) -> ActivationRule:
        return self.activation or ActivationRule(
            kind="on_event",
            event_type=self.reaction.event_type,
            source=self.reaction.source,
            owner=self.reaction.owner,
            payload_filter=(
                dict(self.reaction.payload_filter)
                if isinstance(self.reaction.payload_filter, Mapping)
                else None
            ),
            scope=self.scope,
        )

    def armed(self, frame: int) -> bool:
        return frame >= self.start_frame and (self.end_frame is None or frame < self.end_frame)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.clip_id,
            "state_id": self.state_id,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "owner_id": self.owner_id,
            "scope": self.scope,
            "activation": self.effective_activation.to_dict(),
            "reaction": self.reaction.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        action_resolver: Callable[[str], Callable[..., Any] | None] | None = None,
    ) -> "ReactiveClip":
        if not isinstance(data, Mapping):
            raise ValueError("reactive clip must be an object")
        allowed = {
            "id", "clip_id", "state_id", "start_frame", "end_frame", "owner_id",
            "scope", "activation", "reaction",
        }
        unknown = set(data).difference(allowed)
        if unknown:
            raise ValueError(
                "reactive clip unknown fields: "
                + ", ".join(sorted(str(item) for item in unknown))
            )
        reaction_data = data.get("reaction")
        if not isinstance(reaction_data, Mapping):
            raise ValueError("reactive clip reaction must be an object")
        activation_data = data.get("activation")
        activation = (
            ActivationRule.from_dict(activation_data)
            if isinstance(activation_data, Mapping)
            else None
        )
        return cls(
            str(data.get("id", data.get("clip_id", ""))),
            ReactionSpec.from_dict(reaction_data, action_resolver=action_resolver),
            state_id=data.get("state_id"),
            start_frame=data.get("start_frame", 0),
            end_frame=data.get("end_frame"),
            owner_id=data.get("owner_id"),
            activation=activation,
            scope=data.get("scope", "state"),
        )


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
    # N4 fields are appended so existing positional N3 integrations retain
    # their constructor order.
    clip_id: str | None = None
    owner_id: str | None = None
    trigger_kind: str | None = None
    source: str | None = None
    trigger_frame: int | None = None
    started_frame: int | None = None
    stopped_frame: int | None = None
    activation_snapshot: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "reaction_id": self.reaction_id,
            "kind": self.kind,
            "event_type": self.event_type,
            "event_id": self.event_id,
            "instance_id": self.instance_id,
            "scope_id": self.scope_id,
            "reason": self.reason,
            "count": self.count,
            "causal_depth": self.causal_depth,
            "clip_id": self.clip_id,
            "owner_id": self.owner_id,
            "trigger_kind": self.trigger_kind,
            "source": self.source,
            "trigger_frame": self.trigger_frame,
            "started_frame": self.started_frame,
            "stopped_frame": self.stopped_frame,
            "activation_snapshot": self.activation_snapshot,
        }

    @property
    def trigger_source(self) -> str | None:
        return self.source

    @property
    def actual_start_frame(self) -> int | None:
        return self.started_frame

    @property
    def stop_reason(self) -> str | None:
        return self.reason


@dataclass
class _ReactionInstance:
    instance_id: str
    spec: ReactionSpec
    scope: TaskScope
    started_frame: int
    event: Event
    clip_id: str | None = None
    owner_id: str | None = None
    trigger_kind: str | None = None
    trigger_frame: int | None = None
    activation_snapshot: Any = None


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
        self._budget_frame: int | None = None
        self._started_this_frame = 0
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
                        clip_id=instance.clip_id,
                        owner_id=instance.owner_id,
                        trigger_kind=instance.trigger_kind,
                        source=instance.event.source,
                        trigger_frame=instance.trigger_frame,
                        started_frame=instance.started_frame,
                        stopped_frame=frame,
                        activation_snapshot=instance.activation_snapshot,
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
        clip_id: str | None = None,
        owner_id: str | None = None,
        trigger_kind: str | None = None,
        trigger_frame: int | None = None,
        activation_snapshot: Any = None,
        action_resolver: Callable[[str], Callable[..., Any] | None] | None = None,
    ) -> tuple[ReactionTrace, ...]:
        if self._budget_frame != frame:
            self._budget_frame = frame
            self._started_this_frame = 0
        scope = self.create_scope(scope_id, owner_id=scope_id)
        values = tuple(events)
        before = len(self.trace)
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
                if self._started_this_frame >= self.max_instances_per_frame:
                    self._suppress(spec, event, frame, "frame_instance_budget", clip_id=clip_id)
                    continue
                if len(event.causal_chain) > min(self.max_causal_depth, spec.max_causal_depth):
                    self._suppress(spec, event, frame, "causal_depth", clip_id=clip_id)
                    continue
                identity = clip_id or spec.reaction_id
                key = (identity, scope.scope_id)
                active = [
                    item
                    for item in self.instances.values()
                    if item.spec.reaction_id == spec.reaction_id
                    and (clip_id is None or item.clip_id == clip_id)
                    and item.scope.parent is scope
                ]
                if spec.once_per_scope and key in self._started:
                    self._suppress(spec, event, frame, "once_per_scope", clip_id=clip_id)
                    continue
                if spec.cooldown_frames and key in self._last_start and frame - self._last_start[key] < spec.cooldown_frames:
                    self._suppress(spec, event, frame, "cooldown", clip_id=clip_id)
                    continue
                if len(active) >= spec.max_instances:
                    if spec.reentry == "restart":
                        for item in tuple(active):
                            item.scope.cancel("replaced", frame=frame)
                            self.instances.pop(item.instance_id, None)
                            self.trace.append(
                                ReactionTrace(
                                    frame,
                                    spec.reaction_id,
                                    "cancel",
                                    event.type,
                                    event.event_id,
                                    item.instance_id,
                                    scope.scope_id,
                                    "replaced",
                                    _event_count(event),
                                    len(event.causal_chain),
                                    clip_id=item.clip_id,
                                    owner_id=item.owner_id,
                                    trigger_kind=item.trigger_kind,
                                    source=item.event.source,
                                    trigger_frame=item.trigger_frame,
                                    started_frame=item.started_frame,
                                    stopped_frame=frame,
                                    activation_snapshot=item.activation_snapshot,
                                )
                            )
                    else:
                        self._suppress(
                            spec,
                            event,
                            frame,
                            "ignore_while_running" if spec.reentry != "parallel" else "max_instances",
                            clip_id=clip_id,
                        )
                        continue
                instance = self._start(
                    spec,
                    event,
                    frame,
                    scope,
                    context,
                    clip_id=clip_id,
                    owner_id=owner_id,
                    trigger_kind=trigger_kind,
                    trigger_frame=trigger_frame,
                    activation_snapshot=activation_snapshot,
                    action_resolver=action_resolver,
                )
                if instance is not None:
                    self._started_this_frame += 1
        return tuple(self.trace[before:])

    def process_pending(
        self,
        frame: int,
        *,
        context: Any = None,
        variables: Any = None,
        scope_id: str = "stage",
        specs: Iterable[ReactionSpec] | None = None,
        action_resolver: Callable[[str], Callable[..., Any] | None] | None = None,
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
            action_resolver=action_resolver,
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
        self._budget_frame = None
        self._started_this_frame = 0
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
        clip_id: str | None = None,
    ) -> int:
        """Cancel active instances for one clip while keeping its state scope."""

        cancelled = 0
        for instance_id, instance in tuple(self.instances.items()):
            parent = instance.scope.parent
            if instance.spec.reaction_id != reaction_id or parent is None:
                continue
            if clip_id is not None and instance.clip_id != clip_id:
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
                    clip_id=instance.clip_id,
                    owner_id=instance.owner_id,
                    trigger_kind=instance.trigger_kind,
                    source=instance.event.source,
                    trigger_frame=instance.trigger_frame,
                    started_frame=instance.started_frame,
                    stopped_frame=frame,
                    activation_snapshot=instance.activation_snapshot,
                )
            )
            self.instances.pop(instance_id, None)
            cancelled += 1
        return cancelled

    def tick(self, frame: int) -> None:
        for instance_id, instance in tuple(self.instances.items()):
            instance.scope.tick(frame)
            if not instance.scope.active:
                self.trace.append(
                    ReactionTrace(
                        frame,
                        instance.spec.reaction_id,
                        "complete",
                        instance.event.type,
                        instance.event.event_id,
                        instance_id,
                        instance.scope.scope_id,
                        causal_depth=len(instance.event.causal_chain),
                        count=_event_count(instance.event),
                        clip_id=instance.clip_id,
                        owner_id=instance.owner_id,
                        trigger_kind=instance.trigger_kind,
                        source=instance.event.source,
                        trigger_frame=instance.trigger_frame,
                        started_frame=instance.started_frame,
                        stopped_frame=frame,
                        activation_snapshot=instance.activation_snapshot,
                    )
                )
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

    def _start(
        self,
        spec: ReactionSpec,
        event: Event,
        frame: int,
        scope: TaskScope,
        context: Any,
        *,
        clip_id: str | None = None,
        owner_id: str | None = None,
        trigger_kind: str | None = None,
        trigger_frame: int | None = None,
        activation_snapshot: Any = None,
        action_resolver: Callable[[str], Callable[..., Any] | None] | None = None,
    ) -> _ReactionInstance | None:
        instance_id = f"{clip_id or spec.reaction_id}@{scope.scope_id}#{next(self._serial)}"
        child = TaskScope(instance_id, owner_id=owner_id or instance_id, parent=scope)
        self.scopes[instance_id] = child
        identity = clip_id or spec.reaction_id
        self._started.add((identity, scope.scope_id))
        self._last_start[(identity, scope.scope_id)] = frame
        instance = _ReactionInstance(
            instance_id,
            spec,
            child,
            frame,
            event,
            clip_id=clip_id,
            owner_id=owner_id,
            trigger_kind=trigger_kind,
            trigger_frame=frame if trigger_frame is None else trigger_frame,
            activation_snapshot=activation_snapshot,
        )
        self.instances[instance_id] = instance
        self.trace.append(
            ReactionTrace(
                frame,
                spec.reaction_id,
                "start",
                event.type,
                event.event_id,
                instance_id,
                scope.scope_id,
                count=_event_count(event),
                causal_depth=len(event.causal_chain),
                clip_id=clip_id,
                owner_id=owner_id,
                trigger_kind=trigger_kind,
                source=event.source,
                trigger_frame=instance.trigger_frame,
                started_frame=frame,
                activation_snapshot=activation_snapshot,
            )
        )
        action = spec.action
        if action is None and spec.action_id and action_resolver is not None:
            action = _resolve_action(action_resolver, spec.action_id)
            if action is None:
                self.diagnostics.append(
                    {
                        "kind": "reaction_action_unresolved",
                        "reaction_id": spec.reaction_id,
                        "action_id": spec.action_id,
                        "frame": frame,
                    }
                )
                child.state = TaskScopeState.FAILED
                self.trace.append(
                    ReactionTrace(
                        frame,
                        spec.reaction_id,
                        "error",
                        event.type,
                        event.event_id,
                        instance_id,
                        scope.scope_id,
                        "action_unresolved",
                        _event_count(event),
                        len(event.causal_chain),
                        clip_id=clip_id,
                        owner_id=owner_id,
                        trigger_kind=trigger_kind,
                        source=event.source,
                        trigger_frame=instance.trigger_frame,
                        started_frame=frame,
                        stopped_frame=frame,
                        activation_snapshot=activation_snapshot,
                    )
                )
                self.instances.pop(instance_id, None)
                self.scopes.pop(instance_id, None)
                return None
        if action is None:
            child.complete(frame)
        else:
            try:
                child.start(action, task_id="action", frame=frame, context=context, event=event)
            except Exception as exc:  # noqa: BLE001 - action failure is diagnosed
                child.state = TaskScopeState.FAILED
                self.diagnostics.append({"kind": "reaction_action_error", "reaction_id": spec.reaction_id, "frame": frame, "detail": str(exc)})
                self.trace.append(
                    ReactionTrace(
                        frame,
                        spec.reaction_id,
                        "error",
                        event.type,
                        event.event_id,
                        instance_id,
                        scope.scope_id,
                        "action_error",
                        _event_count(event),
                        len(event.causal_chain),
                        clip_id=clip_id,
                        owner_id=owner_id,
                        trigger_kind=trigger_kind,
                        source=event.source,
                        trigger_frame=instance.trigger_frame,
                        started_frame=frame,
                        stopped_frame=frame,
                        activation_snapshot=activation_snapshot,
                    )
                )
                self.instances.pop(instance_id, None)
                self.scopes.pop(instance_id, None)
                return None
        return instance

    def _suppress(
        self,
        spec: ReactionSpec,
        event: Event,
        frame: int,
        reason: str,
        *,
        clip_id: str | None = None,
    ) -> None:
        self.trace.append(
            ReactionTrace(
                frame,
                spec.reaction_id,
                "suppress",
                event.type,
                event.event_id,
                scope_id=spec.scope,
                reason=reason,
                count=_event_count(event),
                causal_depth=len(event.causal_chain),
                clip_id=clip_id,
                source=event.source,
                trigger_frame=frame,
            )
        )
        self.diagnostics.append(
            {
                "kind": "reaction_suppressed",
                "reaction_id": spec.reaction_id,
                "clip_id": clip_id,
                "frame": frame,
                "reason": reason,
            }
        )


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


def _resolve_action(
    resolver: Callable[[str], Callable[..., Any] | None],
    action_id: str,
) -> Callable[..., Any] | None:
    """Resolve an action ID without imposing a callable signature on plugins."""

    try:
        result = resolver(action_id)
    except TypeError:
        # A few runtime adapters expose a mapping-like resolver that accepts a
        # keyword.  Keep the fallback narrow so body errors are not swallowed.
        result = resolver(action_id=action_id)  # type: ignore[call-arg]
    if result is not None and not callable(result):
        raise TypeError(f"reaction action resolver returned non-callable for {action_id!r}")
    return result


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
        self._activation_memory: dict[tuple[str, str], dict[str, Any]] = {}
        self._pending: dict[tuple[str, str], list[tuple[int, int, Event, str, Any]]] = {}
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
        for key in tuple(self._pending):
            if key[0] == state_id:
                self._pending.pop(key, None)
        for key in tuple(self._activation_memory):
            if key[0] == state_id:
                self._activation_memory.pop(key, None)
        if scope_id is not None:
            self.scheduler.cancel_scope(scope_id, reason, frame=frame)

    def reset(self, *, frame: int = 0) -> None:
        """Reset scopes, instances, cooldowns, and traces for replay."""

        self.scheduler.reset(frame=frame)
        self._state_scopes.clear()
        self._armed_by_state.clear()
        self._activation_memory.clear()
        self._pending.clear()
        self._generation = 0

    def cancel_owner(
        self,
        owner_id: str,
        *,
        frame: int = 0,
        reason: str = "owner_cancelled",
    ) -> int:
        """Cancel active and delayed work for one authoring owner."""

        cancelled = self.scheduler.cancel_owner(owner_id, reason=reason, frame=frame)
        for key in tuple(self._pending):
            state_id, clip_id = key
            clip = next((item for item in self.clips if item.clip_id == clip_id), None)
            if clip is not None and clip.owner_id == owner_id:
                pending = self._pending.pop(key, ())
                for due, trigger_frame, event, trigger_kind, snapshot in pending:
                    self.scheduler.trace.append(
                        ReactionTrace(
                            frame,
                            clip.reaction.reaction_id,
                            "cancel",
                            event.type,
                            event.event_id,
                            f"pending:{clip_id}:{trigger_frame}",
                            self._state_scopes.get(state_id),
                            reason,
                            count=_event_count(event),
                            causal_depth=len(event.causal_chain),
                            clip_id=clip_id,
                            owner_id=owner_id,
                            trigger_kind=trigger_kind,
                            source=event.source,
                            trigger_frame=trigger_frame,
                            stopped_frame=frame,
                            activation_snapshot=snapshot,
                        )
                    )
                    cancelled += 1
        return cancelled

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
        action_resolver: Callable[[str], Callable[..., Any] | None] | None = None,
        local_frame: int | None = None,
    ) -> tuple[ReactionTrace, ...]:
        scope_id = self._state_scopes.get(state_id) or self.enter_state(state_id, frame)
        activation_frame = frame if local_frame is None else local_frame
        active = tuple(
            sorted(self.armed_clips(state_id, activation_frame), key=lambda item: item.clip_id)
        )
        active_ids = {clip.clip_id for clip in active}
        previous_ids = self._armed_by_state.setdefault(state_id, set())
        clip_by_id = {clip.clip_id: clip for clip in self.clips}
        for clip_id in previous_ids - active_ids:
            old_clip = clip_by_id.get(clip_id)
            if old_clip is None:
                continue
            self.scheduler.cancel_reaction(
                old_clip.reaction.reaction_id,
                scope_id,
                reason="clip_window_end",
                frame=frame,
                clip_id=clip_id,
            )
            pending = self._pending.pop((state_id, clip_id), None) or []
            for due, trigger_frame, event, trigger_kind, snapshot in pending:
                self.scheduler.trace.append(
                    ReactionTrace(
                        frame,
                        old_clip.reaction.reaction_id,
                        "cancel",
                        event.type,
                        event.event_id,
                        f"pending:{clip_id}:{trigger_frame}",
                        scope_id,
                        "clip_window_end",
                        count=_event_count(event),
                        causal_depth=len(event.causal_chain),
                        clip_id=clip_id,
                        owner_id=old_clip.owner_id,
                        trigger_kind=trigger_kind,
                        source=event.source,
                        trigger_frame=trigger_frame,
                        stopped_frame=frame,
                        activation_snapshot=snapshot,
                    )
                )
        self._armed_by_state[state_id] = active_ids
        incoming = tuple(events)
        before = len(self.scheduler.trace)
        for clip in active:
            rule = clip.effective_activation
            key = (state_id, clip.clip_id)
            memory = self._activation_memory.setdefault(key, {})
            triggers: list[tuple[Event, str, Any, int]] = []
            if rule.kind in {"on_event", "on_lifecycle"}:
                for event in incoming:
                    if rule.match_event(event):
                        triggers.append((event, rule.kind, _activation_snapshot(rule, event), frame))
            elif rule.kind == "at_frame" and rule.matches_frame(activation_frame):
                triggers.append(
                    (
                        _synthetic_activation_event(clip, frame),
                        rule.kind,
                        _activation_snapshot(rule, None),
                        frame,
                    )
                )
            elif rule.kind == "when_variable":
                value = _read_activation_variable(variables, rule)
                if rule.match_variable(value, memory):
                    triggers.append(
                        (
                            _synthetic_activation_event(clip, frame, payload={"value": value}),
                            rule.kind,
                            _activation_snapshot(rule, None, value=value),
                            frame,
                        )
                    )
            pending = self._pending.setdefault(key, [])
            for event, trigger_kind, snapshot, trigger_frame in triggers:
                due = activation_frame + rule.delay_frames
                pending.append((due, trigger_frame, event, trigger_kind, snapshot))
            due_values = [item for item in pending if item[0] <= activation_frame]
            self._pending[key] = [item for item in pending if item[0] > activation_frame]
            for due, trigger_frame, event, trigger_kind, snapshot in due_values:
                # Activation rules select a lifecycle; the ReactionSpec still
                # owns the actual event/action descriptor.  Normalize a
                # synthetic or alias event to the spec's event type so the
                # common scheduler matcher remains the only execution path.
                if event.type != clip.reaction.event_type:
                    event = _retag_event(event, clip.reaction.event_type)
                if event.source == "timeline" and event.frame != frame:
                    event = _reframe_event(event, frame)
                self.scheduler.process(
                    (event,),
                    frame,
                    context=context,
                    variables=variables,
                    scope_id=scope_id,
                    specs=(clip.reaction,),
                    clip_id=clip.clip_id,
                    owner_id=clip.owner_id,
                    trigger_kind=trigger_kind,
                    trigger_frame=trigger_frame,
                    activation_snapshot=snapshot,
                    action_resolver=action_resolver,
                )
        if advance_scheduler:
            self.scheduler.tick(frame)
        return tuple(self.scheduler.trace[before:])

    @property
    def active_instances(self) -> tuple[dict[str, Any], ...]:
        values = []
        for instance in self.scheduler.instances.values():
            values.append(
                {
                    "instance_id": instance.instance_id,
                    "clip_id": instance.clip_id,
                    "reaction_id": instance.spec.reaction_id,
                    "owner_id": instance.owner_id,
                    "started_frame": instance.started_frame,
                    "trigger_frame": instance.trigger_frame,
                    "event_type": instance.event.type,
                    "scope_id": instance.scope.scope_id,
                }
            )
        return tuple(sorted(values, key=lambda item: str(item["instance_id"])))

    @property
    def overlay(self) -> dict[str, Any]:
        return {
            "active_instances": [dict(item) for item in self.active_instances],
            "trace": [item.to_dict() for item in self.scheduler.trace[-50:]],
            "diagnostics": [dict(item) for item in self.scheduler.diagnostics[-50:]],
        }


def _activation_snapshot(
    rule: ActivationRule,
    event: Event | None,
    *,
    value: Any = None,
) -> dict[str, Any]:
    payload = {"rule": rule.to_dict()}
    if event is not None:
        payload.update(
            {
                "event_id": event.event_id,
                "event_type": event.type,
                "source": event.source,
                "frame": event.frame,
            }
        )
    if rule.kind == "when_variable":
        payload["value"] = _json_safe(value, path="activation.snapshot.value")
    return payload


def _synthetic_activation_event(
    clip: ReactiveClip,
    frame: int,
    *,
    payload: Mapping[str, Any] | None = None,
) -> Event:
    return Event(
        type=clip.reaction.event_type,
        source="timeline",
        frame=frame,
        payload=dict(payload or {"clip_id": clip.clip_id}),
        owner=clip.owner_id,
    )


def _retag_event(event: Event, event_type: str) -> Event:
    values = dict(
        type=event_type,
        source=event.source,
        frame=event.frame,
        payload=event.payload,
        owner=event.owner,
        causal_chain=event.causal_chain,
        schema_version=event.schema_version,
    )
    if isinstance(event, LifecycleEvent):
        return LifecycleEvent(
            **values,
            reason=event.reason,
            count=event.count,
            representative_ids=event.representative_ids,
        )
    return Event(**values)


def _reframe_event(event: Event, frame: int) -> Event:
    values = dict(
        type=event.type,
        source=event.source,
        frame=frame,
        payload=event.payload,
        owner=event.owner,
        causal_chain=event.causal_chain,
        schema_version=event.schema_version,
    )
    if isinstance(event, LifecycleEvent):
        return LifecycleEvent(
            **values,
            reason=event.reason,
            count=event.count,
            representative_ids=event.representative_ids,
        )
    return Event(**values)


def _read_activation_variable(variables: Any, rule: ActivationRule) -> Any:
    name = rule.variable_name
    if name is None:
        return None
    scope = None
    owner_id = None
    if isinstance(rule.variable, Mapping):
        scope = rule.variable.get("scope")
        owner_id = rule.variable.get("owner_id")
    if isinstance(variables, Mapping):
        if name in variables:
            return variables[name]
        if scope in variables and isinstance(variables[scope], Mapping):
            bucket = variables[scope]
            if owner_id in bucket and isinstance(bucket[owner_id], Mapping):
                return bucket[owner_id].get(name)
            return bucket.get(name)
        return None
    reader = getattr(variables, "read", None)
    if callable(reader):
        try:
            from src.authoring.variables import VariableRef

            return reader(
                VariableRef(name, scope=scope, owner_id=owner_id),
                owner_id=owner_id,
            )
        except Exception:  # noqa: BLE001 - inactive scopes evaluate false
            return None
    return None


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
    "ActivationRule",
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

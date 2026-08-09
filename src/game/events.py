"""Typed, frame-boundary runtime events.

The event layer is deliberately independent from Qt, renderers, and stage
objects.  Producers publish facts to an outbox.  A fixed-frame boundary moves
that outbox into the read-only inbox for the next frame; handlers are never
re-entered by an event they publish while the current inbox is dispatching.

``dispatch()`` keeps the old immediate test/adapter entry point for callers
that do not own a frame loop.  Formal runtime code should use
``dispatch_frame()`` or the explicit ``tick(); dispatch(strict=True)`` pair.
"""

from __future__ import annotations

import math
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


class EventBusError(RuntimeError):
    """Raised when an event contract is violated."""


def _json_value(value: Any, path: str = "payload") -> Any:
    """Return a detached JSON-compatible value or raise a typed error."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EventBusError(f"{path} must be finite")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise EventBusError(f"{path} keys must be strings")
            result[key] = _json_value(item, f"{path}.{key}")
        return result
    raise EventBusError(f"{path} contains unsupported type {type(value).__name__}")


def _validate_owner(owner: Any, path: str = "owner") -> str | None:
    if owner is None:
        return None
    if not isinstance(owner, str) or not owner.strip():
        raise EventBusError(f"{path} must be a non-empty string or null")
    return owner.strip()


def _validate_chain(chain: Iterable[str], path: str = "causal_chain") -> tuple[str, ...]:
    if isinstance(chain, (str, bytes)):
        raise EventBusError(f"{path} must be an array of event IDs")
    try:
        values = tuple(chain)
    except TypeError as exc:
        raise EventBusError(f"{path} must be an array of event IDs") from exc
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise EventBusError(f"{path}[{index}] must be a non-empty string")
    return tuple(value.strip() for value in values)


@dataclass(frozen=True)
class EventSpec:
    """Versioned descriptor for one event schema.

    ``density`` is part of the contract: sparse events may default to an
    ``each`` reaction policy, while batch events should normally be aggregated
    by count.  ``payload_fields`` is optional; when supplied it closes the
    object shape and rejects silently ignored fields.
    """

    type: str
    version: int = 1
    density: str = "sparse"
    payload_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not self.type.strip():
            raise EventBusError("event spec type must be a non-empty string")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise EventBusError("event spec version must be a positive integer")
        if self.density not in {"sparse", "batch"}:
            raise EventBusError("event spec density must be sparse or batch")
        if isinstance(self.payload_fields, (str, bytes)):
            raise EventBusError("event spec payload fields must be an array")
        fields = tuple(self.payload_fields)
        if any(not isinstance(item, str) or not item.strip() for item in fields):
            raise EventBusError("event spec payload fields must be non-empty strings")
        if len(set(fields)) != len(fields):
            raise EventBusError("event spec payload fields must be unique")
        object.__setattr__(self, "type", self.type.strip())
        object.__setattr__(self, "payload_fields", tuple(item.strip() for item in fields))

    def normalize(self, payload: Any) -> Any:
        value = _json_value(payload)
        if self.payload_fields:
            if not isinstance(value, dict):
                raise EventBusError(f"payload for {self.type} must be an object")
            unknown = set(value).difference(self.payload_fields)
            if unknown:
                raise EventBusError(
                    f"payload for {self.type} has unknown fields: {', '.join(sorted(unknown))}"
                )
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "version": self.version,
            "density": self.density,
            "payload_fields": list(self.payload_fields),
        }


@dataclass(frozen=True)
class Event:
    """Immutable sparse fact shared by adapters and runtime systems."""

    type: str
    source: str
    frame: int
    payload: Any = None
    owner: str | None = None
    causal_chain: tuple[str, ...] = ()
    schema_version: int = 1
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not self.type.strip():
            raise EventBusError("event type must be a non-empty string")
        if not isinstance(self.source, str) or not self.source.strip():
            raise EventBusError("event source must be a non-empty string")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise EventBusError("event frame must be a non-negative integer")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise EventBusError("event schema_version must be a positive integer")
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise EventBusError("event_id must be a non-empty string")
        object.__setattr__(self, "type", self.type.strip())
        object.__setattr__(self, "source", self.source.strip())
        object.__setattr__(self, "owner", _validate_owner(self.owner))
        object.__setattr__(self, "causal_chain", _validate_chain(self.causal_chain))
        object.__setattr__(self, "event_id", self.event_id.strip())
        object.__setattr__(self, "payload", _json_value(self.payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "source": self.source,
            "frame": self.frame,
            "payload": _json_value(self.payload),
            "owner": self.owner,
            "causal_chain": list(self.causal_chain),
            "schema_version": self.schema_version,
            "event_id": self.event_id,
        }


@dataclass(frozen=True)
class LifecycleEvent(Event):
    """A lifecycle fact with a batch-friendly count and termination reason."""

    reason: str | None = None
    count: int = 1
    representative_ids: tuple[str, ...] = ()
    density: str = "batch"

    def __post_init__(self) -> None:
        Event.__post_init__(self)
        if self.reason is not None and (not isinstance(self.reason, str) or not self.reason.strip()):
            raise EventBusError("lifecycle reason must be a non-empty string or null")
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 1:
            raise EventBusError("lifecycle count must be a positive integer")
        if self.density != "batch":
            raise EventBusError("lifecycle events must use batch density")
        values = _validate_chain(self.representative_ids, "representative_ids")
        object.__setattr__(self, "reason", self.reason.strip() if self.reason else None)
        object.__setattr__(self, "representative_ids", values)

    def to_dict(self) -> dict[str, Any]:
        value = super().to_dict()
        value.update(
            {
                "reason": self.reason,
                "count": self.count,
                "representative_ids": list(self.representative_ids),
                "density": self.density,
            }
        )
        return value


EventHandler = Callable[[Event], None]


@dataclass
class Subscription:
    bus: "EventBus"
    event_type: str
    handler: EventHandler
    order: int
    owner: str | None = None
    _cancelled: bool = field(default=False, init=False, repr=False)

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self.bus._cancel(self)


class EventBus:
    """Deterministic event queue with explicit frame boundaries."""

    def __init__(self, max_queue: int = 256, *, max_causal_depth: int = 32) -> None:
        self.max_queue = int(max_queue)
        if self.max_queue < 1:
            raise ValueError("max_queue must be positive")
        self.max_causal_depth = int(max_causal_depth)
        if self.max_causal_depth < 1:
            raise ValueError("max_causal_depth must be positive")
        self.frame = 0
        self.dropped = 0
        self.cancelled = 0
        self.errors: list[tuple[Event, Exception]] = []
        self._last_dispatched: tuple[Event, ...] = ()
        self._inbox: deque[Event] = deque()
        self._outbox: deque[Event] = deque()
        self._handlers: dict[str, list[Subscription]] = {}
        self._order = 0
        self._closed = False
        self._dispatching = False
        self._lock = threading.RLock()

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._inbox) + len(self._outbox)

    @property
    def inbox_pending(self) -> int:
        with self._lock:
            return len(self._inbox)

    @property
    def outbox_pending(self) -> int:
        with self._lock:
            return len(self._outbox)

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def last_dispatched(self) -> tuple[Event, ...]:
        return self._last_dispatched

    def tick(self) -> int:
        """Advance one fixed frame and publish the previous outbox to Inbox."""

        with self._lock:
            self.frame += 1
            self._promote_outbox_locked()
            return self.frame

    advance_frame = tick

    def emit(
        self,
        event_type: str,
        payload: Any = None,
        *,
        source: str = "runtime",
        owner: str | None = None,
        causal_chain: Iterable[str] = (),
        schema_version: int = 1,
        spec: EventSpec | None = None,
    ) -> Event:
        with self._lock:
            self._ensure_open()
            normalized = spec.normalize(payload) if spec is not None else _json_value(payload)
            if spec is not None:
                if event_type and event_type != spec.type:
                    raise EventBusError("event type does not match event spec")
                event_type = spec.type
                schema_version = spec.version
            chain = _validate_chain(causal_chain)
            if len(chain) > self.max_causal_depth:
                raise EventBusError(
                    f"causal_chain depth {len(chain)} exceeds max {self.max_causal_depth}"
                )
            event = Event(
                type=event_type,
                source=source,
                frame=self.frame,
                payload=normalized,
                owner=owner,
                causal_chain=chain,
                schema_version=schema_version,
            )
            self._enqueue_locked(event)
            return event

    def emit_lifecycle(
        self,
        event_type: str,
        payload: Any = None,
        *,
        source: str = "runtime",
        owner: str | None = None,
        reason: str | None = None,
        count: int = 1,
        representative_ids: Iterable[str] = (),
        causal_chain: Iterable[str] = (),
        schema_version: int = 1,
        spec: EventSpec | None = None,
    ) -> LifecycleEvent:
        with self._lock:
            self._ensure_open()
            normalized = spec.normalize(payload) if spec is not None else _json_value(payload)
            if spec is not None:
                if event_type and event_type != spec.type:
                    raise EventBusError("event type does not match event spec")
                event_type = spec.type
                schema_version = spec.version
                if spec.density != "batch":
                    raise EventBusError("lifecycle event spec must have batch density")
            chain = _validate_chain(causal_chain)
            if len(chain) > self.max_causal_depth:
                raise EventBusError(
                    f"causal_chain depth {len(chain)} exceeds max {self.max_causal_depth}"
                )
            event = LifecycleEvent(
                type=event_type,
                source=source,
                frame=self.frame,
                payload=normalized,
                owner=owner,
                causal_chain=chain,
                schema_version=schema_version,
                reason=reason,
                count=count,
                representative_ids=tuple(representative_ids),
            )
            self._enqueue_locked(event)
            return event

    publish = emit

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        *,
        owner: str | None = None,
    ) -> Subscription:
        with self._lock:
            if not isinstance(event_type, str) or (not event_type.strip() and event_type != "*"):
                raise EventBusError("subscription event type must be non-empty or '*'")
            if not callable(handler):
                raise EventBusError("handler must be callable")
            normalized_owner = _validate_owner(owner, "subscription owner")
            self._order += 1
            subscription = Subscription(
                bus=self,
                event_type=event_type.strip() if event_type != "*" else event_type,
                handler=handler,
                order=self._order,
                owner=normalized_owner,
            )
            self._handlers.setdefault(subscription.event_type, []).append(subscription)
            return subscription

    def _ensure_open(self) -> None:
        if self._closed:
            raise EventBusError("event bus is closed")

    def _promote_outbox_locked(self) -> None:
        while self._outbox:
            self._inbox.append(self._outbox.popleft())

    def _enqueue_locked(self, event: Event) -> None:
        self._outbox.append(event)
        while len(self._inbox) + len(self._outbox) > self.max_queue:
            if self._inbox:
                self._inbox.popleft()
            else:
                self._outbox.popleft()
            self.dropped += 1

    def _cancel(self, subscription: Subscription) -> None:
        with self._lock:
            subscriptions = self._handlers.get(subscription.event_type)
            if subscriptions is None:
                return
            self._handlers[subscription.event_type] = [
                item for item in subscriptions if item is not subscription
            ]

    def cancel_owner(self, owner: str) -> int:
        """Cancel subscriptions and pending facts owned by one scope."""

        normalized = _validate_owner(owner, "owner")
        assert normalized is not None
        with self._lock:
            removed = 0
            for subscriptions in self._handlers.values():
                for subscription in subscriptions:
                    if subscription.owner == normalized and not subscription._cancelled:
                        subscription._cancelled = True
                        removed += 1
            for queue in (self._inbox, self._outbox):
                kept = deque()
                while queue:
                    event = queue.popleft()
                    if event.owner == normalized:
                        removed += 1
                    else:
                        kept.append(event)
                queue.extend(kept)
            self.cancelled += removed
            return removed

    def drain_inbox(self) -> tuple[Event, ...]:
        """Remove and return the current Inbox without invoking handlers."""

        with self._lock:
            values = tuple(self._inbox)
            self._inbox.clear()
            return values

    def dispatch(self, *, strict: bool = False) -> int:
        """Dispatch a bounded Inbox snapshot in FIFO order.

        With ``strict=True`` only events already in Inbox are considered.  The
        compatibility default promotes an outbox when Inbox is empty, which
        preserves the historical ``emit(); dispatch()`` adapter/test pattern.
        In both modes, facts emitted by handlers remain for a later dispatch.
        """

        with self._lock:
            if self._closed:
                self._last_dispatched = ()
                return 0
            if not strict and not self._inbox and self._outbox and not self._dispatching:
                self._promote_outbox_locked()
            count = len(self._inbox)
            self._dispatching = True
        delivered: list[Event] = []
        try:
            for _ in range(count):
                with self._lock:
                    if self._closed or not self._inbox:
                        break
                    event = self._inbox.popleft()
                    handlers = tuple(self._handlers.get(event.type, ()))
                    wildcards = tuple(self._handlers.get("*", ()))
                delivered.append(event)
                self._deliver(event, handlers)
                self._deliver(event, wildcards)
            return count
        finally:
            with self._lock:
                self._dispatching = False
                self._last_dispatched = tuple(delivered)

    def dispatch_frame(self) -> int:
        """Advance one fixed frame, then dispatch only that frame's Inbox."""

        self.tick()
        return self.dispatch(strict=True)

    def _deliver(self, event: Event, handlers: tuple[Subscription, ...]) -> None:
        for subscription in handlers:
            if subscription._cancelled:
                continue
            try:
                subscription.handler(event)
            except Exception as exc:  # noqa: BLE001 - delivery is isolated
                with self._lock:
                    self.errors.append((event, exc))

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._inbox.clear()
            self._outbox.clear()


__all__ = [
    "Event",
    "EventBus",
    "EventBusError",
    "EventHandler",
    "EventSpec",
    "LifecycleEvent",
    "Subscription",
]

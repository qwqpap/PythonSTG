"""Main-thread typed runtime EventBus.

M7 frozen contract (see docs/EDITOR_ROADMAP_TODO.md):

- ``Event`` is a frozen dataclass with ``type``, ``source``, ``frame``, and
  ``payload``.
- ``EventBus(max_queue=256)`` holds a main-thread dispatch queue. ``tick()``
  advances the frame counter; ``emit`` only enqueues; ``dispatch()`` drains
  FIFO, invoking type subscribers in subscription order then ``"*"``
  subscribers in subscription order. Handler exceptions are recorded and
  isolated. Overflow drops the oldest event and increments ``dropped``.
  ``close()`` rejects further emits and disables dispatch (idempotent).
"""

from __future__ import annotations

import uuid
import math
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable


class EventBusError(RuntimeError):
    """Raised when an EventBus contract is violated."""


def _json_value(value: Any, path: str = "payload") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EventBusError(f"{path} must be finite")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise EventBusError(f"{path} keys must be strings")
            result[key] = _json_value(item, f"{path}.{key}")
        return result
    raise EventBusError(f"{path} contains unsupported type {type(value).__name__}")


@dataclass(frozen=True)
class Event:
    type: str
    source: str
    frame: int
    payload: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not self.type.strip():
            raise EventBusError("event type must be a non-empty string")
        if not isinstance(self.source, str) or not self.source.strip():
            raise EventBusError("event source must be a non-empty string")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise EventBusError("event frame must be a non-negative integer")
        _json_value(self.payload)


EventHandler = Callable[[Event], None]


@dataclass
class Subscription:
    bus: "EventBus"
    event_type: str
    handler: EventHandler
    order: int
    _cancelled: bool = field(default=False, init=False, repr=False)

    def cancel(self) -> None:
        self._cancelled = True
        self.bus._cancel(self)


class EventBus:
    """Typed, deterministic, main-thread event dispatch queue."""

    def __init__(self, max_queue: int = 256) -> None:
        self.max_queue = int(max_queue)
        if self.max_queue < 1:
            raise ValueError("max_queue must be positive")
        self.frame = 0
        self.pending = 0
        self.dropped = 0
        self.errors: list[tuple[Event, Exception]] = []
        self._queue: deque[Event] = deque()
        self._handlers: dict[str, list[Subscription]] = {}
        self._order = 0
        self._closed = False
        self._lock = threading.RLock()

    def tick(self) -> int:
        """Advance the frame counter; returns the new frame."""
        with self._lock:
            self.frame += 1
            return self.frame

    def emit(
        self,
        event_type: str,
        payload: Any = None,
        *,
        source: str = "runtime",
    ) -> Event:
        with self._lock:
            if self._closed:
                raise EventBusError("event bus is closed")
            event = Event(
                type=event_type,
                source=source,
                frame=self.frame,
                payload=payload,
            )
            self._queue.append(event)
            self.pending += 1
            if self.pending > self.max_queue:
                self._queue.popleft()
                self.pending -= 1
                self.dropped += 1
            return event

    def subscribe(self, event_type: str, handler: EventHandler) -> Subscription:
        with self._lock:
            if not isinstance(event_type, str) or (not event_type.strip() and event_type != "*"):
                raise EventBusError("subscription event type must be non-empty or '*'")
            if not callable(handler):
                raise EventBusError("handler must be callable")
            self._order += 1
            subscription = Subscription(
                bus=self,
                event_type=event_type,
                handler=handler,
                order=self._order,
            )
            self._handlers.setdefault(event_type, []).append(subscription)
            return subscription

    def _cancel(self, subscription: Subscription) -> None:
        with self._lock:
            subscriptions = self._handlers.get(subscription.event_type)
            if subscriptions is None:
                return
            self._handlers[subscription.event_type] = [
                item for item in subscriptions if item is not subscription
            ]

    def dispatch(self) -> int:
        """Drain the queue FIFO; returns the number of events dispatched."""
        count = 0
        while True:
            with self._lock:
                if self._closed or not self._queue:
                    return count
                event = self._queue.popleft()
                self.pending -= 1
                handlers = tuple(self._handlers.get(event.type, ()))
                wildcards = tuple(self._handlers.get("*", ()))
            count += 1
            for subscription in handlers:
                if subscription._cancelled:
                    continue
                try:
                    subscription.handler(event)
                except Exception as exc:  # noqa: BLE001 - isolated delivery
                    with self._lock:
                        self.errors.append((event, exc))
            for subscription in wildcards:
                if subscription._cancelled:
                    continue
                try:
                    subscription.handler(event)
                except Exception as exc:  # noqa: BLE001 - isolated delivery
                    with self._lock:
                        self.errors.append((event, exc))

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._queue.clear()
            self.pending = 0

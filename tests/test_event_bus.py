"""Typed runtime EventBus regression contract.

These tests preserve the currently shipped EventBus behavior. A future
frame-boundary migration is planned in ``docs/EDITOR_IMPLEMENTATION_TODO.md``.

Contract summary:
- ``src/game/events.py`` exposes ``Event``, ``EventBus``, ``Subscription``,
  and ``EventBusError``.
- ``Event`` is frozen with ``type``/``source``/``frame``/``payload``.
- ``emit`` only enqueues; ``dispatch`` drains FIFO in subscription order,
  then ``"*"`` wildcards; handler exceptions are recorded and isolated.
- Queue overflow drops the oldest event; ``close`` rejects further emits.
"""

import pytest

from src.game.events import Event, EventBus, EventBusError, Subscription


def test_event_carries_type_source_frame_and_payload():
    event = Event(type="player.died", source="boss", frame=120, payload={"phase": 2})

    assert event.type == "player.died"
    assert event.source == "boss"
    assert event.frame == 120
    assert event.payload == {"phase": 2}


def test_emit_enqueues_and_stamps_the_current_frame():
    bus = EventBus()
    bus.tick()
    bus.tick()

    event = bus.emit("shot.fired", payload={"x": 1.0}, source="player")

    assert event.frame == 2
    assert bus.frame == 2
    assert bus.pending == 1
    assert not event.payload is None


def test_dispatch_runs_handlers_in_fifo_and_subscription_order():
    bus = EventBus()
    calls = []

    def first(_event):
        calls.append("first")

    def second(_event):
        calls.append("second")

    bus.subscribe("a.b", first)
    bus.subscribe("a.b", second)
    bus.subscribe("*", lambda _event: calls.append("wild"))

    bus.emit("a.b")
    bus.emit("a.b")
    bus.dispatch()

    assert calls == ["first", "second", "wild", "first", "second", "wild"]
    assert bus.pending == 0


def test_handler_exception_is_recorded_and_isolated():
    bus = EventBus()
    calls = []

    def broken(_event):
        raise RuntimeError("handler blew up")

    def healthy(_event):
        calls.append("healthy")

    bus.subscribe("boom", broken)
    bus.subscribe("boom", healthy)
    bus.emit("boom")
    bus.dispatch()

    assert calls == ["healthy"]
    assert len(bus.errors) == 1
    event, error = bus.errors[0]
    assert event.type == "boom"
    assert "handler blew up" in str(error)
    assert bus.pending == 0


def test_subscription_cancel_stops_delivery():
    bus = EventBus()
    calls = []

    def handler(_event):
        calls.append("hit")

    subscription = bus.subscribe("tick", handler)
    bus.emit("tick")
    bus.dispatch()
    assert calls == ["hit"]

    subscription.cancel()
    bus.emit("tick")
    bus.dispatch()
    assert calls == ["hit"]


def test_duplicate_subscriptions_are_allowed():
    bus = EventBus()
    calls = []

    def handler(_event):
        calls.append("dup")

    bus.subscribe("x", handler)
    bus.subscribe("x", handler)
    bus.emit("x")
    bus.dispatch()

    assert calls == ["dup", "dup"]


def test_queue_overflow_drops_oldest_and_counts():
    bus = EventBus(max_queue=3)
    bus.subscribe("full", lambda _event: None)

    bus.emit("full", payload=1)
    bus.emit("full", payload=2)
    bus.emit("full", payload=3)
    bus.emit("full", payload=4)
    bus.emit("full", payload=5)

    assert bus.dropped == 2
    delivered = []
    bus.subscribe("full", lambda event: delivered.append(event.payload))
    bus.dispatch()

    assert delivered == [3, 4, 5]


def test_close_rejects_emit_and_disables_dispatch():
    bus = EventBus()
    calls = []

    def handler(_event):
        calls.append("hit")

    bus.subscribe("late", handler)
    bus.close()
    bus.close()

    with pytest.raises(EventBusError, match="closed"):
        bus.emit("late")

    bus.dispatch()
    assert calls == []
    assert bus.pending == 0


def test_event_is_immutable():
    event = Event(type="t", source="s", frame=0, payload={})

    with pytest.raises(Exception):
        event.type = "other"  # noqa: B018 - frozen dataclass must reject

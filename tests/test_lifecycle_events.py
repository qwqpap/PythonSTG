"""N3.0 contract tests for typed lifecycle facts and event ownership."""

import json

import pytest

from src.game.events import Event, EventBus, EventBusError, EventSpec, LifecycleEvent


def test_event_spec_and_lifecycle_event_round_trip_as_json_payloads():
    spec = EventSpec(
        "bullet.terminated",
        version=2,
        density="batch",
        payload_fields=("tag", "count"),
    )
    event = LifecycleEvent(
        type=spec.type,
        source="bullet_pool",
        frame=7,
        payload=spec.normalize({"tag": 12, "count": 32}),
        owner="12",
        reason="expired",
        count=32,
        representative_ids=("4", "9"),
        causal_chain=("root-event",),
        schema_version=spec.version,
    )

    encoded = json.dumps(event.to_dict(), ensure_ascii=False, allow_nan=False)
    decoded = json.loads(encoded)

    assert spec.to_dict() == {
        "type": "bullet.terminated",
        "version": 2,
        "density": "batch",
        "payload_fields": ["tag", "count"],
    }
    assert decoded["type"] == "bullet.terminated"
    assert decoded["schema_version"] == 2
    assert decoded["payload"] == {"tag": 12, "count": 32}
    assert decoded["reason"] == "expired"
    assert decoded["count"] == 32
    assert decoded["representative_ids"] == ["4", "9"]
    assert decoded["causal_chain"] == ["root-event"]


def test_event_spec_rejects_unknown_fields_and_non_json_values():
    spec = EventSpec("boss.hit", payload_fields=("boss_id",))

    with pytest.raises(EventBusError, match="unknown fields"):
        spec.normalize({"boss_id": "fake", "private": 1})
    with pytest.raises(EventBusError, match="finite"):
        Event(type="bad", source="test", frame=0, payload={"value": float("nan")})


def test_event_bus_emits_typed_lifecycle_facts_with_owner_and_causal_depth():
    bus = EventBus(max_causal_depth=2)
    event = bus.emit_lifecycle(
        "bullet.terminated",
        {"tag": 3, "count": 4},
        source="bullet_pool",
        owner="3",
        reason="hit_destroyed",
        count=4,
        representative_ids=("1", "2"),
        causal_chain=("boss-hit",),
    )

    assert isinstance(event, LifecycleEvent)
    assert event.owner == "3"
    assert event.reason == "hit_destroyed"
    assert event.count == 4
    assert bus.outbox_pending == 1

    with pytest.raises(EventBusError, match="causal_chain depth"):
        bus.emit("loop", causal_chain=("a", "b", "c"))


def test_cancel_owner_removes_owned_subscriptions_and_pending_facts():
    bus = EventBus()
    calls = []
    bus.subscribe("owned", lambda event: calls.append(event.payload), owner="state:old")
    bus.subscribe("kept", lambda event: calls.append(event.payload), owner="state:new")
    bus.emit("owned", 1, owner="state:old")
    bus.emit("kept", 2, owner="state:new")

    removed = bus.cancel_owner("state:old")
    assert removed == 2  # one subscription and one pending event

    bus.dispatch_frame()
    assert calls == [2]

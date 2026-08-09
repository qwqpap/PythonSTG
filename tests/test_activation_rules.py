"""N4.0 activation-rule contracts."""

import pytest

from src.game.events import Event, LifecycleEvent
from src.game.reactions import ActivationRule


def test_activation_rule_round_trips_json_and_rejects_unknown_fields():
    rule = ActivationRule(
        kind="on_event",
        event_type="boss.hit",
        source="boss",
        payload_filter={"target_tag": "fake"},
        delay_frames=3,
        scope="state",
    )
    payload = rule.to_dict()
    assert ActivationRule.from_dict(payload).to_dict() == payload
    with pytest.raises(ValueError, match="unknown"):
        ActivationRule.from_dict({"kind": "at_frame", "frame": 4, "future": True})


def test_activation_rule_validates_kind_fields_and_json_values():
    with pytest.raises(ValueError, match="kind"):
        ActivationRule(kind="unknown")
    with pytest.raises(ValueError, match="frame"):
        ActivationRule(kind="at_frame")
    with pytest.raises(ValueError, match="event_type"):
        ActivationRule(kind="on_event")
    with pytest.raises(ValueError, match="variable"):
        ActivationRule(kind="when_variable", operator="truthy")
    with pytest.raises(ValueError, match="operator"):
        ActivationRule(kind="when_variable", variable="armed", operator="between")
    with pytest.raises(ValueError, match="JSON"):
        ActivationRule(kind="on_event", event_type="hit", payload_filter={"x": object()})


def test_event_and_lifecycle_matching_are_fact_only():
    event_rule = ActivationRule(
        kind="on_event",
        event_type="boss.hit",
        source="boss",
        payload_filter={"target_tag": "fake"},
    )
    event = Event("boss.hit", "boss", 2, {"target_tag": "fake"})
    assert event_rule.match_event(event)
    assert not event_rule.match_event(Event("boss.hit", "player", 2, {"target_tag": "fake"}))

    lifecycle_rule = ActivationRule(
        kind="on_lifecycle",
        event_type="bullet.terminated",
        reason="expired",
    )
    assert lifecycle_rule.match_event(
        LifecycleEvent("bullet.terminated", "pool", 2, {}, reason="expired")
    )
    assert not lifecycle_rule.match_event(Event("bullet.terminated", "pool", 2, {}))


def test_variable_edges_have_deterministic_first_sample_semantics():
    rule = ActivationRule(
        kind="when_variable",
        variable="armed",
        operator="truthy",
        edge="on_rise",
    )
    memory = {}
    assert rule.match_variable(True, memory)
    assert not rule.match_variable(True, memory)
    assert not rule.match_variable(False, memory)
    assert rule.match_variable(True, memory)

    changed = ActivationRule(
        kind="when_variable", variable="value", operator="truthy", edge="on_change"
    )
    memory = {}
    assert not changed.match_variable(0, memory)
    assert changed.match_variable(1, memory)
    assert not changed.match_variable(1, memory)


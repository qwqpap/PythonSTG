"""N3.2 event matching and batch reaction policy contracts."""

from src.game.events import Event, LifecycleEvent
from src.game.reactions import ReactionScheduler, ReactionSpec


def _complete_action(callback):
    def action(event, scope):
        callback(event)
        scope.complete()

    return action


def _event(name="bullet.terminated", payload=None, *, frame=0, count=1, chain=()):
    if count != 1:
        return LifecycleEvent(
            type=name,
            source="bullet_pool",
            frame=frame,
            payload=payload or {"count": count},
            count=count,
            representative_ids=("1",),
            causal_chain=chain,
        )
    return Event(
        type=name,
        source="bullet_pool",
        frame=frame,
        payload=payload or {},
        causal_chain=chain,
    )


def test_each_first_count_and_debounce_have_observable_batch_semantics():
    events = [_event(payload={"id": 1}), _event(payload={"id": 2}), _event(payload={"id": 3})]
    seen = []

    def action(event, scope):
        seen.append((scope.scope_id, event.payload.get("id"), getattr(event, "count", 1)))
        scope.complete()

    scheduler = ReactionScheduler()
    scheduler.register(
        ReactionSpec(
            "each",
            "bullet.terminated",
            action,
            policy="each",
            reentry="parallel",
            once_per_scope=False,
            max_instances=4,
        )
    )
    scheduler.process(events, 0)
    scheduler.tick(0)
    assert [item[1] for item in seen] == [1, 2, 3]

    first = ReactionScheduler()
    first_seen = []
    first.register(
        ReactionSpec(
            "first",
            "bullet.terminated",
            _complete_action(lambda event: first_seen.append(event.payload["id"])),
            policy="first_per_frame",
            once_per_scope=False,
        )
    )
    first.process(events, 0)
    first.tick(0)
    assert first_seen == [1]

    counts = []
    counted = ReactionScheduler()
    counted.register(
        ReactionSpec(
            "count",
            "bullet.terminated",
            _complete_action(lambda event: counts.append(event.count)),
            policy="count_per_frame",
            once_per_scope=False,
        )
    )
    counted.process([_event(count=4), _event(count=3)], 5)
    counted.tick(5)
    assert counts == [7]

    debounce = ReactionScheduler()
    debounce_seen = []
    debounce.register(
        ReactionSpec(
            "debounce",
            "bullet.terminated",
            _complete_action(lambda event: debounce_seen.append(event.count)),
            policy="debounce",
            once_per_scope=False,
        )
    )
    debounce.process([_event(count=2), _event(count=5)], 8)
    debounce.tick(8)
    assert debounce_seen == [7]


def test_payload_filter_and_variable_guard_are_checked_before_start():
    seen = []
    scheduler = ReactionScheduler()
    scheduler.register(
        ReactionSpec(
            "fake-boss-overload",
            "boss.hit",
            _complete_action(lambda event: seen.append(event.payload["boss_id"])),
            payload_filter={"boss_id": "fake"},
            guard=lambda event, variables: bool(variables.get("armed")),
            once_per_scope=False,
        )
    )

    scheduler.process([_event("boss.hit", {"boss_id": "real"})], 0, variables={"armed": True})
    scheduler.process([_event("boss.hit", {"boss_id": "fake"})], 1, variables={"armed": False})
    scheduler.process([_event("boss.hit", {"boss_id": "fake"})], 2, variables={"armed": True})
    scheduler.tick(2)

    assert seen == ["fake"]


def test_once_per_scope_and_cooldown_are_visible_in_trace():
    scheduler = ReactionScheduler()
    scheduler.register(
        ReactionSpec(
            "once",
            "boss.defeated",
            _complete_action(lambda event: None),
            once_per_scope=True,
        )
    )
    scheduler.process([_event("boss.defeated")], 0)
    scheduler.tick(0)
    scheduler.process([_event("boss.defeated")], 1)
    assert any(item.reason == "once_per_scope" for item in scheduler.trace if item.kind == "suppress")

    cooldown = ReactionScheduler()
    cooldown.register(
        ReactionSpec(
            "cooldown",
            "boss.defeated",
            _complete_action(lambda event: None),
            once_per_scope=False,
            cooldown_frames=3,
        )
    )
    cooldown.process([_event("boss.defeated")], 0)
    cooldown.tick(0)
    cooldown.process([_event("boss.defeated")], 2)
    cooldown.process([_event("boss.defeated")], 3)
    assert any(item.reason == "cooldown" for item in cooldown.trace if item.kind == "suppress")
    assert len([item for item in cooldown.trace if item.kind == "start"]) == 2

"""N3.2 reentry, cancellation, budgets, and causal-depth diagnostics."""

from src.game.events import Event, EventBus
from src.game.reactions import ReactionScheduler, ReactionSpec, TaskWait


def _event(frame=0, chain=()):
    return Event(type="pulse", source="test", frame=frame, payload={}, causal_chain=chain)


def _waiting_action(log):
    def action(event, scope):
        log.append(("start", event.frame))
        yield TaskWait(4)
        log.append(("done", event.frame))

    return action


def test_ignore_restart_and_parallel_reentry_policies():
    ignored_log = []
    ignored = ReactionScheduler()
    ignored.register(
        ReactionSpec(
            "ignore",
            "pulse",
            _waiting_action(ignored_log),
            once_per_scope=False,
            reentry="ignore_while_running",
            max_instances=1,
        )
    )
    ignored.process([_event()], 0)
    ignored.tick(0)
    ignored.process([_event(1)], 1)
    assert len([item for item in ignored.trace if item.kind == "start"]) == 1
    assert any(item.reason == "ignore_while_running" for item in ignored.trace if item.kind == "suppress")

    restart_log = []
    restarted = ReactionScheduler()
    restarted.register(
        ReactionSpec(
            "restart",
            "pulse",
            _waiting_action(restart_log),
            once_per_scope=False,
            reentry="restart",
            max_instances=1,
        )
    )
    restarted.process([_event()], 0)
    restarted.tick(0)
    restarted.process([_event(1)], 1)
    restarted.tick(1)
    assert len([item for item in restarted.trace if item.kind == "start"]) == 2
    assert any(item.reason == "replaced" for item in restarted.trace if item.kind == "cancel")

    parallel_log = []
    parallel = ReactionScheduler()
    parallel.register(
        ReactionSpec(
            "parallel",
            "pulse",
            _waiting_action(parallel_log),
            once_per_scope=False,
            reentry="parallel",
            max_instances=2,
        )
    )
    parallel.process([_event(), _event(), _event()], 0)
    parallel.tick(0)
    assert len([item for item in parallel.trace if item.kind == "start"]) == 2
    assert any(item.reason == "max_instances" for item in parallel.trace if item.kind == "suppress")


def test_max_instance_budget_and_causal_depth_suppress_deterministically():
    scheduler = ReactionScheduler(max_causal_depth=2, max_instances_per_frame=1)
    scheduler.register(
        ReactionSpec(
            "bounded",
            "pulse",
            lambda: None,
            once_per_scope=False,
            reentry="parallel",
            max_instances=4,
        )
    )

    scheduler.process([_event(chain=("a", "b", "c")), _event(), _event()], 0)
    reasons = [item.reason for item in scheduler.trace if item.kind == "suppress"]
    assert "causal_depth" in reasons
    assert "frame_instance_budget" in reasons


def test_event_bus_binding_queues_events_until_scheduler_processes_them():
    bus = EventBus()
    scheduler = ReactionScheduler(event_bus=bus)
    seen = []
    scheduler.register(
        ReactionSpec(
            "input",
            "input",
            lambda event, scope: seen.append(event.payload["value"]),
            once_per_scope=False,
        )
    )

    bus.emit("input", {"value": 9})
    assert scheduler.process_pending(0) == ()
    bus.dispatch_frame()
    scheduler.process_pending(1)
    scheduler.tick(1)

    assert seen == [9]


def test_owner_cancellation_removes_pending_instances_and_allows_new_scope_generation():
    log = []
    scheduler = ReactionScheduler()
    scheduler.register(
        ReactionSpec(
            "owned",
            "pulse",
            _waiting_action(log),
            once_per_scope=True,
        )
    )
    scheduler.process([_event()], 0, scope_id="state:old")
    scheduler.tick(0)
    assert scheduler.instances
    assert scheduler.cancel_owner("state:old", frame=2) == 1
    assert scheduler.instances == {}
    assert any(item.kind == "cancel" and item.reason == "owner_cancelled" for item in scheduler.trace)

"""N4.0 reactive timeline activation and cancellation contracts."""

from src.game.events import Event, LifecycleEvent
from src.game.reactions import (
    ActivationRule,
    ReactionSpec,
    ReactiveClip,
    ReactiveTimeline,
    TaskWait,
)


def test_at_frame_and_dynamic_delay_start_at_the_due_frame():
    starts = []

    def action(event, scope):
        starts.append((scope.scope_id, event.frame))
        scope.complete()

    clip = ReactiveClip(
        "frame-hook",
        ReactionSpec("frame-reaction", "timeline.activation", action, once_per_scope=False),
        start_frame=0,
        end_frame=10,
        activation=ActivationRule(kind="at_frame", frame=2, delay_frames=2),
    )
    timeline = ReactiveTimeline((clip,))
    for frame in range(5):
        timeline.tick("state", frame)
    assert starts == [("frame-hook@state:state#1#1", 4)]
    trace = [item for item in timeline.scheduler.trace if item.kind == "start"]
    assert trace[0].clip_id == "frame-hook"
    assert trace[0].trigger_kind == "at_frame"
    assert trace[0].trigger_frame == 2


def test_variable_rule_and_event_rule_can_share_reaction_id_without_cross_talk():
    seen = []

    def action(event, scope):
        seen.append(event.type)
        scope.complete()

    reaction = ReactionSpec("shared", "boss.hit", action, once_per_scope=False)
    event_clip = ReactiveClip(
        "event-clip", reaction, activation=ActivationRule(kind="on_event", event_type="boss.hit")
    )
    variable_clip = ReactiveClip(
        "variable-clip",
        reaction,
        activation=ActivationRule(
            kind="when_variable", variable="armed", operator="truthy", edge="on_rise"
        ),
    )
    timeline = ReactiveTimeline((event_clip, variable_clip))
    timeline.tick("state", 0, [Event("boss.hit", "boss", 0, {})], variables={"armed": False})
    timeline.tick("state", 1, variables={"armed": True})
    assert seen == ["boss.hit", "boss.hit"]
    starts = [item for item in timeline.scheduler.trace if item.kind == "start"]
    assert {item.clip_id for item in starts} == {"event-clip", "variable-clip"}


def test_clip_window_and_state_exit_cancel_pending_and_running_work():
    log = []

    def action(event, scope):
        log.append("start")
        yield TaskWait(20)
        log.append("done")

    clip = ReactiveClip(
        "window",
        ReactionSpec("window-reaction", "pulse", action, once_per_scope=False),
        start_frame=0,
        end_frame=3,
        activation=ActivationRule(kind="on_event", event_type="pulse", delay_frames=4),
    )
    timeline = ReactiveTimeline((clip,))
    timeline.tick("state", 0, [Event("pulse", "test", 0, {})])
    timeline.tick("state", 3)
    timeline.tick("state", 4)
    assert log == []
    assert any(item.reason == "clip_window_end" for item in timeline.scheduler.trace)

    immediate = ReactiveClip(
        "running",
        ReactionSpec("running-reaction", "pulse", action, once_per_scope=False),
        start_frame=0,
        end_frame=10,
    )
    timeline = ReactiveTimeline((immediate,))
    timeline.tick("state", 0, [Event("pulse", "test", 0, {})])
    timeline.exit_state("state", frame=1)
    assert any(item.reason == "state_exit" for item in timeline.scheduler.trace)


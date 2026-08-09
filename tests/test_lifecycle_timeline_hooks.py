"""Timeline lifecycle slots and State/Clip ownership integration examples."""

from src.game.events import Event, EventBus, LifecycleEvent
from src.game.reactions import ReactionScheduler, ReactionSpec, ReactiveClip, ReactiveTimeline, TaskWait
from src.game.stage.program import (
    StageProgram,
    StageRunner,
    StageState,
    StageStateGraph,
    StageTransition,
)


def _lifecycle(event_type, *, frame=0, reason=None, count=1, payload=None):
    return LifecycleEvent(
        type=event_type,
        source="runtime",
        frame=frame,
        payload=payload or {},
        reason=reason,
        count=count,
        representative_ids=("bullet-1",),
    )


def test_death_bloom_reaction_is_a_timeline_slot_not_a_blueprint_to_timeline_wire():
    blooms = []

    def bloom(event, scope):
        blooms.append((event.reason, event.count))
        scope.complete()

    clip = ReactiveClip(
        "death-bloom",
        ReactionSpec(
            "on-death-bloom",
            "bullet.terminated",
            bloom,
            guard=lambda event: event.reason == "expired",
            once_per_scope=False,
        ),
        state_id="normal",
        start_frame=0,
        end_frame=20,
    )
    timeline = ReactiveTimeline((clip,))
    timeline.enter_state("normal")
    timeline.tick("normal", 3, [_lifecycle("bullet.terminated", reason="expired", count=6)])

    assert blooms == [("expired", 6)]
    assert clip.state_id == "normal"
    assert clip.reaction.trigger == "bullet.terminated"


def test_clip_window_end_cancels_a_running_reaction_with_structured_reason():
    log = []

    def long_action(event, scope):
        log.append("start")
        yield TaskWait(20)
        log.append("done")

    clip = ReactiveClip(
        "short-window",
        ReactionSpec(
            "short-reaction",
            "pulse",
            long_action,
            once_per_scope=False,
            reentry="ignore_while_running",
        ),
        state_id="state",
        start_frame=0,
        end_frame=2,
    )
    timeline = ReactiveTimeline((clip,))
    timeline.enter_state("state")
    timeline.tick("state", 0, [Event("pulse", "test", 0, {})])
    timeline.tick("state", 1)
    timeline.tick("state", 2)

    assert log == ["start"]
    cancellations = [item for item in timeline.scheduler.trace if item.kind == "cancel"]
    assert cancellations and cancellations[-1].reason == "clip_window_end"


def test_state_exit_has_priority_over_old_state_reaction_in_formal_stage_runner():
    bus = EventBus()
    log = []

    def action(event, scope):
        log.append("started")
        yield TaskWait(20)
        log.append("completed")

    clips = (
        ReactiveClip(
            "old-hook",
            ReactionSpec("old-reaction", "boss.hit", action, once_per_scope=False),
            state_id="old",
            start_frame=0,
            end_frame=20,
        ),
    )
    graph = StageStateGraph(
        graph_id="graph",
        name="Graph",
        initial_state_id="old",
        states=(
            StageState(
                "old",
                "Old",
                duration_frames=10,
                entry_actions=(),
                exit_actions=(),
                transitions=(
                    StageTransition("to-new", "old", "new", "after", 2, 0, 0),
                ),
            ),
            StageState("new", "New", 10, (), (), ()),
        ),
    )
    program = StageProgram(
        resource_id="stage:test-reactions",
        schema_version=1,
        content_hash="hash",
        name="Reaction Stage",
        tick_rate=60,
        duration_frames=30,
        nodes=(),
        patterns=(),
        automations=(),
        actions=(),
        state_graph=graph,
        reactive_clips=clips,
    )

    class Context:
        event_bus = bus

        def clear_authored_stage_state(self):
            pass

    context = Context()
    runner = StageRunner(program)
    runner.start(context)
    bus.emit("boss.hit", {"boss": "fake"}, source="boss")
    runner.tick(context)
    runner.tick(context)

    assert log == ["started"]
    assert runner.current_state_path == ("new",)
    trace = runner.reactive_timeline.scheduler.trace
    assert any(item.kind == "cancel" and item.reason == "state_exit" for item in trace)

"""N4.0 runtime identity, owner, and budget diagnostics."""

from src.game.events import Event
from src.game.reactions import ReactionScheduler, ReactionSpec, ReactiveClip, ReactiveTimeline


def test_trace_separates_author_clip_from_runtime_instance_and_owner():
    scheduler = ReactionScheduler()
    clip = ReactiveClip(
        "author-clip",
        ReactionSpec(
            "reaction",
            "pulse",
            lambda event, scope: scope.complete(),
            once_per_scope=False,
        ),
        owner_id="boss.fake",
    )
    timeline = ReactiveTimeline((clip,), scheduler=scheduler)
    timeline.tick("state", 7, [Event("pulse", "boss", 7, {})])
    trace = next(item for item in scheduler.trace if item.kind == "start")
    assert trace.clip_id == "author-clip"
    assert trace.owner_id == "boss.fake"
    assert trace.instance_id != trace.clip_id
    assert trace.started_frame == 7


def test_frame_budget_and_causal_depth_are_structured_diagnostics():
    scheduler = ReactionScheduler(max_instances_per_frame=1, max_causal_depth=1)
    scheduler.register(
        ReactionSpec(
            "bounded", "pulse", lambda: None, once_per_scope=False,
            reentry="parallel", max_instances=4,
        )
    )
    scheduler.process(
        [
            Event("pulse", "test", 0, {}, causal_chain=("root", "child")),
            Event("pulse", "test", 0, {}),
            Event("pulse", "test", 0, {}),
        ],
        0,
    )
    reasons = [item.reason for item in scheduler.trace if item.kind == "suppress"]
    assert reasons == ["causal_depth", "frame_instance_budget"]
    assert scheduler.diagnostics[-1]["reason"] == "frame_instance_budget"


def test_reset_replay_reuses_generation_but_new_runtime_instance_ids():
    scheduler = ReactionScheduler()
    scheduler.register(
        ReactionSpec("pulse", "pulse", lambda event, scope: scope.complete(), once_per_scope=False)
    )
    scheduler.process([Event("pulse", "test", 0, {})], 0, scope_id="state:one")
    first = next(item.instance_id for item in scheduler.trace if item.kind == "start")
    scheduler.reset()
    scheduler.process([Event("pulse", "test", 0, {})], 0, scope_id="state:one")
    second = [item.instance_id for item in scheduler.trace if item.kind == "start"][-1]
    assert first != second

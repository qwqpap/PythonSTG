"""N4.1 formal SceneDocument -> compiler -> StageRunner integration."""

from copy import deepcopy

import pytest

from src.core.project_context import ProjectContext
from src.editor import SceneEditorSession, TimelineClip, TimelineTrack
from src.authoring.scene.document import DocumentError
from src.compiler.stage import StageCompileError, compile_stage
from src.game.events import EventBus
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext


class DummyPlayer:
    pos = [0.0, -0.75]


def _scene(payload, *, validate=True):
    scene = SceneEditorSession.new_document("Reactive stage")
    state = scene.state_graph.find_state(scene.state_graph.initial_state_id)
    state.duration_frames = 12
    state.tracks.append(
        TimelineTrack(
            name="Reactive hooks",
            kind="Reactive",
            channel="reaction",
            clips=[
                TimelineClip(
                    name="Fake boss overload",
                    kind="Reactive",
                    start_frame=0,
                    duration_frames=10,
                    channel="reaction",
                    payload=payload,
                )
            ],
        )
    )
    scene.metadata["duration_frames"] = 12
    if validate:
        scene.validate()
    return scene


def test_reactive_clip_compiles_and_runs_through_formal_stage_runner(tmp_path):
    payload = {
        "activation": {
            "kind": "on_event",
            "event_type": "boss.hit",
            "source": "boss",
            "payload_filter": {"target_tag": "fake"},
        },
        "reaction": {
            "id": "fake-overload",
            "event_type": "boss.hit",
            "once_per_scope": False,
            "action": "spawn-overload",
        },
        "owner_id": "boss.fake",
    }
    scene = _scene(payload)
    canonical = deepcopy(scene.to_canonical_dict())
    program = compile_stage(ProjectContext(tmp_path), scene)
    assert len(program.reactive_clips) == 1
    assert scene.to_canonical_dict() == canonical

    bus = EventBus()
    context = StageContext(OptimizedBulletPool(max_bullets=64), DummyPlayer(), event_bus=bus)
    seen = []

    def overload(event, scope):
        seen.append((event.payload["target_tag"], scope.owner_id))
        scope.complete()

    context.register_reaction_action("spawn-overload", overload)
    from src.game.stage.program import StageRunner

    runner = StageRunner(program)
    runner.start(context)
    bus.emit("boss.hit", {"target_tag": "fake"}, source="boss")
    runner.tick(context)
    # EventBus facts emitted before the tick are dispatched at the fixed
    # boundary and are consumed by the same formal runtime path.
    assert seen == [("fake", "boss.fake")]
    assert runner.reactive_trace[0].clip_id == program.reactive_clips[0].clip_id
    assert runner.reactive_overlay["trace"]


def test_reactive_payload_diagnostic_points_to_nested_authoring_path(tmp_path):
    scene = _scene(
        {
            "activation": {"kind": "when_variable", "operator": "truthy"},
            "reaction": {"id": "broken", "event_type": "pulse"},
        }
        , validate=False)
    with pytest.raises(DocumentError, match="variable"):
        scene.validate()

    scene = _scene(
        {
            "activation": {"kind": "on_event", "event_type": "pulse"},
            "reaction": {"id": "broken", "event_type": "pulse", "future": True},
        }, validate=False
    )
    with pytest.raises(DocumentError, match="unknown"):
        scene.validate()

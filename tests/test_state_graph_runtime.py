"""N1 contract: StateGraph compiles into and runs through formal StageProgram."""

from __future__ import annotations

from copy import deepcopy

from src.core.project_context import ProjectContext
from src.editor import (
    SceneEditorSession,
    StateActionSpec,
    StateGraphSpec,
    StateSpec,
    TimelineClip,
    TimelineTrack,
    TransitionSpec,
)
from src.editor.stage_compile import StageCompileError, compile_stage
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.game.stage.program import StageRunner, StageRunnerState
from src.preview.controller import PatternPreviewController


class DummyPlayer:
    pos = [0.0, -0.75]


def _context() -> StageContext:
    return StageContext(OptimizedBulletPool(max_bullets=64), DummyPlayer())


def _event_action(event_type: str) -> StateActionSpec:
    return StateActionSpec(
        name=event_type,
        kind="Event",
        channel="state",
        payload={"event_type": event_type, "data": {}},
    )


def _event_clip(event_type: str, frame: int = 0) -> TimelineClip:
    return TimelineClip(
        name=event_type,
        kind="Event",
        start_frame=frame,
        duration_frames=1,
        channel="state",
        payload={"event_type": event_type, "data": {}},
    )


def _event_names(context: StageContext) -> list[str]:
    return [str(item["type"]) for item in context.timeline_events()]


def _hierarchical_scene():
    scene = SceneEditorSession.new_document("State Runtime")
    intro = StateSpec(
        name="Intro",
        duration_frames=2,
        entry_actions=[_event_action("intro.enter")],
        exit_actions=[_event_action("intro.exit")],
        tracks=[
            TimelineTrack(
                name="Intro events",
                kind="Event",
                channel="state",
                clips=[_event_clip("intro.frame_one", frame=1)],
            )
        ],
    )
    phase_a = StateSpec(
        name="Phase A",
        duration_frames=1,
        entry_actions=[_event_action("phase_a.enter")],
        exit_actions=[_event_action("phase_a.exit")],
    )
    phase_b = StateSpec(
        name="Phase B",
        duration_frames=1,
        entry_actions=[_event_action("phase_b.enter")],
        exit_actions=[_event_action("phase_b.exit")],
    )
    phase_a.transitions.append(
        TransitionSpec(
            name="A to B",
            target_state_id=phase_b.id,
            trigger="after",
            after_frames=1,
        )
    )
    boss = StateSpec(
        name="Boss",
        duration_frames=0,
        entry_actions=[_event_action("boss.enter")],
        exit_actions=[_event_action("boss.exit")],
        child_graph=StateGraphSpec(
            name="PhaseFlow",
            initial_state_id=phase_a.id,
            states=[phase_a, phase_b],
        ),
    )
    end = StateSpec(
        name="End",
        duration_frames=1,
        entry_actions=[_event_action("end.enter")],
        exit_actions=[_event_action("end.exit")],
    )
    intro.transitions.append(
        TransitionSpec(
            name="Intro timer",
            target_state_id=boss.id,
            trigger="after",
            after_frames=2,
        )
    )
    boss.transitions.append(
        TransitionSpec(
            name="Phases complete",
            target_state_id=end.id,
            trigger="complete",
        )
    )
    scene.state_graph = StateGraphSpec(
        name="StageFlow",
        initial_state_id=intro.id,
        states=[intro, boss, end],
    )
    scene.metadata["duration_frames"] = 30
    scene.validate()
    return scene, intro, boss, phase_a, phase_b, end


def test_time_and_completion_transitions_use_local_frames_and_nested_initial_state(
    tmp_path,
):
    scene, intro, boss, phase_a, phase_b, end = _hierarchical_scene()
    program = compile_stage(ProjectContext(tmp_path), scene)
    context = _context()
    runner = StageRunner(program)

    runner.start(context)
    assert runner.current_state_path == (intro.id,)
    assert runner.current_state_names == ("Intro",)
    assert _event_names(context) == ["intro.enter"]

    runner.tick(context)  # Intro local frame 0
    assert runner.current_state_path == (intro.id,)
    runner.tick(context)  # Intro local frame 1, then after_frames=2
    assert runner.current_state_path == (boss.id, phase_a.id)
    assert _event_names(context) == [
        "intro.enter",
        "intro.frame_one",
        "intro.exit",
        "boss.enter",
        "phase_a.enter",
    ]

    runner.tick(context)  # Phase A completes and transitions to Phase B
    assert runner.current_state_path == (boss.id, phase_b.id)
    runner.tick(context)  # terminal Phase B completes, then parent on_complete fires
    assert runner.current_state_path == (end.id,)
    assert _event_names(context)[-5:] == [
        "phase_a.exit",
        "phase_b.enter",
        "phase_b.exit",
        "boss.exit",
        "end.enter",
    ]

    runner.tick(context)
    assert runner.state == StageRunnerState.FINISHED
    assert runner.current_state_path == ()
    assert _event_names(context)[-1] == "end.exit"


def test_parent_time_transition_cancels_child_subtree_before_parent_exit(tmp_path):
    scene = SceneEditorSession.new_document("Cancellation")
    child = StateSpec(
        name="Long child",
        duration_frames=20,
        entry_actions=[_event_action("child.enter")],
        exit_actions=[_event_action("child.exit")],
        tracks=[
            TimelineTrack(
                name="Late event",
                kind="Event",
                channel="state",
                clips=[_event_clip("child.must_not_run", frame=2)],
            )
        ],
    )
    parent = StateSpec(
        name="Parent",
        duration_frames=0,
        exit_actions=[_event_action("parent.exit")],
        child_graph=StateGraphSpec(
            name="PhaseFlow",
            initial_state_id=child.id,
            states=[child],
        ),
    )
    next_state = StateSpec(name="Next", duration_frames=5)
    parent.transitions.append(
        TransitionSpec(
            name="Cancel subtree",
            target_state_id=next_state.id,
            trigger="after",
            after_frames=1,
        )
    )
    scene.state_graph = StateGraphSpec(
        name="StageFlow",
        initial_state_id=parent.id,
        states=[parent, next_state],
    )
    scene.metadata["duration_frames"] = 30
    context = _context()
    runner = StageRunner(compile_stage(ProjectContext(tmp_path), scene))

    runner.start(context)
    runner.tick(context)

    assert runner.current_state_path == (next_state.id,)
    assert _event_names(context) == [
        "child.enter",
        "child.exit",
        "parent.exit",
    ]
    runner.advance(context, 3)
    assert "child.must_not_run" not in _event_names(context)


def test_reset_replay_restores_same_state_path_trace_and_entry_exit_order(tmp_path):
    scene, _intro, _boss, _phase_a, _phase_b, _end = _hierarchical_scene()
    program = compile_stage(ProjectContext(tmp_path), scene)
    context = _context()
    runner = StageRunner(program)

    runner.start(context)
    runner.advance(context, 4)
    first_trace = tuple(runner.trace)
    first_path = runner.current_state_path
    first_events = tuple(context.timeline_events())

    runner.reset(context)
    assert runner.current_state_path == ()
    runner.start(context, reset=False)
    runner.advance(context, 4)

    assert tuple(runner.trace) == first_trace
    assert runner.current_state_path == first_path
    assert tuple(context.timeline_events()) == first_events


def test_preview_stats_report_runtime_state_path_without_mutating_authoring(tmp_path):
    project = ProjectContext(tmp_path)
    scene, intro, boss, phase_a, _phase_b, _end = _hierarchical_scene()
    before = deepcopy(scene.to_dict())
    controller = PatternPreviewController(
        OptimizedBulletPool(max_bullets=64),
        project=project,
    )

    controller.load(scene.to_dict())
    controller.play()
    controller.update()
    first = controller.get_stats(emit=False)
    controller.update()
    second = controller.get_stats(emit=False)

    assert first["state_path"] == [intro.id]
    assert first["state_path_names"] == ["Intro"]
    assert second["state_path"] == [boss.id, phase_a.id]
    assert second["state_path_names"] == ["Boss", "Phase A"]
    assert scene.to_dict() == before
    assert controller.document.to_dict() == before


def test_compile_diagnostic_identifies_state_track_clip_and_property_path(tmp_path):
    scene, intro, _boss, _phase_a, _phase_b, _end = _hierarchical_scene()
    broken = TimelineClip(
        name="Missing pattern",
        kind="Pattern",
        start_frame=0,
        duration_frames=1,
        channel="danmaku",
        payload={"pattern": "res://missing.pystg.json"},
    )
    track = TimelineTrack(
        name="Broken",
        kind="Pattern",
        channel="danmaku",
        clips=[broken],
    )
    intro.tracks.append(track)

    try:
        compile_stage(ProjectContext(tmp_path), scene)
    except StageCompileError as exc:
        diagnostic = exc.diagnostics[0]
    else:
        raise AssertionError("invalid state-local Pattern must fail compilation")

    assert diagnostic.state_id == intro.id
    assert diagnostic.track_id == track.id
    assert diagnostic.clip_id == broken.id
    assert f"state_graph.states.{intro.id}.tracks.{track.id}" in diagnostic.path

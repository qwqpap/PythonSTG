"""N2.7 deterministic variable seek contracts."""

from __future__ import annotations

from src.authoring.variables import VariableSpec
from src.core.project_context import ProjectContext
from src.editor import SceneEditorSession, StateActionSpec, TimelineClip, TimelineTrack
from src.editor.stage_compile import compile_stage
from src.game.stage.program import StageRunner


def _program(tmp_path):
    scene = SceneEditorSession.new_document("Seek")
    scene.variables.append(VariableSpec("rank", "int", 1, writable_by=("safe_action", "timeline"), animatable=True))
    state = scene.state_graph.initial_state
    state.entry_actions.append(
        StateActionSpec(
            name="Initial rank", kind="Variable", channel="variables",
            payload={"variable": {"name": "rank", "scope": "stage"}, "operation": "add", "value": 1},
        )
    )
    state.tracks.append(
        TimelineTrack(
            name="Writes", kind="Variable", channel="variables",
            clips=[TimelineClip(
                name="Frame 2", kind="Variable", channel="variables", start_frame=2,
                duration_frames=1, payload={"variable": {"name": "rank", "scope": "stage"}, "value": 5},
            )],
        )
    )
    state.duration_frames = 8
    return compile_stage(ProjectContext(tmp_path), scene)


def test_stage_seek_replays_variable_actions_even_when_external_dispatch_is_disabled(tmp_path):
    program = _program(tmp_path)
    normal = StageRunner(program)
    normal.start()
    normal.advance(object(), 5)

    replay = StageRunner(program)
    replay.seek(object(), 5, dispatch_actions=False)

    assert replay.frame == normal.frame == 5
    assert replay.read_variable("rank") == normal.read_variable("rank") == 5
    assert [(item.frame, item.kind, item.value) for item in replay.trace] == [
        (item.frame, item.kind, item.value) for item in normal.trace
    ]
    assert replay.replay_identity["actual_trigger_frames"] == [item.frame for item in replay.trace]


def test_state_and_clip_seek_replay_through_the_same_formal_runner(tmp_path):
    program = _program(tmp_path)
    state_id = program.state_graph.initial_state_id
    clip_id = program.variable_automations[0].clip_id
    runner = StageRunner(program)

    state_results = runner.seek_state(object(), state_id, 2)
    assert len(state_results) == 2
    assert runner.current_state_path == (state_id,)
    assert runner.frame == 2
    assert clip_id in runner.active_clip_ids

    clip_results = runner.reset_clip(object(), clip_id)
    assert len(clip_results) == 2
    assert runner.current_state_path == (state_id,)
    assert clip_id in runner.active_clip_ids

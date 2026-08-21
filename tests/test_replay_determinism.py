"""N2.7 replay identity and fixed-tick determinism contracts."""

from __future__ import annotations

from src.authoring.variables import VariableSpec
from src.core.project_context import ProjectContext
from src.editor import SceneEditorSession, StateActionSpec, TimelineClip, TimelineTrack
from src.compiler.stage import compile_stage
from src.game.stage.program import StageRunner


def _program(tmp_path):
    scene = SceneEditorSession.new_document("Replay")
    scene.variables.append(VariableSpec("rank", "int", 1, writable_by=("safe_action", "timeline"), animatable=True))
    state = scene.state_graph.initial_state
    state.entry_actions.append(StateActionSpec(name="Initial", kind="Variable", channel="variables", payload={"variable": {"name": "rank", "scope": "stage"}, "operation": "add", "value": 1}))
    state.tracks.append(TimelineTrack(name="Writes", kind="Variable", channel="variables", clips=[TimelineClip(name="Frame", kind="Variable", channel="variables", start_frame=2, duration_frames=1, payload={"variable": {"name": "rank", "scope": "stage"}, "value": 5})]))
    state.duration_frames = 8
    return compile_stage(ProjectContext(tmp_path), scene)


def test_reset_and_seek_have_identical_trace_and_replay_identity(tmp_path):
    program = _program(tmp_path)
    first = StageRunner(program)
    first.start()
    first.advance(object(), 5)

    second = StageRunner(program)
    second.seek(object(), 5)

    assert first.frame == second.frame
    assert [(item.frame, item.kind, item.value) for item in first.trace] == [
        (item.frame, item.kind, item.value) for item in second.trace
    ]
    assert first.replay_identity["program_hash"] == second.replay_identity["program_hash"]
    assert second.replay_identity["initial_variables"] == first.replay_identity["initial_variables"]

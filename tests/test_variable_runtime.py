"""N2.0 runtime contract for scope ownership and explicit write capabilities."""

from __future__ import annotations

import pytest

from src.authoring.variables import VariableError, VariableRef, VariableSpec, VariableStore


def _store() -> VariableStore:
    return VariableStore(
        (
            VariableSpec("rank", "float", 1.0, scope="stage", writable_by=("safe_action",)),
            VariableSpec("enrage", "bool", False, scope="state", writable_by=("timeline",), animatable=True),
            VariableSpec("count", "int", 0, scope="behavior", writable_by=("behavior",), behavior_output=True),
            VariableSpec("hp", "float", 1.0, scope="engine_snapshot", writable_by=("engine_snapshot",)),
        )
    )


def test_scope_lifecycle_and_cross_state_values() -> None:
    store = _store()
    store.write("rank", 2.0, writer="safe_action")
    store.enter_scope("state", "00000000-0000-0000-0000-000000000001")
    store.write("enrage", True, writer="timeline", owner_id="00000000-0000-0000-0000-000000000001")
    assert store.read("rank") == 2.0
    assert store.read("enrage", owner_id="00000000-0000-0000-0000-000000000001") is True
    store.exit_scope("state", "00000000-0000-0000-0000-000000000001")
    with pytest.raises(VariableError):
        store.read(VariableRef("enrage", scope="state"), owner_id="00000000-0000-0000-0000-000000000001")


def test_write_permissions_and_operations_are_explicit() -> None:
    store = _store()
    with pytest.raises(VariableError, match="not allowed"):
        store.write("rank", 3.0, writer="timeline")
    store.write("rank", 1.0, writer="safe_action", operation="add")
    assert store.read("rank") == 2.0
    with pytest.raises(VariableError, match="Engine Snapshot"):
        store.write("hp", 0.5, writer="engine_snapshot")
    store.publish_engine_snapshot({"hp": 0.5})
    assert store.read("hp", owner_id="engine_snapshot") == 0.5
    with pytest.raises(VariableError, match="declared output"):
        store.write("rank", 1.0, writer="behavior")
    store.write("count", 3, writer="behavior", owner_id="behavior-1")
    assert store.read("count", owner_id="behavior-1") == 3


def test_runtime_snapshot_is_a_copy_and_reset_is_deterministic() -> None:
    store = _store()
    store.write("rank", 9.0, writer="safe_action")
    snapshot = store.snapshot()
    snapshot["stage"]["stage"]["rank"] = -100
    assert store.read("rank") == 9.0
    store.reset()
    assert store.read("rank") == 1.0
    assert store.writes == ()


def test_formal_stage_runner_applies_variable_timeline_and_safe_action(tmp_path) -> None:
    from src.core.project_context import ProjectContext
    from src.editor.document import TimelineClip, TimelineTrack
    from src.editor.stage_compile import compile_stage
    from src.editor import SceneEditorSession, StateActionSpec
    from src.game.stage.program import StageRunner

    scene = SceneEditorSession.new_document("Variable Stage")
    scene.variables.append(
        VariableSpec("rank", "float", 1.0, writable_by=("safe_action",))
    )
    state = scene.state_graph.initial_state
    state.variables.append(
        VariableSpec("enrage", "bool", False, scope="state", writable_by=("timeline",), animatable=True)
    )
    state.entry_actions.append(
        StateActionSpec(
            name="Raise rank",
            kind="Variable",
            channel="variables",
            payload={"variable": "rank", "operation": "add", "value": 1.0},
        )
    )
    state.tracks.append(
        TimelineTrack(
            name="Variables",
            kind="Variable",
            channel="variables",
            clips=[
                TimelineClip(
                    name="Enrage",
                    kind="Variable",
                    start_frame=0,
                    duration_frames=1,
                    channel="variables",
                    payload={"variable": {"name": "enrage", "scope": "state"}, "value": True},
                )
            ],
        )
    )
    state.duration_frames = 2
    program = compile_stage(ProjectContext(tmp_path), scene)
    runner = StageRunner(program)
    runner.start()
    result = runner.tick(object())
    assert runner.read_variable("rank") == 2.0
    assert runner.read_variable("enrage", owner_id=state.id) is True
    assert result.variable_snapshot["stage"]["stage"]["rank"] == 2.0
    runner.reset()
    assert runner.read_variable("rank") == 1.0


def test_variable_conflict_requires_explicit_reducer(tmp_path) -> None:
    from src.core.project_context import ProjectContext
    from src.editor.document import TimelineClip, TimelineTrack
    from src.editor.stage_compile import StageCompileError, compile_stage
    from src.editor import SceneEditorSession

    scene = SceneEditorSession.new_document("Conflict")
    scene.variables.append(VariableSpec("value", "float", 0.0, writable_by=("timeline",), animatable=True))
    state = scene.state_graph.initial_state
    state.tracks.append(
        TimelineTrack(
            name="A", kind="Variable", channel="variables",
            clips=[TimelineClip(name="A", kind="Variable", start_frame=0, duration_frames=2, channel="variables", payload={"variable": "value", "value": 1.0})],
        )
    )
    state.tracks.append(
        TimelineTrack(
            name="B", kind="Variable", channel="variables",
            clips=[TimelineClip(name="B", kind="Variable", start_frame=0, duration_frames=2, channel="variables", payload={"variable": "value", "value": 2.0})],
        )
    )
    with pytest.raises(StageCompileError, match="Multiple writers overlap"):
        compile_stage(ProjectContext(tmp_path), scene)

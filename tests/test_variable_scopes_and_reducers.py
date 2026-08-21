"""N2.3–N2.5 scope ownership, mapping, and reducer contracts."""

from __future__ import annotations

import pytest

from src.authoring.variables import VariableError, VariableRef, VariableSpec, VariableStore


def test_resolution_refuses_implicit_scope_and_owner_guessing():
    store = VariableStore(
        (
            VariableSpec("phase", "int", 1, scope="stage"),
            VariableSpec("phase", "int", 2, scope="behavior", writable_by=("behavior",), behavior_output=True),
        )
    )
    with pytest.raises(VariableError, match="ambiguous"):
        store.read("phase")
    store.enter_scope("behavior", "b-1")
    assert store.read(VariableRef("phase", scope="behavior", owner_id="b-1")) == 2
    store.exit_scope("behavior", "b-1")
    with pytest.raises(VariableError, match="not active"):
        store.read(VariableRef("phase", scope="behavior", owner_id="b-1"))


def test_scope_owner_lifecycle_is_visible_and_dynamic_writes_do_not_auto_create():
    store = VariableStore(
        (VariableSpec("value", "float", 0.0, scope="clip", writable_by=("timeline",), animatable=True),)
    )
    assert store.active_owners("clip") == ()
    with pytest.raises(VariableError, match="not active"):
        store.write("value", 1.0, writer="timeline", owner_id="clip-1")
    store.create_scope("clip", "clip-1")
    assert store.scope_active("clip", "clip-1")
    store.write("value", 1.0, writer="timeline", owner_id="clip-1")
    store.destroy_scope("clip", "clip-1")
    assert not store.scope_active("clip", "clip-1")


def test_reducers_support_numeric_vector_and_complex_values():
    store = VariableStore(
        (
            VariableSpec("n", "float", 2.0, writable_by=("timeline",), animatable=True, reducer="multiply"),
            VariableSpec("v", "vector2", {"x": 1.0, "y": 2.0}, writable_by=("timeline",), animatable=True, reducer="add"),
            VariableSpec("z", "complex", {"real": 1.0, "imag": 0.0}, writable_by=("timeline",), animatable=True, reducer="multiply"),
        )
    )
    store.write("n", 3.0, writer="timeline", reducer="multiply")
    store.write("v", {"x": 2.0, "y": 3.0}, writer="timeline", reducer="add")
    store.write("z", {"real": 0.0, "imag": 1.0}, writer="timeline", reducer="multiply")
    assert store.read("n") == 6.0
    assert store.read("v") == {"x": 3.0, "y": 5.0}
    assert store.read("z") == {"real": 0.0, "imag": 1.0}
    store.set_frame(1)
    store.write("n", 3.0, writer="timeline", reducer="multiply")
    assert store.read("n") == 6.0


def test_stage_compiler_applies_declared_reducer_in_fixed_track_order(tmp_path):
    from src.core.project_context import ProjectContext
    from src.editor import SceneEditorSession, TimelineClip, TimelineTrack
    from src.compiler.stage import compile_stage
    from src.game.stage.program import StageRunner

    scene = SceneEditorSession.new_document("Reducer")
    scene.variables.append(
        VariableSpec(
            "score", "float", 0.0, writable_by=("timeline",), animatable=True, reducer="add"
        )
    )
    state = scene.state_graph.initial_state
    for order, value in enumerate((2.0, 3.0)):
        state.tracks.append(
            TimelineTrack(
                name=f"Writer {order}", kind="Variable", channel="variables", order=order,
                clips=[TimelineClip(
                    name=f"Write {order}", kind="Variable", channel="variables",
                    start_frame=0, duration_frames=2, order=0,
                    payload={"variable": {"name": "score", "scope": "stage"}, "value": value},
                )],
            )
        )
    state.duration_frames = 2
    runner = StageRunner(compile_stage(ProjectContext(tmp_path), scene))
    runner.start()
    runner.tick(object())
    assert runner.read_variable("score") == 5.0
    runner.tick(object())
    assert runner.read_variable("score") == 5.0


def test_behavior_output_mapping_validates_types_and_executes_formal_runner(tmp_path):
    from src.authoring.variables import VariableOutputMapping
    from src.core.project_context import ProjectContext
    from src.editor import SceneEditorSession
    from src.compiler.stage import compile_stage
    from src.game.stage.program import StageRunner

    scene = SceneEditorSession.new_document("Mapping")
    scene.variables.extend(
        [
            VariableSpec("generated", "float", 0.0, scope="behavior", writable_by=("behavior",), behavior_output=True),
            VariableSpec("score", "float", 1.0, scope="stage", writable_by=("behavior",)),
        ]
    )
    scene.output_mappings.append(
        VariableOutputMapping(
            source=VariableRef("generated", scope="behavior", type="float"),
            target=VariableRef("score", scope="stage", type="float"),
        )
    )
    runner = StageRunner(compile_stage(ProjectContext(tmp_path), scene))
    runner.start()
    runner.publish_behavior_output("behavior-1", {"generated": 4.0})
    assert runner.read_variable("score") == 4.0

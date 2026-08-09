"""N2.6 native/offscreen contract for the variable workspace."""

from __future__ import annotations

from src.authoring.variables import VariableSpec
from src.editor import SceneEditorSession
from src.editor.variable_workspace import VariableEditor


def test_variable_editor_exposes_typed_properties_and_read_only_overlay(qapp_session):
    scene = SceneEditorSession.new_document("Variables")
    scene.variables.append(
        VariableSpec(
            "rank", "float", 1.0, writable_by=("safe_action",), readers=("debugger",), reducer="override"
        )
    )
    before = scene.to_dict()
    editor = VariableEditor()
    editor.set_document(scene)
    editor.set_runtime_overlay({"stage": {"stage": {"rank": 9.0}}})
    assert editor.table.columnCount() == 10
    assert editor.table.item(0, 9).text() == "9.0"
    assert scene.to_dict() == before


def test_variable_editor_controls_stay_inside_a_narrow_dock(qapp_session):
    scene = SceneEditorSession.new_document("Narrow variables")
    scene.variables.append(VariableSpec("rank", "float", 1.0))
    editor = VariableEditor()
    editor.set_document(scene)
    editor.resize(360, 420)
    editor.show()
    qapp_session.processEvents()

    controls = (
        editor.name_edit,
        editor.type_combo,
        editor.scope_combo,
        editor.default_edit,
        editor.writers_edit,
        editor.readers_edit,
        editor.reducer_combo,
        editor.animatable_check,
        editor.replay_check,
        editor.behavior_output_check,
        editor.table,
    )
    right_edge = editor.rect().right()
    assert all(control.geometry().right() <= right_edge for control in controls)
    assert editor.minimumSizeHint().width() <= 360
    editor.close()

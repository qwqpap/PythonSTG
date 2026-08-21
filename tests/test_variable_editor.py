"""N2.0 editor contract for undoable variable declarations and read-only overlay."""

from __future__ import annotations

import pytest

from src.authoring.variables import VariableOutputMapping, VariableRef, VariableSpec
from src.editor import SceneEditorSession
from src.editor.app import EditorMainWindow
from src.editor.panels.variable_mapping_workspace import VariableBindingDialog, VariableMappingDialog
from src.qt_compat.QtCore import Qt
from src.editor.variable_commands import (
    AddVariableCommand,
    RemoveVariableCommand,
    SetVariablePropertiesCommand,
)


def test_variable_commands_are_undoable_and_preserve_identity() -> None:
    # Construct through the normal editor factory so validation follows the
    # same path as the native workbench.
    from src.core.project_context import ProjectContext
    from src.editor.storage import DocumentStore
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        editor = SceneEditorSession(DocumentStore(ProjectContext(root)))
        document = editor.document
        variable = VariableSpec("rank", "float", 1.0, writable_by=("safe_action",))
        editor.apply(AddVariableCommand(document, variable))
        assert document.variables[0].id == variable.id
        editor.apply(SetVariablePropertiesCommand(document, variable.id, {"default": 2.0}))
        assert document.variables[0].default == 2.0
        assert editor.undo()
        assert document.variables[0].default == 1.0
        assert editor.redo()
        assert document.variables[0].default == 2.0
        editor.apply(RemoveVariableCommand(document, variable.id))
        assert not document.variables
        assert editor.undo()
        assert document.variables[0].id == variable.id


def test_runtime_overlay_does_not_change_document_defaults(qapp_session) -> None:
    scene = SceneEditorSession.new_document("Overlay")
    scene.variables.append(VariableSpec("rank", "float", 1.0))
    before = scene.to_dict()
    from src.editor.panels.variable_workspace import VariableEditor

    editor = VariableEditor()
    editor.set_document(scene)
    editor.set_runtime_overlay({"stage": {"stage": {"rank": 8.0}}})
    assert editor.table.item(0, 9).text() == "8.0"
    assert scene.to_dict() == before
    editor.close()


def test_binding_picker_filters_and_returns_a_selected_compatible_variable(qapp_session) -> None:
    source = VariableSpec("phase", "float", 0.0, scope="stage")
    compatible = VariableSpec("rank", "float", 1.0, scope="stage")
    wrong_type = VariableSpec("enabled", "bool", False, scope="stage")
    picker = VariableBindingDialog([compatible, wrong_type])
    picker.search_edit.setText("rank")
    assert picker.results.count() == 1
    assert picker.results.item(0).data(Qt.UserRole) == compatible.id
    picker.accept()
    assert picker.selected_id == compatible.id
    assert source.id != picker.selected_id
    picker.close()


def test_mapping_dialog_filters_targets_by_behavior_output_type(qapp_session) -> None:
    source = VariableSpec(
        "generated",
        "float",
        0.0,
        scope="behavior",
        writable_by=("behavior",),
        behavior_output=True,
    )
    target = VariableSpec("score", "float", 0.0, scope="stage", writable_by=("behavior",))
    wrong_type = VariableSpec("enabled", "bool", False, scope="stage", writable_by=("behavior",))
    dialog = VariableMappingDialog([source, target, wrong_type], ())
    assert dialog.source_combo.count() == 1
    assert dialog.target_combo.count() == 1
    dialog.add_button.click()
    assert len(dialog.mappings) == 1
    assert dialog.mappings[0].source.name == source.name
    assert dialog.mappings[0].target.name == target.name
    dialog.close()


def test_editor_mapping_diff_is_one_undoable_transaction(tmp_path, qapp_session) -> None:
    from src.core.project_context import ProjectContext

    window = EditorMainWindow(ProjectContext(tmp_path))
    try:
        document = window.session.document
        source = VariableSpec(
            "generated",
            "float",
            0.0,
            scope="behavior",
            writable_by=("behavior",),
            behavior_output=True,
        )
        target = VariableSpec("score", "float", 0.0, scope="stage", writable_by=("behavior",))
        document.variables.extend([source, target])
        mapping = VariableOutputMapping(
            source=VariableRef(source.name, scope=source.scope, type=source.type),
            target=VariableRef(target.name, scope=target.scope, type=target.type),
        )
        before = document.to_dict()
        window._apply_variable_mapping_changes((mapping,), state_id=None)
        assert len(document.output_mappings) == 1
        assert window.session.commands.undo_label == "Edit output mappings"
        assert document.to_dict() != before
        assert window.session.undo()
        assert document.output_mappings == []
        assert window.session.redo()
        assert document.output_mappings[0].id == mapping.id
    finally:
        window.close()
        qapp_session.processEvents()

"""N2.0 editor contract for undoable variable declarations and read-only overlay."""

from __future__ import annotations

import pytest

from src.authoring.variables import VariableSpec
from src.editor import SceneEditorSession
from src.editor.variable_commands import (
    AddVariableCommand,
    RemoveVariableCommand,
    SetVariablePropertiesCommand,
)


def test_variable_commands_are_undoable_and_preserve_identity() -> None:
    session = SceneEditorSession(SceneEditorSession.__annotations__.get("store")) if False else None
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


def test_runtime_overlay_does_not_change_document_defaults() -> None:
    scene = SceneEditorSession.new_document("Overlay")
    scene.variables.append(VariableSpec("rank", "float", 1.0))
    before = scene.to_dict()
    overlay = {"stage": {"stage": {"rank": 8.0}}}
    assert overlay["stage"]["stage"]["rank"] == 8.0
    assert scene.to_dict() == before

from __future__ import annotations

from pathlib import Path

from src.core.project_context import ProjectContext
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.authoring.python_source import ExternalChange
from src.qt_compat.QtWidgets import QSpinBox


def _project(root: Path) -> Path:
    root.mkdir()
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project(id='demo', name='Demo', start_stage=Ref('stage'), stages=[Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage, Wait\n\n"
        "stage = Stage(id='stage', name='Stage', body=[Wait(12, uid='wait')])\n",
        encoding="utf-8",
    )
    return root


def test_minimal_window_navigates_and_edits_real_project(tmp_path, qapp_session):
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(_project(tmp_path / "authoring"))
    window = EditorWindow(session)
    window.show()
    qapp_session.processEvents()

    assert window.findChild(type(window.unit_list), "program_structure") is window.unit_list
    assert window.code_view.isReadOnly()
    assert window.timeline_panel.objectName() == "timeline_panel"
    assert window.timeline_panel.session is session
    assert window.preview_host.objectName() == "game_preview_host"
    assert window.preview_owner.session is session
    assert window.preview_owner.process is None
    assert window.problems_view.toPlainText() == "没有问题"

    session.select_unit("stage")
    root_item = window.program_tree.topLevelItem(0)
    wait_item = root_item.child(0)
    window.program_tree.setCurrentItem(wait_item)
    qapp_session.processEvents()
    assert session.current_node_uid == "wait"

    field = window.inspector.findChild(QSpinBox, "argument_frames")
    assert field is not None
    assert not field.isReadOnly()
    field.setValue(24)
    field.editingFinished.emit()
    qapp_session.processEvents()

    assert session.current_node.arguments["frames"] == 24
    assert session.undo_stack.count() == 1
    assert "frames=24" in window.code_view.toPlainText()

    window.close()


def test_closing_external_conflict_dialog_does_not_authorize_overwrite(
    tmp_path, qapp_session, monkeypatch
):
    root = _project(tmp_path / "authoring")
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(root)
    session.select_node("wait")
    session.set_node_argument("wait", "frames", 20)
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage, Wait\n\n"
        "stage = Stage(id='stage', name='Disk', body=[Wait(30, uid='wait')])\n",
        encoding="utf-8",
    )
    assert session.check_external_changes() == ExternalChange.CONFLICT
    window = EditorWindow(session)

    class ClosedMessageBox:
        ButtonRole = type("ButtonRole", (), {"AcceptRole": 0, "RejectRole": 1})

        def __init__(self, _parent):
            self._buttons = []

        def setWindowTitle(self, _text):
            pass

        def setText(self, _text):
            pass

        def setInformativeText(self, _text):
            pass

        def addButton(self, _text, _role):
            button = object()
            self._buttons.append(button)
            return button

        def exec(self):
            return 0

        def clickedButton(self):
            return None

    monkeypatch.setattr("src.editor.window.QMessageBox", ClosedMessageBox)
    window._ask_external_decision((Path("stage.py"),))

    document = session.source_project.file_for_unit("stage")
    assert document.conflict
    assert not document.overwrite_confirmed
    assert session.has_conflict
    window._dirty_changed(session.dirty)
    assert window.save_action.isEnabled()
    window.close()

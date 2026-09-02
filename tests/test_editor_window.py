from __future__ import annotations

from pathlib import Path

import pytest

from src.authoring.program import DropPlacement
from src.core.project_context import ProjectContext
from src.editor.node_palette import PROTOTYPE_MIME
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.authoring.python_source import ExternalChange
from src.qt_compat.QtCore import QEvent, QMimeData, QPointF, Qt
from src.qt_compat.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QMouseEvent
from src.qt_compat.QtWidgets import QApplication, QDockWidget, QLabel, QSpinBox
from src.editor.sidebars import UNIT_REFERENCE_MIME


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


def _project_with_boss(root: Path) -> Path:
    root = _project(root)
    (root / "nons.py").write_text(
        "from src.authoring.dsl import NonSpell\n\n"
        "nons = NonSpell(id='nons', name='NonSpell', body=[])\n",
        encoding="utf-8",
    )
    (root / "boss.py").write_text(
        "from src.authoring.dsl import Boss, Ref\n\n"
        "boss = Boss(id='boss', name='Boss', texture='enemy_fairy', phases=[Ref('nons')])\n",
        encoding="utf-8",
    )
    return root


def _unit_tree_mime(window: EditorWindow, unit_id: str) -> QMimeData:
    def walk(item):
        yield item
        for index in range(item.childCount()):
            yield from walk(item.child(index))

    for top in range(window.unit_list.topLevelItemCount()):
        for item in walk(window.unit_list.topLevelItem(top)):
            if item.data(0, int(Qt.ItemDataRole.UserRole)) == unit_id:
                mime = window.unit_list.mimeData([item])
                assert mime.hasFormat(UNIT_REFERENCE_MIME)
                return mime
    raise AssertionError(f"unit {unit_id!r} is not visible in the structure tree")


def _drop_unit_reference(widget, mime: QMimeData) -> QDropEvent:
    target = widget.viewport()
    position = target.rect().center()
    actions = Qt.DropAction.MoveAction
    buttons = Qt.MouseButton.LeftButton
    modifiers = Qt.KeyboardModifier.NoModifier
    enter = QDragEnterEvent(position, actions, mime, buttons, modifiers)
    move = QDragMoveEvent(position, actions, mime, buttons, modifiers)
    drop = QDropEvent(position, actions, mime, buttons, modifiers)
    QApplication.sendEvent(target, enter)
    QApplication.sendEvent(target, move)
    assert move.isAccepted()
    QApplication.sendEvent(target, drop)
    return drop


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
    canvas = window.program_tree.canvas
    rect = canvas.rect_for_uid("wait")
    assert rect is not None, "the Wait card must be visible in the program flow"
    click = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(rect.center()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, click)
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


def test_window_respects_960_by_640_working_size(tmp_path, qapp_session):
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(_project(tmp_path / "authoring"))
    window = EditorWindow(session)
    window.resize(960, 640)
    window.show()
    qapp_session.processEvents()

    assert window.size().width() == 960
    assert window.size().height() == 640
    assert window.findChild(QDockWidget, "left_activity_dock").width() >= 200
    assert window.inspector_dock.width() >= 220
    assert window.central_groups.width() >= 450
    assert window.program_tree.viewport().width() >= 250
    assert window.timeline_dock.isVisible()

    window.close()


@pytest.mark.parametrize(("unit_id", "kind"), (("demo", "Project"), ("boss", "Boss")))
def test_non_statement_units_reject_palette_add_drag_and_real_insert(
    tmp_path, qapp_session, unit_id, kind
):
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(_project_with_boss(tmp_path / "authoring"))
    window = EditorWindow(session)
    window.show()
    session.select_unit(unit_id)
    qapp_session.processEvents()
    before = session.program.semantic_data()

    palette = window.node_palette
    allowed, reason = palette.compatibility(palette.entry("Wait"))
    assert not allowed
    assert reason == f"{kind} 不包含执行节点"

    # This is the same callback used by the visible generic Add button and
    # palette double-click fallback.  It must not create an Undo entry.
    window._insert_selected_prototype("Wait")
    assert session.program.semantic_data() == before
    assert session.undo_stack.count() == 0

    mime = QMimeData()
    mime.setData(PROTOTYPE_MIME, b"Wait")
    assert not window._validate_program_drop(
        mime, None, DropPlacement.AFTER, None
    ).allowed

    canvas = window.program_tree.canvas
    summary = next(element for element in canvas._layout.elements if element.kind == "summary")
    enter = QDragEnterEvent(
        summary.rect.center(),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move = QDragMoveEvent(
        summary.rect.center(),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, enter)
    QApplication.sendEvent(canvas, move)
    assert not move.isAccepted()
    assert session.program.semantic_data() == before
    window.close()


def test_project_stage_order_and_boss_phases_use_dedicated_unit_ref_drop_lists(
    tmp_path, qapp_session
):
    root = _project_with_boss(tmp_path / "authoring")
    (root / "stage_two.py").write_text(
        "from src.authoring.dsl import Stage\n\n"
        "stage_two = Stage(id='stage_two', name='Second Stage', body=[])\n",
        encoding="utf-8",
    )
    (root / "spell.py").write_text(
        "from src.authoring.dsl import Spell\n\n"
        "spell = Spell(id='spell', name='Spell', body=[])\n",
        encoding="utf-8",
    )
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(root)
    window = EditorWindow(session)
    window.show()

    session.select_unit("demo")
    qapp_session.processEvents()
    assert window.program_content_stack.currentWidget() is window.project_reference_panel
    before = session.undo_stack.count()
    stage_drop = _drop_unit_reference(
        window.project_stage_list,
        _unit_tree_mime(window, "stage_two"),
    )
    assert stage_drop.isAccepted()
    assert [ref.id for ref in session.program.get_unit("demo").metadata["stages"]] == [
        "stage",
        "stage_two",
    ]
    assert session.undo_stack.count() == before + 1
    stage_two_index = window.start_stage_combo.findData("stage_two")
    window.start_stage_combo.setCurrentIndex(stage_two_index)
    qapp_session.processEvents()
    assert session.program.get_unit("demo").metadata["start_stage"].id == "stage_two"

    # The specialised list must be editable in both directions.  A start
    # Stage is deliberately not removed until the author explicitly chooses
    # another start Stage in the visible combobox.
    stage_one_index = window.start_stage_combo.findData("stage")
    window.start_stage_combo.setCurrentIndex(stage_one_index)
    qapp_session.processEvents()
    window.project_stage_list.setCurrentRow(1)
    qapp_session.processEvents()
    assert window.project_stage_remove_button.isEnabled()
    window.project_stage_remove_button.click()
    qapp_session.processEvents()
    assert [ref.id for ref in session.program.get_unit("demo").metadata["stages"]] == [
        "stage"
    ]

    session.select_unit("boss")
    qapp_session.processEvents()
    assert window.program_content_stack.currentWidget() is window.boss_reference_panel
    assert any(
        label.text() == "Boss 阶段"
        for label in window.boss_reference_panel.findChildren(QLabel)
    )
    assert "Boss 阶段列表" in window.next_step_hint.text()
    before = session.undo_stack.count()
    phase_drop = _drop_unit_reference(
        window.boss_phase_list,
        _unit_tree_mime(window, "spell"),
    )
    assert phase_drop.isAccepted()
    assert [ref.id for ref in session.program.get_unit("boss").metadata["phases"]] == [
        "nons",
        "spell",
    ]
    assert session.undo_stack.count() == before + 1
    window.boss_phase_list.setCurrentRow(1)
    qapp_session.processEvents()
    assert window.boss_phase_remove_button.isEnabled()
    window.boss_phase_remove_button.click()
    qapp_session.processEvents()
    assert [ref.id for ref in session.program.get_unit("boss").metadata["phases"]] == [
        "nons"
    ]
    session.save_all()
    window.close()

    reopened = EditorSession(project_context=ProjectContext(Path.cwd()))
    reopened.open_project(root)
    assert [ref.id for ref in reopened.program.get_unit("demo").metadata["stages"]] == [
        "stage",
    ]
    assert reopened.program.get_unit("demo").metadata["start_stage"].id == "stage"
    assert [ref.id for ref in reopened.program.get_unit("boss").metadata["phases"]] == [
        "nons",
    ]


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


def test_timeline_panel_controls_are_wired_to_the_preview_owner(
    tmp_path, qapp_session, monkeypatch
):
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(_project(tmp_path / "authoring"))
    window = EditorWindow(session)
    window.show()
    qapp_session.processEvents()

    calls = []
    monkeypatch.setattr(
        window.preview_owner, "seek", lambda frame: calls.append(("seek", frame))
    )
    monkeypatch.setattr(window.preview_owner, "pause", lambda: calls.append(("pause",)))
    monkeypatch.setattr(
        window.preview_owner, "resume", lambda: calls.append(("resume",))
    )

    window.timeline_panel.seek_requested.emit(240)
    window.timeline_panel.pause_requested.emit()
    window.timeline_panel.resume_requested.emit()

    assert ("seek", 240) in calls
    assert ("pause",) in calls
    assert ("resume",) in calls
    window.close()

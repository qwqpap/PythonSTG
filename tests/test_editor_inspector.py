from __future__ import annotations

from pathlib import Path

from src.authoring.program import Expr, Ref
from src.core.project_context import ProjectContext
from src.editor.inspector import (
    InspectorPanel,
    LiteralTextEdit,
    ParameterTable,
    ResourceLineEdit,
)
from src.editor.session import EditorSession
from src.qt_compat.QtCore import Qt
from src.qt_compat.QtTest import QTest
from src.qt_compat.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QToolButton,
)


def _project(root: Path) -> Path:
    root.mkdir(parents=True)
    sources = {
        "project.py": (
            "from src.authoring.dsl import Project, Ref\n\n"
            "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n"
        ),
        "stage.py": (
            "from src.authoring.dsl import PlayDialogue, Ref, RunBoss, Stage, Wait\n\n"
            "stage = Stage('stage', 'Stage', body=[Wait(12, uid='wait'), "
            "RunBoss(Ref('boss'), uid='run_boss'), "
            "PlayDialogue([('Reimu', 'left', 'Ready?')], uid='dialogue')])\n"
        ),
        "stage2.py": (
            "from src.authoring.dsl import Stage\n\n"
            "stage = Stage('stage2', 'Stage Two')\n"
        ),
        "enemy.py": (
            "from src.authoring.dsl import Enemy, MoveTo\n\n"
            "enemy = Enemy('enemy', 'Enemy', body=[MoveTo(0.5, 0.25, duration=30, uid='move')])\n"
        ),
        "boss.py": (
            "from src.authoring.dsl import Boss, Ref\n\n"
            "boss = Boss('boss', 'Boss', 'res://assets/boss.png', [Ref('spell')])\n"
        ),
        "spell.py": (
            "from src.authoring.dsl import Spell, Wait\n\n"
            "spell = Spell('spell', 'Spell', body=[Wait(1, uid='spell_wait')])\n"
        ),
        "task.py": (
            "from src.authoring.dsl import Parameter, Task, Wait\n\n"
            "task = Task('task', 'Task', parameters=[Parameter('count', 'int', 3)], "
            "body=[Wait(1, uid='task_wait')])\n"
        ),
    }
    for name, source in sources.items():
        (root / name).write_text(source, encoding="utf-8")
    return root


def _session(tmp_path: Path) -> EditorSession:
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(_project(tmp_path / "authoring"))
    return session


def test_inspector_uses_dsl_annotations_for_scalar_controls_and_undo(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    panel = InspectorPanel(session)
    panel.show()

    session.select_node("wait")
    qapp_session.processEvents()
    frames = panel.findChild(QSpinBox, "argument_frames")
    assert frames is not None
    assert "int" in frames.property("pystg_annotation")
    frames.setValue(24)
    frames.editingFinished.emit()
    qapp_session.processEvents()
    assert session.current_node.arguments["frames"] == 24
    assert session.undo_stack.count() == 1

    session.select_node("move")
    qapp_session.processEvents()
    x = panel.findChild(QDoubleSpinBox, "argument_x")
    duration = panel.findChild(QSpinBox, "argument_duration")
    assert x is not None and duration is not None
    assert x.value() == 0.5
    assert duration.value() == 30

    session.select_node("run_boss")
    qapp_session.processEvents()
    midboss = panel.findChild(QCheckBox, "argument_is_midboss")
    assert midboss is not None
    assert not midboss.isChecked()
    midboss.setChecked(True)
    assert session.current_node.arguments["is_midboss"] is True
    assert session.undo_stack.count() == 2

    session.undo_stack.undo()
    assert "is_midboss" not in session.current_node.arguments
    session.undo_stack.undo()
    session.select_node("wait")
    assert session.current_node.arguments["frames"] == 12
    panel.close()


def test_numeric_zero_keyboard_commit_does_not_destroy_active_editor(
    tmp_path, qapp_session
):
    """A real key event must finish before Inspector replaces its controls."""

    session = _session(tmp_path)
    panel = InspectorPanel(session)
    panel.show()
    session.select_node("wait")
    qapp_session.processEvents()

    frames = panel.findChild(QSpinBox, "argument_frames")
    assert frames is not None
    frames.setFocus()
    frames.lineEdit().selectAll()
    QTest.keyClick(frames, Qt.Key.Key_0)
    frames.editingFinished.emit()
    assert session.current_node.arguments["frames"] == 12
    qapp_session.processEvents()

    assert session.current_node.arguments["frames"] == 0
    assert session.undo_stack.count() == 1
    panel.close()


def test_ref_selector_is_typed_and_task_parameter_table_is_undoable(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    panel = InspectorPanel(session)
    panel.show()

    session.select_node("run_boss")
    qapp_session.processEvents()
    selector = panel.findChild(QComboBox, "argument_boss_def")
    assert selector is not None
    assert [selector.itemText(index) for index in range(selector.count())] == ["boss"]

    session.select_unit("task")
    qapp_session.processEvents()
    parameters = panel.findChild(ParameterTable, "argument_parameters")
    assert parameters is not None
    parameters.table.item(0, 2).setText("5")
    parameters.commit_requested.emit(parameters.parameters())
    assert session.program.get_unit("task").parameters[0].default == 5
    assert session.undo_stack.count() == 1
    session.undo_stack.undo()
    assert session.program.get_unit("task").parameters[0].default == 3
    panel.close()


def test_unit_name_is_plain_text_and_ref_lists_use_headless_author_values(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    panel = InspectorPanel(session)
    panel.show()
    session.select_unit("demo")
    qapp_session.processEvents()

    name = panel.findChild(QLineEdit, "argument_unit_name")
    assert name is not None and not isinstance(name, ResourceLineEdit)
    assert panel.findChild(QToolButton, "expression_toggle_名称") is None

    stages = panel.findChild(LiteralTextEdit, "argument_stages")
    assert stages is not None
    stages.setPlainText("[Ref('stage'), Ref('stage2')]")
    stages.commit_requested.emit()
    assert session.program.get_unit("demo").metadata["stages"] == [
        Ref("stage"),
        Ref("stage2"),
    ]
    panel.close()


def test_expr_toggle_is_bidirectional_and_rejects_nonliteral_numeric_source(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    panel = InspectorPanel(session)
    panel.show()
    session.select_node("wait")
    qapp_session.processEvents()

    to_expr = panel.findChild(QToolButton, "expression_toggle_frames")
    assert to_expr is not None and to_expr.text() == "ƒ"
    to_expr.click()
    assert session.current_node.arguments["frames"] == Expr("12")

    expression = panel.findChild(QLineEdit, "argument_frames")
    to_constant = panel.findChild(QToolButton, "expression_toggle_frames")
    assert expression is not None and to_constant is not None
    assert to_constant.text() == "常"
    expression.setText("player_x")
    to_constant.click()
    assert session.current_node.arguments["frames"] == Expr("12")
    error = panel.findChild(QLabel, "error_frames")
    assert error is not None and "字面量" in error.text()

    expression.setText("24")
    to_constant.click()
    assert session.current_node.arguments["frames"] == 24
    panel.close()


def test_structured_literal_errors_stay_in_the_field_and_do_not_mutate(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    panel = InspectorPanel(session)
    panel.show()
    session.select_node("dialogue")
    qapp_session.processEvents()

    editor = panel.findChild(LiteralTextEdit, "argument_dialogue_list")
    assert editor is not None
    original = session.current_node.arguments["dialogue_list"]
    editor.setPlainText("[")
    editor.commit_requested.emit()
    assert session.current_node.arguments["dialogue_list"] == original
    error = panel.findChild(QLabel, "error_dialogue_list")
    assert error is not None and "字面量" in error.text()

    editor.setPlainText("[('Marisa', 'right', 'Go!')]")
    editor.commit_requested.emit()
    assert session.current_node.arguments["dialogue_list"] == [
        ("Marisa", "right", "Go!")
    ]
    panel.close()


def test_compatible_resource_drop_assigns_one_unit_field_command(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    session.select_unit("stage")
    panel = InspectorPanel(session)
    panel.show()
    qapp_session.processEvents()
    bgm = panel.findChild(ResourceLineEdit, "argument_bgm")
    assert bgm is not None

    assert not bgm.drop_resource("res://assets/background.json")
    assert session.undo_stack.count() == 0
    assert bgm.drop_resource("res://assets/theme.ogg")
    assert session.undo_stack.count() == 1
    assert session.program.get_unit("stage").metadata["bgm"] == "res://assets/theme.ogg"

    session.undo_stack.undo()
    assert "bgm" not in session.program.get_unit("stage").metadata
    session.undo_stack.redo()
    assert session.program.get_unit("stage").metadata["bgm"] == "res://assets/theme.ogg"
    panel.close()

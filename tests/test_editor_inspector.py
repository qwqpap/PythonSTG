from __future__ import annotations

from pathlib import Path

from src.core.project_context import ProjectContext
from src.editor.inspector import InspectorPanel, ResourceLineEdit
from src.editor.session import EditorSession
from src.qt_compat.QtWidgets import QCheckBox, QDoubleSpinBox, QSpinBox


def _project(root: Path) -> Path:
    root.mkdir(parents=True)
    sources = {
        "project.py": (
            "from src.authoring.dsl import Project, Ref\n\n"
            "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n"
        ),
        "stage.py": (
            "from src.authoring.dsl import Ref, RunBoss, Stage, Wait\n\n"
            "stage = Stage('stage', 'Stage', body=[Wait(12, uid='wait'), "
            "RunBoss(Ref('boss'), uid='run_boss')])\n"
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

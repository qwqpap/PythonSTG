from __future__ import annotations

from pathlib import Path

import pytest

from src.authoring.program import ProgramError, find_node
from src.authoring.timeline import Unknown
from src.core.project_context import ProjectContext
from src.editor.session import EditorSession
from src.editor.timeline import TimelinePanel
from src.qt_compat.QtCore import QPoint, Qt
from src.qt_compat.QtTest import QTest


def _write_project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('timeline_ui', 'Timeline UI', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage, Wait\n\n"
        "stage = Stage('stage', 'Stage', [Wait(1, uid='stage_wait')])\n",
        encoding="utf-8",
    )
    (root / "task.py").write_text(
        "from src.authoring.dsl import At, Expr, MoveTo, Task, Wait\n\n"
        "task = Task(\n"
        "    id='timeline_task',\n"
        "    name='Timeline Task',\n"
        "    body=[\n"
        "        Wait(30, uid='wait'),\n"
        "        MoveTo(0.0, 0.5, duration=45, uid='move'),\n"
        "        At(120, body=[Wait(10, uid='at_wait')], uid='at'),\n"
        "        Wait(Expr('dynamic_frames'), uid='dynamic_wait'),\n"
        "    ],\n"
        ")\n",
        encoding="utf-8",
    )
    return root


def _session(tmp_path: Path) -> EditorSession:
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(_write_project(tmp_path / "authoring"))
    session.select_unit("timeline_task")
    return session


def test_timeline_panel_projects_selection_and_trace(tmp_path, qapp_session):
    session = _session(tmp_path)
    panel = TimelinePanel(session)
    panel.resize(900, 260)
    panel.show()
    qapp_session.processEvents()

    assert panel.projection.unit_id == "timeline_task"
    assert panel.projection.find("wait").end == 30
    assert isinstance(panel.projection.find("dynamic_wait").end, Unknown)
    assert panel.projection.find("dynamic_wait").editable == "none"

    session.reset_trace("run-7")
    session.append_trace(
        [
            {"uid": "wait", "phase": "start", "frame": 4},
            {"uid": "wait", "phase": "end", "frame": 40},
        ],
        run_id="run-7",
    )
    qapp_session.processEvents()
    assert panel.projection.trace_run_id == "run-7"
    assert panel.projection.find("wait").start == 4
    assert panel.projection.find("wait").end == 40
    assert "Trace run-7" in panel.status_label.text()
    panel.close()


def test_timeline_click_selects_the_source_node(tmp_path, qapp_session):
    session = _session(tmp_path)
    panel = TimelinePanel(session)
    panel.resize(900, 260)
    panel.show()
    qapp_session.processEvents()
    painted = next(item for item in panel.canvas._painted if item.interval.uid == "wait")
    point = painted.rect.center()
    QTest.mouseClick(
        panel.canvas,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(round(point.x()), round(point.y())),
    )

    assert session.current_node_uid == "wait"
    assert panel.canvas.selected_uid == "wait"
    panel.close()


def test_wait_duration_and_at_reverse_edits_share_one_undo_stack(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    panel = TimelinePanel(session)

    panel.edit_interval("wait", 60)
    panel.edit_interval("move", 90)
    panel.edit_interval("at", 180)
    assert find_node(session.program, "wait")[1].arguments["frames"] == 60
    assert find_node(session.program, "move")[1].arguments["duration"] == 90
    assert find_node(session.program, "at")[1].arguments["frame"] == 180
    assert session.undo_stack.count() == 3

    session.undo_stack.undo()
    assert find_node(session.program, "at")[1].arguments["frame"] == 120
    session.undo_stack.undo()
    assert find_node(session.program, "move")[1].arguments["duration"] == 45
    session.undo_stack.undo()
    assert find_node(session.program, "wait")[1].arguments["frames"] == 30
    session.undo_stack.redo()
    assert find_node(session.program, "wait")[1].arguments["frames"] == 60


def test_timeline_rejects_dynamic_or_unapproved_rewrites(tmp_path, qapp_session):
    session = _session(tmp_path)
    panel = TimelinePanel(session)
    with pytest.raises(ProgramError, match="只允许"):
        panel.edit_interval("dynamic_wait", 20)
    with pytest.raises(ProgramError, match="non-negative"):
        panel.edit_interval("wait", -1)
    assert session.undo_stack.count() == 0


def test_timeline_keeps_an_unresolved_call_project_open(tmp_path, qapp_session):
    root = _write_project(tmp_path / "authoring")
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Call, Ref, Stage\n\n"
        "stage = Stage(\n"
        "    'stage',\n"
        "    'Stage',\n"
        "    [Call(Ref('missing_task'), [3], uid='missing_call')],\n"
        ")\n",
        encoding="utf-8",
    )
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(root)
    session.select_unit("stage")

    panel = TimelinePanel(session)

    assert any(item.code == "unresolved_reference" for item in session.diagnostics)
    assert isinstance(panel.projection.find("missing_call").end, Unknown)

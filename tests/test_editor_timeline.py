from __future__ import annotations

import gc
import time
from pathlib import Path

import pytest

from src.authoring.dsl import Project, RawPython, Ref, Stage, Wait
from src.authoring.program import AuthoringProgram, ProgramError, find_node
from src.authoring.timeline import Unknown, project_timeline
from src.core.project_context import ProjectContext
from src.editor.session import EditorSession
from src.editor.timeline import TimelineCanvas, TimelinePanel, _layout_timeline_intervals
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
        "from src.authoring.dsl import Call, Ref, Stage, Wait\n\n"
        "stage = Stage('stage', 'Stage', ["
        "Wait(1, uid='stage_wait'), "
        "Call(Ref('timeline_task'), uid='stage_call')"
        "])\n",
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
            {"kind": "metrics", "frame": 36, "emitted": 12, "live": 40, "lasers": 1},
        ],
        run_id="run-7",
    )
    qapp_session.processEvents()
    assert panel.projection.trace_run_id == "run-7"
    assert panel.projection.find("wait").start == 0
    assert panel.projection.find("wait").end == 30
    assert panel.projection.find("wait").observed_start == 4
    assert panel.projection.find("wait").observed_end == 40
    assert panel.projection.metrics[0].live == 40
    assert "密度采样 1" in panel.status_label.text()
    assert "Trace run-7" in panel.status_label.text()
    panel.canvas.grab()
    assert panel.canvas._painted
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


def test_timeline_scope_navigation_and_range_loop_use_existing_seek(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    panel = TimelinePanel(session)
    panel.resize(900, 300)
    panel.show()
    qapp_session.processEvents()

    panel.scope_combo.setCurrentIndex(1)
    qapp_session.processEvents()
    assert panel.projection.unit_id == "stage"
    assert panel.projection.find("stage_call") is not None
    assert panel.projection.find("wait").parent_uid == "stage_call"

    seeks = []
    panel.seek_requested.connect(seeks.append)
    panel.loop_start.setValue(30)
    panel.loop_end.setValue(90)
    panel.loop_button.setChecked(True)
    session.set_preview_state("running")
    panel.handle_preview_event({"event": "frame", "payload": {"frame": 90}})
    assert seeks == [30]

    panel.fit_all()
    assert 0.1 <= panel.canvas.pixels_per_frame <= 4.0
    panel.center_playhead()
    panel.close()


def test_timeline_2000_interval_layout_and_zoom_p95_is_below_budget(
    tmp_path, qapp_session
):
    stage = Stage(
        "dense_stage",
        "Dense Stage",
        [Wait(1, uid=f"wait_{index}") for index in range(2000)],
    )
    program = AuthoringProgram.from_units(
        [Project("dense", "Dense", Ref("dense_stage"), [Ref("dense_stage")]), stage]
    )
    projection = project_timeline(program, stage)
    session = _session(tmp_path)
    canvas = TimelineCanvas(session)
    canvas.set_projection(projection, selected_uid=None, cursor_frame=0)

    # Warm caches and allocator state so the budget measures steady-state
    # interaction latency, not first-touch noise from earlier heavy tests.
    for _ in range(10):
        canvas.zoom(1.01)
        _layout_timeline_intervals(projection, pixels_per_frame=canvas.pixels_per_frame)
    gc.collect()

    samples = []
    for index in range(25):
        started = time.perf_counter()
        canvas.zoom(1.01 if index % 2 == 0 else 1 / 1.01)
        _layout_timeline_intervals(
            projection,
            pixels_per_frame=canvas.pixels_per_frame,
        )
        samples.append((time.perf_counter() - started) * 1000)
    p95 = sorted(samples)[round(0.95 * (len(samples) - 1))]
    assert p95 < 33.0, f"Timeline 2,000 interval zoom/layout p95={p95:.3f}ms"


def test_selecting_a_node_reveals_its_interval_in_the_timeline(tmp_path, qapp_session):
    root = tmp_path / "authoring"
    root.mkdir(parents=True)
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('far_ui', 'Far UI', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Call, Ref, Stage\n\n"
        "stage = Stage('stage', 'Stage', [Call(Ref('far_task'), uid='stage_call')])\n",
        encoding="utf-8",
    )
    (root / "task.py").write_text(
        "from src.authoring.dsl import Expr, Task, Wait\n\n"
        "task = Task(\n"
        "    id='far_task',\n"
        "    name='Far Task',\n"
        "    body=[\n"
        "        Wait(60, uid='early_wait'),\n"
        "        Wait(3000, uid='far_wait'),\n"
        "        Wait(Expr('d'), uid='dynamic_wait'),\n"
        "    ],\n"
        ")\n",
        encoding="utf-8",
    )
    session = EditorSession(project_context=ProjectContext(Path.cwd()))
    session.open_project(root)
    session.select_unit("far_task")
    panel = TimelinePanel(session)
    panel.resize(900, 260)
    panel.show()
    qapp_session.processEvents()

    def painted_rect(uid: str):
        layout = _layout_timeline_intervals(
            panel.projection,
            pixels_per_frame=panel.canvas.pixels_per_frame,
        )
        return next(item.rect for item in layout if item.interval.uid == uid)

    bar = panel.scroll.horizontalScrollBar()
    outside = painted_rect("dynamic_wait")
    assert outside.left() > bar.value() + panel.scroll.viewport().width(), (
        "precondition: the dynamic interval starts outside the viewport"
    )

    session.select_node("dynamic_wait")
    qapp_session.processEvents()

    assert panel.canvas.selected_uid == "dynamic_wait"
    revealed = painted_rect("dynamic_wait")
    assert revealed.left() >= bar.value()
    assert revealed.right() <= bar.value() + panel.scroll.viewport().width()
    panel.close()


def test_timeline_drag_gesture_edits_literal_wait_through_real_mouse(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    panel = TimelinePanel(session)
    panel.resize(900, 260)
    panel.show()
    qapp_session.processEvents()
    painted = next(
        item for item in panel.canvas._painted if item.interval.uid == "wait"
    )
    start = painted.rect.center()
    # The drag value is measured from the interval's left edge: 60 frames at
    # 0.5 px/frame lands 30 px right of the rect start.
    end_x = round(painted.rect.left() + 60 * panel.canvas.pixels_per_frame)

    QTest.mousePress(
        panel.canvas,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(round(start.x()), round(start.y())),
    )
    QTest.mouseMove(panel.canvas, QPoint(end_x, round(start.y())))
    QTest.mouseRelease(
        panel.canvas,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(end_x, round(start.y())),
    )

    assert find_node(session.program, "wait")[1].arguments["frames"] == 60
    assert session.undo_stack.count() == 1
    session.undo_stack.undo()
    assert find_node(session.program, "wait")[1].arguments["frames"] == 30
    panel.close()


def test_layout_keeps_source_order_after_dynamic_unknown(tmp_path, qapp_session):
    stage = Stage(
        "unknown_order_stage",
        "Unknown Order Stage",
        [
            RawPython("marker = 1", uid="raw_block"),
            Wait(10, uid="after_raw_1"),
            Wait(20, uid="after_raw_2"),
        ],
    )
    program = AuthoringProgram.from_units(
        [
            Project(
                "unknown_order",
                "Unknown Order",
                Ref("unknown_order_stage"),
                [Ref("unknown_order_stage")],
            ),
            stage,
        ]
    )
    projection = project_timeline(program, stage)
    assert isinstance(projection.find("raw_block").end, Unknown)
    assert isinstance(projection.find("after_raw_1").start, Unknown)
    assert isinstance(projection.find("after_raw_2").start, Unknown)

    layout = _layout_timeline_intervals(projection, pixels_per_frame=0.5)
    lefts = {item.interval.uid: item.rect.left() for item in layout}
    assert lefts["raw_block"] < lefts["after_raw_1"] < lefts["after_raw_2"]

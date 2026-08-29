"""ProgramFlow interaction tests driven by real Qt drag events."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.authoring.program import DropPlacement, ProgramError, find_node
from src.core.project_context import ProjectContext
from src.editor.node_palette import PROTOTYPE_MIME
from src.editor.program_tree import NODE_MIME, ProgramFlow
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtCore import QMimeData, QPoint, Qt
from src.qt_compat.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from src.qt_compat.QtWidgets import QApplication


def _project(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Parallel, Repeat, Stage, Wait\n\n"
        "stage = Stage(\n"
        "    'stage',\n"
        "    'Stage',\n"
        "    body=[\n"
        "        Repeat(2, body=[Wait(1, uid='inner')], uid='container'),\n"
        "        Repeat(1, body=[], uid='wrapper'),\n"
        "        Wait(2, uid='a'),\n"
        "        Wait(3, uid='b'),\n"
        "    ],\n"
        ")\n",
        encoding="utf-8",
    )
    return root


def _session(tmp_path: Path) -> EditorSession:
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(_project(tmp_path / "authoring"))
    session.select_unit("stage")
    return session


def _window(tmp_path: Path) -> EditorWindow:
    window = EditorWindow(_session(tmp_path))
    window.resize(1080, 720)
    window.show()
    QApplication.processEvents()
    window.inspector_dock.hide()
    window.timeline_dock.hide()
    window.resize(1080, 720)
    QApplication.processEvents()
    return window


def _drag_mime(window: EditorWindow, kind: str) -> QMimeData:
    """Build the MIME exactly as the visible palette tree emits it."""

    palette = window.node_palette

    def walk(item):
        yield item
        for index in range(item.childCount()):
            yield from walk(item.child(index))

    for top in range(palette.tree.topLevelItemCount()):
        for item in walk(palette.tree.topLevelItem(top)):
            if item.data(0, int(Qt.ItemDataRole.UserRole)) == kind and not item.isDisabled():
                mime = palette.tree.mimeData([item])
                assert mime.hasFormat(PROTOTYPE_MIME)
                return mime
    raise AssertionError(f"palette has no enabled {kind!r} entry")


def _node_mime(uid: str) -> QMimeData:
    mime = QMimeData()
    mime.setData(NODE_MIME, uid.encode("utf-8"))
    return mime


def _drag_events(flow, mime: QMimeData, position: QPoint):
    actions = Qt.DropAction.MoveAction
    buttons = Qt.MouseButton.LeftButton
    modifiers = Qt.KeyboardModifier.NoModifier
    return (
        QDragEnterEvent(position, actions, mime, buttons, modifiers),
        QDragMoveEvent(position, actions, mime, buttons, modifiers),
        QDropEvent(position, actions, mime, buttons, modifiers),
    )


def _hover_card(flow: ProgramFlow, mime: QMimeData, uid: str) -> QRect:
    """Enter a card drag; the magnified four-zone panel must appear."""

    rect = flow.canvas.rect_for_uid(uid)
    assert rect is not None, f"card {uid} is not visible in the flow"
    enter, move, _drop = _drag_events(flow, mime, rect.center())
    QApplication.sendEvent(flow.canvas, enter)
    QApplication.sendEvent(flow.canvas, move)
    panel = flow.canvas._panel_rect
    assert panel is not None, "hovering a card must anchor the four-zone panel"
    return panel


def _panel_point(panel: QRect, placement: DropPlacement) -> QPoint:
    strip = int(panel.height() * 0.34)
    if placement == DropPlacement.BEFORE:
        return QPoint(panel.center().x(), panel.top() + 2)
    if placement == DropPlacement.AFTER:
        return QPoint(panel.center().x(), panel.bottom() - 2)
    if placement == DropPlacement.CHILD:
        return QPoint(panel.left() + 4, panel.center().y())
    return QPoint(panel.right() - 4, panel.center().y())


def _send_drag(
    flow: ProgramFlow,
    mime: QMimeData,
    target_uid: str,
    placement: DropPlacement,
    *,
    expect_accepted: bool = True,
) -> QDropEvent:
    panel = _hover_card(flow, mime, target_uid)
    position = _panel_point(panel, placement)
    canvas = flow.canvas
    _enter, move, _ = _drag_events(flow, mime, position)
    QApplication.sendEvent(canvas, move)
    if expect_accepted:
        assert move.isAccepted(), "drag move must be accepted over a visible drop target"
    else:
        assert not move.isAccepted(), "an illegal drop zone must refuse the drag"
    _e, _m, drop = _drag_events(flow, mime, position)
    QApplication.sendEvent(canvas, drop)
    return drop


def _send_drag_at(flow: ProgramFlow, mime: QMimeData, position: QPoint) -> QDropEvent:
    """Drop onto a large direct landing (empty slot, new branch, root)."""

    canvas = flow.canvas
    enter, move, drop = _drag_events(flow, mime, position)
    QApplication.sendEvent(canvas, enter)
    QApplication.sendEvent(canvas, move)
    QApplication.sendEvent(canvas, drop)
    return drop


@pytest.mark.parametrize(
    ("source", "target", "placement", "top_level"),
    (
        ("b", "a", DropPlacement.BEFORE, ["container", "wrapper", "b", "a"]),
        ("a", "b", DropPlacement.AFTER, ["container", "wrapper", "b", "a"]),
        ("wrapper", "a", DropPlacement.WRAP, ["container", "wrapper", "b"]),
    ),
)
def test_real_drag_events_move_nodes_with_one_undoable_command(
    tmp_path, qapp_session, source, target, placement, top_level
):
    window = _window(tmp_path)
    session = window.session
    flow = window.program_tree
    before = session.program.semantic_data()

    drop = _send_drag(flow, _node_mime(source), target, placement)

    assert drop.isAccepted()
    assert session.undo_stack.count() == 1
    assert [node.uid for node in session.program.get_unit("stage").body] == top_level
    after = session.program.semantic_data()
    session.undo_stack.undo()
    assert session.program.semantic_data() == before
    session.undo_stack.redo()
    assert session.program.semantic_data() == after
    window.close()


def test_real_palette_drag_inserts_node_and_flashes_it(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    flow = window.program_tree
    mime = _drag_mime(window, "Wait")

    drop = _send_drag(flow, mime, "a", DropPlacement.BEFORE)

    assert drop.isAccepted()
    body = session.program.get_unit("stage").body
    assert body[2].kind == "Wait"
    assert session.undo_stack.count() == 1
    assert flow.canvas._flash_uid == body[2].uid
    session.undo_stack.undo()
    assert len(session.program.get_unit("stage").body) == 4
    window.close()


def test_invalid_drag_zone_is_rejected_without_model_changes(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    flow = window.program_tree
    before = session.program.semantic_data()

    feedback: list[str] = []
    flow.drop_feedback.connect(feedback.append)
    # Wrapping a plain Wait with an existing Repeat is not a legal move.
    drop = _send_drag(
        flow,
        _node_mime("container"),
        "a",
        DropPlacement.WRAP,
        expect_accepted=False,
    )

    assert not drop.isAccepted()
    assert session.program.semantic_data() == before
    assert session.undo_stack.count() == 0
    assert feedback and "不能" in feedback[-1] or "只有" in feedback[-1] or feedback[-1]
    window.close()


def test_empty_unit_root_landing_takes_the_first_node(tmp_path, qapp_session):
    root = _project(tmp_path / "authoring")
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage\n\n"
        "stage = Stage('stage', 'Empty Stage', body=[])\n",
        encoding="utf-8",
    )
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(root)
    session.select_unit("stage")
    window = EditorWindow(session)
    window.show()
    QApplication.processEvents()
    flow = window.program_tree
    canvas = flow.canvas
    landing = canvas._layout.root_landing
    assert landing is not None and landing.rect.height() >= 120

    drop = _send_drag_at(flow, _drag_mime(window, "Wait"), landing.rect.center())

    assert drop.isAccepted()
    body = session.program.get_unit("stage").body
    assert len(body) == 1 and body[0].kind == "Wait"
    assert session.undo_stack.count() == 1
    window.close()


def test_if_dual_slots_and_parallel_new_branch_accept_drops(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    flow = window.program_tree
    session.select_node("container")
    QApplication.processEvents()
    window.insert_palette_node("If", DropPlacement.AFTER, target_uid="container")
    condition = session.current_node_uid
    if_node = find_node(session.program, condition)[1]
    parallel_uid = None
    session.select_node("a")
    window.insert_palette_node("Parallel", DropPlacement.AFTER, target_uid="a")
    parallel_uid = session.current_node_uid

    landings = [
        element for element in flow.canvas._layout.elements if element.kind == "landing"
    ]
    slot_uids = {element.uid for element in landings}
    assert {if_node.uid} <= slot_uids  # 条件成立/否则 landings exist for the If
    new_branch = [
        element for element in flow.canvas._layout.elements if element.kind == "new_branch"
    ]
    assert any(element.uid == parallel_uid for element in new_branch)

    parallel = find_node(session.program, parallel_uid)[1]
    branch_landing = next(
        element.rect for element in new_branch if element.uid == parallel_uid
    )
    drop = _send_drag_at(flow, _drag_mime(window, "Wait"), branch_landing.center())
    assert drop.isAccepted()
    parallel_after = find_node(session.program, parallel_uid)[1]
    assert len(parallel_after.children["branches"]) == 2
    assert parallel_after.children["branches"][1].children["body"][0].kind == "Wait"
    assert session.undo_stack.count() == 3
    window.close()


def test_drop_preview_describes_the_full_result(tmp_path, qapp_session):
    window = _window(tmp_path)
    flow = window.program_tree
    feedback: list[str] = []
    flow.drop_feedback.connect(feedback.append)
    mime = _drag_mime(window, "Repeat")

    panel = _hover_card(flow, mime, "a")
    position = _panel_point(panel, DropPlacement.WRAP)
    _enter, move, _drop = _drag_events(flow, mime, position)
    QApplication.sendEvent(flow.canvas, move)

    assert feedback, "drag move must emit a result preview"
    assert "包裹" in feedback[-1] and "等待" in feedback[-1]
    assert flow.canvas._drop_check.allowed
    flow.canvas._end_drop()
    window.close()


def test_hover_over_collapsed_container_expands_after_450ms(tmp_path, qapp_session):
    window = _window(tmp_path)
    flow = window.program_tree
    canvas = flow.canvas
    canvas.collapse("container")
    QApplication.processEvents()
    assert "container" in canvas._collapsed

    rect = flow.canvas.rect_for_uid("container")
    assert rect is not None
    position = rect.center()
    mime = _node_mime("a")
    QApplication.sendEvent(
        canvas,
        QDragEnterEvent(
            position,
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    move_event = QDragMoveEvent(
        position,
        Qt.DropAction.MoveAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_event)
    qapp_session.processEvents()
    from src.qt_compat.QtTest import QTest

    QTest.qWait(520)
    QApplication.sendEvent(
        canvas,
        QDragMoveEvent(
            position,
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    qapp_session.processEvents()

    assert "container" not in canvas._collapsed
    canvas._end_drop()
    window.close()


def test_drag_near_the_bottom_edge_autoscrolls(tmp_path, qapp_session):
    window = _window(tmp_path)
    flow = window.program_tree
    canvas = flow.canvas
    for index in range(6):
        session = window.session
        session.select_node("b")
        window.insert_palette_node("Repeat", DropPlacement.AFTER, target_uid="b")
    QApplication.processEvents()
    bar = flow.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(0)
    position = QPoint(canvas.width() // 2, flow.viewport().height() - 2)
    mime = _node_mime("a")
    QApplication.sendEvent(
        canvas,
        QDragEnterEvent(
            position,
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    QApplication.sendEvent(
        canvas,
        QDragMoveEvent(
            position,
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )

    canvas._autoscroll_step()
    canvas._autoscroll_step()

    assert bar.value() > 0
    canvas._end_drop()
    window.close()


def test_collapse_keeps_selection_and_refolds_without_model_changes(
    tmp_path, qapp_session
):
    window = _window(tmp_path)
    session = window.session
    flow = window.program_tree
    before = session.program.semantic_data()

    flow.collapse("container")
    QApplication.processEvents()
    folded = [
        element
        for element in flow.canvas._layout.elements
        if element.kind == "folded" and element.uid == "container"
    ]
    assert folded, "collapsed container must show its fold hint"
    assert find_node(session.program, "container")[1].children["body"]

    flow.expand("container")
    QApplication.processEvents()
    assert session.program.semantic_data() == before
    assert session.undo_stack.count() == 0
    window.close()


def test_double_click_activates_node_for_parameter_focus(tmp_path, qapp_session):
    window = _window(tmp_path)
    flow = window.program_tree
    activated: list[str] = []
    flow.node_activated.connect(activated.append)
    canvas = flow.canvas
    rect = canvas.rect_for_uid("a")
    from src.qt_compat.QtCore import QEvent, QPointF
    from src.qt_compat.QtGui import QMouseEvent

    click = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        QPointF(rect.center()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, click)

    assert activated == ["a"]
    assert window.session.current_node_uid == "a"
    window.close()

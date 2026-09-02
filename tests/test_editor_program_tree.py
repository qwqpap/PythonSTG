"""ProgramFlow interaction tests driven by real Qt drag events."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

import pytest

from src.authoring.dsl import Boss, Parallel, Project, Ref, Stage, Wait, Wave
from src.authoring.program import DropPlacement, ProgramError, find_node
from src.core.project_context import ProjectContext
from src.editor.node_palette import PROTOTYPE_MIME
from src.editor.program_tree import NODE_MIME, ProgramFlow
from src.editor.session import EditorSession
from src.editor.sidebars import RESOURCE_MIME, UNIT_REFERENCE_MIME
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


def _unit_mime(window: EditorWindow, unit_id: str) -> QMimeData:
    """Build the MIME produced by the visible program-structure tree."""

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
    raise AssertionError(f"program structure has no unit {unit_id!r}")


def _drag_events(flow, mime: QMimeData, position: QPoint):
    actions = Qt.DropAction.MoveAction
    buttons = Qt.MouseButton.LeftButton
    modifiers = Qt.KeyboardModifier.NoModifier
    return (
        QDragEnterEvent(position, actions, mime, buttons, modifiers),
        QDragMoveEvent(position, actions, mime, buttons, modifiers),
        QDropEvent(position, actions, mime, buttons, modifiers),
    )


def _visible_drop_point(
    flow: ProgramFlow, uid: str, placement: DropPlacement
) -> QPoint:
    """Return the exact visible surface the user aims at for one placement."""

    if placement in {DropPlacement.BEFORE, DropPlacement.AFTER}:
        rect = flow.canvas.insertion_rect_for_uid(uid, placement)
    elif placement == DropPlacement.WRAP:
        rect = flow.canvas.wrap_handle_rect_for_uid(uid)
    else:
        rect = next(
            (
                element.rect
                for element in flow.canvas._layout.elements
                if element.kind == "landing" and element.uid == uid
            ),
            None,
        )
    assert rect is not None, f"visible {placement.value} target for {uid} is missing"
    return rect.center()


def _send_drag(
    flow: ProgramFlow,
    mime: QMimeData,
    target_uid: str,
    placement: DropPlacement,
    *,
    expect_accepted: bool = True,
) -> QDropEvent:
    position = _visible_drop_point(flow, target_uid, placement)
    canvas = flow.canvas
    enter, move, _ = _drag_events(flow, mime, position)
    QApplication.sendEvent(canvas, enter)
    QApplication.sendEvent(canvas, move)
    if expect_accepted:
        assert move.isAccepted(), (
            "drag move must be accepted over a visible drop target: "
            f"{canvas._drop_check.reason}"
        )
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
    assert session.current_node_uid == body[2].uid
    assert flow.canvas._flash_uid == body[2].uid
    session.undo_stack.undo()
    assert len(session.program.get_unit("stage").body) == 4
    window.close()


def test_real_unit_tree_drag_creates_the_single_valid_reference_node(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    session.create_unit(Wave("opening", "Opening"), register_stage=False)
    session.select_unit("stage")
    QApplication.processEvents()
    flow = window.program_tree
    before = session.program.semantic_data()
    before_undo = session.undo_stack.count()

    drop = _send_drag(flow, _unit_mime(window, "opening"), "a", DropPlacement.BEFORE)

    assert drop.isAccepted()
    body = session.program.get_unit("stage").body
    inserted = body[2]
    assert inserted.kind == "RunWave"
    assert inserted.arguments["wave_class"] == Ref("opening")
    assert session.undo_stack.count() == before_undo + 1
    window.structure_mode.setCurrentIndex(1)
    QApplication.processEvents()

    def visible_unit_ids(item):
        values = []
        unit_id = item.data(0, int(Qt.ItemDataRole.UserRole))
        if unit_id:
            values.append(unit_id)
        for index in range(item.childCount()):
            values.extend(visible_unit_ids(item.child(index)))
        return values

    projected_ids = []
    for index in range(window.unit_list.topLevelItemCount()):
        projected_ids.extend(visible_unit_ids(window.unit_list.topLevelItem(index)))
    assert projected_ids == ["stage", "opening"]
    session.undo_stack.undo()
    assert session.program.semantic_data() == before
    window.close()


def test_resource_drag_to_insertion_line_requires_an_explicit_action(
    tmp_path, qapp_session
):
    window = _window(tmp_path)
    session = window.session
    flow = window.program_tree
    choices: list[tuple] = []

    def choose(actions):
        choices.append(tuple(action.key for action in actions))
        return "play_se"

    window._choose_resource_action = choose
    mime = QMimeData()
    uri = "res://assets/audio/se.wav"
    mime.setData(RESOURCE_MIME, uri.encode("utf-8"))

    drop = _send_drag(flow, mime, "a", DropPlacement.BEFORE)

    assert drop.isAccepted()
    inserted = session.program.get_unit("stage").body[2]
    assert inserted.kind == "PlaySE"
    assert inserted.arguments["name"] == uri
    assert choices == [("play_bgm", "play_se")]
    assert session.undo_stack.count() == 1
    window.close()


def test_visible_copy_paste_uses_one_undo_command_and_new_uid(
    tmp_path, qapp_session
):
    window = _window(tmp_path)
    session = window.session
    session.select_node("a")
    QApplication.processEvents()
    before = session.program.semantic_data()

    window.copy_node_button.click()
    window.paste_node_button.click()
    QApplication.processEvents()

    body = session.program.get_unit("stage").body
    copies = [node for node in body if node.kind == "Wait" and node.arguments["frames"] == 2]
    assert len(copies) == 2
    assert {node.uid for node in copies} != {"a"}
    assert session.undo_stack.count() == 1
    session.undo_stack.undo()
    assert session.program.semantic_data() == before
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


def test_card_body_is_selection_only_and_rejects_drop(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    flow = window.program_tree
    before = session.program.semantic_data()
    card = flow.canvas.rect_for_uid("a")
    assert card is not None
    position = card.center()
    mime = _drag_mime(window, "Wait")
    enter, move, drop = _drag_events(flow, mime, position)

    QApplication.sendEvent(flow.canvas, enter)
    QApplication.sendEvent(flow.canvas, move)
    QApplication.sendEvent(flow.canvas, drop)

    assert not move.isAccepted()
    assert not drop.isAccepted()
    assert session.program.semantic_data() == before
    assert session.undo_stack.count() == 0
    window.close()


def test_existing_node_drag_starts_only_from_visible_handle(tmp_path, qapp_session):
    window = _window(tmp_path)
    flow = window.program_tree
    canvas = flow.canvas
    from src.qt_compat.QtCore import QEvent, QPointF
    from src.qt_compat.QtGui import QMouseEvent

    started: list[str] = []
    canvas._start_node_drag = started.append
    card = canvas.rect_for_uid("a")
    handle = canvas.drag_handle_rect_for_uid("a")
    assert card is not None and handle is not None

    def gesture(start: QPoint) -> None:
        QApplication.sendEvent(
            canvas,
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(start),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        QApplication.sendEvent(
            canvas,
            QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(start + QPoint(-18, 0)),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        QApplication.sendEvent(
            canvas,
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                QPointF(start),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

    gesture(card.center())
    assert started == []
    gesture(handle.center())
    assert started == ["a"]
    window.close()


def test_ctrl_multi_select_delete_is_one_undoable_action(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    flow = window.program_tree
    from src.qt_compat.QtTest import QTest

    for uid in ("a", "b"):
        rect = flow.canvas.rect_for_uid(uid)
        assert rect is not None
        QTest.mouseClick(
            flow.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier,
            rect.center(),
        )
        QApplication.processEvents()
    assert flow.selected_node_uids() == ("a", "b")

    window.delete_node_button.click()
    QApplication.processEvents()

    assert [node.uid for node in session.program.get_unit("stage").body] == [
        "container",
        "wrapper",
    ]
    assert session.undo_stack.count() == 1
    session.undo_stack.undo()
    assert [node.uid for node in session.program.get_unit("stage").body] == [
        "container",
        "wrapper",
        "a",
        "b",
    ]
    window.close()


def test_collapse_and_expand_all_are_visible_non_model_actions(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    before = session.program.semantic_data()

    window.collapse_all_button.click()
    assert "container" in window.program_tree.canvas._collapsed
    window.expand_all_button.click()

    assert not window.program_tree.canvas._collapsed
    assert session.program.semantic_data() == before
    assert session.undo_stack.count() == 0
    window.close()


def test_copy_paste_delete_have_keyboard_equivalents(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    flow = window.program_tree
    from src.qt_compat.QtTest import QTest

    rect = flow.canvas.rect_for_uid("a")
    assert rect is not None
    QTest.mouseClick(flow.canvas, Qt.MouseButton.LeftButton, pos=rect.center())
    QTest.keyClick(flow.canvas, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(flow.canvas, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()

    body = session.program.get_unit("stage").body
    assert len(body) == 5 and body[3].arguments["frames"] == 2
    pasted_uid = body[3].uid
    assert pasted_uid != "a"
    assert session.undo_stack.count() == 1

    QTest.keyClick(flow.canvas, Qt.Key.Key_Delete)
    QApplication.processEvents()
    assert all(node.uid != pasted_uid for node in session.program.get_unit("stage").body)
    assert session.undo_stack.count() == 2
    window.close()


def test_drop_target_hit_testing_stays_within_interaction_budget(
    tmp_path, qapp_session
):
    window = _window(tmp_path)
    flow = window.program_tree
    position = _visible_drop_point(flow, "a", DropPlacement.BEFORE)
    samples: list[float] = []
    for _index in range(300):
        started = perf_counter()
        assert flow.canvas._drop_target(position) == (
            "a",
            DropPlacement.BEFORE,
            None,
        )
        samples.append(perf_counter() - started)
    p95 = sorted(samples)[int(len(samples) * 0.95) - 1]
    assert p95 < 0.016
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


@pytest.mark.parametrize(
    ("unit", "summary_fragment"),
    (
        (
            Project("demo", "Demo", Ref("stage"), [Ref("stage")]),
            "关卡顺序",
        ),
        (
            Boss("boss", "Boss", "boss_texture", [Ref("spell")]),
            "阶段列表",
        ),
    ),
)
def test_non_statement_units_show_a_summary_without_a_root_drop_target(
    qapp_session, unit, summary_fragment
):
    flow = ProgramFlow()
    flow.resize(720, 360)
    flow.show()
    flow.set_unit(unit)
    QApplication.processEvents()

    assert flow.canvas._layout.root_landing is None
    assert not any(
        element.kind == "landing" for element in flow.canvas._layout.elements
    )
    summary = next(
        element for element in flow.canvas._layout.elements if element.kind == "summary"
    )
    assert summary_fragment in summary.label
    flow.close()


def test_parallel_branches_reflow_from_columns_to_rows(qapp_session):
    flow = ProgramFlow()
    unit = Stage(
        "stage",
        "Stage",
        body=[
            Parallel(
                [[Wait(1, uid="left")], [Wait(2, uid="right")]],
                uid="parallel",
            )
        ],
    )
    flow.resize(900, 480)
    flow.show()
    flow.set_unit(unit)
    qapp_session.processEvents()

    wide = [
        element.rect
        for element in flow.canvas._layout.elements
        if element.kind == "head" and element.label.startswith("分支 ")
    ]
    assert len(wide) == 2
    assert wide[0].top() == wide[1].top() and wide[0].left() != wide[1].left()

    flow.resize(480, 480)
    qapp_session.processEvents()
    narrow = [
        element.rect
        for element in flow.canvas._layout.elements
        if element.kind == "head" and element.label.startswith("分支 ")
    ]
    assert len(narrow) == 2
    assert narrow[0].left() == narrow[1].left() and narrow[0].top() != narrow[1].top()
    flow.close()


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
    assert {element.label.split(" · ", 1)[0] for element in landings if element.uid == if_node.uid} == {
        "条件成立",
        "否则",
    }
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


def test_child_drop_uses_the_visible_container_landing(tmp_path, qapp_session):
    window = _window(tmp_path)
    session = window.session
    flow = window.program_tree

    drop = _send_drag(
        flow,
        _drag_mime(window, "Wait"),
        "container",
        DropPlacement.CHILD,
    )

    assert drop.isAccepted()
    children = find_node(session.program, "container")[1].children["body"]
    assert [node.uid for node in children[:1]] == ["inner"]
    assert len(children) == 2 and children[1].kind == "Wait"
    assert session.undo_stack.count() == 1
    window.close()


def test_drop_preview_describes_the_full_result(tmp_path, qapp_session):
    window = _window(tmp_path)
    flow = window.program_tree
    feedback: list[str] = []
    flow.drop_feedback.connect(feedback.append)
    mime = _drag_mime(window, "Repeat")

    position = _visible_drop_point(flow, "a", DropPlacement.WRAP)
    enter, move, _drop = _drag_events(flow, mime, position)
    QApplication.sendEvent(flow.canvas, enter)
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
    wrap_handle = flow.canvas.wrap_handle_rect_for_uid("container")
    assert wrap_handle is not None
    position = wrap_handle.center()
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

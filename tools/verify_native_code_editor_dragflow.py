"""Real Windows gate for the drag-driven editor workflow.

This verifier refuses offscreen/minimal Qt.  It opens an exposed top-level
PySide6 window and exercises the current interaction contract: visible
insertion lines, container landings, the dedicated wrap handle, physical
Win32 mouse drags, edge auto-scroll, Inspector edits, Undo/Redo, and the
Parallel side-by-side/stacked branch layout at both required sizes.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.authoring.program import DropPlacement, find_node
from src.core.project_context import ProjectContext
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtCore import QPoint, Qt, QTimer
from src.qt_compat.QtGui import (
    QCursor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
)
from src.qt_compat.QtWidgets import QApplication


REQUIRED_SIZES = ((1480, 920), (960, 640))
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004


def _write_project(root: Path) -> Path:
    authoring = root / "game_content" / "authoring" / "native_dragflow"
    authoring.mkdir(parents=True)
    (authoring / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('native_dragflow', 'Native DragFlow', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
        newline="\n",
    )
    (authoring / "stage.py").write_text(
        "from src.authoring.dsl import If, Parallel, Repeat, Stage, Wait\n\n"
        "stage = Stage(\n"
        "    'stage',\n"
        "    'Stage',\n"
        "    body=[\n"
        "        Wait(12, uid='wait'),\n"
        "        Repeat(2, body=[Wait(1, uid='inner')], uid='container'),\n"
        "        If(True, body=[Wait(1)], uid='branch'),\n"
        "        Parallel([[Wait(1)], [Wait(2)]], uid='par'),\n"
        "    ],\n"
        ")\n",
        encoding="utf-8",
        newline="\n",
    )
    return authoring


def _process_events(app: QApplication, rounds: int = 6) -> None:
    for _ in range(rounds):
        app.processEvents()


def _palette_mime(window: EditorWindow, kind: str):
    palette = window.node_palette

    def walk(item):
        yield item
        for index in range(item.childCount()):
            yield from walk(item.child(index))

    role = int(Qt.ItemDataRole.UserRole)
    for top in range(palette.tree.topLevelItemCount()):
        for item in walk(palette.tree.topLevelItem(top)):
            if item.data(0, role) == kind and not item.isDisabled():
                return palette.tree.mimeData([item])
    raise AssertionError(f"palette entry {kind!r} is not available")


def _drag_events(flow, mime, position):
    actions = Qt.DropAction.MoveAction
    buttons = Qt.MouseButton.LeftButton
    modifiers = Qt.KeyboardModifier.NoModifier
    enter = QDragEnterEvent(position, actions, mime, buttons, modifiers)
    move = QDragMoveEvent(position, actions, mime, buttons, modifiers)
    drop = QDropEvent(position, actions, mime, buttons, modifiers)
    return enter, move, drop


def _visible_drop_point(
    flow,
    uid: str,
    placement: DropPlacement | str,
    slot: str | None = None,
) -> QPoint:
    """Resolve the exact painted target used by ProgramFlow hit testing."""

    placement = DropPlacement(placement)
    if placement in {DropPlacement.BEFORE, DropPlacement.AFTER}:
        rect = flow.canvas.insertion_rect_for_uid(uid, placement)
    elif placement == DropPlacement.WRAP:
        rect = flow.canvas.wrap_handle_rect_for_uid(uid)
    else:
        rect = next(
            (
                element.rect
                for element in flow.canvas._layout.elements
                if element.kind == "landing"
                and element.uid == uid
                and (slot is None or element.slot == slot)
            ),
            None,
        )
    if rect is None:
        raise AssertionError(
            f"visible {placement.value} target for {uid!r}/{slot!r} is missing"
        )
    return rect.center()


def _palette_item(window: EditorWindow, kind: str):
    """Return the visible draggable palette row for an enabled prototype."""

    role = int(Qt.ItemDataRole.UserRole)

    def walk(item):
        yield item
        for index in range(item.childCount()):
            yield from walk(item.child(index))

    for top in range(window.node_palette.tree.topLevelItemCount()):
        for item in walk(window.node_palette.tree.topLevelItem(top)):
            if item.data(0, role) == kind and not item.isDisabled():
                window.node_palette.tree.scrollToItem(item)
                QApplication.processEvents()
                return item
    raise AssertionError(f"palette entry {kind!r} is not available")


def _to_physical(window, point: QPoint) -> QPoint:
    """Win32 SetCursorPos takes physical pixels; Qt widget geometry is logical.

    Without this conversion a display scale factor such as 125% offsets every
    physical gesture away from the widget the Qt coordinates describe.
    """

    ratio = window.devicePixelRatioF()
    if abs(ratio - 1.0) <= 1e-9:
        return point
    return QPoint(round(point.x() * ratio), round(point.y() * ratio))


def _move_cursor(
    user32,
    start: QPoint,
    end: QPoint,
    steps: int = 12,
    *,
    to_physical=None,
) -> None:
    for index in range(1, steps + 1):
        ratio = index / steps
        x = round(start.x() + (end.x() - start.x()) * ratio)
        y = round(start.y() + (end.y() - start.y()) * ratio)
        if to_physical is not None:
            physical = to_physical(QPoint(x, y))
            x, y = physical.x(), physical.y()
        if not user32.SetCursorPos(x, y):
            raise OSError(ctypes.get_last_error(), "SetCursorPos failed")
        time.sleep(0.018)


def _physical_palette_drop(
    app: QApplication,
    window: EditorWindow,
    kind: str,
    target_uid: str,
    placement: DropPlacement | str,
    *,
    slot: str | None = None,
) -> None:
    """Perform one actual Windows mouse drag from the palette into ProgramFlow.

    Directly constructing ``QDropEvent`` is useful for exact widget contracts,
    but it cannot prove that a human mouse gesture starts ``QDrag``.  This gate
    uses Win32 cursor and button input while Qt runs its native nested drag loop.
    The original cursor position is restored even when the gesture fails.
    """

    if sys.platform != "win32":
        raise RuntimeError("physical mouse gate requires Windows")
    placement = DropPlacement(placement)
    tree = window.node_palette.tree
    item = _palette_item(window, kind)
    item_rect = tree.visualItemRect(item)
    if item_rect.isEmpty():
        raise RuntimeError(f"palette row {kind!r} is not visible")
    source = tree.viewport().mapToGlobal(item_rect.center())
    flow = window.program_tree
    # The verifier project keeps all three targets at the top of the flow.
    # Pinning the scroll position also makes screen coordinates independent of
    # QScrollArea's platform-specific child translation during native QDrag.
    flow.verticalScrollBar().setValue(0)
    _process_events(app)
    canvas = window.program_tree.canvas
    card = canvas._layout.cards.get(target_uid)
    if card is None:
        raise RuntimeError(f"target card {target_uid!r} is not visible")
    target_local = _visible_drop_point(flow, target_uid, placement, slot)
    target = canvas.mapToGlobal(target_local)
    approach = canvas.mapToGlobal(QPoint(-8, target_local.y()))
    original = QCursor.pos()
    error: list[BaseException] = []
    released = threading.Event()
    target_ready = threading.Event()
    observed_candidates: list[tuple[object, object, object]] = []
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    to_physical = lambda point: _to_physical(window, point)

    ready_timer = QTimer(window)

    def observe_target() -> None:
        # These gestures prove exact drop geometry, not scrolling.  Keep the
        # fixed verifier targets stationary while the pointer travels from the
        # palette; auto-scroll has its own physical gate below.
        flow.verticalScrollBar().setValue(0)
        canvas._autoscroll_direction = 0
        canvas._autoscroll_timer.stop()
        candidate = canvas._drop_candidate
        state = (
            candidate,
            canvas._drop_check.allowed,
            canvas.mapFromGlobal(QCursor.pos()),
        )
        if not observed_candidates or observed_candidates[-1] != state:
            observed_candidates.append(state)
        if (
            candidate == (target_uid, placement, slot)
            and canvas._drop_check.allowed
        ):
            target_ready.set()

    ready_timer.timeout.connect(observe_target)
    ready_timer.start(10)

    def gesture() -> None:
        button_down = False
        try:
            time.sleep(0.12)
            user32.SetForegroundWindow(int(window.winId()))
            press = to_physical(source)
            if not user32.SetCursorPos(press.x(), press.y()):
                raise OSError(ctypes.get_last_error(), "SetCursorPos failed")
            time.sleep(0.08)
            user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            button_down = True
            time.sleep(0.06)
            # Cross QApplication.startDragDistance() before heading to the card.
            threshold = QPoint(source.x() + 24, source.y())
            _move_cursor(user32, source, threshold, 4, to_physical=to_physical)
            # Stay left of ProgramFlow until the target y-coordinate is
            # reached.  A diagonal path through the bottom edge legitimately
            # arms auto-scroll and moves the narrow insertion line.
            _move_cursor(user32, threshold, approach, 12, to_physical=to_physical)
            _move_cursor(user32, approach, target, 10, to_physical=to_physical)
            if not target_ready.wait(1.5):
                raise RuntimeError(
                    f"physical cursor never activated {placement.value} "
                    f"for {target_uid!r}/{slot!r}; "
                    f"observed={observed_candidates!r}"
                )
            time.sleep(0.10)
            user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            button_down = False
            # Let Qt's nested QDrag loop consume the native button-up before
            # restoring the user's cursor.  Restoring too early can turn an
            # otherwise valid release into a final move outside the target.
            time.sleep(0.25)
        except BaseException as exc:  # surfaced on the Qt/main thread below
            error.append(exc)
        finally:
            if button_down:
                user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.05)
            restore = to_physical(original)
            user32.SetCursorPos(restore.x(), restore.y())
            released.set()

    window.raise_()
    window.activateWindow()
    app.processEvents()
    worker = threading.Thread(target=gesture, name="pystg-physical-drag", daemon=True)
    worker.start()
    deadline = time.monotonic() + 5.0
    while not released.is_set() and time.monotonic() < deadline:
        # This call may enter QDrag.exec(); the worker continues issuing native
        # input until the release lets that nested event loop return.
        app.processEvents()
        time.sleep(0.005)
    worker.join(timeout=0.5)
    ready_timer.stop()
    app.processEvents()
    if worker.is_alive() or not released.is_set():
        raise RuntimeError("physical mouse drag timed out")
    if error:
        raise RuntimeError(f"physical mouse drag failed: {error[0]}") from error[0]


def _assert_physical_palette_drop(
    app: QApplication,
    window: EditorWindow,
    kind: str,
    target_uid: str,
    placement: DropPlacement,
    *,
    slot: str | None = None,
) -> str:
    """Verify one real mouse drop, its exact result, and one-step Undo/Redo."""

    session = window.session
    flow = window.program_tree
    before = session.program.semantic_data()
    before_index = session.undo_stack.index()
    feedback: list[str] = []
    flow.drop_feedback.connect(feedback.append)
    try:
        _physical_palette_drop(
            app,
            window,
            kind,
            target_uid,
            placement,
            slot=slot,
        )
    finally:
        flow.drop_feedback.disconnect(feedback.append)
    _process_events(app)
    inserted_uid = session.current_node_uid
    if not inserted_uid or inserted_uid == target_uid:
        raise RuntimeError(
            f"physical {placement.value} drop did not select a new node: "
            f"selected={inserted_uid!r} feedback={feedback!r}"
        )
    if session.undo_stack.index() != before_index + 1:
        raise RuntimeError(
            f"physical {placement.value} drop did not create exactly one undo step: "
            f"before={before_index} after={session.undo_stack.index()} "
            f"selected={inserted_uid!r} feedback={feedback!r}"
        )

    stage = session.program.get_unit("stage")
    if placement == DropPlacement.AFTER:
        body_uids = [node.uid for node in stage.body]
        target_index = body_uids.index(target_uid)
        if body_uids[target_index + 1] != inserted_uid:
            raise RuntimeError(
                f"physical insertion-line drop landed at the wrong index: "
                f"selected={inserted_uid!r} body={body_uids!r} feedback={feedback!r}"
            )
        marker = "之后"
    elif placement == DropPlacement.CHILD:
        target = find_node(session.program, target_uid)[1]
        children = target.children.get(slot or "body", [])
        if not children or children[-1].uid != inserted_uid:
            raise RuntimeError(
                f"physical child drop missed {target_uid!r}/{slot!r}: "
                f"children={[node.uid for node in children]!r}"
            )
        marker = "放入"
    elif placement == DropPlacement.WRAP:
        wrapper = find_node(session.program, inserted_uid)[1]
        wrapped = [
            child.uid
            for children in wrapper.children.values()
            for child in children
        ]
        if wrapper.kind != kind or target_uid not in wrapped:
            raise RuntimeError(
                f"physical wrap missed {target_uid!r}: "
                f"wrapper={wrapper.kind!r} children={wrapped!r}"
            )
        marker = "包裹"
    else:
        raise AssertionError(f"unsupported native placement: {placement}")
    if not any(marker in message for message in feedback):
        raise RuntimeError(
            f"physical {placement.value} drop emitted no clear preview: {feedback!r}"
        )

    session.undo_stack.undo()
    _process_events(app)
    if session.program.semantic_data() != before or session.undo_stack.index() != before_index:
        raise RuntimeError(f"undo did not restore the physical {placement.value} drop")
    session.undo_stack.redo()
    _process_events(app)
    if session.program.semantic_data() == before:
        raise RuntimeError(f"redo did not restore the physical {placement.value} drop")
    session.undo_stack.undo()
    _process_events(app)
    if session.program.semantic_data() != before:
        raise RuntimeError(f"second undo did not restore the {placement.value} drop")
    return inserted_uid


def _physical_node_autoscroll(
    app: QApplication,
    window: EditorWindow,
    source_uid: str,
) -> None:
    """Hold a real existing-node drag at the bottom edge until it scrolls."""

    if sys.platform != "win32":
        raise RuntimeError("physical mouse gate requires Windows")
    session = window.session
    flow = window.program_tree
    canvas = flow.canvas
    bar = flow.verticalScrollBar()
    bar.setValue(0)
    _process_events(app)
    if bar.maximum() <= 0:
        raise RuntimeError("autoscroll fixture is not taller than the viewport")
    handle = canvas.drag_handle_rect_for_uid(source_uid)
    if handle is None:
        raise RuntimeError(f"drag handle for {source_uid!r} is not visible")
    source = canvas.mapToGlobal(handle.center())
    target = canvas.mapToGlobal(QPoint(2, flow.viewport().height() - 2))
    before = session.program.semantic_data()
    before_index = session.undo_stack.index()
    original = QCursor.pos()
    error: list[BaseException] = []
    released = threading.Event()
    scrolled = threading.Event()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    to_physical = lambda point: _to_physical(window, point)
    observer = QTimer(window)

    def observe_scroll() -> None:
        if bar.value() > 0 and canvas._autoscroll_timer.isActive():
            scrolled.set()

    observer.timeout.connect(observe_scroll)
    observer.start(10)

    def gesture() -> None:
        button_down = False
        try:
            time.sleep(0.12)
            user32.SetForegroundWindow(int(window.winId()))
            press = to_physical(source)
            if not user32.SetCursorPos(press.x(), press.y()):
                raise OSError(ctypes.get_last_error(), "SetCursorPos failed")
            time.sleep(0.08)
            user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            button_down = True
            threshold = QPoint(source.x() - 24, source.y())
            _move_cursor(user32, source, threshold, 4, to_physical=to_physical)
            _move_cursor(user32, threshold, target, 18, to_physical=to_physical)
            if not scrolled.wait(1.5):
                raise RuntimeError("physical node drag did not trigger edge auto-scroll")
            time.sleep(0.10)
            user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            button_down = False
            time.sleep(0.20)
        except BaseException as exc:
            error.append(exc)
        finally:
            if button_down:
                user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.05)
            restore = to_physical(original)
            user32.SetCursorPos(restore.x(), restore.y())
            released.set()

    window.raise_()
    window.activateWindow()
    app.processEvents()
    worker = threading.Thread(
        target=gesture,
        name="pystg-physical-autoscroll",
        daemon=True,
    )
    worker.start()
    deadline = time.monotonic() + 5.0
    while not released.is_set() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    worker.join(timeout=0.5)
    observer.stop()
    canvas._end_drop()
    app.processEvents()
    if worker.is_alive() or not released.is_set():
        raise RuntimeError("physical auto-scroll drag timed out")
    if error:
        raise RuntimeError(f"physical auto-scroll drag failed: {error[0]}") from error[0]
    if bar.value() <= 0:
        raise RuntimeError("physical auto-scroll did not move the scrollbar")
    if session.program.semantic_data() != before or session.undo_stack.index() != before_index:
        raise RuntimeError("cancelled physical auto-scroll drag mutated the program")


def verify_native_dragflow() -> dict[str, object]:
    platform_override = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if platform_override in {"offscreen", "minimal"}:
        raise RuntimeError(f"native gate refuses QT_QPA_PLATFORM={platform_override!r}")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    if app.platformName().lower() != "windows":
        raise RuntimeError(f"native gate requires Qt windows platform, got {app.platformName()!r}")

    observations: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="pystg-dragflow-native-") as temporary:
        project_root = Path(temporary)
        authoring = _write_project(project_root)
        session = EditorSession(project_context=ProjectContext(project_root))
        session.open_project(authoring)
        window = EditorWindow(session)
        window.show()
        _process_events(app)
        handle = window.windowHandle()
        if handle is None or not handle.isExposed() or int(window.winId()) == 0:
            raise RuntimeError("top-level editor window was not exposed as a real native window")

        # Keep the contract panels visible.  The gate must exercise the real
        # layout authors receive, not a widened test-only editor surface.
        window.inspector_dock.show()
        window.timeline_dock.show()
        window.output_dock.hide()
        session.select_unit("stage")
        session.select_node("wait")
        _process_events(app)

        for width, height in REQUIRED_SIZES:
            window.resize(width, height)
            _process_events(app)
            if (window.width(), window.height()) != (width, height):
                raise RuntimeError(
                    f"native window refused required size {width}x{height}: "
                    f"actual={window.width()}x{window.height()}"
                )
            flow = window.program_tree
            canvas = flow.canvas

            # 1. Palette search narrows the visible tree.
            window.node_palette.search.setText("重复")
            _process_events(app)
            if window.node_palette.tree.topLevelItemCount() == 0:
                raise RuntimeError("palette search produced no categories")
            matching = 0

            def walk(item):
                nonlocal matching
                for index in range(item.childCount()):
                    child = item.child(index)
                    if "重复" in child.text(0):
                        matching += 1
                    walk(child)

            for top in range(window.node_palette.tree.topLevelItemCount()):
                walk(window.node_palette.tree.topLevelItem(top))
            if matching < 1:
                raise RuntimeError("palette search did not surface the Repeat entry")
            window.node_palette.search.setText("")
            _process_events(app)

            # 2. Each current drop surface maps to exactly one placement.  The
            # card body itself is deliberately not a drop surface.
            targets = {}
            mime = _palette_mime(window, "Repeat")
            for placement, slot in (
                (DropPlacement.BEFORE, None),
                (DropPlacement.AFTER, None),
                (DropPlacement.CHILD, "body"),
                (DropPlacement.WRAP, None),
            ):
                position = _visible_drop_point(flow, "container", placement, slot)
                enter, _move, _drop = _drag_events(flow, mime, position)
                QApplication.sendEvent(canvas, enter)
                _enter, move, _drop = _drag_events(flow, mime, position)
                QApplication.sendEvent(canvas, move)
                _process_events(app)
                if not move.isAccepted():
                    raise RuntimeError(
                        f"drag move refused at visible {placement.value} target: "
                        f"{canvas._drop_check.reason}"
                    )
                candidate = flow.canvas._drop_candidate
                targets[placement.value] = (
                    candidate[1].value if candidate else None,
                    candidate[2] if candidate else None,
                )
            expected = {
                "before": ("before", None),
                "after": ("after", None),
                "child": ("child", "body"),
                "wrap": ("wrap", None),
            }
            if targets != expected:
                raise RuntimeError(f"visible drop target mapping wrong: {targets}")
            card = canvas.rect_for_uid("container")
            if card is None:
                raise RuntimeError("container card is not visible")
            card_body = QPoint(card.center().x(), card.center().y())
            enter, move, _drop = _drag_events(flow, mime, card_body)
            QApplication.sendEvent(canvas, enter)
            QApplication.sendEvent(canvas, move)
            if move.isAccepted() or canvas._drop_candidate is not None:
                raise RuntimeError("card body still behaves like an invisible drop zone")
            canvas._end_drop()

            # 3. Real Win32 mouse drags prove the three distinct targets.  Each
            # gesture creates one command and survives one Undo/Redo roundtrip.
            _assert_physical_palette_drop(
                app,
                window,
                "Wait",
                "container",
                DropPlacement.AFTER,
            )
            _assert_physical_palette_drop(
                app,
                window,
                "Wait",
                "container",
                DropPlacement.CHILD,
                slot="body",
            )
            _assert_physical_palette_drop(
                app,
                window,
                "Repeat",
                "wait",
                DropPlacement.WRAP,
            )

            # 4. A real existing-node drag held at the bottom edge scrolls but
            # does not mutate when released outside a visible target.
            session.select_node("wait")
            for _ in range(4):
                window.insert_palette_node("Repeat", "after", target_uid="wait")
            _process_events(app)
            _physical_node_autoscroll(app, window, "wait")
            for _ in range(4):
                session.undo_stack.undo()
            flow.verticalScrollBar().setValue(0)
            _process_events(app)

            # 5. The visible selection plus standard shortcuts copy/paste as
            # one undoable user action.
            from src.qt_compat.QtTest import QTest

            session.select_node("wait")
            flow.selected_uids = {"wait"}
            flow.selected_uid = "wait"
            flow.canvas.setFocus()
            before_copy = session.program.semantic_data()
            before_copy_index = session.undo_stack.index()
            QTest.keyClick(
                flow.canvas,
                Qt.Key.Key_C,
                Qt.KeyboardModifier.ControlModifier,
            )
            QTest.keyClick(
                flow.canvas,
                Qt.Key.Key_V,
                Qt.KeyboardModifier.ControlModifier,
            )
            _process_events(app)
            if session.program.semantic_data() == before_copy:
                raise RuntimeError("Ctrl+C/Ctrl+V did not paste the selected node")
            if session.undo_stack.index() != before_copy_index + 1:
                raise RuntimeError("paste did not create one undoable action")
            session.undo_stack.undo()
            _process_events(app)
            if session.program.semantic_data() != before_copy:
                raise RuntimeError("one undo did not remove the pasted node")

            # 6. Inspector edit via the visible field plus Undo/Redo.
            session.select_node("wait")
            _process_events(app)
            from src.qt_compat.QtWidgets import QSpinBox

            frames = window.inspector.findChild(QSpinBox, "argument_frames")
            if frames is None:
                raise RuntimeError("Inspector did not expose the Wait frames field")
            frames.setValue(48)
            frames.editingFinished.emit()
            _process_events(app)
            if session.current_node.arguments["frames"] != 48:
                raise RuntimeError("Inspector edit did not commit")
            session.undo_stack.undo()
            if session.current_node.arguments["frames"] != 12:
                raise RuntimeError("undo did not restore the argument")
            session.undo_stack.redo()
            session.undo_stack.undo()

            # 7. Parallel branches: side by side when wide, stacked when narrow.
            def branch_heads():
                heads = [
                    element
                    for element in flow.canvas._layout.elements
                    if element.kind == "head"
                    and element.node is not None
                    and element.node.kind == "Branch"
                    and element.uid.startswith("par__branch")
                ]
                if len(heads) != 2:
                    raise RuntimeError("Parallel layout did not expose two branch heads")
                return heads[0].rect, heads[1].rect

            flow.canvas.relayout()
            _process_events(app)
            wide_rect_a, wide_rect_b = branch_heads()
            side_by_side = (
                wide_rect_a.top() == wide_rect_b.top()
                and wide_rect_a.left() < wide_rect_b.left()
            )
            stacked = (
                wide_rect_a.left() == wide_rect_b.left()
                and wide_rect_a.top() < wide_rect_b.top()
            )
            # The interaction spec: wide screens render Parallel branches side
            # by side, small windows stack them vertically.  1480x920 is the
            # wide case; 960x640 is the small case.
            if width == 1480 and not side_by_side:
                raise RuntimeError(
                    f"1480x920 must render Parallel branches side by side: "
                    f"a={wide_rect_a} b={wide_rect_b} canvas={flow.canvas.width()}"
                )
            if width == 960 and not stacked:
                raise RuntimeError(
                    f"960x640 must stack Parallel branches vertically: "
                    f"a={wide_rect_a} b={wide_rect_b} canvas={flow.canvas.width()}"
                )
            _process_events(app)
            par = flow.canvas.rect_for_uid("par")
            observations.append(
                {
                    "size": f"{width}x{height}",
                    "parallel_card_width": par.width(),
                    "physical_mouse_targets": ["after", "child", "wrap"],
                    "physical_autoscroll": True,
                    "shortcut_copy_paste": True,
                    "undo_redo": True,
                    "inspector_visible": window.inspector_dock.isVisible(),
                    "timeline_visible": window.timeline_dock.isVisible(),
                    "side_by_side": side_by_side,
                    "stacked": stacked,
                }
            )

        window.close()
        _process_events(app)
    return {"platform": app.platformName(), "observations": observations}
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    arguments = parser.parse_args()
    result = verify_native_dragflow()
    if arguments.json:
        print(json.dumps(result))
    else:
        print("Native drag-flow verification PASS")
        for observation in result["observations"]:
            print(observation)

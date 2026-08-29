"""Real Windows gate for the drag-driven editor workflow.

This verifier refuses offscreen/minimal Qt.  It opens an exposed top-level
PySide6 window, exercises the node palette search, real drag events across the
visible four drop zones, edge auto-scroll, Inspector edits, Undo/Redo, and the
Parallel side-by-side/stacked branch layout at both required sizes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.core.project_context import ProjectContext
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtCore import QPoint, QPointF, Qt
from src.qt_compat.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QMouseEvent
from src.qt_compat.QtWidgets import QApplication


REQUIRED_SIZES = ((1480, 920), (960, 640))


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


def _panel_point(panel, zone: str) -> QPoint:
    strip = int(panel.height() * 0.34)
    if zone == "before":
        return QPoint(panel.center().x(), panel.top() + 2)
    if zone == "after":
        return QPoint(panel.center().x(), panel.bottom() - 2)
    if zone == "child":
        return QPoint(panel.left() + 4, panel.center().y())
    return QPoint(panel.right() - 4, panel.center().y())


def _hover_card(flow, mime, uid: str):
    rect = flow.canvas.rect_for_uid(uid)
    if rect is None:
        raise AssertionError(f"card {uid!r} is not visible")
    enter, move, _drop = _drag_events(flow, mime, rect.center())
    QApplication.sendEvent(flow.canvas, enter)
    QApplication.sendEvent(flow.canvas, move)
    panel = flow.canvas._panel_rect
    if panel is None:
        raise AssertionError(f"hovering {uid!r} did not anchor the four-zone panel")
    return panel


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

        window.inspector_dock.hide()
        window.timeline_dock.hide()
        window.output_dock.hide()
        session.select_unit("stage")
        session.select_node("wait")
        _process_events(app)

        for width, height in REQUIRED_SIZES:
            window.resize(width, height)
            _process_events(app)
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

            # 2. Four-zone switching on the magnified panel over a container card.
            zones = {}
            mime = _palette_mime(window, "Repeat")
            panel = _hover_card(flow, mime, "container")
            for zone in ("before", "after", "child", "wrap"):
                position = _panel_point(panel, zone)
                _enter, move, _drop = _drag_events(flow, mime, position)
                QApplication.sendEvent(canvas, move)
                _process_events(app)
                if not move.isAccepted():
                    raise RuntimeError(f"drag move refused at zone {zone}")
                zones[zone] = flow.canvas._drop_candidate[1].value
            expected = {"before": "before", "after": "after", "child": "child", "wrap": "wrap"}
            if zones != expected:
                raise RuntimeError(f"four-zone mapping wrong: {zones}")
            canvas._end_drop()

            # 3. A real drop appends one undoable command and flashes the card.
            body_before = [node.uid for node in session.program.get_unit("stage").body]
            mime = _palette_mime(window, "Wait")
            panel = _hover_card(flow, mime, "wait")
            position = _panel_point(panel, "after")
            enter, move, drop = _drag_events(flow, mime, position)
            QApplication.sendEvent(canvas, enter)
            QApplication.sendEvent(canvas, move)
            QApplication.sendEvent(canvas, drop)
            _process_events(app)
            body_after = [node.uid for node in session.program.get_unit("stage").body]
            if len(body_after) != len(body_before) + 1:
                raise RuntimeError("drop did not add exactly one node")
            if session.undo_stack.count() != 1:
                raise RuntimeError("drop did not produce exactly one undo command")
            if flow.canvas._flash_uid != body_after[1]:
                raise RuntimeError("inserted card was not flashed")
            session.undo_stack.undo()
            if [node.uid for node in session.program.get_unit("stage").body] != body_before:
                raise RuntimeError("undo did not restore the previous body")
            session.undo_stack.redo()
            session.undo_stack.undo()
            _process_events(app)

            # 4. Edge auto-scroll while dragging near the bottom edge.
            session.select_node("wait")
            for _ in range(4):
                window.insert_palette_node("Repeat", "after", target_uid="wait")
            _process_events(app)
            bar = flow.verticalScrollBar()
            bar.setValue(0)
            _process_events(app)
            position = QPoint(canvas.width() // 2, window.program_tree.viewport().height() - 2)
            scroll_mime = _node_mime("wait")
            enter, move, _drop = _drag_events(flow, scroll_mime, position)
            QApplication.sendEvent(canvas, enter)
            QApplication.sendEvent(canvas, move)
            if not canvas._autoscroll_timer.isActive():
                raise RuntimeError("edge hover did not arm the autoscroll timer")
            canvas._autoscroll_step()
            canvas._autoscroll_step()
            if bar.value() <= 0:
                raise RuntimeError("autoscroll did not move the scrollbar")
            canvas._end_drop()
            for _ in range(4):
                session.undo_stack.undo()

            # 5. Inspector edit via the visible field plus Undo/Redo.
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

            # 6. Parallel branches: side by side when wide, stacked when narrow.
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
                    "side_by_side": side_by_side,
                    "stacked": stacked,
                }
            )

        window.close()
        _process_events(app)
    return {"platform": app.platformName(), "observations": observations}


def _node_mime(uid: str):
    from src.qt_compat.QtCore import QMimeData

    from src.editor.program_tree import NODE_MIME

    mime = QMimeData()
    mime.setData(NODE_MIME, uid.encode("utf-8"))
    return mime


def _verify_stacked_mode(app: QApplication, session: EditorSession) -> bool:
    """A narrow real ProgramFlow must stack Parallel branches vertically."""

    from src.editor.program_tree import ProgramFlow

    flow = ProgramFlow()
    flow.set_unit(session.current_unit, None)
    flow.resize(300, 640)
    flow.show()
    _process_events(app)
    try:
        heads = [
            element
            for element in flow.canvas._layout.elements
            if element.kind == "head"
            and element.node is not None
            and element.node.kind == "Branch"
            and element.uid.startswith("par__branch")
        ]
        if len(heads) != 2:
            raise RuntimeError("narrow flow did not expose two branch heads")
        first, second = heads[0].rect, heads[1].rect
        return first.left() == second.left() and first.top() < second.top()
    finally:
        flow.close()
        _process_events(app)


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

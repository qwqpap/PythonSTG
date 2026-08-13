"""Run the N6 contextual-search and beginner-flow gate in a native Qt window."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.project_context import ProjectContext
from src.editor.action_catalog import ActionQuery
from src.editor.app import EditorMainWindow
from src.editor.i18n import LANGUAGE_CHINESE
from src.editor.pattern_workspace import PatternWorkspace
from src.qt_compat.QtCore import Qt, QTimer
from src.qt_compat.QtGui import QKeyEvent
from src.qt_compat.QtWidgets import QApplication, QPushButton


def _tap_space(widget) -> None:
    QApplication.sendEvent(
        widget,
        QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Space, Qt.NoModifier),
    )
    QApplication.sendEvent(
        widget,
        QKeyEvent(QKeyEvent.KeyRelease, Qt.Key_Space, Qt.NoModifier),
    )


def _save_screenshot(window, path: Path | None) -> None:
    if path is not None and not window.grab().save(str(path)):
        raise RuntimeError(f"could not save native screenshot: {path}")


def run(
    *,
    project_root: Path,
    screenshot: Path | None = None,
    compact_screenshot: Path | None = None,
) -> None:
    app = QApplication.instance() or QApplication([])
    window = EditorMainWindow(ProjectContext(project_root))
    window.resize(1480, 920)
    window.show()
    app.processEvents()
    window.set_language(LANGUAGE_CHINESE)
    app.processEvents()

    before = window.session.document.to_dict()
    window.create_stage_template("two_phase_boss")
    app.processEvents()
    if [state.name for state in window.session.document.state_graph.states] != [
        "登场", "通常阶段", "强化阶段", "结束"
    ]:
        raise AssertionError("Chinese two-phase Boss skeleton was not created")
    intro = window.session.document.state_graph.states[0]
    if [track.name for track in intro.tracks] != ["背景", "背景音乐"]:
        raise AssertionError("Chinese template track names were not preserved")
    if window.action_undo.text() != "撤销 创建两阶段 Boss 模板":
        raise AssertionError("Chinese template transaction was not named naturally")
    window.bottom_tabs.setCurrentWidget(window.timeline)
    app.processEvents()
    if not window.timeline.view.isVisibleTo(window):
        raise AssertionError("timeline did not open for the Boss template")
    _save_screenshot(window, screenshot)
    window.resize(960, 640)
    app.processEvents()
    if window.size().width() != 960 or window.size().height() != 640:
        raise AssertionError(f"minimum editor size was not honored: {window.size()}")
    if window.bottom_dock.height() < 210:
        raise AssertionError("bottom workbench collapsed below its usable height")
    if window.timeline.view.viewport().height() < 40:
        raise AssertionError(
            "timeline has no editable track area at the minimum size: "
            f"dock={window.bottom_dock.height()} timeline={window.timeline.height()} "
            f"view={window.timeline.view.height()} "
            f"viewport={window.timeline.view.viewport().height()}"
        )
    add_clip_button = window.timeline.findChild(QPushButton, "timelineAddClip")
    if add_clip_button is None or not add_clip_button.isVisibleTo(window):
        raise AssertionError("timeline editing toolbar is hidden at the minimum size")
    if not window.timeline.view.graphics_scene.items():
        raise AssertionError("template timeline tracks are missing at the minimum size")
    _save_screenshot(window, compact_screenshot)
    window.resize(1480, 920)
    app.processEvents()
    if not window.session.undo() or window.session.document.to_dict() != before:
        raise AssertionError("Stage skeleton was not one undoable transaction")

    viewport = window.central_tabs.currentWidget()
    viewport.setFocus()
    _tap_space(viewport)
    app.processEvents()
    dialog = window._action_search_dialog
    if dialog is None or dialog.query.context != "scene":
        raise AssertionError("Scene Space did not open contextual search")
    if any(
        match.descriptor.payload.get("node_type") == "SceneRoot"
        for match in dialog._matches
    ):
        raise AssertionError("Scene search exposed an invalid root candidate")
    dialog.close()

    window.new_pattern()
    app.processEvents()
    workspace = window.central_tabs.currentWidget()
    if not isinstance(workspace, PatternWorkspace):
        raise AssertionError("new Pattern did not open PatternWorkspace")
    window._pattern_level_requested("l3")
    app.processEvents()
    if window.session.document.graph is None or workspace.authoring_level() != "l3":
        raise AssertionError("L3 did not expand the same Pattern")
    before_nodes = len(window.session.document.graph.nodes)
    workspace.graph_canvas.setFocus()
    _tap_space(workspace.graph_canvas)
    app.processEvents()
    dialog = window._action_search_dialog
    if dialog is None or dialog.query.context != "graph":
        raise AssertionError("Graph Space did not open contextual search")
    target = next(
        (match.descriptor for match in dialog._matches if match.descriptor.id == "action.graph.shape.arc"),
        None,
    )
    if target is None:
        raise AssertionError("Graph catalog did not offer the arc node")
    window._execute_action(target)
    dialog.close()
    app.processEvents()
    if len(window.session.document.graph.nodes) != before_nodes + 1:
        raise AssertionError("search result did not create through the document command")
    if not window.session.undo() or len(window.session.document.graph.nodes) != before_nodes:
        raise AssertionError("search-created node was not undoable")
    window._pattern_level_requested("l2")
    app.processEvents()
    if workspace.authoring_level() != "l2" or workspace.stack.currentWidget() is not workspace.advanced_view:
        raise AssertionError("progressive return to L2 did not preserve the Pattern")
    visible_levels = {
        workspace.level_picker.itemText(index)
        for index in range(workspace.level_picker.count())
    }
    if "编辑节点" not in visible_levels or "查看脚本源码" not in visible_levels:
        raise AssertionError("progressive navigation exposed implementation-level terms")

    print(
        "native_editor_n6_ok "
        f"scene_candidates={len(window.action_catalog.search(ActionQuery(context='scene', parent_type='SceneRoot')))} "
        f"graph_nodes={before_nodes} language={window.language} "
        "compact=960x640 "
        f"screenshot={screenshot or '(none)'} "
        f"compact_screenshot={compact_screenshot or '(none)'}",
        flush=True,
    )
    QTimer.singleShot(100, lambda: os._exit(0))
    app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="N6 native editor gate")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--compact-screenshot", type=Path)
    args = parser.parse_args()
    for path in (args.screenshot, args.compact_screenshot):
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
    run(
        project_root=args.project.resolve(),
        screenshot=args.screenshot,
        compact_screenshot=args.compact_screenshot,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

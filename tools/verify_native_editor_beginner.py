"""Exercise the task-first authoring path in a real PySide6 window.

This is an automated native interaction gate, not the five-participant N6.4
usability study.  It drives the public controls that a beginning author sees
and verifies that guided/full workspaces remain two presentations of the same
document and CommandStack.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.project_context import ProjectContext
from src.editor.app import create_window
from src.editor.i18n import LANGUAGE_CHINESE
from src.editor.panels.pattern_workspace import PatternWorkspace
from src.qt_compat.QtCore import Qt, QTimer
from src.qt_compat.QtTest import QTest
from src.qt_compat.QtWidgets import QApplication, QPushButton


def _button(root, object_name: str) -> QPushButton:
    button = root.findChild(QPushButton, object_name)
    if button is None:
        raise AssertionError(f"missing native control: {object_name}")
    return button


def _click(widget, app: QApplication) -> None:
    if not widget.isVisibleTo(widget.window()):
        raise AssertionError(f"native control is not visible: {widget.objectName()}")
    QTest.mouseClick(widget, Qt.LeftButton)
    app.processEvents()


def run(*, project_root: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = create_window(ProjectContext(project_root))
    window.resize(1480, 920)
    window.show()
    app.processEvents()

    if window.central_stack.currentWidget() is not window.beginner_home:
        raise AssertionError("production entry did not open the task-first home")
    for dock in (
        window.scene_dock,
        window.state_graph_dock,
        window.inspector_dock,
        window.variables_dock,
        window.bottom_dock,
    ):
        if dock.isVisibleTo(window):
            raise AssertionError(f"technical dock leaked onto home: {dock.objectName()}")

    window.set_language(LANGUAGE_CHINESE)
    window.resize(960, 640)
    app.processEvents()
    pattern_button = _button(window.beginner_home, "beginnerCreatePattern")
    boss_button = _button(window.beginner_home, "beginnerCreateBoss")
    if pattern_button.text() != "做一个弹幕" or boss_button.text() != "做一个 Boss 战":
        raise AssertionError("task cards did not switch to author-facing Chinese")
    for object_name in (
        "beginnerCreatePattern",
        "beginnerCreateMidstage",
        "beginnerCreateBoss",
        "beginnerOpenWork",
        "beginnerOpenExample",
    ):
        button = _button(window.beginner_home, object_name)
        if not button.isVisibleTo(window):
            raise AssertionError(f"home action is unavailable at 960x640: {object_name}")

    _click(pattern_button, app)
    workspace = window.central_tabs.currentWidget()
    if not isinstance(workspace, PatternWorkspace):
        raise AssertionError("Pattern task did not open PatternWorkspace")
    pattern_document_id = window.session.document.id
    pattern_commands = window.session.commands
    if workspace.authoring_level() != "l0":
        raise AssertionError("new Pattern did not start at preset selection")
    if workspace.stack.currentWidget() is not workspace.preset_choice_view:
        raise AssertionError("new Pattern did not show the real preset chooser")
    if workspace.preset_choice_list.count() < 5:
        raise AssertionError("preset chooser has no useful first-run choices")
    if any(
        dock.isVisibleTo(window)
        for dock in (window.scene_dock, window.state_graph_dock, window.variables_dock)
    ):
        raise AssertionError("Pattern guide exposed scene implementation docks")

    workspace.preset_choice_list.setCurrentRow(0)
    _click(_button(workspace, "patternApplyTemplate"), app)
    if window.session.document.id != pattern_document_id:
        raise AssertionError("preset application replaced the authoring document")
    if window.session.commands is not pattern_commands or not pattern_commands.can_undo:
        raise AssertionError("preset application bypassed the shared CommandStack")
    if workspace.authoring_level() != "l1":
        raise AssertionError("preset application did not advance to parameters")

    start_control = window.main_toolbar.widgetForAction(window.action_start)
    if start_control is None:
        raise AssertionError("Start action has no native toolbar control")
    _click(start_control, app)
    if window.central_stack.currentWidget() is not window.beginner_home:
        raise AssertionError("Start action did not return to task home")

    _click(_button(window.beginner_home, "beginnerCreateBoss"), app)
    boss_document_id = window.session.document.id
    boss_commands = window.session.commands
    if not window.beginner_guide_dock.isVisibleTo(window):
        raise AssertionError("Boss task did not expose the phase guide")
    if any(
        dock.isVisibleTo(window)
        for dock in (window.scene_dock, window.state_graph_dock, window.variables_dock)
    ):
        raise AssertionError("Boss guide exposed low-level structure docks")
    selected = window.session.node(window.session.editor_state.selection.node_id)
    if selected is None or selected.type != "Boss":
        raise AssertionError("Boss template did not land on an actionable Boss")

    phase_buttons = [
        button
        for button in window.beginner_guide.findChildren(QPushButton)
        if button.property("beginnerStateId")
    ]
    if len(phase_buttons) != 4:
        raise AssertionError("two-phase Boss guide does not expose four authored phases")
    second_state_id = str(phase_buttons[1].property("beginnerStateId"))
    _click(phase_buttons[1], app)
    if window.session.editor_state.selection.state_id != second_state_id:
        raise AssertionError("phase card did not navigate through the authoring service")
    if window.bottom_tabs.currentWidget() is not window.timeline:
        raise AssertionError("phase card did not open its timeline")

    full_control = _button(window.beginner_guide, "beginnerGuideFullWorkspace")
    _click(full_control, app)
    if not window.action_full_workspace.isChecked():
        raise AssertionError("guided-to-full workspace action did not stay in sync")
    if window.session.document.id != boss_document_id or window.session.commands is not boss_commands:
        raise AssertionError("full workspace created a second document lifecycle")
    if not window.scene_dock.isVisibleTo(window) or not window.inspector_dock.isVisibleTo(window):
        raise AssertionError("full workspace did not restore expert docks")
    if window.preview_panel.beginner_mode:
        raise AssertionError("full workspace retained beginner-only preview presentation")

    toolbar_full_control = window.main_toolbar.widgetForAction(
        window.action_full_workspace
    )
    if toolbar_full_control is None:
        raise AssertionError("Full Workspace action has no native toolbar control")
    _click(toolbar_full_control, app)
    if window.action_full_workspace.isChecked():
        raise AssertionError("toolbar did not return to guided workspace")
    if window.session.document.id != boss_document_id or window.session.commands is not boss_commands:
        raise AssertionError("returning to guided mode changed the authoring lifecycle")
    if not window.beginner_guide_dock.isVisibleTo(window):
        raise AssertionError("guided phase context was not restored")

    print(
        "native_editor_beginner_ok "
        "home_actions=5 pattern_levels=5 boss_phases=4 "
        "compact=960x640 shared_document=true shared_commands=true",
        flush=True,
    )
    QTimer.singleShot(100, lambda: os._exit(0))
    app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="Task-first native editor gate")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()
    run(project_root=args.project.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

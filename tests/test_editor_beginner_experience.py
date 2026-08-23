"""Task-first editor UX contract for a first-time PySTG author.

These tests exercise the real application window and public Qt controls.  The
guided workspace is only a presentation over the same ManagedDocument,
CommandStack, Coordinator and formal preview entry used by the full workbench.
"""

from __future__ import annotations

from src.core.project_context import ProjectContext
from src.editor.app import create_window
from src.editor.panels.pattern_workspace import PatternWorkspace
from src.editor.runtime_preview import RuntimePreviewHost
from src.qt_compat.QtWidgets import QFileDialog, QMenu, QPushButton


class _FakePreviewClient:
    def __init__(self) -> None:
        self.is_running = True
        self.commands: list[tuple[str, dict]] = []

    def start(self):
        self.is_running = True
        return True

    def send_command(self, command, payload=None):
        self.commands.append((str(command), dict(payload or {})))
        return f"request-{len(self.commands)}"

    def stop(self, timeout_ms=1500):
        del timeout_ms
        self.is_running = False

    def close(self):
        self.is_running = False


def _actual_window(tmp_path, qapp_session):
    window = create_window(ProjectContext(tmp_path))
    window.resize(1180, 760)
    window.show()
    qapp_session.processEvents()
    return window


def _button(root, object_name: str) -> QPushButton:
    button = root.findChild(QPushButton, object_name)
    assert button is not None, object_name
    return button


def test_actual_app_starts_at_a_five_choice_home_without_technical_docks(
    tmp_path, qapp_session
):
    window = _actual_window(tmp_path, qapp_session)
    try:
        assert window.central_stack.currentWidget() is window.beginner_home
        assert {
            name
            for name in (
                "beginnerCreatePattern",
                "beginnerCreateMidstage",
                "beginnerCreateBoss",
                "beginnerOpenWork",
                "beginnerOpenExample",
            )
            if window.beginner_home.findChild(QPushButton, name) is not None
        } == {
            "beginnerCreatePattern",
            "beginnerCreateMidstage",
            "beginnerCreateBoss",
            "beginnerOpenWork",
            "beginnerOpenExample",
        }
        assert not window.action_full_workspace.isChecked()
        assert not window.scene_dock.isVisibleTo(window)
        assert not window.state_graph_dock.isVisibleTo(window)
        assert not window.inspector_dock.isVisibleTo(window)
        assert not window.variables_dock.isVisibleTo(window)
        assert not window.bottom_dock.isVisibleTo(window)

        window.set_language("zh-CN")
        qapp_session.processEvents()
        assert _button(window.beginner_home, "beginnerCreatePattern").text() == "做一个弹幕"
        assert _button(window.beginner_home, "beginnerCreateMidstage").text() == "做一段道中"
        assert _button(window.beginner_home, "beginnerCreateBoss").text() == "做一个 Boss 战"
    finally:
        if window.session.is_dirty:
            window.session.revert()
        window.close()
        qapp_session.processEvents()


def test_home_pattern_entry_opens_the_same_document_at_choose_preset(
    tmp_path, qapp_session
):
    window = _actual_window(tmp_path, qapp_session)
    try:
        _button(window.beginner_home, "beginnerCreatePattern").click()
        qapp_session.processEvents()

        workspace = window.central_tabs.currentWidget()
        assert window.central_stack.currentWidget() is window.central_tabs
        assert isinstance(workspace, PatternWorkspace)
        assert workspace._document is window.session.document
        assert workspace.authoring_level() == "l0"
        assert [
            workspace.level_picker.itemData(index)
            for index in range(workspace.level_picker.count())
        ] == ["l0", "l1", "l2", "l3", "l4"]
        assert workspace.stack.currentWidget() is workspace.preset_choice_view
        assert workspace.preset_choice_list.count() >= 5
        assert not window.scene_dock.isVisibleTo(window)
        assert not window.state_graph_dock.isVisibleTo(window)
        assert not window.inspector_dock.isVisibleTo(window)
        assert not window.variables_dock.isVisibleTo(window)
        assert not window.bottom_dock.isVisibleTo(window)
    finally:
        window.close()
        qapp_session.processEvents()


def test_choosing_a_preset_advances_to_parameters_in_one_undoable_document(
    tmp_path, qapp_session
):
    window = _actual_window(tmp_path, qapp_session)
    try:
        _button(window.beginner_home, "beginnerCreatePattern").click()
        qapp_session.processEvents()
        workspace = window.central_tabs.currentWidget()
        session = window.session
        resource_id = session.document.id
        before = session.document.to_dict()

        workspace.preset_choice_list.setCurrentRow(0)
        _button(workspace, "patternApplyTemplate").click()
        qapp_session.processEvents()

        assert window._preset_resolver.instance_from_document(session.document) is not None
        assert session.document.id == resource_id
        assert session.editor_state.pattern.authoring_level == "l1"
        assert workspace.authoring_level() == "l1"
        assert workspace.stack.currentWidget() is workspace.preset_view
        assert session.commands.can_undo

        assert window.undo()
        assert session.document.to_dict() == before
        assert window._preset_resolver.instance_from_document(session.document) is None
    finally:
        window.close()
        qapp_session.processEvents()


def test_boss_home_entry_lands_on_a_phase_task_and_guides_state_navigation(
    tmp_path, qapp_session
):
    window = _actual_window(tmp_path, qapp_session)
    try:
        _button(window.beginner_home, "beginnerCreateBoss").click()
        qapp_session.processEvents()

        document = window.session.document
        assert document.metadata["template"]["kind"] == "two_phase_boss"
        assert window.beginner_guide_dock.isVisibleTo(window)
        assert not window.scene_dock.isVisibleTo(window)
        assert not window.state_graph_dock.isVisibleTo(window)
        assert not window.variables_dock.isVisibleTo(window)
        assert window.inspector_dock.isVisibleTo(window)
        assert window.bottom_dock.isVisibleTo(window)
        selected = window.session.node(window.session.editor_state.selection.node_id)
        assert selected is not None and selected.type == "Boss"

        phase_buttons = [
            button
            for button in window.beginner_guide.findChildren(QPushButton)
            if button.property("beginnerStateId")
        ]
        assert len(phase_buttons) == 4
        second_state_id = str(phase_buttons[1].property("beginnerStateId"))
        phase_buttons[1].click()
        qapp_session.processEvents()
        assert window.session.editor_state.selection.state_id == second_state_id
        assert window.bottom_tabs.currentWidget() is window.timeline

        window.action_full_workspace.trigger()
        qapp_session.processEvents()
        assert window.action_full_workspace.isChecked()
        assert window.scene_dock.isVisibleTo(window)
        assert window.inspector_dock.isVisibleTo(window)
        assert not window.beginner_guide_dock.isVisibleTo(window)
    finally:
        if window.session.is_dirty:
            window.session.revert()
        window.close()
        qapp_session.processEvents()


def test_scene_add_menu_separates_quick_tasks_from_low_level_nodes(
    tmp_path, qapp_session
):
    window = create_window(ProjectContext(tmp_path))
    try:
        actions = {action.objectName(): action for action in window._node_add_menu.actions()}
        quick_menu = actions["beginnerQuickCreateMenu"].menu()
        advanced_menu = actions["advancedNodeMenu"].menu()
        assert isinstance(quick_menu, QMenu)
        assert isinstance(advanced_menu, QMenu)
        assert {action.objectName() for action in quick_menu.actions()} >= {
            "addSimpleSpellFlow",
            "addMidstageSkeleton",
            "addTwoPhaseBossSkeleton",
        }
        assert any(action.objectName().startswith("addNode_") for action in advanced_menu.actions())
    finally:
        window.close()
        qapp_session.processEvents()


def test_pattern_preview_opens_the_formal_runtime_with_beginner_controls(
    tmp_path, qapp_session
):
    window = _actual_window(tmp_path, qapp_session)
    fake = _FakePreviewClient()
    window._pattern_preview_client = fake
    try:
        _button(window.beginner_home, "beginnerCreatePattern").click()
        qapp_session.processEvents()
        workspace = window.central_tabs.currentWidget()
        _button(workspace, "patternFormalPreview").click()
        qapp_session.processEvents()

        assert [command for command, _payload in fake.commands[:2]] == ["load", "play"]
        assert window._preview_session.active_document_id == window.session.document.id
        assert isinstance(window.central_tabs.currentWidget(), RuntimePreviewHost)
        assert window.bottom_dock.isVisibleTo(window)
        assert window.bottom_tabs.currentWidget() is window.preview_panel
        assert window.preview_panel.beginner_mode
        assert "unsaved://" not in window.preview_panel.resource_label.text()
        assert window.preview_panel.resource_label.text() == "Current work · not saved yet"
        assert not window.preview_panel.body_scroll.isVisibleTo(window.preview_panel)
    finally:
        window._preview_session.stop()
        window.close()
        qapp_session.processEvents()


def test_beginner_preview_error_is_actionable_but_keeps_technical_details(
    tmp_path, qapp_session
):
    window = _actual_window(tmp_path, qapp_session)
    try:
        window.preview_panel.set_beginner_mode(True)
        window.preview_panel.handle_issue(
            {
                "code": "no_stage_timeline",
                "message": "Add at least one Timeline track before launching Stage preview",
            }
        )
        assert (
            window.preview_panel.error_label.text()
            == "Preview unavailable: add something to the timeline first."
        )
        assert "no_stage_timeline" in window.preview_panel.error_label.toolTip()
        assert "Timeline track" in window.preview_panel.error_label.toolTip()
    finally:
        window.close()
        qapp_session.processEvents()


def test_save_feedback_tracks_not_saved_dirty_and_saved_states(
    tmp_path, qapp_session, monkeypatch
):
    window = _actual_window(tmp_path, qapp_session)
    try:
        _button(window.beginner_home, "beginnerCreatePattern").click()
        qapp_session.processEvents()
        workspace = window.central_tabs.currentWidget()
        assert window.save_status_label.text() == "Not saved yet"

        workspace.preset_choice_list.setCurrentRow(0)
        _button(workspace, "patternApplyTemplate").click()
        qapp_session.processEvents()
        assert window.save_status_label.text() == "Unsaved changes"

        target = tmp_path / "game_content" / "patterns" / "beginner_saved.pystg.json"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *args, **kwargs: (str(target), ""),
        )
        window.action_save.trigger()
        qapp_session.processEvents()
        assert target.is_file()
        assert window.save_status_label.text() == "Saved"
        assert not window.session.is_dirty
    finally:
        if window.session.is_dirty:
            window.session.revert()
        window.close()
        qapp_session.processEvents()

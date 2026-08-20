"""N1 contract: StateGraph authoring is one undoable view over SceneDocument."""

from __future__ import annotations

from copy import deepcopy

from src.core.project_context import ProjectContext
from src.editor import (
    AddStateCommand,
    AddTrackCommand,
    AddTransitionCommand,
    DuplicateStateCommand,
    MoveStateCommand,
    RemoveStateCommand,
    RenameStateCommand,
    SetTransitionPropertiesCommand,
    StateGraphSpec,
    StateSpec,
    TimelineTrack,
    TransitionSpec,
)
from src.editor.app import EditorMainWindow
from src.qt_compat.QtWidgets import QLineEdit, QPushButton


class FakePreviewClient:
    def __init__(self):
        self.is_running = True
        self.commands = []

    def start(self):
        return True

    def send_command(self, command, payload=None):
        self.commands.append((command, payload or {}))
        return str(len(self.commands))

    def close(self):
        pass


def _window(tmp_path, qapp_session, *, size=(1180, 760)):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window._pattern_preview_client = FakePreviewClient()
    window.resize(*size)
    window.show()
    qapp_session.processEvents()
    return window


def _graph_with_three_states(document):
    first = StateSpec(name="First", duration_frames=60)
    second = StateSpec(name="Second", duration_frames=60)
    third = StateSpec(name="Third", duration_frames=60)
    document.state_graph = StateGraphSpec(
        name="StageFlow",
        initial_state_id=first.id,
        states=[first, second, third],
    )
    document.validate()
    return first, second, third


def test_state_and_transition_commands_round_trip_same_uuids_through_undo_redo(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    session = window.session
    document = session.document
    initial = document.state_graph.initial_state
    added = StateSpec(name="Boss", duration_frames=120)

    session.apply(AddStateCommand(document, document.state_graph.id, added))
    session.apply(RenameStateCommand(document, added.id, "Boss Phase"))
    duplicate_command = DuplicateStateCommand(document, added.id)
    session.apply(duplicate_command)
    duplicate = duplicate_command.duplicated_state
    assert duplicate is not None
    duplicate_id = duplicate.id
    assert duplicate_id != added.id
    assert duplicate.name == "Boss Phase Copy"

    transition = TransitionSpec(
        name="Begin boss",
        target_state_id=added.id,
        trigger="after",
        after_frames=30,
    )
    session.apply(AddTransitionCommand(document, initial.id, transition))
    session.apply(
        SetTransitionPropertiesCommand(
            document,
            transition.id,
            {"name": "Begin boss later", "after_frames": 45, "priority": 3},
        )
    )
    session.apply(MoveStateCommand(document, duplicate_id, 1))
    ids_before_delete = [state.id for state in document.state_graph.states]
    session.apply(RemoveStateCommand(document, added.id))
    assert document.state_graph.find_state(added.id) is None
    assert not initial.transitions

    assert session.undo()  # restore deleted state and incoming transition
    assert [state.id for state in document.state_graph.states] == ids_before_delete
    assert document.state_graph.find_state(added.id) is added
    assert initial.transitions[0].id == transition.id
    assert initial.transitions[0].after_frames == 45
    assert session.redo()
    assert document.state_graph.find_state(added.id) is None
    assert session.undo()

    while session.undo():
        pass
    assert [state.id for state in document.state_graph.states] == [initial.id]
    while session.redo():
        pass
    assert document.state_graph.find_state(duplicate_id).id == duplicate_id
    assert document.state_graph.find_state(added.id) is None

    window.session.revert()
    window.close()
    window.deleteLater()
    qapp_session.processEvents()


def test_timeline_commands_target_selected_state_without_touching_other_states(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    document = window.session.document
    first, second, _third = _graph_with_three_states(document)
    first_track = TimelineTrack(name="First", kind="Event", channel="first")
    second_track = TimelineTrack(name="Second", kind="Event", channel="second")

    window.session.apply(AddTrackCommand(document, first_track, state_id=first.id))
    window.session.apply(AddTrackCommand(document, second_track, state_id=second.id))
    window._refresh()
    window.state_graph.select_state(second.id)
    qapp_session.processEvents()

    assert window.state_graph.selected_state_id == second.id
    assert window.timeline.state_id == second.id
    assert window.timeline.document is document
    assert window.timeline.tracks == second.tracks == [second_track]
    assert first.tracks == [first_track]
    assert document.tracks is first.tracks  # v2 compatibility surface is not a copy

    window.session.revert()
    window.close()
    window.deleteLater()
    qapp_session.processEvents()


def test_stageflow_and_phaseflow_are_contexts_of_same_workspace_instance(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    document = window.session.document
    phase_a = StateSpec(name="Phase A", duration_frames=60)
    phase_b = StateSpec(name="Phase B", duration_frames=60)
    boss = StateSpec(
        name="Boss",
        duration_frames=0,
        child_graph=StateGraphSpec(
            name="PhaseFlow",
            initial_state_id=phase_a.id,
            states=[phase_a, phase_b],
        ),
    )
    end = StateSpec(name="End", duration_frames=1)
    document.state_graph = StateGraphSpec(
        name="StageFlow",
        initial_state_id=boss.id,
        states=[boss, end],
    )
    workspace = window.state_graph
    window._refresh()

    workspace.select_state(boss.id)
    assert workspace.context_name == "StageFlow"
    workspace.select_state(phase_a.id)
    qapp_session.processEvents()

    assert window.state_graph is workspace
    assert workspace.context_name == "PhaseFlow"
    assert workspace.selected_state_id == phase_a.id
    assert window.timeline.state_id == phase_a.id

    window.session.revert()
    window.close()
    window.deleteLater()
    qapp_session.processEvents()


def test_native_controls_create_rename_duplicate_delete_and_remain_readable_at_960x640(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session, size=(960, 640))
    graph = window.session.document.state_graph
    initial_id = graph.initial_state_id
    workspace = window.state_graph

    add = workspace.findChild(QPushButton, "stateGraphAddState")
    duplicate = workspace.findChild(QPushButton, "stateGraphDuplicateState")
    delete = workspace.findChild(QPushButton, "stateGraphDeleteState")
    name = workspace.findChild(QLineEdit, "stateGraphStateName")
    apply_name = workspace.findChild(QPushButton, "stateGraphApplyStateName")
    assert all(widget is not None and widget.isVisible() for widget in (
        add,
        duplicate,
        delete,
        name,
        apply_name,
    ))
    assert workspace.width() >= 240
    assert workspace.geometry().right() <= window.width()
    assert workspace.geometry().bottom() <= window.height()

    add.click()
    qapp_session.processEvents()
    added_id = workspace.selected_state_id
    assert added_id != initial_id
    assert len(graph.states) == 2
    name.setText("Boss Phase")
    apply_name.click()
    assert graph.find_state(added_id).name == "Boss Phase"

    duplicate.click()
    qapp_session.processEvents()
    duplicate_id = workspace.selected_state_id
    assert duplicate_id not in {initial_id, added_id}
    assert graph.find_state(duplicate_id).name == "Boss Phase Copy"
    delete.click()
    assert graph.find_state(duplicate_id) is None
    window.undo()
    assert graph.find_state(duplicate_id).id == duplicate_id

    window.session.revert()
    window.close()
    window.deleteLater()
    qapp_session.processEvents()


def test_runtime_state_feedback_is_overlay_only_and_stays_with_owner_document(
    tmp_path, qapp_session
):
    window = _window(tmp_path, qapp_session)
    owner = window.session
    first, second, _third = _graph_with_three_states(owner.document)
    window._refresh()
    before = deepcopy(owner.document.to_dict())
    before_dirty = owner.is_dirty
    window._active_stage_session = owner
    window._preview_mode = "stage"
    window._preview_loaded_resource_id = owner.document.id

    window._handle_pattern_preview_event(
        {
            "event": "statistics",
            "payload": {
                "mode": "stage",
                "resource_id": owner.document.id,
                "state": "playing",
                "frame": 12,
                "active_clips": [],
                "state_path": [first.id, second.id],
                "state_path_names": ["First", "Second"],
                "node_state": {},
            },
        }
    )
    assert window.runtime_overlay is not None
    assert window.runtime_overlay.state_path == (first.id, second.id)
    assert window.state_graph.active_state_path == (first.id, second.id)
    assert owner.document.to_dict() == before
    assert owner.is_dirty is before_dirty

    window.new_scene()
    current = window.session
    current_path = window.state_graph.active_state_path
    window._handle_pattern_preview_event(
        {
            "event": "statistics",
            "payload": {
                "mode": "stage",
                "resource_id": owner.document.id,
                "state": "playing",
                "frame": 13,
                "active_clips": [],
                "state_path": [second.id],
                "state_path_names": ["Second"],
                "node_state": {},
            },
        }
    )
    assert window.session is current
    assert window.state_graph.active_state_path == current_path
    assert window.runtime_overlay is not None
    assert window.runtime_overlay.document_id == owner.document.id
    assert window.runtime_overlay.state_path == (second.id,)
    assert owner.document.to_dict() == before

    owner.revert()
    window.close()
    window.deleteLater()
    qapp_session.processEvents()

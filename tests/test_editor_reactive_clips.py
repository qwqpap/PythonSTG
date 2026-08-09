"""N4.2 timeline slot, inspector, overlay, and navigation contracts."""

from copy import deepcopy

from PyQt5.QtWidgets import QComboBox, QLabel

from src.core.project_context import ProjectContext
from src.editor import SceneEditorSession, TimelineClip, TimelineTrack
from src.editor.app import EditorMainWindow
from src.editor.timeline_workspace import TimelineClipItem, TimelineEditor


def _reactive_clip():
    return TimelineClip(
        name="Fake hit",
        kind="Reactive",
        start_frame=12,
        duration_frames=60,
        channel="reaction",
        payload={
            "activation": {"kind": "on_event", "event_type": "boss.hit"},
            "reaction": {
                "id": "fake-overload",
                "event_type": "boss.hit",
                "action": "spawn-overload",
                "once_per_scope": False,
            },
            "owner_id": "boss.fake",
        },
    )


def test_timeline_reactive_slot_has_context_badge_and_read_only_overlay(qapp_session):
    document = SceneEditorSession.new_document("Reactive editor")
    track = TimelineTrack(name="Hooks", kind="Reactive", channel="reaction", clips=[_reactive_clip()])
    document.tracks = [track]
    before = deepcopy(document.to_dict())

    editor = TimelineEditor()
    editor.resize(720, 360)
    editor.show()
    editor.set_document(document)
    qapp_session.processEvents()

    picker = editor.findChild(QComboBox, "timelineKindPicker")
    assert picker.findData("Reactive") >= 0
    item = next(
        value
        for value in editor.view.graphics_scene.items()
        if isinstance(value, TimelineClipItem)
    )
    assert item.kind == "Reactive"
    assert item.activation["kind"] == "on_event"

    editor.set_reactive_overlay(
        {
            "active_instances": [{"clip_id": track.clips[0].id, "instance_id": "runtime#1"}],
            "trace": [],
            "diagnostics": [{"clip_id": track.clips[0].id, "reason": "frame_instance_budget"}],
        }
    )
    assert item.active is True
    assert item.conflicts == ("frame_instance_budget",)
    assert document.to_dict() == before
    editor.close()


def test_editor_adds_reactive_track_clip_through_command_stack(tmp_path, qapp_session):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window.resize(900, 650)
    window.show()
    qapp_session.processEvents()
    window._timeline_add_track("Reactive")
    track = window.session.document.tracks[0]
    window.timeline.selected_track_id = track.id
    window._timeline_add_clip(track.id)
    assert track.kind == "Reactive"
    assert track.clips[0].payload["activation"]["kind"] == "on_event"
    assert track.clips[0].payload["reaction"]["id"]
    assert window.session.undo()
    assert track.clips == []
    assert window.session.redo()
    assert len(track.clips) == 1
    window.session.revert()
    window.close()
    qapp_session.processEvents()


def test_reactive_clip_inspector_exposes_activation_reaction_and_owner(tmp_path, qapp_session):
    window = EditorMainWindow(ProjectContext(tmp_path))
    window.show()
    qapp_session.processEvents()
    track = TimelineTrack(name="Hooks", kind="Reactive", channel="reaction", clips=[_reactive_clip()])
    window.session.document.tracks = [track]
    window._refresh()
    window._timeline_clip_selected(track.id, track.clips[0].id)
    qapp_session.processEvents()
    assert window.inspector.findChild(QLabel, "timelineReactiveActivation").text() == "on_event"
    assert window.inspector.findChild(QLabel, "timelineReactiveReaction").text() == "fake-overload"
    assert window.inspector.findChild(QLabel, "timelineReactiveOwner").text() == "boss.fake"
    window.session.revert()
    window.close()
    qapp_session.processEvents()


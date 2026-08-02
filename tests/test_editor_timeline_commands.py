from src.core.project_context import ProjectContext
from src.editor import SceneEditorSession, TimelineClip, TimelineKeyframe, TimelineTrack
from src.editor.document_manager import DocumentManager
from src.editor.timeline_commands import (
    AddClipCommand,
    AddTrackCommand,
    MoveResizeClipCommand,
    RemoveClipCommand,
    SetClipPropertiesCommand,
)


def _managed_scene(tmp_path):
    manager = DocumentManager(ProjectContext(tmp_path))
    return manager.active


def test_track_clip_move_resize_delete_round_trip(tmp_path):
    session = _managed_scene(tmp_path)
    track = TimelineTrack(name="Events", kind="Event", channel="event")
    clip = TimelineClip(
        name="Phase",
        kind="Event",
        start_frame=60,
        duration_frames=1,
        channel="event",
        payload={"event_type": "phase"},
    )

    session.apply(AddTrackCommand(session.document, track))
    session.apply(AddClipCommand(session.document, track.id, clip))
    session.apply(MoveResizeClipCommand(session.document, clip.id, 120, 30))
    session.apply(RemoveClipCommand(session.document, clip.id))
    assert not track.clips

    assert session.undo()
    assert track.clips == [clip]
    assert (clip.start_frame, clip.duration_frames) == (120, 30)
    assert session.undo()
    assert (clip.start_frame, clip.duration_frames) == (60, 1)
    assert session.undo()
    assert not track.clips
    assert session.undo()
    assert not session.document.tracks

    for _ in range(4):
        assert session.redo()
    assert not track.clips


def test_continuous_clip_motion_coalesces_and_property_edit_validates(tmp_path):
    session = _managed_scene(tmp_path)
    track = TimelineTrack(name="Events", kind="Event", channel="event")
    clip = TimelineClip(
        name="Start",
        kind="Event",
        start_frame=0,
        duration_frames=1,
        channel="event",
        payload={"event_type": "start"},
    )
    session.apply(AddTrackCommand(session.document, track))
    session.apply(AddClipCommand(session.document, track.id, clip))

    session.apply(MoveResizeClipCommand(session.document, clip.id, 10, 12), coalesce=True)
    session.apply(MoveResizeClipCommand(session.document, clip.id, 24, 18), coalesce=True)
    assert session.undo()
    assert (clip.start_frame, clip.duration_frames) == (0, 1)

    session.apply(
        SetClipPropertiesCommand(
            session.document,
            clip.id,
            {"payload": {"event_type": "phase", "data": {"value": 2}}},
        )
    )
    assert clip.payload["event_type"] == "phase"
    assert session.undo()
    assert clip.payload == {"event_type": "start"}


def test_keyframes_round_trip_through_clip_property_command(tmp_path):
    session = _managed_scene(tmp_path)
    target = session.document.root.id
    track = TimelineTrack(
        name="Properties",
        kind="Property",
        channel="alpha",
        target_id=target,
    )
    clip = TimelineClip(
        name="Fade",
        kind="Property",
        start_frame=0,
        duration_frames=60,
        channel="alpha",
        target_id=target,
        payload={"value": 1.0},
    )
    session.apply(AddTrackCommand(session.document, track))
    session.apply(AddClipCommand(session.document, track.id, clip))
    keyframes = [
        TimelineKeyframe(0, 0.0).to_dict(),
        TimelineKeyframe(60, 1.0, interpolation="ease_in_out").to_dict(),
    ]

    session.apply(
        SetClipPropertiesCommand(
            session.document,
            clip.id,
            {"keyframes": keyframes},
        )
    )
    assert [item.value for item in clip.keyframes] == [0.0, 1.0]
    assert session.undo()
    assert not clip.keyframes

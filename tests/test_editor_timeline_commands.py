from src.core.project_context import ProjectContext
from src.editor import SceneEditorSession, TimelineClip, TimelineKeyframe, TimelineTrack
from src.editor.document_manager import DocumentManager
from src.editor.timeline_commands import (
    AddClipCommand,
    AddKeyframeCommand,
    AddTrackCommand,
    MoveTrackCommand,
    MoveResizeClipCommand,
    RemoveClipCommand,
    RemoveKeyframeCommand,
    RemoveTrackCommand,
    SetClipPropertiesCommand,
    SetKeyframePropertiesCommand,
    SetTrackPropertiesCommand,
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
        channel="background",
        target_id=target,
    )
    clip = TimelineClip(
        name="Fade",
        kind="Property",
        start_frame=0,
        duration_frames=60,
        channel="background",
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


def test_track_edit_reorder_mute_delete_all_round_trip(tmp_path):
    session = _managed_scene(tmp_path)
    first = TimelineTrack(name="First", kind="Event", channel="event", order=0)
    second = TimelineTrack(name="Second", kind="Event", channel="event", order=1)
    session.apply(AddTrackCommand(session.document, first))
    session.apply(AddTrackCommand(session.document, second))

    session.apply(
        SetTrackPropertiesCommand(
            session.document,
            first.id,
            {"name": "Renamed", "muted": True, "channel": "phase"},
        )
    )
    assert (first.name, first.muted, first.channel) == ("Renamed", True, "phase")
    assert session.undo()
    assert (first.name, first.muted, first.channel) == ("First", False, "event")
    assert session.redo()

    session.apply(MoveTrackCommand(session.document, second.id, 0))
    assert session.document.tracks == [second, first]
    assert [track.order for track in session.document.tracks] == [0, 1]
    assert session.undo()
    assert session.document.tracks == [first, second]
    assert [track.order for track in session.document.tracks] == [0, 1]

    session.apply(RemoveTrackCommand(session.document, first.id))
    assert session.document.tracks == [second]
    assert session.undo()
    assert session.document.tracks == [first, second]


def test_keyframe_add_edit_delete_all_round_trip(tmp_path):
    session = _managed_scene(tmp_path)
    target = session.document.root.id
    track = TimelineTrack(
        name="Background",
        kind="Property",
        channel="background",
        target_id=target,
    )
    clip = TimelineClip(
        name="Tint",
        kind="Property",
        start_frame=0,
        duration_frames=60,
        channel="background",
        target_id=target,
        payload={"value": "#171a24"},
    )
    session.apply(AddTrackCommand(session.document, track))
    session.apply(AddClipCommand(session.document, track.id, clip))
    keyframe = TimelineKeyframe(24, "#334455")

    session.apply(AddKeyframeCommand(session.document, clip.id, keyframe))
    assert clip.keyframes == [keyframe]
    session.apply(
        SetKeyframePropertiesCommand(
            session.document,
            clip.id,
            keyframe.id,
            {"frame": 36, "value": "#ffffff", "interpolation": "step"},
        )
    )
    assert (keyframe.frame, keyframe.value, keyframe.interpolation) == (
        36,
        "#ffffff",
        "step",
    )
    assert session.undo()
    assert (keyframe.frame, keyframe.value, keyframe.interpolation) == (
        24,
        "#334455",
        "linear",
    )

    session.apply(RemoveKeyframeCommand(session.document, clip.id, keyframe.id))
    assert clip.keyframes == []
    assert session.undo()
    assert clip.keyframes == [keyframe]

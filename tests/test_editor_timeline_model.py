import uuid

import pytest

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor import (
    CURRENT_SCHEMA_VERSION,
    DocumentError,
    SceneEditorSession,
    TimelineClip,
    TimelineKeyframe,
    TimelineTrack,
    make_node,
)


def _scene_with_targets():
    scene = SceneEditorSession.new_document("Timeline Stage")
    stage = make_node("Stage", name="Stage")
    boss = make_node("Boss", name="Boss")
    spell = make_node("Spell", name="Spell")
    emitter = make_node("Emitter", name="Emitter")
    pattern = make_node("PatternInstance", name="Pattern")
    scene.root.children.append(stage)
    stage.children.append(boss)
    boss.children.append(spell)
    spell.children.append(emitter)
    emitter.children.append(pattern)
    return scene, emitter, pattern


def _all_initial_tracks(emitter_id, pattern_id):
    return [
        TimelineTrack(
            name="Patterns",
            kind="Pattern",
            channel="danmaku",
            target_id=pattern_id,
            order=0,
            clips=[
                TimelineClip(
                    name="Opening ring",
                    kind="Pattern",
                    start_frame=0,
                    duration_frames=600,
                    channel="danmaku",
                    target_id=pattern_id,
                    loop_count=2,
                )
            ],
        ),
        TimelineTrack(
            name="Movement",
            kind="Movement",
            channel="position",
            target_id=emitter_id,
            order=1,
            clips=[
                TimelineClip(
                    name="Sweep",
                    kind="Movement",
                    start_frame=120,
                    duration_frames=180,
                    channel="position",
                    target_id=emitter_id,
                    keyframes=[
                        TimelineKeyframe(0, {"x": -0.5, "y": 0.5}),
                        TimelineKeyframe(180, {"x": 0.5, "y": 0.5}, interpolation="ease_in_out"),
                    ],
                )
            ],
        ),
        TimelineTrack(
            name="Audio",
            kind="Audio",
            channel="bgm",
            order=2,
            clips=[
                TimelineClip(
                    name="Boss theme",
                    kind="Audio",
                    start_frame=0,
                    duration_frames=1800,
                    channel="bgm",
                    payload={"action": "play", "name": "boss_theme", "loops": -1},
                )
            ],
        ),
        TimelineTrack(
            name="Events",
            kind="Event",
            channel="phase",
            order=3,
            clips=[
                TimelineClip(
                    name="Phase start",
                    kind="Event",
                    start_frame=60,
                    duration_frames=1,
                    channel="phase",
                    payload={"event_type": "phase_started", "data": {"phase": 1}},
                )
            ],
        ),
        TimelineTrack(
            name="Properties",
            kind="Property",
            channel="enabled",
            target_id=pattern_id,
            order=4,
            clips=[
                TimelineClip(
                    name="Enable pattern",
                    kind="Property",
                    start_frame=0,
                    duration_frames=1,
                    channel="enabled",
                    target_id=pattern_id,
                    payload={"value": True},
                )
            ],
        ),
        TimelineTrack(
            name="Script hooks",
            kind="ScriptEvent",
            channel="script",
            order=5,
            clips=[
                TimelineClip(
                    name="Custom escape hatch",
                    kind="ScriptEvent",
                    start_frame=300,
                    duration_frames=1,
                    channel="script",
                    payload={"hook": "on_midspell", "arguments": {"rank": 2}},
                )
            ],
        ),
    ]


def test_track_clip_keyframe_round_trip_and_duration_contract(tmp_path):
    scene, emitter, pattern = _scene_with_targets()
    scene.tracks = _all_initial_tracks(emitter.id, pattern.id)
    scene.metadata["duration_frames"] = 3600

    payload = scene.to_dict()
    reopened = ResourceStore(ProjectContext(tmp_path)).registry.load(payload)

    assert reopened.to_dict() == payload
    assert reopened.schema_version == CURRENT_SCHEMA_VERSION == 2
    assert reopened.duration_frames == 3600
    ids = {
        item.id
        for track in reopened.tracks
        for clip in track.clips
        for item in [track, clip, *clip.keyframes]
    }
    assert len(ids) == sum(
        2 + len(clip.keyframes)
        for track in reopened.tracks
        for clip in track.clips
    )


def test_schema_one_flat_timeline_migrates_deterministically():
    scene, _emitter, _pattern = _scene_with_targets()
    payload = scene.to_dict()
    payload["schema_version"] = 1
    payload.pop("tracks")
    event_id = str(uuid.uuid4())
    payload["timeline"] = [
        {
            "id": event_id,
            "frame": 90,
            "type": "Spawn",
            "properties": {"count": 3},
        }
    ]

    first = type(scene).from_dict(payload)
    second = type(scene).from_dict(payload)

    assert first.schema_version == 2
    assert first.to_dict() == second.to_dict()
    assert len(first.tracks) == 1
    clip = first.tracks[0].clips[0]
    assert clip.id == event_id
    assert clip.kind == "Event"
    assert clip.start_frame == 90
    assert clip.payload == {"event_type": "Spawn", "data": {"count": 3}}
    assert "timeline" not in first.to_dict()


def test_timeline_rejects_duplicate_ids_bad_targets_and_bad_interpolation():
    scene, emitter, _pattern = _scene_with_targets()
    duplicate = TimelineKeyframe(
        frame=0,
        value={"x": 0, "y": 0},
        id=emitter.id,
    )
    scene.tracks = [
        TimelineTrack(
            name="Movement",
            kind="Movement",
            channel="position",
            target_id=emitter.id,
            clips=[
                TimelineClip(
                    name="Move",
                    kind="Movement",
                    start_frame=0,
                    duration_frames=60,
                    channel="position",
                    target_id=emitter.id,
                    keyframes=[duplicate],
                )
            ],
        )
    ]
    with pytest.raises(DocumentError, match="Duplicate document object id"):
        scene.validate()

    duplicate.id = str(uuid.uuid4())
    scene.tracks[0].target_id = str(uuid.uuid4())
    with pytest.raises(DocumentError, match="track.target_id does not exist"):
        scene.validate()

    scene.tracks[0].target_id = emitter.id
    duplicate.interpolation = "bezier"
    with pytest.raises(DocumentError, match="interpolation"):
        scene.validate()


def test_timeline_tracks_survive_atomic_save_and_reopen(tmp_path):
    project = ProjectContext(tmp_path)
    scene, emitter, pattern = _scene_with_targets()
    scene.tracks = _all_initial_tracks(emitter.id, pattern.id)
    store = ResourceStore(project)

    path = store.save(scene, "game_content/scenes/timeline_stage.pystg.json")
    reopened = store.load(path)

    assert reopened.to_dict() == scene.to_dict()
    assert [track.kind for track in reopened.tracks] == [
        "Pattern",
        "Movement",
        "Audio",
        "Event",
        "Property",
        "ScriptEvent",
    ]


def test_movement_and_property_targets_must_expose_required_semantics():
    scene, emitter, pattern = _scene_with_targets()
    scene.tracks = [
        TimelineTrack(
            name="Invalid movement",
            kind="Movement",
            channel="position",
            target_id=pattern.id,
            clips=[
                TimelineClip(
                    name="Move",
                    kind="Movement",
                    start_frame=0,
                    duration_frames=10,
                    channel="position",
                    keyframes=[
                        TimelineKeyframe(0, {"x": 0.0, "y": 0.0}),
                        TimelineKeyframe(10, {"x": 1.0, "y": 1.0}),
                    ],
                )
            ],
        )
    ]
    with pytest.raises(DocumentError, match="numeric x and y"):
        scene.validate()

    scene.tracks = [
        TimelineTrack(
            name="Invalid property",
            kind="Property",
            channel="missing_property",
            target_id=emitter.id,
            clips=[
                TimelineClip(
                    name="Set missing",
                    kind="Property",
                    start_frame=0,
                    duration_frames=10,
                    channel="missing_property",
                    payload={"value": 1},
                )
            ],
        )
    ]
    with pytest.raises(DocumentError, match="has no property 'missing_property'"):
        scene.validate()

import json
from dataclasses import replace

import numpy as np
import pytest

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.document import (
    SceneDocument,
    TimelineClip,
    TimelineKeyframe,
    TimelineTrack,
)
from src.editor.node_types import make_default_root, make_node
from src.editor.stage_compile import StageCompileError, compile_stage
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.game.stage.program import StageRunner, StageRunnerState
from src.pattern import PatternDocument
from src.preview import PatternPreviewController, PreviewState


class DummyPlayer:
    def __init__(self):
        self.pos = [0.8, -0.6]


class RecordingContext(StageContext):
    def __init__(self, pool):
        super().__init__(pool, DummyPlayer())
        self.positions = []
        self.properties = []
        self.events = []
        self.scripts = []
        self.audio_events = []

    def set_node_position(self, node_id, x, y):
        self.positions.append((node_id, x, y))

    def set_node_property(self, node_id, name, value):
        self.properties.append((node_id, name, value))

    def emit_event(self, event_type, data):
        self.events.append((event_type, data))

    def handle_script_event(self, hook, data):
        self.scripts.append((hook, data))

    def play_bgm(self, name, loops=-1, fade_ms=0):
        self.audio_events.append(("play_bgm", name, loops, fade_ms))
        return True


class RecordingAudioManager:
    def __init__(self):
        self.events = []

    def play_bgm(self, name, loops=-1, fade_ms=0):
        self.events.append(("play_bgm", name, loops, fade_ms))
        return True

    def stop_bgm(self, fade_ms=0):
        self.events.append(("stop_bgm", fade_ms))

    def pause_bgm(self):
        self.events.append(("pause_bgm",))

    def unpause_bgm(self):
        self.events.append(("unpause_bgm",))


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


def _authored_stage(tmp_path, *, duration=30):
    project = _project(tmp_path)
    pattern = PatternDocument.new("Timeline Ring")
    pattern.shape = replace(pattern.shape, count=1)
    pattern.schedule = replace(
        pattern.schedule,
        interval_frames=1,
        burst_count=1,
        loop_count=None,
    )
    pattern_uri = "res://game_content/patterns/timeline_ring.pystg.json"
    ResourceStore(project).save(pattern, pattern_uri.removeprefix("res://"))

    root = make_default_root("Timeline Stage")
    stage = make_node("Stage", name="Stage")
    boss = make_node("Boss", name="Boss")
    spell = make_node("Spell", name="Spell")
    emitter = make_node("Emitter", name="Emitter")
    emitter.properties.update({"x": 192.0, "y": 224.0})
    instance = make_node("PatternInstance", name="Pattern")
    instance.properties["pattern"] = pattern_uri
    emitter.children.append(instance)
    spell.children.append(emitter)
    boss.children.append(spell)
    stage.children.append(boss)
    root.children.append(stage)

    pattern_track = TimelineTrack(
        name="Pattern",
        kind="Pattern",
        channel="danmaku",
        target_id=instance.id,
        order=0,
        clips=[
            TimelineClip(
                name="Ring",
                kind="Pattern",
                start_frame=0,
                duration_frames=10,
                channel="danmaku",
            )
        ],
    )
    movement_track = TimelineTrack(
        name="Movement",
        kind="Movement",
        channel="position",
        target_id=emitter.id,
        order=1,
        clips=[
            TimelineClip(
                name="Sweep",
                kind="Movement",
                start_frame=0,
                duration_frames=10,
                channel="position",
                keyframes=[
                    TimelineKeyframe(0, {"x": 192.0, "y": 224.0}),
                    TimelineKeyframe(10, {"x": 384.0, "y": 224.0}),
                ],
            )
        ],
    )
    property_low = TimelineTrack(
        name="Property low",
        kind="Property",
        channel="enabled",
        target_id=instance.id,
        order=2,
        clips=[
            TimelineClip(
                name="Disable",
                kind="Property",
                start_frame=1,
                duration_frames=4,
                channel="enabled",
                payload={"property": "enabled", "value": False},
            )
        ],
    )
    property_high = TimelineTrack(
        name="Property high",
        kind="Property",
        channel="enabled",
        target_id=instance.id,
        order=3,
        clips=[
            TimelineClip(
                name="Enable wins",
                kind="Property",
                start_frame=1,
                duration_frames=4,
                channel="enabled",
                payload={"property": "enabled", "value": True},
            )
        ],
    )
    audio_track = TimelineTrack(
        name="Audio",
        kind="Audio",
        channel="bgm",
        order=4,
        clips=[
            TimelineClip(
                name="Theme",
                kind="Audio",
                start_frame=2,
                duration_frames=5,
                loop_count=2,
                channel="bgm",
                payload={"action": "play", "name": "stage_theme", "loops": -1},
            )
        ],
    )
    event_track = TimelineTrack(
        name="Events",
        kind="Event",
        channel="phase",
        order=5,
        clips=[
            TimelineClip(
                name="Phase",
                kind="Event",
                start_frame=3,
                duration_frames=1,
                channel="phase",
                payload={"event_type": "phase_changed", "data": {"phase": 2}},
            )
        ],
    )
    script_track = TimelineTrack(
        name="Script hooks",
        kind="ScriptEvent",
        channel="script",
        order=6,
        clips=[
            TimelineClip(
                name="Safe hook",
                kind="ScriptEvent",
                start_frame=4,
                duration_frames=1,
                channel="script",
                payload={
                    "hook": "on_midpoint",
                    "script": "__import__('os').system('never run')",
                    "data": {"value": 7},
                },
            )
        ],
    )
    scene = SceneDocument(
        "Timeline Stage",
        root,
        tracks=[
            pattern_track,
            movement_track,
            property_low,
            property_high,
            audio_track,
            event_track,
            script_track,
        ],
        metadata={"duration_frames": duration},
    )
    scene.validate()
    return project, scene, emitter, instance


def test_compile_scene_timeline_to_immutable_stage_program(tmp_path):
    project, scene, emitter, instance = _authored_stage(tmp_path)

    first = compile_stage(project, scene)
    second = compile_stage(project, SceneDocument.from_dict(scene.to_dict()))

    assert first == second
    assert first.content_hash == second.content_hash
    assert first.duration_frames == 30
    assert first.tick_rate == 60
    assert len(first.patterns) == 1
    assert len(first.automations) == 3
    assert [item.kind for item in first.actions] == [
        "Audio",
        "Event",
        "ScriptEvent",
        "Audio",
        "Audio",
    ]
    assert first.actions[-1].payload == {
        "action": "stop",
        "bus": "bgm",
        "fade_ms": 0,
        "automatic": True,
    }
    assert first.patterns[0].target_id == instance.id
    assert first.patterns[0].position_target_id == emitter.id
    assert first.patterns[0].base_origin == pytest.approx((0.0, 0.0))
    with pytest.raises(Exception):
        first.patterns = ()


def test_boss_movement_updates_runtime_node_state_and_feedback_hook(tmp_path):
    project, scene, _emitter, _instance = _authored_stage(tmp_path)
    boss = next(node for node in scene.root.walk() if node.type == "Boss")
    movement = next(track for track in scene.tracks if track.kind == "Movement")
    movement.target_id = boss.id

    program = compile_stage(project, scene)
    pool = OptimizedBulletPool(max_bullets=256)
    context = RecordingContext(pool)
    runner = StageRunner(program)
    runner.start(context)
    initial_x = runner.node_state[boss.id]["x"]
    runner.advance(context, 6)

    assert runner.node_state[boss.id]["x"] > initial_x
    assert any(item[0] == boss.id for item in context.positions)


def test_stage_runner_schedules_all_clip_types_and_last_order_wins(tmp_path):
    project, scene, emitter, instance = _authored_stage(tmp_path)
    program = compile_stage(project, scene)
    pool = OptimizedBulletPool(max_bullets=128)
    context = RecordingContext(pool)
    runner = StageRunner(program)

    runner.start(context)
    results = runner.advance(context, 8)

    assert runner.state == StageRunnerState.RUNNING
    assert context.events == [("phase_changed", {"phase": 2})]
    assert context.scripts == [("on_midpoint", {"value": 7})]
    assert context.audio_events == [
        ("play_bgm", "stage_theme", -1, 0),
        ("play_bgm", "stage_theme", -1, 0),
    ]
    assert runner.node_state[instance.id]["enabled"] is True
    frame_one_property = [
        event
        for event in runner.trace
        if event.frame == 1 and event.kind == "property"
    ]
    assert len(frame_one_property) == 1
    assert frame_one_property[0].clip_id == scene.tracks[3].clips[0].id
    assert frame_one_property[0].value["conflict_count"] == 2
    assert sum(result.spawned_count for result in results) == 8
    assert not pool.emitter_callbacks
    assert not pool.death_handlers

    alive = np.flatnonzero(pool.data["alive"])
    assert len(alive) == 8
    # The emitter moves from runtime x=0 toward x=1. Every frame's burst uses
    # the current semantic position without per-bullet callbacks.
    spawned_x = sorted(float(value) for value in pool.data["pos"][alive, 0])
    assert spawned_x[0] == pytest.approx(0.0)
    assert spawned_x[5] == pytest.approx(0.5)
    assert context.positions[-1][0] == emitter.id


def test_movement_reaches_authored_endpoint_on_last_live_frame(tmp_path):
    project, scene, emitter, _instance = _authored_stage(tmp_path)
    context = RecordingContext(OptimizedBulletPool(max_bullets=128))
    runner = StageRunner(compile_stage(project, scene))

    runner.start(context)
    runner.advance(context, 10)

    assert runner.node_state[emitter.id]["x"] == pytest.approx(1.0)
    assert context.positions[-1][0] == emitter.id
    assert context.positions[-1][1:] == pytest.approx((1.0, 0.0))


def test_property_conflicts_use_property_name_not_display_channel(tmp_path):
    project, scene, emitter, _instance = _authored_stage(tmp_path)
    scene.tracks.extend(
        [
            TimelineTrack(
                name="X",
                kind="Property",
                channel="transform",
                target_id=emitter.id,
                order=10,
                clips=[
                    TimelineClip(
                        name="X value",
                        kind="Property",
                        start_frame=0,
                        duration_frames=2,
                        channel="transform",
                        payload={"property": "x", "value": 11.0},
                    )
                ],
            ),
            TimelineTrack(
                name="Y",
                kind="Property",
                channel="transform",
                target_id=emitter.id,
                order=11,
                clips=[
                    TimelineClip(
                        name="Y value",
                        kind="Property",
                        start_frame=0,
                        duration_frames=2,
                        channel="transform",
                        payload={"property": "y", "value": 22.0},
                    )
                ],
            ),
            TimelineTrack(
                name="Enabled alias",
                kind="Property",
                channel="alternate-channel",
                target_id=scene.tracks[3].target_id,
                order=12,
                clips=[
                    TimelineClip(
                        name="Disable wins across channels",
                        kind="Property",
                        start_frame=1,
                        duration_frames=2,
                        channel="alternate-channel",
                        payload={"property": "enabled", "value": False},
                    )
                ],
            ),
        ]
    )
    scene.validate()
    context = RecordingContext(OptimizedBulletPool(max_bullets=128))
    runner = StageRunner(compile_stage(project, scene))

    runner.start(context)
    runner.advance(context, 2)

    assert runner.node_state[emitter.id]["x"] == pytest.approx(11.0)
    assert runner.node_state[emitter.id]["y"] == pytest.approx(22.0)
    instance_id = scene.tracks[3].target_id
    assert runner.node_state[instance_id]["enabled"] is False
    enabled = [
        event
        for event in runner.last_events
        if event.kind == "property"
        and event.clip_id == scene.tracks[-1].clips[0].id
    ]
    assert len(enabled) == 1
    assert enabled[0].value["conflict_count"] == 3


def test_reset_replay_produces_identical_deterministic_stage_trace(tmp_path):
    project, scene, _emitter, _instance = _authored_stage(tmp_path)
    program = compile_stage(project, scene)
    pool = OptimizedBulletPool(max_bullets=256)
    context = RecordingContext(pool)
    runner = StageRunner(program)

    runner.start(context)
    runner.advance(context, 12)
    first = tuple(runner.trace)
    first_state = json.dumps(runner.node_state, sort_keys=True)

    runner.reset(context)
    runner.start(context, reset=False)
    runner.advance(context, 12, dispatch_actions=False)
    second = tuple(runner.trace)
    second_state = json.dumps(runner.node_state, sort_keys=True)

    assert first == second
    assert first_state == second_state
    assert np.count_nonzero(pool.data["alive"]) == 0  # clip ended at frame 10


def test_stage_compile_reports_scene_track_clip_and_reference_path(tmp_path):
    project, scene, _emitter, _instance = _authored_stage(tmp_path)
    pattern_clip = scene.tracks[0].clips[0]
    target = next(node for node in scene.root.walk() if node.id == scene.tracks[0].target_id)
    target.properties["pattern"] = "res://missing.pystg.json"

    with pytest.raises(StageCompileError) as caught:
        compile_stage(project, scene)

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.resource_id == scene.id
    assert diagnostic.track_id == scene.tracks[0].id
    assert diagnostic.clip_id == pattern_clip.id
    assert diagnostic.node_id == target.id
    assert "missing.pystg.json" in diagnostic.message


def test_stage_program_v1_rejects_non_formal_tick_rate(tmp_path):
    project, scene, _emitter, _instance = _authored_stage(tmp_path)
    scene.metadata["tick_rate"] = 120

    with pytest.raises(StageCompileError, match="60 Hz"):
        compile_stage(project, scene)


def test_formal_preview_loads_scene_and_seek_matches_normal_playback(tmp_path):
    project, scene, _emitter, _instance = _authored_stage(tmp_path, duration=1800)
    pool = OptimizedBulletPool(max_bullets=256)
    controller = PatternPreviewController(pool, project=project)

    loaded = controller.load(scene.to_dict())
    controller.play()
    for _ in range(8):
        controller.update()
    first_trace = tuple(controller.runner.trace)
    first_alive = pool.data["pos"][pool.data["alive"] == 1].copy()

    controller.seek(8)
    second_trace = tuple(controller.runner.trace)
    second_alive = pool.data["pos"][pool.data["alive"] == 1].copy()
    stats = controller.get_stats(emit=False)

    assert loaded["mode"] == "stage"
    assert controller.state == PreviewState.PAUSED
    assert first_trace == second_trace
    assert np.array_equal(first_alive, second_alive)
    assert stats["mode"] == "stage"
    assert stats["duration_frames"] == 1800
    assert stats["seed"] is None
    assert stats["active_clips"]


def test_formal_preview_dispatches_stage_audio_through_injected_manager(tmp_path):
    project, scene, _emitter, _instance = _authored_stage(tmp_path)
    pool = OptimizedBulletPool(max_bullets=256)
    audio = RecordingAudioManager()
    controller = PatternPreviewController(
        pool,
        project=project,
        audio_manager=audio,
    )

    controller.load(scene.to_dict())
    controller.play()
    for _ in range(8):
        controller.update()

    assert audio.events == [
        ("play_bgm", "stage_theme", -1, 0),
        ("play_bgm", "stage_theme", -1, 0),
    ]


def test_stage_audio_pause_resume_seek_reset_stop_and_finish(tmp_path):
    project, scene, _emitter, _instance = _authored_stage(tmp_path)
    audio = RecordingAudioManager()
    controller = PatternPreviewController(
        OptimizedBulletPool(max_bullets=256),
        project=project,
        audio_manager=audio,
    )
    controller.load(scene.to_dict())
    controller.play()
    for _ in range(5):
        controller.update()

    controller.pause()
    controller.play()
    assert audio.events[-2:] == [("pause_bgm",), ("unpause_bgm",)]

    audio.events.clear()
    controller.seek(5)
    assert audio.events == [
        ("stop_bgm", 0),
        ("play_bgm", "stage_theme", -1, 0),
        ("pause_bgm",),
    ]

    controller.reset()
    assert audio.events[-1] == ("stop_bgm", 0)
    controller.play()
    for _ in range(3):
        controller.update()
    controller.stop()
    assert audio.events[-1] == ("stop_bgm", 0)

    short_project, short_scene, _emitter, _instance = _authored_stage(
        tmp_path / "short", duration=3
    )
    short_scene.tracks = [
        TimelineTrack(
            name="Short audio",
            kind="Audio",
            channel="bgm",
            clips=[
                TimelineClip(
                    name="Short theme",
                    kind="Audio",
                    start_frame=0,
                    duration_frames=3,
                    channel="bgm",
                    payload={"action": "play", "name": "stage_theme"},
                )
            ],
        )
    ]
    short_scene.validate()
    short_audio = RecordingAudioManager()
    short = PatternPreviewController(
        OptimizedBulletPool(max_bullets=64),
        project=short_project,
        audio_manager=short_audio,
    )
    short.load(short_scene.to_dict())
    short.play()
    for _ in range(3):
        short.update()
    assert short_audio.events[-2:] == [
        ("play_bgm", "stage_theme", -1, 0),
        ("stop_bgm", 0),
    ]


def test_automatic_audio_stop_does_not_stop_newer_overlapping_bgm(tmp_path):
    project, scene, _emitter, _instance = _authored_stage(tmp_path, duration=20)
    audio_track = next(track for track in scene.tracks if track.kind == "Audio")
    audio_track.channel = "music"
    audio_track.clips = [
        TimelineClip(
            name="First",
            kind="Audio",
            start_frame=0,
            duration_frames=6,
            channel="music",
            payload={"action": "play", "bus": "bgm", "name": "first"},
        ),
        TimelineClip(
            name="Second",
            kind="Audio",
            start_frame=3,
            duration_frames=10,
            channel="music",
            order=1,
            payload={"action": "play", "bus": "bgm", "name": "second"},
        ),
    ]
    scene.validate()
    audio = RecordingAudioManager()
    context = StageContext(
        OptimizedBulletPool(max_bullets=128),
        DummyPlayer(),
        audio_manager=audio,
    )
    runner = StageRunner(compile_stage(project, scene))

    runner.start(context)
    runner.advance(context, 7)
    assert audio.events == [
        ("play_bgm", "first", -1, 0),
        ("play_bgm", "second", -1, 0),
    ]
    runner.advance(context, 13)
    assert audio.events[-1] == ("stop_bgm", 0)

    audio.events.clear()
    runner.reset(context)
    runner.start(context, reset=False)
    runner.advance(context, 7, dispatch_actions=False)
    runner.restore_audio_state(context)
    assert audio.events == [("play_bgm", "second", -1, 0)]

    audio.events.clear()
    runner.reset(context)
    audio.events.clear()
    runner.start(context, reset=False)
    runner.advance(context, 14, dispatch_actions=False)
    runner.restore_audio_state(context)
    assert audio.events == []


def test_explicit_audio_stop_suppresses_duplicate_automatic_stop(tmp_path):
    project, scene, _emitter, _instance = _authored_stage(tmp_path)
    audio_track = next(track for track in scene.tracks if track.kind == "Audio")
    audio_track.clips.append(
        TimelineClip(
            name="Explicit stop",
            kind="Audio",
            start_frame=12,
            duration_frames=1,
            channel="bgm",
            order=1,
            payload={"action": "stop", "fade_ms": 250},
        )
    )

    program = compile_stage(project, scene)
    stops = [
        item
        for item in program.actions
        if item.frame == 12 and item.payload.get("action") == "stop"
    ]
    assert len(stops) == 1
    assert stops[0].payload == {"action": "stop", "fade_ms": 250}


def test_stage_context_records_typed_events_and_invokes_registered_script_hook():
    context = StageContext(OptimizedBulletPool(max_bullets=16), DummyPlayer())
    handled = []
    context.register_script_event_handler("boss_phase", handled.append)

    context.emit_event("phase_changed", {"phase": 2})
    assert context.handle_script_event("boss_phase", {"phase": 3}) is True
    assert context.handle_script_event("missing", None) is False

    assert handled == [{"phase": 3}]
    assert context.timeline_events() == (
        {"kind": "event", "type": "phase_changed", "data": {"phase": 2}},
        {
            "kind": "script",
            "type": "boss_phase",
            "data": {"phase": 3},
            "handled": True,
        },
        {"kind": "script", "type": "missing", "data": None, "handled": False},
    )
    context.clear_authored_stage_state()
    assert context.timeline_events() == ()

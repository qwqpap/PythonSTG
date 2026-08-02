import shutil
from pathlib import Path

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor.document_manager import DocumentManager
from src.editor.timeline_commands import MoveResizeClipCommand
from src.editor.stage_compile import compile_stage
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.game.stage.program import StageRunner


REPOSITORY = Path(__file__).resolve().parents[1]


class DummyPlayer:
    def __init__(self):
        self.pos = [0.0, -0.8]


def _copy_showcase(tmp_path):
    scene_source = REPOSITORY / "game_content" / "scenes" / "timeline_showcase.pystg.json"
    pattern_source = REPOSITORY / "game_content" / "patterns" / "starter_ring.pystg.json"
    aliases_source = REPOSITORY / "assets" / "bullet_aliases.json"
    scene_target = tmp_path / "game_content" / "scenes" / scene_source.name
    pattern_target = tmp_path / "game_content" / "patterns" / pattern_source.name
    aliases_target = tmp_path / "assets" / "bullet_aliases.json"
    scene_target.parent.mkdir(parents=True)
    pattern_target.parent.mkdir(parents=True)
    aliases_target.parent.mkdir(parents=True)
    shutil.copy2(scene_source, scene_target)
    shutil.copy2(pattern_source, pattern_target)
    shutil.copy2(aliases_source, aliases_target)
    return ProjectContext(tmp_path), scene_target


def test_30_second_showcase_edits_undo_redo_save_reopen_and_compile(tmp_path):
    project, scene_path = _copy_showcase(tmp_path)
    manager = DocumentManager(project, create_initial_scene=False)
    session = manager.open(scene_path)
    scene = session.document

    assert scene.duration_frames == 1800
    assert scene.timebase.frames_to_seconds(scene.duration_frames) == 30.0
    assert {track.kind for track in scene.tracks} >= {
        "Pattern",
        "Movement",
        "Audio",
        "Event",
        "Property",
    }

    track = next(item for item in scene.tracks if item.kind == "Pattern")
    clip = track.clips[0]
    original = (clip.start_frame, clip.duration_frames)
    session.apply(
        MoveResizeClipCommand(
            scene,
            clip.id,
            start_frame=60,
            duration_frames=540,
        )
    )
    assert (clip.start_frame, clip.duration_frames) == (60, 540)
    assert session.undo()
    assert (clip.start_frame, clip.duration_frames) == original
    assert session.redo()
    assert (clip.start_frame, clip.duration_frames) == (60, 540)

    manager.save(session)
    manager.close(session)
    reopened = manager.open(scene_path)
    reopened_track = next(
        item for item in reopened.document.tracks if item.kind == "Pattern"
    )
    assert (
        reopened_track.clips[0].start_frame,
        reopened_track.clips[0].duration_frames,
    ) == (60, 540)

    program = compile_stage(project, reopened.document)
    assert program.duration_frames == 1800
    assert len(program.patterns) == 1
    assert len(program.automations) == 3
    assert {item.kind for item in program.actions} == {
        "Audio",
        "Event",
        "ScriptEvent",
    }


def test_30_second_showcase_normal_play_and_replay_agree_at_checkpoints(tmp_path):
    project, scene_path = _copy_showcase(tmp_path)
    scene = ResourceStore(project).load(scene_path)
    program = compile_stage(project, scene)
    pool = OptimizedBulletPool(max_bullets=2048)
    context = StageContext(pool, DummyPlayer())
    runner = StageRunner(program)

    runner.start(context)
    runner.advance(context, 1201)
    first_trace = tuple(runner.trace)
    first_state = {
        node_id: dict(properties)
        for node_id, properties in runner.node_state.items()
    }

    runner.reset(context)
    runner.start(context, reset=False)
    runner.advance(context, 1201)

    assert tuple(runner.trace) == first_trace
    assert runner.node_state == first_state
    assert {event.kind for event in runner.trace} >= {
        "pattern_start",
        "pattern_spawn",
        "movement",
        "audio",
        "event",
        "property",
        "scriptevent",
    }
    assert any(event.frame == 600 and event.kind == "event" for event in runner.trace)
    assert any(event.frame == 1200 and event.kind == "event" for event in runner.trace)
    assert not pool.emitter_callbacks
    assert not pool.death_handlers

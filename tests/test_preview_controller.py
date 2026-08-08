import json
from dataclasses import replace

import numpy as np
import pytest

from src.core.project_context import ProjectContext
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.pattern import PatternDocument
from src.preview import PatternPreviewController, PreviewCommandError, PreviewState


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


def _controller(tmp_path, capacity=256):
    pool = OptimizedBulletPool(max_bullets=capacity)
    return pool, PatternPreviewController(pool, project=_project(tmp_path))


def test_controller_supports_complete_fixed_tick_command_contract(tmp_path):
    pool, controller = _controller(tmp_path)
    document = PatternDocument.new("Controlled")

    loaded = controller.execute("load", {"document": document.to_dict()})
    controller.execute("play")
    controller.update()
    controller.execute("pause")
    paused_frame = controller.frame
    controller.update()
    controller.execute("step")
    controller.execute("seek", {"frame": 5})
    controller.execute("set-player-position", {"x": 0.25, "y": -0.5})
    controller.execute("set-seed", {"seed": 42})
    stats = controller.execute("get-stats")

    assert loaded["resource_id"] == document.id
    assert paused_frame == 1
    assert controller.frame == 0  # set-seed recompiles and resets the runner
    assert controller.state == PreviewState.PAUSED
    assert controller.player.pos == [0.25, -0.5]
    assert controller.document.seed == 42
    assert stats["seed"] == 42
    assert stats["max_bullets"] == pool.max_bullets
    controller.execute("reset")
    controller.execute("stop")
    assert controller.state == PreviewState.STOPPED


def test_fixed_tick_publishes_authoritative_statistics_snapshot(tmp_path):
    _pool, controller = _controller(tmp_path)
    controller.load(PatternDocument.new("Frame feedback"))
    controller.play()
    controller.drain_events()

    controller.update()

    snapshots = [
        event.payload
        for event in controller.drain_events()
        if event.event == "statistics"
    ]
    assert snapshots
    assert snapshots[-1]["frame"] == 1
    assert snapshots[-1]["mode"] == "pattern"
    assert snapshots[-1]["resource_id"] == controller.document.id


def test_inspector_property_reload_preserves_play_state_and_changes_program(tmp_path):
    pool, controller = _controller(tmp_path)
    document = PatternDocument.new()
    document.schedule = replace(document.schedule, loop_count=None)
    controller.load(document)
    controller.play()
    original_hash = controller.program.content_hash

    controller.set_property("shape.count", 7)
    controller.update()

    assert controller.state == PreviewState.PLAYING
    assert controller.document.shape.count == 7
    assert controller.program.content_hash != original_hash
    assert np.count_nonzero(pool.data["alive"]) == 7


def test_invalid_hot_reload_keeps_last_program_bullets_frame_and_play_state(tmp_path):
    pool, controller = _controller(tmp_path)
    document = PatternDocument.new()
    document.schedule = replace(document.schedule, loop_count=None)
    controller.load(document)
    controller.play()
    controller.update()
    old_program = controller.program
    old_runner = controller.runner
    old_frame = controller.frame
    old_count = int(np.count_nonzero(pool.data["alive"]))

    with pytest.raises(PreviewCommandError):
        controller.set_property("shape.count", 0)

    assert controller.program is old_program
    assert controller.runner is old_runner
    assert controller.frame == old_frame
    assert controller.state == PreviewState.PLAYING
    assert np.count_nonzero(pool.data["alive"]) == old_count
    stats = controller.get_stats(emit=False)
    assert stats["reload_ok"] is False
    assert stats["last_error"]["active_program_preserved"] is True
    assert any(event.event == "compile_error" for event in controller.drain_events())

    controller.set_property("shape.count", 8)
    assert controller.state == PreviewState.PLAYING
    assert controller.get_stats(emit=False)["reload_ok"] is True


def test_saved_pattern_resource_loads_without_codegen(tmp_path):
    pool, controller = _controller(tmp_path)
    path = tmp_path / "patterns" / "ring.pystg.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(PatternDocument.new("Saved").to_dict()), encoding="utf-8")

    controller.execute("load", {"resource": "res://patterns/ring.pystg.json"})
    controller.execute("step")

    assert controller.resource_path == path.resolve()
    assert np.count_nonzero(pool.data["alive"]) == 24
    assert not list(tmp_path.rglob("*.py"))


def test_runtime_error_is_structured_and_does_not_escape_update_loop_state(tmp_path):
    _, controller = _controller(tmp_path)
    controller.load(PatternDocument.new())

    def fail_batch(**kwargs):
        raise RuntimeError("batch backend failed")

    controller.context.create_bullets_batch = fail_batch
    controller.play()
    with pytest.raises(Exception, match="batch backend failed"):
        controller.update()

    assert controller.state == PreviewState.ERROR
    error = controller.get_stats(emit=False)["last_error"]
    assert error["kind"] == "runtime"
    assert error["frame"] == 0
    assert error["path"] == "runtime"
    assert "batch backend failed" in error["message"]


def test_close_and_stop_are_idempotent(tmp_path):
    pool, controller = _controller(tmp_path)
    controller.load(PatternDocument.new())
    controller.play()
    controller.update()

    controller.stop()
    controller.stop()
    controller.close()
    controller.close()

    assert np.count_nonzero(pool.data["alive"]) == 0
    assert controller.state == PreviewState.STOPPED
    with pytest.raises(PreviewCommandError, match="closed"):
        controller.play()

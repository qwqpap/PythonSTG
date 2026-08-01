from dataclasses import replace
import math

import numpy as np
import pytest

from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.pattern import (
    AimSpec,
    PatternCompiler,
    PatternDocument,
    PatternRunner,
    PatternRunnerState,
    PatternRuntimeError,
    MotionSpec,
)


class DummyPlayer:
    def __init__(self, x=0.0, y=-0.8):
        self.pos = [x, y]


def _runtime(document, capacity=128):
    pool = OptimizedBulletPool(max_bullets=capacity)
    context = StageContext(pool, DummyPlayer())
    runner = PatternRunner(PatternCompiler().compile(document), owner_tag=1001)
    return pool, context, runner


def test_fixed_tick_schedule_delay_interval_bursts_and_loops():
    document = PatternDocument.new()
    document.shape = replace(document.shape, count=2)
    document.schedule = replace(
        document.schedule,
        delay_frames=2,
        interval_frames=3,
        burst_count=2,
        loop_count=2,
    )
    pool, context, runner = _runtime(document)
    runner.start(context)

    results = runner.advance(context, 12)
    events = [result.event for result in results if result.event]

    assert [event.frame for event in events] == [2, 5, 8, 11]
    assert [(event.loop_index, event.burst_index) for event in events] == [
        (0, 0), (0, 1), (1, 0), (1, 1)
    ]
    assert runner.state == PatternRunnerState.FINISHED
    assert np.count_nonzero(pool.data["alive"]) == 8


def test_runner_pause_resume_reset_and_stop_lifecycle():
    document = PatternDocument.new()
    document.shape = replace(document.shape, count=1)
    document.schedule = replace(document.schedule, loop_count=None)
    _, context, runner = _runtime(document)
    runner.start(context)
    runner.tick(context)
    runner.pause()

    paused_frame = runner.frame
    assert runner.tick(context).state == PatternRunnerState.PAUSED
    assert runner.frame == paused_frame
    runner.resume()
    runner.tick(context)
    runner.reset(context)
    assert runner.state == PatternRunnerState.STOPPED
    assert runner.frame == runner.emission_count == 0
    runner.start(context)
    runner.stop(context)
    assert runner.state == PatternRunnerState.STOPPED


def test_reset_replays_the_same_random_trace_deterministically():
    document = PatternDocument.new()
    document.shape = replace(document.shape, kind="random", count=6)
    document.schedule = replace(document.schedule, burst_count=2, loop_count=1)
    document.modifiers = replace(document.modifiers, random_speed_variation=0.25)
    document.seed = 8128
    pool, context, runner = _runtime(document)

    def play_once():
        runner.start(context)
        return [
            (result.event.positions, result.event.angles, result.event.speeds)
            for result in runner.advance(context, 21)
            if result.event is not None
        ]

    first = play_once()
    runner.reset(context)
    second = play_once()

    assert first == second


def test_player_aim_and_fixed_aim_share_batch_runtime():
    document = PatternDocument.new()
    document.shape = replace(document.shape, count=1, origin_x=0.0, origin_y=0.0)
    document.aim = AimSpec(mode="player", angle=99.0)
    pool = OptimizedBulletPool(max_bullets=4)
    context = StageContext(pool, DummyPlayer(1.0, 1.0))
    runner = PatternRunner(PatternCompiler().compile(document), owner_tag=1002)
    runner.start(context)

    event = runner.tick(context).event

    assert event.angles == pytest.approx((45.0,))
    assert pool.data["angle"][event.indices[0]] == pytest.approx(math.pi / 4)


def test_owner_operations_are_isolated_and_data_oriented():
    document = PatternDocument.new()
    document.shape = replace(document.shape, count=3)
    pool = OptimizedBulletPool(max_bullets=16)
    context = StageContext(pool, DummyPlayer())
    first = PatternRunner(PatternCompiler().compile(document), owner_tag=2001)
    second = PatternRunner(PatternCompiler().compile(document), owner_tag=2002)
    first.start(context)
    second.start(context)
    first_event = first.tick(context).event
    second_event = second.tick(context).event
    second_positions = pool.data["pos"][list(second_event.indices)].copy()

    assert first.translate_owned(context, 0.25, -0.5) == 3
    first.set_owned_time_scale(context, 0.0)
    assert np.all(pool.data["time_scale"][list(first_event.indices)] == 0.0)
    assert np.all(pool.data["time_scale"][list(second_event.indices)] == 1.0)
    assert np.array_equal(pool.data["pos"][list(second_event.indices)], second_positions)
    first.clear_owned(context)
    assert np.all(pool.data["alive"][list(first_event.indices)] == 0)
    assert np.all(pool.data["alive"][list(second_event.indices)] == 1)
    assert not pool.emitter_callbacks
    assert not pool.death_handlers


def test_compiled_motion_is_written_to_data_fields_in_one_batch():
    document = PatternDocument.new()
    document.shape = replace(document.shape, count=4)
    document.motion = MotionSpec(
        speed=3.0,
        friction=0.15,
        spin=90.0,
        time_scale=0.75,
        max_lifetime=4.5,
        render_scale=1.25,
        bounce_x=True,
        bounce_y=True,
    )
    pool, context, runner = _runtime(document)
    runner.start(context)

    event = runner.tick(context).event
    indices = np.asarray(event.indices, dtype=np.intp)

    assert pool.batch_spawn_calls == 1
    assert np.all(pool.data["friction"][indices] == pytest.approx(0.15))
    assert np.all(pool.data["time_scale"][indices] == pytest.approx(0.75))
    assert np.all(pool.data["max_lifetime"][indices] == pytest.approx(4.5))
    assert np.all(pool.data["render_scale"][indices] == pytest.approx(1.25))
    assert np.all(pool.data["angular_vel"][indices] == pytest.approx(math.pi / 2))
    assert np.all((pool.data["flags"][indices] & 0x0001) != 0)
    assert np.all((pool.data["flags"][indices] & 0x0002) != 0)
    assert not pool.emitter_callbacks
    assert not pool.death_handlers


def test_automatic_owner_tags_are_unique_and_engine_namespace_is_rejected():
    program = PatternCompiler().compile(PatternDocument.new())

    first = PatternRunner(program)
    second = PatternRunner(program)

    assert first.owner_tag != second.owner_tag
    assert first.owner_tag >= 100
    with pytest.raises(ValueError, match="engine-reserved"):
        PatternRunner(program, owner_tag=99)


def test_pool_capacity_returns_partial_spawn_without_callbacks():
    document = PatternDocument.new()
    document.shape = replace(document.shape, count=5)
    pool, context, runner = _runtime(document, capacity=3)
    runner.start(context)

    event = runner.tick(context).event

    assert event.requested_count == 5
    assert event.spawned_count == 3
    assert len(pool.free_indices) == 0
    assert pool.batch_spawn_calls == 1
    assert not pool.emitter_callbacks


def test_runtime_failure_has_resource_frame_and_actionable_detail():
    document = PatternDocument.new()
    document.aim = AimSpec(mode="player")
    runner = PatternRunner(PatternCompiler().compile(document), owner_tag=3001)

    class MissingPlayerContext:
        def clear_bullets_by_tag(self, tag):
            return 0

        def get_player(self):
            return None

    context = MissingPlayerContext()
    runner.start(context)

    with pytest.raises(PatternRuntimeError) as caught:
        runner.tick(context)

    assert caught.value.resource_id == document.id
    assert caught.value.frame == 0
    assert "active player" in caught.value.detail
    assert runner.state == PatternRunnerState.ERROR

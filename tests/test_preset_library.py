from pathlib import Path
from time import perf_counter

import numpy as np

from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.pattern import PatternCompiler, PatternRunner, PresetInstance, PresetLibrary, PresetResolver


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "game_content" / "presets" / "builtin_patterns.pystg.json"
EXPECTED_NAMES = {
    "自机狙",
    "奇数弹",
    "偶数弹",
    "圆形开花",
    "扇形扫射",
    "单螺旋",
    "双螺旋",
    "交错螺旋",
    "加速旋转",
    "延迟转向",
    "子弹分裂",
    "速度层叠",
    "波纹",
    "米弹墙",
}


class _Player:
    pos = [0.25, -0.7]


def _run(descriptor):
    resolver = PresetResolver((descriptor,))
    instance = PresetInstance.new(descriptor)
    program = resolver.compile(instance, compiler=PatternCompiler())
    pool = OptimizedBulletPool(max_bullets=max(1024, descriptor.budget["max_bullets_total"] + 16))
    context = StageContext(pool, _Player())
    runner = PatternRunner(program, owner_tag=9001)
    runner.start(context)
    spawned = 0
    while runner.state.value == "running":
        spawned += runner.tick(context).spawned_count
    return instance, program, pool, runner, spawned


def test_builtin_library_contains_the_frozen_starter_set() -> None:
    library = PresetLibrary.load(LIBRARY_PATH)

    assert library.library_id == "builtin.patterns"
    assert library.version == "1.0.0"
    assert {preset.display_name for preset in library.presets} == EXPECTED_NAMES
    assert {preset.category for preset in library.presets} == {"basic", "rotation", "advanced"}
    for preset in library.presets:
        assert preset.parameters
        assert preset.internal_nodes
        assert preset.lifecycle["owner_scope"] == "clip"
        assert preset.budget["max_instances"] == 1


def test_every_builtin_preset_compiles_and_runs_through_the_batch_runtime() -> None:
    library = PresetLibrary.load(LIBRARY_PATH)

    for preset in library.presets:
        _instance, program, pool, runner, spawned = _run(preset)
        assert spawned == preset.budget["max_bullets_total"], preset.display_name
        assert len(runner.spawn_trace) == program.burst_count
        assert pool.batch_spawn_calls == program.burst_count
        assert not pool.death_handlers
        assert not pool.emitter_callbacks


def test_builtin_override_is_formal_runtime_parity() -> None:
    library = PresetLibrary.load(LIBRARY_PATH)
    ring = next(item for item in library.presets if item.display_name == "圆形开花")
    resolver = PresetResolver((ring,))
    instance = PresetInstance.new(ring, parameters={"count": 40, "speed": 3.0})
    resolved = resolver.resolve(instance)
    preset_program = resolver.compile(instance, compiler=PatternCompiler())
    direct_program = PatternCompiler().compile(resolved.document)

    assert preset_program == direct_program
    assert preset_program.content_hash == direct_program.content_hash
    assert preset_program.templates == direct_program.templates
    assert len(preset_program.templates[0].angles) == 40


def test_fixed_builtin_workload_stays_data_oriented() -> None:
    library = PresetLibrary.load(LIBRARY_PATH)
    started = perf_counter()
    total_spawned = 0
    total_batches = 0

    for preset in library.presets:
        _instance, _program, pool, _runner, spawned = _run(preset)
        total_spawned += spawned
        total_batches += pool.batch_spawn_calls

    elapsed_ms = (perf_counter() - started) * 1000.0
    # This is an intentionally generous regression ceiling, not release-grade
    # performance evidence. It catches accidental per-bullet Python expansion.
    assert total_spawned == 1836
    assert total_batches == 101
    assert elapsed_ms < 2500.0


def test_advanced_motion_presets_change_the_vectorized_pool_state() -> None:
    library = PresetLibrary.load(LIBRARY_PATH)
    delayed = next(item for item in library.presets if item.display_name == "延迟转向")
    resolver = PresetResolver((delayed,))
    program = resolver.compile(PresetInstance.new(delayed), compiler=PatternCompiler())
    pool = OptimizedBulletPool(max_bullets=256)
    context = StageContext(pool, _Player())
    runner = PatternRunner(program, owner_tag=9002)
    runner.start(context)
    event = runner.tick(context).event
    indices = np.asarray(event.indices, dtype=np.intp)
    initial_angles = pool.data["angle"][indices].copy()

    for _ in range(20):
        pool.update(1.0 / 60.0)
    assert np.allclose(pool.data["angle"][indices], initial_angles)
    for _ in range(20):
        pool.update(1.0 / 60.0)
    assert not np.allclose(pool.data["angle"][indices], initial_angles)
    assert not pool.death_handlers
    assert not pool.emitter_callbacks


def test_split_preset_uses_one_batch_lifecycle_action_without_callbacks() -> None:
    library = PresetLibrary.load(LIBRARY_PATH)
    split = next(item for item in library.presets if item.display_name == "子弹分裂")
    resolver = PresetResolver((split,))
    program = resolver.compile(PresetInstance.new(split), compiler=PatternCompiler())
    pool = OptimizedBulletPool(max_bullets=512)
    context = StageContext(pool, _Player())
    runner = PatternRunner(program, owner_tag=9003)
    runner.start(context)
    first = runner.tick(context).event

    assert len(first.indices) == 12
    for _ in range(16):
        pool.update(1.0 / 60.0)

    assert int(np.count_nonzero(pool.data["alive"])) == 72
    assert pool.batch_spawn_calls == 2
    assert not pool.death_handlers
    batches = pool.drain_lifecycle_batches()
    assert len(batches) == 1
    assert batches[0].reason == "expired"
    assert batches[0].count == 12

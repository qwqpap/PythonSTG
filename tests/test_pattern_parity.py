from dataclasses import replace

import numpy as np

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.devtools.pattern_lab import PatternSpec, bullet_parameters
from src.devtools.pattern_runtime import PatternPlayback
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.pattern import PatternCompiler, PatternDocument, PatternRunner


class DummyPlayer:
    pos = [0.1, -0.7]


def _run_trace(program):
    pool = OptimizedBulletPool(max_bullets=128)
    context = StageContext(pool, DummyPlayer())
    runner = PatternRunner(program, owner_tag=4242)
    runner.start(context)
    trace = []
    while runner.state.value == "running":
        result = runner.tick(context)
        if result.event:
            indices = np.asarray(result.event.indices, dtype=np.intp)
            trace.append((
                result.event.frame,
                pool.data["pos"][indices].copy(),
                pool.data["vel"][indices].copy(),
                pool.data["tag"][indices].copy(),
            ))
    return trace


def test_same_document_and_seed_produce_identical_formal_traces():
    document = PatternDocument.new()
    document.shape = replace(document.shape, kind="random", count=12)
    document.schedule = replace(document.schedule, interval_frames=2, burst_count=3)
    document.modifiers = replace(document.modifiers, random_speed_variation=0.3)
    document.seed = 987654
    compiler = PatternCompiler()

    first = _run_trace(compiler.compile(document))
    second = _run_trace(compiler.compile(PatternDocument.from_dict(document.to_dict())))

    assert len(first) == len(second)
    for left, right in zip(first, second):
        assert left[0] == right[0]
        for left_array, right_array in zip(left[1:], right[1:]):
            assert np.array_equal(left_array, right_array)


def test_preview_and_game_contexts_consume_the_same_program_and_trace():
    spec = PatternSpec(
        name="FormalParity",
        pattern="spiral",
        count=8,
        bursts=3,
        interval=1,
        angle_offset_per_burst=9.0,
    )
    preview_pool = OptimizedBulletPool(max_bullets=64)
    preview_context = StageContext(preview_pool, DummyPlayer())
    preview = PatternPlayback(spec, owner_tag=4242)
    game_pool = OptimizedBulletPool(max_bullets=64)
    game_context = StageContext(game_pool, DummyPlayer())
    game = PatternRunner(preview.program, owner_tag=4242)
    game.start(game_context)
    preview_trace = []
    game_trace = []
    for _ in range(3):
        assert preview.update(preview_context) == spec.count
        game_result = game.tick(game_context)
        preview_event = preview.runner.last_event
        game_event = game_result.event
        preview_indices = np.asarray(preview_event.indices, dtype=np.intp)
        game_indices = np.asarray(game_event.indices, dtype=np.intp)
        preview_trace.append((
            preview_event.frame,
            preview_pool.data["pos"][preview_indices].copy(),
            preview_pool.data["vel"][preview_indices].copy(),
        ))
        game_trace.append((
            game_event.frame,
            game_pool.data["pos"][game_indices].copy(),
            game_pool.data["vel"][game_indices].copy(),
        ))

    assert game.program is preview.program
    assert [item[0] for item in preview_trace] == [0, 1, 2]
    assert bullet_parameters(spec, 2) == list(zip(
        (
            preview.program.aim_angle + value
            for value in preview.program.templates[2].angle_offsets
        ),
        preview.program.templates[2].speeds,
    ))
    for preview, game in zip(preview_trace, game_trace):
        assert all(np.array_equal(a, b) for a, b in zip(preview[1:], game[1:]))


def test_saved_document_loads_compiles_and_executes_without_python_codegen(tmp_path):
    document = PatternDocument.new("No Codegen")
    store = ResourceStore(ProjectContext(tmp_path))
    path = store.save(document, "patterns/no-codegen.pystg.json")
    loaded = store.load(path)
    program = store.registry["pystg.pattern"].compiler(loaded)

    trace = _run_trace(program)

    assert len(trace) == 1
    assert len(trace[0][1]) == document.shape.count
    assert not list(tmp_path.rglob("*.py"))

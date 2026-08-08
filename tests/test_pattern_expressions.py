"""E5.1 frozen acceptance: restricted expression AST and property bindings.

These tests are the completion gate for the expression/binding half of E5.1
and must pass exactly as written. Do not edit, skip, or xfail them; implement
the contracts they assert instead.

Contract notes:
- ``src/pattern/expressions.py`` exposes ``EXPRESSION_VARIABLES``,
  ``ExpressionError`` (with ``path`` and ``message``), ``parse_expression``,
  and ``compile_expression``.
- ``compile_expression(source) -> CompiledExpression``; calling
  ``compiled.eval(context: Mapping) -> float`` evaluates it. Context keys are
  the declared variables plus ``"rng"`` for the deterministic ``random``.
- Whitelist: numeric literals, ``+ - * / // % **``, unary minus, comparisons,
  ``min`` / ``max`` / ``abs`` / ``clamp``, conditional expressions. Anything
  else (other calls, attribute access, subscription, lambda, imports) raises
  ``ExpressionError``. Division by zero is rejected at compile time.
- Bindings: ``BindingSpec(path, kind, value)`` with kind in ``constant`` /
  ``curve`` / ``variable`` / ``expression``, stored as
  ``PatternDocument.bindings``. Compiled bindings are data in
  ``PatternProgram`` (no callables); runtime evaluation is per-emission on the
  data-oriented path.
"""

import json
import random
from dataclasses import replace

import pytest

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.pattern import (
    BindingSpec,
    PatternCompileError,
    PatternCompiler,
    PatternDocument,
    PatternRunner,
    compile_expression,
)
from src.pattern.expressions import EXPRESSION_VARIABLES, ExpressionError


class DummyPlayer:
    def __init__(self, x=0.0, y=-0.8):
        self.pos = [x, y]


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


# --------------------------------------------------------------------------
# Expression AST
# --------------------------------------------------------------------------


def test_expression_variable_set_is_exactly_declared():
    assert EXPRESSION_VARIABLES == {
        "frame",
        "time",
        "burst_index",
        "player_x",
        "player_y",
        "boss_x",
        "boss_y",
        "random",
    }


def test_whitelisted_arithmetic_evaluates_exact_values():
    assert compile_expression("frame / 60.0 * 2").eval({"frame": 30}) == pytest.approx(1.0)
    assert compile_expression("1 + 2 * 3").eval({}) == pytest.approx(7.0)
    assert compile_expression("frame ** 2").eval({"frame": 4}) == pytest.approx(16.0)
    assert compile_expression("frame % 7").eval({"frame": 10}) == pytest.approx(3.0)
    assert compile_expression("frame // 10").eval({"frame": 95}) == pytest.approx(9.0)
    assert compile_expression("-frame").eval({"frame": 5}) == pytest.approx(-5.0)


def test_whitelisted_helpers_evaluate_exact_values():
    assert compile_expression("min(frame, 10) * 3").eval({"frame": 5}) == pytest.approx(15.0)
    assert compile_expression("min(frame, 10) * 3").eval({"frame": 99}) == pytest.approx(30.0)
    assert compile_expression("clamp(frame, 0, 10)").eval({"frame": -3}) == pytest.approx(0.0)
    assert compile_expression("clamp(frame, 0, 10)").eval({"frame": 42}) == pytest.approx(10.0)
    assert compile_expression("abs(frame - 60)").eval({"frame": 70}) == pytest.approx(10.0)
    assert compile_expression(
        "frame if frame > 0 else 0"
    ).eval({"frame": -4}) == pytest.approx(0.0)
    assert compile_expression(
        "frame if frame > 0 else 0"
    ).eval({"frame": 4}) == pytest.approx(4.0)


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os')",
        "open('x')",
        "eval('1')",
        "print(1)",
        "len(frame)",
        "str(frame)",
    ],
)
def test_expression_rejects_calls_outside_the_whitelist(source):
    with pytest.raises(ExpressionError):
        compile_expression(source)


@pytest.mark.parametrize(
    "source",
    [
        "frame.__class__",
        "frame.name",
        "[1, 2][0]",
        "frame[0]",
        "lambda: 1",
        "frame.x",
    ],
)
def test_expression_rejects_attribute_access_subscription_and_lambda(source):
    with pytest.raises(ExpressionError):
        compile_expression(source)


def test_expression_rejects_unknown_variables():
    with pytest.raises(ExpressionError) as caught:
        compile_expression("mystery + 1")
    assert "mystery" in caught.value.message


def test_expression_rejects_syntax_errors():
    with pytest.raises(ExpressionError):
        compile_expression("frame +")


def test_expression_rejects_division_by_zero_at_compile_time():
    with pytest.raises(ExpressionError):
        compile_expression("1.0 / 0.0")
    with pytest.raises(ExpressionError):
        compile_expression("frame // 0")


def test_expression_evaluates_declared_variables_from_context():
    compiled = compile_expression(
        "frame + time + burst_index + player_x + player_y + boss_x + boss_y"
    )
    context = {
        "frame": 1,
        "time": 2,
        "burst_index": 3,
        "player_x": 4,
        "player_y": 5,
        "boss_x": 6,
        "boss_y": 7,
    }
    assert compiled.eval(context) == pytest.approx(28.0)


def test_random_variable_is_seed_deterministic():
    compiled = compile_expression("random")

    first = compiled.eval({"rng": random.Random(77)})
    second = compiled.eval({"rng": random.Random(77)})
    third = compiled.eval({"rng": random.Random(78)})

    assert first == second
    assert first != third


# --------------------------------------------------------------------------
# Bindings
# --------------------------------------------------------------------------


def test_binding_kinds_are_validated():
    valid = (
        BindingSpec(path="motion.speed", kind="constant", value=2.5),
        BindingSpec(path="motion.speed", kind="curve", value="res://c.pystg.json"),
        BindingSpec(path="motion.speed", kind="variable", value="frame"),
        BindingSpec(path="motion.speed", kind="expression", value="frame / 60.0"),
    )
    for binding in valid:
        binding.validate()

    with pytest.raises(ValueError):
        BindingSpec(path="motion.speed", kind="magic", value=1.0).validate()
    with pytest.raises(ValueError):
        BindingSpec(path="", kind="constant", value=1.0).validate()
    with pytest.raises(ValueError):
        BindingSpec(path="motion.speed", kind="constant", value="not-a-number").validate()


def test_binding_to_unknown_property_diagnostic(tmp_path):
    document = PatternDocument.new()
    document.bindings = (
        BindingSpec(path="motion.nope", kind="constant", value=1.0),
    )

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document, project=_project(tmp_path))

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.resource_id == document.id
    assert diagnostic.code == "unknown_binding_target"
    assert "motion.nope" in diagnostic.path


def test_binding_type_mismatch_diagnostic(tmp_path):
    document = PatternDocument.new()
    document.bindings = (
        BindingSpec(path="motion.bounce_x", kind="constant", value=1.5),
    )

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document, project=_project(tmp_path))

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.resource_id == document.id
    assert diagnostic.code == "binding_type_mismatch"
    assert "motion.bounce_x" in diagnostic.path


def test_binding_to_missing_curve_resource_diagnostic(tmp_path):
    document = PatternDocument.new()
    document.bindings = (
        BindingSpec(
            path="motion.speed",
            kind="curve",
            value="res://game_content/curves/missing.pystg.json",
        ),
    )

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document, project=_project(tmp_path))

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.resource_id == document.id
    assert diagnostic.code in {"missing_resource", "missing_curve_resource"}
    assert "motion.speed" in diagnostic.path


def test_invalid_expression_binding_diagnostic_carries_path(tmp_path):
    document = PatternDocument.new()
    document.bindings = (
        BindingSpec(path="motion.speed", kind="expression", value="frame + __import__('os')"),
    )

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document, project=_project(tmp_path))

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.resource_id == document.id
    assert diagnostic.code == "invalid_expression"
    assert "motion.speed" in diagnostic.path


def test_bindings_round_trip_through_the_document():
    document = PatternDocument.new()
    document.bindings = (
        BindingSpec(path="motion.speed", kind="constant", value=2.5),
        BindingSpec(path="motion.spin", kind="expression", value="burst_index * 5"),
    )

    reloaded = PatternDocument.from_dict(json.loads(json.dumps(document.to_dict())))

    assert reloaded.bindings == document.bindings
    compiler = PatternCompiler()
    assert compiler.compile(reloaded) == compiler.compile(document)


def test_legacy_pattern_without_bindings_field_still_loads():
    payload = PatternDocument.new().to_dict()
    payload.pop("bindings")

    document = PatternDocument.from_dict(payload)

    assert document.bindings == ()
    assert PatternCompiler().compile(document).bindings == ()


def test_binding_compiles_into_program_as_data_not_callbacks(tmp_path):
    project = _project(tmp_path)
    document = PatternDocument.new()
    document.bindings = (
        BindingSpec(path="motion.speed", kind="constant", value=2.5),
    )
    program = PatternCompiler().compile(document, project=project)

    assert program.bindings
    assert not any(callable(entry) for entry in program.bindings)
    binding = program.bindings[0]
    assert binding.target_path == "motion.speed"
    assert binding.mode == "constant"

    pool = OptimizedBulletPool(max_bullets=64)
    context = StageContext(pool, DummyPlayer())
    runner = PatternRunner(program, owner_tag=5001)
    runner.start(context)
    runner.tick(context)

    assert not pool.emitter_callbacks
    assert not pool.death_handlers
    assert pool.batch_spawn_calls == 1


def test_curve_binding_changes_speed_over_time_in_runtime(tmp_path):
    project = _project(tmp_path)
    from src.pattern import CurveDocument
    from src.pattern.curves import CurveKeyframe

    curve = CurveDocument.new(
        "Speed Ramp",
        keyframes=(CurveKeyframe(0, 1.0), CurveKeyframe(10, 3.0)),
        interpolation="linear",
    )
    ResourceStore(project).save(curve, "game_content/curves/ramp.pystg.json")

    document = PatternDocument.new()
    document.shape = replace(document.shape, count=1)
    document.schedule = replace(document.schedule, interval_frames=10, burst_count=2)
    document.bindings = (
        BindingSpec(
            path="motion.speed",
            kind="curve",
            value="res://game_content/curves/ramp.pystg.json",
        ),
    )

    program = PatternCompiler().compile(document, project=project)
    pool = OptimizedBulletPool(max_bullets=64)
    context = StageContext(pool, DummyPlayer())
    runner = PatternRunner(program, owner_tag=5002)
    runner.start(context)
    events = [result.event for result in runner.advance(context, 11) if result.event]

    assert [event.frame for event in events] == [0, 10]
    assert events[0].speeds == pytest.approx((1.0,))
    assert events[1].speeds == pytest.approx((3.0,))
    assert not pool.emitter_callbacks
    assert not pool.death_handlers


def test_expression_binding_uses_burst_index_in_runtime():
    document = PatternDocument.new()
    document.shape = replace(document.shape, count=1)
    document.schedule = replace(document.schedule, interval_frames=5, burst_count=3)
    document.bindings = (
        BindingSpec(path="motion.speed", kind="expression", value="1.0 + burst_index"),
    )

    program = PatternCompiler().compile(document)
    pool = OptimizedBulletPool(max_bullets=64)
    context = StageContext(pool, DummyPlayer())
    runner = PatternRunner(program, owner_tag=5003)
    runner.start(context)
    events = [result.event for result in runner.advance(context, 11) if result.event]

    assert [event.frame for event in events] == [0, 5, 10]
    assert [event.speeds for event in events] == [
        pytest.approx((1.0,)),
        pytest.approx((2.0,)),
        pytest.approx((3.0,)),
    ]
    assert not pool.emitter_callbacks
    assert not pool.death_handlers

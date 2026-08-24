"""Direct contract tests for the retained headless expression engine."""

import random

import pytest

from src.core.expressions import (
    EXPRESSION_VARIABLES,
    ExpressionError,
    compile_expression,
)


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
    cases = (
        ("frame / 60.0 * 2", {"frame": 30}, 1.0),
        ("1 + 2 * 3", {}, 7.0),
        ("frame ** 2", {"frame": 4}, 16.0),
        ("frame % 7", {"frame": 10}, 3.0),
        ("frame // 10", {"frame": 95}, 9.0),
        ("-frame", {"frame": 5}, -5.0),
    )
    for source, context, expected in cases:
        assert compile_expression(source).eval(context) == pytest.approx(expected)


def test_whitelisted_helpers_and_conditional_evaluate_exact_values():
    cases = (
        ("min(frame, 10) * 3", {"frame": 5}, 15.0),
        ("min(frame, 10) * 3", {"frame": 99}, 30.0),
        ("clamp(frame, 0, 10)", {"frame": -3}, 0.0),
        ("clamp(frame, 0, 10)", {"frame": 42}, 10.0),
        ("abs(frame - 60)", {"frame": 70}, 10.0),
        ("frame if frame > 0 else 0", {"frame": -4}, 0.0),
        ("frame if frame > 0 else 0", {"frame": 4}, 4.0),
    )
    for source, context, expected in cases:
        assert compile_expression(source).eval(context) == pytest.approx(expected)


@pytest.mark.parametrize(
    "source",
    (
        "__import__('os')",
        "open('x')",
        "eval('1')",
        "print(1)",
        "len(frame)",
        "str(frame)",
    ),
)
def test_expression_rejects_calls_outside_the_whitelist(source):
    with pytest.raises(ExpressionError):
        compile_expression(source)


@pytest.mark.parametrize(
    "source",
    (
        "frame.__class__",
        "frame.name",
        "[1, 2][0]",
        "frame[0]",
        "lambda: 1",
        "frame.x",
    ),
)
def test_expression_rejects_unsupported_ast_nodes(source):
    with pytest.raises(ExpressionError):
        compile_expression(source)


def test_expression_rejects_unknown_variables_and_syntax_errors():
    with pytest.raises(ExpressionError) as caught:
        compile_expression("mystery + 1")
    assert "mystery" in caught.value.message

    with pytest.raises(ExpressionError, match="syntax error"):
        compile_expression("frame +")


@pytest.mark.parametrize("source", ("1.0 / 0.0", "frame // 0", "frame % 0"))
def test_expression_rejects_constant_division_by_zero(source):
    with pytest.raises(ExpressionError, match="division by zero"):
        compile_expression(source)


def test_expression_evaluates_declared_variables_from_context():
    compiled = compile_expression(
        "frame + time + burst_index + player_x + player_y + boss_x + boss_y"
    )
    assert compiled.eval(
        {
            "frame": 1,
            "time": 2,
            "burst_index": 3,
            "player_x": 4,
            "player_y": 5,
            "boss_x": 6,
            "boss_y": 7,
        }
    ) == pytest.approx(28.0)


def test_random_variable_uses_only_the_supplied_deterministic_rng():
    compiled = compile_expression("random")
    first = compiled.eval({"rng": random.Random(77)})
    second = compiled.eval({"rng": random.Random(77)})
    third = compiled.eval({"rng": random.Random(78)})

    assert first == second
    assert first != third
    with pytest.raises(ExpressionError, match="deterministic rng"):
        compiled.eval({})

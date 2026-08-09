"""Restricted whitelisted expression AST for data-authored bindings.

This module implements the established expression contract:

- ``EXPRESSION_VARIABLES`` is exactly the declared variable set.
- The whitelist covers numeric literals, ``+ - * / // % **``, unary minus,
  comparisons, ``min`` / ``max`` / ``abs`` / ``clamp``, and conditional
  expressions. Everything else (other calls, attribute access, subscription,
  lambda, imports) raises ``ExpressionError`` at compile time.
- Division by zero on constant operands is rejected at compile time.
- ``random`` draws from the deterministic RNG provided in the evaluation
  context (``context["rng"]``); it never reads global state.

Compiled expressions are plain data (nested tuples) with an interpreter, so
``PatternProgram`` can carry them without installing any callable or calling
``eval``/``exec``.
"""

from __future__ import annotations

import ast as _ast
import math
from dataclasses import dataclass
from typing import Any, Mapping

EXPRESSION_VARIABLES = frozenset(
    {
        "frame",
        "time",
        "burst_index",
        "player_x",
        "player_y",
        "boss_x",
        "boss_y",
        "random",
    }
)

_WHITELISTED_FUNCTIONS = frozenset({"min", "max", "abs", "clamp"})
_FUNCTION_ARITY = {
    "min": (1, None),
    "max": (1, None),
    "abs": (1, 1),
    "clamp": (3, 3),
}

_BIN_OPS = {
    _ast.Add: "add",
    _ast.Sub: "sub",
    _ast.Mult: "mul",
    _ast.Div: "truediv",
    _ast.FloorDiv: "floordiv",
    _ast.Mod: "mod",
    _ast.Pow: "pow",
}

_CMP_OPS = {
    _ast.Lt: "lt",
    _ast.LtE: "le",
    _ast.Gt: "gt",
    _ast.GtE: "ge",
    _ast.Eq: "eq",
    _ast.NotEq: "ne",
}


class ExpressionError(ValueError):
    """Raised when an expression violates the whitelist or cannot evaluate."""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


def _finite(value: Any, path: str) -> float:
    """Convert one numeric value while normalizing overflow/domain failures."""

    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ExpressionError(path, f"expression produced an invalid number: {exc}") from exc
    if not math.isfinite(result):
        raise ExpressionError(path, "expression must not produce non-finite values")
    return result


def _arity_error(name: str, count: int) -> ExpressionError | None:
    minimum, maximum = _FUNCTION_ARITY[name]
    if count < minimum or (maximum is not None and count > maximum):
        if maximum is None:
            expected = f"at least {minimum}"
        elif minimum == maximum:
            expected = str(minimum)
        else:
            expected = f"{minimum}..{maximum}"
        return ExpressionError(
            "expression", f"{name} expects {expected} argument(s), got {count}"
        )
    return None


def _compile_node(ast_node: _ast.AST, allowed_variables: frozenset[str] | None = None) -> tuple:
    if allowed_variables is None:
        allowed_variables = EXPRESSION_VARIABLES
    if isinstance(ast_node, _ast.Constant):
        if isinstance(ast_node.value, bool):
            raise ExpressionError(
                "expression", "boolean literals are not supported; use 1/0"
            )
        if not isinstance(ast_node.value, (int, float)):
            raise ExpressionError(
                "expression",
                f"literal type {type(ast_node.value).__name__} is not supported",
            )
        return ("num", _finite(ast_node.value, "expression"))
    if isinstance(ast_node, _ast.Name):
        if ast_node.id not in allowed_variables:
            raise ExpressionError("expression", f"unknown variable {ast_node.id!r}")
        return ("var", ast_node.id)
    if isinstance(ast_node, _ast.BinOp):
        op = _BIN_OPS.get(type(ast_node.op))
        if op is None:
            raise ExpressionError(
                "expression",
                f"unsupported binary operator {type(ast_node.op).__name__}",
            )
        left = _compile_node(ast_node.left, allowed_variables)
        right = _compile_node(ast_node.right, allowed_variables)
        if op in {"truediv", "floordiv", "mod"} and right[0] == "num":
            if right[1] == 0.0:
                raise ExpressionError("expression", "division by zero is not allowed")
        return ("bin", op, left, right)
    if isinstance(ast_node, _ast.UnaryOp):
        if isinstance(ast_node.op, _ast.USub):
            return ("unary", "neg", _compile_node(ast_node.operand, allowed_variables))
        if isinstance(ast_node.op, _ast.UAdd):
            return ("unary", "pos", _compile_node(ast_node.operand, allowed_variables))
        raise ExpressionError(
            "expression", f"unsupported unary operator {type(ast_node.op).__name__}"
        )
    if isinstance(ast_node, _ast.Call):
        if not isinstance(ast_node.func, _ast.Name):
            raise ExpressionError(
                "expression", "function calls outside the whitelist are rejected"
            )
        name = ast_node.func.id
        if name not in _WHITELISTED_FUNCTIONS:
            raise ExpressionError(
                "expression", f"function call {name!r} is outside the whitelist"
            )
        if ast_node.keywords:
            raise ExpressionError(
                "expression", "keyword arguments are not supported in expressions"
            )
        arity_error = _arity_error(name, len(ast_node.args))
        if arity_error is not None:
            raise arity_error
        args = tuple(
            _compile_node(item, allowed_variables) for item in ast_node.args
        )
        return ("call", name, args)
    if isinstance(ast_node, _ast.Compare):
        if len(ast_node.ops) != 1 or len(ast_node.comparators) != 1:
            raise ExpressionError(
                "expression", "chained comparisons are not supported"
            )
        op = _CMP_OPS.get(type(ast_node.ops[0]))
        if op is None:
            raise ExpressionError(
                "expression",
                f"unsupported comparison {type(ast_node.ops[0]).__name__}",
            )
        return (
            "cmp",
            op,
            _compile_node(ast_node.left, allowed_variables),
            _compile_node(ast_node.comparators[0], allowed_variables),
        )
    if isinstance(ast_node, _ast.IfExp):
        return (
            "cond",
            _compile_node(ast_node.test, allowed_variables),
            _compile_node(ast_node.body, allowed_variables),
            _compile_node(ast_node.orelse, allowed_variables),
        )
    raise ExpressionError(
        "expression", f"unsupported expression node: {type(ast_node).__name__}"
    )


@dataclass(frozen=True)
class CompiledExpression:
    """An immutable, serializable, callable-free compiled expression."""

    source: str
    node: tuple

    def eval(self, context: Mapping[str, Any]) -> float:
        return evaluate_node(self.node, context)

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "node": self.node}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CompiledExpression":
        if not isinstance(data, Mapping):
            raise ExpressionError("expression", "compiled expression must be an object")
        source = data.get("source", "")
        if not isinstance(source, str) or not source.strip():
            raise ExpressionError("expression", "compiled expression source must be text")
        node = data.get("node")
        return cls(source=source.strip(), node=_normalize_node(node))


def parse_expression(source: str) -> tuple:
    """Parse and validate ``source`` into the portable node tree."""
    return compile_expression(source).node


def compile_expression(
    source: str, *, extra_variables: frozenset[str] = frozenset()
) -> CompiledExpression:
    """Compile a whitelisted expression string into portable data.

    ``extra_variables`` extends the declared variable set for domain contexts
    (e.g. the UI document ``value`` variable).
    """
    if not isinstance(source, str) or not source.strip():
        raise ExpressionError("expression", "must be a non-empty string")
    try:
        tree = _ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(
            "expression", f"syntax error: {exc.msg} at line {exc.lineno}"
        ) from exc
    allowed = EXPRESSION_VARIABLES | frozenset(extra_variables)
    node = _fold_constants(_compile_node(tree.body, allowed))
    return CompiledExpression(source=source.strip(), node=node)


def _is_constant_node(node: tuple) -> bool:
    kind = node[0]
    if kind == "num":
        return True
    if kind == "var":
        return False
    if kind == "unary":
        return _is_constant_node(node[2])
    if kind in {"bin", "cmp"}:
        return _is_constant_node(node[2]) and _is_constant_node(node[3])
    if kind == "call":
        return all(_is_constant_node(item) for item in node[2])
    if kind == "cond":
        return all(_is_constant_node(item) for item in node[1:])
    return False


def _fold_constants(node: tuple) -> tuple:
    kind = node[0]
    if kind == "unary":
        node = (kind, node[1], _fold_constants(node[2]))
    elif kind in {"bin", "cmp"}:
        node = (kind, node[1], _fold_constants(node[2]), _fold_constants(node[3]))
    elif kind == "call":
        node = (kind, node[1], tuple(_fold_constants(item) for item in node[2]))
    elif kind == "cond":
        node = (kind, *(_fold_constants(item) for item in node[1:]))
    if _is_constant_node(node):
        return ("num", _finite(evaluate_node(node, {}), "expression"))
    return node


def _normalize_node(value: Any) -> tuple:
    """Validate JSON-decoded compiled data without accepting executable values."""
    if not isinstance(value, (tuple, list)) or not value or not isinstance(value[0], str):
        raise ExpressionError("expression", "compiled expression node is malformed")
    kind = value[0]
    if kind == "num":
        if len(value) != 2 or isinstance(value[1], bool) or not isinstance(value[1], (int, float)):
            raise ExpressionError("expression", "compiled numeric node is malformed")
        return ("num", _finite(value[1], "expression"))
    if kind == "var":
        if len(value) != 2 or value[1] not in EXPRESSION_VARIABLES:
            raise ExpressionError("expression", "compiled variable node is malformed")
        return ("var", value[1])
    if kind == "unary":
        if len(value) != 3 or value[1] not in {"neg", "pos"}:
            raise ExpressionError("expression", "compiled unary node is malformed")
        return ("unary", value[1], _normalize_node(value[2]))
    if kind in {"bin", "cmp"}:
        allowed = _BIN_OPS.values() if kind == "bin" else _CMP_OPS.values()
        if len(value) != 4 or value[1] not in allowed:
            raise ExpressionError("expression", "compiled operator node is malformed")
        return (kind, value[1], _normalize_node(value[2]), _normalize_node(value[3]))
    if kind == "call":
        if len(value) != 3 or value[1] not in _WHITELISTED_FUNCTIONS:
            raise ExpressionError("expression", "compiled call node is malformed")
        args = value[2]
        if not isinstance(args, (tuple, list)):
            raise ExpressionError("expression", "compiled call arguments are malformed")
        arity_error = _arity_error(value[1], len(args))
        if arity_error is not None:
            raise arity_error
        return ("call", value[1], tuple(_normalize_node(item) for item in args))
    if kind == "cond":
        if len(value) != 4:
            raise ExpressionError("expression", "compiled conditional node is malformed")
        return ("cond", *(_normalize_node(item) for item in value[1:]))
    raise ExpressionError("expression", f"unknown compiled node kind {kind!r}")


def evaluate_node(node: tuple, context: Mapping[str, Any]) -> float:
    """Interpret one portable expression node without eval/exec."""
    try:
        kind = node[0]
        if kind == "num":
            return _finite(node[1], "runtime")
        if kind == "var":
            name = node[1]
            if name == "random":
                rng = context.get("rng")
                if rng is None:
                    raise ExpressionError(
                        "runtime", "random requires a deterministic rng in the context"
                    )
                return _finite(rng.random(), "runtime")
            value = context.get(name, 0.0)
            return _finite(value, "runtime")
        if kind == "bin":
            _, op, left_node, right_node = node
            left = evaluate_node(left_node, context)
            right = evaluate_node(right_node, context)
            if op == "add":
                return _finite(left + right, "runtime")
            if op == "sub":
                return _finite(left - right, "runtime")
            if op == "mul":
                return _finite(left * right, "runtime")
            if op == "truediv":
                if right == 0.0:
                    raise ExpressionError("runtime", "division by zero")
                return _finite(left / right, "runtime")
            if op == "floordiv":
                if right == 0.0:
                    raise ExpressionError("runtime", "division by zero")
                return _finite(math.floor(left / right), "runtime")
            if op == "mod":
                if right == 0.0:
                    raise ExpressionError("runtime", "division by zero")
                return _finite(math.fmod(left, right), "runtime")
            if op == "pow":
                return _finite(math.pow(left, right), "runtime")
            raise ExpressionError("runtime", f"unknown binary operator {op!r}")
        if kind == "unary":
            _, op, operand_node = node
            value = evaluate_node(operand_node, context)
            if op not in {"neg", "pos"}:
                raise ExpressionError("runtime", f"unknown unary operator {op!r}")
            return _finite(-value if op == "neg" else value, "runtime")
        if kind == "call":
            _, name, args = node
            if name not in _WHITELISTED_FUNCTIONS:
                raise ExpressionError("runtime", f"unknown whitelisted function {name!r}")
            arity_error = _arity_error(name, len(args))
            if arity_error is not None:
                raise ExpressionError("runtime", arity_error.message)
            values = tuple(evaluate_node(item, context) for item in args)
            if name == "min":
                return _finite(min(values), "runtime")
            if name == "max":
                return _finite(max(values), "runtime")
            if name == "abs":
                return _finite(abs(values[0]), "runtime")
            if name == "clamp":
                value, low, high = values
                return _finite(max(low, min(high, value)), "runtime")
        if kind == "cmp":
            _, op, left_node, right_node = node
            left = evaluate_node(left_node, context)
            right = evaluate_node(right_node, context)
            if op == "lt":
                return 1.0 if left < right else 0.0
            if op == "le":
                return 1.0 if left <= right else 0.0
            if op == "gt":
                return 1.0 if left > right else 0.0
            if op == "ge":
                return 1.0 if left >= right else 0.0
            if op == "eq":
                return 1.0 if left == right else 0.0
            if op == "ne":
                return 1.0 if left != right else 0.0
            raise ExpressionError("runtime", f"unknown comparison {op!r}")
        if kind == "cond":
            _, cond_node, true_node, false_node = node
            if evaluate_node(cond_node, context) != 0.0:
                return _finite(evaluate_node(true_node, context), "runtime")
            return _finite(evaluate_node(false_node, context), "runtime")
        raise ExpressionError("runtime", f"unknown expression node kind {kind!r}")
    except ExpressionError:
        raise
    except (ArithmeticError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise ExpressionError("runtime", f"malformed or invalid expression: {exc}") from exc

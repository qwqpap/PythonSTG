"""Headless Timeline projection derived from authoring nodes and runtime Trace.

The projection is disposable view data.  It is never serialized and never
becomes a second authoring model.
"""

from __future__ import annotations

import ast
import json
import operator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import dsl
from .program import AuthoringProgram, Expr, LogicalUnit, Node, ProgramError, Ref
from .python_source import find_python_module_source, load_template_source_definitions
from .templates import (
    TemplateExpansionError,
    TemplateRegistry,
    TemplateResolutionError,
    expand_nodes,
)


@dataclass(frozen=True)
class Unknown:
    """A frame boundary that cannot be proven from declarative source."""

    reason: str

    def __str__(self) -> str:
        return "未知"


Frame = int | Unknown


class _StaticTemplateUnsupported(Exception):
    """A source template cannot be proven without executing author code."""


@dataclass(frozen=True)
class _StaticTemplatePlan:
    signature: Any
    function: ast.FunctionDef
    constructors: Mapping[str, Any]
    module_aliases: frozenset[str]


class _StaticTemplateEvaluator:
    """Interpret a deliberately small, side-effect-free template subset."""

    _BINARY_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
    }
    _UNARY_OPERATORS = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
        ast.Not: operator.not_,
    }

    def __init__(
        self,
        values: Mapping[str, Any],
        constructors: Mapping[str, Any],
        module_aliases: frozenset[str],
    ) -> None:
        self.values = dict(values)
        self.constructors = constructors
        self.module_aliases = module_aliases

    def nodes(self, function: ast.FunctionDef) -> list[Node]:
        returned, value = self._block(function.body)
        if not returned:
            raise _StaticTemplateUnsupported("template has no static return")
        if isinstance(value, Node):
            nodes = [value]
        elif isinstance(value, (list, tuple)) and all(
            isinstance(item, Node) for item in value
        ):
            nodes = list(value)
        else:
            raise _StaticTemplateUnsupported("template return is not a node sequence")
        if len(nodes) > 4096:
            raise _StaticTemplateUnsupported("template result is too large for static analysis")
        return nodes

    def _block(self, statements: Sequence[ast.stmt]) -> tuple[bool, Any]:
        for statement in statements:
            if isinstance(statement, ast.Return):
                return True, self._value(statement.value)
            if isinstance(statement, ast.Assign):
                if len(statement.targets) != 1 or not isinstance(
                    statement.targets[0], ast.Name
                ):
                    raise _StaticTemplateUnsupported("unsupported template assignment")
                self.values[statement.targets[0].id] = self._value(statement.value)
                continue
            if isinstance(statement, ast.AnnAssign):
                if not isinstance(statement.target, ast.Name) or statement.value is None:
                    raise _StaticTemplateUnsupported("unsupported template assignment")
                self.values[statement.target.id] = self._value(statement.value)
                continue
            if isinstance(statement, ast.If):
                condition = self._value(statement.test)
                if isinstance(condition, Expr):
                    raise _StaticTemplateUnsupported("dynamic template branch")
                returned, value = self._block(
                    statement.body if bool(condition) else statement.orelse
                )
                if returned:
                    return True, value
                continue
            if isinstance(statement, ast.Pass):
                continue
            if (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                continue
            raise _StaticTemplateUnsupported(
                f"unsupported template statement: {type(statement).__name__}"
            )
        return False, None

    def _value(self, value: ast.AST | None) -> Any:
        if value is None:
            return None
        if isinstance(value, ast.Constant):
            return value.value
        if isinstance(value, ast.Name):
            try:
                return self.values[value.id]
            except KeyError as exc:
                raise _StaticTemplateUnsupported(
                    f"unknown template name: {value.id}"
                ) from exc
        if isinstance(value, ast.List):
            return [self._value(item) for item in value.elts]
        if isinstance(value, ast.Tuple):
            return tuple(self._value(item) for item in value.elts)
        if isinstance(value, ast.Dict):
            if any(key is None for key in value.keys):
                raise _StaticTemplateUnsupported("template dict unpacking is unsupported")
            return {
                self._value(key): self._value(item)
                for key, item in zip(value.keys, value.values)
            }
        if isinstance(value, ast.UnaryOp):
            operation = self._UNARY_OPERATORS.get(type(value.op))
            operand = self._value(value.operand)
            if operation is None or not isinstance(operand, (bool, int, float)):
                raise _StaticTemplateUnsupported("unsupported template unary expression")
            return operation(operand)
        if isinstance(value, ast.BinOp):
            operation = self._BINARY_OPERATORS.get(type(value.op))
            left = self._value(value.left)
            right = self._value(value.right)
            if operation is None or any(
                isinstance(item, bool) or not isinstance(item, (int, float))
                for item in (left, right)
            ):
                raise _StaticTemplateUnsupported("unsupported template arithmetic")
            try:
                result = operation(left, right)
            except (ArithmeticError, OverflowError) as exc:
                raise _StaticTemplateUnsupported("invalid template arithmetic") from exc
            if not isinstance(result, (int, float)) or abs(result) > 1_000_000_000:
                raise _StaticTemplateUnsupported("template arithmetic is out of bounds")
            return result
        if isinstance(value, ast.IfExp):
            condition = self._value(value.test)
            if isinstance(condition, Expr):
                raise _StaticTemplateUnsupported("dynamic template expression")
            return self._value(value.body if bool(condition) else value.orelse)
        if isinstance(value, ast.Call):
            constructor = self._constructor(value.func)
            if constructor is None or any(isinstance(item, ast.Starred) for item in value.args):
                raise _StaticTemplateUnsupported("template call is not a DSL constructor")
            if any(keyword.arg is None for keyword in value.keywords):
                raise _StaticTemplateUnsupported("template keyword expansion is unsupported")
            arguments = [self._value(item) for item in value.args]
            keywords = {
                str(keyword.arg): self._value(keyword.value)
                for keyword in value.keywords
            }
            try:
                return constructor(*arguments, **keywords)
            except (TypeError, ValueError, ProgramError) as exc:
                raise _StaticTemplateUnsupported("invalid static DSL call") from exc
        raise _StaticTemplateUnsupported(
            f"unsupported template expression: {type(value).__name__}"
        )

    def _constructor(self, value: ast.AST) -> Any | None:
        if isinstance(value, ast.Name):
            if value.id in self.values:
                return None
            return self.constructors.get(value.id)
        if (
            isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id not in self.values
            and value.value.id in self.module_aliases
        ):
            return dsl.PUBLIC_CONSTRUCTORS.get(value.attr)
        return None


@dataclass(frozen=True)
class TimelineInterval:
    uid: str
    start: Frame
    end: Frame
    lane: str
    kind: str
    editable: str = "none"
    label: str = ""
    children: tuple["TimelineInterval", ...] = ()
    parent_uid: str | None = None
    observed_start: int | None = None
    observed_end: int | None = None
    observed_branch: str | None = None
    display: str = "auto"

    def __post_init__(self) -> None:
        if self.kind not in {
            "static",
            "branch",
            "parallel",
            "spawned",
            "template",
            "dynamic",
        }:
            raise ValueError(f"unsupported Timeline kind: {self.kind}")
        if self.editable not in {"none", "wait", "duration", "at"}:
            raise ValueError(f"unsupported Timeline edit: {self.editable}")
        if self.display == "auto":
            if isinstance(self.start, Unknown) or isinstance(self.end, Unknown):
                display = "unknown"
            elif self.children:
                display = "aggregate"
            elif self.start == self.end:
                display = "milestone"
            else:
                display = "span"
            object.__setattr__(self, "display", display)
        elif self.display not in {"span", "milestone", "aggregate", "unknown"}:
            raise ValueError(f"unsupported Timeline display: {self.display}")
        if self.observed_branch not in {None, "then", "else"}:
            raise ValueError(f"unsupported observed branch: {self.observed_branch}")


@dataclass(frozen=True)
class TimelineMetricSample:
    """One bounded runtime density sample, never an authoring document."""

    frame: int
    emitted: int
    live: int
    lasers: int

    def __post_init__(self) -> None:
        for name in ("frame", "emitted", "live", "lasers"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"Timeline metric {name} must be a non-negative integer")


@dataclass(frozen=True)
class TimelineProjection:
    unit_id: str
    intervals: tuple[TimelineInterval, ...]
    end: Frame
    trace_run_id: str | None = None
    metrics: tuple[TimelineMetricSample, ...] = ()

    def all_intervals(self) -> tuple[TimelineInterval, ...]:
        values: list[TimelineInterval] = []

        def visit(interval: TimelineInterval) -> None:
            values.append(interval)
            for child in interval.children:
                visit(child)

        for interval in self.intervals:
            visit(interval)
        return tuple(values)

    def find(self, uid: str) -> TimelineInterval | None:
        return next((item for item in self.all_intervals() if item.uid == uid), None)

    @property
    def observed_end(self) -> int | None:
        values = [
            interval.observed_end
            for interval in self.all_intervals()
            if interval.observed_end is not None
        ]
        values.extend(sample.frame for sample in self.metrics)
        return max(values) if values else None


class TimelineAnalyzer:
    """Project one logical unit without importing Qt, editor, or renderer code."""

    def __init__(
        self,
        program: AuthoringProgram,
        *,
        project_root: str | Path | None = None,
        template_registry: TemplateRegistry | None = None,
    ) -> None:
        self.program = program
        self.project_root = Path(project_root).resolve() if project_root is not None else None
        self.template_registry = template_registry or TemplateRegistry.with_builtins()
        self._static_template_plans: dict[str, _StaticTemplatePlan | None] = {}

    def project(self, unit: str | LogicalUnit) -> TimelineProjection:
        selected = self.program.get_unit(unit) if isinstance(unit, str) else unit
        intervals, end = self._sequence(
            selected.body,
            0,
            "main",
            {},
            (selected.id,),
            parent_uid=None,
        )
        return TimelineProjection(selected.id, intervals, end)

    def _sequence(
        self,
        nodes: Sequence[Node],
        cursor: Frame,
        lane: str,
        environment: Mapping[str, Any],
        unit_stack: tuple[str, ...],
        *,
        collect: bool = True,
        parent_uid: str | None,
    ) -> tuple[tuple[TimelineInterval, ...], Frame]:
        intervals: list[TimelineInterval] = []
        for node in nodes:
            interval = self._node(node, cursor, lane, environment, unit_stack)
            interval = replace(interval, parent_uid=parent_uid)
            if collect:
                intervals.append(interval)
            cursor = interval.end
        return tuple(intervals), cursor

    def _node(
        self,
        node: Node,
        start: Frame,
        lane: str,
        environment: Mapping[str, Any],
        unit_stack: tuple[str, ...],
    ) -> TimelineInterval:
        kind = node.kind
        label = _label(node)

        if kind == "Wait":
            frames = _integer(node.arguments.get("frames"), environment)
            end = _advance(start, frames, f"{node.uid}: Wait 使用动态帧数")
            editable = (
                "wait"
                if _literal_integer(node.arguments.get("frames")) is not None
                else "none"
            )
            return TimelineInterval(node.uid, start, end, lane, _static_kind(end), editable, label)

        if kind == "At":
            frame = _integer(node.arguments.get("frame"), environment)
            body_start = _at_frame(start, frame, node.uid)
            children, end = self._sequence(
                node.children.get("body", ()),
                body_start,
                f"{lane}/body:{node.uid}",
                environment,
                unit_stack,
                parent_uid=node.uid,
            )
            editable = "at" if _literal_integer(node.arguments.get("frame")) is not None else "none"
            return TimelineInterval(
                node.uid,
                start,
                end,
                lane,
                _static_kind(end),
                editable,
                label,
                children,
                display=_aggregate_display(end),
            )

        if kind in {"MoveTo", "MoveLinear"}:
            duration = _integer(node.arguments.get("duration", 60), environment)
            end = _advance(start, duration, f"{node.uid}: duration 为动态值")
            editable = (
                "duration"
                if "duration" in node.arguments
                and _literal_integer(node.arguments["duration"]) is not None
                else "none"
            )
            return TimelineInterval(
                node.uid, start, end, lane, _static_kind(end), editable, label
            )

        if kind == "PlayDialogue":
            duration = self._dialogue_duration(node, environment)
            end = _advance(start, duration, f"{node.uid}: 对话持续时间需运行时确定")
            return TimelineInterval(node.uid, start, end, lane, _static_kind(end), label=label)

        if kind == "Repeat":
            count = _integer(node.arguments.get("count"), environment)
            children, body_end = self._sequence(
                node.children.get("body", ()),
                start,
                f"{lane}/body:{node.uid}",
                environment,
                unit_stack,
                parent_uid=node.uid,
            )
            duration = _difference(body_end, start)
            if count is None or duration is None:
                end: Frame = Unknown(f"{node.uid}: Repeat 次数或循环体持续时间未知")
            else:
                end = _advance(start, max(0, count) * duration, "")
            return TimelineInterval(
                node.uid,
                start,
                end,
                lane,
                _static_kind(end),
                label=label,
                children=children,
                display=_aggregate_display(end),
            )

        if kind == "ForEach":
            iterable = _resolved(node.arguments.get("iterable"), environment)
            count = len(iterable) if isinstance(iterable, (list, tuple)) else None
            children, body_end = self._sequence(
                node.children.get("body", ()),
                start,
                f"{lane}/body:{node.uid}",
                environment,
                unit_stack,
                parent_uid=node.uid,
            )
            duration = _difference(body_end, start)
            if count is None or duration is None:
                end = Unknown(f"{node.uid}: ForEach 迭代次数未知")
            else:
                end = _advance(start, count * duration, "")
            return TimelineInterval(
                node.uid,
                start,
                end,
                lane,
                _static_kind(end),
                label=label,
                children=children,
                display=_aggregate_display(end),
            )

        if kind == "While":
            children, _ = self._sequence(
                node.children.get("body", ()),
                start,
                f"{lane}/body:{node.uid}",
                environment,
                unit_stack,
                parent_uid=node.uid,
            )
            return TimelineInterval(
                node.uid,
                start,
                Unknown(f"{node.uid}: While 循环次数未知"),
                lane,
                "dynamic",
                label=label,
                children=children,
                display="unknown",
            )

        if kind == "If":
            children: list[TimelineInterval] = []
            branch_ends: dict[str, Frame] = {}
            for slot, suffix in (("body", "then"), ("else_body", "else")):
                branch_lane = f"{lane}/branch:{node.uid}:{suffix}"
                values, branch_end = self._sequence(
                    node.children.get(slot, ()),
                    start,
                    branch_lane,
                    environment,
                    unit_stack,
                    parent_uid=node.uid,
                )
                children.extend(values)
                branch_ends[suffix] = branch_end
            condition = _resolved(node.arguments.get("condition"), environment)
            if isinstance(condition, bool):
                end = branch_ends["then" if condition else "else"]
            else:
                end = Unknown(f"{node.uid}: If 运行分支未知")
            return TimelineInterval(
                node.uid,
                start,
                end,
                lane,
                "branch" if not isinstance(end, Unknown) else "dynamic",
                label=label,
                children=tuple(children),
                display=_aggregate_display(end),
            )

        if kind == "Parallel":
            children: list[TimelineInterval] = []
            ends: list[Frame] = []
            for index, branch in enumerate(node.children.get("branches", ())):
                branch_lane = f"{lane}/parallel:{node.uid}:{index + 1}"
                values, branch_end = self._sequence(
                    branch.children.get("body", ()),
                    start,
                    branch_lane,
                    environment,
                    unit_stack,
                    parent_uid=node.uid,
                )
                children.extend(values)
                ends.append(branch_end)
            end = _maximum(ends, start) if node.arguments.get("wait", True) else start
            return TimelineInterval(
                node.uid,
                start,
                end,
                lane,
                "parallel",
                label=label,
                children=tuple(children),
                display=_aggregate_display(end),
            )

        if kind == "SpawnTask":
            spawn_lane = f"{lane}/spawn:{node.uid}"
            if "task" in node.arguments:
                target = node.arguments["task"]
                values = node.arguments.get("arguments", {})
                children = self._referenced_body(
                    target,
                    start,
                    spawn_lane,
                    values if isinstance(values, Mapping) else {},
                    unit_stack,
                    expected={"Task"},
                    parent_uid=node.uid,
                )
            else:
                children, _ = self._sequence(
                    node.children.get("body", ()),
                    start,
                    spawn_lane,
                    environment,
                    unit_stack,
                    parent_uid=node.uid,
                )
            return TimelineInterval(
                node.uid,
                start,
                start,
                lane,
                "spawned",
                label=label,
                children=tuple(children),
                display="aggregate",
            )

        if kind == "Call":
            target = node.arguments.get("function")
            positional = node.arguments.get("arguments", ())
            keywords = node.arguments.get("keywords", {})
            call_values: dict[str, Any] = dict(keywords) if isinstance(keywords, Mapping) else {}
            if isinstance(target, Ref):
                try:
                    unit = self.program.get_unit(target.id)
                except ProgramError:
                    unit = None
                if unit is not None:
                    for parameter, value in zip(unit.parameters, positional):
                        call_values.setdefault(parameter.name, value)
            children, end = self._referenced_sequence(
                target,
                start,
                f"{lane}/call:{node.uid}",
                call_values,
                unit_stack,
                expected={"Task", "Function"},
                parent_uid=node.uid,
            )
            return TimelineInterval(
                node.uid,
                start,
                end,
                lane,
                _static_kind(end),
                label=label,
                children=children,
                display=_aggregate_display(end),
            )

        if kind == "RunWave":
            children, end = self._referenced_sequence(
                node.arguments.get("wave_class"),
                start,
                f"{lane}/wave:{node.uid}",
                {},
                unit_stack,
                expected={"Wave"},
                parent_uid=node.uid,
            )
            return TimelineInterval(
                node.uid,
                start,
                end,
                lane,
                _static_kind(end),
                label=label,
                children=children,
                display=_aggregate_display(end),
            )

        if kind == "RunBoss":
            children, end = self._boss_sequence(
                node.arguments.get("boss_def"),
                start,
                lane,
                environment,
                unit_stack,
                parent_uid=node.uid,
            )
            return TimelineInterval(
                node.uid,
                start,
                end,
                lane,
                _static_kind(end),
                label=label,
                children=children,
                display=_aggregate_display(end),
            )

        if kind == "TemplateCall":
            try:
                expanded = self._expand_template_call(node)
                _, end = self._sequence(
                    expanded,
                    start,
                    lane,
                    environment,
                    unit_stack,
                    collect=False,
                    parent_uid=node.uid,
                )
            except (TemplateExpansionError, TemplateResolutionError) as exc:
                end = Unknown(f"{node.uid}: {exc.code}")
            return TimelineInterval(
                node.uid,
                start,
                end,
                lane,
                "template" if not isinstance(end, Unknown) else "dynamic",
                label=label,
                display=_aggregate_display(end),
            )

        if kind in {"RawPython", "Break", "Continue", "Return"}:
            return TimelineInterval(
                node.uid,
                start,
                Unknown(f"{node.uid}: {kind} 控制流需运行时确定"),
                lane,
                "dynamic",
                label=label,
                display="unknown",
            )

        return TimelineInterval(node.uid, start, start, lane, "static", label=label)

    def _expand_template_call(self, node: Node) -> list[Node]:
        """Expand trusted built-ins or statically interpret source-only templates."""

        target = node.template
        if target is None:
            raise TemplateResolutionError("", "template call has no target")
        try:
            self.template_registry.resolve(target.identity)
        except TemplateResolutionError:
            return self._expand_source_template(node)
        return expand_nodes([node], self.template_registry)

    def _expand_source_template(self, node: Node) -> list[Node]:
        """Interpret a restricted template AST without importing its module."""

        target = node.template
        if target is None:
            raise TemplateResolutionError("", "template call has no target")
        plan = self._static_template_plan(target.identity, target.module, target.symbol, target.definition_path)
        if plan is None:
            raise TemplateResolutionError(
                target.identity,
                "template source cannot be proven without executing author code",
            )
        try:
            bound = plan.signature.bind(
                *node.positional_arguments,
                **node.arguments,
            )
            bound.apply_defaults()
            return _StaticTemplateEvaluator(
                bound.arguments,
                plan.constructors,
                plan.module_aliases,
            ).nodes(plan.function)
        except (TypeError, _StaticTemplateUnsupported) as exc:
            raise TemplateResolutionError(target.identity, str(exc)) from exc

    def _static_template_plan(
        self,
        identity: str,
        module: str | None,
        symbol: str,
        definition_path: str | None,
    ) -> _StaticTemplatePlan | None:
        if identity in self._static_template_plans:
            return self._static_template_plans[identity]
        path = Path(definition_path) if definition_path else None
        if path is None or not path.is_file():
            path = find_python_module_source(module) if module else None
        if path is None:
            self._static_template_plans[identity] = None
            return None
        definitions = load_template_source_definitions(path, module_name=module or "")
        definition = next(
            (
                item
                for item in definitions
                if item.identity == identity or item.symbol == symbol
            ),
            None,
        )
        if definition is None or definition.signature is None:
            self._static_template_plans[identity] = None
            return None
        try:
            tree = ast.parse(definition.source, filename=str(path), mode="exec")
            function = next(
                item for item in tree.body if isinstance(item, ast.FunctionDef)
            )
            constructors, module_aliases = _static_dsl_bindings(path, definition.symbol)
        except (OSError, UnicodeDecodeError, SyntaxError, StopIteration):
            self._static_template_plans[identity] = None
            return None
        plan = _StaticTemplatePlan(
            definition.signature,
            function,
            constructors,
            module_aliases,
        )
        self._static_template_plans[identity] = plan
        return plan

    def _referenced_body(
        self,
        target: Any,
        start: Frame,
        lane: str,
        arguments: Mapping[str, Any],
        unit_stack: tuple[str, ...],
        *,
        expected: set[str],
        parent_uid: str,
    ) -> tuple[TimelineInterval, ...]:
        return self._referenced_sequence(
            target,
            start,
            lane,
            arguments,
            unit_stack,
            expected=expected,
            parent_uid=parent_uid,
        )[0]

    def _referenced_sequence(
        self,
        target: Any,
        start: Frame,
        lane: str,
        arguments: Mapping[str, Any],
        unit_stack: tuple[str, ...],
        *,
        expected: set[str],
        parent_uid: str,
    ) -> tuple[tuple[TimelineInterval, ...], Frame]:
        if not isinstance(target, Ref):
            return (), Unknown("引用不是静态 Ref")
        if target.id in unit_stack:
            return (), Unknown(f"递归逻辑单元引用: {' -> '.join((*unit_stack, target.id))}")
        try:
            unit = self.program.get_unit(target.id)
        except Exception:
            return (), Unknown(f"未解析引用: {target.id}")
        if unit.kind not in expected:
            return (), Unknown(f"引用类型错误: {target.id}")
        environment = _bind_parameters(unit, arguments)
        return self._sequence(
            unit.body,
            start,
            lane,
            environment,
            (*unit_stack, unit.id),
            parent_uid=parent_uid,
        )

    def _boss_sequence(
        self,
        target: Any,
        start: Frame,
        lane: str,
        environment: Mapping[str, Any],
        unit_stack: tuple[str, ...],
        *,
        parent_uid: str,
    ) -> tuple[tuple[TimelineInterval, ...], Frame]:
        del environment
        if not isinstance(target, Ref):
            return (), Unknown("Boss 引用不是静态 Ref")
        try:
            boss = self.program.get_unit(target.id)
        except Exception:
            return (), Unknown(f"未解析 Boss: {target.id}")
        if boss.kind != "Boss" or boss.id in unit_stack:
            return (), Unknown(f"Boss 引用无效: {target.id}")
        cursor = start
        children: list[TimelineInterval] = []
        for index, phase_ref in enumerate(boss.metadata.get("phases", ())):
            if not isinstance(phase_ref, Ref):
                return tuple(children), Unknown(f"{boss.id}: phase 不是 Ref")
            try:
                phase = self.program.get_unit(phase_ref.id)
            except Exception:
                return tuple(children), Unknown(f"未解析 phase: {phase_ref.id}")
            phase_lane = f"{lane}/boss:{boss.id}:phase:{index + 1}"
            values, _ = self._sequence(
                phase.body,
                cursor,
                phase_lane,
                {},
                (*unit_stack, boss.id, phase.id),
                parent_uid=parent_uid,
            )
            children.extend(values)
            limit = phase.metadata.get("time_limit", 60.0)
            if isinstance(limit, bool) or not isinstance(limit, (int, float)):
                cursor = Unknown(f"{phase.id}: time_limit 未知")
            else:
                cursor = _advance(cursor, max(0, round(float(limit) * 60)), "")
        return tuple(children), cursor

    def _dialogue_duration(
        self, node: Node, environment: Mapping[str, Any]
    ) -> int | None:
        delay = _integer(node.arguments.get("initial_delay_frames", 0), environment)
        if delay is None:
            return None
        dialogue = _resolved(node.arguments.get("dialogue_list"), environment)
        if isinstance(dialogue, str) and dialogue.startswith("res://"):
            dialogue = self._load_dialogue_resource(dialogue)
        if not isinstance(dialogue, (list, tuple)):
            return None
        total = max(0, delay)
        for item in dialogue:
            if isinstance(item, tuple) and len(item) == 3 and isinstance(item[2], str):
                total += 60 + len(item[2]) * 5
                continue
            if not isinstance(item, Mapping) or not isinstance(item.get("text"), str):
                return None
            duration = item.get("duration")
            if duration is None:
                total += 60 + len(item["text"]) * 5
            elif _literal_integer(duration) is not None:
                total += max(0, int(duration))
            else:
                return None
        return total

    def _load_dialogue_resource(self, uri: str) -> Any:
        if self.project_root is None:
            return None
        relative = uri.removeprefix("res://").split("#", 1)[0]
        path = (self.project_root / Path(relative)).resolve()
        try:
            path.relative_to(self.project_root)
        except ValueError:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None


def overlay_trace(
    projection: TimelineProjection,
    trace_events: Iterable[Mapping[str, Any]],
    run_id: str,
) -> TimelineProjection:
    """Attach one run's observations without changing the static projection."""

    starts: dict[str, list[int]] = {}
    ends: dict[str, list[int]] = {}
    metrics: dict[int, TimelineMetricSample] = {}
    for event in trace_events:
        event_run = event.get("run_id", run_id)
        if event_run != run_id:
            continue
        if event.get("kind") == "metrics":
            try:
                sample = TimelineMetricSample(
                    frame=event.get("frame"),
                    emitted=event.get("emitted"),
                    live=event.get("live"),
                    lasers=event.get("lasers"),
                )
            except (TypeError, ValueError):
                continue
            metrics[sample.frame] = sample
            continue
        uid = event.get("uid")
        phase = event.get("phase")
        frame = event.get("frame")
        if not isinstance(uid, str) or phase not in {"start", "end"}:
            continue
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            continue
        (starts if phase == "start" else ends).setdefault(uid, []).append(frame)

    def apply(interval: TimelineInterval) -> TimelineInterval:
        children = tuple(apply(child) for child in interval.children)
        observed_starts = starts.get(interval.uid, ())
        observed_ends = ends.get(interval.uid, ())
        branch = None
        if interval.kind in {"branch", "dynamic"} and children:
            observed_lanes = {
                child.lane
                for child in _walk_intervals(children)
                if child.observed_start is not None or child.observed_end is not None
            }
            if any(lane.endswith(":then") for lane in observed_lanes):
                branch = "then"
            elif any(lane.endswith(":else") for lane in observed_lanes):
                branch = "else"
        return replace(
            interval,
            children=children,
            observed_start=min(observed_starts) if observed_starts else None,
            observed_end=max(observed_ends) if observed_ends else None,
            observed_branch=branch,
        )

    intervals = tuple(apply(interval) for interval in projection.intervals)
    return TimelineProjection(
        projection.unit_id,
        intervals,
        projection.end,
        trace_run_id=run_id,
        metrics=tuple(metrics[frame] for frame in sorted(metrics)),
    )


def project_timeline(
    program: AuthoringProgram,
    unit: str | LogicalUnit,
    *,
    project_root: str | Path | None = None,
    template_registry: TemplateRegistry | None = None,
) -> TimelineProjection:
    return TimelineAnalyzer(
        program,
        project_root=project_root,
        template_registry=template_registry,
    ).project(unit)


def _static_dsl_bindings(
    source_path: Path,
    function_name: str,
) -> tuple[dict[str, Any], frozenset[str]]:
    """Return only unshadowed, explicit DSL imports visible to a template."""

    text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(source_path), mode="exec")
    constructors: dict[str, Any] = {}
    module_aliases: set[str] = set()

    def unbind(name: str) -> None:
        constructors.pop(name, None)
        module_aliases.discard(name)

    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom):
            if statement.module == "src.authoring.dsl":
                for alias in statement.names:
                    if alias.name == "*":
                        continue
                    local = alias.asname or alias.name
                    constructor = dsl.PUBLIC_CONSTRUCTORS.get(alias.name)
                    if constructor is not None:
                        unbind(local)
                        constructors[local] = constructor
                continue
            if statement.module == "src.authoring":
                for alias in statement.names:
                    if alias.name == "dsl":
                        local = alias.asname or alias.name
                        unbind(local)
                        module_aliases.add(local)
                continue
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "src.authoring.dsl" and alias.asname:
                    unbind(alias.asname)
                    module_aliases.add(alias.asname)
            continue
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if isinstance(statement, ast.FunctionDef) and statement.name == function_name:
                continue
            unbind(statement.name)
            continue
        targets: list[ast.AST] = []
        if isinstance(statement, ast.Assign):
            targets.extend(statement.targets)
        elif isinstance(statement, (ast.AnnAssign, ast.AugAssign)):
            targets.append(statement.target)
        for target in targets:
            if isinstance(target, ast.Name):
                unbind(target.id)
    return constructors, frozenset(module_aliases)


def _bind_parameters(unit: LogicalUnit, arguments: Mapping[str, Any]) -> dict[str, Any]:
    values = dict(arguments)
    for parameter in unit.parameters:
        if parameter.name not in values and parameter.has_default:
            values[parameter.name] = parameter.default
    return values


def _resolved(value: Any, environment: Mapping[str, Any]) -> Any:
    if isinstance(value, Expr) and value.source in environment:
        return environment[value.source]
    return value


def _literal_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _integer(value: Any, environment: Mapping[str, Any]) -> int | None:
    return _literal_integer(_resolved(value, environment))


def _advance(start: Frame, duration: int | None, reason: str) -> Frame:
    if isinstance(start, Unknown):
        return start
    if duration is None:
        return Unknown(reason or "持续时间未知")
    return start + max(0, duration)


def _difference(end: Frame, start: Frame) -> int | None:
    if isinstance(end, Unknown) or isinstance(start, Unknown):
        return None
    return max(0, end - start)


def _maximum(values: Sequence[Frame], default: Frame) -> Frame:
    if not values:
        return default
    unknown = next((value for value in values if isinstance(value, Unknown)), None)
    return unknown if unknown is not None else max(int(value) for value in values)


def _at_frame(start: Frame, frame: int | None, uid: str) -> Frame:
    if isinstance(start, Unknown):
        return start
    if frame is None:
        return Unknown(f"{uid}: At.frame 为动态值")
    return max(start, max(0, frame))


def _static_kind(end: Frame) -> str:
    return "dynamic" if isinstance(end, Unknown) else "static"


def _aggregate_display(end: Frame) -> str:
    return "unknown" if isinstance(end, Unknown) else "aggregate"


def _walk_intervals(
    intervals: Sequence[TimelineInterval],
) -> Iterable[TimelineInterval]:
    for interval in intervals:
        yield interval
        yield from _walk_intervals(interval.children)


def _label(node: Node) -> str:
    if node.kind == "Wait":
        return f"Wait · {node.arguments.get('frames')} 帧"
    if node.kind == "At":
        return f"At · 第 {node.arguments.get('frame')} 帧"
    if node.kind in {"MoveTo", "MoveLinear"}:
        return f"{node.kind} · {node.arguments.get('duration', 60)} 帧"
    if node.kind == "TemplateCall" and node.template is not None:
        return node.template.display_name or node.template.symbol
    for name in ("wave_class", "boss_def", "enemy_class", "task", "function"):
        value = node.arguments.get(name)
        if isinstance(value, Ref):
            return f"{node.kind} · {value.id}"
    return node.kind


__all__ = [
    "Frame",
    "TimelineAnalyzer",
    "TimelineInterval",
    "TimelineMetricSample",
    "TimelineProjection",
    "Unknown",
    "overlay_trace",
    "project_timeline",
]

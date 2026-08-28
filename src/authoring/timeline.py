"""Headless Timeline projection derived from authoring nodes and runtime Trace.

The projection is disposable view data.  It is never serialized and never
becomes a second authoring model.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .program import AuthoringProgram, Expr, LogicalUnit, Node, ProgramError, Ref
from .templates import (
    TemplateExpansionError,
    TemplateRegistry,
    TemplateResolutionError,
    expand_nodes,
    is_template,
)


@dataclass(frozen=True)
class Unknown:
    """A frame boundary that cannot be proven from declarative source."""

    reason: str

    def __str__(self) -> str:
        return "未知"


Frame = int | Unknown


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


@dataclass(frozen=True)
class TimelineProjection:
    unit_id: str
    intervals: tuple[TimelineInterval, ...]
    end: Frame
    trace_run_id: str | None = None

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

    def project(self, unit: str | LogicalUnit) -> TimelineProjection:
        selected = self.program.get_unit(unit) if isinstance(unit, str) else unit
        intervals, end = self._sequence(
            selected.body,
            0,
            "main",
            {},
            (selected.id,),
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
    ) -> tuple[tuple[TimelineInterval, ...], Frame]:
        intervals: list[TimelineInterval] = []
        for node in nodes:
            interval = self._node(node, cursor, lane, environment, unit_stack)
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
                node.children.get("body", ()), body_start, lane, environment, unit_stack
            )
            editable = "at" if _literal_integer(node.arguments.get("frame")) is not None else "none"
            return TimelineInterval(
                node.uid, start, end, lane, _static_kind(end), editable, label, children
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
                node.children.get("body", ()), start, lane, environment, unit_stack
            )
            duration = _difference(body_end, start)
            if count is None or duration is None:
                end: Frame = Unknown(f"{node.uid}: Repeat 次数或循环体持续时间未知")
            else:
                end = _advance(start, max(0, count) * duration, "")
            return TimelineInterval(
                node.uid, start, end, lane, _static_kind(end), label=label, children=children
            )

        if kind == "ForEach":
            iterable = _resolved(node.arguments.get("iterable"), environment)
            count = len(iterable) if isinstance(iterable, (list, tuple)) else None
            children, body_end = self._sequence(
                node.children.get("body", ()), start, lane, environment, unit_stack
            )
            duration = _difference(body_end, start)
            if count is None or duration is None:
                end = Unknown(f"{node.uid}: ForEach 迭代次数未知")
            else:
                end = _advance(start, count * duration, "")
            return TimelineInterval(
                node.uid, start, end, lane, _static_kind(end), label=label, children=children
            )

        if kind == "While":
            children, _ = self._sequence(
                node.children.get("body", ()), start, lane, environment, unit_stack
            )
            return TimelineInterval(
                node.uid,
                start,
                Unknown(f"{node.uid}: While 循环次数未知"),
                lane,
                "dynamic",
                label=label,
                children=children,
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
                )
            else:
                children, _ = self._sequence(
                    node.children.get("body", ()),
                    start,
                    spawn_lane,
                    environment,
                    unit_stack,
                )
            return TimelineInterval(
                node.uid, start, start, lane, "spawned", label=label, children=tuple(children)
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
            )
            return TimelineInterval(
                node.uid, start, end, lane, _static_kind(end), label=label, children=children
            )

        if kind == "RunWave":
            children, end = self._referenced_sequence(
                node.arguments.get("wave_class"),
                start,
                f"{lane}/wave:{node.uid}",
                {},
                unit_stack,
                expected={"Wave"},
            )
            return TimelineInterval(
                node.uid, start, end, lane, _static_kind(end), label=label, children=children
            )

        if kind == "RunBoss":
            children, end = self._boss_sequence(
                node.arguments.get("boss_def"), start, lane, environment, unit_stack
            )
            return TimelineInterval(
                node.uid, start, end, lane, _static_kind(end), label=label, children=children
            )

        if kind == "TemplateCall":
            try:
                self._register_template_target(node)
                expanded = expand_nodes([node], self.template_registry)
                _, end = self._sequence(
                    expanded, start, lane, environment, unit_stack, collect=False
                )
            except (TemplateExpansionError, TemplateResolutionError) as exc:
                end = Unknown(f"{node.uid}: {exc.code}")
            return TimelineInterval(
                node.uid, start, end, lane, "template" if not isinstance(end, Unknown) else "dynamic", label=label
            )

        if kind in {"RawPython", "Break", "Continue", "Return"}:
            return TimelineInterval(
                node.uid,
                start,
                Unknown(f"{node.uid}: {kind} 控制流需运行时确定"),
                lane,
                "dynamic",
                label=label,
            )

        return TimelineInterval(node.uid, start, start, lane, "static", label=label)

    def _register_template_target(self, node: Node) -> None:
        """Load exactly the retained call target, never scan template packages."""

        target = node.template
        if target is None:
            raise TemplateResolutionError("", "template call has no target")
        try:
            self.template_registry.resolve(target.identity)
            return
        except TemplateResolutionError:
            pass
        if not target.module:
            raise TemplateResolutionError(target.identity, "template has no module")
        try:
            value: Any = importlib.import_module(target.module)
            for part in target.symbol.split("."):
                value = getattr(value, part)
            if not is_template(value):
                raise TypeError("resolved symbol is not decorated with @template")
            definition = self.template_registry.register(value)
            self.template_registry.register_alias(target.identity, definition.identity)
        except Exception as exc:
            raise TemplateResolutionError(
                target.identity,
                f"{type(exc).__name__}: {exc}",
            ) from exc

    def _referenced_body(
        self,
        target: Any,
        start: Frame,
        lane: str,
        arguments: Mapping[str, Any],
        unit_stack: tuple[str, ...],
        *,
        expected: set[str],
    ) -> tuple[TimelineInterval, ...]:
        return self._referenced_sequence(
            target, start, lane, arguments, unit_stack, expected=expected
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
        return self._sequence(unit.body, start, lane, environment, (*unit_stack, unit.id))

    def _boss_sequence(
        self,
        target: Any,
        start: Frame,
        lane: str,
        environment: Mapping[str, Any],
        unit_stack: tuple[str, ...],
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
                phase.body, cursor, phase_lane, {}, (*unit_stack, boss.id, phase.id)
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
    """Return a projection whose observed node bounds use one run's Trace."""

    starts: dict[str, list[int]] = {}
    ends: dict[str, list[int]] = {}
    for event in trace_events:
        event_run = event.get("run_id", run_id)
        if event_run != run_id:
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
        if not observed_starts and not observed_ends:
            return replace(interval, children=children)
        start: Frame = min(observed_starts) if observed_starts else interval.start
        end: Frame = (
            max(observed_ends)
            if observed_ends
            else Unknown(f"{interval.uid}: 本次运行尚未结束")
        )
        return replace(interval, start=start, end=end, children=children)

    intervals = tuple(apply(interval) for interval in projection.intervals)
    observed_end = intervals[-1].end if intervals else projection.end
    return TimelineProjection(
        projection.unit_id,
        intervals,
        observed_end,
        trace_run_id=run_id,
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
    "TimelineProjection",
    "Unknown",
    "overlay_trace",
    "project_timeline",
]

"""PatternDocument to immutable PatternProgram compilation."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.core.project_context import ProjectContext

from .bindings import BindingSpec, CompiledBinding
from .document import PatternDocument, PatternDocumentError
from .expressions import ExpressionError, compile_expression
from .graph import (
    GRAPH_NODE_CATEGORIES,
    NODE_TYPES,
    PORT_TYPES,
    BehaviorGraph,
    GraphDocumentError,
)
from .ir import BurstTemplate, PatternProgram
from .script import ScriptBehavior, ScriptProgramData


SpriteIndexResolver = Callable[[str], int]
MAX_COMPILED_BULLETS = 1_000_000


@dataclass(frozen=True)
class PatternDiagnostic:
    severity: str
    code: str
    resource_id: str
    path: str
    message: str


class PatternCompileError(ValueError):
    def __init__(self, diagnostics: tuple[PatternDiagnostic, ...]):
        self.diagnostics = diagnostics
        message = "; ".join(
            f"{item.path}: {item.message}" for item in diagnostics
        )
        super().__init__(message or "pattern compilation failed")


def _clean(value: float, digits: int = 6) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == 0 else rounded


def _diagnostic(
    document: PatternDocument,
    code: str,
    path: str,
    message: str,
) -> PatternDiagnostic:
    return PatternDiagnostic(
        severity="error",
        code=code,
        resource_id=document.id,
        path=path,
        message=message,
    )


# Bindable numeric/bool property paths. Boolean properties reject numeric
# bindings with ``binding_type_mismatch``; unknown paths reject with
# ``unknown_binding_target``.
BINDABLE_TARGETS = {
    "shape.count": "int",
    "shape.origin_x": "float",
    "shape.origin_y": "float",
    "shape.angle_span": "float",
    "shape.line_length": "float",
    "shape.line_angle": "float",
    "aim.angle": "float",
    "schedule.delay_frames": "int",
    "schedule.interval_frames": "int",
    "schedule.burst_count": "int",
    "schedule.loop_count": "int",
    "motion.speed": "float",
    "motion.friction": "float",
    "motion.spin": "float",
    "motion.time_scale": "float",
    "motion.max_lifetime": "float",
    "motion.render_scale": "float",
    "motion.bounce_x": "bool",
    "motion.bounce_y": "bool",
    "modifiers.angle_offset_per_burst": "float",
    "modifiers.speed_offset_per_burst": "float",
    "modifiers.random_speed_variation": "float",
}


def _number(properties: dict, key: str, default: float) -> float:
    value = properties.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GraphDocumentError(
            f"graph.node.properties.{key}", "must be a number"
        )
    return float(value)


def _boolean(properties: dict, key: str, default: bool) -> bool:
    value = properties.get(key, default)
    if not isinstance(value, bool):
        raise GraphDocumentError(
            f"graph.node.properties.{key}", "must be a boolean"
        )
    return value


def _integer(properties: dict, key: str, default: int) -> int:
    value = properties.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise GraphDocumentError(
            f"graph.node.properties.{key}", "must be an integer"
        )
    return value


def fold_graph_to_fields(
    document: PatternDocument,
) -> tuple[dict, tuple[str, ...]]:
    """Validate a graph-mode document and fold it back to recipe fields.

    Returns ``(fields, binding_diagnostic_paths)`` where ``fields`` is the
    replacement kwargs for the recipe-mode compile and the diagnostic paths
    name the graph node properties that produced each binding.
    """
    graph: BehaviorGraph = document.graph
    assert graph is not None

    issues: list[tuple[str, str, str]] = []
    node_by_id = {node.id: node for node in graph.nodes}

    for node in graph.nodes:
        if node.category not in GRAPH_NODE_CATEGORIES:
            issues.append(
                (
                    "unknown_graph_node_type",
                    f"graph.node:{node.id}",
                    f"unknown node category {node.category!r}",
                )
            )
            continue
        allowed_types = NODE_TYPES.get(node.category, ())
        if node.node_type not in allowed_types:
            issues.append(
                (
                    "unknown_graph_node_type",
                    f"graph.node:{node.id}",
                    f"unknown node type {node.node_type!r} for category "
                    f"{node.category!r}",
                )
            )

    for edge in graph.edges:
        if edge.from_node not in node_by_id or edge.to_node not in node_by_id:
            issues.append(
                (
                    "unknown_graph_edge_endpoint",
                    f"graph.edge:{edge.id}",
                    "edge references an unknown node",
                )
            )
            continue
        source = node_by_id[edge.from_node]
        target = node_by_id[edge.to_node]
        if (
            source.category not in PORT_TYPES
            or target.category not in PORT_TYPES
        ):
            continue
        output_type = PORT_TYPES[source.category][1]
        input_type = PORT_TYPES[target.category][0]
        if output_type != input_type:
            issues.append(
                (
                    "port_type_mismatch",
                    f"graph.edge:{edge.id}",
                    f"cannot connect {source.category} output "
                    f"({output_type!r}) to {target.category} input "
                    f"({input_type!r})",
                )
            )

    if _graph_has_cycle(graph):
        issues.append(
            (
                "graph_cycle",
                "graph",
                "the behavior graph contains a cycle",
            )
        )

    if not issues:
        try:
            fields, binding_paths = _fold_main_chain(graph, node_by_id)
        except _GraphStructureError as exc:
            issues.append((exc.code, exc.path, exc.message))
            binding_paths = ()
        except PatternDocumentError as exc:
            issues.append(("invalid_graph", exc.path, exc.detail))
            binding_paths = ()
        if issues:
            raise _issues_as_error(document, issues)
        return fields, binding_paths

    raise _issues_as_error(document, issues)


class _GraphStructureError(GraphDocumentError):
    """Raised by the main-chain fold when the graph topology is broken."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        super().__init__(path, message)


def _issues_as_error(
    document: PatternDocument,
    issues: list[tuple[str, str, str]],
) -> PatternCompileError:
    return PatternCompileError(
        tuple(_diagnostic(document, code, path, message) for code, path, message in issues)
    )


def _graph_has_cycle(graph: BehaviorGraph) -> bool:
    adjacency: dict[str, list[str]] = {}
    for node in graph.nodes:
        adjacency.setdefault(node.id, [])
    for edge in graph.edges:
        adjacency.setdefault(edge.from_node, []).append(edge.to_node)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for target in adjacency.get(node_id, ()):
            if visit(target):
                return True
        visiting.discard(node_id)
        visited.add(node_id)
        return False

    return any(visit(node.id) for node in graph.nodes)


def _fold_main_chain(
    graph: BehaviorGraph,
    node_by_id: dict[str, object],
) -> tuple[dict, tuple[str, ...]]:
    from .document import AimSpec, BulletSpec, ModifierSpec, MotionSpec, ScheduleSpec, ShapeSpec

    nodes = {node.category: node for node in graph.nodes if node.category in PORT_TYPES}
    duplicates = [
        node.category
        for node in graph.nodes
        if node.category in PORT_TYPES
        and sum(1 for item in graph.nodes if item.category == node.category) > 1
    ]
    if duplicates:
        raise _GraphStructureError(
            "multiple_graph_outputs",
            "graph",
            "duplicate nodes for categories: " + ", ".join(sorted(set(duplicates))),
        )
    chain = ["source", "shape", "aim", "schedule", "motion"]
    missing = [category for category in chain if category not in nodes]
    if missing:
        raise _GraphStructureError(
            "missing_graph_connection",
            "graph",
            "missing required nodes: " + ", ".join(missing),
        )

    connection_map = {edge.from_node: edge.to_node for edge in graph.edges}
    for index, category in enumerate(chain[:-1]):
        current = nodes[category]
        nxt = connection_map.get(current.id)
        expected = chain[index + 1]
        if nxt is None or node_by_id.get(nxt) is None:
            raise _GraphStructureError(
                "missing_graph_connection",
                "graph",
                f"{category} node is not connected to the next required node",
            )
        if node_by_id[nxt].category != expected:
            raise _GraphStructureError(
                "missing_graph_connection",
                "graph",
                f"{category} node must connect to a {expected} node, "
                f"got {node_by_id[nxt].category}",
            )

    shape_node = nodes["shape"]
    aim_node = nodes["aim"]
    schedule_node = nodes["schedule"]
    motion_node = nodes["motion"]
    modifier_node = nodes.get("modifier")
    source_node = nodes["source"]

    shape = ShapeSpec(
        kind=shape_node.node_type,
        count=_integer(shape_node.properties, "count", 24),
        origin_x=_number(shape_node.properties, "origin_x", 0.0),
        origin_y=_number(shape_node.properties, "origin_y", 0.65),
        angle_span=_number(shape_node.properties, "angle_span", 360.0),
        line_length=_number(shape_node.properties, "line_length", 1.0),
        line_angle=_number(shape_node.properties, "line_angle", 0.0),
    )
    aim = AimSpec(
        mode=aim_node.node_type,
        angle=_number(aim_node.properties, "angle", 270.0),
    )
    schedule = ScheduleSpec(
        delay_frames=_integer(schedule_node.properties, "delay_frames", 0),
        interval_frames=_integer(
            schedule_node.properties, "interval_frames", 20
        ),
        burst_count=_integer(schedule_node.properties, "burst_count", 1),
        loop_count=(
            _integer(schedule_node.properties, "loop_count", 1)
            if schedule_node.properties.get("loop_count") is not None
            else None
        ),
    )
    motion = MotionSpec(
        speed=_number(motion_node.properties, "speed", 2.0),
        friction=_number(motion_node.properties, "friction", 0.0),
        spin=_number(motion_node.properties, "spin", 0.0),
        time_scale=_number(motion_node.properties, "time_scale", 1.0),
        max_lifetime=_number(motion_node.properties, "max_lifetime", 0.0),
        render_scale=_number(motion_node.properties, "render_scale", 1.0),
        bounce_x=_boolean(motion_node.properties, "bounce_x", False),
        bounce_y=_boolean(motion_node.properties, "bounce_y", False),
    )
    modifiers = ModifierSpec(
        angle_offset_per_burst=_number(
            modifier_node.properties, "angle_offset_per_burst", 0.0
        )
        if modifier_node
        else 0.0,
        speed_offset_per_burst=_number(
            modifier_node.properties, "speed_offset_per_burst", 0.0
        )
        if modifier_node
        else 0.0,
        random_speed_variation=_number(
            modifier_node.properties, "random_speed_variation", 0.0
        )
        if modifier_node
        else 0.0,
    )
    bullet = BulletSpec(
        bullet_type=str(source_node.properties.get("bullet_type", "ball_m")),
        color=str(source_node.properties.get("color", "red")),
        resource=source_node.properties.get("resource"),
    )

    bindings: list[BindingSpec] = [
        BindingSpec.from_dict(item) for item in graph.bindings
    ]
    binding_paths: list[str] = ["graph.bindings" for _ in bindings]
    binding = motion_node.properties.get("binding")
    if binding is not None and not bindings:
        bindings.append(BindingSpec.from_dict(binding))
        binding_paths.append("binding")
    speed_expression = motion_node.properties.get("speed_expression")
    if speed_expression is not None and not any(
        item.path == "motion.speed" for item in bindings
    ):
        bindings.append(
            BindingSpec(
                path="motion.speed",
                kind="expression",
                value=str(speed_expression),
            )
        )
        binding_paths.append("speed_expression")

    fields = {
        "bullet": bullet,
        "shape": shape,
        "aim": aim,
        "schedule": schedule,
        "motion": motion,
        "modifiers": modifiers,
        "bindings": tuple(bindings),
    }
    return fields, tuple(binding_paths)


def build_burst_template(
    *,
    shape,
    motion,
    modifiers,
    seed: int,
    burst_index: int,
) -> BurstTemplate:
    """Build one data-only burst from validated authoring specs.

    The formal compiler and runtime binding path share this function so a
    dynamically bound shape uses exactly the same geometry and seeded random
    sequence as a direct recipe property.
    """
    count = shape.count
    burst_angle = modifiers.angle_offset_per_burst * burst_index
    base_speed = motion.speed + modifiers.speed_offset_per_burst * burst_index
    if base_speed < 0:
        raise PatternDocumentError(
            "modifiers.speed_offset_per_burst",
            f"produces negative speed at burst {burst_index}",
        )

    positions = [(0.0, 0.0)] * count
    speed_factors = [1.0] * count

    if shape.kind == "ring":
        angles = [burst_angle + index * 360.0 / count for index in range(count)]
    elif shape.kind == "arc":
        if abs(shape.angle_span) >= 360.0:
            start = 0.0
            step = shape.angle_span / count
        else:
            start = -shape.angle_span / 2.0
            step = 0.0 if count == 1 else shape.angle_span / (count - 1)
        angles = [burst_angle + start + index * step for index in range(count)]
    elif shape.kind == "spiral":
        step = shape.angle_span / max(1, count)
        angles = [burst_angle + index * step for index in range(count)]
        speed_factors = [
            0.65 + 0.55 * (index / max(1, count - 1))
            for index in range(count)
        ]
    elif shape.kind == "flower":
        angles = [burst_angle + index * 360.0 / count for index in range(count)]
        speed_factors = [
            0.55
            + 0.45
            * abs(math.sin(math.radians(index * shape.angle_span)))
            for index in range(count)
        ]
    elif shape.kind == "line":
        angles = [burst_angle] * count
        direction = math.radians(shape.line_angle)
        for index in range(count):
            t = 0.0 if count == 1 else index / (count - 1) - 0.5
            distance = t * shape.line_length
            positions[index] = (
                math.cos(direction) * distance,
                math.sin(direction) * distance,
            )
    elif shape.kind == "random":
        random_seed = seed + burst_index * 0x9E3779B97F4A7C15
        rng = random.Random(random_seed & 0x7FFF_FFFF_FFFF_FFFF)
        if abs(shape.angle_span) >= 360.0:
            low, high = sorted((0.0, shape.angle_span))
        else:
            low, high = sorted((-shape.angle_span / 2.0, shape.angle_span / 2.0))
        angles = [burst_angle + rng.uniform(low, high) for _ in range(count)]
        variation = modifiers.random_speed_variation
        speed_factors = [
            rng.uniform(1.0 - variation, 1.0 + variation)
            for _ in range(count)
        ]
    else:  # PatternDocument validation makes this unreachable.
        raise PatternDocumentError("shape.kind", f"unsupported shape {shape.kind!r}")

    return BurstTemplate(
        position_offsets=tuple(
            (_clean(x), _clean(y)) for x, y in positions
        ),
        angle_offsets=tuple(_clean(value) for value in angles),
        speeds=tuple(_clean(base_speed * factor) for factor in speed_factors),
    )


def _shape_values(
    document: PatternDocument,
    burst_index: int,
) -> BurstTemplate:
    return build_burst_template(
        shape=document.shape,
        motion=document.motion,
        modifiers=document.modifiers,
        seed=document.seed,
        burst_index=burst_index,
    )


class PatternCompiler:
    """Compiler with content/dependency keyed in-memory caching."""

    def __init__(self) -> None:
        self._cache: dict[str, PatternProgram] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def compile(
        self,
        document: PatternDocument,
        *,
        project: ProjectContext | None = None,
        sprite_index_resolver: SpriteIndexResolver | None = None,
    ) -> PatternProgram:
        try:
            document.validate()
        except PatternDocumentError as exc:
            raise PatternCompileError(
                (_diagnostic(document, "invalid_document", exc.path, exc.detail),)
            ) from exc

        compile_doc = document
        binding_paths: tuple[str, ...] = ()
        if document.graph is not None:
            try:
                fields, binding_paths = fold_graph_to_fields(document)
                compile_doc = replace(document, graph=None, **fields)
            except PatternCompileError:
                raise
            except (PatternDocumentError, GraphDocumentError) as exc:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "invalid_graph",
                            exc.path,
                            exc.message,
                        ),
                    )
                ) from exc

        bindings, binding_token = self._compile_bindings(
            compile_doc.bindings, binding_paths, project, compile_doc
        )
        script_data, script_token = self._compile_script(compile_doc, project)

        sprite_id, dependency_token = self._resolve_sprite(compile_doc, project)
        sprite_index = -1
        if sprite_index_resolver is not None and sprite_id:
            try:
                sprite_index = int(sprite_index_resolver(sprite_id))
            except Exception as exc:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            compile_doc,
                            "sprite_resolution_failed",
                            "bullet.resource",
                            str(exc),
                        ),
                    )
                ) from exc

        canonical = json.dumps(
            compile_doc.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        identity = "\0".join(
            (
                compile_doc.id,
                str(compile_doc.schema_version),
                canonical,
                dependency_token,
                str(sprite_index),
                binding_token,
                script_token,
            )
        )
        content_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        cached = self._cache.get(content_hash)
        if cached is not None:
            return cached

        compiled_bullets = compile_doc.shape.count * compile_doc.schedule.burst_count
        if compiled_bullets > MAX_COMPILED_BULLETS:
            raise PatternCompileError(
                (
                    _diagnostic(
                        compile_doc,
                        "program_too_large",
                        "schedule.burst_count",
                        f"would precompute {compiled_bullets} bullets; "
                        f"the v1 limit is {MAX_COMPILED_BULLETS}",
                    ),
                )
            )

        try:
            templates = tuple(
                _shape_values(compile_doc, burst_index)
                for burst_index in range(compile_doc.schedule.burst_count)
            )
        except PatternDocumentError as exc:
            raise PatternCompileError(
                (_diagnostic(compile_doc, "invalid_program", exc.path, exc.detail),)
            ) from exc

        program = PatternProgram(
            resource_id=compile_doc.id,
            schema_version=compile_doc.schema_version,
            content_hash=content_hash,
            name=compile_doc.name,
            seed=compile_doc.seed,
            origin=(compile_doc.shape.origin_x, compile_doc.shape.origin_y),
            aim_mode=compile_doc.aim.mode,
            aim_angle=compile_doc.aim.angle,
            delay_frames=compile_doc.schedule.delay_frames,
            interval_frames=compile_doc.schedule.interval_frames,
            burst_count=compile_doc.schedule.burst_count,
            loop_count=compile_doc.schedule.loop_count,
            bullet_type=compile_doc.bullet.bullet_type,
            color=compile_doc.bullet.color,
            resource_uri=compile_doc.bullet.resource,
            sprite_id=sprite_id,
            sprite_index=sprite_index,
            friction=compile_doc.motion.friction,
            spin=compile_doc.motion.spin,
            time_scale=compile_doc.motion.time_scale,
            max_lifetime=compile_doc.motion.max_lifetime,
            render_scale=compile_doc.motion.render_scale,
            bounce_x=compile_doc.motion.bounce_x,
            bounce_y=compile_doc.motion.bounce_y,
            speed=compile_doc.motion.speed,
            templates=templates,
            bindings=bindings,
            script=script_data,
            shape_kind=compile_doc.shape.kind,
            shape_count=compile_doc.shape.count,
            shape_angle_span=compile_doc.shape.angle_span,
            shape_line_length=compile_doc.shape.line_length,
            shape_line_angle=compile_doc.shape.line_angle,
            angle_offset_per_burst=compile_doc.modifiers.angle_offset_per_burst,
            speed_offset_per_burst=compile_doc.modifiers.speed_offset_per_burst,
            random_speed_variation=compile_doc.modifiers.random_speed_variation,
        )
        self._cache[content_hash] = program
        return program

    def _compile_bindings(
        self,
        bindings: tuple[BindingSpec, ...],
        diagnostic_paths: tuple[str, ...],
        project: ProjectContext | None,
        document: PatternDocument,
    ) -> tuple[tuple[CompiledBinding, ...], str]:
        if not bindings:
            return (), ""
        seen_targets: set[str] = set()
        for binding in bindings:
            if binding.path in seen_targets:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "duplicate_binding_target",
                            binding.path,
                            f"property {binding.path!r} has more than one binding",
                        ),
                    )
                )
            seen_targets.add(binding.path)
        compiled: list[CompiledBinding] = []
        tokens: list[str] = []
        for index, binding in enumerate(bindings):
            path = diagnostic_paths[index] if index < len(diagnostic_paths) else binding.path
            target = BINDABLE_TARGETS.get(binding.path)
            if target is None:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "unknown_binding_target",
                            path,
                            f"property {binding.path!r} is not bindable",
                        ),
                    )
                )
            if target == "bool":
                if binding.kind != "constant" or not isinstance(binding.value, bool):
                    raise PatternCompileError(
                        (
                            _diagnostic(
                                document,
                                "binding_type_mismatch",
                                path,
                                f"property {binding.path!r} requires a boolean constant",
                            ),
                        )
                    )
            elif isinstance(binding.value, bool):
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "binding_type_mismatch",
                            path,
                            f"property {binding.path!r} requires a numeric binding value",
                        ),
                    )
                )
            if binding.kind == "constant":
                compiled.append(
                    CompiledBinding(
                        target_path=binding.path,
                        mode="constant",
                        value=(
                            bool(binding.value)
                            if target == "bool"
                            else float(binding.value)
                        ),
                    )
                )
            elif binding.kind == "variable":
                compiled.append(
                    CompiledBinding(
                        target_path=binding.path,
                        mode="variable",
                        value=binding.value,
                    )
                )
            elif binding.kind == "curve":
                curve_data, token = self._resolve_curve(
                    binding, project, path, document
                )
                compiled.append(
                    CompiledBinding(
                        target_path=binding.path,
                        mode="curve",
                        curve_frames=curve_data["frames"],
                        curve_values=curve_data["values"],
                        curve_interpolation=curve_data["interpolation"],
                        curve_default=curve_data["default"],
                    )
                )
                tokens.append(token)
            elif binding.kind == "expression":
                try:
                    compiled_expression = compile_expression(binding.value)
                except ExpressionError as exc:
                    raise PatternCompileError(
                        (
                            _diagnostic(
                                document,
                                "invalid_expression",
                                path,
                                exc.message,
                            ),
                        )
                    ) from exc
                compiled.append(
                    CompiledBinding(
                        target_path=binding.path,
                        mode="expression",
                        expression_source=compiled_expression.source,
                        expression_node=compiled_expression.node,
                    )
                )
            else:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "unknown_binding_kind",
                            path,
                            f"unsupported binding kind {binding.kind!r}",
                        ),
                    )
                )
        return tuple(compiled), "|".join(tokens)

    def _resolve_curve(
        self,
        binding: BindingSpec,
        project: ProjectContext | None,
        diagnostic_path: str,
        document: PatternDocument,
    ) -> tuple[dict, str]:
        if project is None:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "project_required",
                        diagnostic_path,
                        "a ProjectContext is required to resolve curve bindings",
                    ),
                )
            )
        try:
            reference = ResourceReference.parse(binding.value)
        except ResourceDocumentError as exc:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "invalid_resource_reference",
                        diagnostic_path,
                        str(exc),
                    ),
                )
            ) from exc
        try:
            path = reference.resolve(project, must_exist=True)
        except ResourceDocumentError as exc:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "missing_resource",
                        diagnostic_path,
                        str(exc),
                    ),
                )
            ) from exc
        try:
            source_bytes = path.read_bytes()
            payload = json.loads(source_bytes.decode("utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "invalid_curve_resource",
                        diagnostic_path,
                        f"cannot read curve resource: {exc}",
                    ),
                )
            ) from exc
        from src.pattern.curves import CurveDocument, CurveDocumentError

        try:
            curve = CurveDocument.from_dict(payload)
        except CurveDocumentError as exc:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "invalid_curve_resource",
                        diagnostic_path,
                        exc.message,
                    ),
                )
            ) from exc
        dependency_hash = hashlib.sha256(source_bytes).hexdigest()
        token = f"{reference.uri}:{dependency_hash}"
        return (
            {
                "frames": tuple(item.frame for item in curve.keyframes),
                "values": tuple(item.value for item in curve.keyframes),
                "interpolation": curve.interpolation,
                "default": curve.default,
            },
            token,
        )

    def _compile_script(
        self,
        document: PatternDocument,
        project: ProjectContext | None,
    ) -> tuple[ScriptProgramData | None, str]:
        script: ScriptBehavior | None = document.script
        if script is None:
            return None, ""
        if project is None:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "project_required",
                        "script.resource_uri",
                        "a ProjectContext is required to resolve ScriptBehavior",
                    ),
                )
            )
        try:
            reference = ResourceReference.parse(script.resource_uri)
        except ResourceDocumentError as exc:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "invalid_resource_reference",
                        "script.resource_uri",
                        str(exc),
                    ),
                )
            ) from exc
        try:
            path = reference.resolve(project, must_exist=True)
        except ResourceDocumentError as exc:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "missing_script_resource",
                        "script.resource_uri",
                        str(exc),
                    ),
                )
            ) from exc
        try:
            source_text = path.read_text(encoding="utf-8")
            ast.parse(source_text, filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "script_import_error",
                        "script.resource_uri",
                        f"cannot import script: {exc}",
                    ),
                )
            ) from exc
        try:
            import importlib.util

            module_name = f"pystg_compile_script_{hash(str(path)) & 0xFFFFFFFF:x}"
            spec = importlib.util.spec_from_file_location(module_name, str(path))
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot create loader for {path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "script_import_error",
                        "script.resource_uri",
                        f"cannot import script: {exc}",
                    ),
                )
            ) from exc
        dependency_hash = hashlib.sha256(
            source_text.encode("utf-8")
        ).hexdigest()
        token = f"{reference.uri}:{dependency_hash}"
        return (
            ScriptProgramData(
                resource_uri=script.resource_uri,
                script_path=str(path),
            ),
            token,
        )

    def _resolve_sprite(
        self,
        document: PatternDocument,
        project: ProjectContext | None,
    ) -> tuple[str, str]:
        resource = document.bullet.resource
        if resource is not None:
            try:
                reference = ResourceReference.parse(resource)
            except ResourceDocumentError as exc:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "invalid_resource_reference",
                            "bullet.resource",
                            str(exc),
                        ),
                    )
                ) from exc
            if project is None:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "project_required",
                            "bullet.resource",
                            "a ProjectContext is required to resolve this resource",
                        ),
                    )
                )
            try:
                path = reference.resolve(project, must_exist=True)
            except ResourceDocumentError as exc:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "missing_resource",
                            "bullet.resource",
                            str(exc),
                        ),
                    )
                ) from exc
            if reference.subresource is None:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "missing_sprite_fragment",
                            "bullet.resource",
                            "a sprite resource must include a #fragment",
                        ),
                    )
                )
            try:
                source_bytes = path.read_bytes()
                payload = json.loads(source_bytes.decode("utf-8-sig"))
            except (OSError, UnicodeError, ValueError) as exc:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "invalid_sprite_resource",
                            "bullet.resource",
                            f"cannot read sprite resource: {exc}",
                        ),
                    )
                ) from exc
            sprites = payload.get("sprites") if isinstance(payload, dict) else None
            if not isinstance(sprites, dict) or reference.subresource not in sprites:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "missing_sprite_subresource",
                            "bullet.resource",
                            f"sprite fragment {reference.subresource!r} was not found",
                        ),
                    )
                )
            dependency_hash = hashlib.sha256(source_bytes).hexdigest()
            return reference.subresource, f"{reference.uri}:{dependency_hash}"

        if project is None:
            return "", "alias:runtime"
        aliases = project.root / "assets" / "bullet_aliases.json"
        try:
            source_bytes = aliases.read_bytes()
            payload = json.loads(source_bytes.decode("utf-8-sig"))
            mapping = payload["mapping"]
            if not isinstance(mapping, dict):
                raise TypeError("mapping must be an object")
            type_mapping = mapping[document.bullet.bullet_type]
            if not isinstance(type_mapping, dict):
                raise TypeError("bullet type mapping must be an object")
            sprite_id = type_mapping[document.bullet.color]
            if not isinstance(sprite_id, str) or not sprite_id.strip():
                raise TypeError("sprite id must be a non-empty string")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "unknown_bullet_alias",
                        "bullet",
                        "cannot resolve "
                        f"{document.bullet.bullet_type}/{document.bullet.color}: {exc}",
                    ),
                )
            ) from exc
        dependency_hash = hashlib.sha256(source_bytes).hexdigest()
        return sprite_id, f"aliases:{dependency_hash}"


_DEFAULT_COMPILER = PatternCompiler()


def compile_pattern(
    document: PatternDocument,
    *,
    project: ProjectContext | None = None,
    sprite_index_resolver: SpriteIndexResolver | None = None,
) -> PatternProgram:
    return _DEFAULT_COMPILER.compile(
        document,
        project=project,
        sprite_index_resolver=sprite_index_resolver,
    )

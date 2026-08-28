"""Deterministic translation from the declarative model to existing Runtime classes."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.authoring.program import (
    AuthoringProgram,
    Diagnostic,
    Expr,
    LogicalUnit,
    Node,
    Ref,
    RelatedLocation,
    SourceSpan,
)
from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.authoring.templates import (
    TemplateExpansionError,
    TemplateRegistry,
    TemplateResolutionError,
    expand_nodes,
    is_template,
)
from src.core.project_context import ProjectContext, ProjectContextError

from .diagnostics import CompilerError


GENERATOR_VERSION = "pystg-codegen-v2-cd3"
_SUBPACKAGES = ("waves", "enemies", "bosses", "spells", "tasks", "functions")


@dataclass(frozen=True)
class SourceMapEntry:
    uid: str
    author_file: str
    author_span: tuple[int, int, int, int] | None
    generated_file: str
    generated_line_start: int
    generated_line_end: int

    def to_data(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "author_file": self.author_file,
            "author_span": list(self.author_span) if self.author_span else None,
            "generated_file": self.generated_file,
            "generated_line_start": self.generated_line_start,
            "generated_line_end": self.generated_line_end,
        }


@dataclass(frozen=True)
class CodeGeneratorResult:
    modules: dict[str, str]
    source_map: list[dict[str, Any]]
    manifest: dict[str, Any]
    build_hash: str


class _Writer:
    def __init__(self, relative_path: str, author_file: str) -> None:
        self.relative_path = relative_path
        self.author_file = author_file
        self.lines: list[str] = []
        self.entries: list[SourceMapEntry] = []

    def line(self, indent: int = 0, text: str = "") -> None:
        self.lines.append("    " * indent + text)

    def record(self, node: Node, callback) -> None:
        start = len(self.lines) + 1
        callback()
        end = max(start, len(self.lines))
        self.entries.append(
            SourceMapEntry(
                uid=node.uid,
                author_file=self.author_file,
                author_span=_span_tuple(node.source_span),
                generated_file=self.relative_path,
                generated_line_start=start,
                generated_line_end=end,
            )
        )

    def finish(self) -> str:
        return "\n".join(self.lines).rstrip() + "\n"


class CodeGenerator:
    """Generate one isolated Runtime package per Project Stage closure."""

    def __init__(
        self,
        program: AuthoringProgram,
        *,
        project_id: str | None = None,
        source_root: str | Path | None = None,
        template_registry: TemplateRegistry | None = None,
    ) -> None:
        self.program = program
        errors = tuple(item for item in program.validate() if item.severity == "error")
        if errors:
            code = errors[0].code if all(item.code == errors[0].code for item in errors) else "invalid_program"
            raise CompilerError(
                code,
                "cannot compile an invalid authoring program",
                errors,
            )
        projects = [unit for unit in program.logical_units() if unit.kind == "Project"]
        if len(projects) != 1:
            raise CompilerError(
                "invalid_project",
                "a generated package requires exactly one Project logical unit",
            )
        self.project = projects[0]
        if project_id is not None and project_id != self.project.id:
            raise CompilerError(
                "project_id_mismatch",
                f"requested project id {project_id!r} does not match Project {self.project.id!r}",
            )
        self.project_id = self.project.id
        self.source_root = Path(source_root).resolve() if source_root is not None else None
        self.template_registry = template_registry or TemplateRegistry.with_builtins()
        self._helper_index = 0
        self._register_template_targets()
        self._expanded_bodies = self._expand_and_validate_templates()
        self._validate_runtime_reference_boundaries()

    def generate(self) -> CodeGeneratorResult:
        self._helper_index = 0
        modules: dict[str, str] = {
            "__init__.py": '"""Generated PySTG content package; do not edit."""\n',
            "stages/__init__.py": '"""Generated Stage packages."""\n',
        }
        source_entries: list[SourceMapEntry] = []
        stage_info: list[tuple[str, str]] = []

        stage_refs = self.project.metadata["stages"]
        stage_units = [self.program.get_unit(ref.id) for ref in stage_refs]
        start_stage_id = self.project.metadata["start_stage"].id
        for stage in stage_units:
            stage_package = f"stages/{stage.id}"
            modules[f"{stage_package}/__init__.py"] = (
                f'"""Generated package for Stage {stage.id}."""\n'
            )
            modules[f"{stage_package}/_support.py"] = _runtime_support_source()
            for subpackage in _SUBPACKAGES:
                modules[f"{stage_package}/{subpackage}/__init__.py"] = (
                    f'"""Generated {subpackage} for Stage {stage.id}."""\n'
                )

            closure = self._stage_closure(stage)
            for unit in closure:
                relative_path, code, entries = self._generate_unit(unit, stage_package)
                self._validate_generated_module(unit, relative_path, code, entries)
                modules[relative_path] = code
                source_entries.extend(entries)
            stage_info.append((stage.id, f"Stage_{stage.id}"))

        modules["entry.py"] = self._entry_source(stage_info, start_stage_id)
        build_hash = self._build_hash(modules)
        manifest = {
            "project_id": self.project_id,
            "build_hash": build_hash,
            "entry_module": f"game_content.generated.{self.project_id}.entry",
            "stages": [stage_id for stage_id, _ in stage_info],
        }
        source_map = [
            item.to_data()
            for item in sorted(
                source_entries,
                key=lambda value: (
                    value.uid,
                    value.generated_file,
                    value.generated_line_start,
                ),
            )
        ]
        return CodeGeneratorResult(
            modules={path: modules[path] for path in sorted(modules)},
            source_map=source_map,
            manifest=manifest,
            build_hash=build_hash,
        )

    def validate_resources(self, project_root: str | Path) -> None:
        """Reject missing expanded ``res://`` references before filesystem output."""
        project = ProjectContext(Path(project_root))
        diagnostics: list[Diagnostic] = []
        seen: set[tuple[str, str, str | None]] = set()

        for unit in self.program.logical_units():
            for uri in _resource_values(unit.metadata):
                key = (unit.id, uri, None)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    ResourceReference.parse(uri).resolve(project, must_exist=True)
                except (ResourceDocumentError, ProjectContextError) as exc:
                    diagnostics.append(
                        Diagnostic(
                            code="resource_not_found",
                            message=str(exc),
                            source_path=self._author_file(unit),
                            unit_id=unit.id,
                        )
                    )

            for parameter in unit.parameters:
                if not parameter.has_default:
                    continue
                for uri in _resource_values(parameter.default):
                    key = (unit.id, uri, None)
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        ResourceReference.parse(uri).resolve(project, must_exist=True)
                    except (ResourceDocumentError, ProjectContextError) as exc:
                        diagnostics.append(
                            Diagnostic(
                                code="resource_not_found",
                                message=str(exc),
                                source_path=self._author_file(unit),
                                unit_id=unit.id,
                            )
                        )

            nodes = (*_walk_nodes(unit.body), *_walk_nodes(self._expanded_bodies[unit.id]))
            for node in nodes:
                values = (node.arguments, node.positional_arguments)
                for uri in _resource_values(values):
                    uid = _source_uid(node.uid)
                    key = (unit.id, uri, uid)
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        ResourceReference.parse(uri).resolve(project, must_exist=True)
                    except (ResourceDocumentError, ProjectContextError) as exc:
                        diagnostics.append(
                            Diagnostic(
                                code="resource_not_found",
                                message=str(exc),
                                source_path=self._author_file(unit),
                                span=node.source_span,
                                unit_id=unit.id,
                                uid=uid,
                                related=self._template_related(uid),
                            )
                        )

        if diagnostics:
            raise CompilerError(
                "resource_not_found",
                "authoring resources must exist inside the active project",
                tuple(diagnostics),
            )

    def _validate_runtime_reference_boundaries(self) -> None:
        diagnostics: list[Diagnostic] = []
        seen: set[tuple[str, str | None, str]] = set()

        def add_diagnostic(unit: LogicalUnit, target_kind: str, node: Node | None = None) -> None:
            uid = _source_uid(node.uid) if node is not None else None
            key = (unit.id, uid, target_kind)
            if key in seen:
                return
            seen.add(key)
            code = f"{target_kind.lower()}_reference_context"
            if target_kind == "Stage":
                message = "Stage references are only valid in Project.stages and Project.start_stage"
            else:
                message = "Project references cannot be embedded in generated Runtime unit values"
            diagnostics.append(
                Diagnostic(
                    code=code,
                    message=message,
                    source_path=self._author_file(unit),
                    span=node.source_span if node is not None else None,
                    unit_id=unit.id,
                    uid=uid,
                    related=self._template_related(uid),
                )
            )

        for unit in self.program.logical_units():
            if unit.kind == "Project":
                continue

            defaults = tuple(
                parameter.default
                for parameter in unit.parameters
                if parameter.has_default
            )
            for value in (*unit.metadata.values(), *defaults):
                for reference in _references(value):
                    target_kind = self.program.get_unit(reference.id).kind
                    if target_kind in {"Project", "Stage"}:
                        add_diagnostic(unit, target_kind)

            nodes = (*_walk_nodes(unit.body), *_walk_nodes(self._expanded_bodies[unit.id]))
            for node in nodes:
                values = (*node.arguments.values(), *node.positional_arguments)
                for value in values:
                    for reference in _references(value):
                        target_kind = self.program.get_unit(reference.id).kind
                        if target_kind in {"Project", "Stage"}:
                            add_diagnostic(unit, target_kind, node)

        if diagnostics:
            codes = {diagnostic.code for diagnostic in diagnostics}
            code = next(iter(codes)) if len(codes) == 1 else "non_runtime_reference_context"
            raise CompilerError(
                code,
                "Project and Stage logical units cannot be embedded in generated Runtime values",
                tuple(diagnostics),
            )

    def _register_template_targets(self) -> None:
        loaded: set[str] = set()
        for unit in self.program.logical_units():
            for node in unit.walk_nodes():
                if node.kind != "TemplateCall" or node.template is None:
                    continue
                target = node.template
                try:
                    definition = self.template_registry.resolve(target.identity)
                except TemplateResolutionError:
                    if not target.module:
                        self._raise_template_load(unit, node, "template has no module")
                    try:
                        module = importlib.import_module(target.module)
                        value: Any = module
                        for part in target.symbol.split("."):
                            value = getattr(value, part)
                        if not is_template(value):
                            raise TypeError("resolved symbol is not decorated with @template")
                        definition = self.template_registry.register(value)
                        self.template_registry.register_alias(target.identity, definition.identity)
                    except Exception as exc:
                        self._raise_template_load(
                            unit,
                            node,
                            f"{type(exc).__name__}: {exc}",
                        )

                module_name = target.module or definition.function.__module__
                if module_name in loaded:
                    continue
                loaded.add(module_name)
                try:
                    module = importlib.import_module(module_name)
                    for name in sorted(vars(module)):
                        value = getattr(module, name)
                        if is_template(value):
                            self.template_registry.register(value)
                except Exception as exc:
                    self._raise_template_load(
                        unit,
                        node,
                        f"{type(exc).__name__}: {exc}",
                    )

    def _raise_template_load(self, unit: LogicalUnit, node: Node, message: str) -> None:
        target = node.template
        related = ()
        if target is not None and target.definition_path:
            related = (
                RelatedLocation(
                    target.definition_path,
                    target.definition_span,
                    "template definition",
                ),
            )
        diagnostic = Diagnostic(
            code="template_missing",
            message=f"cannot load template {target.identity if target else ''!r}: {message}",
            source_path=self._author_file(unit),
            span=node.source_span,
            unit_id=unit.id,
            uid=node.uid,
            related=related,
        )
        raise CompilerError("template_missing", diagnostic.message, (diagnostic,))

    def _expand_and_validate_templates(self) -> dict[str, list[Node]]:
        expanded: dict[str, list[Node]] = {}
        cloned_units: list[LogicalUnit] = []
        try:
            for unit in self.program.logical_units():
                body = expand_nodes(unit.body, self.template_registry)
                expanded[unit.id] = body
                clone = copy.deepcopy(unit)
                clone.body = copy.deepcopy(body)
                cloned_units.append(clone)
        except TemplateExpansionError as exc:
            unit = self._unit_for_uid(exc.call_uid)
            diagnostic = Diagnostic(
                code=exc.code,
                message=exc.message,
                source_path=self._author_file(unit) if unit else "",
                unit_id=unit.id if unit else None,
                uid=exc.call_uid,
                related=exc.related,
            )
            raise CompilerError(exc.code, exc.message, (diagnostic,)) from exc

        expanded_program = AuthoringProgram.from_units(cloned_units)
        template_related = self._template_definition_locations()
        errors = tuple(
            _map_expanded_diagnostic(item, template_related)
            for item in expanded_program.validate()
            if item.severity == "error"
        )
        if errors:
            raise CompilerError(
                "template_result",
                "expanded templates are invalid in their call context",
                errors,
            )
        return expanded

    def _template_definition_locations(self) -> dict[str, tuple[RelatedLocation, ...]]:
        locations: dict[str, tuple[RelatedLocation, ...]] = {}
        for unit in self.program.logical_units():
            for node in unit.walk_nodes():
                if node.kind != "TemplateCall" or node.template is None:
                    continue
                try:
                    definition = self.template_registry.resolve(node.template.identity)
                except TemplateResolutionError:
                    continue
                path = definition.source_path or node.template.definition_path or ""
                span = definition.span or node.template.definition_span
                if path:
                    locations[node.uid] = (
                        RelatedLocation(path, span, "template definition"),
                    )
        return locations

    def _template_related(self, uid: str | None) -> tuple[RelatedLocation, ...]:
        if not uid:
            return ()
        return self._template_definition_locations().get(_source_uid(uid), ())

    def _unit_for_uid(self, uid: str) -> LogicalUnit | None:
        for unit in self.program.logical_units():
            if any(node.uid == uid for node in unit.walk_nodes()):
                return unit
        return None

    def _stage_closure(self, stage: LogicalUnit) -> list[LogicalUnit]:
        visited: set[str] = set()

        def visit(unit: LogicalUnit) -> None:
            if unit.id in visited:
                return
            visited.add(unit.id)
            for value in self._values_for_unit(unit):
                for reference in _references(value):
                    visit(self.program.get_unit(reference.id))

        visit(stage)
        order = {kind: index for index, kind in enumerate(
            ("Stage", "Wave", "Enemy", "Boss", "NonSpell", "Spell", "Task", "Function")
        )}
        return sorted(
            (self.program.get_unit(unit_id) for unit_id in visited),
            key=lambda unit: (order[unit.kind], unit.id),
        )

    def _generate_unit(
        self,
        unit: LogicalUnit,
        stage_package: str,
    ) -> tuple[str, str, list[SourceMapEntry]]:
        if unit.kind == "Stage":
            return self._generate_executable_class(
                unit, stage_package, "stage.py", "StageScript", "src.game.stage.stage_base"
            )
        if unit.kind == "Wave":
            return self._generate_executable_class(
                unit, stage_package, f"waves/{unit.id}.py", "Wave", "src.game.stage.wave_base"
            )
        if unit.kind == "Enemy":
            return self._generate_executable_class(
                unit,
                stage_package,
                f"enemies/{unit.id}.py",
                "EnemyScript",
                "src.game.stage.enemy_script",
            )
        if unit.kind in {"Spell", "NonSpell"}:
            base = "SpellCard" if unit.kind == "Spell" else "NonSpell"
            return self._generate_executable_class(
                unit,
                stage_package,
                f"spells/{unit.id}.py",
                base,
                "src.game.stage.spellcard",
            )
        if unit.kind == "Boss":
            return self._generate_boss(unit, stage_package)
        if unit.kind in {"Task", "Function"}:
            return self._generate_function(unit, stage_package)
        raise CompilerError("unsupported_unit", f"cannot generate unit kind {unit.kind!r}")

    def _validate_generated_module(
        self,
        unit: LogicalUnit,
        relative_path: str,
        source: str,
        entries: Sequence[SourceMapEntry],
    ) -> None:
        try:
            compile(source, relative_path, "exec")
        except SyntaxError as exc:
            line = exc.lineno or 0
            matches = [
                entry
                for entry in entries
                if entry.generated_line_start <= line <= entry.generated_line_end
            ]
            entry = min(
                matches,
                key=lambda item: item.generated_line_end - item.generated_line_start,
                default=None,
            )
            uid = _source_uid(entry.uid) if entry is not None else None
            node = next(
                (candidate for candidate in unit.walk_nodes() if candidate.uid == uid),
                None,
            )
            # Template calls are aggregate source-map entries.  Any contextual
            # syntax failure inside a validated expansion can only come from a
            # RawPython payload, so keep the error on the retained call node.
            is_raw_python = node is not None and node.kind in {"RawPython", "TemplateCall"}
            code = "raw_python_syntax" if is_raw_python else "generated_compile_failed"
            message = f"generated Python syntax error: {exc.msg}"
            diagnostic = Diagnostic(
                code=code,
                message=message,
                source_path=self._author_file(unit),
                span=node.source_span if node is not None else None,
                unit_id=unit.id,
                uid=uid,
                related=self._template_related(uid),
            )
            raise CompilerError(code, message, (diagnostic,)) from exc

    def _generate_executable_class(
        self,
        unit: LogicalUnit,
        stage_package: str,
        local_path: str,
        base_class: str,
        base_module: str,
    ) -> tuple[str, str, list[SourceMapEntry]]:
        relative_path = f"{stage_package}/{local_path}"
        writer = _Writer(relative_path, self._author_file(unit))
        writer.line(text='"""Generated from declarative PySTG authoring source."""')
        writer.line()
        writer.line(text="from __future__ import annotations")
        writer.line()
        writer.line(text=f"from {base_module} import {base_class}")
        support_prefix = "." if "/" not in local_path else ".."
        writer.line(
            text=f"from {support_prefix}_support import ("
        )
        for name in (
            "_pystg_actor",
            "_pystg_await",
            "_pystg_bind_enemy_resources",
            "_pystg_bind_stage_resources",
            "_pystg_boss_resource",
            "_pystg_clear_lasers",
            "_pystg_close_tasks",
            "_pystg_create_bent_laser",
            "_pystg_create_laser",
            "_pystg_dialogue",
            "_pystg_fire_arc",
            "_pystg_fire_circle",
            "_pystg_parallel",
            "_pystg_play_bgm",
            "_pystg_play_se",
            "_pystg_remove_laser",
            "_pystg_runtime_error",
            "_pystg_set_background",
            "_pystg_set_position",
            "_pystg_spawn",
        ):
            writer.line(1, f"{name},")
        writer.line(text=")")
        imports, symbols = self._reference_imports(unit, local_path)
        for statement in imports:
            writer.line(text=statement)
        writer.line()

        class_name = _unit_symbol(unit)
        writer.line(text=f"class {class_name}({base_class}):")
        writer.line(1, f"id = {unit.id!r}")
        writer.line(1, f"name = {unit.name!r}")
        for name, value in self._class_metadata(unit):
            writer.line(1, f"{name} = {self._format_value(value, symbols)}")
        if unit.kind == "Stage":
            writer.line()
            writer.line(1, "def bind(self, ctx):")
            writer.line(2, "super().bind(ctx)")
            writer.line(2, "_pystg_bind_stage_resources(self)")
            writer.line()
            writer.line(1, "def _play_bgm(self, bgm_name):")
            writer.line(2, "return _pystg_play_bgm(self, bgm_name)")
        elif unit.kind == "Enemy":
            writer.line()
            writer.line(1, "def bind(self, ctx, x=0, y=0):")
            writer.line(2, "super().bind(ctx, x=x, y=y)")
            writer.line(2, "_pystg_bind_enemy_resources(self)")
        writer.line()
        writer.line(1, "async def run(self):")
        writer.line(2, "try:")
        body = unit.body
        if body:
            self._render_nodes(writer, body, 3, unit, symbols, "self", record=True)
        else:
            writer.line(3, "pass")
        writer.line(2, "finally:")
        writer.line(3, "_pystg_close_tasks(self)")
        return relative_path, writer.finish(), writer.entries

    def _generate_function(
        self,
        unit: LogicalUnit,
        stage_package: str,
    ) -> tuple[str, str, list[SourceMapEntry]]:
        folder = "tasks" if unit.kind == "Task" else "functions"
        relative_path = f"{stage_package}/{folder}/{unit.id}.py"
        writer = _Writer(relative_path, self._author_file(unit))
        writer.line(text='"""Generated callable authoring unit."""')
        writer.line()
        writer.line(text="from __future__ import annotations")
        writer.line()
        writer.line(text="from .._support import (")
        for name in (
            "_pystg_actor",
            "_pystg_await",
            "_pystg_boss_resource",
            "_pystg_clear_lasers",
            "_pystg_create_bent_laser",
            "_pystg_create_laser",
            "_pystg_dialogue",
            "_pystg_fire_arc",
            "_pystg_fire_circle",
            "_pystg_parallel",
            "_pystg_play_bgm",
            "_pystg_play_se",
            "_pystg_remove_laser",
            "_pystg_runtime_error",
            "_pystg_set_background",
            "_pystg_set_position",
            "_pystg_spawn",
        ):
            writer.line(1, f"{name},")
        writer.line(text=")")
        imports, symbols = self._reference_imports(unit, f"{folder}/{unit.id}.py")
        for statement in imports:
            writer.line(text=statement)
        writer.line()
        parameters = ["_ctx"]
        for parameter in unit.parameters:
            rendered = parameter.name
            if parameter.has_default:
                rendered += f"={self._format_value(parameter.default, symbols)}"
            parameters.append(rendered)
        writer.line(text=f"async def {_unit_symbol(unit)}({', '.join(parameters)}):")
        if unit.body:
            self._render_nodes(writer, unit.body, 1, unit, symbols, "_ctx", record=True)
        else:
            writer.line(1, "pass")
        return relative_path, writer.finish(), writer.entries

    def _generate_boss(
        self,
        unit: LogicalUnit,
        stage_package: str,
    ) -> tuple[str, str, list[SourceMapEntry]]:
        relative_path = f"{stage_package}/bosses/{unit.id}.py"
        writer = _Writer(relative_path, self._author_file(unit))
        writer.line(text='"""Generated BossDef."""')
        writer.line()
        writer.line(text="from src.game.stage.boss_base import nonspell, spellcard")
        writer.line(text="from src.game.stage.stage_base import BossDef")
        imports, symbols = self._reference_imports(unit, f"bosses/{unit.id}.py")
        for statement in imports:
            writer.line(text=statement)
        writer.line()
        writer.line(text=f"{_unit_symbol(unit)} = BossDef(")
        writer.line(1, f"id={unit.id!r},")
        writer.line(1, f"name={unit.name!r},")
        writer.line(1, f"texture={unit.metadata['texture']!r},")
        writer.line(1, "phases=[")
        for phase_ref in unit.metadata["phases"]:
            phase = self.program.get_unit(phase_ref.id)
            symbol = symbols[phase.id]
            if phase.kind == "NonSpell":
                writer.line(
                    2,
                    "nonspell("
                    f"{symbol}, hp={phase.metadata.get('hp', 1500)!r}, "
                    f"time={phase.metadata.get('time_limit', 60.0)!r}, "
                    f"bonus={phase.metadata.get('bonus', 100_000)!r}),",
                )
            else:
                writer.line(
                    2,
                    "spellcard("
                    f"{symbol}, name={phase.name!r}, "
                    f"hp={phase.metadata.get('hp', 1500)!r}, "
                    f"time={phase.metadata.get('time_limit', 60.0)!r}, "
                    f"bonus={phase.metadata.get('bonus', 1_000_000)!r}, "
                    f"practice={phase.metadata.get('practice_unlock', True)!r}),",
                )
        writer.line(1, "],")
        writer.line(1, f"animations={self._format_value(unit.metadata.get('animations', {}), symbols)},")
        writer.line(text=")")
        return relative_path, writer.finish(), writer.entries

    def _render_nodes(
        self,
        writer: _Writer,
        nodes: Sequence[Node],
        indent: int,
        unit: LogicalUnit,
        symbols: Mapping[str, str],
        context: str,
        *,
        record: bool,
    ) -> None:
        for node in nodes:
            if node.kind == "TemplateCall":
                def render_template() -> None:
                    before = len(writer.lines)
                    try:
                        expanded = expand_nodes([node], self.template_registry)
                    except TemplateExpansionError as exc:
                        raise self._template_error(unit, exc) from exc
                    self._render_nodes(
                        writer,
                        expanded,
                        indent,
                        unit,
                        symbols,
                        context,
                        record=False,
                    )
                    if len(writer.lines) == before:
                        writer.line(indent, "pass")
                if record:
                    writer.record(node, render_template)
                else:
                    render_template()
                continue

            callback = lambda node=node: self._render_node(
                writer, node, indent, unit, symbols, context, record=record
            )
            if record and node.kind != "Branch":
                writer.record(node, callback)
            else:
                callback()

    def _render_node(
        self,
        writer: _Writer,
        node: Node,
        indent: int,
        unit: LogicalUnit,
        symbols: Mapping[str, str],
        context: str,
        *,
        record: bool,
    ) -> None:
        kind = node.kind
        args = node.arguments
        value = lambda name, default=None: self._format_value(args.get(name, default), symbols)

        if kind == "Wait":
            writer.line(indent, f"await _pystg_await({context}, {context}.wait({value('frames')}))")
            return
        if kind == "At":
            frame = value("frame")
            writer.line(
                indent,
                f"await _pystg_await({context}, {context}.wait(max(0, int({frame}) - {context}.time)))",
            )
            self._render_nodes(writer, node.children["body"], indent, unit, symbols, context, record=record)
            return
        if kind in {"Repeat", "While", "ForEach"}:
            if kind == "Repeat":
                header = f"for _pystg_repeat in range({value('count')}):"
            elif kind == "While":
                header = f"while {value('condition')}:"
            else:
                header = f"for {args['target']} in {value('iterable')}:"
            writer.line(indent, header)
            children = node.children["body"]
            if children:
                self._render_nodes(writer, children, indent + 1, unit, symbols, context, record=record)
            else:
                writer.line(indent + 1, "pass")
            return
        if kind == "If":
            writer.line(indent, f"if {value('condition')}:")
            body = node.children["body"]
            if body:
                self._render_nodes(writer, body, indent + 1, unit, symbols, context, record=record)
            else:
                writer.line(indent + 1, "pass")
            else_body = node.children["else_body"]
            if else_body:
                writer.line(indent, "else:")
                self._render_nodes(writer, else_body, indent + 1, unit, symbols, context, record=record)
            return
        if kind == "Else":
            self._render_nodes(writer, node.children["body"], indent, unit, symbols, context, record=record)
            return
        if kind == "Parallel":
            helpers: list[str] = []
            for branch in node.children["branches"]:
                helper = self._next_helper("branch")
                helpers.append(helper)
                writer.line(indent, f"async def {helper}():")
                body = branch.children["body"]
                if body:
                    self._render_nodes(writer, body, indent + 1, unit, symbols, context, record=record)
                else:
                    writer.line(indent + 1, "pass")
            calls = ", ".join(f"{name}()" for name in helpers)
            if args.get("wait", True):
                writer.line(indent, f"await _pystg_parallel({context}, ({calls},))")
            else:
                for helper in helpers:
                    writer.line(indent, f"_pystg_spawn({context}, {helper}())")
            return
        if kind == "SpawnTask":
            if "task" in args:
                target = symbols[args["task"].id]
                arguments = args.get("arguments", {})
                call = self._call_text(target, (), arguments, symbols, first=context)
                writer.line(indent, f"_pystg_spawn({context}, {call})")
            else:
                helper = self._next_helper("spawn")
                writer.line(indent, f"async def {helper}():")
                body = node.children["body"]
                if body:
                    self._render_nodes(writer, body, indent + 1, unit, symbols, context, record=record)
                else:
                    writer.line(indent + 1, "pass")
                writer.line(indent, f"_pystg_spawn({context}, {helper}())")
            return
        if kind == "Break":
            writer.line(indent, "break")
            return
        if kind == "Continue":
            writer.line(indent, "continue")
            return
        if kind == "Return":
            suffix = f" {value('value')}" if "value" in args else ""
            writer.line(indent, f"return{suffix}")
            return
        if kind == "Set":
            writer.line(indent, f"{args['name']} = {value('value')}")
            return
        if kind == "Call":
            target = symbols[args["function"].id]
            call = self._call_text(
                target,
                args.get("arguments", ()),
                args.get("keywords", {}),
                symbols,
                first=context,
            )
            writer.line(indent, f"await _pystg_await({context}, {call})")
            return
        if kind == "RawPython":
            source = args["source"]
            self._validate_raw_python(source, unit, node)
            writer.line(indent, "try:")
            source_lines = source.splitlines() or ["pass"]
            for line in source_lines:
                writer.line(indent + 1, line)
            writer.line(indent, "except Exception as _pystg_exc:")
            writer.line(indent + 1, f"raise _pystg_runtime_error({node.uid!r}, _pystg_exc) from _pystg_exc")
            return

        if kind == "RunWave":
            target = symbols[args["wave_class"].id]
            writer.line(indent, f"await _pystg_await({context}, {context}.run_wave({target}))")
            return
        if kind == "RunBoss":
            target = symbols[args["boss_def"].id]
            middle = ", is_midboss=True" if args.get("is_midboss") else ""
            writer.line(indent, f"await _pystg_await({context}, {context}.run_boss(_pystg_boss_resource({target}){middle}))")
            return
        if kind == "SetBackground":
            writer.line(indent, f"_pystg_set_background({context}, {value('name')})")
            return
        if kind == "PlayBGM":
            writer.line(indent, f"_pystg_play_bgm({context}, {value('name')})")
            return
        if kind == "PlayDialogue":
            delay = value("initial_delay_frames", 0)
            writer.line(
                indent,
                f"await _pystg_await({context}, {context}.play_dialogue(_pystg_dialogue({value('dialogue_list')}), initial_delay_frames={delay}))",
            )
            return
        if kind == "SpawnEnemy":
            target = symbols[args["enemy_class"].id]
            writer.line(
                indent,
                f"{context}.spawn_enemy_class({target}, x={value('x', 0.0)}, y={value('y', 1.0)})",
            )
            return
        if kind == "MoveTo":
            writer.line(
                indent,
                f"await _pystg_await({context}, _pystg_actor({context}).move_to({value('x')}, {value('y')}, duration={value('duration', 60)}))",
            )
            return
        if kind == "MoveLinear":
            writer.line(
                indent,
                f"await _pystg_await({context}, _pystg_actor({context}).move_linear({value('dx')}, {value('dy')}, duration={value('duration', 60)}))",
            )
            return
        if kind == "SetPosition":
            writer.line(indent, f"_pystg_set_position({context}, {value('x')}, {value('y')})")
            return
        if kind in {"FireCircle", "FireArc"}:
            helper = "_pystg_fire_circle" if kind == "FireCircle" else "_pystg_fire_arc"
            writer.line(indent, f"{helper}({context}, {self._keyword_text(args, symbols)})")
            return
        if kind in {"Fire", "FireAtPlayer", "FirePolar", "FireOrbit"}:
            method = {
                "Fire": "fire",
                "FireCircle": "fire_circle",
                "FireArc": "fire_arc",
                "FireAtPlayer": "fire_at_player",
                "FirePolar": "fire_polar",
                "FireOrbit": "fire_orbit",
            }[kind]
            writer.line(indent, f"{context}.{method}({self._keyword_text(args, symbols)})")
            return
        if kind == "ClearBullets":
            writer.line(indent, f"{context}.clear_bullets(to_items={args.get('to_items', False)!r})")
            return
        if kind == "Kill":
            writer.line(indent, f"{context}.kill()")
            return
        if kind == "PlaySE":
            writer.line(indent, f"_pystg_play_se({context}, {self._keyword_text(args, symbols)})")
            return
        if kind == "CreateLaser":
            assign = args.get("assign")
            runtime_args = {key: item for key, item in args.items() if key != "assign"}
            prefix = f"{assign} = " if assign else ""
            writer.line(indent, f"{prefix}_pystg_create_laser({context}, {self._keyword_text(runtime_args, symbols)})")
            return
        if kind == "CreateBentLaser":
            assign = args.get("assign")
            runtime_args = {key: item for key, item in args.items() if key != "assign"}
            prefix = f"{assign} = " if assign else ""
            writer.line(indent, f"{prefix}_pystg_create_bent_laser({context}, {self._keyword_text(runtime_args, symbols)})")
            return
        if kind == "RemoveLaser":
            writer.line(
                indent,
                f"_pystg_remove_laser({context}, {value('laser')}, off_time={value('off_time', 0)})",
            )
            return
        if kind == "ClearLasers":
            writer.line(indent, f"_pystg_clear_lasers({context})")
            return
        if kind == "Branch":
            self._render_nodes(writer, node.children["body"], indent, unit, symbols, context, record=record)
            return
        raise CompilerError("unsupported_node", f"cannot generate node kind {kind!r}")

    def _reference_imports(
        self,
        unit: LogicalUnit,
        local_path: str,
    ) -> tuple[list[str], dict[str, str]]:
        refs = sorted({
            ref.id
            for value in self._values_for_unit(unit)
            for ref in _references(value)
        })
        symbols: dict[str, str] = {}
        prefix = "." if "/" not in local_path else ".."
        imports: list[str] = []
        for ref_id in refs:
            target = self.program.get_unit(ref_id)
            if target.kind == "Stage":
                continue
            folder = {
                "Wave": "waves",
                "Enemy": "enemies",
                "Boss": "bosses",
                "Spell": "spells",
                "NonSpell": "spells",
                "Task": "tasks",
                "Function": "functions",
            }[target.kind]
            symbol = _unit_symbol(target)
            imports.append(f"from {prefix}{folder}.{target.id} import {symbol}")
            symbols[target.id] = symbol
        return sorted(set(imports)), symbols

    def _values_for_unit(self, unit: LogicalUnit) -> list[Any]:
        values: list[Any] = list(unit.metadata.values())
        for parameter in unit.parameters:
            if parameter.has_default:
                values.append(parameter.default)
        values.extend(self._expanded_bodies.get(unit.id, unit.body))
        return values

    def _class_metadata(self, unit: LogicalUnit) -> list[tuple[str, Any]]:
        if unit.kind == "Stage":
            names = ("title", "subtitle", "bgm", "boss_bgm", "background")
        elif unit.kind == "Enemy":
            names = ("hp", "sprite", "score", "hitbox_radius", "drops", "clear_bullets_on_death")
        elif unit.kind in {"Spell", "NonSpell"}:
            names = ("hp", "time_limit", "bonus", "is_survival", "is_timeout", "practice_unlock")
        else:
            names = ()
        return [(name, unit.metadata[name]) for name in names if name in unit.metadata]

    def _format_value(self, value: Any, symbols: Mapping[str, str]) -> str:
        if isinstance(value, Expr):
            return value.source
        if isinstance(value, Ref):
            try:
                return symbols[value.id]
            except KeyError as exc:
                raise CompilerError("missing_symbol", f"no generated symbol for Ref({value.id!r})") from exc
        if isinstance(value, list):
            return "[" + ", ".join(self._format_value(item, symbols) for item in value) + "]"
        if isinstance(value, tuple):
            payload = ", ".join(self._format_value(item, symbols) for item in value)
            return f"({payload}{',' if len(value) == 1 else ''})"
        if isinstance(value, Mapping):
            return "{" + ", ".join(
                f"{key!r}: {self._format_value(value[key], symbols)}"
                for key in sorted(value)
            ) + "}"
        return repr(value)

    def _keyword_text(self, values: Mapping[str, Any], symbols: Mapping[str, str]) -> str:
        return ", ".join(
            f"{name}={self._format_value(values[name], symbols)}"
            for name in sorted(values)
        )

    def _call_text(
        self,
        name: str,
        positional: Sequence[Any],
        keywords: Mapping[str, Any],
        symbols: Mapping[str, str],
        *,
        first: str | None = None,
    ) -> str:
        parts = [first] if first is not None else []
        parts.extend(self._format_value(item, symbols) for item in positional)
        parts.extend(
            f"{key}={self._format_value(keywords[key], symbols)}"
            for key in sorted(keywords)
        )
        return f"{name}({', '.join(parts)})"

    def _validate_raw_python(self, source: str, unit: LogicalUnit, node: Node) -> None:
        payload = "async def __pystg_raw__():\n" + "\n".join(
            f"    {line}" for line in (source.splitlines() or ["pass"])
        )
        try:
            ast.parse(payload, filename=self._author_file(unit), mode="exec")
        except SyntaxError as exc:
            diagnostic = Diagnostic(
                code="raw_python_syntax",
                message=f"RawPython syntax error: {exc.msg}",
                source_path=self._author_file(unit),
                span=node.source_span,
                unit_id=unit.id,
                uid=node.uid,
            )
            raise CompilerError("raw_python_syntax", diagnostic.message, (diagnostic,)) from exc

    def _template_error(self, unit: LogicalUnit, exc: TemplateExpansionError) -> CompilerError:
        diagnostic = Diagnostic(
            code=exc.code,
            message=exc.message,
            source_path=self._author_file(unit),
            unit_id=unit.id,
            uid=exc.call_uid,
            related=exc.related,
        )
        return CompilerError(exc.code, exc.message, (diagnostic,))

    def _next_helper(self, prefix: str) -> str:
        self._helper_index += 1
        return f"_pystg_{prefix}_{self._helper_index}"

    def _author_file(self, unit: LogicalUnit | None) -> str:
        if unit is None or unit.source_path is None:
            return f"{unit.kind.lower()}s/{unit.id}.py" if unit else ""
        path = Path(unit.source_path)
        if self.source_root is not None:
            try:
                return path.resolve().relative_to(self.source_root).as_posix()
            except ValueError:
                pass
        parts = path.parts
        if "game_content" in parts:
            index = parts.index("game_content")
            return Path(*parts[index:]).as_posix()
        if not path.is_absolute():
            return path.as_posix()
        return f"{unit.kind.lower()}s/{unit.id}.py"

    def _entry_source(self, stages: Sequence[tuple[str, str]], start_stage_id: str) -> str:
        lines = [
            '"""Generated content entry; do not edit."""',
            "",
            "from __future__ import annotations",
            "",
            "from src.game.stage.stage_base import StageScript",
        ]
        for stage_id, class_name in stages:
            lines.append(f"from .stages.{stage_id}.stage import {class_name}")
        lines.append("")
        class_names = [class_name for _, class_name in stages]
        tuple_text = ", ".join(class_names) + ("," if len(class_names) == 1 else "")
        lines.append(f"STAGES: tuple[type[StageScript], ...] = ({tuple_text})")
        start_class = dict(stages)[start_stage_id]
        lines.append(f"START_STAGE: type[StageScript] = {start_class}")
        lines.append("STAGE_BY_ID: dict[str, type[StageScript]] = {")
        for stage_id, class_name in stages:
            lines.append(f"    {stage_id!r}: {class_name},")
        lines.extend(
            [
                "}",
                "",
                "def get_stage(stage_id: str | None = None) -> type[StageScript]:",
                "    if stage_id is None:",
                "        return START_STAGE",
                "    try:",
                "        return STAGE_BY_ID[stage_id]",
                "    except KeyError as exc:",
                "        raise KeyError(f'unknown stage id: {stage_id}') from exc",
                "",
                '__all__ = ["STAGES", "START_STAGE", "STAGE_BY_ID", "get_stage"]',
            ]
        )
        return "\n".join(lines) + "\n"

    def _build_hash(self, modules: Mapping[str, str]) -> str:
        hasher = hashlib.sha256()
        hasher.update(GENERATOR_VERSION.encode("utf-8"))
        hasher.update(b"\0")
        semantic = [
            unit.semantic_data()
            for unit in sorted(
                self.program.logical_units(),
                key=lambda item: (item.kind, item.id),
            )
        ]
        hasher.update(
            json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        hasher.update(b"\0")
        for identity, definition in sorted(self.template_registry._definitions.items()):
            hasher.update(identity.encode("utf-8"))
            hasher.update(b"\0")
            try:
                source = inspect.getsource(definition.function)
            except (OSError, TypeError):
                source = repr(definition.signature)
            hasher.update(source.replace("\r\n", "\n").encode("utf-8"))
            hasher.update(b"\0")
        for path in sorted(modules):
            hasher.update(path.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(modules[path].encode("utf-8"))
            hasher.update(b"\0")
        return hasher.hexdigest()


def _runtime_support_source() -> str:
    return '''"""Generated control-flow helpers using the existing frame coroutine protocol."""

from __future__ import annotations

import hashlib
import inspect
import json
import operator
from dataclasses import replace

from src.core.project_context import get_project_context


_PYSTG_SPRITE_RESOURCES = {}


def _pystg_resource_path(value):
    if not isinstance(value, str) or not value.startswith("res://"):
        return None
    path_text = value[6:].partition("#")[0]
    project = get_project_context()
    path = project.resolve(path_text)
    project.relative(path)
    if not path.is_file():
        raise FileNotFoundError(f"resource does not exist: {value}")
    return path


def _pystg_resource_key(kind, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"_pystg_{kind}_{digest}"


def _pystg_context(owner):
    context = getattr(owner, "ctx", None)
    if context is None:
        raise RuntimeError("authoring action requires a bound Runtime context")
    return context


def _pystg_bind_stage_resources(owner):
    background = getattr(owner, "background", "")
    if _pystg_resource_path(background) is not None:
        _pystg_set_background(owner, background)
        owner.background = ""


def _pystg_sprite_name(value):
    path = _pystg_resource_path(value)
    if path is None:
        return value
    cached = _PYSTG_SPRITE_RESOURCES.get(value)
    if cached is not None:
        return cached
    from src.resource.texture_asset import get_texture_asset_manager

    manager = get_texture_asset_manager()
    atlas_name = path.stem
    if manager.load_atlas_config(str(path), atlas_name=atlas_name) is None:
        raise RuntimeError(f"failed to load sprite resource: {value}")
    fragment = value.partition("#")[2]
    resolved = fragment or atlas_name
    _PYSTG_SPRITE_RESOURCES[value] = resolved
    return resolved


def _pystg_bind_enemy_resources(owner):
    owner.sprite = _pystg_sprite_name(getattr(owner, "sprite", ""))


def _pystg_boss_resource(boss_def):
    texture = _pystg_sprite_name(getattr(boss_def, "texture", ""))
    if texture == boss_def.texture:
        return boss_def
    return replace(boss_def, texture=texture)


def _pystg_play_bgm(owner, name):
    context = _pystg_context(owner)
    path = _pystg_resource_path(name)
    if path is not None:
        audio = getattr(context, "audio", None)
        bank = getattr(audio, "stage_bank", None) if audio is not None else None
        if bank is None:
            raise RuntimeError("res:// BGM requires the active StageAudioBank")
        key = _pystg_resource_key("bgm", name)
        if not bank.has_bgm(key) and not bank.load_bgm(key, str(path)):
            raise RuntimeError(f"failed to register BGM resource: {name}")
        if not context.play_bgm(key):
            raise RuntimeError(f"failed to play BGM resource: {name}")
        return True
    runtime_name = name.rsplit(".", 1)[0] if isinstance(name, str) and "." in name else name
    return bool(context.play_bgm(runtime_name))


def _pystg_set_background(owner, name):
    context = _pystg_context(owner)
    path = _pystg_resource_path(name)
    if path is None:
        return bool(context.set_background(name))
    renderer = getattr(context, "background_renderer", None)
    if renderer is None:
        return False
    if not renderer.load_from_json(str(path), asset_base=str(path.parent)):
        raise RuntimeError(f"failed to load background resource: {name}")
    return True


def _pystg_play_se(owner, name, volume=None, min_interval=0.0):
    context = _pystg_context(owner)
    path = _pystg_resource_path(name)
    runtime_name = name
    if path is not None:
        audio = getattr(context, "audio", None)
        bank = getattr(audio, "stage_bank", None) if audio is not None else None
        if bank is None:
            raise RuntimeError("res:// SE requires the active StageAudioBank")
        runtime_name = _pystg_resource_key("se", name)
        if not bank.has_se(runtime_name) and not bank.load_se(runtime_name, str(path)):
            raise RuntimeError(f"failed to load SE resource: {name}")
    return bool(context.play_se(runtime_name, volume, min_interval=min_interval))


def _pystg_dialogue(value):
    path = _pystg_resource_path(value)
    if path is None:
        return value
    with path.open("r", encoding="utf-8") as handle:
        dialogue = json.load(handle)
    if not isinstance(dialogue, list):
        raise ValueError(f"dialogue resource must contain a top-level list: {value}")
    return dialogue


def _pystg_fire_origin(owner, x, y):
    actor = _pystg_actor(owner)
    if x is None:
        x = getattr(actor, "x", None)
    if y is None:
        y = getattr(actor, "y", None)
    if x is None or y is None:
        raise RuntimeError("batch fire action requires an explicit or actor-derived x/y")
    return x, y


def _pystg_fire_batch(owner, angles, *, x=None, y=None, speed=2.0,
                      play_sound=True, **options):
    context = _pystg_context(owner)
    x, y = _pystg_fire_origin(owner, x, y)
    angles = list(angles)
    bullet_type = options.pop("bullet_type", "ball_m")
    color = options.pop("color", "red")
    options.pop("accel", None)
    options.pop("angle_accel", None)
    if "curve_params" in options:
        options["curve_param"] = options.pop("curve_params")
    if play_sound and hasattr(owner, "_play_danmaku_se"):
        owner._play_danmaku_se(count=len(angles), speed=speed, bullet_type=bullet_type)
    indices = context.create_bullets_batch(
        positions=[(x, y)] * len(angles),
        angles=angles,
        speeds=[speed] * len(angles),
        bullet_type=bullet_type,
        color=color,
        **options,
    )
    result = [int(index) for index in indices]
    bullets = getattr(owner, "_bullets", None)
    if bullets is not None:
        bullets.extend(result)
    return result


def _pystg_default(owner, method_name, parameter):
    return inspect.signature(getattr(owner, method_name)).parameters[parameter].default


def _pystg_fire_circle(owner, *, x=None, y=None, count=None, speed=2.0,
                       start_angle=0.0, play_sound=True, **options):
    if count is None:
        count = _pystg_default(owner, "fire_circle", "count")
    count = operator.index(count)
    if count < 1:
        raise ValueError("FireCircle.count must be at least 1")
    angles = (start_angle + (360.0 / count) * index for index in range(count))
    return _pystg_fire_batch(
        owner, angles, x=x, y=y, speed=speed, play_sound=play_sound, **options
    )


def _pystg_fire_arc(owner, *, x=None, y=None, count=5, speed=2.0,
                    center_angle=-90.0, arc_angle=60.0, play_sound=True, **options):
    count = operator.index(count)
    if count < 1:
        raise ValueError("FireArc.count must be at least 1")
    if count == 1:
        angles = [center_angle]
    else:
        start = center_angle - arc_angle / 2
        step = arc_angle / (count - 1)
        angles = (start + step * index for index in range(count))
    return _pystg_fire_batch(
        owner, angles, x=x, y=y, speed=speed, play_sound=play_sound, **options
    )


def _pystg_actor(owner):
    boss = getattr(owner, "boss", None)
    return boss if boss is not None else owner


def _pystg_set_position(owner, x, y):
    actor = _pystg_actor(owner)
    if hasattr(actor, "set_position"):
        actor.set_position(x, y)
    elif hasattr(actor, "move_to_instant"):
        actor.move_to_instant(x, y)
    else:
        actor.x, actor.y = x, y


def _pystg_spawn(owner, coroutine):
    tasks = getattr(owner, "_pystg_tasks", None)
    if tasks is None:
        tasks = []
        owner._pystg_tasks = tasks
    tasks.append(coroutine)


def _pystg_pump(owner):
    if getattr(owner, "_pystg_pumping", False):
        return
    tasks = list(getattr(owner, "_pystg_tasks", ()))
    owner._pystg_tasks = []
    pending = []
    owner._pystg_pumping = True
    try:
        for index, coroutine in enumerate(tasks):
            try:
                coroutine.send(None)
            except StopIteration:
                continue
            except Exception:
                for pending_coroutine in pending:
                    pending_coroutine.close()
                for remaining in tasks[index + 1:]:
                    remaining.close()
                for spawned in owner._pystg_tasks:
                    spawned.close()
                owner._pystg_tasks = []
                raise
            pending.append(coroutine)
    finally:
        owner._pystg_pumping = False
    owner._pystg_tasks = pending + list(owner._pystg_tasks)


async def _pystg_await(owner, awaitable):
    if getattr(owner, "_pystg_pumping", False) or getattr(owner, "_pystg_driving", False):
        return await awaitable
    iterator = awaitable.__await__() if hasattr(awaitable, "__await__") else iter(awaitable)
    completed = False
    try:
        while True:
            owner._pystg_driving = True
            try:
                iterator.send(None)
            except StopIteration as stop:
                completed = True
                return stop.value
            finally:
                owner._pystg_driving = False
            _pystg_pump(owner)
            await owner.wait(1)
    finally:
        if not completed:
            iterator.close()


async def _pystg_parallel(owner, coroutines):
    active = list(coroutines)
    nested = getattr(owner, "_pystg_pumping", False) or getattr(owner, "_pystg_driving", False)
    try:
        while active:
            pending = []
            previous = getattr(owner, "_pystg_pumping", False)
            owner._pystg_pumping = True
            try:
                for coroutine in active:
                    try:
                        coroutine.send(None)
                    except StopIteration:
                        continue
                    pending.append(coroutine)
            finally:
                owner._pystg_pumping = previous
            active = pending
            if not nested:
                _pystg_pump(owner)
            if active:
                await owner.wait(1)
    finally:
        for coroutine in active:
            coroutine.close()


def _pystg_close_tasks(owner):
    tasks = list(getattr(owner, "_pystg_tasks", ()))
    owner._pystg_tasks = []
    for coroutine in tasks:
        coroutine.close()


def _pystg_laser_context(owner):
    context = getattr(owner, "ctx", None)
    if context is None:
        raise RuntimeError("laser action requires a bound Runtime context")
    return context


def _pystg_create_laser(owner, **kwargs):
    return _pystg_laser_context(owner).create_laser(**kwargs)


def _pystg_create_bent_laser(owner, **kwargs):
    return _pystg_laser_context(owner).create_bent_laser(**kwargs)


def _pystg_remove_laser(owner, laser, off_time=0):
    return _pystg_laser_context(owner).remove_laser(laser, off_time=off_time)


def _pystg_clear_lasers(owner):
    return _pystg_laser_context(owner).clear_all_lasers()


def _pystg_runtime_error(uid, error):
    return RuntimeError(f"authoring node {uid}: {type(error).__name__}: {error}")
'''


def _unit_symbol(unit: LogicalUnit) -> str:
    return {
        "Stage": f"Stage_{unit.id}",
        "Wave": f"Wave_{unit.id}",
        "Enemy": f"Enemy_{unit.id}",
        "Boss": f"Boss_{unit.id}",
        "Spell": f"Spell_{unit.id}",
        "NonSpell": f"NonSpell_{unit.id}",
        "Task": f"task_{unit.id}",
        "Function": f"function_{unit.id}",
    }[unit.kind]


def _references(value: Any):
    if isinstance(value, Ref):
        yield value
    elif isinstance(value, Node):
        for item in value.arguments.values():
            yield from _references(item)
        for item in value.positional_arguments:
            yield from _references(item)
        for children in value.children.values():
            for child in children:
                yield from _references(child)
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _references(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _references(item)


def _resource_values(value: Any):
    if isinstance(value, Expr):
        return
    if isinstance(value, str):
        if value.startswith("res://"):
            yield value
        return
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _resource_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _resource_values(item)


def _walk_nodes(nodes: Sequence[Node]):
    for node in nodes:
        yield node
        for children in node.children.values():
            yield from _walk_nodes(children)


def _source_uid(uid: str) -> str:
    return uid.split("__expanded_", 1)[0]


def _span_tuple(span: SourceSpan | None) -> tuple[int, int, int, int] | None:
    if span is None:
        return None
    return (span.start_line, span.start_column, span.end_line, span.end_column)


def _map_expanded_diagnostic(
    diagnostic: Diagnostic,
    template_related: Mapping[str, tuple[RelatedLocation, ...]],
) -> Diagnostic:
    uid = diagnostic.uid
    if uid and "__expanded_" in uid:
        uid = uid.split("__expanded_", 1)[0]
    related = list(diagnostic.related)
    for location in template_related.get(uid or "", ()):
        if location not in related:
            related.append(location)
    return Diagnostic(
        code=diagnostic.code,
        message=diagnostic.message,
        severity=diagnostic.severity,
        source_path=diagnostic.source_path,
        span=diagnostic.span,
        unit_id=diagnostic.unit_id,
        uid=uid,
        related=tuple(related),
    )


__all__ = [
    "CodeGenerator",
    "CodeGeneratorResult",
    "GENERATOR_VERSION",
    "SourceMapEntry",
]

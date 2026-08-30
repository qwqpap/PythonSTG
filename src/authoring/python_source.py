"""Restricted Python source loading, stable formatting, and file conflicts."""

from __future__ import annotations

import ast
import hashlib
import importlib.machinery
import importlib.util
import inspect
import io
import os
import sys
import tempfile
import tokenize
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import dsl
from .program import (
    AuthoringProgram,
    Diagnostic,
    Expr,
    LogicalUnit,
    Node,
    NodeComments,
    Parameter,
    ProgramError,
    ProgramValidationError,
    Ref,
    SourceSpan,
    TemplateTarget,
    make_template_call,
)
from .templates import ImportSpec, TemplateSourceDefinition


_UID_NAMESPACE = uuid.UUID("d48d1453-1332-4b26-9e5f-b66574d21c51")


class SourceMode(str, Enum):
    SUPPORTED = "supported"
    READ_ONLY = "read_only"


class ExternalChange(str, Enum):
    UNCHANGED = "unchanged"
    RELOADED = "reloaded"
    CONFLICT = "conflict"


class SourceError(ProgramError):
    pass


class UnsupportedSourceError(SourceError):
    def __init__(self, message: str):
        super().__init__("unsupported_python", message)


class SourceConflictError(SourceError):
    def __init__(self, message: str = "source has an unresolved external modification"):
        super().__init__("external_conflict", message)


class SourceSaveError(SourceError):
    pass


@dataclass
class SourceDocument:
    path: Path
    raw_bytes: bytes
    text: str
    mode: SourceMode
    unit: LogicalUnit | None = None
    imports: tuple[ImportSpec, ...] = ()
    templates: tuple[TemplateSourceDefinition, ...] = ()
    active_dsl_bindings: tuple[tuple[str, str], ...] = ()
    active_module_bindings: tuple[tuple[str, str], ...] = ()
    active_external_bindings: tuple[tuple[str, str, str], ...] = ()
    active_local_templates: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    prefix_text: str = ""
    suffix_text: str = ""
    module_name: str = ""
    disk_digest: str = ""
    dirty: bool = False
    conflict: bool = False
    overwrite_confirmed: bool = False
    is_new: bool = False

    @property
    def read_only(self) -> bool:
        return self.mode == SourceMode.READ_ONLY

    def mark_dirty(self, unit: LogicalUnit | None = None) -> None:
        if self.read_only:
            raise SourceSaveError("read_only", "unsupported Python is read-only")
        if unit is not None:
            self.unit = unit
        self.dirty = True


@dataclass
class AuthoringSourceProject:
    root: Path
    files: dict[Path, SourceDocument]
    program: AuthoringProgram
    diagnostics: tuple[Diagnostic, ...] = ()
    deleted_files: dict[Path, SourceDocument] = field(default_factory=dict)

    def file_for_unit(self, unit_id: str) -> SourceDocument:
        for document in self.files.values():
            if document.unit is not None and document.unit.id == unit_id:
                return document
        raise SourceError("unknown_unit", f"no source file for logical unit {unit_id!r}")

    def refresh_program(self) -> AuthoringProgram:
        self.program = AuthoringProgram.from_units(
            document.unit
            for document in self.files.values()
            if document.unit is not None and not document.read_only
        )
        semantic = self.program.validate()
        source = tuple(
            diagnostic
            for document in self.files.values()
            for diagnostic in document.diagnostics
        )
        self.diagnostics = (*source, *semantic)
        return self.program

    def add_unsaved_unit(self, unit: LogicalUnit, relative_path: str | Path) -> SourceDocument:
        """Add a supported in-memory document without touching the filesystem."""

        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".py":
            raise SourceError("invalid_source_path", f"invalid authoring path {relative.as_posix()!r}")
        if relative in self.files:
            raise SourceError("source_exists", f"source path already exists: {relative.as_posix()}")
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise SourceError("invalid_source_path", "source path escapes the authoring root") from exc
        module = ".".join([_project_module_prefix(self.root), *relative.with_suffix("").parts])
        document = SourceDocument(
            path=path,
            raw_bytes=b"",
            text="",
            mode=SourceMode.SUPPORTED,
            unit=unit,
            module_name=module,
            disk_digest=_digest(b""),
            dirty=True,
            is_new=True,
        )
        unit.source_path = path
        self.files[relative] = document
        self.deleted_files.pop(relative, None)
        self.refresh_program()
        return document

    def tombstone_unit(self, unit_id: str) -> SourceDocument:
        """Hide a source document until save; callers may restore it for Undo."""

        for relative, document in tuple(self.files.items()):
            if document.unit is not None and document.unit.id == unit_id:
                del self.files[relative]
                self.deleted_files[relative] = document
                self.refresh_program()
                return document
        raise SourceError("unknown_unit", f"no source file for logical unit {unit_id!r}")

    def restore_tombstone(self, relative_path: str | Path) -> SourceDocument:
        relative = Path(relative_path)
        try:
            document = self.deleted_files.pop(relative)
        except KeyError as exc:
            raise SourceError("unknown_tombstone", relative.as_posix()) from exc
        self.files[relative] = document
        self.refresh_program()
        return document

    def save_unit(self, unit_id: str, *, confirm_overwrite: bool = False) -> str:
        document = self.file_for_unit(unit_id)
        text = save_python_source(
            document,
            program=self.program,
            confirm_overwrite=confirm_overwrite,
        )
        self.refresh_program()
        return text


def load_python_source(
    path: str | Path,
    *,
    module_name: str | None = None,
) -> SourceDocument:
    source_path = Path(path)
    raw = source_path.read_bytes()
    digest = _digest(raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _readonly_document(
            source_path,
            raw,
            "",
            digest,
            f"source is not valid UTF-8: {exc}",
            module_name or source_path.stem,
        )
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    resolved_module = module_name or source_path.stem
    try:
        parser = _SourceParser(source_path, normalized, resolved_module)
        parsed = parser.parse()
    except (SyntaxError, UnsupportedSourceError, ProgramError) as exc:
        if isinstance(exc, SyntaxError):
            message = f"syntax error: {exc.msg} at line {exc.lineno}"
            span = SourceSpan(exc.lineno or 1, max(0, (exc.offset or 1) - 1), exc.lineno or 1, max(0, exc.offset or 0))
        else:
            message = exc.message
            span = None
        return SourceDocument(
            path=source_path,
            raw_bytes=raw,
            text=text,
            mode=SourceMode.READ_ONLY,
            diagnostics=(
                Diagnostic(
                    code="unsupported_python",
                    message=message,
                    source_path=str(source_path),
                    span=span,
                ),
            ),
            module_name=resolved_module,
            disk_digest=digest,
        )
    parsed.raw_bytes = raw
    parsed.disk_digest = digest
    return parsed


def load_source(path: str | Path, *, module_name: str | None = None) -> SourceDocument:
    """Short public alias used by editor/session callers."""

    return load_python_source(path, module_name=module_name)


def find_python_module_source(module_name: str) -> Path | None:
    """Resolve a module's ``.py`` origin without importing that module."""

    search_path: Sequence[str] | None = sys.path
    full_name = ""
    spec = None
    for part in module_name.split("."):
        full_name = f"{full_name}.{part}" if full_name else part
        spec = importlib.machinery.PathFinder.find_spec(full_name, search_path)
        if spec is None:
            return None
        search_path = spec.submodule_search_locations
    if spec is None or not spec.origin or spec.origin in {"built-in", "frozen"}:
        return None
    path = Path(spec.origin)
    return path if path.is_file() and path.suffix.lower() == ".py" else None


def load_template_source_definitions(
    path: str | Path,
    *,
    module_name: str,
) -> tuple[TemplateSourceDefinition, ...]:
    """Read direct ``@template`` signatures without executing module code."""

    source_path = Path(path)
    try:
        text = source_path.read_text(encoding="utf-8")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        parser = _SourceParser(source_path, text, module_name)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return ()
    definitions: list[TemplateSourceDefinition] = []
    for statement in parser.tree.body:
        try:
            if isinstance(statement, ast.Import):
                parser._record_import(statement)
            elif isinstance(statement, ast.ImportFrom):
                parser._record_from_import(statement)
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if isinstance(statement, ast.FunctionDef) and parser._is_template_definition(
                    statement
                ):
                    definitions.append(parser._template_definition(statement))
                parser._unbind_name(statement.name)
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = (
                    statement.targets
                    if isinstance(statement, ast.Assign)
                    else [statement.target]
                )
                for target in targets:
                    if isinstance(target, ast.Name):
                        parser._unbind_name(target.id)
        except (UnsupportedSourceError, ProgramError, ValueError, TypeError):
            continue
    return tuple(definitions)


def load_authoring_project(root: str | Path) -> AuthoringSourceProject:
    project_root = Path(root).resolve()
    if not project_root.is_dir():
        raise SourceError("project_missing", f"authoring project does not exist: {project_root}")
    files: dict[Path, SourceDocument] = {}
    project_package = _project_module_prefix(project_root)
    for path in sorted(project_root.rglob("*.py"), key=lambda item: item.relative_to(project_root).as_posix()):
        if path.name == "__init__.py":
            continue
        relative = path.relative_to(project_root)
        module_parts = [project_package, *relative.with_suffix("").parts]
        document = load_python_source(path, module_name=".".join(module_parts))
        files[relative] = document
    project = AuthoringSourceProject(project_root, files, AuthoringProgram())
    project.refresh_program()
    return project


def load_project(root: str | Path) -> AuthoringSourceProject:
    return load_authoring_project(root)


def render_python_source(document: SourceDocument) -> str:
    if document.read_only or document.unit is None:
        raise SourceSaveError("read_only", "unsupported Python cannot be formatted")
    _validate_template_imports(document)
    prefix = _normalize_block(document.prefix_text).rstrip()
    required_names = _required_dsl_names(document.unit)
    bare_imports = {
        local
        for local, canonical in document.active_dsl_bindings
        if local == canonical
    }
    missing_imports = required_names - bare_imports
    if missing_imports:
        _validate_dsl_import_insertion(document, missing_imports)
        prefix = _insert_canonical_dsl_import(prefix, missing_imports).rstrip()
    suffix = _normalize_block(document.suffix_text).strip("\n")
    parts: list[str] = []
    if prefix:
        parts.append(prefix)
    parts.append(_render_unit_assignment(document.unit))
    if suffix:
        parts.append(suffix)
    return "\n\n".join(parts).rstrip() + "\n"


def save_python_source(
    document: SourceDocument,
    *,
    program: AuthoringProgram | None = None,
    confirm_overwrite: bool = False,
) -> str:
    if document.read_only or document.unit is None:
        raise SourceSaveError("read_only", "unsupported Python is read-only and was not written")
    current = document.path.read_bytes() if document.path.exists() else b""
    current_digest = _digest(current)
    disk_changed = current_digest != document.disk_digest
    if document.conflict or (document.dirty and disk_changed):
        document.conflict = True
        if not (confirm_overwrite or document.overwrite_confirmed):
            raise SourceConflictError()
    if disk_changed and not document.dirty:
        if document.path.exists():
            try:
                reloaded = load_python_source(
                    document.path,
                    module_name=document.module_name,
                )
            except FileNotFoundError:
                reloaded = _readonly_document(
                    document.path,
                    b"",
                    "",
                    _digest(b""),
                    "source file was deleted externally",
                    document.module_name,
                )
        else:
            reloaded = _readonly_document(
                document.path,
                b"",
                "",
                _digest(b""),
                "source file was deleted externally",
                document.module_name,
            )
        _copy_document_state(document, reloaded)
        if document.read_only:
            raise SourceSaveError(
                "read_only",
                "externally changed Python is unsupported and was not written",
            )
        return document.text
    validation_program = program or AuthoringProgram.from_units([document.unit])
    blocking = list(validation_program.validate())
    if program is None:
        # A single source file cannot resolve project-level references.  Every
        # other structural error still blocks the atomic write.
        blocking = [item for item in blocking if item.code != "unresolved_reference"]
    if blocking:
        raise ProgramValidationError(blocking)
    text = render_python_source(document)
    payload = text.encode("utf-8")
    try:
        refreshed = _SourceParser(document.path, text, document.module_name).parse()
    except (SyntaxError, UnsupportedSourceError, ProgramError) as exc:
        message = exc.msg if isinstance(exc, SyntaxError) else exc.message
        raise SourceSaveError(
            "render_invalid", f"formatter produced unsupported Python: {message}"
        ) from exc
    if refreshed.unit is None or refreshed.unit.semantic_data() != document.unit.semantic_data():
        raise SourceSaveError(
            "render_changed_semantics",
            "formatter output is not semantically equivalent to the in-memory unit",
        )
    document.path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{document.path.name}.",
            suffix=".tmp",
            dir=document.path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temporary_path, document.path)
    except OSError as exc:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise SourceSaveError("atomic_save_failed", str(exc)) from exc
    refreshed.raw_bytes = payload
    refreshed.disk_digest = _digest(payload)
    _copy_document_state(document, refreshed)
    return text


def _copy_document_state(target: SourceDocument, source: SourceDocument) -> None:
    target.raw_bytes = source.raw_bytes
    target.text = source.text
    target.mode = source.mode
    target.unit = source.unit
    target.imports = source.imports
    target.templates = source.templates
    target.active_dsl_bindings = source.active_dsl_bindings
    target.active_module_bindings = source.active_module_bindings
    target.active_external_bindings = source.active_external_bindings
    target.active_local_templates = source.active_local_templates
    target.diagnostics = source.diagnostics
    target.prefix_text = source.prefix_text
    target.suffix_text = source.suffix_text
    target.module_name = source.module_name
    target.disk_digest = source.disk_digest
    target.dirty = False
    target.conflict = False
    target.overwrite_confirmed = False
    target.is_new = False


def save_source(
    document: SourceDocument,
    *,
    program: AuthoringProgram | None = None,
    confirm_overwrite: bool = False,
) -> str:
    return save_python_source(document, program=program, confirm_overwrite=confirm_overwrite)


def check_external_change(document: SourceDocument) -> tuple[ExternalChange, SourceDocument]:
    try:
        current = document.path.read_bytes()
    except FileNotFoundError:
        current = b""
    if _digest(current) == document.disk_digest:
        return ExternalChange.UNCHANGED, document
    if document.dirty:
        document.conflict = True
        document.overwrite_confirmed = False
        return ExternalChange.CONFLICT, document
    if not document.path.exists():
        return ExternalChange.RELOADED, _readonly_document(
            document.path,
            b"",
            "",
            _digest(b""),
            "source file was deleted externally",
            document.module_name,
        )
    return ExternalChange.RELOADED, load_python_source(document.path, module_name=document.module_name)


def resolve_external_conflict(document: SourceDocument, decision: str) -> SourceDocument:
    if decision == "reload":
        if not document.path.exists():
            return _readonly_document(
                document.path,
                b"",
                "",
                _digest(b""),
                "source file was deleted externally",
                document.module_name,
            )
        return load_python_source(document.path, module_name=document.module_name)
    if decision == "keep":
        if not document.conflict:
            raise SourceConflictError("source is not in conflict")
        document.overwrite_confirmed = True
        return document
    raise ValueError("decision must be 'keep' or 'reload'")


def _readonly_document(
    path: Path,
    raw: bytes,
    text: str,
    digest: str,
    message: str,
    module_name: str,
) -> SourceDocument:
    return SourceDocument(
        path=path,
        raw_bytes=raw,
        text=text,
        mode=SourceMode.READ_ONLY,
        diagnostics=(
            Diagnostic(
                code="unsupported_python",
                message=message,
                source_path=str(path),
            ),
        ),
        module_name=module_name,
        disk_digest=digest,
    )


class _SourceParser:
    def __init__(self, path: Path, text: str, module_name: str):
        self.path = path
        self.text = text
        self.lines = text.splitlines()
        self.module_name = module_name
        self.tree = ast.parse(text, filename=str(path), mode="exec")
        self.imports: list[ImportSpec] = []
        self.dsl_aliases: dict[str, str] = {}
        self.module_aliases: dict[str, str] = {}
        self.external_aliases: dict[str, tuple[str, str]] = {}
        self.template_nodes: dict[str, ast.FunctionDef] = {}
        self.comment_tokens = self._comments()

    def parse(self) -> SourceDocument:
        assignment: ast.Assign | None = None
        unit: LogicalUnit | None = None
        active_dsl_bindings: tuple[tuple[str, str], ...] = ()
        active_module_bindings: tuple[tuple[str, str], ...] = ()
        active_external_bindings: tuple[tuple[str, str, str], ...] = ()
        active_local_templates: tuple[str, ...] = ()
        templates: list[TemplateSourceDefinition] = []
        for index, statement in enumerate(self.tree.body):
            if index == 0 and _is_docstring(statement):
                continue
            if isinstance(statement, ast.Import):
                self._record_import(statement)
                continue
            if isinstance(statement, ast.ImportFrom):
                self._record_from_import(statement)
                continue
            if isinstance(statement, ast.FunctionDef) and self._is_template_definition(statement):
                if statement.name in self.template_nodes:
                    raise UnsupportedSourceError(f"duplicate template {statement.name!r}")
                self._unbind_name(statement.name)
                self.template_nodes[statement.name] = statement
                templates.append(self._template_definition(statement))
                continue
            if isinstance(statement, ast.Assign):
                if assignment is not None:
                    raise UnsupportedSourceError("each file must contain exactly one main logical unit assignment")
                if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                    raise UnsupportedSourceError("main logical unit must use one simple name assignment")
                assignment = statement
                unit = self._parse_unit_call(statement.value)
                self._reject_template_binding_collisions(unit)
                active_dsl_bindings = tuple(sorted(self.dsl_aliases.items()))
                active_module_bindings = tuple(sorted(self.module_aliases.items()))
                active_external_bindings = tuple(
                    (local, module, symbol)
                    for local, (module, symbol) in sorted(self.external_aliases.items())
                )
                active_local_templates = tuple(sorted(self.template_nodes))
                continue
            raise UnsupportedSourceError(
                f"unsupported top-level statement {type(statement).__name__} at line {getattr(statement, 'lineno', '?')}"
            )
        if assignment is None:
            raise UnsupportedSourceError("file has no main logical unit assignment")
        assert unit is not None
        unit.assignment_name = assignment.targets[0].id
        unit.source_path = self.path
        unit.source_span = _span(assignment.value)
        start_offset = _line_offset(self.text, assignment.lineno)
        end_offset = _line_offset(self.text, assignment.end_lineno + 1 if assignment.end_lineno else assignment.lineno + 1)
        prefix = self.text[:start_offset]
        suffix = self.text[end_offset:]
        return SourceDocument(
            path=self.path,
            raw_bytes=b"",
            text=self.text,
            mode=SourceMode.SUPPORTED,
            unit=unit,
            imports=tuple(self.imports),
            templates=tuple(templates),
            active_dsl_bindings=active_dsl_bindings,
            active_module_bindings=active_module_bindings,
            active_external_bindings=active_external_bindings,
            active_local_templates=active_local_templates,
            prefix_text=prefix,
            suffix_text=suffix,
            module_name=self.module_name,
        )

    def _reject_template_binding_collisions(self, unit: LogicalUnit) -> None:
        required_names = _required_dsl_names(unit)
        for node in unit.walk_nodes():
            if node.kind != "TemplateCall" or node.template is None:
                continue
            display_name = node.template.display_name or node.template.symbol
            root = display_name.partition(".")[0]
            if (
                node.template.module == "src.authoring.dsl"
                and display_name == node.template.symbol
            ):
                continue
            if root in required_names:
                raise UnsupportedSourceError(
                    f"template call {display_name!r} conflicts with required DSL name {root!r}"
                )

    def _record_import(self, statement: ast.Import) -> None:
        for alias in statement.names:
            spec = ImportSpec(alias.name, alias=alias.asname)
            self.imports.append(spec)
            local = alias.asname or alias.name.split(".", 1)[0]
            self._unbind_name(local)
            self.module_aliases[local] = alias.name
            if alias.name == "src.authoring.dsl":
                self.module_aliases[local] = "src.authoring.dsl"

    def _record_from_import(self, statement: ast.ImportFrom) -> None:
        if statement.level:
            module = "." * statement.level + (statement.module or "")
        else:
            module = statement.module or ""
        if module.startswith("."):
            package = self.module_name.rpartition(".")[0]
            try:
                module = importlib.util.resolve_name(module, package)
            except (ImportError, ValueError) as exc:
                raise UnsupportedSourceError(f"invalid relative import {module!r}: {exc}") from exc
        if not module:
            raise UnsupportedSourceError("relative import has no module")
        for alias in statement.names:
            if alias.name == "*":
                raise UnsupportedSourceError("star imports are not supported")
            spec = ImportSpec(module, alias.name, alias.asname)
            self.imports.append(spec)
            local = alias.asname or alias.name
            self._unbind_name(local)
            if module == "src.authoring.dsl" and alias.name in dsl.PUBLIC_CONSTRUCTORS:
                self.dsl_aliases[local] = alias.name
            elif module == "src.authoring.dsl" and alias.name == "template":
                self.dsl_aliases[local] = "template"
            else:
                self.external_aliases[local] = (module, alias.name)

    def _unbind_name(self, local: str) -> None:
        self.dsl_aliases.pop(local, None)
        self.module_aliases.pop(local, None)
        self.external_aliases.pop(local, None)
        self.template_nodes.pop(local, None)

    def _is_template_definition(self, statement: ast.FunctionDef) -> bool:
        if len(statement.decorator_list) != 1:
            return False
        name = _dotted_name(statement.decorator_list[0])
        if name in self.dsl_aliases and self.dsl_aliases[name] == "template":
            return True
        if (
            name == "src.authoring.dsl.template"
            and self.module_aliases.get("src") == "src.authoring.dsl"
        ):
            return True
        if "." in name:
            prefix, _, attr = name.rpartition(".")
            return self.module_aliases.get(prefix) == "src.authoring.dsl" and attr == "template"
        return False

    def _template_definition(self, statement: ast.FunctionDef) -> TemplateSourceDefinition:
        positional_nodes = [*statement.args.posonlyargs, *statement.args.args]
        positional_defaults: list[Any] = [inspect.Parameter.empty] * (
            len(positional_nodes) - len(statement.args.defaults)
        ) + [self._parse_value(value) for value in statement.args.defaults]
        signature_parameters: list[inspect.Parameter] = []
        for index, (argument, default) in enumerate(zip(positional_nodes, positional_defaults)):
            kind = (
                inspect.Parameter.POSITIONAL_ONLY
                if index < len(statement.args.posonlyargs)
                else inspect.Parameter.POSITIONAL_OR_KEYWORD
            )
            annotation = (
                ast.unparse(argument.annotation)
                if argument.annotation is not None
                else inspect.Parameter.empty
            )
            signature_parameters.append(
                inspect.Parameter(argument.arg, kind, default=default, annotation=annotation)
            )
        if statement.args.vararg is not None:
            argument = statement.args.vararg
            annotation = (
                ast.unparse(argument.annotation)
                if argument.annotation is not None
                else inspect.Parameter.empty
            )
            signature_parameters.append(
                inspect.Parameter(
                    argument.arg,
                    inspect.Parameter.VAR_POSITIONAL,
                    annotation=annotation,
                )
            )
        for argument, default_node in zip(statement.args.kwonlyargs, statement.args.kw_defaults):
            default = (
                inspect.Parameter.empty
                if default_node is None
                else self._parse_value(default_node)
            )
            annotation = (
                ast.unparse(argument.annotation)
                if argument.annotation is not None
                else inspect.Parameter.empty
            )
            signature_parameters.append(
                inspect.Parameter(
                    argument.arg,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=default,
                    annotation=annotation,
                )
            )
        if statement.args.kwarg is not None:
            argument = statement.args.kwarg
            annotation = (
                ast.unparse(argument.annotation)
                if argument.annotation is not None
                else inspect.Parameter.empty
            )
            signature_parameters.append(
                inspect.Parameter(
                    argument.arg,
                    inspect.Parameter.VAR_KEYWORD,
                    annotation=annotation,
                )
            )
        return_annotation = (
            ast.unparse(statement.returns)
            if statement.returns is not None
            else inspect.Signature.empty
        )
        signature = inspect.Signature(
            signature_parameters,
            return_annotation=return_annotation,
        )
        parameters = tuple(parameter.name for parameter in signature_parameters)
        source = ast.get_source_segment(self.text, statement) or ast.unparse(statement)
        return TemplateSourceDefinition(
            identity=f"{self.module_name}.{statement.name}",
            symbol=statement.name,
            parameters=parameters,
            source=source,
            source_path=str(self.path),
            span=_span(statement),
            signature=signature,
        )

    def _parse_unit_call(self, value: ast.AST) -> LogicalUnit:
        if not isinstance(value, ast.Call):
            raise UnsupportedSourceError("main logical unit value must be a constructor call")
        constructor_name = self._dsl_constructor_name(value.func)
        if constructor_name not in dsl.UNIT_CONSTRUCTORS:
            raise UnsupportedSourceError(f"main assignment must construct a logical unit, got {constructor_name or _dotted_name(value.func)!r}")
        unit = self._invoke_constructor(dsl.UNIT_CONSTRUCTORS[constructor_name], value)
        if not isinstance(unit, LogicalUnit):
            raise UnsupportedSourceError("main constructor did not create a logical unit")
        return unit

    def _parse_value(self, value: ast.AST) -> Any:
        if isinstance(value, ast.Constant):
            if value.value is None or isinstance(value.value, (bool, int, float, str)):
                return value.value
            raise UnsupportedSourceError(f"unsupported literal {type(value.value).__name__}")
        if isinstance(value, ast.List):
            return [self._parse_value(item) for item in value.elts]
        if isinstance(value, ast.Tuple):
            return tuple(self._parse_value(item) for item in value.elts)
        if isinstance(value, ast.Dict):
            result: dict[str, Any] = {}
            for key_node, item in zip(value.keys, value.values):
                if key_node is None:
                    raise UnsupportedSourceError("dictionary unpacking is not supported")
                key = self._parse_value(key_node)
                if not isinstance(key, str):
                    raise UnsupportedSourceError("dictionary keys must be strings")
                result[key] = self._parse_value(item)
            return result
        if isinstance(value, ast.UnaryOp) and isinstance(value.op, (ast.USub, ast.UAdd)):
            operand = self._parse_value(value.operand)
            if isinstance(operand, bool) or not isinstance(operand, (int, float)):
                raise UnsupportedSourceError("unary +/- is only supported for numbers")
            return -operand if isinstance(value.op, ast.USub) else +operand
        if isinstance(value, ast.Call):
            constructor_name = self._dsl_constructor_name(value.func)
            if constructor_name in dsl.PUBLIC_CONSTRUCTORS:
                result = self._invoke_constructor(dsl.PUBLIC_CONSTRUCTORS[constructor_name], value)
                if isinstance(result, Node):
                    result.source_span = _span(value)
                    result.comments = self._node_comments(value)
                return result
            return self._parse_template_call(value)
        raise UnsupportedSourceError(
            f"unsupported expression {type(value).__name__} at line {getattr(value, 'lineno', '?')}"
        )

    def _invoke_constructor(self, constructor: Any, call: ast.Call) -> Any:
        positional = [self._parse_value(item) for item in call.args]
        keywords: dict[str, Any] = {}
        for keyword in call.keywords:
            if keyword.arg is None:
                raise UnsupportedSourceError("** expansion is not supported")
            if keyword.arg in keywords:
                raise UnsupportedSourceError(f"duplicate keyword {keyword.arg!r}")
            keywords[keyword.arg] = self._parse_value(keyword.value)
        is_node = constructor in dsl.NODE_CONSTRUCTORS.values()
        if is_node and "uid" not in keywords:
            keywords["uid"] = self._stable_uid(constructor.__name__, call)
        try:
            inspect.signature(constructor).bind(*positional, **keywords)
            return constructor(*positional, **keywords)
        except (TypeError, ProgramError) as exc:
            raise UnsupportedSourceError(
                f"invalid {constructor.__name__} call at line {call.lineno}: {exc}"
            ) from exc

    def _parse_template_call(self, call: ast.Call) -> Node:
        target = self._template_target(call.func)
        if target is None:
            raise UnsupportedSourceError(
                f"call {_dotted_name(call.func)!r} is neither a DSL constructor nor an explicitly imported template"
            )
        positional = [self._parse_value(item) for item in call.args]
        keywords: dict[str, Any] = {}
        uid: str | None = None
        seen_keywords: set[str] = set()
        for keyword in call.keywords:
            if keyword.arg is None:
                raise UnsupportedSourceError("template ** expansion is not supported")
            if keyword.arg in seen_keywords:
                raise UnsupportedSourceError(
                    f"duplicate template keyword {keyword.arg!r}"
                )
            seen_keywords.add(keyword.arg)
            parsed = self._parse_value(keyword.value)
            if keyword.arg == "uid":
                if not isinstance(parsed, str):
                    raise UnsupportedSourceError("template uid must be text")
                uid = parsed
            else:
                keywords[keyword.arg] = parsed
        node = make_template_call(
            target,
            positional,
            keywords,
            uid=uid if uid is not None else self._stable_uid("template", call),
            source_span=_span(call),
        )
        node.comments = self._node_comments(call)
        return node

    def _dsl_constructor_name(self, value: ast.AST) -> str | None:
        dotted = _dotted_name(value)
        if not dotted:
            return None
        if "." not in dotted:
            if dotted in self.dsl_aliases:
                return self.dsl_aliases[dotted]
            return None
        prefix, _, attr = dotted.rpartition(".")
        if (
            dotted.startswith("src.authoring.dsl.")
            and self.module_aliases.get("src") == "src.authoring.dsl"
            and attr in dsl.PUBLIC_CONSTRUCTORS
        ):
            return attr
        if self.module_aliases.get(prefix) == "src.authoring.dsl" and attr in dsl.PUBLIC_CONSTRUCTORS:
            return attr
        root, _, remainder = dotted.partition(".")
        module = self.module_aliases.get(root)
        if module == "src.authoring.dsl" and remainder in dsl.PUBLIC_CONSTRUCTORS:
            return remainder
        return None

    def _template_target(self, value: ast.AST) -> TemplateTarget | None:
        dotted = _dotted_name(value)
        if not dotted:
            return None
        if "." not in dotted and dotted in self.template_nodes:
            definition = self.template_nodes[dotted]
            return TemplateTarget(
                identity=f"{self.module_name}.{dotted}",
                symbol=dotted,
                display_name=dotted,
                module=self.module_name,
                resolved=True,
                definition_path=str(self.path),
                definition_span=_span(definition),
            )
        if "." not in dotted and dotted in self.external_aliases:
            module, symbol = self.external_aliases[dotted]
            return TemplateTarget(
                identity=f"{module}.{symbol}",
                symbol=symbol,
                display_name=dotted,
                module=module,
                resolved=True,
            )
        if "." in dotted:
            prefix, _, symbol = dotted.partition(".")
            module = self.module_aliases.get(prefix)
            if module is None and prefix in self.external_aliases:
                parent_module, imported_name = self.external_aliases[prefix]
                module = f"{parent_module}.{imported_name}"
            if module:
                module_suffix = module[len(prefix) + 1 :] if module.startswith(f"{prefix}.") else ""
                if module_suffix and symbol.startswith(f"{module_suffix}."):
                    symbol = symbol[len(module_suffix) + 1 :]
            is_builtin_template = (
                module == "src.authoring.dsl"
                and symbol in {value.__name__ for value in dsl.BUILTIN_TEMPLATES}
            )
            if module and (module != "src.authoring.dsl" or is_builtin_template):
                return TemplateTarget(
                    identity=f"{module}.{symbol}",
                    symbol=symbol,
                    display_name=dotted,
                    module=module,
                    resolved=True,
                )
        return None

    def _stable_uid(self, kind: str, value: ast.AST) -> str:
        seed = f"{self.module_name}:{value.lineno}:{value.col_offset}:{kind}"
        return f"node_{uuid.uuid5(_UID_NAMESPACE, seed).hex}"

    def _comments(self) -> dict[int, list[tuple[int, str]]]:
        result: dict[int, list[tuple[int, str]]] = {}
        try:
            tokens = tokenize.generate_tokens(io.StringIO(self.text).readline)
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    result.setdefault(token.start[0], []).append((token.start[1], token.string))
        except tokenize.TokenError:
            return result
        return result

    def _node_comments(self, value: ast.AST) -> NodeComments:
        leading: list[str] = []
        line = value.lineno - 1
        while line >= 1:
            text = self.lines[line - 1] if line - 1 < len(self.lines) else ""
            stripped = text.strip()
            if not stripped:
                break
            comments = self.comment_tokens.get(line, [])
            if not comments or not stripped.startswith("#"):
                break
            leading.insert(0, comments[0][1])
            line -= 1
        trailing = None
        end_line = value.end_lineno or value.lineno
        source_line = self.lines[end_line - 1] if end_line - 1 < len(self.lines) else ""
        end_column = _utf8_byte_column_to_character(
            source_line, value.end_col_offset or 0
        )
        for column, comment in self.comment_tokens.get(end_line, []):
            if column >= end_column:
                trailing = comment
                break
        return NodeComments(tuple(leading), trailing)


def _is_docstring(statement: ast.AST) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _dotted_name(value: ast.AST) -> str:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        prefix = _dotted_name(value.value)
        return f"{prefix}.{value.attr}" if prefix else ""
    return ""


def _span(value: ast.AST) -> SourceSpan:
    return SourceSpan(
        value.lineno,
        value.col_offset,
        value.end_lineno or value.lineno,
        value.end_col_offset or value.col_offset,
    )


def _utf8_byte_column_to_character(line: str, byte_column: int) -> int:
    prefix = line.encode("utf-8")[:byte_column]
    return len(prefix.decode("utf-8", errors="ignore"))


def _line_offset(text: str, one_based_line: int) -> int:
    if one_based_line <= 1:
        return 0
    lines = text.splitlines(keepends=True)
    return sum(len(item) for item in lines[: one_based_line - 1])


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalize_block(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _project_module_prefix(project_root: Path) -> str:
    parts = list(project_root.parts)
    if "game_content" in parts:
        index = len(parts) - 1 - parts[::-1].index("game_content")
        return ".".join(parts[index:])
    return project_root.name


def _required_dsl_names(unit: LogicalUnit) -> set[str]:
    names = {unit.kind}
    for parameter in unit.parameters:
        names.add("Parameter")
        if parameter.has_default:
            _collect_value_dsl_names(parameter.default, names)
    for value in unit.metadata.values():
        _collect_value_dsl_names(value, names)
    for node in unit.body:
        _collect_node_dsl_names(node, names)
    return names


def _collect_node_dsl_names(node: Node, names: set[str]) -> None:
    if node.kind in dsl.NODE_CONSTRUCTORS:
        names.add(node.kind)
    elif (
        node.kind == "TemplateCall"
        and node.template is not None
        and node.template.module == "src.authoring.dsl"
    ):
        names.add(node.template.symbol)
    for value in node.positional_arguments:
        _collect_value_dsl_names(value, names)
    for value in node.arguments.values():
        _collect_value_dsl_names(value, names)
    for children in node.children.values():
        for child in children:
            _collect_node_dsl_names(child, names)


def _collect_value_dsl_names(value: Any, names: set[str]) -> None:
    if isinstance(value, Ref):
        names.add("Ref")
    elif isinstance(value, Expr):
        names.add("Expr")
    elif isinstance(value, Parameter):
        names.add("Parameter")
        if value.has_default:
            _collect_value_dsl_names(value.default, names)
    elif isinstance(value, Mapping):
        for item in value.values():
            _collect_value_dsl_names(item, names)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_value_dsl_names(item, names)


def _validate_template_imports(document: SourceDocument) -> None:
    if document.unit is None:
        return
    for node in document.unit.walk_nodes():
        if node.kind != "TemplateCall" or node.template is None:
            continue
        target = node.template
        display_name = target.display_name or target.symbol
        if (
            target.module == "src.authoring.dsl"
            and display_name == target.symbol
            and "." not in display_name
        ):
            # Programmatically inserted built-ins are rendered by their canonical
            # symbol and receive a canonical import below.
            continue
        if _active_template_identity(document, display_name) == target.identity:
            continue
        raise SourceSaveError(
            "template_not_imported",
            f"template {target.identity!r} is not bound as {display_name!r} at the main assignment",
        )


def _active_template_identity(document: SourceDocument, display_name: str) -> str | None:
    if not display_name:
        return None
    dsl_bindings = dict(document.active_dsl_bindings)
    module_bindings = dict(document.active_module_bindings)
    external_bindings = {
        local: (module, symbol)
        for local, module, symbol in document.active_external_bindings
    }
    root, separator, remainder = display_name.partition(".")
    if not separator:
        if root in document.active_local_templates:
            return f"{document.module_name}.{root}"
        if root in external_bindings:
            module, symbol = external_bindings[root]
            return f"{module}.{symbol}"
        canonical = dsl_bindings.get(root)
        return f"src.authoring.dsl.{canonical}" if canonical else None

    if root in external_bindings:
        module, symbol = external_bindings[root]
        return f"{module}.{symbol}.{remainder}"
    module = module_bindings.get(root)
    if module is None:
        return None
    module_suffix = module[len(root) + 1 :] if module.startswith(f"{root}.") else ""
    if module_suffix and remainder.startswith(f"{module_suffix}."):
        remainder = remainder[len(module_suffix) + 1 :]
    return f"{module}.{remainder}"


def _validate_dsl_import_insertion(
    document: SourceDocument,
    missing_imports: set[str],
) -> None:
    if document.unit is None:
        return
    for node in document.unit.walk_nodes():
        if node.kind != "TemplateCall" or node.template is None:
            continue
        target = node.template
        display_name = target.display_name or target.symbol
        if (
            target.module == "src.authoring.dsl"
            and display_name == target.symbol
        ):
            continue
        root = display_name.partition(".")[0]
        if root not in missing_imports:
            continue
        if _active_template_identity(document, display_name) != target.identity:
            continue
        raise SourceSaveError(
            "template_binding_conflict",
            f"adding the required DSL import {root!r} would shadow template {target.identity!r}",
        )


def _insert_canonical_dsl_import(prefix: str, names: set[str]) -> str:
    ordered = sorted(names)
    single = f"from src.authoring.dsl import {', '.join(ordered)}"
    if len(single) <= 100:
        import_text = single + "\n"
    else:
        import_text = "from src.authoring.dsl import (\n"
        import_text += "".join(f"    {name},\n" for name in ordered)
        import_text += ")\n"

    before = prefix.rstrip()
    if not before:
        return import_text
    return before + "\n\n" + import_text


def _render_unit_assignment(unit: LogicalUnit) -> str:
    fields: list[tuple[str, Any]] = [("id", unit.id), ("name", unit.name)]
    if unit.kind == "Project":
        fields.extend(
            (
                ("start_stage", unit.metadata["start_stage"]),
                ("stages", unit.metadata["stages"]),
            )
        )
    elif unit.kind == "Boss":
        fields.extend(_ordered_metadata(unit))
    elif unit.kind in {"Task", "Function"}:
        if unit.parameters:
            fields.append(("parameters", unit.parameters))
        fields.append(("body", unit.body))
    else:
        fields.extend(_ordered_metadata(unit))
        fields.append(("body", unit.body))
    lines = [f"{unit.assignment_name or unit.kind.lower()} = {unit.kind}("]
    for name, value in fields:
        if name == "body" and isinstance(value, list):
            lines.extend(_render_node_list_field(name, value, 4))
        else:
            lines.extend(_render_named_value(name, value, 4))
    lines.append(")")
    return "\n".join(lines)


def _ordered_metadata(unit: LogicalUnit, excluded: set[str] | None = None) -> list[tuple[str, Any]]:
    excluded = excluded or set()
    constructor = dsl.UNIT_CONSTRUCTORS[unit.kind]
    order = [
        name
        for name in inspect.signature(constructor).parameters
        if name not in {"id", "name", "body", "parameters"}
    ]
    result = [(name, unit.metadata[name]) for name in order if name in unit.metadata and name not in excluded]
    seen = {name for name, _ in result} | excluded
    result.extend((name, unit.metadata[name]) for name in sorted(unit.metadata) if name not in seen)
    return result


def _render_named_value(name: str, value: Any, indent: int) -> list[str]:
    prefix = " " * indent + f"{name}="
    rendered = _render_value(value, indent + 4)
    if len(rendered) == 1 and len(prefix) + len(rendered[0]) + 1 <= 100:
        return [prefix + rendered[0] + ","]
    lines = [prefix + rendered[0]]
    lines.extend(rendered[1:])
    lines[-1] += ","
    return lines


def _render_node_list_field(name: str, nodes: Sequence[Node], indent: int) -> list[str]:
    lines = [" " * indent + f"{name}=["]
    lines.extend(_render_node_entries(nodes, indent + 4))
    lines.append(" " * indent + "],")
    return lines


def _render_node_entries(nodes: Sequence[Node], indent: int) -> list[str]:
    lines: list[str] = []
    for node in nodes:
        for comment in node.comments.leading:
            text = comment.strip()
            lines.append(" " * indent + (text if text.startswith("#") else f"# {text}"))
        rendered = _render_node(node, indent)
        rendered[-1] += ","
        if node.comments.trailing:
            trailing = node.comments.trailing.strip()
            rendered[-1] += "  " + (trailing if trailing.startswith("#") else f"# {trailing}")
        lines.extend(rendered)
    return lines


def _render_node(node: Node, indent: int) -> list[str]:
    if node.kind == "TemplateCall":
        return _render_template_call(node, indent)
    fields = _ordered_node_fields(node)
    if node.kind == "Parallel":
        return _render_parallel(node, fields, indent)
    fields.extend((slot, values) for slot, values in node.children.items())
    fields.append(("uid", node.uid))
    simple = not node.children and all(_simple_value(value) for _, value in fields)
    if simple:
        payload = ", ".join(f"{name}={_render_value(value, indent)[0]}" for name, value in fields)
        candidate = " " * indent + f"{node.kind}({payload})"
        if len(candidate) <= 100:
            return [candidate]
    lines = [" " * indent + f"{node.kind}("]
    for name, value in fields:
        if name in node.children:
            lines.extend(_render_node_list_field(name, value, indent + 4))
        else:
            lines.extend(_render_named_value(name, value, indent + 4))
    lines.append(" " * indent + ")")
    return lines


def _ordered_node_fields(node: Node) -> list[tuple[str, Any]]:
    constructor = dsl.NODE_CONSTRUCTORS.get(node.kind)
    if constructor is None:
        return list(node.arguments.items())
    order = [
        name
        for name, parameter in inspect.signature(constructor).parameters.items()
        if name not in {"uid", "runtime_options"}
        and parameter.kind not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
    ]
    result = [(name, node.arguments[name]) for name in order if name in node.arguments]
    seen = {name for name, _ in result}
    result.extend((name, node.arguments[name]) for name in sorted(node.arguments) if name not in seen)
    return result


def _render_parallel(node: Node, fields: list[tuple[str, Any]], indent: int) -> list[str]:
    lines = [" " * indent + "Parallel("]
    lines.append(" " * (indent + 4) + "branches=[")
    for branch in node.children.get("branches", []):
        lines.append(" " * (indent + 8) + "[")
        lines.extend(_render_node_entries(branch.children.get("body", []), indent + 12))
        lines.append(" " * (indent + 8) + "],")
    lines.append(" " * (indent + 4) + "],")
    for name, value in fields:
        lines.extend(_render_named_value(name, value, indent + 4))
    lines.extend(_render_named_value("uid", node.uid, indent + 4))
    lines.append(" " * indent + ")")
    return lines


def _render_template_call(node: Node, indent: int) -> list[str]:
    if node.template is None:
        raise SourceSaveError("template_missing", "template call has no target")
    positional = [_render_value(item, indent + 4) for item in node.positional_arguments]
    keyword_values = [
        (name, _render_value(value, indent + 8))
        for name, value in node.arguments.items()
    ]
    values = [rendered[0] for rendered in positional]
    values.extend(f"{name}={rendered[0]}" for name, rendered in keyword_values)
    values.append(f"uid={node.uid!r}")
    call_name = node.template.display_name or node.template.symbol
    candidate = " " * indent + f"{call_name}({', '.join(values)})"
    if (
        len(candidate) <= 100
        and all(len(rendered) == 1 for rendered in positional)
        and all(len(rendered) == 1 for _, rendered in keyword_values)
    ):
        return [candidate]
    lines = [" " * indent + f"{call_name}("]
    for rendered in positional:
        rendered = list(rendered)
        rendered[0] = " " * (indent + 4) + rendered[0]
        rendered[-1] += ","
        lines.extend(rendered)
    for name, value in node.arguments.items():
        lines.extend(_render_named_value(name, value, indent + 4))
    lines.extend(_render_named_value("uid", node.uid, indent + 4))
    lines.append(" " * indent + ")")
    return lines


def _render_value(value: Any, indent: int) -> list[str]:
    if isinstance(value, Ref):
        return [f"Ref({value.id!r})"]
    if isinstance(value, Expr):
        return [f"Expr({value.source!r})"]
    if isinstance(value, Parameter):
        fields = [f"name={value.name!r}", f"annotation={value.annotation!r}"]
        if not value.has_default:
            return [f"Parameter({', '.join(fields)})"]
        rendered_default = _render_value(value.default, indent + 4)
        candidate = (
            f"Parameter({', '.join(fields)}, default={rendered_default[0]})"
        )
        if len(rendered_default) == 1 and len(candidate) <= 80:
            return [candidate]
        lines = ["Parameter("]
        lines.extend(" " * (indent + 4) + f"{field}," for field in fields)
        lines.extend(_render_named_value("default", value.default, indent + 4))
        lines.append(" " * indent + ")")
        return lines
    if isinstance(value, Node):
        return _render_node(value, indent)
    if isinstance(value, list):
        if not value:
            return ["[]"]
        rendered_items = [_render_value(item, indent + 4) for item in value]
        if all(len(rendered) == 1 for rendered in rendered_items):
            candidate = "[" + ", ".join(rendered[0] for rendered in rendered_items) + "]"
            if len(candidate) <= 80:
                return [candidate]
        lines = ["["]
        for item_lines in rendered_items:
            rendered = list(item_lines)
            rendered[0] = " " * (indent + 4) + rendered[0]
            rendered[-1] += ","
            lines.extend(rendered)
        lines.append(" " * indent + "]")
        return lines
    if isinstance(value, tuple):
        if not value:
            return ["()"]
        rendered_items = [_render_value(item, indent + 4) for item in value]
        if all(len(rendered) == 1 for rendered in rendered_items):
            payload = ", ".join(rendered[0] for rendered in rendered_items)
            candidate = f"({payload}{',' if len(value) == 1 else ''})"
            if len(candidate) <= 80:
                return [candidate]
        lines = ["("]
        for item_lines in rendered_items:
            rendered = list(item_lines)
            rendered[0] = " " * (indent + 4) + rendered[0]
            rendered[-1] += ","
            lines.extend(rendered)
        lines.append(" " * indent + ")")
        return lines
    if isinstance(value, Mapping):
        if not value:
            return ["{}"]
        items = sorted(value.items())
        if all(_simple_value(item) for _, item in items):
            candidate = "{" + ", ".join(f"{key!r}: {_render_value(item, indent)[0]}" for key, item in items) + "}"
            if len(candidate) <= 80:
                return [candidate]
        lines = ["{"]
        for key, item in items:
            rendered = _render_value(item, indent + 4)
            if len(rendered) == 1:
                lines.append(" " * (indent + 4) + f"{key!r}: {rendered[0]},")
            else:
                lines.append(" " * (indent + 4) + f"{key!r}: {rendered[0]}")
                lines.extend(rendered[1:-1])
                lines.append(rendered[-1] + ",")
        lines.append(" " * indent + "}")
        return lines
    return [repr(value)]


def _simple_value(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str, Ref, Expr)):
        return "\n" not in value if isinstance(value, str) else True
    if isinstance(value, tuple):
        return len(value) <= 4 and all(_simple_value(item) for item in value)
    if isinstance(value, list):
        return len(value) <= 4 and all(_simple_value(item) for item in value)
    if isinstance(value, Mapping):
        return len(value) <= 3 and all(isinstance(key, str) and _simple_value(item) for key, item in value.items())
    return False


__all__ = [
    "AuthoringSourceProject",
    "ExternalChange",
    "SourceConflictError",
    "SourceDocument",
    "SourceError",
    "SourceMode",
    "SourceSaveError",
    "UnsupportedSourceError",
    "check_external_change",
    "find_python_module_source",
    "load_authoring_project",
    "load_project",
    "load_python_source",
    "load_source",
    "load_template_source_definitions",
    "render_python_source",
    "resolve_external_conflict",
    "save_python_source",
    "save_source",
]

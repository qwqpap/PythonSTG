"""Single owner for one open authoring project and its editor state."""

from __future__ import annotations

import os
import tempfile
import hashlib
import copy
from collections import deque
from pathlib import Path
from typing import Any

from src.authoring.program import (
    AuthoringProgram,
    DropPlacement,
    Expr,
    LogicalUnit,
    Node,
    ProgramError,
    Ref,
    TemplateTarget,
    find_node,
)
from src.authoring.python_source import (
    AuthoringSourceProject,
    ExternalChange,
    SourceConflictError,
    SourceDocument,
    SourceMode,
    SourceSaveError,
    check_external_change,
    find_python_module_source,
    load_authoring_project,
    load_template_source_definitions,
    render_python_source,
    resolve_external_conflict,
    save_python_source,
)
from src.core.project_context import ProjectContext
from src.qt_compat.QtCore import QFileSystemWatcher, QObject, Signal
from src.qt_compat.QtGui import QUndoStack


_ASSET_SUFFIXES = frozenset(
    {
        ".bmp",
        ".flac",
        ".gif",
        ".jpeg",
        ".jpg",
        ".json",
        ".mp3",
        ".ogg",
        ".otf",
        ".png",
        ".ttf",
        ".wav",
        ".webp",
    }
)
_IGNORED_ASSET_DIRECTORIES = frozenset(
    {
        ".claude",
        ".codex",
        ".git",
        ".github",
        ".hg",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".venv",
        ".vscode",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "trash",
        "venv",
    }
)


class EditorSession(QObject):
    """Own every mutable state value for exactly one editor window."""

    project_changed = Signal()
    selection_changed = Signal()
    source_changed = Signal()
    program_changed = Signal()
    dirty_changed = Signal(bool)
    problems_changed = Signal()
    build_changed = Signal(str)
    preview_changed = Signal(str)
    log_changed = Signal()
    trace_changed = Signal()
    external_conflict = Signal(tuple)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        project_context: ProjectContext | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_context = project_context
        self.source_project: AuthoringSourceProject | None = None
        self.current_unit_id: str | None = None
        self.current_node_uid: str | None = None
        self.current_source_path: Path | None = None
        self.build_state = "idle"
        self.preview_state = "stopped"
        self.preview_frame = 0
        self.last_build_identity: str | None = None
        self.trace_run_id: str | None = None
        self.run_log = deque(maxlen=512)
        self.trace_events = deque(maxlen=4096)
        self.undo_stack = QUndoStack(self)
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.fileChanged.connect(self._on_file_changed)
        self._saved_semantics: dict[str, dict[str, Any]] = {}
        self._pending_external: dict[Path, SourceDocument] = {}
        self._pending_tombstone_external: set[Path] = set()
        self._external_keep: set[Path] = set()
        self._saving = False
        self.undo_stack.cleanChanged.connect(self._emit_dirty)

    @property
    def is_open(self) -> bool:
        return self.source_project is not None

    @property
    def program(self) -> AuthoringProgram:
        if self.source_project is None:
            raise ProgramError("project_closed", "no authoring project is open")
        return self.source_project.program

    @property
    def current_unit(self) -> LogicalUnit | None:
        if self.source_project is None or self.current_unit_id is None:
            return None
        try:
            return self.program.get_unit(self.current_unit_id)
        except ProgramError:
            return None

    @property
    def current_node(self) -> Node | None:
        if self.source_project is None or self.current_node_uid is None:
            return None
        try:
            return find_node(self.program, self.current_node_uid)[1]
        except ProgramError:
            return None

    @property
    def current_document(self) -> SourceDocument | None:
        if self.source_project is None:
            return None
        if self.current_source_path is not None:
            return self.source_project.files.get(self.current_source_path)
        unit = self.current_unit
        if unit is None:
            return next(iter(self.source_project.files.values()), None)
        return self.source_project.file_for_unit(unit.id)

    @property
    def dirty(self) -> bool:
        return bool(
            self.source_project
            and (
                self.source_project.deleted_files
                or any(document.dirty for document in self.source_project.files.values())
            )
        )

    @property
    def has_conflict(self) -> bool:
        return bool(
            self.source_project
            and any(
                document.conflict
                for document in (
                    *self.source_project.files.values(),
                    *self.source_project.deleted_files.values(),
                )
            )
        )

    @property
    def pending_external_paths(self) -> tuple[Path, ...]:
        return tuple(sorted(self._pending_external, key=lambda path: path.as_posix()))

    @property
    def can_edit(self) -> bool:
        document = self.current_document
        return bool(
            document
            and not document.read_only
            and (not document.conflict or document.overwrite_confirmed)
        )

    @property
    def diagnostics(self):
        return self.source_project.diagnostics if self.source_project else ()

    @property
    def palette_templates(self) -> tuple[TemplateTarget, ...]:
        if self.source_project is None:
            return ()
        targets: dict[str, TemplateTarget] = {}
        external_definitions: dict[str, tuple] = {}
        for document in self.source_project.files.values():
            for definition in document.templates:
                targets[definition.identity] = TemplateTarget(
                    identity=definition.identity,
                    symbol=definition.symbol,
                    display_name=definition.symbol,
                    module=document.module_name,
                    resolved=True,
                    definition_path=definition.source_path,
                    definition_span=definition.span,
                    signature=definition.signature,
                )
            for local, module, symbol in document.active_external_bindings:
                if module not in external_definitions:
                    source_path = find_python_module_source(module)
                    external_definitions[module] = (
                        load_template_source_definitions(
                            source_path, module_name=module
                        )
                        if source_path is not None
                        else ()
                    )
                definition = next(
                    (
                        item
                        for item in external_definitions[module]
                        if item.symbol == symbol
                    ),
                    None,
                )
                if definition is None:
                    continue
                targets[definition.identity] = TemplateTarget(
                    identity=definition.identity,
                    symbol=definition.symbol,
                    display_name=local,
                    module=module,
                    resolved=True,
                    definition_path=definition.source_path or None,
                    definition_span=definition.span,
                    signature=definition.signature,
                )
        return tuple(targets[key] for key in sorted(targets))

    @property
    def source_text(self) -> str:
        document = self.current_document
        if document is None:
            return ""
        if document.read_only or document.unit is None:
            return document.text
        try:
            return render_python_source(document)
        except SourceSaveError:
            return document.text

    def open_project(self, root: str | Path) -> AuthoringSourceProject:
        source_project = load_authoring_project(root)
        if self.project_context is None:
            self.project_context = ProjectContext.discover(source_project.root)
        self.source_project = source_project
        self.undo_stack.clear()
        self._pending_external.clear()
        self._pending_tombstone_external.clear()
        self._external_keep.clear()
        self._remember_saved_semantics()
        units = sorted(
            source_project.program.logical_units(),
            key=lambda unit: (unit.kind != "Project", unit.kind, unit.id),
        )
        self.current_unit_id = units[0].id if units else None
        self.current_node_uid = None
        self.current_source_path = self._path_for_unit(self.current_unit_id)
        self._watch_project_files()
        self.project_changed.emit()
        self.program_changed.emit()
        self.selection_changed.emit()
        self.source_changed.emit()
        self.problems_changed.emit()
        self._emit_dirty()
        return source_project

    def close_project(self) -> None:
        watched = self.file_watcher.files()
        if watched:
            self.file_watcher.removePaths(watched)
        self.source_project = None
        self.current_unit_id = None
        self.current_node_uid = None
        self.current_source_path = None
        self.undo_stack.clear()
        self._saved_semantics.clear()
        self._pending_external.clear()
        self._pending_tombstone_external.clear()
        self._external_keep.clear()
        self.set_build_state("idle")
        self.set_preview_state("stopped")
        self.last_build_identity = None
        self.trace_run_id = None
        self.run_log.clear()
        self.trace_events.clear()
        self.project_changed.emit()
        self.program_changed.emit()
        self.selection_changed.emit()
        self.source_changed.emit()
        self.problems_changed.emit()
        self._emit_dirty()

    def select_unit(self, unit_id: str) -> None:
        unit = self.program.get_unit(unit_id)
        self.current_unit_id = unit.id
        self.current_node_uid = None
        self.current_source_path = self._path_for_unit(unit.id)
        self.selection_changed.emit()
        self.source_changed.emit()

    def select_source(self, relative_path: str | Path) -> None:
        if self.source_project is None:
            raise ProgramError("project_closed", "no authoring project is open")
        path = Path(relative_path)
        if path not in self.source_project.files:
            raise ProgramError("unknown_source", f"unknown source file {path.as_posix()!r}")
        document = self.source_project.files[path]
        self.current_source_path = path
        self.current_unit_id = document.unit.id if document.unit is not None else None
        self.current_node_uid = None
        self.selection_changed.emit()
        self.source_changed.emit()

    def select_node(self, uid: str | None) -> None:
        if uid is None:
            self.current_node_uid = None
        else:
            unit, _node, _location = find_node(self.program, uid)
            self.current_unit_id = unit.id
            self.current_source_path = self._path_for_unit(unit.id)
            self.current_node_uid = uid
        self.selection_changed.emit()
        self.source_changed.emit()

    def set_node_argument(self, uid: str, name: str, value: Any) -> None:
        unit, _node, _location = find_node(self.program, uid)
        self._require_editable_unit(unit.id)
        from .commands import SetNodeArgumentCommand

        self.undo_stack.push(SetNodeArgumentCommand(self, uid, name, value))

    def set_unit_field(self, unit_id: str, name: str, value: Any) -> None:
        self._require_editable_unit(unit_id)
        from .commands import SetUnitFieldCommand

        self.undo_stack.push(SetUnitFieldCommand(self, unit_id, name, value))

    def move_node(
        self,
        uid: str,
        target_uid: str,
        placement: DropPlacement | str,
        *,
        target_slot: str | None = None,
    ) -> None:
        unit, _node, _location = find_node(self.program, uid)
        self._require_editable_unit(unit.id)
        from .commands import MoveNodeCommand

        self.undo_stack.push(
            MoveNodeCommand(
                self,
                uid,
                target_uid,
                placement,
                target_slot=target_slot,
            )
        )

    def insert_node_relative(
        self,
        target_uid: str,
        placement: DropPlacement | str,
        node: Node,
        *,
        target_slot: str | None = None,
    ) -> None:
        unit, _target, _location = find_node(self.program, target_uid)
        self._require_editable_unit(unit.id)
        from .commands import InsertNodeCommand

        self.undo_stack.push(
            InsertNodeCommand(
                self, target_uid, placement, node, target_slot=target_slot
            )
        )

    def append_node(self, node: Node) -> None:
        unit = self.current_unit
        if unit is None:
            raise ProgramError("no_unit", "请先选择一个逻辑单元")
        self._require_editable_unit(unit.id)
        from .commands import AppendNodeCommand

        self.undo_stack.push(AppendNodeCommand(self, unit.id, node))

    def delete_node(self, uid: str) -> None:
        unit, _node, _location = find_node(self.program, uid)
        self._require_editable_unit(unit.id)
        from .commands import DeleteNodeCommand

        self.undo_stack.push(DeleteNodeCommand(self, uid))

    def duplicate_node(self, uid: str) -> None:
        unit, _node, _location = find_node(self.program, uid)
        self._require_editable_unit(unit.id)
        from .commands import DuplicateNodeCommand

        self.undo_stack.push(DuplicateNodeCommand(self, uid))

    def create_unit(
        self,
        unit: LogicalUnit,
        *,
        register_stage: bool = True,
    ) -> None:
        from .commands import CreateUnitCommand

        self.undo_stack.push(CreateUnitCommand(self, unit, register_stage=register_stage))

    def duplicate_unit(
        self,
        source_id: str,
        new_id: str,
        new_name: str,
        *,
        register_stage: bool = False,
    ) -> None:
        self._require_editable_unit(source_id)
        from .commands import DuplicateUnitCommand

        self.undo_stack.push(
            DuplicateUnitCommand(
                self, source_id, new_id, new_name, register_stage=register_stage
            )
        )

    def delete_unit(
        self,
        unit_id: str,
        *,
        replacement_start_stage: str | None = None,
    ) -> None:
        self._require_editable_unit(unit_id)
        from .commands import DeleteUnitCommand

        self.undo_stack.push(
            DeleteUnitCommand(
                self, unit_id, replacement_start_stage=replacement_start_stage
            )
        )

    @property
    def global_assets(self) -> tuple[str, ...]:
        if self.project_context is None:
            return ()
        return _scan_project_assets(self.project_context.root)

    @property
    def current_stage_id(self) -> str | None:
        unit = self.current_unit
        if unit is None:
            return None
        if unit.kind == "Stage":
            return unit.id
        project = next(
            (
                candidate
                for candidate in self.program.logical_units()
                if candidate.kind == "Project"
            ),
            None,
        )
        stage_ids = (
            [reference.id for reference in project.metadata.get("stages", ())]
            if project
            else []
        )
        for stage_id in stage_ids:
            if unit.id in self._unit_closure(stage_id):
                return stage_id
        return None

    @property
    def stage_assets(self) -> tuple[str, ...]:
        stage_id = self.current_stage_id
        if stage_id is None or self.project_context is None:
            return ()
        resources: set[str] = set()
        for unit_id in self._unit_closure(stage_id):
            unit = self.program.get_unit(unit_id)
            for value in unit.metadata.values():
                resources.update(_resource_values(value))
            for parameter in unit.parameters:
                if parameter.has_default:
                    resources.update(_resource_values(parameter.default))
            for node in unit.walk_nodes():
                if node.kind == "RawPython":
                    continue
                resources.update(_resource_values(node.arguments))
                resources.update(_resource_values(node.positional_arguments))
        root = self.project_context.root
        return tuple(sorted(uri for uri in resources if _resource_stays_in_root(uri, root)))

    def save_all(self) -> tuple[Path, ...]:
        if self.source_project is None:
            return ()
        if self.has_conflict and any(
            document.conflict and not document.overwrite_confirmed
            for document in (
                *self.source_project.files.values(),
                *self.source_project.deleted_files.values(),
            )
        ):
            raise SourceConflictError()
        saved: list[Path] = []
        touched = {
            relative: document.path
            for relative, document in self.source_project.files.items()
            if document.dirty and not document.read_only
        }
        touched.update(
            (relative, document.path)
            for relative, document in self.source_project.deleted_files.items()
        )
        disk_snapshot = {
            path: (path.read_bytes() if path.exists() else None)
            for path in touched.values()
        }
        document_snapshot = copy.deepcopy(self.source_project.files)
        tombstone_snapshot = copy.deepcopy(self.source_project.deleted_files)
        self._saving = True
        watched = self.file_watcher.files()
        if watched:
            self.file_watcher.removePaths(watched)
        try:
            self.source_project.refresh_program()
            for relative, document in sorted(
                self.source_project.files.items(), key=lambda item: item[0].as_posix()
            ):
                if document.read_only or not document.dirty:
                    continue
                save_python_source(document, program=self.source_project.program)
                document.is_new = False
                saved.append(relative)
            for relative, document in sorted(
                self.source_project.deleted_files.items(), key=lambda item: item[0].as_posix()
            ):
                if document.path.exists():
                    document.path.unlink()
                saved.append(relative)
            self.source_project.deleted_files.clear()
            self._pending_tombstone_external.clear()
            self.source_project.refresh_program()
            self._external_keep.clear()
            self._remember_saved_semantics()
            self.undo_stack.setClean()
        except Exception:
            for path, payload in disk_snapshot.items():
                _restore_disk_file(path, payload)
            self.source_project.files = document_snapshot
            self.source_project.deleted_files = tombstone_snapshot
            self.source_project.refresh_program()
            raise
        finally:
            self._saving = False
            self._watch_project_files()
        self.source_changed.emit()
        self.problems_changed.emit()
        self._emit_dirty()
        return tuple(saved)

    def set_build_state(self, state: str, identity: str | None = None) -> None:
        if state not in {"idle", "building", "ready", "error"}:
            raise ValueError(f"unsupported build state: {state}")
        self.build_state = state
        if identity is not None:
            self.last_build_identity = identity
        self.build_changed.emit(state)

    def set_preview_state(self, state: str) -> None:
        if state not in {
            "stopped",
            "starting",
            "running",
            "paused",
            "seeking",
            "stale",
            "stopping",
            "error",
        }:
            raise ValueError(f"unsupported preview state: {state}")
        if self.preview_state != state:
            self.preview_state = state
            self.preview_changed.emit(state)

    def append_run_log(self, text: str) -> None:
        for line in str(text).replace("\r\n", "\n").replace("\r", "\n").splitlines():
            self.run_log.append(line[:16_384])
        self.log_changed.emit()

    def reset_trace(self, run_id: str | None = None) -> None:
        self.trace_events.clear()
        self.trace_run_id = run_id
        self.preview_frame = 0
        self.trace_changed.emit()

    def append_trace(self, events, *, run_id: str | None = None) -> None:
        if run_id is not None:
            if self.trace_run_id is None:
                self.trace_run_id = run_id
            elif self.trace_run_id != run_id:
                return
        for event in events:
            if isinstance(event, dict):
                value = dict(event)
                if self.trace_run_id is not None:
                    value["run_id"] = self.trace_run_id
                self.trace_events.append(value)
        self.trace_changed.emit()

    def check_external_changes(self) -> ExternalChange:
        if self.source_project is None or self._saving:
            return ExternalChange.UNCHANGED
        changed: dict[Path, SourceDocument] = {}
        documents = [
            (False, relative, document)
            for relative, document in self.source_project.files.items()
        ]
        documents.extend(
            (True, relative, document)
            for relative, document in self.source_project.deleted_files.items()
        )
        for tombstoned, relative, document in documents:
            state, candidate = check_external_change(document)
            if state != ExternalChange.UNCHANGED:
                if state == ExternalChange.CONFLICT:
                    candidate = resolve_external_conflict(document, "reload")
                changed[relative] = candidate
                if tombstoned:
                    self._pending_tombstone_external.add(relative)
        if not changed:
            return ExternalChange.UNCHANGED

        if self.dirty or self.undo_stack.count() > 0:
            self._pending_external.update(changed)
            for relative in changed:
                document = (
                    self.source_project.deleted_files[relative]
                    if relative in self._pending_tombstone_external
                    else self.source_project.files[relative]
                )
                document.conflict = True
                document.overwrite_confirmed = False
            self.external_conflict.emit(tuple(sorted(changed, key=lambda path: path.as_posix())))
            self.source_changed.emit()
            self._emit_dirty()
            return ExternalChange.CONFLICT

        self.source_project.files.update(changed)
        self._reload_program_from_documents(clear_undo=True)
        return ExternalChange.RELOADED

    def resolve_external_changes(self, decision: str) -> ExternalChange:
        if self.source_project is None or not self._pending_external:
            raise SourceConflictError("there is no pending external change")
        pending = tuple(sorted(self._pending_external, key=lambda path: path.as_posix()))
        if decision == "reload":
            for relative in pending:
                if relative in self._pending_tombstone_external:
                    self.source_project.deleted_files.pop(relative, None)
                self.source_project.files[relative] = self._pending_external[relative]
            self._pending_external.clear()
            self._pending_tombstone_external.clear()
            self._external_keep.clear()
            self._reload_program_from_documents(clear_undo=True)
            return ExternalChange.RELOADED
        if decision == "keep":
            for relative in pending:
                document = (
                    self.source_project.deleted_files[relative]
                    if relative in self._pending_tombstone_external
                    else self.source_project.files[relative]
                )
                document.conflict = True
                resolve_external_conflict(document, "keep")
                document.dirty = True
                self._external_keep.add(relative)
            self._pending_external.clear()
            self._pending_tombstone_external.clear()
            self.source_changed.emit()
            self._emit_dirty()
            return ExternalChange.CONFLICT
        raise ValueError("decision must be 'keep' or 'reload'")

    def _apply_program(self, program: AuthoringProgram) -> None:
        if self.source_project is None:
            raise ProgramError("project_closed", "no authoring project is open")
        self.source_project.program = program.clone()
        desired_ids = {unit.id for unit in self.source_project.program.logical_units()}
        for relative, document in tuple(self.source_project.files.items()):
            if document.unit is None:
                continue
            try:
                document.unit = self.source_project.program.get_unit(document.unit.id)
            except ProgramError:
                del self.source_project.files[relative]
                if not document.is_new or document.path.exists():
                    self.source_project.deleted_files[relative] = document
        documented_ids = {
            document.unit.id
            for document in self.source_project.files.values()
            if document.unit is not None
        }
        for relative, document in tuple(self.source_project.deleted_files.items()):
            if document.unit is not None and document.unit.id in desired_ids:
                del self.source_project.deleted_files[relative]
                document.unit = self.source_project.program.get_unit(document.unit.id)
                self.source_project.files[relative] = document
                documented_ids.add(document.unit.id)
        for unit in self.source_project.program.logical_units():
            if unit.id in documented_ids:
                continue
            relative = _unit_source_path(unit)
            path = (self.source_project.root / relative).resolve()
            document = SourceDocument(
                path=path,
                raw_bytes=b"",
                text="",
                mode=SourceMode.SUPPORTED,
                unit=unit,
                module_name=".".join((*self.source_project.root.parts[-1:], *relative.with_suffix("").parts)),
                disk_digest=_empty_digest(),
                dirty=True,
                is_new=True,
            )
            self.source_project.files[relative] = document
        self._sync_dirty_flags()
        self.source_project.refresh_program()
        self.selection_changed.emit()
        self.source_changed.emit()
        self.problems_changed.emit()
        self.program_changed.emit()
        self._emit_dirty()

    def _sync_dirty_flags(self) -> None:
        if self.source_project is None:
            return
        for relative, document in self.source_project.files.items():
            if document.read_only or document.unit is None:
                continue
            saved = self._saved_semantics.get(document.unit.id)
            document.dirty = (
                relative in self._external_keep or document.unit.semantic_data() != saved
            )

    def _unit_closure(self, start_id: str) -> tuple[str, ...]:
        visited: set[str] = set()

        def visit(unit_id: str) -> None:
            if unit_id in visited:
                return
            visited.add(unit_id)
            unit = self.program.get_unit(unit_id)
            values: list[Any] = [*unit.metadata.values(), *unit.body]
            values.extend(
                parameter.default for parameter in unit.parameters if parameter.has_default
            )
            for value in values:
                for reference in _references(value):
                    target = self.program.get_unit(reference.id)
                    if target.kind not in {"Project", "Stage"}:
                        visit(target.id)

        visit(start_id)
        return tuple(sorted(visited))

    def _remember_saved_semantics(self) -> None:
        self._saved_semantics = {
            unit.id: unit.semantic_data()
            for unit in self.program.logical_units()
        } if self.source_project is not None else {}
        if self.source_project is not None:
            for document in self.source_project.files.values():
                document.dirty = False
                document.conflict = False
                document.overwrite_confirmed = False

    def _reload_program_from_documents(self, *, clear_undo: bool) -> None:
        if self.source_project is None:
            return
        previous_unit = self.current_unit_id
        previous_source = self.current_source_path
        self.source_project.refresh_program()
        if clear_undo:
            self.undo_stack.clear()
        self._remember_saved_semantics()
        unit_ids = {unit.id for unit in self.program.logical_units()}
        self.current_unit_id = previous_unit if previous_unit in unit_ids else None
        if self.current_unit_id is None and unit_ids:
            self.current_unit_id = sorted(unit_ids)[0]
        self.current_source_path = (
            previous_source
            if previous_source in self.source_project.files
            else self._path_for_unit(self.current_unit_id)
        )
        self.current_node_uid = None
        self._watch_project_files()
        self.project_changed.emit()
        self.selection_changed.emit()
        self.source_changed.emit()
        self.problems_changed.emit()
        self.program_changed.emit()
        self._emit_dirty()

    def _path_for_unit(self, unit_id: str | None) -> Path | None:
        if self.source_project is None or unit_id is None:
            return None
        for relative, document in self.source_project.files.items():
            if document.unit is not None and document.unit.id == unit_id:
                return relative
        return None

    def _require_editable_unit(self, unit_id: str) -> None:
        if self.source_project is None:
            raise SourceSaveError("project_closed", "no authoring project is open")
        document = self.source_project.file_for_unit(unit_id)
        if document.read_only:
            raise SourceSaveError("read_only", "unsupported Python is read-only")
        if document.conflict and not document.overwrite_confirmed:
            raise SourceConflictError()

    def _watch_project_files(self) -> None:
        watched = self.file_watcher.files()
        if watched:
            self.file_watcher.removePaths(watched)
        if self.source_project is None:
            return
        paths = [
            str(document.path)
            for document in (
                *self.source_project.files.values(),
                *self.source_project.deleted_files.values(),
            )
            if document.path.exists()
        ]
        if paths:
            self.file_watcher.addPaths(paths)

    def _on_file_changed(self, _path: str) -> None:
        if self._saving:
            return
        self.check_external_changes()
        self._watch_project_files()

    def _emit_dirty(self, _clean: bool | None = None) -> None:
        self.dirty_changed.emit(self.dirty)


def _references(value: Any):
    if isinstance(value, Ref):
        yield value
    elif isinstance(value, Node):
        if value.kind == "RawPython":
            return
        for item in value.arguments.values():
            yield from _references(item)
        for item in value.positional_arguments:
            yield from _references(item)
        for children in value.children.values():
            for child in children:
                yield from _references(child)
    elif isinstance(value, dict):
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
    if isinstance(value, dict):
        for item in value.values():
            yield from _resource_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _resource_values(item)


def _scan_project_assets(root: Path) -> tuple[str, ...]:
    """Scan supported project assets without entering build, cache, or archive trees."""

    root = root.resolve()
    values: list[str] = []
    for directory, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        relative_directory = current.relative_to(root)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in _IGNORED_ASSET_DIRECTORIES
            and not (
                relative_directory.parts == ("game_content",)
                and name == "generated"
            )
        )
        for file_name in sorted(file_names):
            path = current / file_name
            if path.suffix.lower() not in _ASSET_SUFFIXES or not path.is_file():
                continue
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if not _path_stays_in_root(path, root):
                continue
            values.append(f"res://{relative.as_posix()}")
    return tuple(values)


def _resource_stays_in_root(uri: str, root: Path) -> bool:
    relative = uri.removeprefix("res://").split("#", 1)[0]
    return _path_stays_in_root(root / Path(*relative.split("/")), root)


def _path_stays_in_root(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve())
    except ValueError:
        return False
    return True


_UNIT_DIRECTORIES = {
    "Stage": "stages",
    "Wave": "waves",
    "Enemy": "enemies",
    "Boss": "bosses",
    "Spell": "spells",
    "NonSpell": "spells",
    "Task": "tasks",
    "Function": "functions",
}


def _unit_source_path(unit: LogicalUnit) -> Path:
    if unit.kind == "Project":
        return Path("project.py")
    try:
        directory = _UNIT_DIRECTORIES[unit.kind]
    except KeyError as exc:
        raise ProgramError("invalid_unit", f"unsupported source unit kind {unit.kind!r}") from exc
    return Path(directory) / f"{unit.id}.py"


def _empty_digest() -> str:
    return hashlib.sha256(b"").hexdigest()


def _restore_disk_file(path: Path, payload: bytes | None) -> None:
    """Best-effort atomic rollback used only after a multi-file save failure."""

    if payload is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".rollback", dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


__all__ = ["EditorSession"]

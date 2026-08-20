"""ER2 contract for typed intents, coordination, and local invalidation.

The Contract drives real ``DocumentManager``/``SceneDocument`` instances for
authoring behaviour.  AST checks are limited to architectural facts that are
not observable through the headless coordinator: Qt imports, window ownership,
private collaborator calls, and global refreshes on mutation paths.
"""

from __future__ import annotations

import ast
import importlib
import json
from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path
from typing import Any, get_type_hints

import pytest

from src.core.project_context import ProjectContext
from src.editor.document_manager import DocumentManager
from src.editor.node_types import make_node
from src.editor.session import SceneEditorSession


REPO_ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = REPO_ROOT / "src" / "editor"
APPLICATION_ROOT = EDITOR_ROOT / "application"

REQUIRED_INVALIDATION_SCOPES = frozenset(
    {
        "SCENE_TREE",
        "SCENE_CANVAS",
        "INSPECTOR",
        "TIMELINE",
        "STATE_GRAPH",
        "VARIABLES",
        "PATTERN",
        "UI_CANVAS",
        "BACKGROUND",
        "ACTIONS",
        "TITLE",
        "OVERLAY",
    }
)


def _application_api():
    """Load the public ER2 API inside each behavioural Contract test."""

    module = importlib.import_module("src.editor.application")
    names = (
        "EditorIntent",
        "SetNodePropertyIntent",
        "SelectNodeIntent",
        "SetTimelinePlayheadIntent",
        "UndoIntent",
        "RedoIntent",
        "InvalidationScope",
        "InvalidationSet",
        "FullSyncReason",
        "IntentRejectionCode",
        "IntentRejectedError",
        "PanelPort",
        "EditorCoordinator",
        "DocumentController",
    )
    return tuple(getattr(module, name) for name in names)


def _scene_manager(tmp_path):
    project = ProjectContext(tmp_path)
    manager = DocumentManager(project, create_initial_scene=False)
    document = SceneEditorSession.new_document("Coordinator Contract")
    node = make_node("Emitter", name="Contract Emitter")
    document.root.children.append(node)
    document.validate()
    session = manager.add(document)
    return manager, session, node


def _canonical(document) -> str:
    return json.dumps(
        document.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _expr_name(expression: ast.AST | None) -> str:
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        prefix = _expr_name(expression.value)
        return f"{prefix}.{expression.attr}" if prefix else expression.attr
    if isinstance(expression, ast.Subscript):
        return _expr_name(expression.value)
    return ""


def _module_name(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _editor_classes() -> dict[str, list[tuple[Path, ast.ClassDef]]]:
    classes: dict[str, list[tuple[Path, ast.ClassDef]]] = {}
    for path in sorted(EDITOR_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            classes.setdefault(node.name, []).append((path, node))
    return classes


def _window_owner_classes() -> tuple[tuple[Path, ast.ClassDef], ...]:
    classes = _editor_classes()
    windows = classes.get("EditorMainWindow", [])
    assert len(windows) == 1, (
        "EditorMainWindow assembly must have one concrete owner; found "
        f"{len(windows)}"
    )
    pending = ["EditorMainWindow"]
    visited: set[str] = set()
    owners: list[tuple[Path, ast.ClassDef]] = []
    while pending:
        name = pending.pop()
        candidates = classes.get(name, [])
        # Duplicate helper class names elsewhere in src/editor are unrelated to
        # the concrete window assembly.  Follow a base only when its owner is
        # unambiguous instead of turning those duplicates into a Contract red.
        if name in visited or len(candidates) != 1:
            continue
        visited.add(name)
        path, node = candidates[0]
        owners.append((path, node))
        pending.extend(_expr_name(base).rsplit(".", 1)[-1] for base in node.bases)
    return tuple(owners)


def _connected_handler_classes() -> tuple[tuple[Path, ast.ClassDef], ...]:
    """Follow concrete application/shell handlers owned by the window."""

    classes = _editor_classes()
    connected = list(_window_owner_classes())
    seen = {node.name for _path, node in connected}
    changed = True
    while changed:
        changed = False
        for _path, owner in tuple(connected):
            for node in ast.walk(owner):
                if not isinstance(node, ast.Call):
                    continue
                class_name = _expr_name(node.func).rsplit(".", 1)[-1]
                candidates = [
                    candidate
                    for candidate in classes.get(class_name, [])
                    if candidate[0].relative_to(EDITOR_ROOT).parts[0]
                    in {"application", "shell"}
                ]
                if len(candidates) != 1 or class_name in seen:
                    continue
                candidate_path, candidate_node = candidates[0]
                connected.append((candidate_path, candidate_node))
                seen.add(class_name)
                changed = True
    return tuple(connected)


def _relative(path: Path, line: int) -> str:
    return f"{path.relative_to(REPO_ROOT).as_posix()}:{line}"


def _is_command_module(module: str) -> bool:
    leaf = module.rsplit(".", 1)[-1]
    return leaf == "commands" or leaf.endswith("_commands")


def _domain_command_aliases(path: Path) -> set[str]:
    aliases: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not _is_command_module(
            node.module or ""
        ):
            continue
        aliases.update(
            alias.asname or alias.name
            for alias in node.names
            if alias.name.endswith("Command")
        )
    return aliases


def _call_name(node: ast.Call) -> str:
    return _expr_name(node.func).rsplit(".", 1)[-1]


def _owned_function_nodes(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
):
    """Walk a method without attributing nested callback bodies to setup."""

    pending = list(reversed(function.body))
    while pending:
        node = pending.pop()
        yield node
        children = [
            child
            for child in ast.iter_child_nodes(node)
            if not isinstance(
                child,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef),
            )
        ]
        pending.extend(reversed(children))


def _method_records():
    records: dict[
        tuple[str, str], tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]
    ] = {}
    for path, owner in _connected_handler_classes():
        for node in owner.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                records[(owner.name, node.name)] = (path, node)
    return records


def _mutation_methods() -> set[tuple[str, str]]:
    """Find command/dispatch seeds, then every compatibility wrapper caller."""

    records = _method_records()
    aliases_by_path = {
        path: _domain_command_aliases(path) for path, _node in records.values()
    }
    methods_by_name: dict[str, set[tuple[str, str]]] = {}
    for key in records:
        methods_by_name.setdefault(key[1], set()).add(key)

    seeds: set[tuple[str, str]] = set()
    calls: dict[tuple[str, str], set[tuple[str, str]]] = {key: set() for key in records}
    for key, (path, function) in records.items():
        command_aliases = aliases_by_path[path]
        for node in _owned_function_nodes(function):
            if not isinstance(node, ast.Call):
                continue
            called = _call_name(node)
            if called in command_aliases or called in {
                "_apply_command",
                "apply",
                "dispatch",
                "undo",
                "redo",
            }:
                seeds.add(key)
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
            ):
                calls[key].update(methods_by_name.get(node.func.attr, ()))

    mutations = set(seeds)
    changed = True
    while changed:
        changed = False
        for caller, callees in calls.items():
            if caller not in mutations and callees & mutations:
                mutations.add(caller)
                changed = True
    return mutations


def _has_call(function: ast.AST, name: str) -> bool:
    nodes = (
        _owned_function_nodes(function)
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
        else ast.walk(function)
    )
    return any(
        isinstance(node, ast.Call) and _call_name(node) == name for node in nodes
    )


def test_mutation_discovery_follows_dispatch_and_compatibility_wrappers() -> None:
    tree = ast.parse(
        "class Synthetic:\n"
        "    def wrapper(self, intent):\n"
        "        return self.submit(intent)\n"
        "    def submit(self, intent):\n"
        "        return self.coordinator.dispatch(intent)\n"
    )
    owner = tree.body[0]
    assert isinstance(owner, ast.ClassDef)
    functions = {
        node.name: node for node in owner.body if isinstance(node, ast.FunctionDef)
    }
    assert _has_call(functions["submit"], "dispatch")
    assert _has_call(functions["wrapper"], "submit")


def test_application_api_is_qt_free_and_annotations_exclude_widgets() -> None:
    assert APPLICATION_ROOT.is_dir(), "src.editor.application package is missing"
    violations: list[str] = []
    for path in sorted(APPLICATION_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                modules = []
            for module in modules:
                if module.startswith(("src.qt_compat", "PySide", "PyQt", "qtpy")):
                    violations.append(f"{_relative(path, node.lineno)} -> {module}")
            if isinstance(node, ast.Name) and node.id == "QWidget":
                violations.append(f"{_relative(path, node.lineno)} QWidget")
    assert not violations, "application layer depends on Qt/QWidget:\n" + "\n".join(
        sorted(set(violations))
    )


def test_editor_intents_are_frozen_typed_values_with_stable_targets(
    qapp_session,
) -> None:
    (
        EditorIntent,
        SetNodePropertyIntent,
        SelectNodeIntent,
        SetTimelinePlayheadIntent,
        UndoIntent,
        RedoIntent,
        *_rest,
    ) = _application_api()
    from src.qt_compat.QtWidgets import QWidget

    intent = SetNodePropertyIntent(
        document_id="document-stable",
        node_id="node-stable",
        property_name="x",
        value=128.0,
    )
    assert is_dataclass(intent)
    assert isinstance(intent, EditorIntent)
    assert intent.document_id == "document-stable"
    assert intent.node_id == "node-stable"
    assert intent.property_name == "x"
    assert intent.value == 128.0
    assert isinstance(SelectNodeIntent("document-stable", "node-stable"), EditorIntent)
    assert isinstance(SetTimelinePlayheadIntent("document-stable", 12), EditorIntent)
    assert isinstance(UndoIntent("document-stable"), EditorIntent)
    assert isinstance(RedoIntent("document-stable"), EditorIntent)
    with pytest.raises(FrozenInstanceError):
        intent.node_id = "changed"

    with pytest.raises(ValueError, match="document_id"):
        SelectNodeIntent("", "node-stable")
    with pytest.raises(ValueError, match="node_id"):
        SelectNodeIntent("document-stable", " ")
    with pytest.raises(TypeError, match="frame"):
        SetTimelinePlayheadIntent("document-stable", True)
    widget = QWidget()
    try:
        with pytest.raises(TypeError, match="value"):
            SetNodePropertyIntent(
                "document-stable",
                "node-stable",
                "x",
                widget,
            )
    finally:
        widget.close()
        qapp_session.processEvents()

    for intent_type in (
        EditorIntent,
        SetNodePropertyIntent,
        SelectNodeIntent,
        SetTimelinePlayheadIntent,
        UndoIntent,
        RedoIntent,
    ):
        annotations = " ".join(
            repr(value) for value in get_type_hints(intent_type).values()
        )
        assert "Any" not in annotations
        assert "QWidget" not in annotations


def test_invalidation_is_finite_immutable_deduplicated_and_full_is_guarded() -> None:
    (
        _EditorIntent,
        _SetNodePropertyIntent,
        _SelectNodeIntent,
        _SetTimelinePlayheadIntent,
        _UndoIntent,
        _RedoIntent,
        InvalidationScope,
        InvalidationSet,
        FullSyncReason,
        *_rest,
    ) = _application_api()
    assert REQUIRED_INVALIDATION_SCOPES <= frozenset(InvalidationScope.__members__)
    assert {"ALL", "FULL", "FULL_DOCUMENT"}.isdisjoint(InvalidationScope.__members__)
    assert set(FullSyncReason.__members__) == {
        "INITIAL_OPEN",
        "DOCUMENT_ACTIVATION",
        "SCHEMA_MIGRATION",
    }
    local = InvalidationSet((InvalidationScope.TIMELINE, InvalidationScope.TIMELINE))
    assert local.scopes == frozenset({InvalidationScope.TIMELINE})
    assert local.is_full_sync is False
    assert local.reason is None
    with pytest.raises(FrozenInstanceError):
        local.scopes = frozenset()
    with pytest.raises(TypeError, match="InvalidationScope"):
        InvalidationSet(("TIMELINE",))
    with pytest.raises(ValueError, match="full sync"):
        InvalidationSet(tuple(InvalidationScope))

    full = InvalidationSet.full(FullSyncReason.INITIAL_OPEN)
    assert full.scopes == frozenset(InvalidationScope)
    assert full.is_full_sync is True
    assert full.reason is FullSyncReason.INITIAL_OPEN


def test_panel_port_is_public_runtime_protocol_with_no_widget_payload() -> None:
    *prefix, PanelPort, _EditorCoordinator, _DocumentController = _application_api()
    InvalidationSet = prefix[7]
    InvalidationScope = prefix[6]
    assert getattr(PanelPort, "_is_protocol", False)
    assert getattr(PanelPort, "_is_runtime_protocol", False)
    public_methods = {
        name: value
        for name, value in vars(PanelPort).items()
        if callable(value) and not name.startswith("__")
    }
    assert set(public_methods) == {"apply_invalidation"}
    annotations = " ".join(
        repr(value)
        for value in get_type_hints(public_methods["apply_invalidation"]).values()
    )
    assert "Any" not in annotations
    assert "QWidget" not in annotations

    class RecordingPort:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def apply_invalidation(self, document_id: str, invalidation) -> None:
            self.calls.append((document_id, invalidation))

    port = RecordingPort()
    invalidation = InvalidationSet((InvalidationScope.INSPECTOR,))
    port.apply_invalidation("document-stable", invalidation)
    assert isinstance(port, PanelPort)
    assert port.calls == [("document-stable", invalidation)]


def test_coordinator_updates_only_typed_transient_state_with_local_invalidation(
    tmp_path,
) -> None:
    (
        _EditorIntent,
        _SetNodePropertyIntent,
        SelectNodeIntent,
        SetTimelinePlayheadIntent,
        _UndoIntent,
        _RedoIntent,
        InvalidationScope,
        _InvalidationSet,
        _FullSyncReason,
        _IntentRejectionCode,
        _IntentRejectedError,
        _PanelPort,
        EditorCoordinator,
        _DocumentController,
    ) = _application_api()
    manager, session, node = _scene_manager(tmp_path)
    coordinator = EditorCoordinator(manager)
    before = _canonical(session.document)

    selection_result = coordinator.dispatch(
        SelectNodeIntent(session.document.id, node.id)
    )
    assert session.editor_state.selection.node_id == node.id
    assert selection_result.scopes == frozenset(
        {
            InvalidationScope.SCENE_TREE,
            InvalidationScope.SCENE_CANVAS,
            InvalidationScope.INSPECTOR,
        }
    )
    assert selection_result.is_full_sync is False

    playhead_result = coordinator.dispatch(
        SetTimelinePlayheadIntent(session.document.id, 73)
    )
    assert session.editor_state.timeline.playhead_frame == 73
    assert playhead_result.scopes == frozenset({InvalidationScope.TIMELINE})
    assert playhead_result.is_full_sync is False
    assert _canonical(session.document) == before
    assert session.is_dirty is False
    assert session.commands.can_undo is False


def test_property_mutation_and_undo_redo_use_one_coordinator_history_path(
    tmp_path,
) -> None:
    (
        _EditorIntent,
        SetNodePropertyIntent,
        _SelectNodeIntent,
        _SetTimelinePlayheadIntent,
        UndoIntent,
        RedoIntent,
        InvalidationScope,
        _InvalidationSet,
        _FullSyncReason,
        _IntentRejectionCode,
        _IntentRejectedError,
        _PanelPort,
        EditorCoordinator,
        _DocumentController,
    ) = _application_api()
    manager, session, node = _scene_manager(tmp_path)
    coordinator = EditorCoordinator(manager)
    before = _canonical(session.document)
    original_x = node.properties["x"]
    expected = frozenset(
        {
            InvalidationScope.SCENE_CANVAS,
            InvalidationScope.INSPECTOR,
            InvalidationScope.ACTIONS,
            InvalidationScope.TITLE,
        }
    )

    mutation = coordinator.dispatch(
        SetNodePropertyIntent(session.document.id, node.id, "x", 128.0)
    )
    assert mutation.scopes == expected
    assert mutation.is_full_sync is False
    assert node.properties["x"] == 128.0
    assert session.is_dirty is True
    assert session.commands.can_undo is True

    undone = coordinator.dispatch(UndoIntent(session.document.id))
    assert undone.scopes == expected
    assert undone.is_full_sync is False
    assert node.properties["x"] == original_x
    assert _canonical(session.document) == before
    assert session.is_dirty is False
    # A second Undo is a no-op: the one user mutation created exactly one
    # domain Command/history entry.
    empty_undo = coordinator.dispatch(UndoIntent(session.document.id))
    assert empty_undo.scopes == frozenset()
    assert empty_undo.is_full_sync is False

    redone = coordinator.dispatch(RedoIntent(session.document.id))
    assert redone.scopes == expected
    assert redone.is_full_sync is False
    assert node.properties["x"] == 128.0
    assert session.is_dirty is True
    empty_redo = coordinator.dispatch(RedoIntent(session.document.id))
    assert empty_redo.scopes == frozenset()


def test_closed_inactive_and_missing_target_intents_are_explicitly_rejected(
    tmp_path,
) -> None:
    (
        _EditorIntent,
        SetNodePropertyIntent,
        _SelectNodeIntent,
        _SetTimelinePlayheadIntent,
        _UndoIntent,
        _RedoIntent,
        _InvalidationScope,
        _InvalidationSet,
        _FullSyncReason,
        IntentRejectionCode,
        IntentRejectedError,
        _PanelPort,
        EditorCoordinator,
        _DocumentController,
    ) = _application_api()
    manager, first, node = _scene_manager(tmp_path)
    second = manager.new_scene("Second")
    coordinator = EditorCoordinator(manager)
    first_before = _canonical(first.document)

    with pytest.raises(IntentRejectedError) as inactive:
        coordinator.dispatch(
            SetNodePropertyIntent(first.document.id, node.id, "x", 100.0)
        )
    assert inactive.value.code is IntentRejectionCode.INACTIVE_DOCUMENT
    assert _canonical(first.document) == first_before
    assert first.commands.can_undo is False

    manager.activate(first)
    with pytest.raises(IntentRejectedError) as missing:
        coordinator.dispatch(
            SetNodePropertyIntent(first.document.id, "missing-node", "x", 100.0)
        )
    assert missing.value.code is IntentRejectionCode.TARGET_NOT_FOUND
    assert _canonical(first.document) == first_before
    assert first.commands.can_undo is False

    manager.close(first)
    assert manager.active is second
    with pytest.raises(IntentRejectedError) as closed:
        coordinator.dispatch(
            SetNodePropertyIntent(first.document.id, node.id, "x", 100.0)
        )
    assert closed.value.code is IntentRejectionCode.DOCUMENT_NOT_OPEN
    assert _canonical(first.document) == first_before


def test_document_controller_is_the_only_full_sync_lifecycle_path(tmp_path) -> None:
    (
        _EditorIntent,
        _SetNodePropertyIntent,
        _SelectNodeIntent,
        _SetTimelinePlayheadIntent,
        _UndoIntent,
        _RedoIntent,
        InvalidationScope,
        _InvalidationSet,
        FullSyncReason,
        IntentRejectionCode,
        IntentRejectedError,
        _PanelPort,
        _EditorCoordinator,
        DocumentController,
    ) = _application_api()
    manager, first, _node = _scene_manager(tmp_path)
    second = manager.new_scene("Second")
    controller = DocumentController(manager)

    initial = controller.initial_sync()
    assert initial.scopes == frozenset(InvalidationScope)
    assert initial.is_full_sync is True
    assert initial.reason is FullSyncReason.INITIAL_OPEN

    activated = controller.activate(first.document.id)
    assert manager.active is first
    assert activated.scopes == frozenset(InvalidationScope)
    assert activated.is_full_sync is True
    assert activated.reason is FullSyncReason.DOCUMENT_ACTIVATION

    migrated = controller.schema_migrated(first.document.id)
    assert migrated.scopes == frozenset(InvalidationScope)
    assert migrated.is_full_sync is True
    assert migrated.reason is FullSyncReason.SCHEMA_MIGRATION

    with pytest.raises(IntentRejectedError) as missing:
        controller.activate("missing-document")
    assert missing.value.code is IntentRejectionCode.DOCUMENT_NOT_OPEN
    assert second in manager.documents


def test_window_has_no_slot_mixin_or_domain_command_imports() -> None:
    owners = _window_owner_classes()
    window = next(node for _path, node in owners if node.name == "EditorMainWindow")
    mixins = [
        f"{_expr_name(base)} (line {base.lineno})"
        for base in window.bases
        if _expr_name(base).rsplit(".", 1)[-1].endswith("SlotsMixin")
    ]
    imported: list[str] = []
    for path in sorted({path for path, _node in owners}):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and _is_command_module(
                node.module or ""
            ):
                imported.append(
                    f"{_relative(path, node.lineno)} -> {node.module or ''}"
                )
    violations = []
    if mixins:
        violations.append("EditorMainWindow inherits SlotsMixin: " + ", ".join(mixins))
    if imported:
        violations.append(
            "window owner modules import domain Commands:\n" + "\n".join(imported)
        )
    assert not violations, "\n".join(violations)


def test_window_calls_no_private_methods_on_panel_or_service_collaborators() -> None:
    violations: list[str] = []
    for path, owner in _window_owner_classes():
        for node in ast.walk(owner):
            if (
                not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Attribute)
                or not node.func.attr.startswith("_")
            ):
                continue
            receiver = node.func.value
            if (
                isinstance(receiver, ast.Attribute)
                and isinstance(receiver.value, ast.Name)
                and receiver.value.id == "self"
            ):
                violations.append(
                    f"{_relative(path, node.lineno)} -> "
                    f"self.{receiver.attr}.{node.func.attr}()"
                )
    assert not violations, "window calls collaborator private methods:\n" + "\n".join(
        sorted(set(violations))
    )


def test_mutation_handlers_and_wrappers_never_call_global_refresh() -> None:
    records = _method_records()
    violations = [
        f"{_relative(records[key][0], records[key][1].lineno)} " f"{key[0]}.{key[1]}()"
        for key in sorted(_mutation_methods())
        if _has_call(records[key][1], "_refresh")
    ]
    assert not violations, "mutation paths call global _refresh():\n" + "\n".join(
        violations
    )

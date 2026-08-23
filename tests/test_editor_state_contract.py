"""ER1 contract for typed, document-local editor state.

The editor historically stored the values below in ``ManagedDocument`` fields
and an untyped ``editor_context`` dictionary.  ER1 keeps their observable
authoring behaviour while assigning every value to one typed owner.  Runtime
feedback is deliberately separate: it is a read-only preview snapshot, not a
document view and never part of authoring serialization.
"""

from __future__ import annotations

import ast
import importlib
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path
from typing import get_type_hints

import pytest

from src.core.project_context import ProjectContext
from src.editor import AddNodeCommand, DocumentManager, RemoveNodeCommand, make_node


REPO_ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = REPO_ROOT / "src" / "editor"


# This is the complete inventory observed before ER1: 18 document-local
# selection/view values and four preview-owned overlay values.  The earlier
# roadmap prose counted 21, but omitting the subsequently observed ui_viewport
# key would silently discard real editor behaviour.  Keeping the mapping in the
# Contract makes every migration decision reviewable without preserving a
# runtime string-key compatibility layer.
LEGACY_DOCUMENT_STATE_MAPPINGS = {
    "background_selected_layer": "background_selected_layer",
    "graph_mode": "pattern.graph_mode",
    "pattern_authoring_level": "pattern.authoring_level",
    "player_position": "pattern.player_position",
    "preset_mode": "pattern.preset_mode",
    "reactive_navigation": "timeline.reactive_navigation",
    "runtime_source_path": "pattern.runtime_source_path",
    "selected_binding_id": "selection.binding_id",
    "selected_clip_id": "selection.clip_id",
    "selected_graph_node_id": "selection.graph_node_id",
    "selected_state_id": "selection.state_id",
    "selected_track_id": "selection.track_id",
    "selected_ui_node_id": "selection.ui_node_id",
    "timeline_playhead": "timeline.playhead_frame",
    "timeline_playheads_by_state": "timeline.playheads_by_state",
    "timeline_zoom": "timeline.zoom",
    "ui_viewport": "ui_viewport",
    "variable_binding_candidates": "selection.binding_candidate_ids",
}

LEGACY_OVERLAY_MAPPINGS = {
    "timeline_active_clips": "active_clip_ids",
    "runtime_state_path": "state_path",
    "runtime_variables": "variable_snapshot",
    "reactive_overlay": "reactive_overlay",
}

LEGACY_CONTEXT_KEYS = frozenset(
    (*LEGACY_DOCUMENT_STATE_MAPPINGS, *LEGACY_OVERLAY_MAPPINGS)
)


def _state_api():
    """Load the ER1 public API inside each behavioural test.

    Keeping this out of module scope lets the initial Contract collect and
    report each missing behaviour instead of collapsing into one import error.
    """

    module = importlib.import_module("src.editor.state")
    return tuple(
        getattr(module, name)
        for name in (
            "SelectionState",
            "TimelineViewState",
            "PatternViewState",
            "DocumentEditorState",
            "RuntimeOverlayState",
        )
    )


def _editor_python_files() -> tuple[Path, ...]:
    return tuple(sorted(EDITOR_ROOT.rglob("*.py")))


def _relative(path: Path, line: int) -> str:
    return f"{path.relative_to(REPO_ROOT).as_posix()}:{line}"


def _legacy_state_references() -> tuple[str, ...]:
    violations: list[str] = []
    for path in _editor_python_files():
        typed_state_module = EDITOR_ROOT / "state" in path.parents
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "editor_context":
                violations.append(f"{_relative(path, node.lineno)} editor_context")
            elif (
                not typed_state_module
                and isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in LEGACY_CONTEXT_KEYS
            ):
                violations.append(f"{_relative(path, node.lineno)} {node.value!r}")
    return tuple(sorted(set(violations)))


def _window(tmp_path):
    # Importing the Qt shell only in the two ownership tests keeps the
    # headless document-state tests focused on their actual boundary.
    from src.editor.app import EditorMainWindow

    return EditorMainWindow(ProjectContext(tmp_path))


class _Signal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def disconnect(self, callback) -> None:
        self._callbacks.remove(callback)

    def emit(self, value) -> None:
        for callback in tuple(self._callbacks):
            callback(value)


class _FormalClient:
    def __init__(self) -> None:
        self.runningChanged = _Signal()
        self.is_running = False

    def start(self) -> bool:
        self.is_running = True
        self.runningChanged.emit(True)
        return True

    def stop(self) -> None:
        self.is_running = False
        self.runningChanged.emit(False)


def _send_stage_feedback(window, session, *, frame: int) -> None:
    """Drive feedback through PreviewSession's owner/identity boundary."""

    if window._preview_session.active_document_id != session.document.id:
        window._pattern_preview_client = _FormalClient()
        assert window._preview_session.start_formal(
            document_id=session.document.id,
            resource_id=f"unsaved://{session.document.id}",
        )
    window.preview_service._handle_pattern_preview_event(
        {
            "protocol_version": 1,
            "request_id": None,
            "event": "statistics",
            "payload": {
                "mode": "stage",
                "state": "playing",
                "resource_id": session.document.id,
                "frame": frame,
                "active_clips": ["clip-runtime"],
                "state_path": ["state-runtime"],
                "variable_snapshot": {"stage": {"score": 7}},
                "reactive_overlay": {
                    "active_instances": ["reaction-runtime"],
                    "trace": [],
                    "diagnostics": [],
                },
            },
        }
    )


def test_legacy_inventory_freezes_all_22_observed_migrations() -> None:
    assert len(LEGACY_DOCUMENT_STATE_MAPPINGS) == 18
    assert len(LEGACY_OVERLAY_MAPPINGS) == 4
    assert len(LEGACY_CONTEXT_KEYS) == 22
    assert len(set(LEGACY_DOCUMENT_STATE_MAPPINGS.values())) == 18
    assert len(set(LEGACY_OVERLAY_MAPPINGS.values())) == 4


def test_production_has_no_untyped_context_or_exact_legacy_keys() -> None:
    violations = _legacy_state_references()
    assert not violations, "legacy editor state references remain:\n" + "\n".join(
        violations
    )


def test_state_types_are_dataclasses_with_independent_typed_defaults() -> None:
    (
        SelectionState,
        TimelineViewState,
        PatternViewState,
        DocumentEditorState,
        RuntimeOverlayState,
    ) = _state_api()

    assert all(
        is_dataclass(item)
        for item in (
            SelectionState,
            TimelineViewState,
            PatternViewState,
            DocumentEditorState,
            RuntimeOverlayState,
        )
    )
    first = DocumentEditorState()
    second = DocumentEditorState()
    assert first.selection is not second.selection
    assert first.timeline is not second.timeline
    assert first.pattern is not second.pattern
    assert first.selection == SelectionState()
    assert first.timeline == TimelineViewState()
    assert first.pattern == PatternViewState()
    assert first.timeline.playhead_frame == 0
    assert first.timeline.zoom == 0.25
    assert first.pattern.player_position == (0.0, -0.8)
    assert first.pattern.authoring_level == "l0"
    assert first.background_selected_layer == 0
    assert first.ui_viewport is None


@pytest.mark.parametrize(
    "case",
    (
        "selection-construction",
        "selection-assignment",
        "timeline-construction",
        "timeline-assignment",
        "pattern-construction",
        "pattern-assignment",
        "document-construction",
        "document-assignment",
        "overlay-construction",
    ),
)
def test_state_rejects_wrong_types_at_construction_and_assignment(case: str) -> None:
    (
        SelectionState,
        TimelineViewState,
        PatternViewState,
        DocumentEditorState,
        RuntimeOverlayState,
    ) = _state_api()

    if case == "selection-construction":
        with pytest.raises(TypeError, match="node_id"):
            SelectionState(node_id=17)
    elif case == "selection-assignment":
        value = SelectionState()
        with pytest.raises(TypeError, match="binding_candidate_ids"):
            value.binding_candidate_ids = ["variable"]
    elif case == "timeline-construction":
        with pytest.raises(TypeError, match="playhead_frame"):
            TimelineViewState(playhead_frame=True)
    elif case == "timeline-assignment":
        value = TimelineViewState()
        with pytest.raises(TypeError, match="playheads_by_state"):
            value.playheads_by_state = {"state": False}
    elif case == "pattern-construction":
        with pytest.raises(TypeError, match="player_position"):
            PatternViewState(player_position=[0.0, -0.8])
    elif case == "pattern-assignment":
        value = PatternViewState()
        with pytest.raises(TypeError, match="graph_mode"):
            value.graph_mode = 1
    elif case == "document-construction":
        with pytest.raises(TypeError, match="selection"):
            DocumentEditorState(selection={})
    elif case == "document-assignment":
        value = DocumentEditorState()
        with pytest.raises(TypeError, match="ui_viewport"):
            value.ui_viewport = (384.0, 448.0)
    else:
        with pytest.raises(TypeError, match="frame"):
            RuntimeOverlayState(document_id="scene", frame=True)


@pytest.mark.parametrize(
    "factory, expected_field",
    (
        (lambda api: api[1](playhead_frame=-1), "playhead_frame"),
        (lambda api: api[1](zoom=0.0), "zoom"),
        (lambda api: api[2](authoring_level="internal"), "authoring_level"),
        (lambda api: api[3](ui_viewport=(0, 448)), "ui_viewport"),
        (lambda api: api[4](document_id="", frame=0), "document_id"),
        (lambda api: api[4](document_id="scene", frame=-1), "frame"),
    ),
)
def test_state_rejects_invalid_domain_values(factory, expected_field: str) -> None:
    with pytest.raises(ValueError, match=expected_field):
        factory(_state_api())


def test_managed_document_owns_exactly_one_document_editor_state() -> None:
    *_, DocumentEditorState, RuntimeOverlayState = _state_api()
    from src.editor.document_manager import ManagedDocument

    state_fields = {item.name: item for item in fields(ManagedDocument)}
    assert "editor_state" in state_fields
    assert {"selected_id", "selected_resource", "editor_context"}.isdisjoint(
        state_fields
    )
    hints = get_type_hints(ManagedDocument)
    assert hints["editor_state"] is DocumentEditorState
    assert RuntimeOverlayState not in hints.values()
    temporary_fields = {
        name
        for name in state_fields
        if name == "editor_state"
        or any(
            token in name.casefold()
            for token in ("context", "overlay", "playhead", "select", "view", "zoom")
        )
    }
    assert temporary_fields == {"editor_state"}


def test_two_real_documents_isolate_selection_playhead_and_views(tmp_path) -> None:
    (
        _SelectionState,
        _TimelineViewState,
        _PatternViewState,
        DocumentEditorState,
        _Overlay,
    ) = _state_api()
    manager = DocumentManager(ProjectContext(tmp_path))
    first = manager.active
    assert first is not None
    second = manager.new_scene("Second")

    first.editor_state.selection.resource_uri = "res://assets/first.png"
    first.editor_state.timeline.playhead_frame = 42
    first.editor_state.timeline.zoom = 0.5
    first.editor_state.pattern.player_position = (0.25, -0.5)

    assert second.editor_state.selection.node_id == second.document.root.id
    assert second.editor_state.selection.resource_uri is None
    assert second.editor_state.timeline == DocumentEditorState().timeline
    assert second.editor_state.pattern == DocumentEditorState().pattern
    second.editor_state.selection.resource_uri = "res://assets/second.png"
    second.editor_state.timeline.playhead_frame = 9
    second.editor_state.timeline.zoom = 1.0
    second.editor_state.pattern.player_position = (-0.25, 0.5)

    manager.activate(first)
    assert first.editor_state.selection.resource_uri == "res://assets/first.png"
    assert first.editor_state.timeline.playhead_frame == 42
    assert first.editor_state.timeline.zoom == 0.5
    assert first.editor_state.pattern.player_position == (0.25, -0.5)
    manager.activate(second)
    assert second.editor_state.selection.resource_uri == "res://assets/second.png"
    assert second.editor_state.timeline.playhead_frame == 9
    assert second.editor_state.timeline.zoom == 1.0
    assert second.editor_state.pattern.player_position == (-0.25, 0.5)


def test_deleting_selected_scene_node_corrects_selection_without_touching_history(
    tmp_path,
) -> None:
    _state_api()
    manager = DocumentManager(ProjectContext(tmp_path))
    session = manager.active
    assert session is not None
    root = session.document.root
    child = make_node("Emitter")
    session.apply(AddNodeCommand(root, root.id, child))
    session.editor_state.selection.node_id = child.id
    undo_label = session.commands.undo_label

    session.apply(RemoveNodeCommand(root, child.id))

    assert session.editor_state.selection.node_id == root.id
    assert session.commands.undo_label != undo_label
    assert session.commands.can_undo
    assert session.undo()
    assert session.node(child.id) is child
    # Undo restores authoring data; it must not resurrect a stale transient
    # selection that was corrected when the target disappeared.
    assert session.editor_state.selection.node_id == root.id


def test_editor_state_never_changes_dirty_canonical_json_or_command_history(
    tmp_path,
) -> None:
    _state_api()
    manager = DocumentManager(ProjectContext(tmp_path))
    session = manager.active
    assert session is not None
    target = manager.save(session, "game_content/scenes/state-contract.pystg.json")
    canonical_before = target.read_bytes()
    payload_before = session.document.to_dict()

    session.editor_state.selection.resource_uri = "res://assets/bullets.json#ball"
    session.editor_state.selection.state_id = (
        session.document.state_graph.initial_state_id
    )
    session.editor_state.timeline.playhead_frame = 73
    session.editor_state.timeline.zoom = 0.75
    session.editor_state.timeline.playheads_by_state = {
        session.document.state_graph.initial_state_id: 73
    }
    session.editor_state.timeline.reactive_navigation = (
        "reaction",
        "reaction-resource",
    )
    session.editor_state.pattern.preset_mode = True
    session.editor_state.pattern.player_position = (0.125, -0.625)
    session.editor_state.background_selected_layer = 2
    session.editor_state.ui_viewport = (384, 448)

    assert session.document.to_dict() == payload_before
    assert not session.is_dirty
    assert not session.commands.can_undo
    manager.save(session)
    assert target.read_bytes() == canonical_before


def test_runtime_overlay_is_an_immutable_recursive_snapshot() -> None:
    *_, RuntimeOverlayState = _state_api()
    variables = {"stage": {"score": 7}}
    reactive = {
        "active_instances": ["reaction-runtime"],
        "trace": [{"instance_id": "reaction-runtime", "frame": 12}],
        "diagnostics": [],
    }
    overlay = RuntimeOverlayState(
        document_id="scene",
        frame=12,
        active_clip_ids=("clip-runtime",),
        state_path=("state-runtime",),
        variable_snapshot=variables,
        reactive_overlay=reactive,
    )
    variables["stage"]["score"] = 99
    reactive["active_instances"].append("late-mutation")

    assert overlay.variable_snapshot["stage"]["score"] == 7
    assert overlay.reactive_overlay["active_instances"] == ("reaction-runtime",)
    assert isinstance(overlay.variable_snapshot, Mapping)
    assert isinstance(overlay.variable_snapshot["stage"], Mapping)
    with pytest.raises(TypeError):
        overlay.variable_snapshot["stage"]["score"] = 8
    with pytest.raises(FrozenInstanceError):
        overlay.frame = 13


def test_preview_feedback_and_stop_clear_only_overlay_not_document_view(
    tmp_path, qapp_session
) -> None:
    del qapp_session
    *_, RuntimeOverlayState = _state_api()
    window = _window(tmp_path)
    session = window.document_manager.active
    assert session is not None
    session.editor_state.timeline.playhead_frame = 73

    _send_stage_feedback(window, session, frame=120)

    assert isinstance(window.runtime_overlay, RuntimeOverlayState)
    assert window.runtime_overlay.document_id == session.document.id
    assert window.runtime_overlay.frame == 120
    assert window.runtime_overlay.active_clip_ids == ("clip-runtime",)
    assert session.editor_state.timeline.playhead_frame == 73
    with pytest.raises(AttributeError):
        window.runtime_overlay = RuntimeOverlayState(
            document_id=session.document.id,
            frame=999,
        )

    window.preview_service._handle_pattern_preview_event(
        {
            "protocol_version": 1,
            "request_id": None,
            "event": "status",
            "payload": {
                "mode": "stage",
                "state": "stopped",
                "resource_id": session.document.id,
                "frame": 0,
            },
        }
    )
    assert window.runtime_overlay is None
    assert session.editor_state.timeline.playhead_frame == 73

    _send_stage_feedback(window, session, frame=121)
    window.preview_service._preview_running_changed(False)
    assert window.runtime_overlay is None
    assert session.editor_state.timeline.playhead_frame == 73
    window.close()


def test_closing_preview_owner_clears_overlay_and_document_state_ownership(
    tmp_path, qapp_session
) -> None:
    del qapp_session
    *_, DocumentEditorState, _RuntimeOverlayState = _state_api()
    window = _window(tmp_path)
    session = window.document_manager.active
    assert session is not None
    session.editor_state.timeline.playhead_frame = 31
    session.editor_state.selection.resource_uri = "res://assets/selected.png"
    _send_stage_feedback(window, session, frame=120)
    assert window.runtime_overlay is not None

    window.document_service.close_active_document()

    assert session not in window.document_manager.documents
    assert session.editor_state == DocumentEditorState()
    assert window.runtime_overlay is None
    assert window._preview_session.active_document_id is None
    window.close()

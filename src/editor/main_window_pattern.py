"""Pattern shell adapters for typed coordinator intents and preview effects."""

from __future__ import annotations

from src.pattern import PatternDocument

from .application import (
    IntentRejectedError,
    InvalidationScope,
    InvalidationSet,
    PatternAction,
    PatternIntent,
)
from .panels.pattern_workspace import PatternWorkspace
from .shell import WindowService
from .shell.ports import PatternPort


class PatternService(WindowService[PatternPort]):
    def _submit_pattern_intent(
        self,
        intent: PatternIntent,
        *,
        label: str = "",
        sync_preview: bool = False,
    ) -> bool:
        # Tests and plugin adapters may replace the active resolver after the
        # window is assembled.  Keep the Qt-free coordinator pointed at the
        # window's one current resolver instead of a stale construction-time
        # instance.
        self.port.editor_coordinator.preset_resolver = self.port._preset_resolver
        try:
            invalidation = self.port.editor_coordinator.dispatch(intent)
        except (IntentRejectedError, ValueError) as exc:
            issue_code = (
                "invalid_graph_edit"
                if "GRAPH" in intent.action.name
                else "invalid_pattern_edit"
            )
            self.port.preview_panel.handle_issue(
                {"code": issue_code, "message": str(exc)}
            )
            self.port._log(f"[pattern-edit:error] {exc}")
            # A form control can already contain the rejected value when its
            # signal reaches this adapter.  Rebind only the Pattern/Inspector
            # consumers so the UI returns to the authoritative document value
            # without a global refresh or a compensating Command.
            self.port.apply_invalidation(
                intent.document_id,
                InvalidationSet(
                    (InvalidationScope.PATTERN, InvalidationScope.INSPECTOR)
                ),
            )
            return False
        if invalidation.scopes:
            self.port.apply_invalidation(intent.document_id, invalidation)
            if label:
                self.port._log(label)
            if sync_preview:
                self.port.preview_service.sync_active_pattern_preview()
        self.port._active_pattern_document = self.port.session.document
        return bool(invalidation.scopes)

    def new_pattern(self) -> None:
        session, invalidation = self.port.document_controller.new_pattern()
        self.port.document_service.add_document_tab(session)
        self.port._active_pattern_session = session
        self.port._active_pattern_document = session.document
        self.port._active_pattern_resource = ""
        self.port._log("New Pattern")
        self.port.apply_invalidation(session.document.id, invalidation)

    def pattern_property_requested(self, path: str, value) -> None:
        if not path or not isinstance(self.port.session.document, PatternDocument):
            return
        changed = self.apply_pattern_properties(
            {str(path): value},
            f"Set {path}",
        )
        if not changed:
            return
        if not self.port._pattern_preview_client.is_running:
            self.port.preview_service.launch_active_pattern_preview()
        else:
            request_id = self.port._pattern_preview_client.send_command(
                "set-property", {"path": path, "value": value}
            )
            self.port._preview_session.record_pending_property(request_id, str(path), value)

    def graph_mode_changed(self, mode: str) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.SET_MODE,
                target_id=str(mode),
            )
        )

    def pattern_level_requested(self, level: str) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.SET_LEVEL,
                target_id=str(level),
            ),
            label=f"Set authoring level {level}",
            sync_preview=True,
        )

    def pattern_binding_requested(self, path: str, kind: str, value) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.SET_BINDING,
                target_id=str(path),
                related_id=str(kind),
                value=value,
            ),
            label=f"Set {path} binding",
            sync_preview=True,
        )

    def pattern_binding_remove_requested(self, path: str) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.REMOVE_BINDING,
                target_id=str(path),
            ),
            label=f"Remove {path} binding",
            sync_preview=True,
        )

    def pattern_source_navigate_requested(self, resource_uri: str) -> None:
        if self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.SET_SOURCE_PATH,
                target_id=str(resource_uri),
            )
        ):
            self.port._log(
                f"Runtime source: {self.port.session.editor_state.pattern.runtime_source_path}"
            )

    def graph_expand_requested(self) -> None:
        self._submit_pattern_intent(
            PatternIntent(self.port.session.document.id, PatternAction.EXPAND_GRAPH),
            label="Expand pattern to graph",
            sync_preview=True,
        )

    def graph_fold_requested(self) -> None:
        self._submit_pattern_intent(
            PatternIntent(self.port.session.document.id, PatternAction.FOLD_GRAPH),
            label="Fold back to recipe",
            sync_preview=True,
        )

    def graph_node_selected(self, node_id: str) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.SELECT_GRAPH_NODE,
                target_id=str(node_id),
            )
        )

    def graph_node_property_requested(self, node_id: str, properties) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.SET_GRAPH_NODE_PROPERTIES,
                target_id=str(node_id),
                values=dict(properties),
            ),
            label="Set graph node property",
            sync_preview=True,
        )

    def graph_node_position_requested(self, node_id: str, x: float, y: float) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.MOVE_GRAPH_NODE,
                target_id=str(node_id),
                x=float(x),
                y=float(y),
            ),
            label="Move graph node",
            sync_preview=True,
        )

    def graph_node_create_requested(self, category: str, node_type: str) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.ADD_GRAPH_NODE,
                target_id=str(category),
                related_id=str(node_type),
            ),
            label=f"Add {category} node",
            sync_preview=True,
        )

    def graph_edge_requested(self, from_id: str, to_id: str) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.ADD_GRAPH_EDGE,
                target_id=str(from_id),
                related_id=str(to_id),
            ),
            label="Connect graph nodes",
            sync_preview=True,
        )

    def graph_node_remove_requested(self, node_id: str) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.REMOVE_GRAPH_NODE,
                target_id=str(node_id),
            ),
            label="Remove graph node",
            sync_preview=True,
        )

    def graph_edge_remove_requested(self, edge_id: str) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.REMOVE_GRAPH_EDGE,
                target_id=str(edge_id),
            ),
            label="Remove graph edge",
            sync_preview=True,
        )

    def apply_graph_diagnostics(self, diagnostics) -> None:
        node_ids: list[str] = []
        edge_ids: list[str] = []
        for item in diagnostics or ():
            prefix, separator, rest = str(item.get("path") or "").partition(":")
            if not separator:
                continue
            object_id = rest.split(":", 1)[0]
            if prefix == "graph.node":
                node_ids.append(object_id)
            elif prefix == "graph.edge":
                edge_ids.append(object_id)
        session = self.port.document_manager.active
        widget = (
            self.port._document_widgets.get(session.document.id)
            if session is not None
            else None
        )
        if (node_ids or edge_ids) and isinstance(widget, PatternWorkspace) and widget.mode() == "graph":
            widget.set_graph_diagnostics(tuple(node_ids), tuple(edge_ids))

    def clear_graph_diagnostics(self) -> None:
        session = self.port.document_manager.active
        widget = (
            self.port._document_widgets.get(session.document.id)
            if session is not None
            else None
        )
        if isinstance(widget, PatternWorkspace):
            widget.clear_graph_diagnostics()

    def apply_pattern_properties(
        self,
        values: dict[str, object],
        label: str,
    ) -> bool:
        return self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.SET_PROPERTIES,
                target_id=str(label),
                values=dict(values),
            ),
            label=label,
        )

    def apply_pattern_template(self, template: str) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.APPLY_TEMPLATE,
                target_id=str(template),
            ),
            label=f"Apply {template}",
            sync_preview=True,
        )

    def preset_parameter_requested(self, parameter_id: str, value) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.SET_PRESET_PARAMETER,
                target_id=str(parameter_id),
                value=value,
            ),
            label=f"Set preset parameter {parameter_id}",
            sync_preview=True,
        )

    def preset_slot_requested(self, slot_id: str, value) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.SET_PRESET_SLOT,
                target_id=str(slot_id),
                value=value,
            ),
            label=f"Set preset slot {slot_id}",
            sync_preview=True,
        )

    def preset_migrate_requested(self, target_version: str) -> None:
        self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.MIGRATE_PRESET,
                target_id=str(target_version),
            ),
            label=f"Migrate preset to {target_version}",
            sync_preview=True,
        )

    def preset_materialize_requested(self) -> None:
        self._submit_pattern_intent(
            PatternIntent(self.port.session.document.id, PatternAction.MATERIALIZE_PRESET),
            label="Make preset local",
            sync_preview=True,
        )

    def pattern_origin_requested(self, x: float, y: float) -> None:
        if self.apply_pattern_properties(
            {"shape.origin_x": float(x), "shape.origin_y": float(y)},
            "Move Pattern emitter",
        ):
            self.port.preview_service.sync_active_pattern_preview()

    def pattern_player_requested(self, x: float, y: float) -> None:
        if self._submit_pattern_intent(
            PatternIntent(
                self.port.session.document.id,
                PatternAction.SET_PLAYER_POSITION,
                x=float(x),
                y=float(y),
            )
        ):
            self.port.preview_service.send_pattern_preview_command(
                "set-player-position", {"x": float(x), "y": float(y)}
            )


__all__ = ["PatternService"]

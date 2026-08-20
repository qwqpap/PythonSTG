"""Pattern authoring slots: properties, node graph, bindings and presets."""

from __future__ import annotations

from src.pattern import BindingSpec, PatternDocument
from .pattern_commands import (
    RemovePatternBindingCommand,
    SetPatternBindingCommand,
    SetPatternPropertyCommand,
    pattern_with_property,
)
from .pattern_workspace import PatternWorkspace
from .graph_commands import (
    AddGraphEdgeCommand,
    AddGraphNodeCommand,
    ExpandToGraphCommand,
    FoldBackToRecipeCommand,
    RemoveGraphEdgeCommand,
    RemoveGraphNodeCommand,
    SetGraphNodePositionCommand,
    SetGraphNodePropertiesCommand,
)
from .preset_commands import (
    ApplyPresetCommand,
    ApplyPresetMigrationCommand,
    MaterializePresetCommand,
    SetPresetOverrideCommand,
    SetPresetSlotOverrideCommand,
)
from .progressive_authoring import authoring_level
from .shell import WindowService


class PatternService(WindowService):
    """Pattern authoring slots: properties, node graph, bindings and presets.

    These slots stay bound to the window instance instead of moving into a
    controller object: every attribute they touch is owned by
    ``EditorMainWindow``, and the editor tests plus the three native gates drive
    these methods by name.  Mix in before the Qt base class, the same way
    ``SpaceTapSearchMixin`` is used by ``SceneViewport``.
    """

    def new_pattern(self) -> None:
        session = self.document_manager.new_pattern()
        self._add_document_tab(session)
        self._active_pattern_session = session
        self._active_pattern_document = session.document
        self._active_pattern_resource = ""
        self._log("New Pattern")
        self._refresh()

    def _pattern_property_requested(self, path: str, value) -> None:
        session = self._active_pattern_session
        if session is None or not isinstance(session.document, PatternDocument):
            self.preview_panel.handle_issue(
                {"code": "no_pattern", "message": "Select a Pattern resource first"}
            )
            return
        if not path:
            return
        if not self._apply_pattern_properties({str(path): value}, f"Set {path}"):
            if self._pattern_preview_client.is_running:
                request_id = self._pattern_preview_client.send_command(
                    "set-property",
                    {"path": path, "value": value},
                )
                self._preview_pending_properties[request_id] = (str(path), value)
            return
        if not self._pattern_preview_client.is_running:
            self._launch_active_pattern_preview()
        elif self._pattern_preview_client.is_running:
            request_id = self._pattern_preview_client.send_command(
                "set-property",
                {"path": path, "value": value},
            )
            self._preview_pending_properties[request_id] = (str(path), value)

    @staticmethod
    def _pattern_with_property(
        document: PatternDocument,
        path: str,
        value,
    ) -> PatternDocument:
        return pattern_with_property(document, path, value)

    def _apply_graph_command(self, command, label: str) -> bool:
        session = self._active_pattern_session
        if session is None or not isinstance(session.document, PatternDocument):
            return False
        try:
            session.apply(command)
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_graph_edit", "message": str(exc)}
            )
            self._log(f"[graph-edit:error] {exc}")
            self._refresh()
            return False
        self._active_pattern_document = session.document
        self._log(label)
        self._refresh()
        self._sync_active_pattern_preview()
        return True

    def _graph_mode_changed(self, mode: str) -> None:
        session = self._active_pattern_session
        if session is None:
            return
        mode = str(mode)
        session.editor_state.pattern.preset_mode = mode == "preset"
        if mode == "graph":
            session.editor_state.pattern.graph_mode = True
            session.editor_state.pattern.authoring_level = "l3"
        else:
            session.editor_state.pattern.graph_mode = False
            session.editor_state.selection.graph_node_id = None
            session.editor_state.pattern.authoring_level = (
                "l0" if mode == "preset" else "l1"
            )
        self._refresh()

    def _pattern_level_requested(self, level: str) -> None:
        session = self._active_pattern_session
        if session is None or not isinstance(session.document, PatternDocument):
            return
        authoring_level(level)
        session.editor_state.pattern.authoring_level = level
        session.editor_state.pattern.preset_mode = level == "l0"
        session.editor_state.pattern.graph_mode = level == "l3"
        if level == "l3" and session.document.graph is None:
            self._graph_expand_requested()
            return
        self._refresh()

    def _pattern_binding_requested(self, path: str, kind: str, value) -> None:
        self._apply_graph_command(
            SetPatternBindingCommand(
                self._active_pattern_document,
                BindingSpec(str(path), str(kind), value),
            ),
            f"Set {path} binding",
        )

    def _pattern_binding_remove_requested(self, path: str) -> None:
        self._apply_graph_command(
            RemovePatternBindingCommand(
                self._active_pattern_document,
                str(path),
            ),
            f"Remove {path} binding",
        )

    def _pattern_source_navigate_requested(self, resource_uri: str) -> None:
        reference = str(resource_uri)
        try:
            path = self.project.resolve(reference, must_exist=True)
        except Exception as exc:
            self._show_error("Open Runtime source failed", exc)
            return
        self.session.editor_state.pattern.runtime_source_path = str(path)
        self._log(f"Runtime source: {path}")

    def _graph_expand_requested(self) -> None:
        session = self._active_pattern_session
        if session is None:
            return
        session.editor_state.pattern.graph_mode = True
        session.editor_state.pattern.authoring_level = "l3"
        if self._apply_graph_command(
            ExpandToGraphCommand(session.document),
            "Expand pattern to graph",
        ):
            pass

    def _graph_fold_requested(self) -> None:
        session = self._active_pattern_session
        if session is None:
            return
        session.editor_state.pattern.graph_mode = False
        session.editor_state.pattern.authoring_level = "l1"
        session.editor_state.selection.graph_node_id = None
        if self._apply_graph_command(
            FoldBackToRecipeCommand(session.document),
            "Fold back to recipe",
        ):
            pass

    def _graph_node_selected(self, node_id: str) -> None:
        session = self._active_pattern_session
        if session is None or not isinstance(session.document, PatternDocument):
            return
        if session.document.graph is None:
            return
        session.editor_state.selection.graph_node_id = str(node_id)
        selected = next(
            (
                node
                for node in session.document.graph.nodes
                if node.id == str(node_id)
            ),
            None,
        )
        self.inspector.set_graph_node(selected)

    def _graph_node_property_requested(self, node_id: str, properties) -> None:
        self._apply_graph_command(
            SetGraphNodePropertiesCommand(
                self._active_pattern_document,
                str(node_id),
                dict(properties),
            ),
            "Set graph node property",
        )

    def _graph_node_position_requested(self, node_id: str, x: float, y: float) -> None:
        self._apply_graph_command(
            SetGraphNodePositionCommand(
                self._active_pattern_document,
                str(node_id),
                float(x),
                float(y),
            ),
            "Move graph node",
        )

    def _graph_node_create_requested(self, category: str, node_type: str) -> None:
        self._apply_graph_command(
            AddGraphNodeCommand(
                self._active_pattern_document,
                str(category),
                str(node_type),
                label=f"Add {category} node",
            ),
            f"Add {category} node",
        )

    def _graph_edge_requested(self, from_id: str, to_id: str) -> None:
        self._apply_graph_command(
            AddGraphEdgeCommand(
                self._active_pattern_document,
                str(from_id),
                str(to_id),
            ),
            "Connect graph nodes",
        )

    def _graph_node_remove_requested(self, node_id: str) -> None:
        self._apply_graph_command(
            RemoveGraphNodeCommand(self._active_pattern_document, str(node_id)),
            "Remove graph node",
        )

    def _graph_edge_remove_requested(self, edge_id: str) -> None:
        self._apply_graph_command(
            RemoveGraphEdgeCommand(self._active_pattern_document, str(edge_id)),
            "Remove graph edge",
        )

    def _apply_graph_diagnostics(self, diagnostics) -> None:
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
        if not node_ids and not edge_ids:
            return
        session = self.document_manager.active
        if session is None:
            return
        widget = self._document_widgets.get(session.document.id)
        if isinstance(widget, PatternWorkspace) and widget.mode() == "graph":
            widget.set_graph_diagnostics(tuple(node_ids), tuple(edge_ids))

    def _clear_graph_diagnostics(self) -> None:
        session = self.document_manager.active
        if session is None:
            return
        widget = self._document_widgets.get(session.document.id)
        if isinstance(widget, PatternWorkspace):
            widget.clear_graph_diagnostics()

    def _apply_pattern_properties(
        self,
        values: dict[str, object],
        label: str,
    ) -> bool:
        session = self._active_pattern_session
        if session is None or not isinstance(session.document, PatternDocument):
            return False
        session.commands.begin_transaction(label)
        try:
            for path, value in values.items():
                session.apply(
                    SetPatternPropertyCommand(
                        session.document,
                        path,
                        value,
                        label=f"Set {path}",
                    )
                )
        except Exception as exc:
            session.commands.cancel_transaction()
            self.preview_panel.handle_issue(
                {"code": "invalid_pattern_edit", "message": str(exc)}
            )
            self._log(f"[pattern-edit:error] {exc}")
            self._refresh()
            return False
        session.commands.end_transaction()
        self._active_pattern_document = session.document
        self._log(label)
        self._refresh()
        return True

    def _apply_pattern_template(self, template: str) -> None:
        if "@" in template:
            preset_id, version = template.rsplit("@", 1)
            session = self._active_pattern_session
            if session is None:
                return
            descriptor = self._preset_resolver.registry.resolve(preset_id, version)
            session.editor_state.pattern.preset_mode = True
            session.editor_state.pattern.graph_mode = False
            session.editor_state.pattern.authoring_level = "l0"
            if self._apply_graph_command(
                ApplyPresetCommand(session.document, self._preset_resolver, descriptor),
                f"Apply {descriptor.display_name} preset",
            ):
                return
            session.editor_state.pattern.preset_mode = False
            session.editor_state.pattern.authoring_level = "l1"
            return
        templates = {
            "starter_ring": {
                "shape.kind": "ring",
                "shape.count": 24,
                "aim.mode": "fixed",
                "aim.angle": 270.0,
                "schedule.interval_frames": 12,
                "schedule.burst_count": 8,
                "schedule.loop_count": None,
                "motion.speed": 2.0,
                "motion.max_lifetime": 5.0,
            },
            "aimed_arc": {
                "shape.kind": "arc",
                "shape.count": 12,
                "shape.angle_span": 60.0,
                "aim.mode": "player",
                "schedule.interval_frames": 24,
                "schedule.burst_count": 4,
                "motion.speed": 2.5,
            },
            "spiral": {
                "shape.kind": "spiral",
                "shape.count": 18,
                "aim.mode": "fixed",
                "schedule.interval_frames": 8,
                "schedule.burst_count": 24,
                "modifiers.angle_offset_per_burst": 11.0,
                "motion.speed": 2.0,
            },
        }
        values = templates.get(template)
        if values is not None and self._apply_pattern_properties(
            values, f"Apply {template.replace('_', ' ')} template"
        ):
            self._sync_active_pattern_preview()

    def _preset_parameter_requested(self, parameter_id: str, value) -> None:
        session = self._active_pattern_session
        if session is None:
            return
        if self._apply_graph_command(
            SetPresetOverrideCommand(
                session.document,
                self._preset_resolver,
                str(parameter_id),
                value,
            ),
            f"Set preset parameter {parameter_id}",
        ):
            session.editor_state.pattern.preset_mode = True
            session.editor_state.pattern.authoring_level = "l0"

    def _preset_slot_requested(self, slot_id: str, value) -> None:
        session = self._active_pattern_session
        if session is None:
            return
        if self._apply_graph_command(
            SetPresetSlotOverrideCommand(
                session.document,
                self._preset_resolver,
                str(slot_id),
                value,
            ),
            f"Set preset slot {slot_id}",
        ):
            session.editor_state.pattern.preset_mode = True
            session.editor_state.pattern.authoring_level = "l0"

    def _preset_migrate_requested(self, target_version: str) -> None:
        session = self._active_pattern_session
        if session is None:
            return
        instance = self._preset_resolver.instance_from_document(session.document)
        if instance is None:
            return
        try:
            preview = self._preset_resolver.registry.preview_migration(
                instance, str(target_version)
            )
        except Exception as exc:
            # A rejected preview is the author's answer, not a crash: the target
            # has no exact migration path, or an override no longer fits it.
            self.preview_panel.handle_issue(
                {"code": "preset_migration_unavailable", "message": str(exc)}
            )
            self._log(f"[preset-migration:error] {exc}")
            return
        if self._apply_graph_command(
            ApplyPresetMigrationCommand(
                session.document,
                self._preset_resolver,
                preview,
            ),
            f"Migrate preset to {target_version}",
        ):
            session.editor_state.pattern.preset_mode = True
            session.editor_state.pattern.authoring_level = "l0"

    def _preset_materialize_requested(self) -> None:
        session = self._active_pattern_session
        if session is None:
            return
        session.editor_state.pattern.preset_mode = False
        session.editor_state.pattern.graph_mode = False
        session.editor_state.pattern.authoring_level = "l1"
        if self._apply_graph_command(
            MaterializePresetCommand(session.document, self._preset_resolver),
            "Make preset local",
        ):
            return
        session.editor_state.pattern.preset_mode = True
        session.editor_state.pattern.authoring_level = "l0"

    def _pattern_origin_requested(self, x: float, y: float) -> None:
        if self._apply_pattern_properties(
            {"shape.origin_x": x, "shape.origin_y": y},
            "Move Pattern emitter",
        ):
            self._sync_active_pattern_preview()

    def _pattern_player_requested(self, x: float, y: float) -> None:
        if self._active_pattern_session is not None:
            self._active_pattern_session.editor_state.pattern.player_position = (
                float(x),
                float(y),
            )
        self._send_pattern_preview_command(
            "set-player-position", {"x": float(x), "y": float(y)}
        )

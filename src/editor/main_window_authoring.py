"""State-graph and variable authoring slots."""

from __future__ import annotations

from src.qt_compat.QtWidgets import QDialog
from src.authoring.variables import VariableOutputMapping, VariableSpec
from .document import DocumentError, SceneDocument, StateSpec, TransitionSpec
from .variable_mapping_workspace import VariableBindingDialog, VariableMappingDialog
from .variable_commands import (
    AddOutputMappingCommand,
    AddVariableCommand,
    RemoveOutputMappingCommand,
    RemoveVariableCommand,
    SetOutputMappingPropertiesCommand,
    SetVariablePropertiesCommand,
    compatible_variable_bindings,
    find_variable,
)
from .state_graph_commands import (
    AddStateCommand,
    AddTransitionCommand,
    DuplicateStateCommand,
    MoveStateCommand,
    RemoveStateCommand,
    RemoveTransitionCommand,
    RenameStateCommand,
    SetTransitionPropertiesCommand,
)


class AuthoringSlotsMixin:
    """State-graph and variable authoring slots.

    These slots stay bound to the window instance instead of moving into a
    controller object: every attribute they touch is owned by
    ``EditorMainWindow``, and the editor tests plus the three native gates drive
    these methods by name.  Mix in before the Qt base class, the same way
    ``SpaceTapSearchMixin`` is used by ``SceneViewport``.
    """

    def _state_graph_state_selected(self, state_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        state = self.session.document.state_graph.find_state(state_id)
        if state is None:
            return
        previous = self.session.editor_context.get("selected_state_id")
        playheads = self.session.editor_context.setdefault(
            "timeline_playheads_by_state", {}
        )
        if isinstance(playheads, dict) and previous:
            playheads[str(previous)] = int(self.timeline.playhead_frame)
        self.session.editor_context["selected_state_id"] = state.id
        self.session.editor_context.pop("selected_track_id", None)
        self.session.editor_context.pop("selected_clip_id", None)
        frame = int(playheads.get(state.id, 0)) if isinstance(playheads, dict) else 0
        self.session.editor_context["timeline_playhead"] = frame
        self._refresh()

    def _variable_add_requested(
        self,
        name: str,
        type_id: str,
        default: object,
        scope: str,
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        selected_state = str(
            self.session.editor_context.get("selected_state_id")
            or self.session.document.state_graph.initial_state_id
        )
        state_id = selected_state if scope == "state" else None
        try:
            variable = VariableSpec(
                name=name,
                type=type_id,
                default=default,
                scope=scope,
                writable_by=("timeline",) if scope == "state" else (),
                animatable=scope == "state",
            )
            self.session.apply(AddVariableCommand(self.session.document, variable, state_id=state_id))
        except (DocumentError, ValueError) as exc:
            self._show_error("Add Variable failed", exc)
            return
        self._refresh()
        self._sync_active_stage_preview()

    def _variable_delete_requested(self, variable_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(RemoveVariableCommand(self.session.document, variable_id))
        except (DocumentError, ValueError) as exc:
            self._show_error("Delete Variable failed", exc)
            return
        self._refresh()
        self._sync_active_stage_preview()

    def _variable_edit_requested(self, variable_id: str, values: object) -> None:
        if not isinstance(self.session.document, SceneDocument) or not isinstance(values, dict):
            return
        try:
            self.session.apply(SetVariablePropertiesCommand(self.session.document, variable_id, values))
        except (DocumentError, ValueError) as exc:
            self._show_error("Edit Variable failed", exc)
            return
        self._refresh()
        self._sync_active_stage_preview()

    def _variable_binding_requested(self, variable_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        variable = find_variable(self.session.document, variable_id)
        if variable is None:
            return
        candidates = compatible_variable_bindings(
            self.session.document,
            type_id=variable.type,
            scope=variable.scope,
            owner_id=variable.owner_id,
            exclude_id=variable.id,
        )
        self.session.editor_context["variable_binding_candidates"] = tuple(item.id for item in candidates)
        picker = VariableBindingDialog(candidates, parent=self)
        if picker.exec() != QDialog.Accepted or picker.selected_id is None:
            return
        selected = find_variable(self.session.document, picker.selected_id)
        if selected is None:
            return
        # A binding is an editor selection, not a document mutation.  The
        # selected reference is consumed by the owning pattern/behavior tool;
        # choosing it must not create a dirty document or an undo entry.
        self.session.editor_context["selected_binding_id"] = selected.id
        self.statusBar().showMessage(
            f"Binding candidate: {selected.name} ({selected.scope}, {selected.type})",
            5000,
        )

    @staticmethod
    def _variable_specs(document: SceneDocument) -> tuple:
        values = list(document.variables)
        values.extend(variable for state in document.state_graph.walk_states() for variable in state.variables)
        return tuple(values)

    @staticmethod
    def _mapping_collection(document: SceneDocument, state_id: str | None):
        if state_id:
            state = document.state_graph.find_state(state_id)
            if state is None:
                raise DocumentError(f"State does not exist: {state_id}")
            return state.output_mappings
        return document.output_mappings

    def _variable_mapping_requested(self) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        state_id = str(self.session.editor_context.get("selected_state_id") or "") or None
        try:
            mappings = tuple(self._mapping_collection(self.session.document, state_id))
        except DocumentError as exc:
            self._show_error("Output mappings unavailable", exc)
            return
        dialog = VariableMappingDialog(
            self._variable_specs(self.session.document),
            mappings,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self._apply_variable_mapping_changes(dialog.mappings, state_id=state_id)
        except (DocumentError, ValueError) as exc:
            self._show_error("Output mapping failed", exc)
            return
        self._refresh()
        self._sync_active_stage_preview()

    def _apply_variable_mapping_changes(
        self,
        mappings: tuple[VariableOutputMapping, ...],
        *,
        state_id: str | None,
    ) -> None:
        """Commit one mapping dialog result as one undoable transaction."""

        if not isinstance(self.session.document, SceneDocument):
            return
        existing = tuple(self._mapping_collection(self.session.document, state_id))
        old_by_id = {item.id: item for item in existing}
        new_by_id = {item.id: item for item in mappings}
        commands = []
        for mapping_id in sorted(set(old_by_id).difference(new_by_id)):
            commands.append(RemoveOutputMappingCommand(self.session.document, mapping_id))
        for mapping_id in sorted(set(new_by_id).difference(old_by_id)):
            commands.append(
                AddOutputMappingCommand(
                    self.session.document,
                    new_by_id[mapping_id],
                    state_id=state_id,
                )
            )
        for mapping_id in sorted(set(old_by_id).intersection(new_by_id)):
            old = old_by_id[mapping_id]
            new = new_by_id[mapping_id]
            if old.to_dict() == new.to_dict():
                continue
            commands.append(
                SetOutputMappingPropertiesCommand(
                    self.session.document,
                    mapping_id,
                    {
                        "source": new.source.to_dict(),
                        "target": new.target.to_dict(),
                        "operation": new.operation,
                    },
                )
            )
        if not commands:
            return
        with self.session.commands.transaction("Edit output mappings"):
            for command in commands:
                self.session.apply(command)

    def _state_graph_add_state(self, graph_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        graph = self.session.document.state_graph.find_graph(graph_id)
        if graph is None:
            return
        state = StateSpec(
            name=f"State {len(graph.states) + 1}",
            order=len(graph.states),
            duration_frames=60,
        )
        try:
            self.session.apply(
                AddStateCommand(self.session.document, graph.id, state)
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Add State failed", exc)
            return
        self.session.editor_context["selected_state_id"] = state.id
        self.session.editor_context.pop("selected_track_id", None)
        self.session.editor_context.pop("selected_clip_id", None)
        self._log(f"Added State {state.name}")
        self._refresh()
        self._sync_active_stage_preview()

    def _state_graph_rename_state(self, state_id: str, name: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                RenameStateCommand(self.session.document, state_id, name),
                coalesce=True,
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Rename State failed", exc)
            self._refresh()
            return
        self.session.editor_context["selected_state_id"] = state_id
        self._refresh()
        self._sync_active_stage_preview()

    def _state_graph_duplicate_state(self, state_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        command = DuplicateStateCommand(self.session.document, state_id)
        try:
            self.session.apply(command)
        except (DocumentError, ValueError) as exc:
            self._show_error("Duplicate State failed", exc)
            return
        if command.duplicated_state is not None:
            self.session.editor_context["selected_state_id"] = (
                command.duplicated_state.id
            )
        self.session.editor_context.pop("selected_track_id", None)
        self.session.editor_context.pop("selected_clip_id", None)
        self._refresh()
        self._sync_active_stage_preview()

    def _state_graph_delete_state(self, state_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        graph = self.session.document.state_graph.graph_for_state(state_id)
        if graph is None:
            return
        try:
            self.session.apply(RemoveStateCommand(self.session.document, state_id))
        except (DocumentError, ValueError) as exc:
            self._show_error("Delete State failed", exc)
            return
        self.session.editor_context["selected_state_id"] = graph.initial_state_id
        self.session.editor_context.pop("selected_track_id", None)
        self.session.editor_context.pop("selected_clip_id", None)
        self._refresh()
        self._sync_active_stage_preview()

    def _state_graph_move_state(self, state_id: str, delta: int) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        graph = self.session.document.state_graph.graph_for_state(state_id)
        state = self.session.document.state_graph.find_state(state_id)
        if graph is None or state is None:
            return
        current = graph.states.index(state)
        target = max(0, min(current + int(delta), len(graph.states) - 1))
        if target == current:
            return
        try:
            self.session.apply(
                MoveStateCommand(self.session.document, state_id, target)
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Move State failed", exc)
            return
        self.session.editor_context["selected_state_id"] = state_id
        self._refresh()
        self._sync_active_stage_preview()

    def _state_graph_add_transition(
        self,
        source_state_id: str,
        target_state_id: str,
        trigger: str,
        after_frames: int,
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        target = self.session.document.state_graph.find_state(target_state_id)
        if target is None:
            return
        transition = TransitionSpec(
            name=f"To {target.name}",
            target_state_id=target.id,
            trigger=trigger,
            after_frames=(int(after_frames) if trigger == "after" else None),
        )
        try:
            self.session.apply(
                AddTransitionCommand(
                    self.session.document,
                    source_state_id,
                    transition,
                )
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Add transition failed", exc)
            return
        self.session.editor_context["selected_state_id"] = source_state_id
        self._refresh()
        self._sync_active_stage_preview()

    def _state_graph_edit_transition(
        self,
        transition_id: str,
        values: dict[str, object],
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                SetTransitionPropertiesCommand(
                    self.session.document,
                    transition_id,
                    values,
                ),
                coalesce=True,
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Edit transition failed", exc)
            self._refresh()
            return
        self._refresh()
        self._sync_active_stage_preview()

    def _state_graph_delete_transition(self, transition_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                RemoveTransitionCommand(self.session.document, transition_id)
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Delete transition failed", exc)
            return
        self._refresh()
        self._sync_active_stage_preview()

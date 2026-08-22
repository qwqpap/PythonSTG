"""State-graph and variable shell adapters using typed coordinator intents."""

from __future__ import annotations

from src.qt_compat.QtWidgets import QDialog
from src.authoring.variables import VariableOutputMapping

from .application import AuthoringAction, AuthoringIntent, IntentRejectedError
from .application.queries import compatible_variable_bindings, find_variable
from src.authoring.scene.document import DocumentError, SceneDocument
from .shell import WindowService
from .panels.variable_mapping_workspace import VariableBindingDialog, VariableMappingDialog


class AuthoringService(WindowService):
    def _submit_authoring_intent(
        self,
        intent: AuthoringIntent,
        *,
        label: str = "",
        error_title: str = "Authoring edit failed",
        sync_preview: bool = False,
    ) -> bool:
        try:
            invalidation = self.editor_coordinator.dispatch(intent)
        except (IntentRejectedError, DocumentError, ValueError) as exc:
            self._show_error(error_title, exc)
            return False
        if invalidation.scopes:
            self.apply_invalidation(intent.document_id, invalidation)
            if label:
                self._log(label)
            if sync_preview:
                self._sync_active_stage_preview()
        return bool(invalidation.scopes)

    def _state_graph_state_selected(self, state_id: str) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.SELECT_STATE,
                target_id=str(state_id),
                amount=int(self.timeline.playhead_frame),
            )
        )

    def _variable_add_requested(
        self,
        name: str,
        type_id: str,
        default: object,
        scope: str,
    ) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.ADD_VARIABLE,
                values={
                    "name": str(name),
                    "type": str(type_id),
                    "default": default,
                    "scope": str(scope),
                },
            ),
            error_title="Add Variable failed",
            sync_preview=True,
        )

    def _variable_delete_requested(self, variable_id: str) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.REMOVE_VARIABLE,
                target_id=str(variable_id),
            ),
            error_title="Delete Variable failed",
            sync_preview=True,
        )

    def _variable_edit_requested(self, variable_id: str, values: object) -> None:
        if isinstance(values, dict):
            self._submit_authoring_intent(
                AuthoringIntent(
                    self.session.document.id,
                    AuthoringAction.SET_VARIABLE,
                    target_id=str(variable_id),
                    values=dict(values),
                ),
                error_title="Edit Variable failed",
                sync_preview=True,
            )

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
        candidate_items = tuple({"id": item.id} for item in candidates)
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.SELECT_BINDING,
                items=candidate_items,
            )
        )
        picker = VariableBindingDialog(candidates, parent=self)
        if picker.exec() != QDialog.Accepted or picker.selected_id is None:
            return
        selected = find_variable(self.session.document, picker.selected_id)
        if selected is None:
            return
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.SELECT_BINDING,
                target_id=selected.id,
                items=candidate_items,
            )
        )
        self.statusBar().showMessage(
            f"Binding candidate: {selected.name} ({selected.scope}, {selected.type})",
            5000,
        )

    @staticmethod
    def _variable_specs(document: SceneDocument) -> tuple:
        values = list(document.variables)
        values.extend(
            variable
            for state in document.state_graph.walk_states()
            for variable in state.variables
        )
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
        state_id = self.session.editor_state.selection.state_id
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
        if dialog.exec() == QDialog.Accepted:
            self._apply_variable_mapping_changes(dialog.mappings, state_id=state_id)

    def _apply_variable_mapping_changes(
        self,
        mappings: tuple[VariableOutputMapping, ...],
        *,
        state_id: str | None,
    ) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.SET_OUTPUT_MAPPINGS,
                target_id=str(state_id or ""),
                items=tuple(item.to_dict() for item in mappings),
            ),
            error_title="Output mapping failed",
            sync_preview=True,
        )

    def _state_graph_add_state(self, graph_id: str) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.ADD_STATE,
                target_id=str(graph_id),
            ),
            label="Add State",
            error_title="Add State failed",
            sync_preview=True,
        )

    def _state_graph_rename_state(self, state_id: str, name: str) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.RENAME_STATE,
                target_id=str(state_id),
                values={"name": str(name)},
            ),
            error_title="Rename State failed",
            sync_preview=True,
        )

    def _state_graph_duplicate_state(self, state_id: str) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.DUPLICATE_STATE,
                target_id=str(state_id),
            ),
            error_title="Duplicate State failed",
            sync_preview=True,
        )

    def _state_graph_delete_state(self, state_id: str) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.REMOVE_STATE,
                target_id=str(state_id),
            ),
            error_title="Delete State failed",
            sync_preview=True,
        )

    def _state_graph_move_state(self, state_id: str, delta: int) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.MOVE_STATE,
                target_id=str(state_id),
                amount=int(delta),
            ),
            error_title="Move State failed",
            sync_preview=True,
        )

    def _state_graph_add_transition(
        self,
        source_state_id: str,
        target_state_id: str,
        trigger: str,
        after_frames: int,
    ) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.ADD_TRANSITION,
                target_id=str(source_state_id),
                related_id=str(target_state_id),
                values={"trigger": str(trigger), "after_frames": int(after_frames)},
            ),
            error_title="Add transition failed",
            sync_preview=True,
        )

    def _state_graph_edit_transition(
        self,
        transition_id: str,
        values: dict[str, object],
    ) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.SET_TRANSITION,
                target_id=str(transition_id),
                values=dict(values),
            ),
            error_title="Edit transition failed",
            sync_preview=True,
        )

    def _state_graph_delete_transition(self, transition_id: str) -> None:
        self._submit_authoring_intent(
            AuthoringIntent(
                self.session.document.id,
                AuthoringAction.REMOVE_TRANSITION,
                target_id=str(transition_id),
            ),
            error_title="Delete transition failed",
            sync_preview=True,
        )


__all__ = ["AuthoringService"]

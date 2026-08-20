"""UI and background document slots: nodes, layers, transforms and bindings."""

from __future__ import annotations

from src.qt_compat import sip
from src.authoring.resources import ResourceDocumentError
from src.game.background_render.document import BackgroundDocument
from src.ui.document import UIDocument
from .application import (
    BackgroundAction,
    BackgroundIntent,
    IntentRejectedError,
    UIDocumentAction,
    UIDocumentIntent,
)
from .main_window_support import _find_ui_node
from .shell import WindowService


class UIDocumentService(WindowService):
    """UI and background document slots: nodes, layers, transforms and bindings.

    Public compatibility methods translate Qt events into typed application
    intents.  The coordinator owns document validation, commands, transient
    state and the finite invalidation returned for each request.
    """

    def _active_document(self, document_type):
        session = self.document_manager.active
        if session is None or not isinstance(session.document, document_type):
            return None
        return session

    def _submit_ui_document_intent(
        self,
        intent: UIDocumentIntent,
        *,
        issue_code: str,
        log_prefix: str,
        label: str = "",
    ) -> bool:
        try:
            result = self.editor_coordinator.dispatch(intent)
        except (IntentRejectedError, ValueError) as exc:
            self.preview_panel.handle_issue(
                {"code": issue_code, "message": str(exc)}
            )
            self._log(f"[{log_prefix}:error] {exc}")
            return False
        self.apply_invalidation(intent.document_id, result)
        if label:
            self._log(label)
        return True

    def _submit_background_intent(
        self,
        intent: BackgroundIntent,
        *,
        issue_code: str,
        label: str = "",
    ) -> bool:
        try:
            result = self.editor_coordinator.dispatch(intent)
        except (IntentRejectedError, ValueError) as exc:
            self.preview_panel.handle_issue(
                {"code": issue_code, "message": str(exc)}
            )
            self._log(f"[background-edit:error] {exc}")
            return False
        self._applying_background_invalidation = True
        try:
            self.apply_invalidation(intent.document_id, result)
        finally:
            self._applying_background_invalidation = False
        if label:
            self._log(label)
        return True

    def _apply_ui_document_view_if_alive(self, widget, document) -> None:
        """Deferred entry point for _apply_ui_document_view.

        Runs one event loop turn after the document swap, by which point the
        window or the workspace widget may already be gone.
        """

        if sip.isdeleted(self) or widget is None or sip.isdeleted(widget):
            return
        self._apply_ui_document_view(widget, document)

    def _apply_ui_document_view(self, widget, document) -> None:
        widget.set_document(document)
        selected = self.session.editor_state.selection.ui_node_id
        if selected:
            widget.select_node(str(selected))

    def _ui_node_selected(self, node_id: str) -> None:
        session = self._active_document(UIDocument)
        if session is None:
            return
        document_id = session.document.id
        self._submit_ui_document_intent(
            UIDocumentIntent(
                document_id,
                UIDocumentAction.SELECT_NODE,
                target_id=str(node_id),
            ),
            issue_code="invalid_ui_select",
            log_prefix="ui-edit",
        )

    def _ui_node_create_requested(
        self, parent_id: str, node_type: str, name: str
    ) -> None:
        session = self._active_document(UIDocument)
        if session is None:
            return
        if node_type not in {
            "text",
            "rect",
            "bar",
            "image",
            "panel",
            "container_h",
            "container_v",
            "container_grid",
        }:
            self._log(f"[ui-edit:error] unknown UI node type: {node_type}")
            return
        document_id = session.document.id
        self._submit_ui_document_intent(
            UIDocumentIntent(
                document_id,
                UIDocumentAction.ADD_NODE,
                parent_id=str(parent_id or session.document.root.id),
                node_type=str(node_type),
                name=str(name or f"New {node_type}"),
            ),
            issue_code="invalid_ui_add",
            log_prefix="ui-edit",
            label="Add UI node",
        )

    def _ui_node_remove_requested(self, node_id: str) -> None:
        session = self._active_document(UIDocument)
        if session is None:
            return
        if str(node_id) == session.document.root.id:
            self._log("[ui-edit] root node cannot be removed")
            return
        document_id = session.document.id
        self._submit_ui_document_intent(
            UIDocumentIntent(
                document_id,
                UIDocumentAction.REMOVE_NODE,
                target_id=str(node_id),
            ),
            issue_code="invalid_ui_remove",
            log_prefix="ui-edit",
            label="Remove UI node",
        )

    def _ui_node_property_requested(self, node_id: str, properties) -> None:
        session = self._active_document(UIDocument)
        if session is None:
            return
        document_id = session.document.id
        self._submit_ui_document_intent(
            UIDocumentIntent(
                document_id,
                UIDocumentAction.SET_NODE_PROPERTIES,
                target_id=str(node_id),
                values=dict(properties),
            ),
            issue_code="invalid_ui_edit",
            log_prefix="ui-edit",
            label="Set UI node property",
        )

    def _ui_node_geometry_requested(
        self,
        node_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        session = self._active_document(UIDocument)
        if session is None:
            return
        document_id = session.document.id
        self._submit_ui_document_intent(
            UIDocumentIntent(
                document_id,
                UIDocumentAction.SET_NODE_PROPERTIES,
                target_id=str(node_id),
                values={
                    "x": float(x),
                    "y": float(y),
                    "width": float(width),
                    "height": float(height),
                },
            ),
            issue_code="invalid_ui_geometry",
            log_prefix="ui-edit",
            label="Move UI node",
        )

    def _ui_resource_dropped(self, node_id: str, resource_uri: str) -> None:
        """Assign a dropped project resource through the normal command path."""
        session = self._active_document(UIDocument)
        if session is None:
            return
        node = _find_ui_node(session.document.root, str(node_id))
        if node is None:
            return
        property_name = "texture" if node.node_type == "image" else "style"
        value = str(resource_uri).strip()
        if not value.startswith("res://"):
            self._show_error(
                "Invalid UI resource",
                ResourceDocumentError("UI resources must use res:// references"),
            )
            return
        document_id = session.document.id
        self._submit_ui_document_intent(
            UIDocumentIntent(
                document_id,
                UIDocumentAction.SET_NODE_PROPERTIES,
                target_id=str(node_id),
                values={property_name: value},
            ),
            issue_code="invalid_ui_resource",
            log_prefix="ui-edit",
            label="Assign UI resource",
        )

    def _background_layer_selected(self, index: int) -> None:
        if getattr(self, "_applying_background_invalidation", False):
            return
        session = self._active_document(BackgroundDocument)
        if session is None:
            return
        document_id = session.document.id
        self._submit_background_intent(
            BackgroundIntent(
                document_id,
                BackgroundAction.SELECT_LAYER,
                index=int(index),
            ),
            issue_code="invalid_background_select",
        )

    def _background_property_requested(self, path: str, value) -> None:
        session = self._active_document(BackgroundDocument)
        if session is None:
            return
        document_id = session.document.id
        self._submit_background_intent(
            BackgroundIntent(
                document_id,
                BackgroundAction.SET_PROPERTY,
                target=str(path),
                value=value,
                coalesce=True,
            ),
            issue_code="invalid_background_edit",
            label=f"Set background property {path}",
        )

    def _background_layer_transform_requested(
        self, index: int, x: float, y: float, scale: float, rotation: float
    ) -> None:
        session = self._active_document(BackgroundDocument)
        if session is None:
            return
        layers = session.document.body.get("layers") or []
        if not isinstance(layers, list) or not 0 <= int(index) < len(layers):
            return
        current = dict(layers[int(index)].get("transform") or {})
        current.update(
            x=float(x), y=float(y), scale=float(scale), rotation=float(rotation)
        )
        document_id = session.document.id
        self._submit_background_intent(
            BackgroundIntent(
                document_id,
                BackgroundAction.SET_PROPERTY,
                target=f"layers.{int(index)}.transform",
                value=current,
                coalesce=True,
            ),
            issue_code="invalid_background_transform",
        )

    def _background_layer_create_requested(self) -> None:
        session = self._active_document(BackgroundDocument)
        if session is None:
            return
        document_id = session.document.id
        self._submit_background_intent(
            BackgroundIntent(document_id, BackgroundAction.ADD_LAYER),
            issue_code="invalid_background_add",
        )

    def _background_layer_remove_requested(self, index: int) -> None:
        session = self._active_document(BackgroundDocument)
        if session is None:
            return
        document_id = session.document.id
        self._submit_background_intent(
            BackgroundIntent(
                document_id,
                BackgroundAction.REMOVE_LAYER,
                index=int(index),
            ),
            issue_code="invalid_background_remove",
        )

    def _background_binding_requested(self, target: str, expression: str) -> None:
        session = self._active_document(BackgroundDocument)
        if session is None:
            return
        document_id = session.document.id
        self._submit_background_intent(
            BackgroundIntent(
                document_id,
                BackgroundAction.SET_BINDING,
                target=str(target).strip(),
                expression=str(expression).strip(),
            ),
            issue_code="invalid_background_binding",
        )

    def _ui_viewport_changed(self, width: int, height: int) -> None:
        session = self._active_document(UIDocument)
        if session is None:
            return
        document_id = session.document.id
        self._submit_ui_document_intent(
            UIDocumentIntent(
                document_id,
                UIDocumentAction.SET_VIEWPORT,
                width=int(width),
                height=int(height),
            ),
            issue_code="invalid_ui_viewport",
            log_prefix="ui-edit",
        )

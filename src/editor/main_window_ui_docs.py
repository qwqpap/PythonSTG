"""UI and background document slots: nodes, layers, transforms and bindings."""

from __future__ import annotations

from src.qt_compat import sip
from src.authoring.resources import ResourceDocumentError
from src.game.background_render.document import BackgroundDocument
from src.ui.document import UIDocument, UIDocumentNode
from .ui_workspace import BackgroundWorkspace, UIWorkspace
from .main_window_support import _find_ui_node
from .ui_commands import (
    AddUINodeCommand,
    RemoveUINodeCommand,
    SetUINodePropertyCommand,
)
from .background_commands import (
    AddBackgroundLayerCommand,
    RemoveBackgroundLayerCommand,
    SetBackgroundBindingCommand,
    SetBackgroundPropertyCommand,
)


class UIDocumentSlotsMixin:
    """UI and background document slots: nodes, layers, transforms and bindings.

    These slots stay bound to the window instance instead of moving into a
    controller object: every attribute they touch is owned by
    ``EditorMainWindow``, and the editor tests plus the three native gates drive
    these methods by name.  Mix in before the Qt base class, the same way
    ``SpaceTapSearchMixin`` is used by ``SceneViewport``.
    """

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
        selected = self.session.editor_context.get("selected_ui_node_id")
        if selected:
            widget.select_node(str(selected))

    def _ui_node_selected(self, node_id: str) -> None:
        session, _widget = self._ui_session_for_sender()
        if session is None:
            return
        session.editor_context["selected_ui_node_id"] = str(node_id)
        node = _find_ui_node(session.document.root, str(node_id))
        if session is self.document_manager.active:
            self.inspector.set_ui_node(node)

    def _ui_node_create_requested(
        self, parent_id: str, node_type: str, name: str
    ) -> None:
        session, widget = self._ui_session_for_sender()
        if session is None:
            return
        if not isinstance(session.document, UIDocument):
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
        node = UIDocumentNode(
            node_type=str(node_type),
            name=str(name or f"New {node_type}"),
            width=96.0,
            height=32.0,
        )
        if node_type == "text":
            node.text = node.name
        elif node_type == "image":
            node.width = 64.0
            node.height = 64.0
        try:
            session.apply(
                AddUINodeCommand(
                    session.document,
                    str(parent_id or session.document.root.id),
                    node,
                )
            )
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_ui_add", "message": str(exc)}
            )
            self._log(f"[ui-edit:error] {exc}")
            return
        session.editor_context["selected_ui_node_id"] = node.id
        self._log("Add UI node")
        if session is self.document_manager.active:
            self._refresh()
        elif isinstance(widget, UIWorkspace):
            self._apply_ui_document_view(widget, session.document)

    def _ui_node_remove_requested(self, node_id: str) -> None:
        session, widget = self._ui_session_for_sender()
        if session is None or not isinstance(session.document, UIDocument):
            return
        if str(node_id) == session.document.root.id:
            self._log("[ui-edit] root node cannot be removed")
            return
        try:
            session.apply(RemoveUINodeCommand(session.document, str(node_id)))
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_ui_remove", "message": str(exc)}
            )
            self._log(f"[ui-edit:error] {exc}")
            return
        session.editor_context["selected_ui_node_id"] = session.document.root.id
        self._log("Remove UI node")
        if session is self.document_manager.active:
            self._refresh()
        elif isinstance(widget, UIWorkspace):
            self._apply_ui_document_view(widget, session.document)

    def _ui_node_property_requested(self, node_id: str, properties) -> None:
        session, widget = self._ui_session_for_sender()
        if session is None:
            return
        try:
            session.apply(
                SetUINodePropertyCommand(
                    session.document,
                    str(node_id),
                    dict(properties),
                )
            )
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_ui_edit", "message": str(exc)}
            )
            self._log(f"[ui-edit:error] {exc}")
            return
        self._log("Set UI node property")
        if session is self.document_manager.active:
            self._refresh()
        elif isinstance(widget, UIWorkspace):
            self._apply_ui_document_view(widget, session.document)

    def _ui_session_for_sender(self):
        """Resolve a UI signal to its owning document, not merely the active tab."""
        sender = self.sender()
        widget = sender
        while widget is not None:
            session = self._managed_for_widget(widget)
            if session is not None and isinstance(session.document, UIDocument):
                return session, widget
            parent_getter = getattr(widget, "parentWidget", None)
            widget = parent_getter() if callable(parent_getter) else None
        active = self.document_manager.active
        if active is not None and isinstance(active.document, UIDocument):
            return active, self._document_widgets.get(active.document.id)
        return None, None

    def _ui_node_geometry_requested(
        self,
        node_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        session, widget = self._ui_session_for_sender()
        if session is None:
            return
        try:
            session.apply(
                SetUINodePropertyCommand(
                    session.document,
                    str(node_id),
                    {
                        "x": float(x),
                        "y": float(y),
                        "width": float(width),
                        "height": float(height),
                    },
                )
            )
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_ui_geometry", "message": str(exc)}
            )
            self._log(f"[ui-edit:error] {exc}")
            return
        self._log("Move UI node")
        if session is self.document_manager.active:
            self._refresh()
        elif isinstance(widget, UIWorkspace):
            self._apply_ui_document_view(widget, session.document)

    def _ui_resource_dropped(self, node_id: str, resource_uri: str) -> None:
        """Assign a dropped project resource through the normal command path."""
        session, _widget = self._ui_session_for_sender()
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
        try:
            session.apply(
                SetUINodePropertyCommand(
                    session.document,
                    str(node_id),
                    {property_name: value},
                )
            )
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_ui_resource", "message": str(exc)}
            )
            self._log(f"[ui-edit:error] {exc}")
            return
        self._log("Assign UI resource")
        if session is self.document_manager.active:
            self._refresh()

    def _background_session_for_sender(self):
        sender = self.sender()
        widget = sender
        while widget is not None:
            document_id = str(widget.property("managedDocumentId") or "")
            if document_id:
                session = next(
                    (
                        item
                        for item in self.document_manager
                        if item.document.id == document_id
                    ),
                    None,
                )
                if session is not None and isinstance(session.document, BackgroundDocument):
                    return session, widget
            parent_getter = getattr(widget, "parentWidget", None)
            widget = parent_getter() if callable(parent_getter) else None
        active = self.document_manager.active
        if active is not None and isinstance(active.document, BackgroundDocument):
            return active, self._document_widgets.get(active.document.id)
        return None, None

    def _background_layer_selected(self, index: int) -> None:
        session, _widget = self._background_session_for_sender()
        if session is not None:
            session.editor_context["background_selected_layer"] = int(index)
            if session is self.document_manager.active:
                self.inspector.set_background_document(session.document)

    def _background_property_requested(self, path: str, value) -> None:
        session, widget = self._background_session_for_sender()
        if session is None:
            return
        try:
            session.apply(
                SetBackgroundPropertyCommand(session.document, str(path), value),
                coalesce=True,
            )
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_background_edit", "message": str(exc)}
            )
            self._log(f"[background-edit:error] {exc}")
            return
        self._log(f"Set background property {path}")
        if session is self.document_manager.active:
            self._refresh()
        elif isinstance(widget, BackgroundWorkspace):
            widget.set_document(session.document)

    def _background_layer_transform_requested(
        self, index: int, x: float, y: float, scale: float, rotation: float
    ) -> None:
        session, widget = self._background_session_for_sender()
        if session is None:
            return
        layers = session.document.body.get("layers") or []
        if not isinstance(layers, list) or not 0 <= int(index) < len(layers):
            return
        current = dict(layers[int(index)].get("transform") or {})
        current.update(
            x=float(x), y=float(y), scale=float(scale), rotation=float(rotation)
        )
        try:
            session.apply(
                SetBackgroundPropertyCommand(
                    session.document,
                    f"layers.{int(index)}.transform",
                    current,
                ),
                coalesce=True,
            )
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_background_transform", "message": str(exc)}
            )
            self._log(f"[background-edit:error] {exc}")
            return
        if session is self.document_manager.active:
            self._refresh()
        elif isinstance(widget, BackgroundWorkspace):
            widget.set_document(session.document)

    def _background_layer_create_requested(self) -> None:
        session, widget = self._background_session_for_sender()
        if session is None:
            return
        textures = session.document.body.get("textures") or {}
        texture = next(iter(textures), None)
        layer = {
            "name": f"Layer {len(session.document.body.get('layers') or []) + 1}",
            "texture": texture,
            "z_order": len(session.document.body.get("layers") or []),
            "z_depth": 0.0,
            "blend_mode": "normal",
            "alpha": 1.0,
            "scroll_multiplier": 1.0,
            "tile": {"x_range": [-1, 1], "y_range": [-1, 1], "size": 1.0},
            "variants": [],
            "enabled": True,
            "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0},
        }
        try:
            session.apply(AddBackgroundLayerCommand(session.document, layer))
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_background_add", "message": str(exc)}
            )
            self._log(f"[background-edit:error] {exc}")
            return
        if session is self.document_manager.active:
            self._refresh()
        elif isinstance(widget, BackgroundWorkspace):
            widget.set_document(session.document)

    def _background_layer_remove_requested(self, index: int) -> None:
        session, widget = self._background_session_for_sender()
        if session is None:
            return
        try:
            session.apply(RemoveBackgroundLayerCommand(session.document, int(index)))
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_background_remove", "message": str(exc)}
            )
            self._log(f"[background-edit:error] {exc}")
            return
        if session is self.document_manager.active:
            self._refresh()
        elif isinstance(widget, BackgroundWorkspace):
            widget.set_document(session.document)

    def _background_binding_requested(self, target: str, expression: str) -> None:
        session, widget = self._background_session_for_sender()
        if session is None:
            return
        try:
            session.apply(
                SetBackgroundBindingCommand(
                    session.document, str(target).strip(), str(expression).strip()
                )
            )
        except Exception as exc:
            self.preview_panel.handle_issue(
                {"code": "invalid_background_binding", "message": str(exc)}
            )
            self._log(f"[background-edit:error] {exc}")
            return
        if session is self.document_manager.active:
            self._refresh()
        elif isinstance(widget, BackgroundWorkspace):
            widget.set_document(session.document)

    def _ui_viewport_changed(self, width: int, height: int) -> None:
        session, widget = self._ui_session_for_sender()
        if session is None:
            return
        session.editor_context["ui_viewport"] = (int(width), int(height))
        if session is self.document_manager.active:
            self._refresh()
        elif isinstance(widget, UIWorkspace):
            widget.refresh_canvas()

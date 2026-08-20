"""Document lifecycle slots: new, open, save, revert, close and central tabs."""

from __future__ import annotations

from pathlib import Path
from src.qt_compat.QtCore import Qt
from src.qt_compat.QtWidgets import QFileDialog, QMessageBox, QWidget
from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.game.background_render.document import BackgroundDocument
from src.pattern import PatternDocument
from src.ui.document import UIDocument
from .document import DocumentError, SceneDocument
from .runtime_preview import RuntimePreviewHost
from .document_manager import DocumentManagerError, ManagedDocument
from .pattern_workspace import PatternWorkspace
from .ui_workspace import BackgroundWorkspace, UIWorkspace
from .main_window_support import RESOURCE_FILTER, _scene_has_stage_content
from .scene_view import SceneViewport


class DocumentSlotsMixin:
    """Document lifecycle slots: new, open, save, revert, close and central tabs.

    These slots stay bound to the window instance instead of moving into a
    controller object: every attribute they touch is owned by
    ``EditorMainWindow``, and the editor tests plus the three native gates drive
    these methods by name.  Mix in before the Qt base class, the same way
    ``SpaceTapSearchMixin`` is used by ``SceneViewport``.
    """

    def _add_document_tab(self, session: ManagedDocument) -> QWidget:
        existing = self._document_widgets.get(session.document.id)
        if existing is not None:
            self.central_tabs.setCurrentWidget(existing)
            return existing
        if isinstance(session.document, SceneDocument):
            widget: QWidget = SceneViewport(
                self.project,
                node_registry=self.node_type_registry,
                language_manager=self.language_manager,
            )
            widget.nodeSelected.connect(self._select_from_viewport)
            widget.nodePositionRequested.connect(self._set_node_position)
            widget.resourceDropped.connect(self._resource_dropped)
            widget.actionSearchRequested.connect(
                lambda _unused: self._open_scene_action_search()
            )
        elif isinstance(session.document, PatternDocument):
            widget = PatternWorkspace()
            widget.set_language_manager(self.language_manager)
            widget.previewRequested.connect(self._launch_active_preview)
            widget.templateRequested.connect(self._apply_pattern_template)
            widget.bulletResourceRequested.connect(
                lambda value: self._apply_pattern_properties(
                    {"bullet.resource": value},
                    "Assign bullet resource",
                )
            )
            widget.originPositionRequested.connect(self._pattern_origin_requested)
            widget.playerPositionRequested.connect(self._pattern_player_requested)
            widget.graphExpandRequested.connect(self._graph_expand_requested)
            widget.graphFoldRequested.connect(self._graph_fold_requested)
            widget.graphModeChanged.connect(self._graph_mode_changed)
            widget.graphNodeSelected.connect(self._graph_node_selected)
            widget.graphNodePropertyRequested.connect(
                self._graph_node_property_requested
            )
            widget.graphNodePositionRequested.connect(
                self._graph_node_position_requested
            )
            widget.graphNodeCreateRequested.connect(self._graph_node_create_requested)
            widget.graphEdgeRequested.connect(self._graph_edge_requested)
            widget.graphNodeRemoveRequested.connect(self._graph_node_remove_requested)
            widget.graphEdgeRemoveRequested.connect(self._graph_edge_remove_requested)
            widget.presetParameterRequested.connect(self._preset_parameter_requested)
            widget.presetSlotRequested.connect(self._preset_slot_requested)
            widget.presetMigrateRequested.connect(self._preset_migrate_requested)
            widget.presetMaterializeRequested.connect(self._preset_materialize_requested)
            widget.authoringLevelRequested.connect(self._pattern_level_requested)
            widget.patternBindingRequested.connect(self._pattern_binding_requested)
            widget.patternBindingRemoveRequested.connect(
                self._pattern_binding_remove_requested
            )
            widget.sourceNavigateRequested.connect(
                self._pattern_source_navigate_requested
            )
            widget.actionSearchRequested.connect(
                lambda input_type: self._open_action_search(
                    "graph", input_type=input_type
                )
            )
            widget.set_available_presets(self._preset_library.presets)
        elif isinstance(session.document, UIDocument):
            widget = UIWorkspace()
            widget.nodeSelected.connect(self._ui_node_selected)
            widget.nodePropertyRequested.connect(self._ui_node_property_requested)
            widget.nodeCreateRequested.connect(self._ui_node_create_requested)
            widget.nodeRemoveRequested.connect(self._ui_node_remove_requested)
            widget.canvas.nodeGeometryCommitted.connect(
                self._ui_node_geometry_requested
            )
            widget.canvas.resourceDropped.connect(self._ui_resource_dropped)
            widget.viewportChanged.connect(self._ui_viewport_changed)
        elif isinstance(session.document, BackgroundDocument):
            widget = BackgroundWorkspace()
            widget.layerSelected.connect(self._background_layer_selected)
            widget.layerTransformCommitted.connect(
                self._background_layer_transform_requested
            )
            widget.layerCreateRequested.connect(self._background_layer_create_requested)
            widget.layerRemoveRequested.connect(self._background_layer_remove_requested)
            widget.bindingRequested.connect(self._background_binding_requested)
        else:
            raise DocumentManagerError(
                f"No editor workspace for {session.document.type!r}"
            )
        widget.setProperty("managedDocumentId", session.document.id)
        self._document_widgets[session.document.id] = widget
        index = self.central_tabs.addTab(widget, session.display_name)
        self.central_tabs.setCurrentIndex(index)
        return widget

    def _managed_for_widget(self, widget: QWidget | None) -> ManagedDocument | None:
        if widget is None:
            return None
        document_id = str(widget.property("managedDocumentId") or "")
        return next(
            (
                session
                for session in self.document_manager
                if session.document.id == document_id
            ),
            None,
        )

    def _central_tab_changed(self, index: int) -> None:
        widget = self.central_tabs.widget(index)
        if widget is not None and bool(widget.property("runtimePreview")):
            return
        session = self._managed_for_widget(widget)
        if session is None:
            return
        self.document_manager.activate(session)
        if isinstance(session.document, SceneDocument):
            self.viewport = self.central_tabs.widget(index)
            if _scene_has_stage_content(session.document):
                self.preview_panel.set_resource(
                    session.resource_uri or f"unsaved://{session.document.id}"
                )
                self.preview_panel.set_mode("stage")
        elif isinstance(session.document, PatternDocument):
            self._active_pattern_session = session
            self._active_pattern_document = session.document
            self._active_pattern_resource = session.resource_uri or ""
            self.preview_panel.set_resource(
                self._active_pattern_resource or f"unsaved://{session.document.id}"
            )
            self.preview_panel.set_mode("pattern")
            if hasattr(self, "bottom_dock"):
                target_height = 180 if self.height() <= 700 else 250
                self.resizeDocks([self.bottom_dock], [target_height], Qt.Vertical)
        if not hasattr(self, "tree"):
            return
        self._refresh()

    def _close_central_tab(self, index: int) -> None:
        widget = self.central_tabs.widget(index)
        if widget is not None and bool(widget.property("runtimePreview")):
            if isinstance(widget, RuntimePreviewHost):
                widget.detach()
            self.central_tabs.removeTab(index)
            widget.deleteLater()
            self._runtime_preview_host = None
            return
        session = self._managed_for_widget(widget)
        if session is not None:
            if not self._confirm_discard(session):
                return
            self.document_manager.close(session, discard=True)
            if self._active_pattern_session is session:
                self._active_pattern_session = None
                self._active_pattern_document = None
                self._active_pattern_resource = ""
            self._document_widgets.pop(session.document.id, None)
            self.central_tabs.removeTab(index)
            widget.deleteLater()
            if self.document_manager.active is None and self.central_tabs.count() == 0:
                self.new_scene()
            elif self.document_manager.active is not None:
                active_widget = self._document_widgets.get(
                    self.document_manager.active.document.id
                )
                if active_widget is not None:
                    self.central_tabs.setCurrentWidget(active_widget)
            self._refresh()
            return
        if widget is None or not widget.close():
            return
        plugin_id = str(widget.property("editorPluginId") or "")
        self.central_tabs.removeTab(index)
        if plugin_id:
            self._plugin_widgets.pop(plugin_id, None)
        widget.deleteLater()

    def new_scene(self) -> None:
        session = self.document_manager.new_scene()
        self._add_document_tab(session)
        self._log("New scene")
        self._refresh()

    def open_resource(self) -> None:
        start = self.project.game_content / "scenes"
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.language_manager.translate("Open PySTG Resource"),
            str(start),
            RESOURCE_FILTER,
        )
        if not path:
            return
        self._open_document(path)

    def open_scene(self) -> None:
        """Compatibility alias retained for existing integrations."""

        self.open_resource()

    def _open_document(self, resource_value: str) -> ManagedDocument | None:
        try:
            if str(resource_value).startswith("res://"):
                reference = ResourceReference.parse(resource_value)
                if reference.subresource is not None:
                    raise ResourceDocumentError(
                        "Authoring documents cannot be opened from a fragment"
                    )
                path = reference.resolve(self.project, must_exist=True)
            else:
                path = self.project.resolve(resource_value)
            session = self.document_manager.open(path)
        except (
            OSError,
            DocumentError,
            DocumentManagerError,
            ResourceDocumentError,
            ValueError,
        ) as exc:
            self._show_error("Open failed", exc)
            return None
        self._add_document_tab(session)
        self._log(f"Opened {self.project.relative(path)}")
        self._refresh()
        return session

    def save_scene(self) -> bool:
        return self._save_document(self.session)

    def save_scene_as(self) -> bool:
        return self._save_document(self.session, save_as=True)

    def autosave_open_documents(self) -> tuple[Path, ...]:
        """Autosave dirty, path-backed sessions to recovery sidecars."""
        written: list[Path] = []
        store = self.document_manager.store
        for session in tuple(self.document_manager):
            if not session.is_dirty or session.path is None:
                continue
            written.append(store.autosave(session.document, session.path))
        return tuple(written)

    def find_recovery_candidates(self):
        """Return sidecars that can be offered without changing open sessions."""
        return self.document_manager.store.recovery_candidates()

    def _save_document(
        self,
        session: ManagedDocument,
        *,
        save_as: bool = False,
    ) -> bool:
        if session.path is not None and not save_as:
            try:
                saved = self.document_manager.save(session)
            except (OSError, DocumentError, ResourceDocumentError, ValueError) as exc:
                self._show_error("Save failed", exc)
                return False
            self._log(f"Saved {self.project.relative(saved)}")
            if session is self._active_pattern_session:
                self._active_pattern_resource = session.resource_uri or ""
                self.preview_panel.set_resource(self._active_pattern_resource)
            if hasattr(self, "resource_browser"):
                self.resource_browser.refresh()
            self._refresh()
            return True
        folder = "patterns" if isinstance(session.document, PatternDocument) else "scenes"
        start = self.project.game_content / folder
        start.mkdir(parents=True, exist_ok=True)
        suggested = start / (
            session.path.name
            if session.path
            else ("new_pattern.pystg.json" if folder == "patterns" else "untitled.pystg.json")
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.language_manager.translate("Save PySTG Resource"),
            str(suggested),
            RESOURCE_FILTER,
        )
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".pystg.json"
        try:
            saved = self.document_manager.save(session, path)
        except (OSError, DocumentError, ResourceDocumentError, ValueError) as exc:
            self._show_error("Save failed", exc)
            return False
        self._log(f"Saved {self.project.relative(saved)}")
        if session is self._active_pattern_session:
            self._active_pattern_resource = session.resource_uri or ""
            self.preview_panel.set_resource(self._active_pattern_resource)
        if hasattr(self, "resource_browser"):
            self.resource_browser.refresh()
        self._refresh()
        return True

    def revert_document(self) -> None:
        session = self.session
        if session.is_dirty:
            result = QMessageBox.warning(
                self,
                self.language_manager.translate("Revert document"),
                self.language_manager.translate(
                    f"Discard all changes to {session.display_name}?"
                ),
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if result != QMessageBox.Yes:
                return
        try:
            self.document_manager.revert(session)
        except (OSError, ValueError, ResourceDocumentError) as exc:
            self._show_error("Revert failed", exc)
            return
        self._selected_id = session.default_selection
        self._log(f"Reverted {session.display_name}")
        self._refresh()
        self._sync_active_pattern_preview()

    def close_active_document(self) -> None:
        widget = self._document_widgets.get(self.session.document.id)
        if widget is not None:
            self._close_central_tab(self.central_tabs.indexOf(widget))

    def _confirm_discard(self, session: ManagedDocument | None = None) -> bool:
        session = session or self.session
        if not session.is_dirty:
            return True
        # Programmatic/offscreen smoke windows are never user-owned interactive
        # surfaces, so closing them must not open a modal dialog during teardown.
        if not self.isVisible():
            return True
        result = QMessageBox.warning(
            self,
            self.language_manager.translate("Unsaved changes"),
            self.language_manager.translate(
                f"Save changes to {session.display_name}?"
            ),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if result == QMessageBox.Cancel:
            return False
        if result == QMessageBox.Save:
            return self._save_document(session)
        return True

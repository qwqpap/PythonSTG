"""Document lifecycle slots: new, open, save, revert, close and central tabs."""

from __future__ import annotations

from .shell import WindowService
from .shell.ports import DocumentPort

from pathlib import Path
from src.qt_compat.QtCore import Qt
from src.qt_compat.QtWidgets import QFileDialog, QMessageBox, QWidget
from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.game.background_render.document import BackgroundDocument
from src.pattern import PatternDocument
from src.ui.document import UIDocument
from src.authoring.scene.document import DocumentError, SceneDocument
from .runtime_preview import RuntimePreviewHost
from .document_manager import DocumentManagerError, ManagedDocument
from .panels.pattern_workspace import PatternWorkspace
from .panels.ui_workspace import BackgroundWorkspace, UIWorkspace
from .main_window_support import RESOURCE_FILTER, _scene_has_stage_content
from .panels.scene_view import SceneViewport


class DocumentService(WindowService[DocumentPort]):
    """Document lifecycle slots: new, open, save, revert, close and central tabs.

    These slots stay bound to the window instance instead of moving into a
    controller object: every attribute they touch is owned by
    ``EditorMainWindow``, and the editor tests plus the three native gates drive
    these methods by name.  Mix in before the Qt base class, the same way
    ``SpaceTapSearchMixin`` is used by ``SceneViewport``.
    """

    def add_document_tab(
        self,
        session: ManagedDocument,
        *,
        show: bool = True,
    ) -> QWidget:
        existing = self.port._document_widgets.get(session.document.id)
        if existing is not None:
            self.port.central_tabs.setCurrentWidget(existing)
            if show:
                self.port.show_document_workbench()
            return existing
        if isinstance(session.document, SceneDocument):
            widget: QWidget = SceneViewport(
                self.port.project,
                node_registry=self.port.node_type_registry,
                language_manager=self.port.language_manager,
            )
            widget.nodeSelected.connect(self.port.scene_edit_service.select_from_viewport)
            widget.nodePositionRequested.connect(self.port.scene_edit_service.set_node_position)
            widget.resourceDropped.connect(self.port.workbench_service.resource_dropped)
            widget.actionSearchRequested.connect(
                lambda _unused: self.port.workbench_service.open_scene_action_search()
            )
        elif isinstance(session.document, PatternDocument):
            widget = PatternWorkspace()
            widget.set_language_manager(self.port.language_manager)
            widget.previewRequested.connect(self.port.preview_service.launch_active_preview)
            widget.templateRequested.connect(self.port.pattern_service.apply_pattern_template)
            widget.bulletResourceRequested.connect(
                lambda value: self.port.pattern_service.apply_pattern_properties(
                    {"bullet.resource": value},
                    "Assign bullet resource",
                )
            )
            widget.originPositionRequested.connect(self.port.pattern_service.pattern_origin_requested)
            widget.playerPositionRequested.connect(self.port.pattern_service.pattern_player_requested)
            widget.graphExpandRequested.connect(self.port.pattern_service.graph_expand_requested)
            widget.graphFoldRequested.connect(self.port.pattern_service.graph_fold_requested)
            widget.graphModeChanged.connect(self.port.pattern_service.graph_mode_changed)
            widget.graphNodeSelected.connect(self.port.pattern_service.graph_node_selected)
            widget.graphNodePropertyRequested.connect(
                self.port.pattern_service.graph_node_property_requested
            )
            widget.graphNodePositionRequested.connect(
                self.port.pattern_service.graph_node_position_requested
            )
            widget.graphNodeCreateRequested.connect(self.port.pattern_service.graph_node_create_requested)
            widget.graphEdgeRequested.connect(self.port.pattern_service.graph_edge_requested)
            widget.graphNodeRemoveRequested.connect(self.port.pattern_service.graph_node_remove_requested)
            widget.graphEdgeRemoveRequested.connect(self.port.pattern_service.graph_edge_remove_requested)
            widget.presetParameterRequested.connect(self.port.pattern_service.preset_parameter_requested)
            widget.presetSlotRequested.connect(self.port.pattern_service.preset_slot_requested)
            widget.presetMigrateRequested.connect(self.port.pattern_service.preset_migrate_requested)
            widget.presetMaterializeRequested.connect(self.port.pattern_service.preset_materialize_requested)
            widget.authoringLevelRequested.connect(self.port.pattern_service.pattern_level_requested)
            widget.patternBindingRequested.connect(self.port.pattern_service.pattern_binding_requested)
            widget.patternBindingRemoveRequested.connect(
                self.port.pattern_service.pattern_binding_remove_requested
            )
            widget.sourceNavigateRequested.connect(
                self.port.pattern_service.pattern_source_navigate_requested
            )
            widget.actionSearchRequested.connect(
                lambda input_type: self.port.workbench_service.open_action_search(
                    "graph", input_type=input_type
                )
            )
            widget.set_available_presets(self.port._preset_library.presets)
        elif isinstance(session.document, UIDocument):
            widget = UIWorkspace()
            widget.nodeSelected.connect(self.port.ui_document_service.ui_node_selected)
            widget.nodePropertyRequested.connect(self.port.ui_document_service.ui_node_property_requested)
            widget.nodeCreateRequested.connect(self.port.ui_document_service.ui_node_create_requested)
            widget.nodeRemoveRequested.connect(self.port.ui_document_service.ui_node_remove_requested)
            widget.canvas.nodeGeometryCommitted.connect(
                self.port.ui_document_service.ui_node_geometry_requested
            )
            widget.canvas.resourceDropped.connect(self.port.ui_document_service.ui_resource_dropped)
            widget.viewportChanged.connect(self.port.ui_document_service.ui_viewport_changed)
        elif isinstance(session.document, BackgroundDocument):
            widget = BackgroundWorkspace()
            widget.layerSelected.connect(self.port.ui_document_service.background_layer_selected)
            widget.layerTransformCommitted.connect(
                self.port.ui_document_service.background_layer_transform_requested
            )
            widget.layerCreateRequested.connect(self.port.ui_document_service.background_layer_create_requested)
            widget.layerRemoveRequested.connect(self.port.ui_document_service.background_layer_remove_requested)
            widget.bindingRequested.connect(self.port.ui_document_service.background_binding_requested)
        else:
            raise DocumentManagerError(
                f"No editor workspace for {session.document.type!r}"
            )
        widget.setProperty("managedDocumentId", session.document.id)
        self.port._document_widgets[session.document.id] = widget
        index = self.port.central_tabs.addTab(widget, session.display_name)
        self.port.central_tabs.setCurrentIndex(index)
        if show:
            self.port.show_document_workbench()
        return widget

    def managed_for_widget(self, widget: QWidget | None) -> ManagedDocument | None:
        if widget is None:
            return None
        document_id = str(widget.property("managedDocumentId") or "")
        return next(
            (
                session
                for session in self.port.document_manager
                if session.document.id == document_id
            ),
            None,
        )

    def central_tab_changed(self, index: int) -> None:
        widget = self.port.central_tabs.widget(index)
        if widget is not None and bool(widget.property("runtimePreview")):
            return
        session = self.managed_for_widget(widget)
        if session is None:
            return
        self.port.show_document_workbench()
        invalidation = self.port.document_controller.activate(session.document.id)
        if isinstance(session.document, SceneDocument):
            self.port.viewport = self.port.central_tabs.widget(index)
            if _scene_has_stage_content(session.document):
                self.port.preview_panel.set_resource(
                    session.resource_uri or f"unsaved://{session.document.id}"
                )
                self.port.preview_panel.set_mode("stage")
        elif isinstance(session.document, PatternDocument):
            self.port._active_pattern_session = session
            self.port._active_pattern_document = session.document
            self.port._active_pattern_resource = session.resource_uri or ""
            self.port.preview_panel.set_resource(
                self.port._active_pattern_resource or f"unsaved://{session.document.id}"
            )
            self.port.preview_panel.set_mode("pattern")
            if hasattr(self.port, "bottom_dock"):
                target_height = 180 if self.port.height() <= 700 else 250
                self.port.resizeDocks([self.port.bottom_dock], [target_height], Qt.Vertical)
        if not hasattr(self.port, "tree"):
            return
        self.port.apply_invalidation(session.document.id, invalidation)

    def close_central_tab(self, index: int) -> None:
        widget = self.port.central_tabs.widget(index)
        if widget is not None and bool(widget.property("runtimePreview")):
            if isinstance(widget, RuntimePreviewHost):
                widget.detach()
            self.port.central_tabs.removeTab(index)
            widget.deleteLater()
            self.port._runtime_preview_host = None
            return
        session = self.managed_for_widget(widget)
        if session is not None:
            if not self.confirm_discard(session):
                return
            if self.port._preview_session.active_document_id == session.document.id:
                self.port.preview_service.clear_stage_runtime_feedback()
                self.port._preview_session.stop()
            _removed, active, invalidation = self.port.document_controller.close(
                session.document.id,
                discard=True,
            )
            if self.port._active_pattern_session is session:
                self.port._active_pattern_session = None
                self.port._active_pattern_document = None
                self.port._active_pattern_resource = ""
            self.port._document_widgets.pop(session.document.id, None)
            self.port.central_tabs.removeTab(index)
            widget.deleteLater()
            if active is None and self.port.central_tabs.count() == 0:
                self.new_scene()
            elif active is not None:
                active_widget = self.port._document_widgets.get(
                    active.document.id
                )
                if active_widget is not None:
                    self.port.central_tabs.setCurrentWidget(active_widget)
                self.port.apply_invalidation(active.document.id, invalidation)
            return
        if widget is None or not widget.close():
            return
        plugin_id = str(widget.property("editorPluginId") or "")
        self.port.central_tabs.removeTab(index)
        if plugin_id:
            self.port._plugin_widgets.pop(plugin_id, None)
        widget.deleteLater()

    def new_scene(self) -> None:
        session, invalidation = self.port.document_controller.new_scene()
        self.add_document_tab(session)
        self.port._log("New scene")
        self.port.apply_invalidation(session.document.id, invalidation)

    def open_resource(self) -> None:
        start = self.port.project.game_content / "scenes"
        path, _ = QFileDialog.getOpenFileName(
            self.port.qt_parent,
            self.port.language_manager.translate("Open PySTG Resource"),
            str(start),
            RESOURCE_FILTER,
        )
        if not path:
            return
        self.open_document(path)

    def open_scene(self) -> None:
        """Compatibility alias retained for existing integrations."""

        self.open_resource()

    def open_document(self, resource_value: str) -> ManagedDocument | None:
        try:
            if str(resource_value).startswith("res://"):
                reference = ResourceReference.parse(resource_value)
                if reference.subresource is not None:
                    raise ResourceDocumentError(
                        "Authoring documents cannot be opened from a fragment"
                    )
                path = reference.resolve(self.port.project, must_exist=True)
            else:
                path = self.port.project.resolve(resource_value)
            session, invalidation = self.port.document_controller.open(path)
        except (
            OSError,
            DocumentError,
            DocumentManagerError,
            ResourceDocumentError,
            ValueError,
        ) as exc:
            self.port._show_error("Open failed", exc)
            return None
        self.add_document_tab(session)
        self.port._log(f"Opened {self.port.project.relative(path)}")
        self.port.apply_invalidation(session.document.id, invalidation)
        return session

    def save_scene(self) -> bool:
        return self._save_document(self.port.session)

    def save_scene_as(self) -> bool:
        return self._save_document(self.port.session, save_as=True)

    def autosave_open_documents(self) -> tuple[Path, ...]:
        """Autosave dirty, path-backed sessions to recovery sidecars."""
        written: list[Path] = []
        store = self.port.document_manager.store
        for session in tuple(self.port.document_manager):
            if not session.is_dirty or session.path is None:
                continue
            written.append(store.autosave(session.document, session.path))
        return tuple(written)

    def find_recovery_candidates(self):
        """Return sidecars that can be offered without changing open sessions."""
        return self.port.document_manager.store.recovery_candidates()

    def _save_document(
        self,
        session: ManagedDocument,
        *,
        save_as: bool = False,
    ) -> bool:
        if session.path is not None and not save_as:
            try:
                saved, invalidation = self.port.document_controller.save(
                    session.document.id
                )
            except (OSError, DocumentError, ResourceDocumentError, ValueError) as exc:
                self.port._show_error("Save failed", exc)
                return False
            self.port._log(f"Saved {self.port.project.relative(saved)}")
            if session is self.port._active_pattern_session:
                self.port._active_pattern_resource = session.resource_uri or ""
                self.port.preview_panel.set_resource(self.port._active_pattern_resource)
            if hasattr(self.port, "resource_browser"):
                self.port.resource_browser.refresh()
            self.port.apply_invalidation(session.document.id, invalidation)
            return True
        folder = "patterns" if isinstance(session.document, PatternDocument) else "scenes"
        start = self.port.project.game_content / folder
        start.mkdir(parents=True, exist_ok=True)
        suggested = start / (
            session.path.name
            if session.path
            else ("new_pattern.pystg.json" if folder == "patterns" else "untitled.pystg.json")
        )
        path, _ = QFileDialog.getSaveFileName(
            self.port.qt_parent,
            self.port.language_manager.translate("Save PySTG Resource"),
            str(suggested),
            RESOURCE_FILTER,
        )
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".pystg.json"
        try:
            saved, invalidation = self.port.document_controller.save(
                session.document.id,
                path,
            )
        except (OSError, DocumentError, ResourceDocumentError, ValueError) as exc:
            self.port._show_error("Save failed", exc)
            return False
        self.port._log(f"Saved {self.port.project.relative(saved)}")
        if session is self.port._active_pattern_session:
            self.port._active_pattern_resource = session.resource_uri or ""
            self.port.preview_panel.set_resource(self.port._active_pattern_resource)
        if hasattr(self.port, "resource_browser"):
            self.port.resource_browser.refresh()
        self.port.apply_invalidation(session.document.id, invalidation)
        return True

    def revert_document(self) -> None:
        session = self.port.session
        if session.is_dirty:
            result = QMessageBox.warning(
                self.port.qt_parent,
                self.port.language_manager.translate("Revert document"),
                self.port.language_manager.translate(
                    f"Discard all changes to {session.display_name}?"
                ),
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if result != QMessageBox.Yes:
                return
        try:
            invalidation = self.port.document_controller.revert(session.document.id)
        except (OSError, ValueError, ResourceDocumentError) as exc:
            self.port._show_error("Revert failed", exc)
            return
        self.port._selected_id = session.default_selection
        self.port._log(f"Reverted {session.display_name}")
        self.port.apply_invalidation(session.document.id, invalidation)
        self.port.preview_service.sync_active_pattern_preview()

    def close_active_document(self) -> None:
        widget = self.port._document_widgets.get(self.port.session.document.id)
        if widget is not None:
            self.close_central_tab(self.port.central_tabs.indexOf(widget))

    def confirm_discard(self, session: ManagedDocument | None = None) -> bool:
        session = session or self.port.session
        if not session.is_dirty:
            return True
        # Programmatic/offscreen smoke windows are never user-owned interactive
        # surfaces, so closing them must not open a modal dialog during teardown.
        if not self.port.isVisible():
            return True
        result = QMessageBox.warning(
            self.port.qt_parent,
            self.port.language_manager.translate("Unsaved changes"),
            self.port.language_manager.translate(
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

"""Concrete Qt main-window assembly for the PySTG editor."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Callable

from src.qt_compat.QtCore import QProcess, Qt, QTimer
from src.qt_compat.QtGui import QColor, QKeySequence
from src.qt_compat.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from src.qt_compat.QtGui import QAction
except ImportError:  # The legacy Qt binding keeps QAction in QtWidgets.
    from src.qt_compat.QtWidgets import QAction

from src.core.project_context import ProjectContext
from src.core.atomic_io import atomic_write_json
from src.authoring.registry import build_default_resource_type_registry
from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.game.background_render.document import BackgroundDocument
from src.pattern import PatternDocument, PresetLibrary, PresetResolver
from src.ui.document import UIDocument

from ..action_catalog import ActionExecutor, build_editor_action_catalog
from ..action_search import ActionSearchDialog
from src.authoring.scene.document import DocumentError, EditorNode, SceneDocument
from src.authoring.scene.node_types import build_default_node_type_registry
from ..preview_panel import PatternPreviewPanel
from ..preview import PreviewSession
from ..runtime_preview import RuntimePreviewHost
from ..document_manager import (
    DocumentManager,
    DocumentManagerError,
    ManagedDocument,
)
from ..panels.pattern_workspace import PatternWorkspace
from ..panels.ui_workspace import BackgroundWorkspace, UIWorkspace
from ..application import (
    DocumentController,
    EditorCoordinator,
    InvalidationScope,
    InvalidationSet,
    RedoIntent,
    UndoIntent,
)
from ..application.queries import find_timeline_clip, find_timeline_track
from ..panels.timeline_workspace import TimelineEditor
from ..panels.variable_workspace import VariableEditor
from ..panels.state_graph_workspace import StateGraphEditor
from ..i18n import (
    LANGUAGE_CHINESE,
    LANGUAGE_ENGLISH,
    LanguageManager,
    translate_widget_tree,
)
from ..plugins import EditorPluginRegistry
from ..panels.inspector_panel import InspectorPanel
from ..main_window_support import APP_NAME, build_preview_command
from ..panels.scene_view import NodeGraphicsItem, SceneTreeWidget, SceneViewport
from ..main_window_authoring import AuthoringService
from ..main_window_documents import DocumentService
from ..main_window_pattern import PatternService
from ..main_window_preview import PreviewService
from ..main_window_scene_edit import SceneEditService
from ..main_window_timeline import TimelineService
from ..main_window_ui_docs import UIDocumentService
from ..main_window_workbench import WorkbenchService
from ..state import RuntimeOverlayState
from .actions import ShellActions
from .docks import ShellDocks
from .lifecycle import ShellLifecycle
from .ports import (
    AuthoringPort,
    DocumentPort,
    PatternPort,
    PreviewPort,
    SceneEditPort,
    TimelinePort,
    UIDocumentPort,
    WorkbenchPort,
    ActionsPort,
    DocksPort,
    LifecyclePort,
)

# ``build_preview_command`` and ``NodeGraphicsItem`` now live in the modules split
# out of this file; they stay importable from here because the editor tests and
# the native gates address them as ``src.editor.app`` attributes.
__all__ = [
    "EditorMainWindow",
    "InspectorPanel",
    "NodeGraphicsItem",
    "SceneViewport",
    "build_preview_command",
]


class EditorMainWindow(QMainWindow):
    """The editor shell: window chrome, selection state and the refresh loop.

    Domain requests are handled by a Qt-free coordinator.  The declarations
    below are an explicit compatibility port: each public shell callback names
    exactly one service implementation at class-definition time.  There is no
    runtime method injection and services never proxy arbitrary window state.
    """

    def __init__(self, project: ProjectContext):
        super().__init__()
        self.project = project
        self.language_manager = LanguageManager(self)
        self.language_manager.languageChanged.connect(self._language_changed)
        # These resource/node type registries are the same objects wired into
        # the document manager below and, through the plugin facade, into the
        # SDK registry -- so plugin-contributed types land where scene
        # validation reads them.  Never replace them with a detached copy.
        self.resource_type_registry = build_default_resource_type_registry()
        self.node_type_registry = build_default_node_type_registry()
        self.document_manager = DocumentManager(
            project,
            registry=self.resource_type_registry,
            node_registry=self.node_type_registry,
        )
        self.editor_coordinator = EditorCoordinator(self.document_manager)
        self.document_controller = DocumentController(
            self.document_manager,
            history_reset=self.editor_coordinator.reset_document_history,
        )
        # Real service instances form the shell composition boundary.
        # Qt signals below connect to these objects directly; the window does not
        # transplant their methods into its own class surface.
        self.authoring_service = AuthoringService(AuthoringPort(self))
        self.document_service = DocumentService(DocumentPort(self))
        self.pattern_service = PatternService(PatternPort(self))
        self.preview_service = PreviewService(PreviewPort(self))
        self.scene_edit_service = SceneEditService(SceneEditPort(self))
        self.timeline_service = TimelineService(TimelinePort(self))
        self.ui_document_service = UIDocumentService(UIDocumentPort(self))
        self.workbench_service = WorkbenchService(WorkbenchPort(self))
        self.actions_service = ShellActions(ActionsPort(self))
        self.docks_service = ShellDocks(DocksPort(self))
        self.lifecycle_service = ShellLifecycle(LifecyclePort(self))
        self._fallback_selected_id = ""
        self._selected_id = self.session.document.root.id
        self._syncing_selection = False
        self._preview_session = PreviewSession(project, parent=self)
        self._active_pattern_document: PatternDocument | None = None
        self._active_pattern_session: ManagedDocument | None = None
        self._active_pattern_resource = ""
        self._preset_library = self._load_builtin_preset_library()
        self._preset_resolver = PresetResolver(self._preset_library.presets)
        self.editor_coordinator.preset_resolver = self._preset_resolver
        self.action_catalog = build_editor_action_catalog(
            presets=self._preset_library.presets,
            node_registry=self.node_type_registry,
        )
        self.action_executor = ActionExecutor()
        self.action_executor.register("apply_preset", self.workbench_service.execute_preset_action)
        self.action_executor.register("add_graph_node", self.workbench_service.execute_graph_action)
        self.action_executor.register("add_timeline_track", self.workbench_service.execute_track_action)
        self.action_executor.register("add_timeline_clip", self.workbench_service.execute_clip_action)
        self.action_executor.register("add_scene_node", self.workbench_service.execute_scene_action)
        self._action_search_dialog: ActionSearchDialog | None = None
        self._runtime_preview_host: RuntimePreviewHost | None = None
        self._sdk_plugins_deactivated = False
        self._tool_processes: dict[str, QProcess] = {}
        self._plugin_widgets: dict[str, QWidget] = {}
        self._document_widgets: dict[str, QWidget] = {}
        self._bottom_dock_resize_guard = False
        # One plugin-contribution facade: it owns the Qt view catalog (built-in
        # tool widgets) and, composed inside it, the transactional SDK registry
        # for project-local contributions.  The SDK registry receives the same
        # resource/node type registries wired into DocumentManager above.  The
        # window reaches the SDK surface via ``self.plugin_registry.sdk`` -- no
        # second window attribute mirrors it (ER5 hard metric).
        self.plugin_registry = EditorPluginRegistry(
            project,
            resource_types=self.resource_type_registry,
            node_types=self.node_type_registry,
        )
        self.workbench_service.register_plugins()
        self.actions_service.build_actions()
        self.docks_service.build_ui()
        self.workbench_service.discover_sdk_plugins()
        self.preview_service.connect_pattern_preview()
        self.docks_service.apply_theme()
        self.apply_invalidation(
            self.session.document.id,
            self.document_controller.initial_sync(),
        )
        self.resize(1480, 920)
        self.setMinimumSize(960, 640)

    @property
    def _pattern_preview_client(self):
        """The formal NDJSON preview client owned by the preview session.

        Exposed as a property so the single owner stays :class:`PreviewSession`
        while the slot code (and the editor tests that swap in a fake) keep
        addressing it as ``self._pattern_preview_client``.
        """

        return self._preview_session.formal_client

    @_pattern_preview_client.setter
    def _pattern_preview_client(self, client) -> None:
        self._preview_session.formal_client = client

    def _load_builtin_preset_library(self) -> PresetLibrary:
        path = self.project.root / "game_content" / "presets" / "builtin_patterns.pystg.json"
        if not path.is_file():
            path = Path(__file__).resolve().parents[3] / "game_content" / "presets" / "builtin_patterns.pystg.json"
        return PresetLibrary.load(path)

    # Stable top-level shell ports used by menu actions, app integrations and
    # existing editor automation.  Domain behavior remains on the composed
    # services; these methods deliberately contain no authoring logic.
    def new_scene(self) -> None:
        self.document_service.new_scene()

    def new_pattern(self) -> None:
        self.pattern_service.new_pattern()

    def open_resource(self) -> None:
        self.document_service.open_resource()

    def open_scene(self) -> None:
        self.document_service.open_scene()

    def save_scene(self) -> None:
        self.document_service.save_scene()

    def save_scene_as(self) -> None:
        self.document_service.save_scene_as()

    def autosave_open_documents(self) -> None:
        self.document_service.autosave_open_documents()

    def find_recovery_candidates(self):
        return self.document_service.find_recovery_candidates()

    def revert_document(self) -> None:
        self.document_service.revert_document()

    def close_active_document(self) -> None:
        self.document_service.close_active_document()

    def run_preview(self) -> None:
        self.preview_service.run_preview()

    def add_node(self, node_type: str) -> None:
        self.scene_edit_service.add_node(node_type)

    def create_simple_spell_flow(self) -> None:
        self.scene_edit_service.create_simple_spell_flow()

    def create_stage_template(self, template_id: str = "two_phase_boss") -> None:
        self.scene_edit_service.create_stage_template(template_id)

    def delete_selected(self) -> None:
        self.scene_edit_service.delete_selected()

    def rename_selected(self) -> None:
        self.scene_edit_service.rename_selected()

    def rename_node(self, node_id: str, name: str) -> None:
        self.scene_edit_service.rename_node(node_id, name)

    def set_node_property(self, node_id: str, key: str, value: object) -> None:
        self.scene_edit_service.set_node_property(node_id, key, value)

    def move_selected(self, delta: int) -> None:
        self.scene_edit_service.move_selected(delta)

    def indent_selected(self) -> None:
        self.scene_edit_service.indent_selected()

    def outdent_selected(self) -> None:
        self.scene_edit_service.outdent_selected()

    def open_plugin(self, plugin_id: str) -> None:
        self.workbench_service.open_plugin(plugin_id)

    def resizeEvent(self, event) -> None:
        """Keep the bottom workbench compact at the editor's minimum size.

        The left and right authoring docks now share their columns as tabs, so
        the bottom panel no longer has to collapse to a tab strip at the
        supported 960x640 size.  Keep enough height for both timeline toolbars
        and at least one editable track.
        """
        super().resizeEvent(event)
        if not hasattr(self, "bottom_dock") or self._bottom_dock_resize_guard:
            return
        target_height = 230 if self.height() <= 700 else 220
        if abs(self.bottom_dock.height() - target_height) < 8:
            return
        self._bottom_dock_resize_guard = True
        try:
            self.resizeDocks([self.bottom_dock], [target_height], Qt.Vertical)
        finally:
            self._bottom_dock_resize_guard = False

    @property
    def language(self) -> str:
        """Return the current UI language code."""

        return self.language_manager.language

    def set_language(self, language: str) -> None:
        return self.lifecycle_service.set_language(language)

    def _language_changed(self, _language: str) -> None:
        # Refresh the existing editor context so dynamically rebuilt Inspector
        # forms and newly opened workspaces receive the same language as the
        # shell.  No document command is issued by this path.
        return self.lifecycle_service.language_changed(_language)

    def _update_language_actions(self) -> None:
        return self.lifecycle_service.update_language_actions()

    @property
    def session(self) -> ManagedDocument:
        session = self.document_manager.active
        if session is None:
            raise DocumentManagerError("No active document")
        return session

    @property
    def _selected_id(self) -> str:
        session = self.document_manager.active
        if session is None:
            return self._fallback_selected_id
        return session.editor_state.selection.node_id or session.default_selection

    @_selected_id.setter
    def _selected_id(self, value: str) -> None:
        self._fallback_selected_id = str(value)
        session = self.document_manager.active
        if session is not None:
            session.editor_state.selection.node_id = str(value)

    @property
    def runtime_overlay(self) -> RuntimeOverlayState | None:
        """Return the latest immutable formal-preview feedback snapshot."""

        return self._preview_session.runtime_overlay

    @property
    def _active_stage_session(self) -> ManagedDocument | None:
        owner_id = self._preview_session.active_document_id
        return next(
            (
                candidate
                for candidate in self.document_manager
                if candidate.document.id == owner_id
            ),
            None,
        )

    @_active_stage_session.setter
    def _active_stage_session(self, session: ManagedDocument | None) -> None:
        if session is None:
            self._preview_session.stop()
            return
        self._preview_session.bind_runtime_feedback(
            session.document.id,
            resource_id=session.resource_uri or f"unsaved://{session.document.id}",
        )

    @property
    def _preview_mode(self) -> str:
        return self._preview_session.runtime_mode

    @_preview_mode.setter
    def _preview_mode(self, mode: str) -> None:
        owner_id = self._preview_session.active_document_id
        if owner_id is not None:
            self._preview_session.bind_runtime_feedback(owner_id, runtime_mode=mode)

    @property
    def _preview_state(self) -> str:
        return self._preview_session.runtime_state

    @_preview_state.setter
    def _preview_state(self, state: str) -> None:
        owner_id = self._preview_session.active_document_id
        if owner_id is not None:
            self._preview_session.bind_runtime_feedback(owner_id, runtime_state=state)

    @property
    def _preview_loaded_resource_id(self) -> str | None:
        return self._preview_session.loaded_resource_id

    @_preview_loaded_resource_id.setter
    def _preview_loaded_resource_id(self, resource_id: str | None) -> None:
        owner_id = self._preview_session.active_document_id
        if owner_id is not None and resource_id is not None:
            self._preview_session.bind_runtime_feedback(
                owner_id,
                loaded_resource_id=resource_id,
            )

    def _runtime_overlay_for(
        self, session: ManagedDocument
    ) -> RuntimeOverlayState | None:
        overlay = self._preview_session.runtime_overlay
        if overlay is None or overlay.document_id != session.document.id:
            return None
        return overlay

    def _refresh_node_add_menu(self) -> None:
        return self.actions_service.refresh_node_add_menu()

    def _build_actions(self) -> None:
        return self.actions_service.build_actions()

    def _action(self, text: str, shortcut, callback: Callable) -> QAction:
        return self.actions_service.action(text, shortcut, callback)

    def _build_ui(self) -> None:
        return self.docks_service.build_ui()

    def _build_menus(self) -> None:
        return self.actions_service.build_menus()

    def _build_main_toolbar(self) -> None:
        return self.actions_service.build_main_toolbar()

    def _build_central_tabs(self) -> None:
        return self.docks_service.build_central_tabs()

    def _build_scene_dock(self) -> None:
        return self.docks_service.build_scene_dock()

    def _build_state_graph_dock(self) -> None:
        return self.docks_service.build_state_graph_dock()

    def _build_inspector_dock(self) -> None:
        return self.docks_service.build_inspector_dock()

    def _build_variables_dock(self) -> None:
        return self.docks_service.build_variables_dock()

    def _build_bottom_dock(self) -> None:
        return self.docks_service.build_bottom_dock()

    def _apply_theme(self) -> None:
        return self.docks_service.apply_theme()

    def _populate_tree(self) -> None:
        return self.docks_service.populate_tree()

    def _find_tree_item(self, node_id: str) -> QTreeWidgetItem | None:
        return self.docks_service.find_tree_item(node_id)

    def _refresh(self) -> None:
        return self.docks_service.refresh()

    def apply_invalidation(
        self,
        document_id: str,
        invalidation: InvalidationSet,
    ) -> None:
        return self.docks_service.apply_invalidation(document_id, invalidation)

    def _refresh_active_inspector(self, document) -> None:
        return self.docks_service.refresh_active_inspector(document)

    def _refresh_active_timeline(self, document) -> None:
        return self.docks_service.refresh_active_timeline(document)

    def _refresh_active_state_graph(self, document) -> None:
        return self.docks_service.refresh_active_state_graph(document)

    def _refresh_active_variables(self, document) -> None:
        return self.docks_service.refresh_active_variables(document)

    def _refresh_scene_document(self, document: SceneDocument, widget) -> None:
        return self.docks_service.refresh_scene_document(document, widget)

    def _refresh_foreign_document(self, document, widget) -> None:
        return self.docks_service.refresh_foreign_document(document, widget)

    def _apply_pattern_document_view(
        self,
        session: ManagedDocument,
        widget: PatternWorkspace,
    ) -> None:
        return self.docks_service.apply_pattern_document_view(session, widget)

    def _sync_document_docks(self, document) -> None:
        return self.docks_service.sync_document_docks(document)

    def _update_actions(self) -> None:
        return self.actions_service.update_actions()

    def _update_title(self) -> None:
        return self.docks_service.update_title()

    def _log(self, message: str) -> None:
        return self.docks_service.log(message)

    def undo(self) -> bool:
        invalidation = self.editor_coordinator.dispatch(
            UndoIntent(self.session.document.id)
        )
        if invalidation.scopes:
            self._log("Undo")
            self.apply_invalidation(self.session.document.id, invalidation)
            self.preview_service.sync_active_pattern_preview()
            self.preview_service.sync_active_stage_preview()
        return bool(invalidation.scopes)

    def redo(self) -> bool:
        invalidation = self.editor_coordinator.dispatch(
            RedoIntent(self.session.document.id)
        )
        if invalidation.scopes:
            self._log("Redo")
            self.apply_invalidation(self.session.document.id, invalidation)
            self.preview_service.sync_active_pattern_preview()
            self.preview_service.sync_active_stage_preview()
        return bool(invalidation.scopes)

    def _fit_viewport(self) -> None:
        return self.docks_service.fit_viewport()

    def save_layout(self, path: str | Path) -> Path:
        return self.lifecycle_service.save_layout(path)

    def restore_layout(self, path: str | Path) -> None:
        return self.lifecycle_service.restore_layout(path)

    def _show_error(self, title: str, error: Exception) -> None:
        return self.docks_service.show_error(title, error)

    def closeEvent(self, event) -> None:
        for session in tuple(self.document_manager):
            if not self.document_service.confirm_discard(session):
                event.ignore()
                return
        for index in range(self.central_tabs.count() - 1, -1, -1):
            widget = self.central_tabs.widget(index)
            if self.document_service.managed_for_widget(widget) is not None:
                continue
            if widget is not None and not widget.close():
                event.ignore()
                return
        self.preview_service.clear_stage_runtime_feedback()
        self._preview_session.close()
        for process in tuple(self._tool_processes.values()):
            if process.state() == QProcess.NotRunning:
                continue
            process.terminate()
            if not process.waitForFinished(1500):
                process.kill()
        if not self._sdk_plugins_deactivated:
            self.plugin_registry.shutdown()
            self._sdk_plugins_deactivated = True
        event.accept()

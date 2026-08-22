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

    _submit_authoring_intent = AuthoringService._submit_authoring_intent
    _state_graph_state_selected = AuthoringService._state_graph_state_selected
    _variable_add_requested = AuthoringService._variable_add_requested
    _variable_delete_requested = AuthoringService._variable_delete_requested
    _variable_edit_requested = AuthoringService._variable_edit_requested
    _variable_binding_requested = AuthoringService._variable_binding_requested
    _variable_specs = staticmethod(AuthoringService._variable_specs)
    _mapping_collection = staticmethod(AuthoringService._mapping_collection)
    _variable_mapping_requested = AuthoringService._variable_mapping_requested
    _apply_variable_mapping_changes = AuthoringService._apply_variable_mapping_changes
    _state_graph_add_state = AuthoringService._state_graph_add_state
    _state_graph_rename_state = AuthoringService._state_graph_rename_state
    _state_graph_duplicate_state = AuthoringService._state_graph_duplicate_state
    _state_graph_delete_state = AuthoringService._state_graph_delete_state
    _state_graph_move_state = AuthoringService._state_graph_move_state
    _state_graph_add_transition = AuthoringService._state_graph_add_transition
    _state_graph_edit_transition = AuthoringService._state_graph_edit_transition
    _state_graph_delete_transition = AuthoringService._state_graph_delete_transition

    _add_document_tab = DocumentService._add_document_tab
    _managed_for_widget = DocumentService._managed_for_widget
    _central_tab_changed = DocumentService._central_tab_changed
    _close_central_tab = DocumentService._close_central_tab
    new_scene = DocumentService.new_scene
    open_resource = DocumentService.open_resource
    open_scene = DocumentService.open_scene
    _open_document = DocumentService._open_document
    save_scene = DocumentService.save_scene
    save_scene_as = DocumentService.save_scene_as
    autosave_open_documents = DocumentService.autosave_open_documents
    find_recovery_candidates = DocumentService.find_recovery_candidates
    _save_document = DocumentService._save_document
    revert_document = DocumentService.revert_document
    close_active_document = DocumentService.close_active_document
    _confirm_discard = DocumentService._confirm_discard

    _submit_pattern_intent = PatternService._submit_pattern_intent
    new_pattern = PatternService.new_pattern
    _pattern_property_requested = PatternService._pattern_property_requested
    _graph_mode_changed = PatternService._graph_mode_changed
    _pattern_level_requested = PatternService._pattern_level_requested
    _pattern_binding_requested = PatternService._pattern_binding_requested
    _pattern_binding_remove_requested = PatternService._pattern_binding_remove_requested
    _pattern_source_navigate_requested = PatternService._pattern_source_navigate_requested
    _graph_expand_requested = PatternService._graph_expand_requested
    _graph_fold_requested = PatternService._graph_fold_requested
    _graph_node_selected = PatternService._graph_node_selected
    _graph_node_property_requested = PatternService._graph_node_property_requested
    _graph_node_position_requested = PatternService._graph_node_position_requested
    _graph_node_create_requested = PatternService._graph_node_create_requested
    _graph_edge_requested = PatternService._graph_edge_requested
    _graph_node_remove_requested = PatternService._graph_node_remove_requested
    _graph_edge_remove_requested = PatternService._graph_edge_remove_requested
    _apply_graph_diagnostics = PatternService._apply_graph_diagnostics
    _clear_graph_diagnostics = PatternService._clear_graph_diagnostics
    _apply_pattern_properties = PatternService._apply_pattern_properties
    _apply_pattern_template = PatternService._apply_pattern_template
    _preset_parameter_requested = PatternService._preset_parameter_requested
    _preset_slot_requested = PatternService._preset_slot_requested
    _preset_migrate_requested = PatternService._preset_migrate_requested
    _preset_materialize_requested = PatternService._preset_materialize_requested
    _pattern_origin_requested = PatternService._pattern_origin_requested
    _pattern_player_requested = PatternService._pattern_player_requested

    _connect_pattern_preview = PreviewService._connect_pattern_preview
    _ensure_runtime_preview_host = PreviewService._ensure_runtime_preview_host
    _show_runtime_preview_host = PreviewService._show_runtime_preview_host
    _preview_running_changed = PreviewService._preview_running_changed
    _clear_stage_runtime_feedback = PreviewService._clear_stage_runtime_feedback
    _open_pattern_preview = PreviewService._open_pattern_preview
    _launch_active_preview = PreviewService._launch_active_preview
    _launch_active_stage_preview = PreviewService._launch_active_stage_preview
    _launch_active_pattern_preview = PreviewService._launch_active_pattern_preview
    _send_pattern_preview_command = PreviewService._send_pattern_preview_command
    _sync_active_pattern_preview = PreviewService._sync_active_pattern_preview
    _sync_active_stage_preview = PreviewService._sync_active_stage_preview
    _handle_pattern_preview_event = PreviewService._handle_pattern_preview_event
    _sync_stage_runtime_feedback = PreviewService._sync_stage_runtime_feedback
    _handle_pattern_preview_issue = PreviewService._handle_pattern_preview_issue
    run_preview = PreviewService.run_preview
    _preview_finished = PreviewService._preview_finished

    _submit_scene_intent = SceneEditService._submit_scene_intent
    _select_from_tree = SceneEditService._select_from_tree
    _select_from_viewport = SceneEditService._select_from_viewport
    _tree_item_changed = SceneEditService._tree_item_changed
    _move_from_tree = SceneEditService._move_from_tree
    _set_node_position = SceneEditService._set_node_position
    add_node = SceneEditService.add_node
    create_simple_spell_flow = SceneEditService.create_simple_spell_flow
    create_stage_template = SceneEditService.create_stage_template
    delete_selected = SceneEditService.delete_selected
    rename_selected = SceneEditService.rename_selected
    rename_node = SceneEditService.rename_node
    set_node_property = SceneEditService.set_node_property
    move_selected = SceneEditService.move_selected
    indent_selected = SceneEditService.indent_selected
    outdent_selected = SceneEditService.outdent_selected

    _dispatch_timeline_intent = TimelineService._dispatch_timeline_intent
    _timeline_add_track = TimelineService._timeline_add_track
    _timeline_track_selected = TimelineService._timeline_track_selected
    _timeline_reactive_navigate = TimelineService._timeline_reactive_navigate
    _timeline_track_properties_requested = TimelineService._timeline_track_properties_requested
    _timeline_delete_track = TimelineService._timeline_delete_track
    _timeline_move_track = TimelineService._timeline_move_track
    _timeline_mute_track = TimelineService._timeline_mute_track
    _timeline_add_clip = TimelineService._timeline_add_clip
    _timeline_add_keyframe = TimelineService._timeline_add_keyframe
    _timeline_delete_keyframe = TimelineService._timeline_delete_keyframe
    _timeline_keyframe_geometry = TimelineService._timeline_keyframe_geometry
    _timeline_clip_geometry = TimelineService._timeline_clip_geometry
    _timeline_duplicate_clip = TimelineService._timeline_duplicate_clip
    _timeline_delete_clip = TimelineService._timeline_delete_clip
    _timeline_clip_selected = TimelineService._timeline_clip_selected
    _timeline_clip_properties_requested = TimelineService._timeline_clip_properties_requested
    _timeline_keyframe_properties_requested = TimelineService._timeline_keyframe_properties_requested
    _timeline_playhead_changed = TimelineService._timeline_playhead_changed
    _timeline_zoom_changed = TimelineService._timeline_zoom_changed

    _active_document = UIDocumentService._active_document
    _submit_ui_document_intent = UIDocumentService._submit_ui_document_intent
    _submit_background_intent = UIDocumentService._submit_background_intent
    _apply_ui_document_view_if_alive = UIDocumentService._apply_ui_document_view_if_alive
    _apply_ui_document_view = UIDocumentService._apply_ui_document_view
    _ui_node_selected = UIDocumentService._ui_node_selected
    _ui_node_create_requested = UIDocumentService._ui_node_create_requested
    _ui_node_remove_requested = UIDocumentService._ui_node_remove_requested
    _ui_node_property_requested = UIDocumentService._ui_node_property_requested
    _ui_node_geometry_requested = UIDocumentService._ui_node_geometry_requested
    _ui_resource_dropped = UIDocumentService._ui_resource_dropped
    _background_layer_selected = UIDocumentService._background_layer_selected
    _background_property_requested = UIDocumentService._background_property_requested
    _background_layer_transform_requested = UIDocumentService._background_layer_transform_requested
    _background_layer_create_requested = UIDocumentService._background_layer_create_requested
    _background_layer_remove_requested = UIDocumentService._background_layer_remove_requested
    _background_binding_requested = UIDocumentService._background_binding_requested
    _ui_viewport_changed = UIDocumentService._ui_viewport_changed

    _open_scene_action_search = WorkbenchService._open_scene_action_search
    _open_action_search = WorkbenchService._open_action_search
    _execute_action = WorkbenchService._execute_action
    _execute_preset_action = WorkbenchService._execute_preset_action
    _execute_graph_action = WorkbenchService._execute_graph_action
    _execute_track_action = WorkbenchService._execute_track_action
    _execute_clip_action = WorkbenchService._execute_clip_action
    _execute_scene_action = WorkbenchService._execute_scene_action
    _register_plugins = WorkbenchService._register_plugins
    _discover_sdk_plugins = WorkbenchService._discover_sdk_plugins
    _create_bullet_alias_editor = staticmethod(WorkbenchService._create_bullet_alias_editor)
    open_plugin = WorkbenchService.open_plugin
    _start_external_plugin = WorkbenchService._start_external_plugin
    _read_tool_output = WorkbenchService._read_tool_output
    _tool_finished = WorkbenchService._tool_finished
    _resource_selected = WorkbenchService._resource_selected
    _resource_activated = WorkbenchService._resource_activated
    _resource_dropped = WorkbenchService._resource_dropped
    _add_sprite_resource = WorkbenchService._add_sprite_resource
    _log_scene_diagnostics = WorkbenchService._log_scene_diagnostics
    _diagnostic_link_clicked = WorkbenchService._diagnostic_link_clicked

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
        self.action_executor.register("apply_preset", self._execute_preset_action)
        self.action_executor.register("add_graph_node", self._execute_graph_action)
        self.action_executor.register("add_timeline_track", self._execute_track_action)
        self.action_executor.register("add_timeline_clip", self._execute_clip_action)
        self.action_executor.register("add_scene_node", self._execute_scene_action)
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
        self._register_plugins()
        self._build_actions()
        self._build_ui()
        self._discover_sdk_plugins()
        self._connect_pattern_preview()
        self._apply_theme()
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
        """Switch UI labels without changing document or runtime data."""

        self.language_manager.set_language(language)

    def _language_changed(self, _language: str) -> None:
        # Refresh the existing editor context so dynamically rebuilt Inspector
        # forms and newly opened workspaces receive the same language as the
        # shell.  No document command is issued by this path.
        if hasattr(self, "tree"):
            self.state_graph.set_language_manager(self.language_manager)
            self.inspector.set_language_manager(self.language_manager)
            self.timeline.set_language_manager(self.language_manager)
            for widget in self._document_widgets.values():
                if isinstance(widget, PatternWorkspace):
                    widget.set_language_manager(self.language_manager)
                    widget.set_available_presets(self._preset_library.presets)
        translate_widget_tree(self, self.language_manager)
        runtime_host = getattr(self, "_runtime_preview_host", None)
        if runtime_host is not None:
            index = self.central_tabs.indexOf(runtime_host)
            if index >= 0:
                self.central_tabs.setTabText(
                    index,
                    self.language_manager.translate("Runtime Preview"),
                )
        self._update_language_actions()
        if hasattr(self, "central_tabs"):
            self._update_title()

    def _update_language_actions(self) -> None:
        english = self.language == LANGUAGE_ENGLISH
        self.action_language_english.setChecked(english)
        self.action_language_chinese.setChecked(not english)

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
        """Expose newly activated SDK node contributions in the shell menu."""
        menu = getattr(self, "_node_add_menu", None)
        if menu is None:
            return
        for type_name, spec in self.node_type_registry.items():
            if type_name == "SceneRoot" or type_name in self._node_menu_types:
                continue
            action = menu.addAction(spec.display_name)
            action.triggered.connect(
                lambda checked=False, node_type=type_name: self.add_node(node_type)
            )
            self._node_menu_types.add(type_name)

    def _build_actions(self) -> None:
        self.action_new = self._action("New Scene", QKeySequence.New, self.new_scene)
        self.action_new_pattern = self._action("New Pattern", "Ctrl+Shift+N", self.new_pattern)
        self.action_open = self._action("Open Resource…", QKeySequence.Open, self.open_resource)
        self.action_save = self._action("Save", QKeySequence.Save, self.save_scene)
        self.action_save_as = self._action("Save As…", QKeySequence.SaveAs, self.save_scene_as)
        self.action_revert = self._action("Revert", None, self.revert_document)
        self.action_close_document = self._action("Close Document", QKeySequence.Close, self.close_active_document)
        self.action_undo = self._action("Undo", QKeySequence.Undo, self.undo)
        self.action_redo = self._action("Redo", QKeySequence.Redo, self.redo)
        self.action_delete = self._action("Delete Node", QKeySequence.Delete, self.delete_selected)
        self.action_rename = self._action("Rename Node", Qt.Key_F2, self.rename_selected)
        self.action_move_up = self._action("Move Up", "Alt+Up", lambda: self.move_selected(-1))
        self.action_move_down = self._action("Move Down", "Alt+Down", lambda: self.move_selected(1))
        self.action_outdent = self._action("Move to Parent", "Alt+Left", self.outdent_selected)
        self.action_indent = self._action("Make Child of Previous", "Alt+Right", self.indent_selected)
        self.action_run = self._action("Run / Preview", Qt.Key_F6, self.run_preview)
        self.action_fit = self._action("Frame Canvas", "F", self._fit_viewport)
        self.action_language_english = self._action(
            "English",
            None,
            lambda checked=False: self.set_language(LANGUAGE_ENGLISH),
        )
        self.action_language_english.setCheckable(True)
        self.action_language_chinese = self._action(
            "简体中文",
            None,
            lambda checked=False: self.set_language(LANGUAGE_CHINESE),
        )
        self.action_language_chinese.setCheckable(True)

    def _action(self, text: str, shortcut, callback: Callable) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        self.addAction(action)
        return action

    def _build_ui(self) -> None:
        self._build_menus()
        self._build_main_toolbar()
        self._build_central_tabs()
        self._build_scene_dock()
        self._build_state_graph_dock()
        self._build_inspector_dock()
        self._build_variables_dock()
        self._build_bottom_dock()
        self.statusBar().showMessage(str(self.project.root))

    def _build_menus(self) -> None:
        """Populate the menu bar (File/Edit/Run/Tools/Language)."""
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions([
            self.action_new,
            self.action_new_pattern,
            self.action_open,
            self.action_save,
            self.action_save_as,
            self.action_revert,
            self.action_close_document,
        ])
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([
            self.action_undo,
            self.action_redo,
            self.action_rename,
            self.action_delete,
            self.action_move_up,
            self.action_move_down,
            self.action_outdent,
            self.action_indent,
        ])
        run_menu = self.menuBar().addMenu("&Run")
        run_menu.addActions([self.action_run, self.action_fit])
        tools_menu = self.menuBar().addMenu("&Tools")
        for plugin in self.plugin_registry.all():
            action = tools_menu.addAction(plugin.title)
            action.setObjectName(f"pluginAction_{plugin.id}")
            action.setToolTip(plugin.description)
            if plugin.shortcut:
                action.setShortcut(plugin.shortcut)
            action.triggered.connect(
                lambda checked=False, plugin_id=plugin.id: self.open_plugin(plugin_id)
            )

        self.language_menu = self.menuBar().addMenu("&Language")
        self.language_menu.addActions(
            [self.action_language_english, self.action_language_chinese]
        )

    def _build_main_toolbar(self) -> None:
        """Assemble the main toolbar."""
        main_toolbar = QToolBar("Main", self)
        self.main_toolbar = main_toolbar
        main_toolbar.setObjectName("mainToolbar")
        main_toolbar.setMovable(False)
        main_toolbar.addActions([
            self.action_new,
            self.action_open,
            self.action_save,
        ])
        main_toolbar.addSeparator()
        main_toolbar.addActions([self.action_undo, self.action_redo])
        main_toolbar.addSeparator()
        main_toolbar.addAction(self.action_run)
        self.addToolBar(main_toolbar)

    def _build_central_tabs(self) -> None:
        """Create the central document tab widget."""
        self.central_tabs = QTabWidget()
        self.central_tabs.setObjectName("centralWorkbench")
        self.central_tabs.setTabsClosable(True)
        self.central_tabs.tabCloseRequested.connect(self._close_central_tab)
        self.central_tabs.currentChanged.connect(self._central_tab_changed)
        initial_widget = self._add_document_tab(self.session)
        self.viewport = initial_widget
        self.setCentralWidget(self.central_tabs)

    def _build_scene_dock(self) -> None:
        """Build the Scene hierarchy dock."""
        self.tree = SceneTreeWidget()
        self.tree.currentItemChanged.connect(self._select_from_tree)
        self.tree.itemChanged.connect(self._tree_item_changed)
        self.tree.nodeMoveRequested.connect(self._move_from_tree)

        tree_content = QWidget()
        tree_layout = QVBoxLayout(tree_content)
        tree_layout.setContentsMargins(4, 4, 4, 4)
        tree_buttons = QHBoxLayout()
        add_button = QToolButton()
        add_button.setText("+ Add")
        add_button.setPopupMode(QToolButton.InstantPopup)
        add_menu = QMenu(add_button)
        quick_flow = add_menu.addAction("Simple Spell Setup")
        quick_flow.setObjectName("addSimpleSpellFlow")
        quick_flow.triggered.connect(self.create_simple_spell_flow)
        midstage = add_menu.addAction("Midstage Skeleton")
        midstage.setObjectName("addMidstageSkeleton")
        midstage.triggered.connect(lambda: self.create_stage_template("midstage"))
        boss = add_menu.addAction("Two-phase Boss Skeleton")
        boss.setObjectName("addTwoPhaseBossSkeleton")
        boss.triggered.connect(
            lambda: self.create_stage_template("two_phase_boss")
        )
        add_menu.addSeparator()
        self._node_add_menu = add_menu
        self._node_menu_types: set[str] = set()
        for type_name, spec in self.node_type_registry.items():
            if type_name == "SceneRoot":
                continue
            action = add_menu.addAction(spec.display_name)
            self._node_menu_types.add(type_name)
            action.triggered.connect(
                lambda checked=False, node_type=type_name: self.add_node(node_type)
            )
        add_button.setMenu(add_menu)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.delete_selected)
        tree_buttons.addWidget(add_button)
        tree_buttons.addWidget(delete_button)
        tree_buttons.addStretch()
        tree_layout.addLayout(tree_buttons)
        hierarchy_buttons = QHBoxLayout()
        for text, tooltip, action in (
            ("↑", "Move up (Alt+Up)", self.action_move_up),
            ("↓", "Move down (Alt+Down)", self.action_move_down),
            ("←", "Move to parent (Alt+Left)", self.action_outdent),
            ("→", "Make child of previous node (Alt+Right)", self.action_indent),
        ):
            button = QToolButton()
            button.setText(text)
            button.setFixedWidth(44)
            button.setToolTip(tooltip)
            button.clicked.connect(
                lambda checked=False, target=action: target.trigger()
            )
            hierarchy_buttons.addWidget(button)
        hierarchy_buttons.addStretch()
        tree_layout.addLayout(hierarchy_buttons)
        tree_layout.addWidget(self.tree)

        tree_dock = QDockWidget("Scene", self)
        self.scene_dock = tree_dock
        tree_dock.setObjectName("sceneDock")
        tree_dock.setWidget(tree_content)
        tree_dock.setMinimumWidth(220)
        self.addDockWidget(Qt.LeftDockWidgetArea, tree_dock)

    def _build_state_graph_dock(self) -> None:
        """Build the State Flow dock, tabbed behind Scene."""
        self.state_graph = StateGraphEditor()
        self.state_graph.set_language_manager(self.language_manager)
        self.state_graph.stateSelected.connect(self._state_graph_state_selected)
        self.state_graph.addStateRequested.connect(self._state_graph_add_state)
        self.state_graph.renameStateRequested.connect(self._state_graph_rename_state)
        self.state_graph.duplicateStateRequested.connect(
            self._state_graph_duplicate_state
        )
        self.state_graph.deleteStateRequested.connect(self._state_graph_delete_state)
        self.state_graph.moveStateRequested.connect(self._state_graph_move_state)
        self.state_graph.addTransitionRequested.connect(
            self._state_graph_add_transition
        )
        self.state_graph.editTransitionRequested.connect(
            self._state_graph_edit_transition
        )
        self.state_graph.deleteTransitionRequested.connect(
            self._state_graph_delete_transition
        )
        state_graph_dock = QDockWidget("State Flow", self)
        self.state_graph_dock = state_graph_dock
        state_graph_dock.setObjectName("stateGraphDock")
        state_graph_dock.setWidget(self.state_graph)
        state_graph_dock.setMinimumWidth(240)
        self.addDockWidget(Qt.LeftDockWidgetArea, state_graph_dock)
        self.tabifyDockWidget(self.scene_dock, state_graph_dock)
        self.scene_dock.raise_()

    def _build_inspector_dock(self) -> None:
        """Build the Inspector dock."""
        self.inspector = InspectorPanel()
        self.inspector.set_language_manager(self.language_manager)
        self.inspector.node_registry = self.node_type_registry
        self.inspector.renameRequested.connect(self.rename_node)
        self.inspector.propertyRequested.connect(self.set_node_property)
        self.inspector.patternPropertyRequested.connect(self._pattern_property_requested)
        self.inspector.graphNodePropertyRequested.connect(
            self._graph_node_property_requested
        )
        self.inspector.uiNodePropertyRequested.connect(
            self._ui_node_property_requested
        )
        self.inspector.backgroundPropertyRequested.connect(
            self._background_property_requested
        )
        self.inspector.timelineClipPropertiesRequested.connect(
            self._timeline_clip_properties_requested
        )
        self.inspector.timelineTrackPropertiesRequested.connect(
            self._timeline_track_properties_requested
        )
        self.inspector.timelineKeyframePropertiesRequested.connect(
            self._timeline_keyframe_properties_requested
        )
        inspector_dock = QDockWidget("Inspector", self)
        self.inspector_dock = inspector_dock
        inspector_dock.setObjectName("inspectorDock")
        inspector_dock.setWidget(self.inspector)
        inspector_dock.setMinimumWidth(260)
        self.addDockWidget(Qt.RightDockWidgetArea, inspector_dock)

    def _build_variables_dock(self) -> None:
        """Build the output/timeline/variables widgets, then dock Variables beside
        the Inspector.  The output and timeline widgets are constructed here so
        their creation order (before the Variables tabify) is preserved."""
        self.output = QTextBrowser()
        self.output.setReadOnly(True)
        self.output.setOpenLinks(False)
        self.output.anchorClicked.connect(self._diagnostic_link_clicked)
        self.output.document().setMaximumBlockCount(1000)
        self.timeline = TimelineEditor()
        self.timeline.set_language_manager(self.language_manager)
        self.timeline.addTrackRequested.connect(self._timeline_add_track)
        self.timeline.addClipRequested.connect(self._timeline_add_clip)
        self.timeline.clipGeometryRequested.connect(self._timeline_clip_geometry)
        self.timeline.duplicateClipRequested.connect(self._timeline_duplicate_clip)
        self.timeline.deleteClipRequested.connect(self._timeline_delete_clip)
        self.timeline.deleteTrackRequested.connect(self._timeline_delete_track)
        self.timeline.moveTrackRequested.connect(self._timeline_move_track)
        self.timeline.muteTrackRequested.connect(self._timeline_mute_track)
        self.timeline.addKeyframeRequested.connect(self._timeline_add_keyframe)
        self.timeline.deleteKeyframeRequested.connect(self._timeline_delete_keyframe)
        self.timeline.keyframeGeometryRequested.connect(
            self._timeline_keyframe_geometry
        )
        self.timeline.trackSelected.connect(self._timeline_track_selected)
        self.timeline.clipSelected.connect(self._timeline_clip_selected)
        self.timeline.reactiveNavigateRequested.connect(
            self._timeline_reactive_navigate
        )
        self.timeline.playheadChanged.connect(self._timeline_playhead_changed)
        self.timeline.actionSearchRequested.connect(
            lambda _unused: self._open_action_search("timeline")
        )
        self.timeline.zoomChanged.connect(self._timeline_zoom_changed)
        self.variables = VariableEditor()
        self.variables.addVariableRequested.connect(self._variable_add_requested)
        self.variables.editVariableRequested.connect(self._variable_edit_requested)
        self.variables.deleteVariableRequested.connect(self._variable_delete_requested)
        self.variables.bindingRequested.connect(self._variable_binding_requested)
        self.variables.mappingRequested.connect(self._variable_mapping_requested)
        variables_dock = QDockWidget("Variables", self)
        self.variables_dock = variables_dock
        variables_dock.setObjectName("variablesDock")
        variables_dock.setWidget(self.variables)
        variables_dock.setMinimumWidth(300)
        self.addDockWidget(Qt.RightDockWidgetArea, variables_dock)
        self.tabifyDockWidget(self.inspector_dock, variables_dock)
        self.inspector_dock.raise_()

    def _build_bottom_dock(self) -> None:
        """Assemble the bottom tab dock (Output/Timeline/Preview + bottom plugins)."""
        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.setObjectName("bottomWorkbench")
        self.bottom_tabs.addTab(self.output, "Output")
        self.bottom_tabs.addTab(self.timeline, "Timeline")
        self.preview_panel = PatternPreviewPanel()
        self.preview_panel.set_language_manager(self.language_manager)
        self.preview_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.preview_panel.launchRequested.connect(self._launch_active_preview)
        self.preview_panel.commandRequested.connect(self._send_pattern_preview_command)
        self.preview_panel.propertyRequested.connect(self._pattern_property_requested)
        self.bottom_tabs.addTab(self.preview_panel, "Preview")
        for plugin in self.plugin_registry.by_mode("bottom"):
            widget = plugin.factory()
            if hasattr(widget, "set_language_manager"):
                widget.set_language_manager(self.language_manager)
            self._plugin_widgets[plugin.id] = widget
            self.bottom_tabs.addTab(widget, plugin.title)
            if plugin.id == "resource_browser":
                self.resource_browser = widget
                # Bottom pages must not impose their full content size hint on
                # the entire dock.  They remain vertically resizable and their
                # own scroll areas expose content at compact window sizes.
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
                widget.resourceSelected.connect(self._resource_selected)
                widget.resourceActivated.connect(self._resource_activated)
        self.bottom_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        bottom_dock = QDockWidget("Bottom Panel", self)
        self.bottom_dock = bottom_dock
        bottom_dock.setObjectName("bottomDock")
        bottom_dock.setWidget(self.bottom_tabs)
        bottom_dock.setMinimumHeight(210)
        self.addDockWidget(Qt.BottomDockWidgetArea, bottom_dock)
        self.resizeDocks([bottom_dock], [220], Qt.Vertical)

    def _apply_theme(self) -> None:
        QApplication.instance().setStyle("Fusion")
        self.setStyleSheet(
            """
            QMainWindow, QMenuBar, QMenu, QDockWidget, QWidget {
                background: #20232d;
                color: #d9deea;
            }
            QToolBar, QStatusBar {
                background: #191c24;
                color: #aeb7c8;
                border: 0;
            }
            QDockWidget::title {
                background: #191c24;
                padding: 7px;
                font-weight: 600;
            }
            QTreeWidget, QListView, QTextEdit, QTableWidget, QLineEdit,
            QComboBox, QSpinBox, QDoubleSpinBox, QScrollArea {
                background: #171a22;
                color: #dce2ee;
                border: 1px solid #353b49;
                selection-background-color: #315a82;
            }
            QPushButton, QToolButton {
                background: #303644;
                border: 1px solid #454d5e;
                border-radius: 3px;
                padding: 5px 9px;
            }
            QPushButton:hover, QToolButton:hover { background: #3a4252; }
            QHeaderView::section {
                background: #252a35;
                color: #bec7d8;
                border: 0;
                border-right: 1px solid #353b49;
                padding: 5px;
            }
            QTabBar::tab {
                background: #252a35;
                padding: 6px 14px;
            }
            QTabBar::tab:selected { background: #315a82; }
            """
        )

    def _populate_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        if not isinstance(self.session.document, SceneDocument):
            self.tree.blockSignals(False)
            return

        def add_item(node: EditorNode, parent: QTreeWidgetItem | None = None):
            # Translate only untouched built-in defaults.  User-authored names
            # remain verbatim, while internal type IDs stay stable in data.
            spec = self.node_type_registry.get(node.type)
            display_name = node.name
            if (
                spec is not None and node.name == spec.display_name
            ) or (node.type == "SceneRoot" and node.name == "Untitled Scene"):
                display_name = self.language_manager.translate(node.name)
            item = QTreeWidgetItem(
                [display_name, self.language_manager.translate(node.type)]
            )
            item.setData(0, Qt.UserRole, node.id)
            item.setToolTip(0, node.id)
            flags = item.flags() | Qt.ItemIsDropEnabled | Qt.ItemIsSelectable
            if parent is not None:
                flags |= Qt.ItemIsDragEnabled | Qt.ItemIsEditable
            else:
                flags &= ~Qt.ItemIsDragEnabled
            item.setFlags(flags)
            if spec:
                item.setForeground(1, QColor(spec.color))
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in node.children:
                add_item(child, item)
            return item

        add_item(self.session.document.root)
        self.tree.expandAll()
        selected = self._find_tree_item(self._selected_id)
        if selected is not None:
            self.tree.setCurrentItem(selected)
        self.tree.blockSignals(False)

    def _find_tree_item(self, node_id: str) -> QTreeWidgetItem | None:
        """Find an item through the public tree API used by the shell port."""

        pending = [
            self.tree.topLevelItem(index)
            for index in range(self.tree.topLevelItemCount())
        ]
        while pending:
            item = pending.pop()
            if item is None:
                continue
            if str(item.data(0, Qt.UserRole)) == str(node_id):
                return item
            pending.extend(item.child(index) for index in range(item.childCount()))
        return None

    def _refresh(self) -> None:
        if self.document_manager.active is None:
            return
        document = self.session.document
        self._sync_document_docks(document)
        widget = self._document_widgets.get(document.id)
        if isinstance(document, SceneDocument):
            self._refresh_scene_document(document, widget)
        else:
            self._refresh_foreign_document(document, widget)
        self._update_actions()
        self._update_title()

    def apply_invalidation(
        self,
        document_id: str,
        invalidation: InvalidationSet,
    ) -> None:
        """Apply finite application damage through public panel operations."""

        session = next(
            (item for item in self.document_manager if item.document.id == document_id),
            None,
        )
        if session is None:
            return
        if invalidation.is_full_sync:
            if self.document_manager.active is session:
                self._refresh()
            return
        document = session.document
        widget = self._document_widgets.get(document_id)
        active = self.document_manager.active is session
        scopes = invalidation.scopes

        if InvalidationScope.SCENE_TREE in scopes and active:
            self._populate_tree()
        if InvalidationScope.SCENE_CANVAS in scopes and isinstance(widget, SceneViewport):
            was_syncing = self._syncing_selection
            self._syncing_selection = True
            try:
                widget.rebuild(document)
                if active:
                    self.viewport = widget
                    widget.select_node(
                        session.editor_state.selection.node_id or document.root.id
                    )
            finally:
                self._syncing_selection = was_syncing
        if InvalidationScope.INSPECTOR in scopes and active:
            self._refresh_active_inspector(document)
        if InvalidationScope.TIMELINE in scopes and active:
            self._refresh_active_timeline(document)
        if InvalidationScope.STATE_GRAPH in scopes and active:
            self._refresh_active_state_graph(document)
        if InvalidationScope.VARIABLES in scopes and active:
            self._refresh_active_variables(document)
        if InvalidationScope.PATTERN in scopes and isinstance(widget, PatternWorkspace):
            self._apply_pattern_document_view(session, widget)
        if InvalidationScope.UI_CANVAS in scopes and isinstance(widget, UIWorkspace):
            self._apply_ui_document_view(widget, document)
        if InvalidationScope.BACKGROUND in scopes and isinstance(widget, BackgroundWorkspace):
            widget.set_document(document)
        if InvalidationScope.ACTIONS in scopes and active:
            self._update_actions()
        if InvalidationScope.TITLE in scopes:
            self._update_title()

    def _refresh_active_inspector(self, document) -> None:
        session = self.session
        if isinstance(document, SceneDocument):
            state = session.editor_state
            clip_id = state.selection.clip_id
            track_id = state.selection.track_id
            clip_result = find_timeline_clip(document, clip_id) if clip_id else None
            track_result = (
                find_timeline_track(document, track_id, state.selection.state_id)
                if track_id
                else None
            )
            if clip_result is not None:
                self.inspector.set_timeline_clip(
                    clip_result[0], clip_result[1], list(document.root.walk())
                )
            elif track_result is not None:
                self.inspector.set_timeline_track(
                    track_result, list(document.root.walk())
                )
            else:
                self.inspector.set_node(session.node(state.selection.node_id))
            return
        if isinstance(document, UIDocument):
            from ..main_window_support import _find_ui_node

            self.inspector.set_ui_node(
                _find_ui_node(document.root, session.editor_state.selection.ui_node_id or "")
            )
            return
        if isinstance(document, BackgroundDocument):
            self.inspector.set_background_document(document)
            return
        selected_id = session.editor_state.selection.graph_node_id
        selected = next(
            (node for node in (document.graph.nodes if document.graph else ()) if node.id == selected_id),
            None,
        )
        if session.editor_state.pattern.graph_mode:
            self.inspector.set_graph_node(selected)
        else:
            self.inspector.set_pattern(document)

    def _refresh_active_timeline(self, document) -> None:
        if not isinstance(document, SceneDocument):
            self.timeline.clear_document()
            return
        state = self.session.editor_state
        state_id = str(
            state.selection.state_id or document.state_graph.initial_state_id
        )
        self.timeline.set_document(
            document,
            state_id=state_id,
            selected_clip_id=state.selection.clip_id,
            zoom=state.timeline.zoom,
        )
        self.timeline.selected_track_id = state.selection.track_id
        overlay = self._runtime_overlay_for(self.session)
        self.timeline.set_playhead(
            overlay.frame if overlay is not None else state.timeline.playhead_frame,
            emit=False,
        )

    def _refresh_active_state_graph(self, document) -> None:
        if not isinstance(document, SceneDocument):
            self.state_graph.clear_document()
            return
        state = self.session.editor_state
        overlay = self._runtime_overlay_for(self.session)
        self.state_graph.set_document(
            document,
            selected_state_id=(
                state.selection.state_id or document.state_graph.initial_state_id
            ),
            active_state_path=overlay.state_path if overlay is not None else (),
        )

    def _refresh_active_variables(self, document) -> None:
        if not isinstance(document, SceneDocument):
            self.variables.clear_document()
            return
        state = self.session.editor_state
        self.variables.set_document(document, state_id=state.selection.state_id)
        overlay = self._runtime_overlay_for(self.session)
        self.variables.set_runtime_overlay(
            overlay.mutable_variable_snapshot() if overlay is not None else {}
        )

    def _refresh_scene_document(self, document: SceneDocument, widget) -> None:
        """Repopulate the tree, timeline, state graph and inspector for a scene."""
        if self.session.node(self._selected_id) is None:
            self._selected_id = document.root.id
        self._populate_tree()
        self.tree.setEnabled(True)
        if isinstance(widget, SceneViewport):
            was_syncing = self._syncing_selection
            self._syncing_selection = True
            try:
                self.viewport = widget
                widget.rebuild(document)
                widget.select_node(self._selected_id)
            finally:
                self._syncing_selection = was_syncing
        state = self.session.editor_state
        selected_state_id = str(
            state.selection.state_id or document.state_graph.initial_state_id
        )
        selected_state = document.state_graph.find_state(selected_state_id)
        if selected_state is None:
            selected_state_id = document.state_graph.initial_state_id
            selected_state = document.state_graph.initial_state
        state.selection.state_id = selected_state_id
        selected_clip_id = state.selection.clip_id
        selected_track_id = state.selection.track_id
        clip_result = (
            find_timeline_clip(document, str(selected_clip_id))
            if selected_clip_id
            else None
        )
        track_result = (
            find_timeline_track(document, str(selected_track_id), selected_state_id)
            if selected_track_id
            else None
        )
        if clip_result is not None and clip_result[0] not in selected_state.tracks:
            clip_result = None
        if clip_result is not None:
            self.inspector.set_timeline_clip(
                clip_result[0],
                clip_result[1],
                list(document.root.walk()),
            )
        elif track_result is not None:
            self.inspector.set_timeline_track(
                track_result,
                list(document.root.walk()),
            )
        else:
            state.selection.clip_id = None
            state.selection.track_id = None
            self.inspector.set_node(self.session.node(self._selected_id))
        self.timeline.set_document(
            document,
            state_id=selected_state_id,
            selected_clip_id=(clip_result[1].id if clip_result is not None else None),
            zoom=state.timeline.zoom,
        )
        self.timeline.selected_track_id = (
            track_result.id if track_result is not None else None
        )
        overlay = self._runtime_overlay_for(self.session)
        self.timeline.set_playhead(
            overlay.frame if overlay is not None else state.timeline.playhead_frame,
            emit=False,
        )
        self.timeline.set_active_clips(
            overlay.active_clip_ids if overlay is not None else ()
        )
        self.timeline.set_reactive_overlay(
            overlay.mutable_reactive_overlay() if overlay is not None else {}
        )
        self.state_graph.set_document(
            document,
            selected_state_id=selected_state_id,
            active_state_path=overlay.state_path if overlay is not None else (),
        )
        self.variables.set_document(
            document,
            state_id=selected_state_id,
        )
        self.variables.set_runtime_overlay(
            overlay.mutable_variable_snapshot() if overlay is not None else {}
        )

    def _refresh_foreign_document(self, document, widget) -> None:
        """Refresh docks for UI, background and pattern documents.

        The UI and background paths return early; ``_refresh`` runs the shared
        ``_update_actions``/``_update_title`` tail once control returns."""
        self.tree.blockSignals(True)
        self.tree.clear()
        self.tree.blockSignals(False)
        self.tree.setEnabled(False)
        self.state_graph.clear_document()
        self.variables.clear_document()
        if isinstance(document, UIDocument):
            self.inspector.set_ui_node(None)
            if isinstance(widget, UIWorkspace):
                # Bind the timer to self: a bare singleShot keeps no link to
                # the window, so closing the editor before it fires leaves
                # the lambda calling into a deleted C++ object, which aborts
                # the process instead of raising.  The guard covers the
                # workspace widget, which Qt does not track for us.
                QTimer.singleShot(
                    0,
                    self,
                    lambda doc=document, w=widget: self._apply_ui_document_view_if_alive(
                        w, doc
                    ),
                )
            return
        if isinstance(document, BackgroundDocument):
            self.inspector.set_background_document(document)
            if isinstance(widget, BackgroundWorkspace):
                widget.set_document(document)
                selected_layer = self.session.editor_state.background_selected_layer
                if widget.layers.count():
                    widget.layers.setCurrentRow(
                        max(0, min(int(selected_layer), widget.layers.count() - 1))
                    )
            self.timeline.clear_document()
            return
        state = self.session.editor_state
        graph_mode = state.pattern.graph_mode
        selected_graph_node = state.selection.graph_node_id
        if graph_mode and document.graph is not None:
            selected_node = next(
                (
                    node
                    for node in document.graph.nodes
                    if node.id == str(selected_graph_node)
                ),
                None,
            )
            self.inspector.set_graph_node(selected_node)
        else:
            self.inspector.set_pattern(document)
        self.timeline.clear_document()
        if isinstance(widget, PatternWorkspace):
            self._apply_pattern_document_view(self.session, widget)

    def _apply_pattern_document_view(
        self,
        session: ManagedDocument,
        widget: PatternWorkspace,
    ) -> None:
        """Rebind the public Pattern port from authoring and typed view state."""

        document = session.document
        if not isinstance(document, PatternDocument):
            return
        state = session.editor_state.pattern
        widget.set_document(document, player_position=state.player_position)
        preset_instance = self._preset_resolver.instance_from_document(document)
        if preset_instance is not None:
            descriptor = self._preset_resolver.registry.resolve(
                preset_instance.preset_id, preset_instance.version
            )
            widget.set_preset_expansion(
                descriptor,
                self._preset_resolver.expand_virtual(preset_instance),
                dict(preset_instance.parameters),
                dict(preset_instance.slot_overrides),
                self._preset_resolver.registry.migration_targets(
                    preset_instance.preset_id, preset_instance.version
                ),
            )
        else:
            widget.set_preset_expansion(None)
        mode = (
            "preset"
            if state.preset_mode and preset_instance is not None
            else ("graph" if state.graph_mode else "recipe")
        )
        widget.set_mode(mode, emit=False)
        level = state.authoring_level
        if widget.level_picker.findData(level) < 0:
            level = "l1"
        widget.set_authoring_level(level)
        if hasattr(self, "resource_browser"):
            widget.set_available_bullets(self.resource_browser.index.records)
        # PatternWorkspace rebuilds several combo-box item lists while binding
        # a document.  Re-translate this local subtree after the rebuild so a
        # workspace opened after a language switch does not expose the English
        # source labels until the next global language change.
        translate_widget_tree(widget, self.language_manager)

    def _sync_document_docks(self, document) -> None:
        """Show only tools that can act on the active document."""

        is_scene = isinstance(document, SceneDocument)
        for dock in (self.scene_dock, self.state_graph_dock, self.variables_dock):
            dock.setVisible(is_scene)
        self.inspector_dock.setVisible(True)
        if is_scene:
            self.tabifyDockWidget(self.scene_dock, self.state_graph_dock)
            self.tabifyDockWidget(self.inspector_dock, self.variables_dock)
            self.scene_dock.raise_()
            self.inspector_dock.raise_()

    def _update_actions(self) -> None:
        self.action_undo.setEnabled(self.session.commands.can_undo)
        self.action_redo.setEnabled(self.session.commands.can_redo)
        self.action_undo.setText(
            f"Undo {self.session.commands.undo_label}"
            if self.session.commands.undo_label
            else "Undo"
        )
        self.action_redo.setText(
            f"Redo {self.session.commands.redo_label}"
            if self.session.commands.redo_label
            else "Redo"
        )
        is_scene = isinstance(self.session.document, SceneDocument)
        is_root = is_scene and self._selected_id == self.session.document.root.id
        self.action_delete.setEnabled(is_scene and not is_root)
        self.action_rename.setEnabled(is_scene and not is_root)
        self.action_move_up.setEnabled(is_scene and not is_root)
        self.action_move_down.setEnabled(is_scene and not is_root)
        self.action_outdent.setEnabled(is_scene and not is_root)
        self.action_indent.setEnabled(is_scene and not is_root)
        self.action_revert.setEnabled(self.session.is_dirty or self.session.path is not None)

    def _update_title(self) -> None:
        name = self.language_manager.translate(self.session.display_name)
        self.setWindowModified(self.session.is_dirty)
        app_title = self.language_manager.translate(APP_NAME)
        self.setWindowTitle(f"{name}[*] — {app_title}")
        for session in self.document_manager:
            widget = self._document_widgets.get(session.document.id)
            if widget is None:
                continue
            index = self.central_tabs.indexOf(widget)
            if index >= 0:
                suffix = " *" if session.is_dirty else ""
                display_name = self.language_manager.translate(session.display_name)
                self.central_tabs.setTabText(index, display_name + suffix)
        if hasattr(self, "language_manager"):
            translate_widget_tree(self, self.language_manager)
            self._update_language_actions()

    def _log(self, message: str) -> None:
        self.output.append(
            html.escape(self.language_manager.translate(str(message)))
        )

    def undo(self) -> bool:
        invalidation = self.editor_coordinator.dispatch(
            UndoIntent(self.session.document.id)
        )
        if invalidation.scopes:
            self._log("Undo")
            self.apply_invalidation(self.session.document.id, invalidation)
            self._sync_active_pattern_preview()
            self._sync_active_stage_preview()
        return bool(invalidation.scopes)

    def redo(self) -> bool:
        invalidation = self.editor_coordinator.dispatch(
            RedoIntent(self.session.document.id)
        )
        if invalidation.scopes:
            self._log("Redo")
            self.apply_invalidation(self.session.document.id, invalidation)
            self._sync_active_pattern_preview()
            self._sync_active_stage_preview()
        return bool(invalidation.scopes)

    def _fit_viewport(self) -> None:
        self.viewport.fit_canvas()

    def save_layout(self, path: str | Path) -> Path:
        """Persist dock/tab state plus open document paths."""
        payload = {
            "schema_version": 1,
            "window_state": bytes(self.saveState()).decode("latin-1"),
            "open_documents": [
                session.resource_uri
                for session in self.document_manager
                if session.resource_uri is not None
            ],
            "active_document": self.session.resource_uri
            if self.document_manager.active is not None
            else None,
        }
        return atomic_write_json(path, payload)

    def restore_layout(self, path: str | Path) -> None:
        """Restore dock/tab geometry and reopen persisted documents."""
        layout_path = Path(path).expanduser().resolve()
        try:
            data = json.loads(layout_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            line = getattr(exc, "lineno", None)
            location = f" at line {line}" if line is not None else ""
            raise ResourceDocumentError(
                f"{layout_path}: invalid layout JSON{location}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ResourceDocumentError(f"{layout_path}: layout must be an object")
        if data.get("schema_version") != 1:
            raise ResourceDocumentError(
                f"{layout_path}: unsupported layout schema_version"
            )
        documents = data.get("open_documents")
        if not isinstance(documents, list):
            raise ResourceDocumentError(
                f"{layout_path}: open_documents must be an array"
            )
        if len(documents) > 256:
            raise ResourceDocumentError(
                f"{layout_path}: open_documents exceeds the 256-document limit"
            )
        resolved_documents: list[Path] = []
        for index, document_uri in enumerate(documents):
            if not isinstance(document_uri, str) or not document_uri.startswith("res://"):
                raise ResourceDocumentError(
                    f"{layout_path}: open_documents[{index}] must be a res:// URI"
                )
            try:
                reference = ResourceReference.parse(document_uri)
                if reference.subresource is not None:
                    raise ResourceDocumentError("layout document URI cannot contain a fragment")
                resolved = reference.resolve(self.project, must_exist=True)
                self.project.relative(resolved)
                # Load every document before mutating tabs, so one malformed
                # entry cannot leave a partially restored workspace.
                self.document_manager.store.load(resolved)
            except (OSError, ValueError, ResourceDocumentError) as exc:
                raise ResourceDocumentError(
                    f"{layout_path}: invalid open_documents[{index}] {document_uri!r}: {exc}"
                ) from exc
            resolved_documents.append(resolved)

        window_state = data.get("window_state")
        if window_state is not None and not isinstance(window_state, str):
            raise ResourceDocumentError(
                f"{layout_path}: window_state must be a string"
            )
        active_uri = data.get("active_document")
        if active_uri is not None and active_uri not in documents:
            raise ResourceDocumentError(
                f"{layout_path}: active_document must refer to open_documents"
            )

        if isinstance(window_state, str):
            self.restoreState(bytes(window_state.encode("latin-1")))
        for resolved in resolved_documents:
            self._open_document(resolved)
        if isinstance(active_uri, str):
            target = ResourceReference.parse(active_uri).resolve(
                self.project, must_exist=True
            )
            session = self.document_manager.find_path(target)
            if session is not None:
                self.document_manager.activate(session)

    def _show_error(self, title: str, error: Exception) -> None:
        self._log(f"[error] {title}: {error}")
        QMessageBox.critical(self, self.language_manager.translate(title), str(error))

    def closeEvent(self, event) -> None:
        for session in tuple(self.document_manager):
            if not self._confirm_discard(session):
                event.ignore()
                return
        for index in range(self.central_tabs.count() - 1, -1, -1):
            widget = self.central_tabs.widget(index)
            if self._managed_for_widget(widget) is not None:
                continue
            if widget is not None and not widget.close():
                event.ignore()
                return
        self._clear_stage_runtime_feedback()
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

"""Godot-inspired PyQt scene editor shell for PySTG."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Callable

from src.qt_compat.QtCore import QProcess, Qt, QTimer
from src.qt_compat.QtGui import QColor, QFont, QKeySequence
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

from .action_catalog import ActionExecutor, build_editor_action_catalog
from .action_search import ActionSearchDialog
from .document import DocumentError, EditorNode, SceneDocument
from .node_types import build_default_node_type_registry
from .preview_panel import PatternPreviewPanel
from .preview_process import PatternPreviewProcess
from .runtime_preview import RuntimePreviewHost
from .document_manager import (
    DocumentManager,
    DocumentManagerError,
    ManagedDocument,
)
from .pattern_workspace import PatternWorkspace
from .ui_workspace import BackgroundWorkspace, UIWorkspace
from .scene_commands import SceneMutationError
from .timeline_commands import find_clip, find_track
from .timeline_workspace import TimelineEditor
from .variable_workspace import VariableEditor
from .state_graph_workspace import StateGraphEditor
from .plugin_sdk import PluginRegistry as SDKPluginRegistry
from .i18n import (
    LANGUAGE_CHINESE,
    LANGUAGE_ENGLISH,
    LanguageManager,
    translate_widget_tree,
)
from .workbench import PluginRegistry as EditorPluginRegistry
from .inspector_panel import InspectorPanel
from .main_window_support import APP_NAME, build_preview_command
from .scene_view import NodeGraphicsItem, SceneTreeWidget, SceneViewport
from .main_window_authoring import AuthoringSlotsMixin
from .main_window_documents import DocumentSlotsMixin
from .main_window_pattern import PatternSlotsMixin
from .main_window_preview import PreviewSlotsMixin
from .main_window_scene_edit import SceneEditSlotsMixin
from .main_window_timeline import TimelineSlotsMixin
from .main_window_ui_docs import UIDocumentSlotsMixin
from .main_window_workbench import WorkbenchSlotsMixin

# ``build_preview_command`` and ``NodeGraphicsItem`` now live in the modules split
# out of this file; they stay importable from here because the editor tests and
# the native gates address them as ``src.editor.app`` attributes.
__all__ = [
    "EditorMainWindow",
    "InspectorPanel",
    "NodeGraphicsItem",
    "SceneViewport",
    "build_preview_command",
    "main",
]


class EditorMainWindow(
    TimelineSlotsMixin,
    PreviewSlotsMixin,
    DocumentSlotsMixin,
    SceneEditSlotsMixin,
    PatternSlotsMixin,
    UIDocumentSlotsMixin,
    AuthoringSlotsMixin,
    WorkbenchSlotsMixin,
    QMainWindow,
):
    """The editor shell: window chrome, selection state and the refresh loop.

    Everything domain-specific lives in the slot mixins listed above.  They are
    mixins rather than controller objects so the slots keep operating on this
    instance's attributes, which is what the editor tests and the native gates
    drive directly.  Mixins come before ``QMainWindow`` so their methods win the
    MRO, matching ``SceneViewport(SpaceTapSearchMixin, QGraphicsView)``.
    """

    def __init__(self, project: ProjectContext):
        super().__init__()
        self.project = project
        self.language_manager = LanguageManager(self)
        self.language_manager.languageChanged.connect(self._language_changed)
        # The SDK registries are the same objects used by document loading and
        # scene validation.  Legacy workbench widgets remain a separate view
        # catalog, but plugin contributions now have a real runtime owner.
        self.resource_type_registry = build_default_resource_type_registry()
        self.node_type_registry = build_default_node_type_registry()
        self.plugin_sdk_registry = SDKPluginRegistry(
            project,
            resource_types=self.resource_type_registry,
            node_types=self.node_type_registry,
        )
        self.document_manager = DocumentManager(
            project,
            registry=self.resource_type_registry,
            node_registry=self.node_type_registry,
        )
        self._fallback_selected_id = ""
        self._selected_id = self.session.document.root.id
        self._syncing_selection = False
        self._preview_process: QProcess | None = None
        self._pattern_preview_client = PatternPreviewProcess(project, parent=self)
        self._active_pattern_document: PatternDocument | None = None
        self._active_pattern_session: ManagedDocument | None = None
        self._active_pattern_resource = ""
        self._preset_library = self._load_builtin_preset_library()
        self._preset_resolver = PresetResolver(self._preset_library.presets)
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
        self._active_stage_session: ManagedDocument | None = None
        self._preview_loaded_resource_id: str | None = None
        self._preview_mode = "unloaded"
        self._preview_state = "stopped"
        self._preview_pending_properties: dict[str, tuple[str, object]] = {}
        self._runtime_preview_host: RuntimePreviewHost | None = None
        self._sdk_plugins_deactivated = False
        self._tool_processes: dict[str, QProcess] = {}
        self._plugin_widgets: dict[str, QWidget] = {}
        self._document_widgets: dict[str, QWidget] = {}
        self._bottom_dock_resize_guard = False
        # The legacy registry continues to own built-in Qt tool widgets.  The
        # SDK registry above owns project-local resource/node/runtime
        # contributions and is deliberately the same registry instance wired
        # into DocumentManager; never replace it with a detached copy.
        self.plugin_registry = EditorPluginRegistry(project)
        self._register_plugins()
        self._build_actions()
        self._build_ui()
        self._discover_sdk_plugins()
        self._connect_pattern_preview()
        self._apply_theme()
        self._refresh()
        self.resize(1480, 920)
        self.setMinimumSize(960, 640)

    def _load_builtin_preset_library(self) -> PresetLibrary:
        path = self.project.root / "game_content" / "presets" / "builtin_patterns.pystg.json"
        if not path.is_file():
            path = Path(__file__).resolve().parents[2] / "game_content" / "presets" / "builtin_patterns.pystg.json"
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
            for widget in self._document_widgets.values():
                if isinstance(widget, PatternWorkspace):
                    widget.set_language_manager(self.language_manager)
                    widget.set_available_presets(self._preset_library.presets)
            self._refresh()
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
        return session.selected_id or session.default_selection

    @_selected_id.setter
    def _selected_id(self, value: str) -> None:
        self._fallback_selected_id = str(value)
        session = self.document_manager.active
        if session is not None:
            session.selected_id = str(value)

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
        selected = self.tree._find_item(self._selected_id)
        if selected is not None:
            self.tree.setCurrentItem(selected)
        self.tree.blockSignals(False)

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

    def _refresh_scene_document(self, document: SceneDocument, widget) -> None:
        """Repopulate the tree, timeline, state graph and inspector for a scene."""
        if self.session.node(self._selected_id) is None:
            self._selected_id = document.root.id
        self._populate_tree()
        self.tree.setEnabled(True)
        if isinstance(widget, SceneViewport):
            self.viewport = widget
            widget.rebuild(document)
            widget.select_node(self._selected_id)
        selected_state_id = str(
            self.session.editor_context.get("selected_state_id")
            or document.state_graph.initial_state_id
        )
        selected_state = document.state_graph.find_state(selected_state_id)
        if selected_state is None:
            selected_state_id = document.state_graph.initial_state_id
            selected_state = document.state_graph.initial_state
        self.session.editor_context["selected_state_id"] = selected_state_id
        selected_clip_id = self.session.editor_context.get("selected_clip_id")
        selected_track_id = self.session.editor_context.get("selected_track_id")
        clip_result = (
            find_clip(document, str(selected_clip_id))
            if selected_clip_id
            else None
        )
        track_result = (
            find_track(document, str(selected_track_id), selected_state_id)
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
            self.session.editor_context.pop("selected_clip_id", None)
            self.session.editor_context.pop("selected_track_id", None)
            self.inspector.set_node(self.session.node(self._selected_id))
        self.timeline.set_document(
            document,
            state_id=selected_state_id,
            selected_clip_id=(clip_result[1].id if clip_result is not None else None),
            zoom=float(self.session.editor_context.get("timeline_zoom", 0.25)),
        )
        self.timeline.selected_track_id = (
            track_result.id if track_result is not None else None
        )
        self.timeline.set_playhead(
            int(self.session.editor_context.get("timeline_playhead", 0)),
            emit=False,
        )
        stored_active = self.session.editor_context.get(
            "timeline_active_clips", ()
        )
        self.timeline.set_active_clips(
            stored_active if isinstance(stored_active, (list, tuple, set)) else ()
        )
        stored_reactive = self.session.editor_context.get("reactive_overlay", {})
        self.timeline.set_reactive_overlay(
            stored_reactive if isinstance(stored_reactive, dict) else {}
        )
        runtime_path = self.session.editor_context.get("runtime_state_path", ())
        self.state_graph.set_document(
            document,
            selected_state_id=selected_state_id,
            active_state_path=(
                runtime_path
                if isinstance(runtime_path, (list, tuple, set))
                else ()
            ),
        )
        self.variables.set_document(
            document,
            state_id=selected_state_id,
        )
        self.variables.set_runtime_overlay(
            self.session.editor_context.get("runtime_variables", {})
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
                selected_layer = self.session.editor_context.get(
                    "background_selected_layer", 0
                )
                if widget.layers.count():
                    widget.layers.setCurrentRow(
                        max(0, min(int(selected_layer), widget.layers.count() - 1))
                    )
            self.timeline.clear_document()
            return
        graph_mode = bool(self.session.editor_context.get("graph_mode", False))
        selected_graph_node = self.session.editor_context.get(
            "selected_graph_node_id"
        )
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
            player = tuple(
                self.session.editor_context.get("player_position", (0.0, -0.8))
            )
            widget.set_document(document, player_position=player)
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
            preset_mode = bool(self.session.editor_context.get("preset_mode", False))
            mode = "preset" if preset_mode and preset_instance is not None else ("graph" if graph_mode else "recipe")
            widget.set_mode(mode, emit=False)
            level = str(
                self.session.editor_context.get(
                    "pattern_authoring_level",
                    "l0" if preset_mode and preset_instance is not None else (
                        "l3" if graph_mode else "l1"
                    ),
                )
            )
            if widget.level_picker.findData(level) < 0:
                level = "l1"
            widget.set_authoring_level(level)
            if hasattr(self, "resource_browser"):
                widget.set_available_bullets(self.resource_browser.index.records)

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

    def _apply_command(
        self,
        command,
        *,
        select_id: str | None = None,
        coalesce: bool = False,
    ) -> bool:
        try:
            self.session.apply(command, coalesce=coalesce)
        except (DocumentError, ResourceDocumentError, SceneMutationError, ValueError) as exc:
            self._show_error("Edit failed", exc)
            self._refresh()
            return False
        if select_id is not None:
            self._selected_id = select_id
        self._log(command.label)
        self._refresh()
        return True

    def undo(self) -> bool:
        changed = self.session.undo()
        if changed:
            self._log("Undo")
            self._refresh()
            self._sync_active_pattern_preview()
            self._sync_active_stage_preview()
        return bool(changed)

    def redo(self) -> bool:
        changed = self.session.redo()
        if changed:
            self._log("Redo")
            self._refresh()
            self._sync_active_pattern_preview()
            self._sync_active_stage_preview()
        return bool(changed)

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
        if self._preview_process is not None and self._preview_process.state() != QProcess.NotRunning:
            self._preview_process.terminate()
            if not self._preview_process.waitForFinished(1500):
                self._preview_process.kill()
        self._pattern_preview_client.close()
        for process in tuple(self._tool_processes.values()):
            if process.state() == QProcess.NotRunning:
                continue
            process.terminate()
            if not process.waitForFinished(1500):
                process.kill()
        if not self._sdk_plugins_deactivated:
            self.plugin_sdk_registry.deactivate_all()
            self._sdk_plugins_deactivated = True
        event.accept()


def create_window(project: ProjectContext) -> EditorMainWindow:
    return EditorMainWindow(project)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--project", type=Path, help="PySTG project root")
    args, qt_args = parser.parse_known_args(argv)
    project = ProjectContext.discover(args.project or Path.cwd())
    project.activate()

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("PySTG")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    window = create_window(project)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

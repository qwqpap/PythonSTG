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


from .service import WindowService
from .ports import DocksPort


class ShellDocks(WindowService[DocksPort]):
    def build_ui(self) -> None:
        self.port._build_menus()
        self.port._build_main_toolbar()
        self.build_central_tabs()
        self.build_scene_dock()
        self.build_state_graph_dock()
        self.build_inspector_dock()
        self.build_variables_dock()
        self.build_bottom_dock()
        self.port.statusBar().showMessage(str(self.port.project.root))

    def build_central_tabs(self) -> None:
        """Create the central document tab widget."""
        self.port.central_tabs = QTabWidget()
        self.port.central_tabs.setObjectName('centralWorkbench')
        self.port.central_tabs.setTabsClosable(True)
        self.port.central_tabs.tabCloseRequested.connect(self.port.document_service.close_central_tab)
        self.port.central_tabs.currentChanged.connect(self.port.document_service.central_tab_changed)
        initial_widget = self.port.document_service.add_document_tab(self.port.session)
        self.port.viewport = initial_widget
        self.port.setCentralWidget(self.port.central_tabs)

    def build_scene_dock(self) -> None:
        """Build the Scene hierarchy dock."""
        self.port.tree = SceneTreeWidget()
        self.port.tree.currentItemChanged.connect(self.port.scene_edit_service.select_from_tree)
        self.port.tree.itemChanged.connect(self.port.scene_edit_service.tree_item_changed)
        self.port.tree.nodeMoveRequested.connect(self.port.scene_edit_service.move_from_tree)
        tree_content = QWidget()
        tree_layout = QVBoxLayout(tree_content)
        tree_layout.setContentsMargins(4, 4, 4, 4)
        tree_buttons = QHBoxLayout()
        add_button = QToolButton()
        add_button.setText('+ Add')
        add_button.setPopupMode(QToolButton.InstantPopup)
        add_menu = QMenu(add_button)
        quick_flow = add_menu.addAction('Simple Spell Setup')
        quick_flow.setObjectName('addSimpleSpellFlow')
        quick_flow.triggered.connect(self.port.scene_edit_service.create_simple_spell_flow)
        midstage = add_menu.addAction('Midstage Skeleton')
        midstage.setObjectName('addMidstageSkeleton')
        midstage.triggered.connect(lambda: self.port.scene_edit_service.create_stage_template('midstage'))
        boss = add_menu.addAction('Two-phase Boss Skeleton')
        boss.setObjectName('addTwoPhaseBossSkeleton')
        boss.triggered.connect(lambda: self.port.scene_edit_service.create_stage_template('two_phase_boss'))
        add_menu.addSeparator()
        self.port._node_add_menu = add_menu
        self.port._node_menu_types: set[str] = set()
        for type_name, spec in self.port.node_type_registry.items():
            if type_name == 'SceneRoot':
                continue
            action = add_menu.addAction(spec.display_name)
            self.port._node_menu_types.add(type_name)
            action.triggered.connect(lambda checked=False, node_type=type_name: self.port.scene_edit_service.add_node(node_type))
        add_button.setMenu(add_menu)
        delete_button = QPushButton('Delete')
        delete_button.clicked.connect(self.port.scene_edit_service.delete_selected)
        tree_buttons.addWidget(add_button)
        tree_buttons.addWidget(delete_button)
        tree_buttons.addStretch()
        tree_layout.addLayout(tree_buttons)
        hierarchy_buttons = QHBoxLayout()
        for text, tooltip, action in (('↑', 'Move up (Alt+Up)', self.port.action_move_up), ('↓', 'Move down (Alt+Down)', self.port.action_move_down), ('←', 'Move to parent (Alt+Left)', self.port.action_outdent), ('→', 'Make child of previous node (Alt+Right)', self.port.action_indent)):
            button = QToolButton()
            button.setText(text)
            button.setFixedWidth(44)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda checked=False, target=action: target.trigger())
            hierarchy_buttons.addWidget(button)
        hierarchy_buttons.addStretch()
        tree_layout.addLayout(hierarchy_buttons)
        tree_layout.addWidget(self.port.tree)
        tree_dock = QDockWidget('Scene', self.port.qt_parent)
        self.port.scene_dock = tree_dock
        tree_dock.setObjectName('sceneDock')
        tree_dock.setWidget(tree_content)
        tree_dock.setMinimumWidth(220)
        self.port.addDockWidget(Qt.LeftDockWidgetArea, tree_dock)

    def build_state_graph_dock(self) -> None:
        """Build the State Flow dock, tabbed behind Scene."""
        self.port.state_graph = StateGraphEditor()
        self.port.state_graph.set_language_manager(self.port.language_manager)
        self.port.state_graph.stateSelected.connect(self.port.authoring_service.state_graph_state_selected)
        self.port.state_graph.addStateRequested.connect(self.port.authoring_service.state_graph_add_state)
        self.port.state_graph.renameStateRequested.connect(self.port.authoring_service.state_graph_rename_state)
        self.port.state_graph.duplicateStateRequested.connect(self.port.authoring_service.state_graph_duplicate_state)
        self.port.state_graph.deleteStateRequested.connect(self.port.authoring_service.state_graph_delete_state)
        self.port.state_graph.moveStateRequested.connect(self.port.authoring_service.state_graph_move_state)
        self.port.state_graph.addTransitionRequested.connect(self.port.authoring_service.state_graph_add_transition)
        self.port.state_graph.editTransitionRequested.connect(self.port.authoring_service.state_graph_edit_transition)
        self.port.state_graph.deleteTransitionRequested.connect(self.port.authoring_service.state_graph_delete_transition)
        state_graph_dock = QDockWidget('State Flow', self.port.qt_parent)
        self.port.state_graph_dock = state_graph_dock
        state_graph_dock.setObjectName('stateGraphDock')
        state_graph_dock.setWidget(self.port.state_graph)
        state_graph_dock.setMinimumWidth(240)
        self.port.addDockWidget(Qt.LeftDockWidgetArea, state_graph_dock)
        self.port.tabifyDockWidget(self.port.scene_dock, state_graph_dock)
        self.port.scene_dock.raise_()

    def build_inspector_dock(self) -> None:
        """Build the Inspector dock."""
        self.port.inspector = InspectorPanel()
        self.port.inspector.set_language_manager(self.port.language_manager)
        self.port.inspector.node_registry = self.port.node_type_registry
        self.port.inspector.renameRequested.connect(self.port.scene_edit_service.rename_node)
        self.port.inspector.propertyRequested.connect(self.port.scene_edit_service.set_node_property)
        self.port.inspector.patternPropertyRequested.connect(self.port.pattern_service.pattern_property_requested)
        self.port.inspector.graphNodePropertyRequested.connect(self.port.pattern_service.graph_node_property_requested)
        self.port.inspector.uiNodePropertyRequested.connect(self.port.ui_document_service.ui_node_property_requested)
        self.port.inspector.backgroundPropertyRequested.connect(self.port.ui_document_service.background_property_requested)
        self.port.inspector.timelineClipPropertiesRequested.connect(self.port.timeline_service.timeline_clip_properties_requested)
        self.port.inspector.timelineTrackPropertiesRequested.connect(self.port.timeline_service.timeline_track_properties_requested)
        self.port.inspector.timelineKeyframePropertiesRequested.connect(self.port.timeline_service.timeline_keyframe_properties_requested)
        inspector_dock = QDockWidget('Inspector', self.port.qt_parent)
        self.port.inspector_dock = inspector_dock
        inspector_dock.setObjectName('inspectorDock')
        inspector_dock.setWidget(self.port.inspector)
        inspector_dock.setMinimumWidth(260)
        self.port.addDockWidget(Qt.RightDockWidgetArea, inspector_dock)

    def build_variables_dock(self) -> None:
        """Build the output/timeline/variables widgets, then dock Variables beside
            the Inspector.  The output and timeline widgets are constructed here so
            their creation order (before the Variables tabify) is preserved."""
        self.port.output = QTextBrowser()
        self.port.output.setReadOnly(True)
        self.port.output.setOpenLinks(False)
        self.port.output.anchorClicked.connect(self.port.workbench_service.diagnostic_link_clicked)
        self.port.output.document().setMaximumBlockCount(1000)
        self.port.timeline = TimelineEditor()
        self.port.timeline.set_language_manager(self.port.language_manager)
        self.port.timeline.addTrackRequested.connect(self.port.timeline_service.timeline_add_track)
        self.port.timeline.addClipRequested.connect(self.port.timeline_service.timeline_add_clip)
        self.port.timeline.clipGeometryRequested.connect(self.port.timeline_service.timeline_clip_geometry)
        self.port.timeline.duplicateClipRequested.connect(self.port.timeline_service.timeline_duplicate_clip)
        self.port.timeline.deleteClipRequested.connect(self.port.timeline_service.timeline_delete_clip)
        self.port.timeline.deleteTrackRequested.connect(self.port.timeline_service.timeline_delete_track)
        self.port.timeline.moveTrackRequested.connect(self.port.timeline_service.timeline_move_track)
        self.port.timeline.muteTrackRequested.connect(self.port.timeline_service.timeline_mute_track)
        self.port.timeline.addKeyframeRequested.connect(self.port.timeline_service.timeline_add_keyframe)
        self.port.timeline.deleteKeyframeRequested.connect(self.port.timeline_service.timeline_delete_keyframe)
        self.port.timeline.keyframeGeometryRequested.connect(self.port.timeline_service.timeline_keyframe_geometry)
        self.port.timeline.trackSelected.connect(self.port.timeline_service.timeline_track_selected)
        self.port.timeline.clipSelected.connect(self.port.timeline_service.timeline_clip_selected)
        self.port.timeline.reactiveNavigateRequested.connect(self.port.timeline_service.timeline_reactive_navigate)
        self.port.timeline.playheadChanged.connect(self.port.timeline_service.timeline_playhead_changed)
        self.port.timeline.actionSearchRequested.connect(lambda _unused: self.port.workbench_service.open_action_search('timeline'))
        self.port.timeline.zoomChanged.connect(self.port.timeline_service.timeline_zoom_changed)
        self.port.variables = VariableEditor()
        self.port.variables.addVariableRequested.connect(self.port.authoring_service.variable_add_requested)
        self.port.variables.editVariableRequested.connect(self.port.authoring_service.variable_edit_requested)
        self.port.variables.deleteVariableRequested.connect(self.port.authoring_service.variable_delete_requested)
        self.port.variables.bindingRequested.connect(self.port.authoring_service.variable_binding_requested)
        self.port.variables.mappingRequested.connect(self.port.authoring_service.variable_mapping_requested)
        variables_dock = QDockWidget('Variables', self.port.qt_parent)
        self.port.variables_dock = variables_dock
        variables_dock.setObjectName('variablesDock')
        variables_dock.setWidget(self.port.variables)
        variables_dock.setMinimumWidth(300)
        self.port.addDockWidget(Qt.RightDockWidgetArea, variables_dock)
        self.port.tabifyDockWidget(self.port.inspector_dock, variables_dock)
        self.port.inspector_dock.raise_()

    def build_bottom_dock(self) -> None:
        """Assemble the bottom tab dock (Output/Timeline/Preview + bottom plugins)."""
        self.port.bottom_tabs = QTabWidget()
        self.port.bottom_tabs.setObjectName('bottomWorkbench')
        self.port.bottom_tabs.addTab(self.port.output, 'Output')
        self.port.bottom_tabs.addTab(self.port.timeline, 'Timeline')
        self.port.preview_panel = PatternPreviewPanel()
        self.port.preview_panel.set_language_manager(self.port.language_manager)
        self.port.preview_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.port.preview_panel.launchRequested.connect(self.port.preview_service.launch_active_preview)
        self.port.preview_panel.commandRequested.connect(self.port.preview_service.send_pattern_preview_command)
        self.port.preview_panel.propertyRequested.connect(self.port.pattern_service.pattern_property_requested)
        self.port.bottom_tabs.addTab(self.port.preview_panel, 'Preview')
        for plugin in self.port.plugin_registry.by_mode('bottom'):
            widget = plugin.factory()
            if hasattr(widget, 'set_language_manager'):
                widget.set_language_manager(self.port.language_manager)
            self.port._plugin_widgets[plugin.id] = widget
            self.port.bottom_tabs.addTab(widget, plugin.title)
            if plugin.id == 'resource_browser':
                self.port.resource_browser = widget
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
                widget.resourceSelected.connect(self.port.workbench_service.resource_selected)
                widget.resourceActivated.connect(self.port.workbench_service.resource_activated)
        self.port.bottom_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        bottom_dock = QDockWidget('Bottom Panel', self.port.qt_parent)
        self.port.bottom_dock = bottom_dock
        bottom_dock.setObjectName('bottomDock')
        bottom_dock.setWidget(self.port.bottom_tabs)
        bottom_dock.setMinimumHeight(210)
        self.port.addDockWidget(Qt.BottomDockWidgetArea, bottom_dock)
        self.port.resizeDocks([bottom_dock], [220], Qt.Vertical)

    def apply_theme(self) -> None:
        QApplication.instance().setStyle('Fusion')
        self.port.setStyleSheet('\n            QMainWindow, QMenuBar, QMenu, QDockWidget, QWidget {\n                background: #20232d;\n                color: #d9deea;\n            }\n            QToolBar, QStatusBar {\n                background: #191c24;\n                color: #aeb7c8;\n                border: 0;\n            }\n            QDockWidget::title {\n                background: #191c24;\n                padding: 7px;\n                font-weight: 600;\n            }\n            QTreeWidget, QListView, QTextEdit, QTableWidget, QLineEdit,\n            QComboBox, QSpinBox, QDoubleSpinBox, QScrollArea {\n                background: #171a22;\n                color: #dce2ee;\n                border: 1px solid #353b49;\n                selection-background-color: #315a82;\n            }\n            QPushButton, QToolButton {\n                background: #303644;\n                border: 1px solid #454d5e;\n                border-radius: 3px;\n                padding: 5px 9px;\n            }\n            QPushButton:hover, QToolButton:hover { background: #3a4252; }\n            QHeaderView::section {\n                background: #252a35;\n                color: #bec7d8;\n                border: 0;\n                border-right: 1px solid #353b49;\n                padding: 5px;\n            }\n            QTabBar::tab {\n                background: #252a35;\n                padding: 6px 14px;\n            }\n            QTabBar::tab:selected { background: #315a82; }\n            ')

    def populate_tree(self) -> None:
        self.port.tree.blockSignals(True)
        self.port.tree.clear()
        if not isinstance(self.port.session.document, SceneDocument):
            self.port.tree.blockSignals(False)
            return

        def add_item(node: EditorNode, parent: QTreeWidgetItem | None=None):
            spec = self.port.node_type_registry.get(node.type)
            display_name = node.name
            if spec is not None and node.name == spec.display_name or (node.type == 'SceneRoot' and node.name == 'Untitled Scene'):
                display_name = self.port.language_manager.translate(node.name)
            item = QTreeWidgetItem([display_name, self.port.language_manager.translate(node.type)])
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
                self.port.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in node.children:
                add_item(child, item)
            return item
        add_item(self.port.session.document.root)
        self.port.tree.expandAll()
        selected = self.find_tree_item(self.port._selected_id)
        if selected is not None:
            self.port.tree.setCurrentItem(selected)
        self.port.tree.blockSignals(False)

    def find_tree_item(self, node_id: str) -> QTreeWidgetItem | None:
        """Find an item through the public tree API used by the shell port."""
        pending = [self.port.tree.topLevelItem(index) for index in range(self.port.tree.topLevelItemCount())]
        while pending:
            item = pending.pop()
            if item is None:
                continue
            if str(item.data(0, Qt.UserRole)) == str(node_id):
                return item
            pending.extend((item.child(index) for index in range(item.childCount())))
        return None

    def refresh(self) -> None:
        if self.port.document_manager.active is None:
            return
        document = self.port.session.document
        self.sync_document_docks(document)
        widget = self.port._document_widgets.get(document.id)
        if isinstance(document, SceneDocument):
            self.refresh_scene_document(document, widget)
        else:
            self.refresh_foreign_document(document, widget)
        self.port._update_actions()
        self.update_title()

    def apply_invalidation(self, document_id: str, invalidation: InvalidationSet) -> None:
        """Apply finite application damage through public panel operations."""
        session = next((item for item in self.port.document_manager if item.document.id == document_id), None)
        if session is None:
            return
        if invalidation.is_full_sync:
            if self.port.document_manager.active is session:
                self.refresh()
            return
        document = session.document
        widget = self.port._document_widgets.get(document_id)
        active = self.port.document_manager.active is session
        scopes = invalidation.scopes
        if InvalidationScope.SCENE_TREE in scopes and active:
            self.populate_tree()
        if InvalidationScope.SCENE_CANVAS in scopes and isinstance(widget, SceneViewport):
            was_syncing = self.port._syncing_selection
            self.port._syncing_selection = True
            try:
                widget.rebuild(document)
                if active:
                    self.port.viewport = widget
                    widget.select_node(session.editor_state.selection.node_id or document.root.id)
            finally:
                self.port._syncing_selection = was_syncing
        if InvalidationScope.INSPECTOR in scopes and active:
            self.refresh_active_inspector(document)
        if InvalidationScope.TIMELINE in scopes and active:
            self.refresh_active_timeline(document)
        if InvalidationScope.STATE_GRAPH in scopes and active:
            self.refresh_active_state_graph(document)
        if InvalidationScope.VARIABLES in scopes and active:
            self.refresh_active_variables(document)
        if InvalidationScope.PATTERN in scopes and isinstance(widget, PatternWorkspace):
            self.apply_pattern_document_view(session, widget)
        if InvalidationScope.UI_CANVAS in scopes and isinstance(widget, UIWorkspace):
            self.port.ui_document_service.apply_ui_document_view(widget, document)
        if InvalidationScope.BACKGROUND in scopes and isinstance(widget, BackgroundWorkspace):
            widget.set_document(document)
        if InvalidationScope.ACTIONS in scopes and active:
            self.port._update_actions()
        if InvalidationScope.TITLE in scopes:
            self.update_title()

    def refresh_active_inspector(self, document) -> None:
        session = self.port.session
        if isinstance(document, SceneDocument):
            state = session.editor_state
            clip_id = state.selection.clip_id
            track_id = state.selection.track_id
            clip_result = find_timeline_clip(document, clip_id) if clip_id else None
            track_result = find_timeline_track(document, track_id, state.selection.state_id) if track_id else None
            if clip_result is not None:
                self.port.inspector.set_timeline_clip(clip_result[0], clip_result[1], list(document.root.walk()))
            elif track_result is not None:
                self.port.inspector.set_timeline_track(track_result, list(document.root.walk()))
            else:
                self.port.inspector.set_node(session.node(state.selection.node_id))
            return
        if isinstance(document, UIDocument):
            from ..main_window_support import _find_ui_node
            self.port.inspector.set_ui_node(_find_ui_node(document.root, session.editor_state.selection.ui_node_id or ''))
            return
        if isinstance(document, BackgroundDocument):
            self.port.inspector.set_background_document(document)
            return
        selected_id = session.editor_state.selection.graph_node_id
        selected = next((node for node in (document.graph.nodes if document.graph else ()) if node.id == selected_id), None)
        if session.editor_state.pattern.graph_mode:
            self.port.inspector.set_graph_node(selected)
        else:
            self.port.inspector.set_pattern(document)

    def refresh_active_timeline(self, document) -> None:
        if not isinstance(document, SceneDocument):
            self.port.timeline.clear_document()
            return
        state = self.port.session.editor_state
        state_id = str(state.selection.state_id or document.state_graph.initial_state_id)
        self.port.timeline.set_document(document, state_id=state_id, selected_clip_id=state.selection.clip_id, zoom=state.timeline.zoom)
        self.port.timeline.selected_track_id = state.selection.track_id
        overlay = self.port._runtime_overlay_for(self.port.session)
        self.port.timeline.set_playhead(overlay.frame if overlay is not None else state.timeline.playhead_frame, emit=False)

    def refresh_active_state_graph(self, document) -> None:
        if not isinstance(document, SceneDocument):
            self.port.state_graph.clear_document()
            return
        state = self.port.session.editor_state
        overlay = self.port._runtime_overlay_for(self.port.session)
        self.port.state_graph.set_document(document, selected_state_id=state.selection.state_id or document.state_graph.initial_state_id, active_state_path=overlay.state_path if overlay is not None else ())

    def refresh_active_variables(self, document) -> None:
        if not isinstance(document, SceneDocument):
            self.port.variables.clear_document()
            return
        state = self.port.session.editor_state
        self.port.variables.set_document(document, state_id=state.selection.state_id)
        overlay = self.port._runtime_overlay_for(self.port.session)
        self.port.variables.set_runtime_overlay(overlay.mutable_variable_snapshot() if overlay is not None else {})

    def refresh_scene_document(self, document: SceneDocument, widget) -> None:
        """Repopulate the tree, timeline, state graph and inspector for a scene."""
        if self.port.session.node(self.port._selected_id) is None:
            self.port._selected_id = document.root.id
        self.populate_tree()
        self.port.tree.setEnabled(True)
        if isinstance(widget, SceneViewport):
            was_syncing = self.port._syncing_selection
            self.port._syncing_selection = True
            try:
                self.port.viewport = widget
                widget.rebuild(document)
                widget.select_node(self.port._selected_id)
            finally:
                self.port._syncing_selection = was_syncing
        state = self.port.session.editor_state
        selected_state_id = str(state.selection.state_id or document.state_graph.initial_state_id)
        selected_state = document.state_graph.find_state(selected_state_id)
        if selected_state is None:
            selected_state_id = document.state_graph.initial_state_id
            selected_state = document.state_graph.initial_state
        state.selection.state_id = selected_state_id
        selected_clip_id = state.selection.clip_id
        selected_track_id = state.selection.track_id
        clip_result = find_timeline_clip(document, str(selected_clip_id)) if selected_clip_id else None
        track_result = find_timeline_track(document, str(selected_track_id), selected_state_id) if selected_track_id else None
        if clip_result is not None and clip_result[0] not in selected_state.tracks:
            clip_result = None
        if clip_result is not None:
            self.port.inspector.set_timeline_clip(clip_result[0], clip_result[1], list(document.root.walk()))
        elif track_result is not None:
            self.port.inspector.set_timeline_track(track_result, list(document.root.walk()))
        else:
            state.selection.clip_id = None
            state.selection.track_id = None
            self.port.inspector.set_node(self.port.session.node(self.port._selected_id))
        self.port.timeline.set_document(document, state_id=selected_state_id, selected_clip_id=clip_result[1].id if clip_result is not None else None, zoom=state.timeline.zoom)
        self.port.timeline.selected_track_id = track_result.id if track_result is not None else None
        overlay = self.port._runtime_overlay_for(self.port.session)
        self.port.timeline.set_playhead(overlay.frame if overlay is not None else state.timeline.playhead_frame, emit=False)
        self.port.timeline.set_active_clips(overlay.active_clip_ids if overlay is not None else ())
        self.port.timeline.set_reactive_overlay(overlay.mutable_reactive_overlay() if overlay is not None else {})
        self.port.state_graph.set_document(document, selected_state_id=selected_state_id, active_state_path=overlay.state_path if overlay is not None else ())
        self.port.variables.set_document(document, state_id=selected_state_id)
        self.port.variables.set_runtime_overlay(overlay.mutable_variable_snapshot() if overlay is not None else {})

    def refresh_foreign_document(self, document, widget) -> None:
        """Refresh docks for UI, background and pattern documents.

            The UI and background paths return early; ``_refresh`` runs the shared
            ``_update_actions``/``_update_title`` tail once control returns."""
        self.port.tree.blockSignals(True)
        self.port.tree.clear()
        self.port.tree.blockSignals(False)
        self.port.tree.setEnabled(False)
        self.port.state_graph.clear_document()
        self.port.variables.clear_document()
        if isinstance(document, UIDocument):
            self.port.inspector.set_ui_node(None)
            if isinstance(widget, UIWorkspace):
                    QTimer.singleShot(0, self.port.qt_parent, lambda doc=document, w=widget: self.port.ui_document_service.apply_ui_document_view_if_alive(w, doc))
            return
        if isinstance(document, BackgroundDocument):
            self.port.inspector.set_background_document(document)
            if isinstance(widget, BackgroundWorkspace):
                widget.set_document(document)
                selected_layer = self.port.session.editor_state.background_selected_layer
                if widget.layers.count():
                    widget.layers.setCurrentRow(max(0, min(int(selected_layer), widget.layers.count() - 1)))
            self.port.timeline.clear_document()
            return
        state = self.port.session.editor_state
        graph_mode = state.pattern.graph_mode
        selected_graph_node = state.selection.graph_node_id
        if graph_mode and document.graph is not None:
            selected_node = next((node for node in document.graph.nodes if node.id == str(selected_graph_node)), None)
            self.port.inspector.set_graph_node(selected_node)
        else:
            self.port.inspector.set_pattern(document)
        self.port.timeline.clear_document()
        if isinstance(widget, PatternWorkspace):
            self.apply_pattern_document_view(self.port.session, widget)

    def apply_pattern_document_view(self, session: ManagedDocument, widget: PatternWorkspace) -> None:
        """Rebind the public Pattern port from authoring and typed view state."""
        document = session.document
        if not isinstance(document, PatternDocument):
            return
        state = session.editor_state.pattern
        widget.set_document(document, player_position=state.player_position)
        preset_instance = self.port._preset_resolver.instance_from_document(document)
        if preset_instance is not None:
            descriptor = self.port._preset_resolver.registry.resolve(preset_instance.preset_id, preset_instance.version)
            widget.set_preset_expansion(descriptor, self.port._preset_resolver.expand_virtual(preset_instance), dict(preset_instance.parameters), dict(preset_instance.slot_overrides), self.port._preset_resolver.registry.migration_targets(preset_instance.preset_id, preset_instance.version))
        else:
            widget.set_preset_expansion(None)
        mode = 'preset' if state.preset_mode and preset_instance is not None else 'graph' if state.graph_mode else 'recipe'
        widget.set_mode(mode, emit=False)
        level = state.authoring_level
        if widget.level_picker.findData(level) < 0:
            level = 'l1'
        widget.set_authoring_level(level)
        if hasattr(self.port, 'resource_browser'):
            widget.set_available_bullets(self.port.resource_browser.index.records)
        translate_widget_tree(widget, self.port.language_manager)

    def sync_document_docks(self, document) -> None:
        """Show only tools that can act on the active document."""
        is_scene = isinstance(document, SceneDocument)
        for dock in (self.port.scene_dock, self.port.state_graph_dock, self.port.variables_dock):
            dock.setVisible(is_scene)
        self.port.inspector_dock.setVisible(True)
        if is_scene:
            self.port.tabifyDockWidget(self.port.scene_dock, self.port.state_graph_dock)
            self.port.tabifyDockWidget(self.port.inspector_dock, self.port.variables_dock)
            self.port.scene_dock.raise_()
            self.port.inspector_dock.raise_()

    def update_title(self) -> None:
        name = self.port.language_manager.translate(self.port.session.display_name)
        self.port.setWindowModified(self.port.session.is_dirty)
        app_title = self.port.language_manager.translate(APP_NAME)
        self.port.setWindowTitle(f'{name}[*] — {app_title}')
        for session in self.port.document_manager:
            widget = self.port._document_widgets.get(session.document.id)
            if widget is None:
                continue
            index = self.port.central_tabs.indexOf(widget)
            if index >= 0:
                suffix = ' *' if session.is_dirty else ''
                display_name = self.port.language_manager.translate(session.display_name)
                self.port.central_tabs.setTabText(index, display_name + suffix)
        if hasattr(self.port, 'language_manager'):
            translate_widget_tree(self.port.qt_parent, self.port.language_manager)
            self.port._update_language_actions()

    def log(self, message: str) -> None:
        self.port.output.append(html.escape(self.port.language_manager.translate(str(message))))

    def fit_viewport(self) -> None:
        self.port.viewport.fit_canvas()

    def show_error(self, title: str, error: Exception) -> None:
        self.log(f'[error] {title}: {error}')
        QMessageBox.critical(self.port.qt_parent, self.port.language_manager.translate(title), str(error))

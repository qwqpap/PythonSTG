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
from .ports import ActionsPort


class ShellActions(WindowService[ActionsPort]):
    def refresh_node_add_menu(self) -> None:
        """Expose newly activated SDK node contributions in the shell menu."""
        menu = getattr(self.port, '_node_add_menu', None)
        if menu is None:
            return
        for type_name, spec in self.port.node_type_registry.items():
            if type_name == 'SceneRoot' or type_name in self.port._node_menu_types:
                continue
            action = menu.addAction(spec.display_name)
            action.triggered.connect(lambda checked=False, node_type=type_name: self.port.scene_edit_service.add_node(node_type))
            self.port._node_menu_types.add(type_name)

    def build_actions(self) -> None:
        self.port.action_new = self.action('New Scene', QKeySequence.New, self.port.document_service.new_scene)
        self.port.action_new_pattern = self.action('New Pattern', 'Ctrl+Shift+N', self.port.pattern_service.new_pattern)
        self.port.action_open = self.action('Open Resource…', QKeySequence.Open, self.port.document_service.open_resource)
        self.port.action_save = self.action('Save', QKeySequence.Save, self.port.document_service.save_scene)
        self.port.action_save_as = self.action('Save As…', QKeySequence.SaveAs, self.port.document_service.save_scene_as)
        self.port.action_revert = self.action('Revert', None, self.port.document_service.revert_document)
        self.port.action_close_document = self.action('Close Document', QKeySequence.Close, self.port.document_service.close_active_document)
        self.port.action_undo = self.action('Undo', QKeySequence.Undo, self.port.undo)
        self.port.action_redo = self.action('Redo', QKeySequence.Redo, self.port.redo)
        self.port.action_delete = self.action('Delete Node', QKeySequence.Delete, self.port.scene_edit_service.delete_selected)
        self.port.action_rename = self.action('Rename Node', Qt.Key_F2, self.port.scene_edit_service.rename_selected)
        self.port.action_move_up = self.action('Move Up', 'Alt+Up', lambda: self.port.scene_edit_service.move_selected(-1))
        self.port.action_move_down = self.action('Move Down', 'Alt+Down', lambda: self.port.scene_edit_service.move_selected(1))
        self.port.action_outdent = self.action('Move to Parent', 'Alt+Left', self.port.scene_edit_service.outdent_selected)
        self.port.action_indent = self.action('Make Child of Previous', 'Alt+Right', self.port.scene_edit_service.indent_selected)
        self.port.action_run = self.action('Run / Preview', Qt.Key_F6, self.port.preview_service.run_preview)
        self.port.action_fit = self.action('Frame Canvas', 'F', self.port._fit_viewport)
        self.port.action_language_english = self.action('English', None, lambda checked=False: self.port.set_language(LANGUAGE_ENGLISH))
        self.port.action_language_english.setCheckable(True)
        self.port.action_language_chinese = self.action('简体中文', None, lambda checked=False: self.port.set_language(LANGUAGE_CHINESE))
        self.port.action_language_chinese.setCheckable(True)

    def action(self, text: str, shortcut, callback: Callable) -> QAction:
        action = QAction(text, self.port.qt_parent)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        self.port.addAction(action)
        return action

    def build_menus(self) -> None:
        """Populate the menu bar (File/Edit/Run/Tools/Language)."""
        file_menu = self.port.menuBar().addMenu('&File')
        file_menu.addActions([self.port.action_new, self.port.action_new_pattern, self.port.action_open, self.port.action_save, self.port.action_save_as, self.port.action_revert, self.port.action_close_document])
        edit_menu = self.port.menuBar().addMenu('&Edit')
        edit_menu.addActions([self.port.action_undo, self.port.action_redo, self.port.action_rename, self.port.action_delete, self.port.action_move_up, self.port.action_move_down, self.port.action_outdent, self.port.action_indent])
        run_menu = self.port.menuBar().addMenu('&Run')
        run_menu.addActions([self.port.action_run, self.port.action_fit])
        tools_menu = self.port.menuBar().addMenu('&Tools')
        for plugin in self.port.plugin_registry.all():
            action = tools_menu.addAction(plugin.title)
            action.setObjectName(f'pluginAction_{plugin.id}')
            action.setToolTip(plugin.description)
            if plugin.shortcut:
                action.setShortcut(plugin.shortcut)
            action.triggered.connect(lambda checked=False, plugin_id=plugin.id: self.port.workbench_service.open_plugin(plugin_id))
        self.port.language_menu = self.port.menuBar().addMenu('&Language')
        self.port.language_menu.addActions([self.port.action_language_english, self.port.action_language_chinese])

    def build_main_toolbar(self) -> None:
        """Assemble the main toolbar."""
        main_toolbar = QToolBar('Main', self.port.qt_parent)
        self.port.main_toolbar = main_toolbar
        main_toolbar.setObjectName('mainToolbar')
        main_toolbar.setMovable(False)
        main_toolbar.addActions([self.port.action_new, self.port.action_open, self.port.action_save])
        main_toolbar.addSeparator()
        main_toolbar.addActions([self.port.action_undo, self.port.action_redo])
        main_toolbar.addSeparator()
        main_toolbar.addAction(self.port.action_run)
        self.port.addToolBar(main_toolbar)

    def update_actions(self) -> None:
        self.port.action_undo.setEnabled(self.port.session.commands.can_undo)
        self.port.action_redo.setEnabled(self.port.session.commands.can_redo)
        self.port.action_undo.setText(f'Undo {self.port.session.commands.undo_label}' if self.port.session.commands.undo_label else 'Undo')
        self.port.action_redo.setText(f'Redo {self.port.session.commands.redo_label}' if self.port.session.commands.redo_label else 'Redo')
        is_scene = isinstance(self.port.session.document, SceneDocument)
        is_root = is_scene and self.port._selected_id == self.port.session.document.root.id
        self.port.action_delete.setEnabled(is_scene and (not is_root))
        self.port.action_rename.setEnabled(is_scene and (not is_root))
        self.port.action_move_up.setEnabled(is_scene and (not is_root))
        self.port.action_move_down.setEnabled(is_scene and (not is_root))
        self.port.action_outdent.setEnabled(is_scene and (not is_root))
        self.port.action_indent.setEnabled(is_scene and (not is_root))
        self.port.action_revert.setEnabled(self.port.session.is_dirty or self.port.session.path is not None)

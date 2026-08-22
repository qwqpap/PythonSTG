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
from .ports import LifecyclePort


class ShellLifecycle(WindowService[LifecyclePort]):
    def set_language(self, language: str) -> None:
        """Switch UI labels without changing document or runtime data."""
        self.port.language_manager.set_language(language)

    def language_changed(self, _language: str) -> None:
        if hasattr(self.port, 'tree'):
            self.port.state_graph.set_language_manager(self.port.language_manager)
            self.port.inspector.set_language_manager(self.port.language_manager)
            self.port.timeline.set_language_manager(self.port.language_manager)
            for widget in self.port._document_widgets.values():
                if isinstance(widget, PatternWorkspace):
                    widget.set_language_manager(self.port.language_manager)
                    widget.set_available_presets(self.port._preset_library.presets)
        translate_widget_tree(self.port.qt_parent, self.port.language_manager)
        runtime_host = getattr(self.port, '_runtime_preview_host', None)
        if runtime_host is not None:
            index = self.port.central_tabs.indexOf(runtime_host)
            if index >= 0:
                self.port.central_tabs.setTabText(index, self.port.language_manager.translate('Runtime Preview'))
        self.update_language_actions()
        if hasattr(self.port, 'central_tabs'):
            self.port._update_title()

    def update_language_actions(self) -> None:
        english = self.port.language == LANGUAGE_ENGLISH
        self.port.action_language_english.setChecked(english)
        self.port.action_language_chinese.setChecked(not english)

    def save_layout(self, path: str | Path) -> Path:
        """Persist dock/tab state plus open document paths."""
        payload = {'schema_version': 1, 'window_state': bytes(self.port.saveState()).decode('latin-1'), 'open_documents': [session.resource_uri for session in self.port.document_manager if session.resource_uri is not None], 'active_document': self.port.session.resource_uri if self.port.document_manager.active is not None else None}
        return atomic_write_json(path, payload)

    def restore_layout(self, path: str | Path) -> None:
        """Restore dock/tab geometry and reopen persisted documents."""
        layout_path = Path(path).expanduser().resolve()
        try:
            data = json.loads(layout_path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            line = getattr(exc, 'lineno', None)
            location = f' at line {line}' if line is not None else ''
            raise ResourceDocumentError(f'{layout_path}: invalid layout JSON{location}: {exc}') from exc
        if not isinstance(data, dict):
            raise ResourceDocumentError(f'{layout_path}: layout must be an object')
        if data.get('schema_version') != 1:
            raise ResourceDocumentError(f'{layout_path}: unsupported layout schema_version')
        documents = data.get('open_documents')
        if not isinstance(documents, list):
            raise ResourceDocumentError(f'{layout_path}: open_documents must be an array')
        if len(documents) > 256:
            raise ResourceDocumentError(f'{layout_path}: open_documents exceeds the 256-document limit')
        resolved_documents: list[Path] = []
        for index, document_uri in enumerate(documents):
            if not isinstance(document_uri, str) or not document_uri.startswith('res://'):
                raise ResourceDocumentError(f'{layout_path}: open_documents[{index}] must be a res:// URI')
            try:
                reference = ResourceReference.parse(document_uri)
                if reference.subresource is not None:
                    raise ResourceDocumentError('layout document URI cannot contain a fragment')
                resolved = reference.resolve(self.port.project, must_exist=True)
                self.port.project.relative(resolved)
                self.port.document_manager.store.load(resolved)
            except (OSError, ValueError, ResourceDocumentError) as exc:
                raise ResourceDocumentError(f'{layout_path}: invalid open_documents[{index}] {document_uri!r}: {exc}') from exc
            resolved_documents.append(resolved)
        window_state = data.get('window_state')
        if window_state is not None and (not isinstance(window_state, str)):
            raise ResourceDocumentError(f'{layout_path}: window_state must be a string')
        active_uri = data.get('active_document')
        if active_uri is not None and active_uri not in documents:
            raise ResourceDocumentError(f'{layout_path}: active_document must refer to open_documents')
        if isinstance(window_state, str):
            self.port.restoreState(bytes(window_state.encode('latin-1')))
        for resolved in resolved_documents:
            self.port.document_service.open_document(resolved)
        if isinstance(active_uri, str):
            target = ResourceReference.parse(active_uri).resolve(self.port.project, must_exist=True)
            session = self.port.document_manager.find_path(target)
            if session is not None:
                self.port.document_manager.activate(session)

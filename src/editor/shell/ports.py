"""Explicit capability adapters supplied to composed shell services.

Each adapter exposes only the window capabilities used by one service.  There
is deliberately no ``__getattr__``/``__setattr__`` fallback: adding a new
cross-boundary dependency requires an explicit port change and contract review.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .main_window import EditorMainWindow


class _ExplicitWindowPort:
    def __init__(self, window: "EditorMainWindow") -> None:
        self._window = window

    @property
    def qt_parent(self) -> Any:
        """QObject/QWidget parent capability without a general proxy surface."""
        return self._window


class AuthoringPort(_ExplicitWindowPort):
    """Capabilities required by ``AuthoringService``."""

    @property
    def _log(self) -> Any:
        return self._window._log

    @property
    def _show_error(self) -> Any:
        return self._window._show_error

    @property
    def apply_invalidation(self) -> Any:
        return self._window.apply_invalidation

    @property
    def editor_coordinator(self) -> Any:
        return self._window.editor_coordinator

    @property
    def preview_service(self) -> Any:
        return self._window.preview_service

    @property
    def session(self) -> Any:
        return self._window.session

    @property
    def statusBar(self) -> Any:
        return self._window.statusBar

    @property
    def timeline(self) -> Any:
        return self._window.timeline


class DocumentPort(_ExplicitWindowPort):
    """Capabilities required by ``DocumentService``."""

    @property
    def tree(self) -> Any:
        return self._window.tree

    @property
    def _active_pattern_document(self) -> Any:
        return self._window._active_pattern_document

    @_active_pattern_document.setter
    def _active_pattern_document(self, value: Any) -> None:
        self._window._active_pattern_document = value

    @property
    def _active_pattern_resource(self) -> Any:
        return self._window._active_pattern_resource

    @_active_pattern_resource.setter
    def _active_pattern_resource(self, value: Any) -> None:
        self._window._active_pattern_resource = value

    @property
    def _active_pattern_session(self) -> Any:
        return self._window._active_pattern_session

    @_active_pattern_session.setter
    def _active_pattern_session(self, value: Any) -> None:
        self._window._active_pattern_session = value

    @property
    def _document_widgets(self) -> Any:
        return self._window._document_widgets

    @property
    def _log(self) -> Any:
        return self._window._log

    @property
    def _plugin_widgets(self) -> Any:
        return self._window._plugin_widgets

    @property
    def _preset_library(self) -> Any:
        return self._window._preset_library

    @property
    def _preview_session(self) -> Any:
        return self._window._preview_session

    @property
    def _runtime_preview_host(self) -> Any:
        return self._window._runtime_preview_host

    @_runtime_preview_host.setter
    def _runtime_preview_host(self, value: Any) -> None:
        self._window._runtime_preview_host = value

    @property
    def _selected_id(self) -> Any:
        return self._window._selected_id

    @_selected_id.setter
    def _selected_id(self, value: Any) -> None:
        self._window._selected_id = value

    @property
    def _show_error(self) -> Any:
        return self._window._show_error

    @property
    def apply_invalidation(self) -> Any:
        return self._window.apply_invalidation

    @property
    def bottom_dock(self) -> Any:
        return self._window.bottom_dock

    @property
    def central_tabs(self) -> Any:
        return self._window.central_tabs

    @property
    def document_controller(self) -> Any:
        return self._window.document_controller

    @property
    def document_manager(self) -> Any:
        return self._window.document_manager

    @property
    def height(self) -> Any:
        return self._window.height

    @property
    def isVisible(self) -> Any:
        return self._window.isVisible

    @property
    def language_manager(self) -> Any:
        return self._window.language_manager

    @property
    def node_type_registry(self) -> Any:
        return self._window.node_type_registry

    @property
    def pattern_service(self) -> Any:
        return self._window.pattern_service

    @property
    def preview_panel(self) -> Any:
        return self._window.preview_panel

    @property
    def preview_service(self) -> Any:
        return self._window.preview_service

    @property
    def project(self) -> Any:
        return self._window.project

    @property
    def resizeDocks(self) -> Any:
        return self._window.resizeDocks

    @property
    def resource_browser(self) -> Any:
        return self._window.resource_browser

    @property
    def scene_edit_service(self) -> Any:
        return self._window.scene_edit_service

    @property
    def session(self) -> Any:
        return self._window.session

    @property
    def ui_document_service(self) -> Any:
        return self._window.ui_document_service

    @property
    def viewport(self) -> Any:
        return self._window.viewport

    @viewport.setter
    def viewport(self, value: Any) -> None:
        self._window.viewport = value

    @property
    def workbench_service(self) -> Any:
        return self._window.workbench_service


class PatternPort(_ExplicitWindowPort):
    """Capabilities required by ``PatternService``."""

    @property
    def _active_pattern_document(self) -> Any:
        return self._window._active_pattern_document

    @_active_pattern_document.setter
    def _active_pattern_document(self, value: Any) -> None:
        self._window._active_pattern_document = value

    @property
    def _active_pattern_resource(self) -> Any:
        return self._window._active_pattern_resource

    @_active_pattern_resource.setter
    def _active_pattern_resource(self, value: Any) -> None:
        self._window._active_pattern_resource = value

    @property
    def _active_pattern_session(self) -> Any:
        return self._window._active_pattern_session

    @_active_pattern_session.setter
    def _active_pattern_session(self, value: Any) -> None:
        self._window._active_pattern_session = value

    @property
    def _document_widgets(self) -> Any:
        return self._window._document_widgets

    @property
    def _log(self) -> Any:
        return self._window._log

    @property
    def _pattern_preview_client(self) -> Any:
        return self._window._pattern_preview_client

    @property
    def _preset_resolver(self) -> Any:
        return self._window._preset_resolver

    @property
    def _preview_session(self) -> Any:
        return self._window._preview_session

    @property
    def apply_invalidation(self) -> Any:
        return self._window.apply_invalidation

    @property
    def document_controller(self) -> Any:
        return self._window.document_controller

    @property
    def document_manager(self) -> Any:
        return self._window.document_manager

    @property
    def document_service(self) -> Any:
        return self._window.document_service

    @property
    def editor_coordinator(self) -> Any:
        return self._window.editor_coordinator

    @property
    def preview_panel(self) -> Any:
        return self._window.preview_panel

    @property
    def preview_service(self) -> Any:
        return self._window.preview_service

    @property
    def session(self) -> Any:
        return self._window.session


class PreviewPort(_ExplicitWindowPort):
    """Capabilities required by ``PreviewService``."""

    @property
    def _active_pattern_document(self) -> Any:
        return self._window._active_pattern_document

    @_active_pattern_document.setter
    def _active_pattern_document(self, value: Any) -> None:
        self._window._active_pattern_document = value

    @property
    def _active_pattern_resource(self) -> Any:
        return self._window._active_pattern_resource

    @_active_pattern_resource.setter
    def _active_pattern_resource(self, value: Any) -> None:
        self._window._active_pattern_resource = value

    @property
    def _active_pattern_session(self) -> Any:
        return self._window._active_pattern_session

    @_active_pattern_session.setter
    def _active_pattern_session(self, value: Any) -> None:
        self._window._active_pattern_session = value

    @property
    def _document_widgets(self) -> Any:
        return self._window._document_widgets

    @property
    def _log(self) -> Any:
        return self._window._log

    @property
    def _pattern_preview_client(self) -> Any:
        return self._window._pattern_preview_client

    @property
    def _preview_session(self) -> Any:
        return self._window._preview_session

    @property
    def _runtime_preview_host(self) -> Any:
        return self._window._runtime_preview_host

    @_runtime_preview_host.setter
    def _runtime_preview_host(self, value: Any) -> None:
        self._window._runtime_preview_host = value

    @property
    def _selected_id(self) -> Any:
        return self._window._selected_id

    @property
    def _show_error(self) -> Any:
        return self._window._show_error

    @property
    def bottom_tabs(self) -> Any:
        return self._window.bottom_tabs

    @property
    def central_tabs(self) -> Any:
        return self._window.central_tabs

    @property
    def document_manager(self) -> Any:
        return self._window.document_manager

    @property
    def document_service(self) -> Any:
        return self._window.document_service

    @property
    def language(self) -> Any:
        return self._window.language

    @property
    def language_manager(self) -> Any:
        return self._window.language_manager

    @property
    def pattern_service(self) -> Any:
        return self._window.pattern_service

    @property
    def preview_panel(self) -> Any:
        return self._window.preview_panel

    @property
    def project(self) -> Any:
        return self._window.project

    @property
    def session(self) -> Any:
        return self._window.session

    @property
    def state_graph(self) -> Any:
        return self._window.state_graph

    @property
    def statusBar(self) -> Any:
        return self._window.statusBar

    @property
    def timeline(self) -> Any:
        return self._window.timeline

    @property
    def variables(self) -> Any:
        return self._window.variables

    @property
    def workbench_service(self) -> Any:
        return self._window.workbench_service


class SceneEditPort(_ExplicitWindowPort):
    """Capabilities required by ``SceneEditService``."""

    @property
    def _find_tree_item(self) -> Any:
        return self._window._find_tree_item

    @property
    def _log(self) -> Any:
        return self._window._log

    @property
    def _selected_id(self) -> Any:
        return self._window._selected_id

    @property
    def _show_error(self) -> Any:
        return self._window._show_error

    @property
    def _syncing_selection(self) -> Any:
        return self._window._syncing_selection

    @_syncing_selection.setter
    def _syncing_selection(self, value: Any) -> None:
        self._window._syncing_selection = value

    @property
    def apply_invalidation(self) -> Any:
        return self._window.apply_invalidation

    @property
    def editor_coordinator(self) -> Any:
        return self._window.editor_coordinator

    @property
    def language(self) -> Any:
        return self._window.language

    @property
    def language_manager(self) -> Any:
        return self._window.language_manager

    @property
    def node_type_registry(self) -> Any:
        return self._window.node_type_registry

    @property
    def resource_browser(self) -> Any:
        return self._window.resource_browser

    @property
    def session(self) -> Any:
        return self._window.session

    @property
    def tree(self) -> Any:
        return self._window.tree


class TimelinePort(_ExplicitWindowPort):
    """Capabilities required by ``TimelineService``."""

    @property
    def _log(self) -> Any:
        return self._window._log

    @property
    def _pattern_preview_client(self) -> Any:
        return self._window._pattern_preview_client

    @property
    def _preview_session(self) -> Any:
        return self._window._preview_session

    @property
    def _show_error(self) -> Any:
        return self._window._show_error

    @property
    def _timeline_selection_dispatching(self) -> Any:
        return self._window._timeline_selection_dispatching

    @_timeline_selection_dispatching.setter
    def _timeline_selection_dispatching(self, value: Any) -> None:
        self._window._timeline_selection_dispatching = value

    @property
    def apply_invalidation(self) -> Any:
        return self._window.apply_invalidation

    @property
    def document_manager(self) -> Any:
        return self._window.document_manager

    @property
    def editor_coordinator(self) -> Any:
        return self._window.editor_coordinator

    @property
    def preview_service(self) -> Any:
        return self._window.preview_service

    @property
    def timeline(self) -> Any:
        return self._window.timeline


class UIDocumentPort(_ExplicitWindowPort):
    """Capabilities required by ``UIDocumentService``."""

    @property
    def _applying_background_invalidation(self) -> Any:
        return self._window._applying_background_invalidation

    @_applying_background_invalidation.setter
    def _applying_background_invalidation(self, value: Any) -> None:
        self._window._applying_background_invalidation = value

    @property
    def _log(self) -> Any:
        return self._window._log

    @property
    def _show_error(self) -> Any:
        return self._window._show_error

    @property
    def apply_invalidation(self) -> Any:
        return self._window.apply_invalidation

    @property
    def document_manager(self) -> Any:
        return self._window.document_manager

    @property
    def editor_coordinator(self) -> Any:
        return self._window.editor_coordinator

    @property
    def preview_panel(self) -> Any:
        return self._window.preview_panel

    @property
    def session(self) -> Any:
        return self._window.session


class WorkbenchPort(_ExplicitWindowPort):
    """Capabilities required by ``WorkbenchService``."""

    @property
    def _action_search_dialog(self) -> Any:
        return self._window._action_search_dialog

    @_action_search_dialog.setter
    def _action_search_dialog(self, value: Any) -> None:
        self._window._action_search_dialog = value

    @property
    def _document_widgets(self) -> Any:
        return self._window._document_widgets

    @property
    def _log(self) -> Any:
        return self._window._log

    @property
    def _plugin_widgets(self) -> Any:
        return self._window._plugin_widgets

    @property
    def _refresh_node_add_menu(self) -> Any:
        return self._window._refresh_node_add_menu

    @property
    def _selected_id(self) -> Any:
        return self._window._selected_id

    @property
    def _show_error(self) -> Any:
        return self._window._show_error

    @property
    def _tool_processes(self) -> Any:
        return self._window._tool_processes

    @property
    def action_catalog(self) -> Any:
        return self._window.action_catalog

    @property
    def action_executor(self) -> Any:
        return self._window.action_executor

    @property
    def apply_invalidation(self) -> Any:
        return self._window.apply_invalidation

    @property
    def bottom_tabs(self) -> Any:
        return self._window.bottom_tabs

    @property
    def central_tabs(self) -> Any:
        return self._window.central_tabs

    @property
    def document_controller(self) -> Any:
        return self._window.document_controller

    @property
    def document_manager(self) -> Any:
        return self._window.document_manager

    @property
    def document_service(self) -> Any:
        return self._window.document_service

    @property
    def editor_coordinator(self) -> Any:
        return self._window.editor_coordinator

    @property
    def language_manager(self) -> Any:
        return self._window.language_manager

    @property
    def output(self) -> Any:
        return self._window.output

    @property
    def pattern_service(self) -> Any:
        return self._window.pattern_service

    @property
    def plugin_registry(self) -> Any:
        return self._window.plugin_registry

    @property
    def preview_service(self) -> Any:
        return self._window.preview_service

    @property
    def project(self) -> Any:
        return self._window.project

    @property
    def scene_edit_service(self) -> Any:
        return self._window.scene_edit_service

    @property
    def session(self) -> Any:
        return self._window.session

    @property
    def statusBar(self) -> Any:
        return self._window.statusBar

    @property
    def timeline(self) -> Any:
        return self._window.timeline

    @property
    def timeline_service(self) -> Any:
        return self._window.timeline_service


__all__ = [
    "AuthoringPort",
    "DocumentPort",
    "PatternPort",
    "PreviewPort",
    "SceneEditPort",
    "TimelinePort",
    "UIDocumentPort",
    "WorkbenchPort",
]


class ActionsPort(_ExplicitWindowPort):
    """Capabilities required by the composed shell actions service."""

    @property
    def qt_parent(self) -> Any:
        return self._window

    @property
    def _fit_viewport(self) -> Any:
        return self._window._fit_viewport

    @property
    def _node_menu_types(self) -> Any:
        return self._window._node_menu_types

    @property
    def _selected_id(self) -> Any:
        return self._window._selected_id

    @property
    def action_close_document(self) -> Any:
        return self._window.action_close_document

    @action_close_document.setter
    def action_close_document(self, value: Any) -> None:
        self._window.action_close_document = value

    @property
    def action_delete(self) -> Any:
        return self._window.action_delete

    @action_delete.setter
    def action_delete(self, value: Any) -> None:
        self._window.action_delete = value

    @property
    def action_fit(self) -> Any:
        return self._window.action_fit

    @action_fit.setter
    def action_fit(self, value: Any) -> None:
        self._window.action_fit = value

    @property
    def action_indent(self) -> Any:
        return self._window.action_indent

    @action_indent.setter
    def action_indent(self, value: Any) -> None:
        self._window.action_indent = value

    @property
    def action_language_chinese(self) -> Any:
        return self._window.action_language_chinese

    @action_language_chinese.setter
    def action_language_chinese(self, value: Any) -> None:
        self._window.action_language_chinese = value

    @property
    def action_language_english(self) -> Any:
        return self._window.action_language_english

    @action_language_english.setter
    def action_language_english(self, value: Any) -> None:
        self._window.action_language_english = value

    @property
    def action_move_down(self) -> Any:
        return self._window.action_move_down

    @action_move_down.setter
    def action_move_down(self, value: Any) -> None:
        self._window.action_move_down = value

    @property
    def action_move_up(self) -> Any:
        return self._window.action_move_up

    @action_move_up.setter
    def action_move_up(self, value: Any) -> None:
        self._window.action_move_up = value

    @property
    def action_new(self) -> Any:
        return self._window.action_new

    @action_new.setter
    def action_new(self, value: Any) -> None:
        self._window.action_new = value

    @property
    def action_new_pattern(self) -> Any:
        return self._window.action_new_pattern

    @action_new_pattern.setter
    def action_new_pattern(self, value: Any) -> None:
        self._window.action_new_pattern = value

    @property
    def action_open(self) -> Any:
        return self._window.action_open

    @action_open.setter
    def action_open(self, value: Any) -> None:
        self._window.action_open = value

    @property
    def action_outdent(self) -> Any:
        return self._window.action_outdent

    @action_outdent.setter
    def action_outdent(self, value: Any) -> None:
        self._window.action_outdent = value

    @property
    def action_redo(self) -> Any:
        return self._window.action_redo

    @action_redo.setter
    def action_redo(self, value: Any) -> None:
        self._window.action_redo = value

    @property
    def action_rename(self) -> Any:
        return self._window.action_rename

    @action_rename.setter
    def action_rename(self, value: Any) -> None:
        self._window.action_rename = value

    @property
    def action_revert(self) -> Any:
        return self._window.action_revert

    @action_revert.setter
    def action_revert(self, value: Any) -> None:
        self._window.action_revert = value

    @property
    def action_run(self) -> Any:
        return self._window.action_run

    @action_run.setter
    def action_run(self, value: Any) -> None:
        self._window.action_run = value

    @property
    def action_save(self) -> Any:
        return self._window.action_save

    @action_save.setter
    def action_save(self, value: Any) -> None:
        self._window.action_save = value

    @property
    def action_save_as(self) -> Any:
        return self._window.action_save_as

    @action_save_as.setter
    def action_save_as(self, value: Any) -> None:
        self._window.action_save_as = value

    @property
    def action_undo(self) -> Any:
        return self._window.action_undo

    @action_undo.setter
    def action_undo(self, value: Any) -> None:
        self._window.action_undo = value

    @property
    def addAction(self) -> Any:
        return self._window.addAction

    @property
    def addToolBar(self) -> Any:
        return self._window.addToolBar

    @property
    def document_service(self) -> Any:
        return self._window.document_service

    @property
    def language_menu(self) -> Any:
        return self._window.language_menu

    @language_menu.setter
    def language_menu(self, value: Any) -> None:
        self._window.language_menu = value

    @property
    def main_toolbar(self) -> Any:
        return self._window.main_toolbar

    @main_toolbar.setter
    def main_toolbar(self, value: Any) -> None:
        self._window.main_toolbar = value

    @property
    def menuBar(self) -> Any:
        return self._window.menuBar

    @property
    def node_type_registry(self) -> Any:
        return self._window.node_type_registry

    @property
    def pattern_service(self) -> Any:
        return self._window.pattern_service

    @property
    def plugin_registry(self) -> Any:
        return self._window.plugin_registry

    @property
    def preview_service(self) -> Any:
        return self._window.preview_service

    @property
    def redo(self) -> Any:
        return self._window.redo

    @property
    def scene_edit_service(self) -> Any:
        return self._window.scene_edit_service

    @property
    def session(self) -> Any:
        return self._window.session

    @property
    def set_language(self) -> Any:
        return self._window.set_language

    @property
    def undo(self) -> Any:
        return self._window.undo

    @property
    def workbench_service(self) -> Any:
        return self._window.workbench_service



class DocksPort(_ExplicitWindowPort):
    """Capabilities required by the composed shell docks service."""

    @property
    def qt_parent(self) -> Any:
        return self._window

    @property
    def _build_main_toolbar(self) -> Any:
        return self._window._build_main_toolbar

    @property
    def _build_menus(self) -> Any:
        return self._window._build_menus

    @property
    def _document_widgets(self) -> Any:
        return self._window._document_widgets

    @property
    def _node_add_menu(self) -> Any:
        return self._window._node_add_menu

    @_node_add_menu.setter
    def _node_add_menu(self, value: Any) -> None:
        self._window._node_add_menu = value

    @property
    def _node_menu_types(self) -> Any:
        return self._window._node_menu_types

    @_node_menu_types.setter
    def _node_menu_types(self, value: Any) -> None:
        self._window._node_menu_types = value

    @property
    def _plugin_widgets(self) -> Any:
        return self._window._plugin_widgets

    @property
    def _preset_resolver(self) -> Any:
        return self._window._preset_resolver

    @property
    def _runtime_overlay_for(self) -> Any:
        return self._window._runtime_overlay_for

    @property
    def _selected_id(self) -> Any:
        return self._window._selected_id

    @_selected_id.setter
    def _selected_id(self, value: Any) -> None:
        self._window._selected_id = value

    @property
    def _syncing_selection(self) -> Any:
        return self._window._syncing_selection

    @_syncing_selection.setter
    def _syncing_selection(self, value: Any) -> None:
        self._window._syncing_selection = value

    @property
    def _update_actions(self) -> Any:
        return self._window._update_actions

    @property
    def _update_language_actions(self) -> Any:
        return self._window._update_language_actions

    @property
    def action_indent(self) -> Any:
        return self._window.action_indent

    @property
    def action_move_down(self) -> Any:
        return self._window.action_move_down

    @property
    def action_move_up(self) -> Any:
        return self._window.action_move_up

    @property
    def action_outdent(self) -> Any:
        return self._window.action_outdent

    @property
    def addDockWidget(self) -> Any:
        return self._window.addDockWidget

    @property
    def authoring_service(self) -> Any:
        return self._window.authoring_service

    @property
    def bottom_dock(self) -> Any:
        return self._window.bottom_dock

    @bottom_dock.setter
    def bottom_dock(self, value: Any) -> None:
        self._window.bottom_dock = value

    @property
    def bottom_tabs(self) -> Any:
        return self._window.bottom_tabs

    @bottom_tabs.setter
    def bottom_tabs(self, value: Any) -> None:
        self._window.bottom_tabs = value

    @property
    def central_tabs(self) -> Any:
        return self._window.central_tabs

    @central_tabs.setter
    def central_tabs(self, value: Any) -> None:
        self._window.central_tabs = value

    @property
    def document_manager(self) -> Any:
        return self._window.document_manager

    @property
    def document_service(self) -> Any:
        return self._window.document_service

    @property
    def inspector(self) -> Any:
        return self._window.inspector

    @inspector.setter
    def inspector(self, value: Any) -> None:
        self._window.inspector = value

    @property
    def inspector_dock(self) -> Any:
        return self._window.inspector_dock

    @inspector_dock.setter
    def inspector_dock(self, value: Any) -> None:
        self._window.inspector_dock = value

    @property
    def language_manager(self) -> Any:
        return self._window.language_manager

    @property
    def node_type_registry(self) -> Any:
        return self._window.node_type_registry

    @property
    def output(self) -> Any:
        return self._window.output

    @output.setter
    def output(self, value: Any) -> None:
        self._window.output = value

    @property
    def pattern_service(self) -> Any:
        return self._window.pattern_service

    @property
    def plugin_registry(self) -> Any:
        return self._window.plugin_registry

    @property
    def preview_panel(self) -> Any:
        return self._window.preview_panel

    @preview_panel.setter
    def preview_panel(self, value: Any) -> None:
        self._window.preview_panel = value

    @property
    def preview_service(self) -> Any:
        return self._window.preview_service

    @property
    def project(self) -> Any:
        return self._window.project

    @property
    def resizeDocks(self) -> Any:
        return self._window.resizeDocks

    @property
    def resource_browser(self) -> Any:
        return self._window.resource_browser

    @resource_browser.setter
    def resource_browser(self, value: Any) -> None:
        self._window.resource_browser = value

    @property
    def scene_dock(self) -> Any:
        return self._window.scene_dock

    @scene_dock.setter
    def scene_dock(self, value: Any) -> None:
        self._window.scene_dock = value

    @property
    def scene_edit_service(self) -> Any:
        return self._window.scene_edit_service

    @property
    def session(self) -> Any:
        return self._window.session

    @property
    def setCentralWidget(self) -> Any:
        return self._window.setCentralWidget

    @property
    def setStyleSheet(self) -> Any:
        return self._window.setStyleSheet

    @property
    def setWindowModified(self) -> Any:
        return self._window.setWindowModified

    @property
    def setWindowTitle(self) -> Any:
        return self._window.setWindowTitle

    @property
    def state_graph(self) -> Any:
        return self._window.state_graph

    @state_graph.setter
    def state_graph(self, value: Any) -> None:
        self._window.state_graph = value

    @property
    def state_graph_dock(self) -> Any:
        return self._window.state_graph_dock

    @state_graph_dock.setter
    def state_graph_dock(self, value: Any) -> None:
        self._window.state_graph_dock = value

    @property
    def statusBar(self) -> Any:
        return self._window.statusBar

    @property
    def tabifyDockWidget(self) -> Any:
        return self._window.tabifyDockWidget

    @property
    def timeline(self) -> Any:
        return self._window.timeline

    @timeline.setter
    def timeline(self, value: Any) -> None:
        self._window.timeline = value

    @property
    def timeline_service(self) -> Any:
        return self._window.timeline_service

    @property
    def tree(self) -> Any:
        return self._window.tree

    @tree.setter
    def tree(self, value: Any) -> None:
        self._window.tree = value

    @property
    def ui_document_service(self) -> Any:
        return self._window.ui_document_service

    @property
    def variables(self) -> Any:
        return self._window.variables

    @variables.setter
    def variables(self, value: Any) -> None:
        self._window.variables = value

    @property
    def variables_dock(self) -> Any:
        return self._window.variables_dock

    @variables_dock.setter
    def variables_dock(self, value: Any) -> None:
        self._window.variables_dock = value

    @property
    def viewport(self) -> Any:
        return self._window.viewport

    @viewport.setter
    def viewport(self, value: Any) -> None:
        self._window.viewport = value

    @property
    def workbench_service(self) -> Any:
        return self._window.workbench_service



class LifecyclePort(_ExplicitWindowPort):
    """Capabilities required by the composed shell lifecycle service."""

    @property
    def qt_parent(self) -> Any:
        return self._window

    @property
    def _runtime_preview_host(self) -> Any:
        return self._window._runtime_preview_host

    @property
    def tree(self) -> Any:
        return self._window.tree

    @property
    def _document_widgets(self) -> Any:
        return self._window._document_widgets

    @property
    def _preset_library(self) -> Any:
        return self._window._preset_library

    @property
    def _update_title(self) -> Any:
        return self._window._update_title

    @property
    def action_language_chinese(self) -> Any:
        return self._window.action_language_chinese

    @property
    def action_language_english(self) -> Any:
        return self._window.action_language_english

    @property
    def central_tabs(self) -> Any:
        return self._window.central_tabs

    @property
    def document_manager(self) -> Any:
        return self._window.document_manager

    @property
    def document_service(self) -> Any:
        return self._window.document_service

    @property
    def inspector(self) -> Any:
        return self._window.inspector

    @property
    def language(self) -> Any:
        return self._window.language

    @property
    def language_manager(self) -> Any:
        return self._window.language_manager

    @property
    def project(self) -> Any:
        return self._window.project

    @property
    def restoreState(self) -> Any:
        return self._window.restoreState

    @property
    def saveState(self) -> Any:
        return self._window.saveState

    @property
    def session(self) -> Any:
        return self._window.session

    @property
    def state_graph(self) -> Any:
        return self._window.state_graph

    @property
    def timeline(self) -> Any:
        return self._window.timeline
    "ActionsPort",
    "DocksPort",
    "LifecyclePort",

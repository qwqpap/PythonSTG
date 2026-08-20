"""Workbench slots: plugins, resource browser, action search and diagnostics."""

from __future__ import annotations

import html
import sys
from pathlib import Path
from src.qt_compat.QtCore import QProcess, QUrl, Qt
from src.qt_compat.QtWidgets import QWidget
from .asset_index import AssetRecord
from .action_catalog import ActionDescriptor, ActionQuery
from .action_search import ActionSearchDialog
from .application import (
    AddSceneNodeIntent,
    IntentRejectedError,
    SelectNodeIntent,
    SetNodePropertyIntent,
)
from .document import SceneDocument
from .resource_browser import ResourceBrowserPanel
from .scene_compile import SceneSpellCompileError
from .application.queries import require_timeline_track
from .workbench import EditorPlugin, default_external_plugins
from .shell import WindowService


class WorkbenchService(WindowService):
    """Workbench slots: plugins, resource browser, action search and diagnostics.

    These slots stay bound to the window instance instead of moving into a
    controller object: every attribute they touch is owned by
    ``EditorMainWindow``, and the editor tests plus the three native gates drive
    these methods by name.  Mix in before the Qt base class, the same way
    ``SpaceTapSearchMixin`` is used by ``SceneViewport``.
    """

    def _open_scene_action_search(self) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        parent = self.session.node(self._selected_id) or self.session.document.root
        self._open_action_search("scene", parent_type=parent.type)

    def _open_action_search(
        self,
        context: str,
        *,
        input_type: str | None = None,
        parent_type: str | None = None,
    ) -> None:
        timeline_kind = None
        if context == "timeline" and self.timeline.selected_track_id:
            try:
                timeline_kind = require_timeline_track(
                    self.session.document, self.timeline.selected_track_id
                ).kind
            except (AttributeError, ValueError):
                timeline_kind = None
        dialog = ActionSearchDialog(
            self.action_catalog,
            ActionQuery(
                context=context,
                input_type=input_type,
                parent_type=parent_type,
                timeline_kind=timeline_kind,
            ),
            language_manager=self.language_manager,
            parent=self._window,
        )
        dialog.actionChosen.connect(self._execute_action)
        self._action_search_dialog = dialog
        dialog.open()

    def _execute_action(self, descriptor: ActionDescriptor) -> None:
        try:
            self.action_executor.execute(descriptor)
        except Exception as exc:
            self._show_error("Quick create failed", exc)

    def _execute_preset_action(self, descriptor: ActionDescriptor) -> None:
        self._apply_pattern_template(
            f"{descriptor.payload['preset_id']}@{descriptor.payload['version']}"
        )

    def _execute_graph_action(self, descriptor: ActionDescriptor) -> None:
        self._graph_node_create_requested(
            str(descriptor.payload["category"]),
            str(descriptor.payload["node_type"]),
        )

    def _execute_track_action(self, descriptor: ActionDescriptor) -> None:
        self._timeline_add_track(str(descriptor.payload["kind"]))

    def _execute_clip_action(self, descriptor: ActionDescriptor) -> None:
        track_id = self.timeline.selected_track_id
        if not track_id:
            raise ValueError("timeline.selected_track: select a compatible track first")
        track = require_timeline_track(self.session.document, track_id)
        if track.kind != str(descriptor.payload["kind"]):
            raise ValueError(
                f"timeline.track:{track.id}.kind: expected {track.kind}, "
                f"got {descriptor.payload['kind']}"
            )
        self._timeline_add_clip(track.id)

    def _execute_scene_action(self, descriptor: ActionDescriptor) -> None:
        self.add_node(str(descriptor.payload["node_type"]))

    def _register_plugins(self) -> None:
        self.plugin_registry.register(
            EditorPlugin(
                id="resource_browser",
                title="Assets",
                description="Browse project files and JSON sprite/animation subresources.",
                mode="bottom",
                factory=lambda: ResourceBrowserPanel(self.project),
            )
        )
        self.plugin_registry.register(
            EditorPlugin(
                id="bullet_aliases",
                title="Bullet Aliases",
                description="Edit bullet type and color to sprite mappings.",
                mode="central",
                factory=self._create_bullet_alias_editor,
            )
        )
        for plugin in default_external_plugins(self.project):
            self.plugin_registry.register(plugin)

    def _discover_sdk_plugins(self) -> None:
        """Register and activate project-local SDK manifests in isolation."""
        for manifest in self.plugin_sdk_registry.discover().values():
            try:
                self.plugin_sdk_registry.register(manifest)
            except Exception as exc:  # noqa: BLE001 - one bad plugin is isolated
                # The SDK keeps the structured error; this log is only the
                # editor-facing diagnostic and must not stop the shell.
                self._log(f"[plugin:error] {manifest.id}: {exc}")
        self.plugin_sdk_registry.activate_all()
        self._refresh_node_add_menu()

    @staticmethod
    def _create_bullet_alias_editor() -> QWidget:
        # Kept local on purpose: this pulls a ``tools.*`` GUI widget, and it is
        # the only ``src -> tools`` edge in the tree.  Importing it lazily keeps
        # the dependency direction (tools depend on src) intact and avoids
        # loading the alias editor unless a plugin actually opens it.
        from tools.bullet.bullet_alias_manager import BulletAliasManager

        editor = BulletAliasManager()
        editor.setWindowFlags(Qt.Widget)
        return editor

    def open_plugin(self, plugin_id: str) -> None:
        plugin = self.plugin_registry.get(plugin_id)
        if plugin.mode == "bottom":
            widget = self._plugin_widgets.get(plugin.id)
            if widget is not None:
                self.bottom_tabs.setCurrentWidget(widget)
            return
        if plugin.mode == "central":
            existing = self._plugin_widgets.get(plugin.id)
            if existing is not None:
                self.central_tabs.setCurrentWidget(existing)
                return
            widget = plugin.factory()
            widget.setProperty("editorPluginId", plugin.id)
            self._plugin_widgets[plugin.id] = widget
            index = self.central_tabs.addTab(widget, plugin.title)
            self.central_tabs.setCurrentIndex(index)
            self._log(f"[tool] opened {plugin.title}")
            return
        self._start_external_plugin(plugin)

    def _start_external_plugin(self, plugin: EditorPlugin) -> None:
        running = self._tool_processes.get(plugin.id)
        if running is not None and running.state() != QProcess.NotRunning:
            self.statusBar().showMessage(f"{plugin.title} is already running", 3000)
            return
        if plugin.script is None or not plugin.script.is_file():
            self._show_error(
                "Tool unavailable",
                ValueError(f"Tool script does not exist: {plugin.script}"),
            )
            return
        process = QProcess(self._window)
        process.setProgram(sys.executable)
        process.setArguments([str(plugin.script)])
        process.setWorkingDirectory(str(self.project.root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda plugin_id=plugin.id: self._read_tool_output(plugin_id)
        )
        process.finished.connect(
            lambda exit_code, exit_status, plugin_id=plugin.id: (
                self._tool_finished(plugin_id, exit_code, exit_status)
            )
        )
        process.errorOccurred.connect(
            lambda error, title=plugin.title: self._log(
                f"[tool:error] {title}: process error {int(error)}"
            )
        )
        self._tool_processes[plugin.id] = process
        process.start()
        if not process.waitForStarted(3000):
            self._tool_processes.pop(plugin.id, None)
            self._show_error("Tool failed", ValueError(process.errorString()))
            return
        self._log(f"[tool] started {plugin.title} (PID {process.processId()})")

    def _read_tool_output(self, plugin_id: str) -> None:
        process = self._tool_processes.get(plugin_id)
        if process is None:
            return
        data = bytes(process.readAllStandardOutput())
        output = data.decode("utf-8", errors="replace").rstrip()
        if output:
            self._log(output)

    def _tool_finished(self, plugin_id: str, exit_code: int, exit_status) -> None:
        del exit_status
        self._read_tool_output(plugin_id)
        plugin = self.plugin_registry.get(plugin_id)
        self._log(f"[tool] {plugin.title} exited with code {exit_code}")
        self._tool_processes.pop(plugin_id, None)

    def _resource_selected(self, record: AssetRecord) -> None:
        if self.document_manager.active is not None:
            self.session.editor_state.selection.resource_uri = record.resource_value
        self.statusBar().showMessage(record.resource_value, 3000)

    def _resource_activated(self, record: AssetRecord) -> None:
        selected = self.session.node(self._selected_id)
        if record.kind == "pattern":
            self._open_pattern_preview(record.resource_value)
            return
        if record.kind == "scene":
            self._open_document(record.resource_value)
            return
        if record.kind in {"image", "sprite"}:
            if not isinstance(self.session.document, SceneDocument):
                self.statusBar().showMessage(
                    "Open a Scene document before adding image resources", 3000
                )
                return
            if selected is not None and selected.type == "Sprite":
                self.set_node_property(
                    selected.id,
                    "texture",
                    record.resource_value,
                )
            else:
                self._add_sprite_resource(
                    record.resource_value,
                    record.name,
                )
            return
        if record.kind == "script":
            if selected is not None and selected.type == "SpellCard":
                self.set_node_property(
                    selected.id,
                    "script",
                    record.resource_value,
                )
            else:
                self._log(
                    "[assets] Select a SpellCard before assigning a script."
                )
            return
        if record.kind == "json":
            if record.path.name == "bullet_aliases.json":
                self.open_plugin("bullet_aliases")
            elif record.project_path.startswith("assets/images/"):
                self.open_plugin("texture_editor")

    def _resource_dropped(self, payload: dict, x: float, y: float) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        kind = str(payload.get("kind", ""))
        value = str(payload.get("resource_value", "")).strip()
        name = str(payload.get("name", "Sprite")).strip() or "Sprite"
        if not value:
            return
        if kind in {"image", "sprite"}:
            self._add_sprite_resource(value, name, x=x, y=y)
            return
        if kind == "script":
            selected = self.session.node(self._selected_id)
            if selected is not None and selected.type == "SpellCard":
                self.set_node_property(selected.id, "script", value)
            else:
                self._log(
                    "[assets] Drop scripts while a SpellCard is selected."
                )
            return
        if kind == "pattern":
            selected = self.session.node(self._selected_id)
            if selected is not None and selected.type == "PatternInstance":
                invalidation = self.editor_coordinator.dispatch(
                    SetNodePropertyIntent(
                        self.session.document.id,
                        selected.id,
                        "pattern",
                        value,
                    )
                )
                self.apply_invalidation(self.session.document.id, invalidation)
            self._open_pattern_preview(value)
            return

    def _add_sprite_resource(
        self,
        resource_value: str,
        name: str,
        *,
        x: float | None = None,
        y: float | None = None,
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        parent = self.session.node(self._selected_id) or self.session.document.root
        properties: dict[str, object] = {"texture": resource_value}
        if x is not None:
            properties["x"] = float(x)
        if y is not None:
            properties["y"] = float(y)
        invalidation = self.editor_coordinator.dispatch(
            AddSceneNodeIntent(
                self.session.document.id,
                parent.id,
                "Sprite",
                Path(name).stem or "Sprite",
                properties,
            )
        )
        self.apply_invalidation(self.session.document.id, invalidation)

    def _log_scene_diagnostics(self, error: SceneSpellCompileError) -> None:
        for diagnostic in error.diagnostics:
            href = (
                f"pystg-node:{diagnostic.resource_id}:{diagnostic.node_id}"
            )
            path = diagnostic.path
            if diagnostic.referenced_path:
                path += f" → {diagnostic.referenced_path}"
            self.output.append(
                f'<a href="{html.escape(href)}">'
                f'{html.escape(diagnostic.code)}: {html.escape(path)}</a> '
                f'{html.escape(diagnostic.message)}'
            )

    def _diagnostic_link_clicked(self, url: QUrl) -> None:
        value = url.toString()
        if not value.startswith("pystg-node:"):
            return
        parts = value.split(":", 2)
        if len(parts) != 3:
            return
        document_id, node_id = parts[1], parts[2]
        session = next(
            (
                item
                for item in self.document_manager
                if item.document.id == document_id
            ),
            None,
        )
        if session is None or not isinstance(session.document, SceneDocument):
            return
        invalidation = self.document_controller.activate(document_id)
        widget = self._document_widgets.get(document_id)
        if widget is not None:
            self.central_tabs.setCurrentWidget(widget)
        self.apply_invalidation(document_id, invalidation)
        selection = self.editor_coordinator.dispatch(
            SelectNodeIntent(document_id, node_id)
        )
        self.apply_invalidation(document_id, selection)

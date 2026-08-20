"""Preview slots: launching, transport, live properties and runtime feedback."""

from __future__ import annotations

import sys
from src.qt_compat.QtCore import QProcess
from src.pattern import PatternDocument
from .document import SceneDocument
from .runtime_preview import RuntimePreviewHost
from .document_manager import ManagedDocument
from .scene_compile import SceneSpellCompileError, compile_simple_spell
from .i18n import LANGUAGE_ENGLISH, translate_widget_tree
from .main_window_support import _scene_has_stage_content, build_preview_command
from .scene_view import SceneViewport
from .state import RuntimeOverlayState
from .shell import WindowService


class PreviewService(WindowService):
    """Preview slots: launching, transport, live properties and runtime feedback.

    These slots stay bound to the window instance instead of moving into a
    controller object: every attribute they touch is owned by
    ``EditorMainWindow``, and the editor tests plus the three native gates drive
    these methods by name.  Mix in before the Qt base class, the same way
    ``SpaceTapSearchMixin`` is used by ``SceneViewport``.
    """

    def _connect_pattern_preview(self) -> None:
        client = self._pattern_preview_client
        client.eventReceived.connect(self._handle_pattern_preview_event)
        client.protocolError.connect(self._handle_pattern_preview_issue)
        client.processLog.connect(
            lambda text: self._log(f"[pattern-preview:stderr] {text}")
        )
        client.runningChanged.connect(self.preview_panel.set_running)
        client.runningChanged.connect(self._preview_running_changed)

    def _ensure_runtime_preview_host(self) -> RuntimePreviewHost:
        host = self._runtime_preview_host
        if host is not None:
            return host
        host = RuntimePreviewHost()
        host.set_language_manager(self.language_manager)
        host.setProperty("runtimePreview", True)
        self._runtime_preview_host = host
        index = self.central_tabs.addTab(
            host,
            self.language_manager.translate("Runtime Preview"),
        )
        if self.language == LANGUAGE_ENGLISH:
            # The English source is captured by the normal tree pass.  Keeping
            # this explicit also covers a host created after a language toggle.
            self.central_tabs.setTabText(index, "Runtime Preview")
        translate_widget_tree(self, self.language_manager)
        return host

    def _show_runtime_preview_host(self, *, select: bool = False) -> None:
        """Show the formal renderer inside the Qt workbench when possible."""

        host = self._ensure_runtime_preview_host()
        host.attach_process(self._pattern_preview_client)
        if select:
            self.central_tabs.setCurrentWidget(host)

    def _preview_running_changed(self, running: bool) -> None:
        if running:
            return
        if self._runtime_preview_host is not None:
            self._runtime_preview_host.detach()
        self._preview_loaded_resource_id = None
        self._preview_mode = "unloaded"
        self._preview_state = "stopped"
        self._clear_stage_runtime_feedback()
        self._active_stage_session = None

    def _clear_stage_runtime_feedback(self) -> None:
        self._runtime_overlay = None
        self.timeline.set_active_clips(())
        self.timeline.set_reactive_overlay({})
        self.state_graph.set_active_state_path(())
        if hasattr(self, "variables"):
            self.variables.set_runtime_overlay({})
        active = self.document_manager.active
        if active is not None and isinstance(active.document, SceneDocument):
            self.timeline.set_playhead(
                active.editor_state.timeline.playhead_frame,
                emit=False,
            )
        for widget in self._document_widgets.values():
            if isinstance(widget, SceneViewport):
                widget.clear_runtime_state()

    def _open_pattern_preview(self, resource_value: str) -> None:
        session = self._open_document(resource_value)
        if session is None:
            return
        if not isinstance(session.document, PatternDocument):
            self._show_error(
                "Pattern preview unavailable",
                ValueError("Selected resource is not a PatternDocument"),
            )
            return
        self._active_pattern_session = session
        self._active_pattern_document = session.document
        self._active_pattern_resource = session.resource_uri or ""
        self._active_stage_session = None
        self._preview_loaded_resource_id = None
        self._preview_mode = "pattern"
        self.preview_panel.set_resource(self._active_pattern_resource)
        self.bottom_tabs.setCurrentWidget(self.preview_panel)
        self._launch_active_pattern_preview()

    def _launch_active_preview(self) -> None:
        session = self.document_manager.active
        if (
            session is not None
            and isinstance(session.document, SceneDocument)
            and _scene_has_stage_content(session.document)
        ):
            self._launch_active_stage_preview(session)
            return
        self._launch_active_pattern_preview()

    def _launch_active_stage_preview(self, session: ManagedDocument) -> None:
        if (
            not isinstance(session.document, SceneDocument)
            or not _scene_has_stage_content(session.document)
        ):
            self.preview_panel.handle_issue(
                {
                    "code": "no_stage_timeline",
                    "message": "Add at least one Timeline track before launching Stage preview",
                }
            )
            return
        if not self._pattern_preview_client.start():
            return
        self._show_runtime_preview_host(select=True)
        if self._active_stage_session is not session:
            self._clear_stage_runtime_feedback()
        self._active_stage_session = session
        self._preview_loaded_resource_id = None
        self._preview_mode = "stage"
        self.preview_panel.set_resource(
            session.resource_uri or f"unsaved://{session.document.id}"
        )
        self.preview_panel.set_mode("stage")
        self.bottom_tabs.setCurrentWidget(self.preview_panel)
        self._pattern_preview_client.send_command(
            "load",
            {"document": session.document.to_dict()},
        )
        self._pattern_preview_client.send_command("play")
        self._log(
            f"[stage-preview] opening {session.resource_uri or session.document.name}"
        )

    def _launch_active_pattern_preview(self) -> None:
        if self._active_pattern_document is None:
            self.preview_panel.handle_issue(
                {"code": "no_pattern", "message": "Select a Pattern resource first"}
            )
            return
        if not self._pattern_preview_client.start():
            return
        # Keep the Pattern workspace visible while the formal renderer runs in
        # its dedicated Runtime Preview tab.  The Stage flow selects that tab
        # because its timeline is authored in the scene workspace.
        self._show_runtime_preview_host()
        self._clear_stage_runtime_feedback()
        self._active_stage_session = None
        self._preview_loaded_resource_id = None
        self._preview_mode = "pattern"
        self._pattern_preview_client.send_command(
            "load",
            {"document": self._active_pattern_document.to_dict()},
        )
        self._pattern_preview_client.send_command("play")
        self.preview_panel.set_mode("pattern")
        label = self._active_pattern_resource or self._active_pattern_document.name
        self._log(f"[pattern-preview] opening {label}")

    def _send_pattern_preview_command(self, command: str, payload: dict) -> None:
        if command in {"reset", "stop"}:
            self._clear_stage_runtime_feedback()
        active_document = (
            self.document_manager.active.document
            if self.document_manager.active is not None
            else None
        )
        if command == "set-seed" and isinstance(active_document, PatternDocument):
            self._pattern_property_requested("seed", payload.get("seed"))
            return
        if command == "set-property" and isinstance(active_document, PatternDocument):
            self._pattern_property_requested(payload.get("path"), payload.get("value"))
            return
        if not self._pattern_preview_client.is_running:
            self._launch_active_preview()
        if not self._pattern_preview_client.is_running:
            return
        try:
            self._pattern_preview_client.send_command(command, payload)
        except RuntimeError as exc:
            self._handle_pattern_preview_issue(
                {"code": "command_failed", "message": str(exc)}
            )

    def _sync_active_pattern_preview(self) -> None:
        session = self.document_manager.active
        if (
            session is None
            or not isinstance(session.document, PatternDocument)
            or not self._pattern_preview_client.is_running
        ):
            return
        self._active_pattern_session = session
        self._active_pattern_document = session.document
        self._active_pattern_resource = session.resource_uri or ""
        self._pattern_preview_client.send_command(
            "load", {"document": session.document.to_dict()}
        )

    def _sync_active_stage_preview(self) -> None:
        session = self.document_manager.active
        if (
            session is None
            or not isinstance(session.document, SceneDocument)
            or not _scene_has_stage_content(session.document)
            or not self._pattern_preview_client.is_running
            or self._active_stage_session is not session
            or self._preview_mode != "stage"
            or self._preview_loaded_resource_id != session.document.id
        ):
            return
        frame = int(self.timeline.playhead_frame)
        was_playing = self._preview_state == "playing"
        self._pattern_preview_client.send_command(
            "load", {"document": session.document.to_dict()}
        )
        self._pattern_preview_client.send_command("seek", {"frame": frame})
        if was_playing:
            self._pattern_preview_client.send_command("play")

    def _handle_pattern_preview_event(self, message: dict) -> None:
        self.preview_panel.handle_event(message)
        request_id = message.get("request_id")
        payload = message.get("payload") or {}
        if message.get("event") == "response" and request_id in self._preview_pending_properties:
            self._preview_pending_properties.pop(request_id)
        event = message.get("event")
        if event in {"status", "statistics"}:
            self._preview_state = str(payload.get("state") or self._preview_state)
            self._preview_mode = str(payload.get("mode") or self._preview_mode)
            resource_id = payload.get("resource_id")
            if resource_id:
                self._preview_loaded_resource_id = str(resource_id)
            self._sync_stage_runtime_feedback(payload)
        if event == "program_loaded":
            mode = str(payload.get("mode") or "pattern")
            self._preview_mode = mode
            self._preview_loaded_resource_id = str(payload.get("resource_id") or "") or None
            self._log(
                f"[{mode}-preview] loaded {payload.get('name')} "
                f"({str(payload.get('content_hash') or '')[:12]})"
            )
            self._clear_graph_diagnostics()
        elif event in {"compile_error", "runtime_error", "protocol_error"}:
            self._clear_stage_runtime_feedback()
            self._log(f"[pattern-preview:{event}] {payload}")
            if event == "compile_error":
                self._apply_graph_diagnostics(payload.get("diagnostics"))

    def _sync_stage_runtime_feedback(self, payload: dict) -> None:
        # Runtime feedback belongs to the scene that launched the preview, not
        # whichever document happens to be active while the preview is still
        # running.  This matters when the user switches tabs mid-playback: the
        # owner scene must keep receiving the authoritative pose/playhead so it
        # is correct as soon as the user returns to it.
        session = self._active_stage_session
        if (
            session is None
            or not isinstance(session.document, SceneDocument)
            or self._preview_mode != "stage"
            or self._preview_loaded_resource_id != session.document.id
        ):
            return
        widget = self._document_widgets.get(session.document.id)
        state = str(payload.get("state") or self._preview_state)
        node_state = payload.get("node_state")
        if state in {"stopped", "unloaded", "error"}:
            self._clear_stage_runtime_feedback()
            return
        frame = payload.get("frame")
        if not isinstance(frame, int) or isinstance(frame, bool) or frame < 0:
            return
        overlay = RuntimeOverlayState.from_payload(session.document.id, payload)
        self._runtime_overlay = overlay
        if self.document_manager.active is session:
            self.timeline.set_playhead(overlay.frame, emit=False)
            self.timeline.set_active_clips(overlay.active_clip_ids)
            self.timeline.set_reactive_overlay(overlay.mutable_reactive_overlay())
            self.state_graph.set_active_state_path(overlay.state_path)
            if hasattr(self, "variables"):
                self.variables.set_runtime_overlay(
                    overlay.mutable_variable_snapshot()
                )
        if isinstance(widget, SceneViewport):
            if state in {"playing", "paused"} and isinstance(node_state, dict):
                widget.set_runtime_state(node_state)

    def _handle_pattern_preview_issue(self, issue: dict) -> None:
        self.preview_panel.handle_issue(issue)
        self._log(
            f"[pattern-preview:error] {issue.get('code')}: {issue.get('message')}"
        )

    def run_preview(self) -> None:
        if isinstance(self.session.document, PatternDocument):
            self._active_pattern_session = self.session
            self._active_pattern_document = self.session.document
            self._active_pattern_resource = self.session.resource_uri or ""
            self._launch_active_pattern_preview()
            return
        if (
            isinstance(self.session.document, SceneDocument)
            and _scene_has_stage_content(self.session.document)
        ):
            self._launch_active_stage_preview(self.session)
            return
        node = self.session.node(self._selected_id)
        if node is not None and node.type == "PatternInstance":
            resource = str(node.properties.get("pattern") or "").strip()
            if resource:
                self._open_pattern_preview(resource)
                return
        if node is not None and node.type == "Spell":
            try:
                preview = compile_simple_spell(
                    self.project,
                    self.session.document,
                    node.id,
                )
            except SceneSpellCompileError as exc:
                self._log_scene_diagnostics(exc)
                self._show_error("No-code Spell preview unavailable", exc)
                return
            self._active_pattern_session = None
            self._active_pattern_document = preview.document
            self._active_pattern_resource = preview.pattern_resource
            self.preview_panel.set_resource(preview.pattern_resource)
            self.bottom_tabs.setCurrentWidget(self.preview_panel)
            self._launch_active_pattern_preview()
            self._log(
                f"[scene-preview] Spell {node.name} compiled through PatternInstance "
                f"{preview.pattern_instance_id}"
            )
            return
        if self._preview_process is not None and self._preview_process.state() != QProcess.NotRunning:
            self.statusBar().showMessage(
                self.language_manager.translate("Preview is already running"),
                3000,
            )
            return

        try:
            arguments, label = build_preview_command(
                self.project,
                self.session.document,
                node,
            )
        except (OSError, ValueError) as exc:
            self._show_error("Preview unavailable", exc)
            return

        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments(arguments)
        process.setWorkingDirectory(str(self.project.root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_preview_output)
        process.finished.connect(self._preview_finished)
        process.errorOccurred.connect(
            lambda error: self._log(f"[preview:error] process error {int(error)}")
        )
        self._preview_process = process
        process.start()
        if not process.waitForStarted(3000):
            self._show_error("Preview failed", ValueError(process.errorString()))
            self._preview_process = None
            return
        self._log(f"[preview] started {label} (PID {process.processId()})")
        self.statusBar().showMessage(f"Started {label}", 3000)

    def _read_preview_output(self) -> None:
        if self._preview_process is None:
            return
        data = bytes(self._preview_process.readAllStandardOutput())
        text = data.decode("utf-8", errors="replace").rstrip()
        if text:
            self._log(text)

    def _preview_finished(self, exit_code: int, exit_status) -> None:
        self._read_preview_output()
        self._log(f"[preview] exited with code {exit_code}")
        self.statusBar().showMessage(f"Preview exited ({exit_code})", 3000)

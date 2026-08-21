"""One owner for every editor preview subprocess (EDITOR_ARCHITECTURE ER4).

:class:`PreviewSession` unifies the two ways the editor previews authored
content and guarantees only one of them runs at a time:

``formal_authoring``
    The canonical path.  Pattern/Stage documents are streamed to
    :class:`~src.editor.preview_process.PatternPreviewProcess`, which drives the
    real runtime behind the NDJSON preview protocol and reports feedback back to
    the owning authoring document.

``legacy_game_run``
    A raw ``main.py``/spell smoke run launched as a plain child process for a
    visual sanity check.  Its output is surfaced verbatim and is *never* dressed
    up as a formal protocol result.

Starting either mode stops the other first, and :meth:`stop`/:meth:`close` tear
down whatever processes exist, so a reset, crash, or window close always leaves
no orphaned preview and no overlay attributed to the wrong document.

The raw ``QProcess`` for the legacy run is constructed *here* on purpose: the
window must not own it (see the boundary test
``test_editor_main_window_does_not_own_raw_preview_qprocess``).  External
editing-tool processes stay outside this session -- they are not previews.
"""

from __future__ import annotations

from typing import Any

from src.qt_compat.QtCore import QObject, QProcess, pyqtSignal

from src.core.project_context import ProjectContext

from ..preview_process import PatternPreviewProcess


PREVIEW_MODE_UNLOADED = "unloaded"
PREVIEW_MODE_FORMAL = "formal_authoring"
PREVIEW_MODE_LEGACY = "legacy_game_run"

# Cap the merged stdout retained/forwarded from a legacy game run so a chatty
# process cannot grow the editor log without bound.  The formal NDJSON transport
# enforces its own per-line and stderr caps inside PatternPreviewProcess.
MAX_LEGACY_OUTPUT_BYTES = 64 * 1024


def _qt_enum_value(value: Any) -> int:
    """Return an int for both PyQt integer enums and PySide ``Enum`` values."""

    return int(getattr(value, "value", value))


class PreviewStartError(RuntimeError):
    """Raised when a legacy game-run preview process fails to start."""


class PreviewSession(QObject):
    """Owns the editor's preview subprocesses and enforces one active preview."""

    # Merged stdout text from a legacy game run (already decoded and capped).
    legacyOutput = pyqtSignal(str)
    # Exit code, emitted once when a legacy game run finishes.
    legacyFinished = pyqtSignal(int)
    # Transport mode changed: one of the PREVIEW_MODE_* constants.
    modeChanged = pyqtSignal(str)

    def __init__(
        self, project: ProjectContext, *, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.project = project
        # The formal client is created eagerly and kept swappable so tests can
        # inject a fake without the window (or this session) losing ownership.
        self._formal_client: Any = PatternPreviewProcess(project, parent=self)
        self._legacy_process: QProcess | None = None
        self._mode = PREVIEW_MODE_UNLOADED
        # Identity of the authoring document the *active* preview belongs to, so
        # runtime feedback is never attributed to whichever document happens to
        # be focused while a preview is still running.
        self._active_document_id: str | None = None
        self._active_resource_id: str | None = None
        self._legacy_output_forwarded = 0
        self._legacy_output_truncated = False

    # -- formal client access (single source of truth, swappable) --------
    @property
    def formal_client(self) -> Any:
        return self._formal_client

    @formal_client.setter
    def formal_client(self, client: Any) -> None:
        self._formal_client = client

    # -- state introspection ---------------------------------------------
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def active_document_id(self) -> str | None:
        return self._active_document_id

    @property
    def active_resource_id(self) -> str | None:
        return self._active_resource_id

    @property
    def is_formal_running(self) -> bool:
        client = self._formal_client
        return bool(client is not None and getattr(client, "is_running", False))

    @property
    def is_legacy_running(self) -> bool:
        process = self._legacy_process
        return process is not None and process.state() != QProcess.NotRunning

    @property
    def is_active(self) -> bool:
        return self.is_formal_running or self.is_legacy_running

    # -- formal_authoring -------------------------------------------------
    def start_formal(
        self,
        *,
        document_id: str | None = None,
        resource_id: str | None = None,
    ) -> bool:
        """Start (or reuse) the formal NDJSON worker, stopping any legacy run.

        Returns whatever the formal client's ``start()`` returns so callers keep
        their existing ``if not ...: return`` guard.  On success the active
        document identity is recorded for feedback routing.
        """

        self._stop_legacy()
        client = self._formal_client
        if client is None:
            return False
        started = bool(client.start())
        if started:
            self._active_document_id = document_id
            self._active_resource_id = resource_id
            self._set_mode(PREVIEW_MODE_FORMAL)
        return started

    # -- legacy_game_run --------------------------------------------------
    def start_legacy(
        self,
        program: str,
        arguments: list[str],
        *,
        started_timeout_ms: int = 3000,
    ) -> QProcess:
        """Launch the raw game-run preview, stopping the formal worker first.

        The session *owns* the returned process; callers may read it (e.g. for a
        PID) but must never store it on the window.  Raises
        :class:`PreviewStartError` if the process fails to start.
        """

        self._stop_formal()
        self._stop_legacy()
        self._legacy_output_forwarded = 0
        self._legacy_output_truncated = False
        process = QProcess(self)
        process.setProgram(program)
        process.setArguments(list(arguments))
        process.setWorkingDirectory(str(self.project.root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_legacy_output)
        process.finished.connect(self._legacy_finished)
        process.errorOccurred.connect(self._legacy_error)
        self._legacy_process = process
        # A legacy game run is deliberately *not* a formal result: it owns no
        # document identity and cannot be mistaken for the protocol path.
        self._active_document_id = None
        self._active_resource_id = None
        self._set_mode(PREVIEW_MODE_LEGACY)
        process.start()
        if not process.waitForStarted(started_timeout_ms):
            message = process.errorString()
            self._legacy_process = None
            self._set_mode(PREVIEW_MODE_UNLOADED)
            raise PreviewStartError(message)
        return process

    # -- teardown ---------------------------------------------------------
    def stop(self) -> None:
        """Stop whichever preview is active (both, defensively)."""

        self._stop_legacy()
        self._stop_formal()
        self._active_document_id = None
        self._active_resource_id = None
        self._set_mode(PREVIEW_MODE_UNLOADED)

    def close(self) -> None:
        """Terminate every preview subprocess for good (window close)."""

        self._stop_legacy()
        client = self._formal_client
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        self._active_document_id = None
        self._active_resource_id = None
        self._set_mode(PREVIEW_MODE_UNLOADED)

    # -- internals --------------------------------------------------------
    def _set_mode(self, mode: str) -> None:
        if mode != self._mode:
            self._mode = mode
            self.modeChanged.emit(mode)

    def _stop_formal(self) -> None:
        client = self._formal_client
        if client is None:
            return
        if getattr(client, "is_running", False):
            stop = getattr(client, "stop", None)
            if callable(stop):
                stop()

    def _stop_legacy(self, timeout_ms: int = 1500) -> None:
        process = self._legacy_process
        if process is None:
            return
        if process.state() != QProcess.NotRunning:
            self._read_legacy_output()
            process.terminate()
            if not process.waitForFinished(timeout_ms):
                process.kill()
                process.waitForFinished(500)
        self._legacy_process = None

    def _read_legacy_output(self) -> None:
        process = self._legacy_process
        if process is None:
            return
        raw = bytes(process.readAllStandardOutput())
        allowance = max(0, MAX_LEGACY_OUTPUT_BYTES - self._legacy_output_forwarded)
        forwarded = raw[:allowance]
        self._legacy_output_forwarded += len(forwarded)
        text = forwarded.decode("utf-8", errors="replace").rstrip()
        if text:
            self.legacyOutput.emit(text)
        if len(raw) > allowance and not self._legacy_output_truncated:
            self._legacy_output_truncated = True
            self.legacyOutput.emit(
                f"[preview output truncated after {MAX_LEGACY_OUTPUT_BYTES} bytes]"
            )

    def _legacy_finished(self, exit_code: int, exit_status: Any) -> None:
        self._read_legacy_output()
        self._legacy_process = None
        if self._mode == PREVIEW_MODE_LEGACY:
            self._set_mode(PREVIEW_MODE_UNLOADED)
        self.legacyFinished.emit(int(exit_code))

    def _legacy_error(self, error: Any) -> None:
        self.legacyOutput.emit(
            f"[preview:error] process error {_qt_enum_value(error)}"
        )

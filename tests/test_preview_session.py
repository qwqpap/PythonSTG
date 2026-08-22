"""ER4: the editor's single PreviewSession owns every preview subprocess.

These tests pin the session contract independently of the Qt window:

* only one preview is active at a time (formal <-> legacy are mutually
  exclusive, each stops the other);
* a legacy game run is never labelled as a formal result (it carries no
  authoring-document identity), so feedback cannot be routed to the wrong
  document;
* stop / close / natural exit always tear the processes down;
* legacy stdout is surfaced (capped) and the exit code is reported, never
  swallowed.

The formal NDJSON transport itself is exercised by ``test_preview_process.py``
and ``test_preview_protocol.py``; here it is represented by a lightweight fake
so the mutual-exclusion and identity logic can be tested without launching the
real runtime.
"""

from __future__ import annotations

import sys
import time

import pytest

from src.qt_compat.QtCore import QObject, QProcess, pyqtSignal
from src.qt_compat.QtWidgets import QApplication

from src.core.project_context import ProjectContext
from src.editor.preview_process import PatternPreviewProcess
from src.editor.preview import (
    MAX_LEGACY_OUTPUT_BYTES,
    PREVIEW_MODE_FORMAL,
    PREVIEW_MODE_LEGACY,
    PREVIEW_MODE_UNLOADED,
    PreviewSession,
    PreviewStartError,
)


# A child process that blocks until it is terminated -- stands in for the game
# window during mutual-exclusion tests.  It is always killed by the session.
_BLOCK = ["-c", "import sys; sys.stdin.read()"]


class FakeFormalClient(QObject):
    """Stand-in for PatternPreviewProcess with just the surface the session uses."""

    runningChanged = pyqtSignal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.running = False
        self.started = 0
        self.stopped = 0
        self.closed = 0

    @property
    def is_running(self) -> bool:
        return self.running

    def start(self) -> bool:
        self.running = True
        self.started += 1
        self.runningChanged.emit(True)
        return True

    def stop(self, timeout_ms: int = 1500) -> None:
        self.running = False
        self.stopped += 1
        self.runningChanged.emit(False)

    def close(self) -> None:
        self.running = False
        self.closed += 1
        self.runningChanged.emit(False)

    def finish_naturally(self) -> None:
        """Model the formal worker exiting without an explicit session stop."""

        self.running = False
        self.runningChanged.emit(False)


def _pump_until(predicate, timeout_ms: int = 5000) -> bool:
    app = QApplication.instance()
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if app is not None:
            app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    if app is not None:
        app.processEvents()
    return predicate()


def test_default_session_is_unloaded_and_owns_a_real_formal_client(qapp_session, tmp_path):
    del qapp_session
    session = PreviewSession(ProjectContext(tmp_path))
    assert session.mode == PREVIEW_MODE_UNLOADED
    assert not session.is_active
    assert session.active_document_id is None
    # The canonical Pattern/Stage path still goes through the NDJSON runtime.
    assert isinstance(session.formal_client, PatternPreviewProcess)


def test_formal_client_property_is_the_single_swappable_owner(qapp_session, tmp_path):
    del qapp_session
    session = PreviewSession(ProjectContext(tmp_path))
    fake = FakeFormalClient()
    session.formal_client = fake
    assert session.formal_client is fake


def test_start_formal_records_document_identity(qapp_session, tmp_path):
    del qapp_session
    session = PreviewSession(ProjectContext(tmp_path))
    session.formal_client = FakeFormalClient()

    assert session.start_formal(document_id="doc-1", resource_id="res://a")
    assert session.mode == PREVIEW_MODE_FORMAL
    assert session.is_formal_running
    assert session.active_document_id == "doc-1"
    assert session.active_resource_id == "res://a"


def test_starting_legacy_stops_formal_and_is_not_a_formal_result(qapp_session, tmp_path):
    del qapp_session
    session = PreviewSession(ProjectContext(tmp_path))
    fake = FakeFormalClient()
    session.formal_client = fake
    session.start_formal(document_id="doc-1", resource_id="res://a")

    process = session.start_legacy(sys.executable, _BLOCK)
    try:
        assert fake.stopped == 1
        assert not session.is_formal_running
        assert session.is_legacy_running
        assert session.mode == PREVIEW_MODE_LEGACY
        # A legacy game run carries no authoring identity, so runtime feedback
        # can never be attributed to a document by mistake.
        assert session.active_document_id is None
        assert session.active_resource_id is None
    finally:
        session.close()
    assert not session.is_legacy_running
    assert process.state() == QProcess.NotRunning
    assert fake.closed == 1
    assert session.mode == PREVIEW_MODE_UNLOADED


def test_starting_formal_stops_a_running_legacy(qapp_session, tmp_path):
    del qapp_session
    session = PreviewSession(ProjectContext(tmp_path))
    fake = FakeFormalClient()
    session.formal_client = fake

    process = session.start_legacy(sys.executable, _BLOCK)
    assert session.is_legacy_running
    assert session.mode == PREVIEW_MODE_LEGACY

    assert session.start_formal(document_id="doc-2")
    assert process.state() == QProcess.NotRunning
    assert not session.is_legacy_running
    assert session.is_formal_running
    assert session.mode == PREVIEW_MODE_FORMAL
    assert fake.started == 1
    session.close()


def test_stop_tears_down_formal_and_clears_identity(qapp_session, tmp_path):
    del qapp_session
    session = PreviewSession(ProjectContext(tmp_path))
    fake = FakeFormalClient()
    session.formal_client = fake
    session.start_formal(document_id="doc-3", resource_id="res://x")

    session.stop()
    assert fake.stopped == 1
    assert session.mode == PREVIEW_MODE_UNLOADED
    assert session.active_document_id is None
    assert session.active_resource_id is None
    assert not session.is_active


def test_formal_natural_exit_clears_mode_and_document_identity(
    qapp_session, tmp_path
):
    """A child exit must transition the owning session, not only the Qt panel."""

    session = PreviewSession(ProjectContext(tmp_path))
    fake = FakeFormalClient()
    session.formal_client = fake
    assert session.start_formal(document_id="doc-exited", resource_id="res://exited")

    fake.finish_naturally()
    qapp_session.processEvents()

    assert session.mode == PREVIEW_MODE_UNLOADED
    assert session.active_document_id is None
    assert session.active_resource_id is None
    assert not session.is_active


def test_legacy_run_streams_output_and_reports_clean_exit(qapp_session, tmp_path):
    del qapp_session
    session = PreviewSession(ProjectContext(tmp_path))
    outputs: list[str] = []
    codes: list[int] = []
    session.legacyOutput.connect(outputs.append)
    session.legacyFinished.connect(codes.append)

    process = session.start_legacy(sys.executable, ["-c", "print('hello-preview')"])
    assert session.mode == PREVIEW_MODE_LEGACY
    process.waitForFinished(5000)
    assert _pump_until(lambda: bool(codes))

    assert codes == [0]
    assert any("hello-preview" in text for text in outputs)
    # A finished run is not a formal result and leaves nothing active.
    assert session.mode == PREVIEW_MODE_UNLOADED
    assert not session.is_legacy_running
    session.close()


def test_legacy_nonzero_exit_is_surfaced_not_swallowed(qapp_session, tmp_path):
    del qapp_session
    session = PreviewSession(ProjectContext(tmp_path))
    codes: list[int] = []
    session.legacyFinished.connect(codes.append)

    process = session.start_legacy(sys.executable, ["-c", "import sys; sys.exit(3)"])
    process.waitForFinished(5000)
    assert _pump_until(lambda: bool(codes))

    assert codes == [3]
    assert session.mode == PREVIEW_MODE_UNLOADED
    session.close()


def test_legacy_start_failure_raises_and_resets_state(qapp_session, tmp_path):
    del qapp_session
    session = PreviewSession(ProjectContext(tmp_path))
    with pytest.raises(PreviewStartError):
        session.start_legacy(
            "pystg-nonexistent-preview-binary",
            ["--nope"],
            started_timeout_ms=1500,
        )
    assert session.mode == PREVIEW_MODE_UNLOADED
    assert not session.is_legacy_running


def test_legacy_output_is_capped(qapp_session, tmp_path):
    del qapp_session
    session = PreviewSession(ProjectContext(tmp_path))
    outputs: list[str] = []
    codes: list[int] = []
    session.legacyOutput.connect(outputs.append)
    session.legacyFinished.connect(codes.append)

    # Emit well beyond the cap; the session must stop forwarding and say so once.
    payload = MAX_LEGACY_OUTPUT_BYTES * 2
    process = session.start_legacy(
        sys.executable,
        ["-c", f"sys=__import__('sys'); sys.stdout.write('x' * {payload})"],
    )
    process.waitForFinished(5000)
    assert _pump_until(lambda: bool(codes))

    forwarded = sum(len(text) for text in outputs if not text.startswith("[preview output truncated"))
    assert forwarded <= MAX_LEGACY_OUTPUT_BYTES
    assert any(text.startswith("[preview output truncated") for text in outputs)
    session.close()

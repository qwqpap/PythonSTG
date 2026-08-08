"""Qt-side lifecycle and NDJSON client for the external formal preview."""

from __future__ import annotations

import json
import sys
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Callable

from src.qt_compat.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal
from src.qt_compat.QtWidgets import QApplication

from src.core.project_context import ProjectContext
from src.preview import PREVIEW_PROTOCOL_VERSION, encode_message


class PatternPreviewProcess(QObject):
    MAX_STDOUT_LINE_BYTES = 64 * 1024
    MAX_STDERR_FORWARD_BYTES = 64 * 1024

    eventReceived = pyqtSignal(dict)
    protocolError = pyqtSignal(dict)
    processLog = pyqtSignal(str)
    runningChanged = pyqtSignal(bool)
    readyChanged = pyqtSignal(bool)

    def __init__(
        self,
        project: ProjectContext,
        *,
        script_path: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.script_path = (
            Path(script_path).resolve()
            if script_path is not None
            else (Path(__file__).resolve().parents[2] / "tools" / "preview_pattern.py")
        )
        self.process: QProcess | None = None
        self.ready = False
        self._stdout_buffer = bytearray()
        self._queued: list[bytes] = []
        self._events: deque[dict] = deque(maxlen=4096)
        self._stopping = False
        self._stderr_forwarded = 0
        self._stderr_truncated = False

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.NotRunning

    @property
    def events(self) -> tuple[dict, ...]:
        return tuple(self._events)

    def start(self, *, headless: bool = False, max_bullets: int = 50000) -> bool:
        if self.is_running:
            return True
        if not self.script_path.is_file():
            self._protocol_issue("missing_worker", f"preview worker not found: {self.script_path}")
            return False
        process = QProcess(self)
        process.setProgram(sys.executable)
        arguments = [
            str(self.script_path),
            "--project",
            str(self.project.root),
            "--max-bullets",
            str(max_bullets),
        ]
        if headless:
            arguments.append("--headless")
        process.setArguments(arguments)
        process.setWorkingDirectory(str(self.project.root))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUTF8", "1")
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._process_error)
        self.process = process
        self.ready = False
        self._stopping = False
        self._stdout_buffer.clear()
        self._queued.clear()
        self._stderr_forwarded = 0
        self._stderr_truncated = False
        process.start()
        if not process.waitForStarted(3000):
            self._protocol_issue("start_failed", process.errorString())
            self.process = None
            return False
        self.runningChanged.emit(True)
        self._write_request("hello", {}, request_id=f"hello-{uuid.uuid4()}")
        return True

    def _write_request(self, command: str, payload: dict, *, request_id: str) -> None:
        if not self.is_running:
            raise RuntimeError("preview process is not running")
        message = encode_message(
            {
                "protocol_version": PREVIEW_PROTOCOL_VERSION,
                "request_id": request_id,
                "command": command,
                "payload": payload,
            }
        )
        assert self.process is not None
        self.process.write(message)

    def send_command(self, command: str, payload: dict | None = None) -> str:
        if not self.is_running:
            raise RuntimeError("preview process is not running")
        request_id = str(uuid.uuid4())
        message = encode_message(
            {
                "protocol_version": PREVIEW_PROTOCOL_VERSION,
                "request_id": request_id,
                "command": command,
                "payload": dict(payload or {}),
            }
        )
        if not self.ready and command != "shutdown":
            self._queued.append(message)
        else:
            assert self.process is not None
            self.process.write(message)
        return request_id

    def send_raw(self, data: bytes) -> None:
        if not self.is_running:
            raise RuntimeError("preview process is not running")
        assert self.process is not None
        self.process.write(data)

    def _read_stdout(self) -> None:
        if self.process is None:
            return
        self._stdout_buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b"\n" in self._stdout_buffer:
            raw, _, remaining = self._stdout_buffer.partition(b"\n")
            self._stdout_buffer = bytearray(remaining)
            if not raw.strip():
                continue
            if len(raw) > self.MAX_STDOUT_LINE_BYTES:
                self._protocol_issue(
                    "worker_line_too_long",
                    f"worker output exceeded {self.MAX_STDOUT_LINE_BYTES} bytes",
                )
                continue
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._protocol_issue("malformed_worker_output", str(exc), raw=raw.decode("utf-8", errors="replace"))
                continue
            if not isinstance(message, dict):
                self._protocol_issue("invalid_worker_message", "worker message must be an object")
                continue
            if message.get("protocol_version") != PREVIEW_PROTOCOL_VERSION:
                self._protocol_issue("worker_version_mismatch", f"got {message.get('protocol_version')!r}")
                continue
            self._events.append(message)
            if message.get("event") == "hello":
                self.ready = True
                self.readyChanged.emit(True)
                assert self.process is not None
                for queued in self._queued:
                    self.process.write(queued)
                self._queued.clear()
            self.eventReceived.emit(message)
        if len(self._stdout_buffer) > self.MAX_STDOUT_LINE_BYTES:
            self._stdout_buffer.clear()
            self._protocol_issue(
                "worker_line_too_long",
                f"worker output exceeded {self.MAX_STDOUT_LINE_BYTES} bytes without a newline",
            )

    def _read_stderr(self) -> None:
        if self.process is None:
            return
        raw = bytes(self.process.readAllStandardError())
        allowance = max(0, self.MAX_STDERR_FORWARD_BYTES - self._stderr_forwarded)
        forwarded = raw[:allowance]
        self._stderr_forwarded += len(forwarded)
        text = forwarded.decode("utf-8", errors="replace").rstrip()
        if text:
            self.processLog.emit(text)
        if len(raw) > allowance and not self._stderr_truncated:
            self._stderr_truncated = True
            self.processLog.emit(
                f"[stderr truncated after {self.MAX_STDERR_FORWARD_BYTES} bytes]"
            )

    def _protocol_issue(self, code: str, message: str, **extra) -> None:
        payload = {"code": code, "message": message, **extra}
        self.protocolError.emit(payload)

    def _process_error(self, error) -> None:
        if self._stopping:
            return
        message = self.process.errorString() if self.process is not None else "process error"
        self._protocol_issue("process_error", message, qt_error=int(error))

    def _finished(self, exit_code: int, exit_status) -> None:
        self._read_stdout()
        self._read_stderr()
        normal = int(exit_status) == int(QProcess.NormalExit) and exit_code == 0
        if not normal and not self._stopping:
            self._protocol_issue(
                "process_crashed",
                f"preview exited with code {exit_code}",
                exit_code=exit_code,
                exit_status=int(exit_status),
            )
        self.ready = False
        self.readyChanged.emit(False)
        self.runningChanged.emit(False)

    def wait_for(self, predicate: Callable[[], bool], timeout_ms: int = 3000) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
            if predicate():
                return True
            if self.process is not None:
                self.process.waitForReadyRead(20)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        return predicate()

    def stop(self, timeout_ms: int = 1500) -> None:
        if self.process is None:
            return
        if self.process.state() == QProcess.NotRunning:
            self.ready = False
            return
        self._stopping = True
        try:
            self.send_command("shutdown")
            self.process.waitForBytesWritten(250)
            if not self.process.waitForFinished(timeout_ms):
                self.process.terminate()
                if not self.process.waitForFinished(500):
                    self.process.kill()
                    self.process.waitForFinished(500)
        finally:
            self.ready = False
            self._queued.clear()

    def close(self) -> None:
        self.stop()

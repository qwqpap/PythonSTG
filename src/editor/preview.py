"""Single real-game preview process owner and Windows native window host."""

from __future__ import annotations

import ctypes
import locale
import sys
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from src.compiler.package_builder import PackageBuilder, PreparedBuild
from src.compiler.practice import PRACTICE_STAGE_ID, practice_program
from src.core.preview_protocol import (
    MAX_PREVIEW_LINE_BYTES,
    PreviewProtocolError,
    control_message,
    decode_message,
    encode_message,
)
from src.qt_compat.QtCore import (
    QProcess,
    QProcessEnvironment,
    QTimer,
    QObject,
    Qt,
    Signal,
)
from src.qt_compat.QtWidgets import QLabel, QVBoxLayout, QWidget

from .session import EditorSession


_USER32 = None


def _user32():
    global _USER32
    if _USER32 is not None:
        return _USER32
    library = ctypes.WinDLL("user32", use_last_error=True)
    library.GetParent.argtypes = [wintypes.HWND]
    library.GetParent.restype = wintypes.HWND
    library.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    library.SetParent.restype = wintypes.HWND
    library.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    library.GetWindowThreadProcessId.restype = wintypes.DWORD
    library.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    library.GetWindowRect.restype = wintypes.BOOL
    get_long = getattr(library, "GetWindowLongPtrW", library.GetWindowLongW)
    get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    get_long.restype = ctypes.c_ssize_t
    set_long = getattr(library, "SetWindowLongPtrW", library.SetWindowLongW)
    set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_long.restype = ctypes.c_ssize_t
    _USER32 = library
    return library


@dataclass(frozen=True)
class PreviewTarget:
    kind: str
    unit_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"project", "stage", "wave", "enemy", "spell"}:
            raise ValueError(f"unsupported preview target: {self.kind}")
        if self.kind != "project" and not self.unit_id:
            raise ValueError(f"{self.kind} preview requires a unit id")


@dataclass(frozen=True)
class _LaunchSpec:
    entry_module: str
    stage_id: str | None
    run_id: str
    seed: int
    project_root: Path
    build_hash: str
    target: PreviewTarget


class PreviewHost(QWidget):
    """Re-parent only the GLFW window owned by the configured QProcess."""

    attached = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("game_preview_host")
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._process: QProcess | None = None
        self._hwnd: int | None = None
        self._original_parent = 0
        self._original_style = 0
        self._original_exstyle = 0
        self._original_rect = (0, 0, 0, 0)
        self.last_error = ""
        self._message = QLabel("点击“运行”启动真实游戏预览", self)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._message)
        self._poll = QTimer(self)
        self._poll.setInterval(50)
        self._poll.timeout.connect(self._try_attach)

    @property
    def is_attached(self) -> bool:
        return self._hwnd is not None

    @property
    def native_handle(self) -> int | None:
        return self._hwnd

    def attach_process(self, process: QProcess) -> None:
        self.detach()
        self._process = process
        if sys.platform != "win32":
            self._message.setText("真实游戏窗口正在外部运行；原生嵌入仅支持 Windows。")
            return
        self._message.setText("正在等待真实 GLFW / ModernGL 窗口…")
        self._message.show()
        self._poll.start()
        self._try_attach()

    def detach(self) -> None:
        self._poll.stop()
        hwnd = self._hwnd
        self._hwnd = None
        if hwnd is not None and sys.platform == "win32":
            user32 = _user32()
            if user32.IsWindow(hwnd):
                _set_window_long(hwnd, -16, self._original_style)
                _set_window_long(hwnd, -20, self._original_exstyle)
                user32.SetParent(hwnd, self._original_parent)
                left, top, right, bottom = self._original_rect
                user32.SetWindowPos(
                    hwnd,
                    0,
                    left,
                    top,
                    max(1, right - left),
                    max(1, bottom - top),
                    0x0020 | 0x0004,
                )
        self._process = None
        self._message.setText("预览已停止")
        self._message.show()
        self.attached.emit(False)

    def _try_attach(self) -> None:
        process = self._process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            self.detach()
            return
        pid = int(process.processId())
        if pid <= 0:
            return
        hwnd = _find_preview_window(pid)
        if hwnd is not None:
            try:
                if self._attach_hwnd(hwnd, pid):
                    self._poll.stop()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"

    def _attach_hwnd(self, hwnd: int, expected_pid: int) -> bool:
        user32 = _user32()
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if int(owner.value) != expected_pid:
            self.last_error = "native window PID changed before attachment"
            return False
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            self.last_error = "GetWindowRect failed"
            return False
        self._original_parent = int(user32.GetParent(hwnd) or 0)
        self._original_style = _get_window_long(hwnd, -16)
        self._original_exstyle = _get_window_long(hwnd, -20)
        self._original_rect = (rect.left, rect.top, rect.right, rect.bottom)

        ws_child = 0x40000000
        ws_popup = 0x80000000
        ws_caption = 0x00C00000
        ws_thickframe = 0x00040000
        style = (self._original_style | ws_child) & ~(
            ws_popup | ws_caption | ws_thickframe
        )
        parent_hwnd = int(self.winId())
        ctypes.set_last_error(0)
        previous_parent = int(user32.SetParent(hwnd, parent_hwnd) or 0)
        # SetParent intentionally does not toggle WS_POPUP/WS_CHILD.  GetParent
        # reports an owner for popup-style windows, so switch to child style
        # before verifying the effective native parent.
        _set_window_long(hwnd, -16, style)
        actual_parent = int(user32.GetParent(hwnd) or 0)
        if actual_parent != parent_hwnd:
            _set_window_long(hwnd, -16, self._original_style)
            self.last_error = (
                f"SetParent failed with WinError {ctypes.get_last_error()} "
                f"(hwnd={hwnd}, expected={parent_hwnd}, actual={actual_parent}, "
                f"previous={previous_parent})"
            )
            return False
        self._hwnd = hwnd
        self.last_error = ""
        self._message.hide()
        self._sync_size()
        user32.ShowWindow(hwnd, 5)
        self.attached.emit(True)
        return True

    def _sync_size(self) -> None:
        if self._hwnd is None or sys.platform != "win32":
            return
        _user32().MoveWindow(
            self._hwnd,
            0,
            0,
            max(1, self.width()),
            max(1, self.height()),
            True,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_size()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.focus_game()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.focus_game()

    def focus_game(self) -> bool:
        if self._hwnd is None or sys.platform != "win32":
            return False
        user32 = _user32()
        target_thread = int(user32.GetWindowThreadProcessId(self._hwnd, None))
        current_thread = int(ctypes.windll.kernel32.GetCurrentThreadId())
        attached = bool(
            target_thread
            and target_thread != current_thread
            and user32.AttachThreadInput(current_thread, target_thread, True)
        )
        try:
            user32.SetFocus(self._hwnd)
            return int(user32.GetFocus() or 0) == self._hwnd
        finally:
            if attached:
                user32.AttachThreadInput(current_thread, target_thread, False)


class PreviewOwner(QObject):
    """Own exactly one QProcess and the transactional Run workflow."""

    process_changed = Signal()
    event_received = Signal(dict)
    build_published = Signal(str)

    MAX_STDERR_BYTES = 64 * 1024
    START_TIMEOUT_MS = 5000
    STOP_TIMEOUT_MS = 1500

    def __init__(
        self,
        session: EditorSession,
        host: PreviewHost,
        parent: QObject | None = None,
        *,
        builder: PackageBuilder | None = None,
        python_executable: str | None = None,
        seed: int = 1337,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.host = host
        self.builder = builder
        self.python_executable = python_executable or sys.executable
        self.seed = int(seed)
        self.process: QProcess | None = None
        self._stdout = bytearray()
        self._stderr_forwarded = 0
        self._stderr_truncated = False
        self._stopping = False
        self._building = False
        self._stale = False
        self._launch_spec: _LaunchSpec | None = None
        self.session.program_changed.connect(self.mark_stale)

    @property
    def is_running(self) -> bool:
        return bool(
            self.process is not None
            and self.process.state() != QProcess.ProcessState.NotRunning
        )

    @property
    def run_id(self) -> str | None:
        return self._launch_spec.run_id if self._launch_spec is not None else None

    def current_target(self) -> PreviewTarget:
        unit = self.session.current_unit
        if unit is None or unit.kind == "Project":
            return PreviewTarget("project")
        if unit.kind == "Stage":
            return PreviewTarget("stage", unit.id)
        if unit.kind in {"Wave", "Enemy", "Spell"}:
            return PreviewTarget(unit.kind.lower(), unit.id)
        stage_id = self.session.current_stage_id
        return PreviewTarget("stage", stage_id) if stage_id else PreviewTarget("project")

    def run_current(self) -> bool:
        return self.run(self.current_target())

    def run(self, target: PreviewTarget) -> bool:
        if not self.session.is_open or self.session.project_context is None:
            self.session.append_run_log("[Preview] 请先打开声明式 Python 工程")
            return False
        old_spec = self._launch_spec if self.is_running else None
        self._building = True
        self.session.set_build_state("building")
        try:
            self.session.save_all()
            errors = [
                diagnostic
                for diagnostic in self.session.diagnostics
                if diagnostic.severity == "error"
            ]
            if errors:
                raise RuntimeError(errors[0].message)
            program = self.session.program
            stage_id = None
            if target.kind in {"wave", "enemy", "spell"}:
                program = practice_program(program, target.unit_id)
                stage_id = PRACTICE_STAGE_ID
            elif target.kind == "stage":
                stage_id = target.unit_id
            builder = self.builder or PackageBuilder(
                project_root=self.session.project_context.root,
                source_root=self.session.source_project.root,
                python_executable=self.python_executable,
            )
            prepared = builder.prepare(program)
        except Exception as exc:
            self.session.set_build_state("error")
            self.session.append_run_log(
                f"[Preview:BUILD_ERROR] {type(exc).__name__}: {exc}"
            )
            self._building = False
            return False

        try:
            if self.is_running:
                self._stop_process(set_stopped=False)
            published = builder.publish(prepared)
        except Exception as exc:
            self.session.set_build_state("error")
            self.session.append_run_log(
                f"[Preview:PUBLISH_ERROR] {type(exc).__name__}: {exc}"
            )
            self._building = False
            if old_spec is not None:
                self._launch(old_spec)
            return False

        spec = _LaunchSpec(
            entry_module=f"game_content.generated.{prepared.project_id}.entry",
            stage_id=stage_id,
            run_id=uuid.uuid4().hex,
            seed=self.seed,
            project_root=self.session.project_context.root,
            build_hash=prepared.build_hash,
            target=target,
        )
        self.session.set_build_state("ready", prepared.build_hash)
        self.session.reset_trace()
        self._stale = False
        self._building = False
        self.build_published.emit(str(published))
        return self._launch(spec)

    def _launch(self, spec: _LaunchSpec) -> bool:
        main_script = spec.project_root / "main.py"
        if not main_script.is_file():
            self.session.append_run_log(f"[Preview] 缺少真实游戏入口：{main_script}")
            self.session.set_preview_state("error")
            return False
        process = QProcess(self)
        process.setProgram(self.python_executable)
        arguments = [
            str(main_script),
            "--content-entry",
            spec.entry_module,
            "--project",
            str(spec.project_root),
            "--editor-preview",
            spec.run_id,
            "--preview-seed",
            str(spec.seed),
        ]
        if spec.stage_id:
            arguments.extend(("--stage", spec.stage_id))
        process.setArguments(arguments)
        process.setWorkingDirectory(str(spec.project_root))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUTF8", "1")
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._process_error)
        self.process = process
        self._launch_spec = spec
        self._stdout.clear()
        self._stderr_forwarded = 0
        self._stderr_truncated = False
        self._stopping = False
        self.session.set_preview_state("starting")
        process.start()
        if not process.waitForStarted(self.START_TIMEOUT_MS):
            self.session.append_run_log(f"[Preview:START_ERROR] {process.errorString()}")
            self.process = None
            self.session.set_preview_state("error")
            return False
        self.host.attach_process(process)
        self.process_changed.emit()
        return True

    def mark_stale(self) -> None:
        if self._building or not self.is_running:
            return
        self._stale = True
        self.session.set_preview_state("stale")

    def pause(self) -> None:
        self._send("pause")

    def resume(self) -> None:
        self._send("resume")

    def restart(self) -> None:
        self._send("restart")

    def seek(self, frame: int) -> None:
        self._send("seek", {"frame": frame})

    def stop(self) -> None:
        self._stop_process(set_stopped=True)

    def _send(self, command: str, payload=None) -> None:
        if not self.is_running or self.process is None or self._launch_spec is None:
            raise RuntimeError("preview process is not running")
        self.process.write(
            encode_message(control_message(self._launch_spec.run_id, command, payload))
        )

    def _stop_process(self, *, set_stopped: bool) -> None:
        process = self.process
        if process is None:
            if set_stopped:
                self.session.set_preview_state("stopped")
            return
        self._stopping = True
        self.session.set_preview_state("stopping")
        try:
            if process.state() != QProcess.ProcessState.NotRunning:
                try:
                    self._send("stop")
                    process.waitForBytesWritten(250)
                except RuntimeError:
                    pass
                if not process.waitForFinished(self.STOP_TIMEOUT_MS):
                    process.terminate()
                    if not process.waitForFinished(750):
                        process.kill()
                        process.waitForFinished(750)
        finally:
            self.host.detach()
            self.process = None
            self._launch_spec = None
            self._stopping = False
            if set_stopped:
                self.session.set_preview_state("stopped")
            self.process_changed.emit()

    def _read_stdout(self) -> None:
        if self.process is None:
            return
        self._stdout.extend(bytes(self.process.readAllStandardOutput()))
        while b"\n" in self._stdout:
            raw, _, remainder = self._stdout.partition(b"\n")
            self._stdout = bytearray(remainder)
            if not raw:
                continue
            if len(raw) > MAX_PREVIEW_LINE_BYTES:
                self._protocol_error("line_too_long", "preview event line is too long")
                continue
            try:
                message = decode_message(raw)
                if "event" not in message:
                    raise PreviewProtocolError(
                        "invalid_message", "editor accepts preview events only"
                    )
            except PreviewProtocolError as exc:
                self._protocol_error(exc.code, exc.message)
                continue
            if self._launch_spec is None or message["run_id"] != self._launch_spec.run_id:
                continue
            self._handle_event(message)
        if len(self._stdout) > MAX_PREVIEW_LINE_BYTES:
            self._stdout.clear()
            self._protocol_error("line_too_long", "unterminated preview event is too long")

    def _read_stderr(self) -> None:
        if self.process is None:
            return
        raw = bytes(self.process.readAllStandardError())
        allowance = max(0, self.MAX_STDERR_BYTES - self._stderr_forwarded)
        forwarded = raw[:allowance]
        self._stderr_forwarded += len(forwarded)
        if forwarded:
            try:
                text = forwarded.decode("utf-8")
            except UnicodeDecodeError:
                text = forwarded.decode(locale.getpreferredencoding(False), errors="replace")
            self.session.append_run_log(text)
        if len(raw) > allowance and not self._stderr_truncated:
            self._stderr_truncated = True
            self.session.append_run_log(
                f"[Preview] stderr 已在 {self.MAX_STDERR_BYTES} bytes 后截断"
            )

    def _handle_event(self, message: dict) -> None:
        event = message["event"]
        payload = message["payload"]
        if event == "state":
            state = payload.get("state")
            if state in {"starting", "running", "paused"} and not self._stale:
                self.session.set_preview_state(state)
        elif event == "trace":
            self.session.append_trace(payload.get("events", ()))
            dropped = payload.get("dropped", 0)
            if dropped:
                self.session.append_run_log(f"[Preview] Trace 丢弃 {dropped} 条旧事件")
        elif event == "frame":
            self.session.preview_frame = payload["frame"]
        elif event == "error":
            self.session.append_run_log(
                f"[Preview:{payload.get('code', 'ERROR')}] {payload.get('message', '')}"
            )
            self.session.set_preview_state("error")
        elif event == "stopped" and not self._stopping:
            self.session.set_preview_state("stopped")
        self.event_received.emit(message)

    def _protocol_error(self, code: str, message: str) -> None:
        self.session.append_run_log(f"[Preview:PROTOCOL:{code}] {message}")

    def _process_error(self, _error) -> None:
        if not self._stopping and self.process is not None:
            self.session.append_run_log(f"[Preview:PROCESS] {self.process.errorString()}")

    def _finished(self, exit_code: int, _exit_status) -> None:
        self._read_stdout()
        self._read_stderr()
        if not self._stopping and exit_code != 0:
            self.session.append_run_log(f"[Preview] 游戏进程退出码 {exit_code}")
            self.session.set_preview_state("error")
        elif not self._stopping:
            self.session.set_preview_state("stopped")
        self.host.detach()
        self.process = None
        self._launch_spec = None
        self.process_changed.emit()


def _find_preview_window(pid: int) -> int | None:
    if sys.platform != "win32":
        return None
    user32 = _user32()
    found = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @callback_type
    def callback(hwnd, _lparam):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if int(owner.value) != pid or not user32.IsWindowVisible(hwnd):
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        title = ctypes.create_unicode_buffer(max(1, length + 1))
        user32.GetWindowTextW(hwnd, title, len(title))
        found.append((int(hwnd), title.value))
        return "pystg editor preview" not in title.value.lower()

    user32.EnumWindows(callback, 0)
    return next(
        (hwnd for hwnd, title in found if "pystg editor preview" in title.lower()),
        None,
    )


def _get_window_long(hwnd: int, index: int) -> int:
    user32 = _user32()
    function = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    return int(function(hwnd, index))


def _set_window_long(hwnd: int, index: int, value: int) -> None:
    user32 = _user32()
    function = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    function(hwnd, index, value)


__all__ = ["PreviewHost", "PreviewOwner", "PreviewTarget"]

"""Single real-game preview process owner and Windows native window host."""

from __future__ import annotations

import ctypes
import locale
import re
import shutil
import sys
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from src.compiler.package_builder import PackageBuilder, PreparedBuild, PublishedBuild
from src.compiler.practice import PRACTICE_STAGE_ID, practice_program
from src.core.preview_protocol import (
    MAX_PREVIEW_LINE_BYTES,
    PREVIEW_DEFAULT_SEED,
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
    python_executable: str = ""
    source_root: Path | None = None
    seek_units: frozenset[str] = frozenset()


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

    def game_size(self) -> tuple[int, int]:
        """The game window's own size when it was first embedded."""

        left, top, right, bottom = self._original_rect
        return max(1, right - left), max(1, bottom - top)

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
        """Fit the game into the host with its aspect ratio preserved.

        MoveWindow works in physical pixels relative to the parent client area,
        so the host's logical size must be scaled by the device pixel ratio;
        otherwise the game overflows or underfills the visible panel on scaled
        displays.
        """

        if self._hwnd is None or sys.platform != "win32":
            return
        ratio = self.devicePixelRatioF()
        host_w = max(1, round(self.width() * ratio))
        host_h = max(1, round(self.height() * ratio))
        left, top, right, bottom = self._original_rect
        game_w = max(1, right - left)
        game_h = max(1, bottom - top)
        scale = min(host_w / game_w, host_h / game_h)
        child_w = max(1, round(game_w * scale))
        child_h = max(1, round(game_h * scale))
        _user32().MoveWindow(
            self._hwnd,
            (host_w - child_w) // 2,
            (host_h - child_h) // 2,
            child_w,
            child_h,
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
        seed: int = PREVIEW_DEFAULT_SEED,
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
        self._launch_spec: _LaunchSpec | None = None
        self._build_process: QProcess | None = None
        self._build_stdout = bytearray()
        self._build_stderr = bytearray()
        self._build_staging: Path | None = None
        self._build_builder: PackageBuilder | None = None
        self._build_target: PreviewTarget | None = None
        self._build_stage_id: str | None = None
        self._build_cancelled = False
        self._previous_spec: _LaunchSpec | None = None
        self._previous_stale = False
        self._previous_state = "stopped"
        self._restore_pause_pending = False
        self._published_transaction: PublishedBuild | None = None
        self._build_timer = QTimer(self)
        self._build_timer.setSingleShot(True)
        self._build_timer.timeout.connect(self._build_timeout)
        self._startup_timer = QTimer(self)
        self._startup_timer.setSingleShot(True)
        self._startup_timer.timeout.connect(self._startup_timeout)
        self.host.attached.connect(self._host_attachment_changed)
        self.session.program_changed.connect(self.mark_stale)

    @property
    def is_building(self) -> bool:
        return self._build_process is not None

    @property
    def is_running(self) -> bool:
        return bool(
            self.process is not None
            and self.process.state() != QProcess.ProcessState.NotRunning
        )

    @property
    def run_id(self) -> str | None:
        return self._launch_spec.run_id if self._launch_spec is not None else None

    @property
    def is_stale(self) -> bool:
        return self.session.preview_stale

    def seek_unavailable_reason(self, unit_id: str | None) -> str:
        """Explain whether this scope belongs to the actual running build."""

        if not self.is_running or self._launch_spec is None:
            return "请先运行预览，再定位播放时间。"
        if unit_id is not None and unit_id not in self._launch_spec.seek_units:
            return "当前时间范围不在正在预览的构建中；请先运行此内容或关卡。"
        if self.session.preview_state not in {"running", "paused"}:
            return "预览正在启动或快进，请稍后再定位。"
        return ""

    def can_seek_unit(self, unit_id: str | None) -> bool:
        return not self.seek_unavailable_reason(unit_id)

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
            self.session.set_preview_error("请先打开声明式 Python 工程")
            return False
        if self.is_building or self._published_transaction is not None:
            self.session.append_run_log("[Preview] 构建正在进行；可点击停止取消")
            return False
        self.session.set_preview_error("")
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
                diagnostic = errors[0]
                self.session.set_preview_error(diagnostic.message, diagnostic.uid)
                if diagnostic.uid:
                    try:
                        self.session.select_node(diagnostic.uid)
                    except Exception as locate_error:
                        self.session.append_run_log(
                            f"[Preview] 无法定位错误节点 {diagnostic.uid}: {locate_error}"
                        )
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
            request, staging = builder.worker_request(program)
        except Exception as exc:
            self.session.set_build_state("error")
            if not self.session.preview_error:
                self.session.set_preview_error(str(exc))
            self.session.append_run_log(
                f"[Preview:BUILD_ERROR] {type(exc).__name__}: {exc}"
            )
            self._building = False
            return False
        process = QProcess(self)
        process.setProgram(builder.worker_command()[0])
        process.setArguments(builder.worker_command()[1:])
        process.setWorkingDirectory(str(builder.project_root))
        environment = QProcessEnvironment.systemEnvironment()
        for name, value in builder.worker_environment().items():
            environment.insert(name, value)
        process.setProcessEnvironment(environment)
        self._build_process = process
        self._build_builder = builder
        self._build_staging = staging
        self._build_target = target
        self._build_stage_id = stage_id
        self._build_stdout.clear()
        self._build_stderr.clear()
        self._build_cancelled = False
        process.started.connect(lambda: (process.write(request), process.closeWriteChannel()))
        process.readyReadStandardOutput.connect(self._read_build_output)
        process.readyReadStandardError.connect(self._read_build_output)
        process.finished.connect(self._build_finished)
        process.errorOccurred.connect(self._build_process_error)
        self._build_timer.start(int(builder.BUILD_TIMEOUT_SECONDS * 1000))
        process.start()
        return True

    def _read_build_output(self) -> None:
        process = self._build_process
        if process is None:
            return
        self._build_stdout.extend(bytes(process.readAllStandardOutput()))
        raw = bytes(process.readAllStandardError())
        self._build_stderr.extend(raw[:max(0, self.MAX_STDERR_BYTES - len(self._build_stderr))])
        if len(self._build_stdout) > 16 * 1024 * 1024:
            self.cancel_build("构建结果超过 16 MiB 上限", failed=True)

    def _build_process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart and self._build_process is not None:
            detail = self._build_process.errorString()
            self._build_failed(detail)
            self._dispose_build()

    def _build_timeout(self) -> None:
        self.cancel_build("构建超时（60 秒）；旧预览保持运行", failed=True)

    def cancel_build(self, reason: str = "构建已取消", *, failed: bool = False) -> None:
        process = self._build_process
        if process is None:
            return
        self._build_cancelled = True
        self._build_timer.stop()
        if failed:
            self._build_failed(reason)
        else:
            self._building = False
            self.session.set_build_state("idle")
            self.session.append_run_log(f"[Preview] {reason}")
        process.kill()

    def _build_failed(self, detail: str, uid: str | None = None) -> None:
        self._building = False
        self.session.set_build_state("error")
        self.session.set_preview_error(detail, uid)
        self.session.append_run_log(f"[Preview:BUILD_ERROR] {detail}")
        if uid:
            try:
                self.session.select_node(uid)
            except Exception as exc:
                self.session.append_run_log(f"[Preview] 无法定位错误节点 {uid}: {exc}")

    def _dispose_build(self, *, preserve_staging: bool = False) -> None:
        self._build_timer.stop()
        process = self._build_process
        self._build_process = None
        if process is not None:
            process.deleteLater()
        if not preserve_staging and self._build_staging is not None:
            if self._build_staging.exists():
                shutil.rmtree(self._build_staging, ignore_errors=True)
        self._build_staging = None

    def _build_finished(self, exit_code: int, _status) -> None:
        self._read_build_output()
        if self._build_cancelled:
            self._dispose_build()
            return
        builder = self._build_builder
        target = self._build_target
        if builder is None or target is None:
            self._dispose_build()
            return
        try:
            prepared = builder.decode_worker_result(bytes(self._build_stdout), exit_code, bytes(self._build_stderr))
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", ())
            uid = diagnostics[0].uid if diagnostics else None
            self._build_failed(str(exc), uid)
            self._dispose_build()
            return
        self._dispose_build(preserve_staging=True)
        self._publish_and_launch(builder, prepared, target, self._build_stage_id)

    def _publish_and_launch(self, builder: PackageBuilder, prepared: PreparedBuild, target: PreviewTarget, stage_id: str | None) -> None:
        seek_units = _prepared_seek_units(prepared, stage_id)
        old_spec = self._launch_spec if self.is_running else None
        self._previous_spec = old_spec
        self._previous_stale = self.is_stale
        self._previous_state = self.session.preview_state
        try:
            if self.is_running:
                self._stop_process(set_stopped=False)
            self._published_transaction = builder.begin_publish(prepared)
        except Exception as exc:
            self.session.set_build_state("error")
            self.session.set_preview_error(str(exc))
            self.session.append_run_log(
                f"[Preview:PUBLISH_ERROR] {type(exc).__name__}: {exc}"
            )
            if old_spec is not None:
                self.session.set_preview_stale(self._previous_stale)
                self._restore_pause_pending = self._previous_state == "paused"
                self.session.set_preview_target(old_spec.target.kind, old_spec.target.unit_id)
                self.session.last_build_identity = old_spec.build_hash
                self.session.reset_trace(old_spec.run_id)
                self._launch(old_spec)
            self._building = False
            return False

        spec = _LaunchSpec(
            entry_module=f"game_content.generated.{prepared.project_id}.entry",
            stage_id=stage_id,
            run_id=uuid.uuid4().hex,
            seed=self.seed,
            project_root=self.session.project_context.root,
            build_hash=prepared.build_hash,
            target=target,
            python_executable=self.python_executable,
            source_root=self.session.source_project.root,
            seek_units=seek_units,
        )
        self.session.set_preview_target(target.kind, target.unit_id)
        self.session.reset_trace(spec.run_id)
        self.session.set_preview_stale(False)
        self._restore_pause_pending = False
        self._building = False
        if not self._launch(spec):
            self._restore_previous_build()

    def _restore_previous_build(self) -> None:
        self._startup_timer.stop()
        transaction = self._published_transaction
        old_spec = self._previous_spec
        old_stale = self._previous_stale
        old_state = self._previous_state
        self._published_transaction = None
        self._previous_spec = None
        self._previous_stale = False
        self._previous_state = "stopped"
        original_error = self.session.preview_error or "新预览启动失败"
        self._stop_process(set_stopped=False)
        self._launch_spec = None
        try:
            if transaction is not None:
                transaction.rollback()
        except Exception as exc:
            self._build_failed(f"{original_error}；恢复上次生成包失败：{exc}")
            self.session.set_preview_state("error")
            return
        self._build_failed(original_error)
        if old_spec is not None:
            self.session.set_preview_stale(old_stale)
            self._restore_pause_pending = old_state == "paused"
            self.session.set_preview_target(old_spec.target.kind, old_spec.target.unit_id)
            self.session.last_build_identity = old_spec.build_hash
            self.session.reset_trace(old_spec.run_id)
            self._launch(old_spec)
        else:
            self.session.set_preview_state("error")

    def _host_attachment_changed(self, attached: bool) -> None:
        if attached and self.session.preview_state in {"running", "paused"}:
            self._commit_started_build()

    def _commit_started_build(self) -> None:
        if self._published_transaction is None:
            return
        if sys.platform == "win32" and not self.host.is_attached:
            return
        transaction = self._published_transaction
        self._published_transaction = None
        self._previous_spec = None
        self._previous_stale = False
        self._previous_state = "stopped"
        self._startup_timer.stop()
        transaction.commit()
        spec = self._launch_spec
        if spec is not None:
            self.session.set_build_state("ready", spec.build_hash)
        self.build_published.emit(str(transaction.target_dir))

    def _startup_timeout(self) -> None:
        self.session.set_preview_error("游戏预览启动或原生嵌入超时")
        if self._published_transaction is not None:
            self._restore_previous_build()
        else:
            self._stop_process(set_stopped=False)
            self.session.set_preview_state("error")

    def _launch(self, spec: _LaunchSpec) -> bool:
        main_script = spec.project_root / "main.py"
        if not main_script.is_file():
            self.session.append_run_log(f"[Preview] 缺少真实游戏入口：{main_script}")
            self.session.set_preview_error(f"缺少真实游戏入口：{main_script}")
            self.session.set_preview_state("error")
            return False
        process = QProcess(self)
        process.setProgram(spec.python_executable or self.python_executable)
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
        if spec.source_root is not None:
            arguments.extend(("--authoring-root", str(spec.source_root)))
        if spec.target.kind in {"wave", "enemy", "spell"} and spec.target.unit_id:
            arguments.extend(("--preview-unit-id", spec.target.unit_id))
        process.setArguments(arguments)
        process.setWorkingDirectory(str(spec.project_root))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUTF8", "1")
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.finished.connect(lambda code, status: self._finished_process(process, code, status))
        process.errorOccurred.connect(lambda error: self._process_error_for(process, error))
        process.started.connect(lambda: self._process_started(process))
        self.process = process
        self._launch_spec = spec
        self._stdout.clear()
        self._stderr_forwarded = 0
        self._stderr_truncated = False
        self._stopping = False
        self.session.set_preview_state("starting")
        self._startup_timer.start(30000)
        process.start()
        return True

    def _process_started(self, process: QProcess) -> None:
        if process is self.process:
            self.host.attach_process(process)
            self.process_changed.emit()

    def mark_stale(self) -> None:
        if self.is_building:
            self.cancel_build("作者内容在构建期间发生变化；请重新运行")
        if not self.is_running and self.session.trace_run_id is None:
            return
        self.session.set_preview_stale(True)

    def pause(self) -> None:
        self._send("pause")

    def resume(self) -> None:
        self._send("resume")

    def restart(self) -> None:
        self._send("restart")

    def seek(self, frame: int, unit_id: str | None = None) -> None:
        """Seek in a Stage or selected unit's local timeline, excluding loading."""
        if unit_id is None and self._launch_spec is not None:
            target = self._launch_spec.target
            unit_id = target.unit_id if target.kind in {"wave", "enemy", "spell"} else None
        reason = self.seek_unavailable_reason(unit_id)
        if reason:
            raise RuntimeError(reason)
        payload = {"frame": frame}
        if unit_id:
            payload["unit_id"] = unit_id
        self._send("seek", payload)

    def stop(self) -> None:
        self._restore_pause_pending = False
        self.cancel_build()
        self._startup_timer.stop()
        self._stop_process(set_stopped=True)
        if self._published_transaction is not None:
            self._published_transaction.rollback()
            self._published_transaction = None
            self._previous_spec = None

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
            process.deleteLater()

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
            if state == "starting":
                # restart/seek keep the process identity but begin a new
                # deterministic execution; old observations must not be
                # overlaid onto the new branch or density samples.
                self.session.reset_trace(message["run_id"])
            if state in {"starting", "running", "paused", "seeking"}:
                self.session.set_preview_state(state)
            if state == "running" and self._restore_pause_pending:
                self._restore_pause_pending = False
                self.pause()
        elif event == "trace":
            self.session.append_trace(
                payload.get("events", ()),
                run_id=message["run_id"],
            )
            dropped = payload.get("dropped", 0)
            if dropped:
                self.session.append_run_log(f"[Preview] Trace 丢弃 {dropped} 条旧事件")
        elif event == "frame":
            self.session.preview_frame = payload["frame"]
        elif event == "error":
            error_message = str(payload.get("message", ""))
            uid = payload.get("uid") or _uid_from_runtime_error(error_message)
            self.session.append_run_log(
                f"[Preview:{payload.get('code', 'ERROR')}] {error_message}"
            )
            self.session.set_preview_error(error_message, uid)
            if uid:
                try:
                    self.session.select_node(str(uid))
                except Exception as locate_error:
                    self.session.append_run_log(
                        f"[Preview] 无法定位错误节点 {uid}: {locate_error}"
                    )
            self.session.set_preview_state("error")
        elif event == "stopped" and not self._stopping and self.session.preview_state != "error":
            self.session.set_preview_state("stopped")
        self.event_received.emit(message)
        if event == "state" and payload.get("state") == "running":
            self._commit_started_build()
            if self._published_transaction is None:
                self._startup_timer.stop()

    def _protocol_error(self, code: str, message: str) -> None:
        self.session.append_run_log(f"[Preview:PROTOCOL:{code}] {message}")

    def _process_error(self, _error) -> None:
        if not self._stopping and self.process is not None:
            message = self.process.errorString()
            self.session.append_run_log(f"[Preview:PROCESS] {message}")
            if not self.session.preview_error:
                self.session.set_preview_error(message)

    def _process_error_for(self, process: QProcess, error) -> None:
        if process is not self.process:
            return
        self._process_error(error)
        if error == QProcess.ProcessError.FailedToStart:
            process.deleteLater()
            self.process = None
            if self._published_transaction is not None:
                self._restore_previous_build()
            else:
                self._launch_spec = None
                self.session.set_preview_state("error")

    def _finished_process(self, process: QProcess, exit_code: int, status) -> None:
        if process is not self.process:
            return
        self._finished(exit_code, status)
        process.deleteLater()

    def _finished(self, exit_code: int, _exit_status) -> None:
        self._read_stdout()
        self._read_stderr()
        if not self._stopping and exit_code != 0:
            self.session.append_run_log(f"[Preview] 游戏进程退出码 {exit_code}")
            if not self.session.preview_error:
                self.session.set_preview_error(f"游戏进程退出码 {exit_code}")
            self.session.set_preview_state("error")
        elif not self._stopping and self.session.preview_state != "error":
            self.session.set_preview_state("stopped")
        self._startup_timer.stop()
        self.host.detach()
        self.process = None
        self._launch_spec = None
        self.process_changed.emit()
        if not self._stopping and self._published_transaction is not None:
            self._restore_previous_build()


def _prepared_seek_units(prepared: PreparedBuild, stage_id: str | None) -> frozenset[str]:
    """Read executable unit IDs from this validated package before publication."""

    stages = (stage_id,) if stage_id is not None else prepared.manifest.get("stages", ())
    units: set[str] = set()
    for stage in stages:
        folder = prepared.temp_dir / "stages" / stage
        if not (folder / "stage.py").is_file():
            continue
        units.add(stage)
        for kind in ("waves", "enemies", "spells", "tasks", "functions"):
            units.update(path.stem for path in (folder / kind).glob("*.py") if path.stem != "__init__")
    return frozenset(units)


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


def _uid_from_runtime_error(message: str) -> str | None:
    match = re.search(r"authoring node ([A-Za-z0-9_.:-]+):", str(message))
    return match.group(1) if match else None


__all__ = ["PreviewHost", "PreviewOwner", "PreviewTarget"]

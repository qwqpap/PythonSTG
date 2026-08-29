"""Real Windows gate for Qt + GLFW/ModernGL embedding and preview controls."""

from __future__ import annotations

import ctypes
import atexit
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from ctypes import wintypes


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.project_context import ProjectContext
from src.editor.preview import PreviewTarget
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtWidgets import QApplication


def _write_authoring(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project(\n"
        "    id='native_preview',\n"
        "    name='Native Preview Gate',\n"
        "    start_stage=Ref('native_stage'),\n"
        "    stages=[Ref('native_stage')],\n"
        ")\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "stage.py").write_text(
        "from src.authoring.dsl import Stage, Wait\n\n"
        "stage = Stage(\n"
        "    id='native_stage',\n"
        "    name='Native Stage',\n"
        "    body=[Wait(3600, uid='native_wait')],\n"
        ")\n",
        encoding="utf-8",
        newline="\n",
    )


def _wait(app: QApplication, predicate, timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise RuntimeError(f"timeout waiting for {label}")


def _expected_child_size(host: tuple[int, int], game: tuple[int, int]) -> tuple[int, int]:
    scale = min(host[0] / game[0], host[1] / game[1])
    return max(1, round(game[0] * scale)), max(1, round(game[1] * scale))


def _child_fits(window, hwnd: int) -> bool:
    ratio = window.preview_host.devicePixelRatioF()
    host = (
        max(1, round(window.preview_host.width() * ratio)),
        max(1, round(window.preview_host.height() * ratio)),
    )
    child = _child_size(hwnd)
    expected = _expected_child_size(host, window.preview_host.game_size())
    return abs(child[0] - expected[0]) <= 2 and abs(child[1] - expected[1]) <= 2


def _assert_letterboxed(window, host_logical, child) -> None:
    ratio = window.preview_host.devicePixelRatioF()
    host = (
        max(1, round(host_logical[0] * ratio)),
        max(1, round(host_logical[1] * ratio)),
    )
    game = window.preview_host.game_size()
    expected = _expected_child_size(host, game)
    if abs(child[0] - expected[0]) > 2 or abs(child[1] - expected[1]) > 2:
        raise RuntimeError(
            f"embedded game must letterbox-fit the host: {host=} {game=} {child=}"
        )
    if child[0] > host[0] + 2 or child[1] > host[1] + 2:
        raise RuntimeError(f"embedded game overflows the host: {host=} {child=}")


def _child_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetClientRect failed for embedded game window")
    return rect.right - rect.left, rect.bottom - rect.top


def _process_is_dead(pid: int) -> bool:
    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return True
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("native preview gate requires Windows")
    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if platform in {"offscreen", "minimal", "headless"}:
        raise RuntimeError(f"native gate refuses QT_QPA_PLATFORM={platform!r}")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    events = []
    with tempfile.TemporaryDirectory(prefix="pystg_cd6_native_") as temporary:
        authoring = Path(temporary) / "authoring"
        _write_authoring(authoring)
        session = EditorSession(project_context=ProjectContext(ROOT))
        session.open_project(authoring)
        session.select_unit("native_stage")
        window = EditorWindow(session)
        cleaned = False

        def cleanup() -> None:
            nonlocal cleaned
            if cleaned:
                return
            cleaned = True
            window.preview_owner.stop()
            window.close()
            app.processEvents()

        atexit.register(cleanup)
        window.preview_owner.event_received.connect(events.append)
        window.resize(1480, 920)
        window.show()
        window.raise_()
        window.activateWindow()
        app.processEvents()

        if not window.preview_owner.run(PreviewTarget("stage", "native_stage")):
            raise RuntimeError("real preview build/start failed: " + "\n".join(session.run_log))
        try:
            _wait(app, lambda: window.preview_host.is_attached, 40.0, "Win32 embedding")
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc}; host={window.preview_host.last_error!r}; "
                f"state={session.preview_state!r}; logs={list(session.run_log)[-12:]!r}"
            ) from exc
        _wait(
            app,
            lambda: session.preview_state == "running",
            20.0,
            "running state",
        )
        process = window.preview_owner.process
        if process is None:
            raise RuntimeError("preview process disappeared after embedding")
        pid = int(process.processId())
        hwnd = window.preview_host.native_handle
        if hwnd is None:
            raise RuntimeError("PreviewHost has no native HWND")

        large_host = (window.preview_host.width(), window.preview_host.height())
        large_child = _child_size(hwnd)
        if min(*large_host, *large_child) < 200:
            raise RuntimeError(f"1480x920 preview is not operable: {large_host=} {large_child=}")
        _assert_letterboxed(window, large_host, large_child)

        window.resize(960, 640)
        _wait(
            app,
            lambda: _child_fits(window, hwnd),
            5.0,
            "embedded resize",
        )
        small_host = (window.preview_host.width(), window.preview_host.height())
        small_child = _child_size(hwnd)
        if min(*small_host, *small_child) < 160:
            raise RuntimeError(f"960x640 preview is not operable: {small_host=} {small_child=}")
        _assert_letterboxed(window, small_host, small_child)

        window.raise_()
        window.activateWindow()
        app.processEvents()
        if not window.preview_host.focus_game():
            raise RuntimeError("keyboard focus did not enter the embedded GLFW child")

        _wait(
            app,
            lambda: any(item.get("uid") == "native_wait" for item in session.trace_events),
            15.0,
            "sparse authoring Trace",
        )
        trace_count = len(session.trace_events)
        window.preview_owner.pause()
        _wait(app, lambda: session.preview_state == "paused", 5.0, "pause")
        window.preview_owner.resume()
        _wait(app, lambda: session.preview_state == "running", 5.0, "resume")

        window.preview_owner.restart()
        _wait(
            app,
            lambda: any(
                item.get("event") == "state"
                and item.get("payload", {}).get("state") == "starting"
                for item in events
            ),
            5.0,
            "restart acknowledgement",
        )
        _wait(app, lambda: session.preview_state == "running", 30.0, "restart completion")
        if window.preview_owner.process is None or int(window.preview_owner.process.processId()) != pid:
            raise RuntimeError("restart replaced the real preview process instead of restarting the run")

        event_count = len(events)
        window.preview_owner.seek(180)
        _wait(
            app,
            lambda: any(
                item.get("event") == "state"
                and item.get("payload", {}).get("state") == "seeking"
                for item in events[event_count:]
            ),
            30.0,
            "seek fast-forward state",
        )
        _wait(
            app,
            lambda: session.preview_frame >= 180 and session.preview_state == "running",
            30.0,
            "seek completion",
        )

        window.preview_owner.stop()
        _wait(app, lambda: window.preview_owner.process is None, 5.0, "stop")
        _wait(app, lambda: _process_is_dead(pid), 5.0, "child process exit")
        if window.preview_host.is_attached:
            raise RuntimeError("native child remained attached after stop")
        cleanup()
        atexit.unregister(cleanup)

    result = {
        "status": "PASS",
        "qt_platform": QApplication.platformName(),
        "pid": pid,
        "large_host": large_host,
        "large_child": large_child,
        "small_host": small_host,
        "small_child": small_child,
        "trace_events": trace_count,
        "controls": ["pause", "resume", "restart", "seek", "stop"],
        "orphan_process": False,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

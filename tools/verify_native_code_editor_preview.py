"""Real Windows gate for Qt + GLFW/ModernGL embedding and preview controls.

The gate runs the complete declarative example project
(``game_content/authoring/code_editor_demo``) so the Project, Stage, and Spell
practice targets are the version-controlled demo content required by CD4.
"""

from __future__ import annotations

import ctypes
import atexit
import json
import os
import sys
import time
from pathlib import Path
from ctypes import wintypes


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.authoring.timeline import Unknown
from src.core.project_context import ProjectContext
from src.editor.preview import PreviewTarget
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtWidgets import QApplication


EXAMPLE = ROOT / "game_content" / "authoring" / "code_editor_demo"


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


def _assert_visible_feedback(window, expected_target: str) -> None:
    if not window.preview_target_label.isVisible():
        raise RuntimeError("preview target feedback is not visible")
    target_text = window.preview_target_label.text()
    if expected_target not in target_text:
        raise RuntimeError(
            f"preview target feedback mismatch: expected {expected_target!r}, "
            f"got {target_text!r}"
        )
    if not window.build_status_label.isVisible():
        raise RuntimeError("preview build feedback is not visible")
    if window.build_status_label.text() != "构建：成功":
        raise RuntimeError(
            f"preview build feedback mismatch: {window.build_status_label.text()!r}"
        )
    if window.preview_error_label.isVisible() or window.preview_error_label.text():
        raise RuntimeError(
            f"unexpected visible preview error: {window.preview_error_label.text()!r}"
        )


def _assert_timeline_operable(window, expected_size: tuple[int, int]) -> None:
    if window.width() > expected_size[0] + 8 or window.height() > expected_size[1] + 8:
        raise RuntimeError(
            f"Timeline controls forced the window beyond {expected_size}: "
            f"actual={(window.width(), window.height())}"
        )
    controls = (
        window.timeline_panel,
        window.timeline_panel.scope_combo,
        window.timeline_panel.loop_button,
        window.timeline_panel.loop_start,
        window.timeline_panel.loop_end,
    )
    if not all(widget.isVisible() and widget.isEnabled() for widget in controls):
        raise RuntimeError(f"Timeline is not operable at {expected_size}")


def _projection_interval(window, uid: str):
    projection = window.timeline_panel.projection
    if projection is None:
        raise RuntimeError("Timeline has no projection during the native run")
    interval = projection.find(uid)
    if interval is None:
        raise RuntimeError(f"Timeline projection lost {uid!r}")
    return interval


def _assert_static_estimate_survives_trace(
    app: QApplication,
    window: EditorWindow,
    uid: str,
    *,
    dynamic: bool,
    static_end: int = 0,
) -> None:
    """The observed Trace bar must sit beside the static estimate, not replace it."""

    def observed() -> bool:
        interval = _projection_interval(window, uid)
        if interval.observed_start is None:
            return False
        return dynamic or interval.observed_end is not None

    _wait(app, observed, 20.0, f"actual Trace overlay for {uid}")
    if dynamic:
        if not isinstance(_projection_interval(window, uid).end, Unknown):
            raise RuntimeError(
                f"static dynamic-Unknown end for {uid!r} was overwritten by Trace"
            )
    else:
        interval = _projection_interval(window, uid)
        if isinstance(interval.start, Unknown) or isinstance(interval.end, Unknown):
            raise RuntimeError(f"static estimate for {uid!r} became Unknown")
        if interval.start != 0 or interval.end != static_end:
            raise RuntimeError(
                f"static estimate for {uid!r} was overwritten by Trace: "
                f"{interval.start!r}..{interval.end!r} (expected 0..{static_end})"
            )


def _start_target(
    app: QApplication,
    window: EditorWindow,
    session: EditorSession,
    target: PreviewTarget,
    *,
    expected_target: str,
    trace_uid: str,
) -> tuple[int, int]:
    if not window.preview_owner.run(target):
        raise RuntimeError(
            f"real {target.kind} preview build/start failed: "
            + "\n".join(session.run_log)
        )
    try:
        _wait(app, lambda: window.preview_host.is_attached, 40.0, "Win32 embedding")
    except RuntimeError as exc:
        raise RuntimeError(
            f"{exc}; target={target!r}; host={window.preview_host.last_error!r}; "
            f"state={session.preview_state!r}; logs={list(session.run_log)[-12:]!r}"
        ) from exc
    _wait(app, lambda: session.preview_state == "running", 20.0, "running state")
    _wait(
        app,
        lambda: any(item.get("uid") == trace_uid for item in session.trace_events),
        20.0,
        f"authoring Trace for {trace_uid}",
    )
    _wait(
        app,
        lambda: any(item.get("kind") == "metrics" for item in session.trace_events),
        10.0,
        f"bounded density metrics for {target.kind}",
    )
    _wait(
        app,
        lambda: "密度采样" in window.timeline_panel.status_label.text(),
        5.0,
        f"visible Timeline density feedback for {target.kind}",
    )
    process = window.preview_owner.process
    hwnd = window.preview_host.native_handle
    if process is None or hwnd is None:
        raise RuntimeError(f"{target.kind} preview lost its process or native HWND")
    _assert_visible_feedback(window, expected_target)
    return int(process.processId()), int(hwnd)


def _controls_roundtrip(
    app: QApplication,
    window: EditorWindow,
    session: EditorSession,
    events: list,
    *,
    label: str,
) -> None:
    if not window.preview_host.focus_game():
        raise RuntimeError(
            f"keyboard focus did not enter the embedded GLFW child ({label})"
        )
    window.preview_owner.pause()
    _wait(app, lambda: session.preview_state == "paused", 5.0, f"{label} pause")
    window.preview_owner.resume()
    _wait(app, lambda: session.preview_state == "running", 5.0, f"{label} resume")
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
        f"{label} seek fast-forward state",
    )
    _wait(
        app,
        lambda: session.preview_frame >= 180 and session.preview_state == "running",
        30.0,
        f"{label} seek completion",
    )


def _stop_target(
    app: QApplication,
    window: EditorWindow,
    pid: int,
    *,
    target_kind: str,
) -> None:
    window.preview_owner.stop()
    _wait(app, lambda: window.preview_owner.process is None, 5.0, f"{target_kind} stop")
    _wait(app, lambda: _process_is_dead(pid), 5.0, f"{target_kind} process exit")
    if window.preview_host.is_attached:
        raise RuntimeError(f"{target_kind} native child remained attached after stop")


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("native preview gate requires Windows")
    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if platform in {"offscreen", "minimal", "headless"}:
        raise RuntimeError(f"native gate refuses QT_QPA_PLATFORM={platform!r}")
    if not EXAMPLE.is_dir():
        raise RuntimeError(f"complete example project is missing: {EXAMPLE}")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    events = []
    session = EditorSession(project_context=ProjectContext(ROOT))
    session.open_project(EXAMPLE)
    session.select_unit("demo_stage")
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
    _assert_timeline_operable(window, (1480, 920))

    target_results = []
    pid, hwnd = _start_target(
        app,
        window,
        session,
        PreviewTarget("project"),
        expected_target="整个工程",
        trace_uid="stage_intro_wait",
    )
    target_results.append(
        {"target": "project", "pid": pid, "trace_events": len(session.trace_events)}
    )
    _assert_static_estimate_survives_trace(
        app,
        window,
        "stage_intro_wait",
        dynamic=False,
        static_end=30,
    )

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
    _assert_timeline_operable(window, (960, 640))

    window.raise_()
    window.activateWindow()
    app.processEvents()
    _controls_roundtrip(app, window, session, events, label="project")
    _assert_timeline_operable(window, (960, 640))

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

    _stop_target(app, window, pid, target_kind="project")

    window.resize(1480, 920)
    app.processEvents()
    pid, hwnd = _start_target(
        app,
        window,
        session,
        PreviewTarget("stage", "demo_stage"),
        expected_target="Stage · demo_stage",
        trace_uid="stage_intro_wait",
    )
    if not _child_fits(window, hwnd):
        raise RuntimeError("Stage preview did not embed at the current host size")
    target_results.append(
        {"target": "stage", "pid": pid, "trace_events": len(session.trace_events)}
    )
    _assert_static_estimate_survives_trace(
        app,
        window,
        "stage_intro_wait",
        dynamic=False,
        static_end=30,
    )
    _controls_roundtrip(app, window, session, events, label="stage")
    _stop_target(app, window, pid, target_kind="stage")

    session.select_unit("demo_spell")
    app.processEvents()
    pid, hwnd = _start_target(
        app,
        window,
        session,
        PreviewTarget("spell", "demo_spell"),
        expected_target="Spell 练习场 · demo_spell",
        trace_uid="spell_raw_python",
    )
    if not _child_fits(window, hwnd):
        raise RuntimeError("Spell practice preview did not embed at the current host size")
    target_results.append(
        {"target": "spell", "pid": pid, "trace_events": len(session.trace_events)}
    )
    _assert_static_estimate_survives_trace(
        app,
        window,
        "spell_raw_python",
        dynamic=True,
    )
    _controls_roundtrip(app, window, session, events, label="spell")
    _stop_target(app, window, pid, target_kind="spell")
    cleanup()
    atexit.unregister(cleanup)

    result = {
        "status": "PASS",
        "qt_platform": QApplication.platformName(),
        "example_project": EXAMPLE.as_posix(),
        "targets": target_results,
        "large_host": large_host,
        "large_child": large_child,
        "small_host": small_host,
        "small_child": small_child,
        "controls": ["focus", "pause", "resume", "seek", "restart", "stop"],
        "static_estimate_preserved": ["stage_intro_wait", "spell_raw_python"],
        "orphan_process": False,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Final Windows gate for the complete code-driven editor workflow."""

from __future__ import annotations

import atexit
import ctypes
import json
import os
import shutil
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.authoring.program import ProgramError, find_node
from src.authoring.timeline import Unknown
from src.compiler.practice import PRACTICE_STAGE_ID
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


def _child_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetClientRect failed for embedded game window")
    return rect.right - rect.left, rect.bottom - rect.top


def _process_is_dead(pid: int) -> bool:
    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        return True
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _choose_palette(window: EditorWindow, app: QApplication, button, label: str) -> None:
    button.click()
    app.processEvents()
    menu = window._node_menu
    if menu is None or not menu.isVisible():
        raise RuntimeError("node palette did not open from its visible toolbar button")
    for category in menu.actions():
        submenu = category.menu()
        for action in submenu.actions() if submenu is not None else ():
            if action.text() == label:
                action.trigger()
                app.processEvents()
                return
    raise RuntimeError(f"node palette did not contain {label!r}")


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("final native editor gate requires Windows")
    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if platform in {"offscreen", "minimal", "headless"}:
        raise RuntimeError(f"native gate refuses QT_QPA_PLATFORM={platform!r}")
    if not EXAMPLE.is_dir():
        raise RuntimeError(f"missing complete example: {EXAMPLE}")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pids: list[int] = []
    trace_counts: dict[str, int] = {}
    sizes: dict[str, dict[str, tuple[int, int]]] = {}
    with tempfile.TemporaryDirectory(prefix="pystg_cd7_native_") as temporary:
        authoring = Path(temporary) / "code_editor_demo"
        shutil.copytree(EXAMPLE, authoring)
        session = EditorSession(project_context=ProjectContext(ROOT))
        session.open_project(authoring)
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
        window.resize(1480, 920)
        window.show()
        window.raise_()
        window.activateWindow()
        app.processEvents()

        session.select_unit("demo_stage")
        app.processEvents()
        projection = window.timeline_panel.projection
        if projection is None:
            raise RuntimeError("Timeline did not project the complete Stage")
        if not isinstance(projection.find("spell_raw_python").end, Unknown):
            raise RuntimeError("Timeline hid the example's dynamic RawPython interval")
        if projection.find("stage_parallel_intro").kind != "parallel":
            raise RuntimeError("Timeline did not expose independent Parallel lanes")

        window.timeline_panel.edit_interval("stage_intro_wait", 45)
        window.timeline_panel.edit_interval("stage_at_cue", 50)
        session.select_unit("aimed_fairy")
        window.timeline_panel.edit_interval("aimed_enter", 75)
        if session.undo_stack.count() != 3:
            raise RuntimeError("Timeline edits did not use the one Undo stack")
        for _ in range(3):
            session.undo_stack.undo()
        if find_node(session.program, "stage_intro_wait")[1].arguments["frames"] != 30:
            raise RuntimeError("Timeline Wait undo did not restore source")
        if find_node(session.program, "stage_at_cue")[1].arguments["frame"] != 35:
            raise RuntimeError("Timeline At undo did not restore source")
        if find_node(session.program, "aimed_enter")[1].arguments["duration"] != 45:
            raise RuntimeError("Timeline duration undo did not restore source")

        session.select_unit("demo_stage")
        session.select_node("stage_intro_wait")
        _choose_palette(window, app, window.add_after_button, "等待")
        appended_uid = session.current_node_uid
        if appended_uid is None or find_node(session.program, appended_uid)[1].kind != "Wait":
            raise RuntimeError("visible add-after interface did not create a Wait node")
        session.select_node("stage_at_cue")
        _choose_palette(window, app, window.add_child_button, "等待")
        child_uid = session.current_node_uid
        if child_uid is None or find_node(session.program, child_uid)[1].kind != "Wait":
            raise RuntimeError("visible add-child interface did not create a Wait node")
        window.delete_node_button.click()
        app.processEvents()
        try:
            find_node(session.program, child_uid)
        except ProgramError:
            pass
        else:
            raise RuntimeError("visible delete interface did not remove the selected node")
        session.undo_stack.undo()
        if find_node(session.program, child_uid)[1].kind != "Wait":
            raise RuntimeError("Undo did not restore the deleted node")
        session.undo_stack.undo()
        session.undo_stack.undo()
        for uid in (appended_uid, child_uid):
            try:
                find_node(session.program, uid)
            except ProgramError:
                continue
            raise RuntimeError("Undo did not restore the original example before preview")

        def run_target(
            name: str,
            target: PreviewTarget,
            expected_uid: str,
            size: tuple[int, int],
            *,
            controls: bool = False,
        ) -> None:
            window.resize(*size)
            app.processEvents()
            if not window.preview_owner.run(target):
                raise RuntimeError(
                    f"{name} preview build/start failed: {list(session.run_log)[-12:]!r}"
                )
            _wait(app, lambda: window.preview_host.is_attached, 45.0, f"{name} embedding")
            _wait(app, lambda: session.preview_state == "running", 30.0, f"{name} running")
            process = window.preview_owner.process
            hwnd = window.preview_host.native_handle
            if process is None or hwnd is None:
                raise RuntimeError(f"{name} lost its process or native child")
            pid = int(process.processId())
            pids.append(pid)
            host_size = (window.preview_host.width(), window.preview_host.height())
            child_size = _child_size(hwnd)
            if abs(host_size[0] - child_size[0]) > 2 or abs(host_size[1] - child_size[1]) > 2:
                raise RuntimeError(f"{name} child does not fill host: {host_size=} {child_size=}")
            if min(*host_size, *child_size) < 160:
                raise RuntimeError(f"{name} preview is not operable: {host_size=} {child_size=}")
            if window.timeline_dock.height() < 90 or window.inspector_dock.width() < 100:
                raise RuntimeError(
                    f"{name} layout hid Timeline or Inspector: "
                    f"timeline={window.timeline_dock.height()} inspector={window.inspector_dock.width()}"
                )
            window.raise_()
            window.activateWindow()
            app.processEvents()
            if not window.preview_host.focus_game():
                raise RuntimeError(f"{name} keyboard focus did not enter GLFW child")
            try:
                _wait(
                    app,
                    lambda: any(
                        item.get("uid") == expected_uid for item in session.trace_events
                    )
                    or session.preview_state == "error",
                    25.0,
                    f"{name} authoring Trace",
                )
            except RuntimeError as exc:
                raise RuntimeError(
                    f"{exc}; state={session.preview_state!r}; frame={session.preview_frame}; "
                    f"trace={list(session.trace_events)[-8:]!r}; "
                    f"logs={list(session.run_log)[-16:]!r}"
                ) from exc
            if not any(item.get("uid") == expected_uid for item in session.trace_events):
                raise RuntimeError(
                    f"{name} preview failed before {expected_uid!r}; "
                    f"state={session.preview_state!r}; frame={session.preview_frame}; "
                    f"trace={list(session.trace_events)[-8:]!r}; "
                    f"logs={list(session.run_log)[-16:]!r}"
                )
            trace_counts[name] = len(session.trace_events)
            if session.trace_run_id != window.preview_owner.run_id:
                raise RuntimeError(f"{name} Trace was not bound to its run identity")
            if window.timeline_panel.projection is None:
                raise RuntimeError(f"{name} Timeline disappeared during Trace overlay")

            if controls:
                window.preview_owner.pause()
                _wait(app, lambda: session.preview_state == "paused", 5.0, "pause")
                window.preview_owner.resume()
                _wait(app, lambda: session.preview_state == "running", 5.0, "resume")
                window.preview_owner.restart()
                _wait(app, lambda: session.preview_state == "running", 30.0, "restart")
                if int(window.preview_owner.process.processId()) != pid:
                    raise RuntimeError("restart replaced the preview process")
                window.preview_owner.seek(180)
                _wait(
                    app,
                    lambda: session.preview_frame >= 180 and session.preview_state == "running",
                    35.0,
                    "seek",
                )

            sizes[name] = {"host": host_size, "child": child_size}
            window.preview_owner.stop()
            _wait(app, lambda: window.preview_owner.process is None, 5.0, f"{name} stop")
            _wait(app, lambda: _process_is_dead(pid), 5.0, f"{name} process exit")

        session.select_unit("demo_stage")
        run_target(
            "project",
            PreviewTarget("project"),
            "stage_background",
            (1480, 920),
        )
        run_target(
            "stage",
            PreviewTarget("stage", "demo_stage"),
            "stage_intro_wait",
            (960, 640),
        )
        session.select_unit("demo_spell")
        run_target(
            "spell",
            PreviewTarget("spell", "demo_spell"),
            "spell_parallel",
            (960, 640),
            controls=True,
        )
        if any(not _process_is_dead(pid) for pid in pids):
            raise RuntimeError("one or more preview child processes survived")
        cleanup()
        atexit.unregister(cleanup)

    print(
        json.dumps(
            {
                "status": "PASS",
                "qt_platform": QApplication.platformName(),
                "targets": ["project", "stage", "spell"],
                "practice_stage": PRACTICE_STAGE_ID,
                "sizes": sizes,
                "trace_counts": trace_counts,
                "timeline_edits": ["wait", "duration", "at"],
                "node_editing": ["add_after", "add_child", "delete", "undo"],
                "controls": ["pause", "resume", "restart", "seek", "stop"],
                "orphan_process": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

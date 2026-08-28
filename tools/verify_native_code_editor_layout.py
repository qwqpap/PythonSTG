"""Real Windows gate for the CD5 code-editor layout.

This verifier deliberately refuses offscreen/minimal Qt.  It opens an exposed
top-level PySide6 window, exercises both required sizes, switches all activity
views, closes/restores both central groups, and confirms the permanent Timeline
remains visible.  It does not stand in for the CD6 GLFW/ModernGL embedding gate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.core.project_context import ProjectContext
from src.editor.session import EditorSession
from src.editor.window import EditorWindow
from src.qt_compat.QtWidgets import QApplication


REQUIRED_SIZES = ((1480, 920), (960, 640))


def _write_project(root: Path) -> Path:
    authoring = root / "game_content" / "authoring" / "native_layout"
    authoring.mkdir(parents=True)
    (root / "assets").mkdir()
    (authoring / "project.py").write_text(
        "from src.authoring.dsl import Project, Ref\n\n"
        "project = Project('native_layout', 'Native Layout', Ref('stage'), [Ref('stage')])\n",
        encoding="utf-8",
        newline="\n",
    )
    (authoring / "stage.py").write_text(
        "from src.authoring.dsl import Stage, Wait\n\n"
        "stage = Stage('stage', 'Stage', body=[Wait(12, uid='wait')])\n",
        encoding="utf-8",
        newline="\n",
    )
    return authoring


def _process_events(app: QApplication, rounds: int = 5) -> None:
    for _ in range(rounds):
        app.processEvents()


def verify_native_layout() -> dict[str, object]:
    platform_override = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if platform_override in {"offscreen", "minimal"}:
        raise RuntimeError(f"native gate refuses QT_QPA_PLATFORM={platform_override!r}")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    if app.platformName().lower() != "windows":
        raise RuntimeError(f"native gate requires Qt windows platform, got {app.platformName()!r}")

    observations: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="pystg-cd5-native-") as temporary:
        project_root = Path(temporary)
        authoring = _write_project(project_root)
        session = EditorSession(project_context=ProjectContext(project_root))
        session.open_project(authoring)
        window = EditorWindow(session)
        window.show()
        _process_events(app)
        handle = window.windowHandle()
        if handle is None or not handle.isExposed() or int(window.winId()) == 0:
            raise RuntimeError("top-level editor window was not exposed as a real native window")

        for width, height in REQUIRED_SIZES:
            window.resize(width, height)
            _process_events(app)
            for index in range(4):
                window.activity_sidebar.show_view(index)
                _process_events(app, 1)
                if window.activity_sidebar.stack.currentIndex() != index:
                    raise RuntimeError(f"activity view {index} did not become active")
            window.central_groups.setSizes([3, 2])
            _process_events(app)
            if window.editor_group.width() <= 0 or window.game_group.width() <= 0:
                raise RuntimeError(f"central groups collapsed at {width}x{height}")

            window.editor_group.close_group()
            _process_events(app, 1)
            window.show_editor_action.trigger()
            _process_events(app)
            window.game_group.close_group()
            _process_events(app, 1)
            window.show_game_action.trigger()
            _process_events(app)
            if not window.editor_group.isVisible() or not window.game_group.isVisible():
                raise RuntimeError(f"central group restore failed at {width}x{height}")
            if not window.inspector_dock.isVisible():
                raise RuntimeError(f"Inspector disappeared at {width}x{height}")
            if not window.timeline_dock.isVisible():
                raise RuntimeError(f"permanent Timeline disappeared at {width}x{height}")
            observations.append(
                {
                    "size": [width, height],
                    "editor_width": window.editor_group.width(),
                    "game_width": window.game_group.width(),
                    "timeline_height": window.timeline_dock.height(),
                }
            )
        window.close()
        _process_events(app)

    return {
        "ok": True,
        "qt_platform": app.platformName(),
        "native_window": True,
        "sizes": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the real Windows CD5 editor layout")
    parser.parse_args()
    try:
        result = verify_native_layout()
    except Exception as exc:
        print(f"CD5 NATIVE FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

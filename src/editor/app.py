"""PySTG editor bootstrap and compatibility exports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.core.project_context import ProjectContext
from src.qt_compat.QtGui import QFont
from src.qt_compat.QtWidgets import QApplication

from .main_window_support import APP_NAME, build_preview_command
from .panels.inspector_panel import InspectorPanel
from .panels.scene_view import NodeGraphicsItem, SceneViewport
from .shell.main_window import EditorMainWindow

__all__ = [
    "EditorMainWindow",
    "InspectorPanel",
    "NodeGraphicsItem",
    "SceneViewport",
    "build_preview_command",
    "create_window",
    "main",
]


def create_window(project: ProjectContext) -> EditorMainWindow:
    return EditorMainWindow(project)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--project", type=Path, help="PySTG project root")
    args, qt_args = parser.parse_known_args(argv)
    project = ProjectContext.discover(args.project or Path.cwd())
    project.activate()

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("PySTG")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    window = create_window(project)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

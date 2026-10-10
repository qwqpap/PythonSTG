"""Command-line entry point for the single-project Qt editor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from src.qt_compat.QtWidgets import QApplication
from src.qt_compat.QtGui import QFont

from .theme import STYLESHEET
from .window import EditorWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PySTG 代码驱动关卡编辑器")
    parser.add_argument("project", nargs="?", type=Path, help="声明式 Python 工程目录")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("PySTG 关卡编辑器")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    # 应用级样式表：让对话框、菜单、工具提示等顶层弹窗与主窗口共用同一套 token。
    app.setStyleSheet(STYLESHEET)
    window = EditorWindow()
    if arguments.project is not None:
        window.open_project(arguments.project)
    window.show()
    return app.exec()


__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())

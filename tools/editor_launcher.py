"""
pystg 编辑器启动器

统一入口，可启动以下编辑器:
  1. 弹幕别名管理器 — 管理弹幕类型/颜色→精灵的映射关系
  2. 纹理资产编辑器 — 编辑精灵图集、裁切区域、动画帧
  3. 自机编辑器     — 编辑自机动画、射击、子机配置

使用:
    python tools/editor_launcher.py
"""

import sys
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QStatusBar, QGridLayout
)
from PyQt5.QtCore import Qt, QSize, QProcess
from PyQt5.QtGui import QFont, QColor, QPainter, QPen

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"


# ═══════════════════════════════════════════════════════════════
# 工具卡片
# ═══════════════════════════════════════════════════════════════

class ToolCard(QFrame):
    """一个编辑器启动卡片。"""

    def __init__(self, title: str, desc: str, icon_text: str,
                 accent_color: str, parent=None):
        super().__init__(parent)
        self.title = title
        self._accent = QColor(accent_color)
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(280, 160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # 图标 + 标题
        header = QHBoxLayout()
        icon_lbl = QLabel(icon_text)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 24))
        icon_lbl.setStyleSheet("background: transparent;")
        header.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Microsoft YaHei UI", 13, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        header.addWidget(title_lbl)
        header.addStretch()
        layout.addLayout(header)

        # 描述
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setFont(QFont("Microsoft YaHei UI", 9))
        desc_lbl.setStyleSheet("color: #a6adc8; background: transparent;")
        layout.addWidget(desc_lbl)
        layout.addStretch()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(40, 42, 54) if self._hover else QColor(30, 30, 46)
        border = self._accent if self._hover else QColor(69, 71, 90)
        p.setBrush(bg)
        p.setPen(QPen(border, 2 if self._hover else 1))
        p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 8, 8)
        p.end()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()


class EditorLauncher(QMainWindow):
    """编辑器启动器主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("pystg 编辑器工具箱")
        self.setFixedSize(900, 420)
        self._processes: list = []

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 12)

        # 标题
        title = QLabel("pystg 编辑器工具箱")
        title.setFont(QFont("Microsoft YaHei UI", 18, QFont.Bold))
        title.setStyleSheet("color: #cdd6f4; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("选择一个编辑器启动")
        subtitle.setFont(QFont("Microsoft YaHei UI", 10))
        subtitle.setStyleSheet("color: #6c7086; background: transparent;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        # 卡片网格
        cards_layout = QGridLayout()
        cards_layout.setSpacing(16)

        # 弹幕别名管理器
        card1 = ToolCard(
            "弹幕别名", "管理弹幕类型和颜色到精灵的映射关系",
            "🎯", "#f38ba8")
        card1.mousePressEvent = lambda e: self._launch("bullet/bullet_alias_manager.py")
        cards_layout.addWidget(card1, 0, 0)

        # 纹理资产编辑器
        card2 = ToolCard(
            "纹理编辑", "编辑精灵图集裁切区域、动画帧、激光配置",
            "🖼️", "#89b4fa")
        card2.mousePressEvent = lambda e: self._launch("asset/asset_manager_qt.py")
        cards_layout.addWidget(card2, 0, 1)

        # 自机编辑器
        card3 = ToolCard(
            "自机编辑", "编辑自机动画、射击类型、子机配置",
            "✈️", "#a6e3a1")
        card3.mousePressEvent = lambda e: self._launch("player/player_editor.py")
        cards_layout.addWidget(card3, 0, 2)

        # 敌人别名管理器
        card4 = ToolCard(
            "敌人别名", "管理敌人贴图和别名映射关系",
            "👾", "#fab387")
        card4.mousePressEvent = lambda e: self._launch("enemy/enemy_alias_manager.py")
        cards_layout.addWidget(card4, 1, 0)

        layout.addLayout(cards_layout)
        layout.addStretch()

        # 状态栏
        self._status = QStatusBar()
        self.setStatusBar(self._status)

        self._apply_theme()

    def _launch(self, script_name: str):
        script = TOOLS_DIR / script_name
        if not script.exists():
            self._status.showMessage(f"❌ 找不到 {script_name}", 5000)
            return

        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments([str(script)])
        process.setWorkingDirectory(str(PROJECT_ROOT))
        process.start()
        self._processes.append(process)
        self._status.showMessage(f"🚀 已启动 {script_name}", 3000)

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow { background: #1e1e2e; }
            QStatusBar { background: #181825; color: #a6adc8; }
        """)

    def closeEvent(self, event):
        for proc in self._processes:
            if proc.state() == QProcess.Running:
                proc.terminate()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    window = EditorLauncher()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

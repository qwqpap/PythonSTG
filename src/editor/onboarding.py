"""Small, presentation-only entry and next-step guidance for authors."""

from __future__ import annotations

from src.qt_compat.QtCore import Signal
from src.qt_compat.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _wrapped_label(text: str, parent: QWidget, *, muted: bool = False) -> QLabel:
    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    if muted:
        label.setStyleSheet("color: #8b949e;")
    return label


class WelcomePanel(QWidget):
    """Give a first-time author two clear ways into the editor."""

    new_project_requested = Signal()
    open_project_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("authoring_welcome")
        self.setMinimumWidth(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        layout.addStretch(1)

        title = _wrapped_label("做第一段弹幕", self)
        title.setStyleSheet("font-size: 22px; font-weight: 600; color: #f0f6fc;")
        layout.addWidget(title)
        layout.addWidget(_wrapped_label(
            "先从一段能运行的示例开始。修改参数、运行看看，再学习怎样组合步骤。",
            self,
        ))

        self.new_project_button = QPushButton("新建工程 · 从示例开始", self)
        self.new_project_button.setObjectName("welcome_new_project")
        self.new_project_button.setToolTip("创建带可运行弹幕的新工程，所有步骤都能继续修改")
        self.new_project_button.setStyleSheet(
            "background: #1f4a73; border-color: #58a6e7; padding: 10px 12px;"
        )
        self.new_project_button.clicked.connect(self.new_project_requested)
        layout.addWidget(self.new_project_button)

        self.open_project_button = QPushButton("打开已有工程…", self)
        self.open_project_button.setObjectName("welcome_open_project")
        self.open_project_button.clicked.connect(self.open_project_requested)
        layout.addWidget(self.open_project_button)

        layout.addWidget(_wrapped_label(
            "1. 新建工程，打开示例中的弹幕。\n"
            "2. 在右侧属性里修改子弹数量、速度或颜色。\n"
            "3. 点击运行（F5），看效果后继续调整。",
            self,
            muted=True,
        ))
        layout.addWidget(_wrapped_label(
            "关卡安排出场顺序；波次安排一组敌人；敌人的步骤决定移动和发射。"
            "这些内容已经在示例中接好，第一次无需从空白搭建。",
            self,
            muted=True,
        ))
        layout.addStretch(1)


class AuthoringGuide(QWidget):
    """A reusable description and up to three existing editor actions."""

    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("authoring_guide")
        self.setMinimumWidth(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(5)
        self.title_label = _wrapped_label("", self)
        self.title_label.setObjectName("authoring_guide_title")
        self.title_label.setStyleSheet("color: #f0f6fc; font-weight: 600;")
        self.description_label = _wrapped_label("", self, muted=True)
        self.description_label.setObjectName("authoring_guide_description")
        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)

        action_row = QWidget(self)
        action_row.setMinimumWidth(0)
        action_layout = QGridLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(5)
        self.buttons: tuple[QPushButton, ...] = tuple(
            QPushButton(action_row) for _ in range(3)
        )
        self._action_keys = ["", "", ""]
        self._busy = False
        for index, button in enumerate(self.buttons):
            button.setObjectName(f"authoring_guide_action_{index + 1}")
            button.setMinimumWidth(0)
            button.clicked.connect(lambda _checked=False, slot=index: self._activate(slot))
            action_layout.addWidget(button, 0, index)
            button.hide()
        layout.addWidget(action_row)
        self.action_row = action_row
        self._action_layout = action_layout
        self.hide()

    def configure(
        self,
        title: str,
        description: str,
        actions: tuple[tuple[str, str], ...],
    ) -> None:
        """Update existing controls; this widget owns no authoring state."""

        visible_actions = actions[:3]
        self.title_label.setText(title)
        self.title_label.setVisible(bool(title))
        self.description_label.setText(description)
        self.description_label.setVisible(bool(description))
        for index, button in enumerate(self.buttons):
            if index < len(visible_actions):
                key, label = visible_actions[index]
                self._action_keys[index] = key
                button.setText(label)
                button.setToolTip(label)
                button.setEnabled(not self._busy)
                button.show()
            else:
                self._action_keys[index] = ""
                button.hide()
        self.action_row.setVisible(bool(visible_actions))
        self.setVisible(bool(title or description or visible_actions))
        self._layout_actions()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in self.buttons:
            button.setEnabled(not busy)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_actions()

    def _layout_actions(self) -> None:
        visible = [button for button, key in zip(self.buttons, self._action_keys) if key]
        available = max(0, self.width() - 16)
        columns = max(1, len(visible))
        while columns > 1 and (
            sum(button.sizeHint().width() for button in visible[:columns])
            + 5 * (columns - 1) > available
        ):
            columns -= 1
        for index, button in enumerate(visible):
            self._action_layout.addWidget(button, index // columns, index % columns)

    def _activate(self, index: int) -> None:
        key = self._action_keys[index]
        if key:
            self.action_requested.emit(key)


__all__ = ["AuthoringGuide", "WelcomePanel"]

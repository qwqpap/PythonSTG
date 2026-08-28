"""Activity Bar and read-only project resource lists."""

from __future__ import annotations

from pathlib import Path

from src.qt_compat.QtCore import QMimeData, Qt, Signal
from src.qt_compat.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


RESOURCE_MIME = "application/x-pystg-resource"
_ROLE_URI = int(Qt.ItemDataRole.UserRole)


class ResourceListWidget(QListWidget):
    """Stable project-relative asset list with a single drag payload."""

    resource_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.itemDoubleClicked.connect(
            lambda item: self.resource_activated.emit(str(item.data(_ROLE_URI)))
        )

    def set_resources(self, resources: tuple[str, ...], *, project_root: Path) -> None:
        self.clear()
        for uri in resources:
            item = QListWidgetItem(uri.removeprefix("res://"))
            item.setData(_ROLE_URI, uri)
            path = project_root / uri.removeprefix("res://").split("#", 1)[0]
            if not path.exists():
                item.setText(f"{item.text()}  [缺失]")
                item.setForeground(Qt.GlobalColor.red)
            self.addItem(item)

    def mimeTypes(self) -> list[str]:
        return [RESOURCE_MIME]

    def mimeData(self, items) -> QMimeData:
        data = QMimeData()
        if items:
            data.setData(RESOURCE_MIME, str(items[0].data(_ROLE_URI)).encode("utf-8"))
        return data


class ActivitySidebar(QWidget):
    """Four fixed views selected from a narrow vertical Activity Bar."""

    def __init__(
        self,
        program_view: QWidget,
        file_view: QWidget,
        global_assets: QWidget,
        stage_assets: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("activity_sidebar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QWidget(self)
        bar.setObjectName("activity_bar")
        bar_layout = QVBoxLayout(bar)
        bar_layout.setContentsMargins(2, 2, 2, 2)
        self.stack = QStackedWidget(self)
        self.stack.setObjectName("activity_stack")
        views = (
            ("程序", program_view),
            ("文件", file_view),
            ("资产", global_assets),
            ("关卡", stage_assets),
        )
        group = QButtonGroup(self)
        group.setExclusive(True)
        self.buttons: list[QToolButton] = []
        for index, (label, view) in enumerate(views):
            button = QToolButton(bar)
            button.setText(label)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.clicked.connect(
                lambda _checked=False, value=index: self.stack.setCurrentIndex(value)
            )
            group.addButton(button)
            bar_layout.addWidget(button)
            self.stack.addWidget(_titled_view(label, view))
            self.buttons.append(button)
        bar_layout.addStretch(1)
        self.buttons[0].setChecked(True)
        layout.addWidget(bar)
        layout.addWidget(self.stack, 1)

    def show_view(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.buttons[index].setChecked(True)


def _titled_view(title: str, view: QWidget) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(4, 4, 4, 4)
    label = QLabel(title, container)
    label.setStyleSheet("font-weight: bold;")
    layout.addWidget(label)
    layout.addWidget(view, 1)
    return container


__all__ = ["ActivitySidebar", "RESOURCE_MIME", "ResourceListWidget"]

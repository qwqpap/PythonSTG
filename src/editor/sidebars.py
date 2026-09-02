"""Activity Bar and read-only project resource lists."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from src.qt_compat.QtCore import QEvent, QMimeData, Qt, Signal
from src.qt_compat.QtWidgets import (
    QButtonGroup,
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


RESOURCE_MIME = "application/x-pystg-resource"
UNIT_REFERENCE_MIME = "application/x-pystg-unit-ref"
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


class UnitTreeWidget(QTreeWidget):
    """Program-structure tree that can drag only a logical-unit identity."""

    unit_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.itemDoubleClicked.connect(
            lambda item, _column: self._emit_unit(item)
        )

    def mimeTypes(self) -> list[str]:
        return [UNIT_REFERENCE_MIME]

    def mimeData(self, items) -> QMimeData:
        data = QMimeData()
        if items:
            unit_id = items[0].data(0, _ROLE_URI)
            if unit_id:
                data.setData(UNIT_REFERENCE_MIME, str(unit_id).encode("utf-8"))
        return data

    def _emit_unit(self, item: QTreeWidgetItem) -> None:
        unit_id = item.data(0, _ROLE_URI)
        if unit_id:
            self.unit_activated.emit(str(unit_id))


class UnitReferenceListWidget(QListWidget):
    """A specialised Project/Boss Ref list with no local authoring state.

    The list paints a projection supplied by ``EditorSession``.  On every drop
    it emits only a unit ID plus the requested insertion index; the window
    validates and commits a single undoable headless mutation before refreshing
    this projection again.
    """

    reference_dropped = Signal(str, int)
    unit_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self._allowed_ids: set[str] = set()
        self.itemDoubleClicked.connect(
            lambda item: self._activate(item)
        )

    def set_references(
        self,
        references: Sequence[tuple[str, str]],
        *,
        allowed_ids: Iterable[str],
    ) -> None:
        self._allowed_ids = {str(item) for item in allowed_ids}
        self.blockSignals(True)
        try:
            self.clear()
            for index, (unit_id, label) in enumerate(references, start=1):
                item = QListWidgetItem(f"{index}. {label}")
                item.setData(_ROLE_URI, unit_id)
                self.addItem(item)
        finally:
            self.blockSignals(False)

    def mimeTypes(self) -> list[str]:
        return [UNIT_REFERENCE_MIME]

    def mimeData(self, items) -> QMimeData:
        data = QMimeData()
        if items:
            unit_id = items[0].data(_ROLE_URI)
            if unit_id:
                data.setData(UNIT_REFERENCE_MIME, str(unit_id).encode("utf-8"))
        return data

    def dragEnterEvent(self, event) -> None:
        if self._accepts(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._accepts(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        unit_id = self._unit_id_from_mime(event.mimeData())
        if unit_id is None or unit_id not in self._allowed_ids:
            event.ignore()
            return
        self.reference_dropped.emit(unit_id, self._drop_index(event.position().toPoint()))
        event.acceptProposedAction()

    def viewportEvent(self, event) -> bool:
        """Handle real QListWidget viewport drops as well as direct Qt events."""

        if event.type() == QEvent.Type.DragEnter:
            self.dragEnterEvent(event)
            return event.isAccepted()
        if event.type() == QEvent.Type.DragMove:
            self.dragMoveEvent(event)
            return event.isAccepted()
        if event.type() == QEvent.Type.Drop:
            self.dropEvent(event)
            return event.isAccepted()
        return super().viewportEvent(event)

    def _accepts(self, mime: QMimeData) -> bool:
        unit_id = self._unit_id_from_mime(mime)
        return unit_id is not None and unit_id in self._allowed_ids

    @staticmethod
    def _unit_id_from_mime(mime: QMimeData) -> str | None:
        if not mime.hasFormat(UNIT_REFERENCE_MIME):
            return None
        value = bytes(mime.data(UNIT_REFERENCE_MIME)).decode("utf-8").strip()
        return value or None

    def _drop_index(self, position) -> int:
        item = self.itemAt(position)
        if item is None:
            return self.count()
        index = self.row(item)
        if position.y() > self.visualItemRect(item).center().y():
            index += 1
        return index

    def _activate(self, item: QListWidgetItem) -> None:
        unit_id = item.data(_ROLE_URI)
        if unit_id:
            self.unit_activated.emit(str(unit_id))


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


__all__ = [
    "ActivitySidebar",
    "RESOURCE_MIME",
    "ResourceListWidget",
    "UNIT_REFERENCE_MIME",
    "UnitReferenceListWidget",
    "UnitTreeWidget",
]

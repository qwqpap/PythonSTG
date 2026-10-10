"""Activity Bar and read-only project resource lists."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

from src.qt_compat.QtCore import QEvent, QMimeData, QSize, Qt, Signal
from src.qt_compat.QtWidgets import (
    QButtonGroup,
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
_ROLE_RESOURCE_KIND = _ROLE_URI + 1
_ROLE_RESOURCE_SEARCH = _ROLE_URI + 2


def _resource_kind(uri: str) -> str:
    suffix = PurePosixPath(uri.removeprefix("res://").split("#", 1)[0]).suffix.lower()
    if suffix in {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}:
        return "图片"
    if suffix in {".flac", ".mp3", ".ogg", ".wav"}:
        return "音频"
    if suffix in {".otf", ".ttf"}:
        return "字体"
    return "数据"


class ResourceListWidget(QListWidget):
    """Stable project-relative asset list with a single drag payload."""

    resource_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._resource_signature: tuple[tuple[str, ...], Path] | None = None
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setUniformItemSizes(True)
        self.itemDoubleClicked.connect(
            lambda item: self.resource_activated.emit(str(item.data(_ROLE_URI)))
        )

    def set_resources(self, resources: tuple[str, ...], *, project_root: Path) -> None:
        signature = (resources, project_root.resolve())
        if signature == self._resource_signature:
            return
        self.clear()
        for uri in resources:
            relative = uri.removeprefix("res://")
            relative_path, _, fragment = relative.partition("#")
            filename = PurePosixPath(relative_path).name
            label = f"{filename}#{fragment}" if fragment else filename
            item = QListWidgetItem(label)
            item.setData(_ROLE_URI, uri)
            kind = _resource_kind(uri)
            item.setData(_ROLE_RESOURCE_KIND, kind)
            item.setData(_ROLE_RESOURCE_SEARCH, relative.casefold())
            item.setToolTip(f"{kind}\n位置：{relative_path}\n引用：{uri}")
            item.setSizeHint(QSize(0, 30))
            path = project_root / relative_path
            if not path.exists():
                item.setText(f"{item.text()}（缺失）")
                item.setToolTip(f"文件不存在\n位置：{relative_path}\n引用：{uri}")
                item.setForeground(Qt.GlobalColor.red)
            self.addItem(item)
        self._resource_signature = signature

    def clear(self) -> None:
        self._resource_signature = None
        super().clear()

    def mimeTypes(self) -> list[str]:
        return [RESOURCE_MIME]

    def mimeData(self, items) -> QMimeData:
        data = QMimeData()
        if items:
            data.setData(RESOURCE_MIME, str(items[0].data(_ROLE_URI)).encode("utf-8"))
        return data


class ResourceBrowser(QWidget):
    """Searchable read-only resource projection; drag keeps the original URI."""

    resource_activated = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        scope: str = "project",
    ) -> None:
        super().__init__(parent)
        self._scope = scope
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        self.hint = QLabel(
            "本关引用的资源，可拖到参数中"
            if scope == "stage"
            else "游戏资源，可拖到参数或步骤中",
            self,
        )
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.search = QLineEdit(self)
        self.search.setObjectName("resource_search")
        self.search.setPlaceholderText("搜索文件名或位置")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_resources)
        layout.addWidget(self.search)
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        self.category = QComboBox(self)
        self.category.setObjectName("resource_category")
        self.category.addItem("全部类型", "")
        for kind in ("图片", "音频", "字体", "数据"):
            self.category.addItem(kind, kind)
        self.category.currentIndexChanged.connect(self._filter_resources)
        filter_row.addWidget(self.category)
        filter_row.addStretch(1)
        self.count_label = QLabel(self)
        filter_row.addWidget(self.count_label)
        layout.addLayout(filter_row)
        self.resource_list = ResourceListWidget(self)
        self.resource_list.setObjectName("resource_files")
        self.resource_list.resource_activated.connect(self.resource_activated.emit)
        self.empty_label = QLabel(self)
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.content_stack = QStackedWidget(self)
        self.content_stack.addWidget(self.resource_list)
        self.content_stack.addWidget(self.empty_label)
        layout.addWidget(self.content_stack, 1)
        self._filter_resources()

    def set_resources(self, resources: tuple[str, ...], *, project_root: Path) -> None:
        self.resource_list.set_resources(resources, project_root=project_root)
        self._filter_resources()

    def clear(self) -> None:
        self.resource_list.clear()
        self._filter_resources()

    def _filter_resources(self, *_args) -> None:
        query = self.search.text().strip().casefold()
        kind = self.category.currentData()
        visible_count = 0
        total_count = self.resource_list.count()
        for index in range(total_count):
            item = self.resource_list.item(index)
            visible = (
                (not query or query in str(item.data(_ROLE_RESOURCE_SEARCH)))
                and (not kind or kind == item.data(_ROLE_RESOURCE_KIND))
            )
            item.setHidden(not visible)
            visible_count += int(visible)
        self.count_label.setText(
            f"{visible_count} / {total_count} 项"
            if query or kind
            else f"{total_count} 项"
        )
        if visible_count:
            self.content_stack.setCurrentWidget(self.resource_list)
        else:
            self.empty_label.setText(
                "没有匹配的资源，请调整搜索或类型。"
                if total_count
                else (
                    "本关尚未引用资源。\n设置背景、音乐或图片后，会显示在这里。"
                    if self._scope == "stage"
                    else "未找到游戏资源。\n将图片、音频、字体或游戏数据放入工程，然后刷新资源。"
                )
            )
            self.content_stack.setCurrentWidget(self.empty_label)


class UnitTreeWidget(QTreeWidget):
    """Program-structure tree that can drag only a logical-unit identity."""

    unit_activated = Signal(str)
    drag_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        # itemClicked is emitted on release, not when a drag begins.  Keeping
        # navigation off mouse-down preserves the current ProgramFlow while a
        # different logical unit is being dragged into it.
        self.itemClicked.connect(
            lambda item, _column: self._emit_unit(item)
        )
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

    def keyPressEvent(self, event) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            item = self.currentItem()
            if item is not None:
                self._emit_unit(item)
                event.accept()
                return
        super().keyPressEvent(event)

    def startDrag(self, supported_actions) -> None:
        try:
            super().startDrag(supported_actions)
        finally:
            self.drag_finished.emit()


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
    """Compact tabs for content, source files, and project resources."""

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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        bar = QWidget(self)
        bar.setObjectName("activity_bar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(2, 2, 2, 2)
        bar_layout.setSpacing(0)
        self.stack = QStackedWidget(self)
        self.stack.setObjectName("activity_stack")
        views = (
            ("内容", program_view),
            ("源码", file_view),
            ("资源", global_assets),
            ("本关", stage_assets),
        )
        group = QButtonGroup(self)
        group.setExclusive(True)
        self.buttons: list[QToolButton] = []
        for index, (label, view) in enumerate(views):
            button = QToolButton(bar)
            button.setText(label)
            button.setCheckable(True)
            button.setToolTip(("这一关的内容与全部内容", "查看作者 Python 源码（只读）", "游戏资源：图片、音频、字体和数据", "当前关卡引用的资源")[index])
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.clicked.connect(
                lambda _checked=False, value=index: self.stack.setCurrentIndex(value)
            )
            group.addButton(button)
            bar_layout.addWidget(button, 1)
            self.stack.addWidget(view)
            self.buttons.append(button)
        self.buttons[0].setChecked(True)
        layout.addWidget(bar)
        layout.addWidget(self.stack, 1)

    def show_view(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.buttons[index].setChecked(True)


__all__ = [
    "ActivitySidebar",
    "RESOURCE_MIME",
    "ResourceBrowser",
    "ResourceListWidget",
    "UNIT_REFERENCE_MIME",
    "UnitReferenceListWidget",
    "UnitTreeWidget",
]

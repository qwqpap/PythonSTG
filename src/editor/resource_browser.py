"""Native resource browser panel for the unified editor workbench."""

from __future__ import annotations

import json
from pathlib import Path

from src.qt_compat.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QMimeData,
    QSize,
    QSortFilterProxyModel,
    Qt,
    pyqtSignal,
)
from src.qt_compat.QtGui import QColor, QFont, QPainter, QPixmap
from src.qt_compat.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.project_context import ProjectContext

from .asset_index import AssetIndex, AssetRecord


RESOURCE_MIME_TYPE = "application/x-pystg-resource"
RECORD_ROLE = Qt.UserRole + 1


class ThumbnailProvider:
    """Create and cache thumbnails for files and atlas subresources."""

    def __init__(self, size: int = 80):
        self.size = size
        self._cache: dict[str, QPixmap] = {}

    def clear(self) -> None:
        self._cache.clear()

    def thumbnail(self, record: AssetRecord) -> QPixmap:
        cached = self._cache.get(record.uri)
        if cached is not None:
            return cached

        pixmap = self._load_preview(record)
        if pixmap.isNull():
            pixmap = self._placeholder(record.kind)
        else:
            pixmap = pixmap.scaled(
                self.size,
                self.size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        canvas = QPixmap(self.size, self.size)
        canvas.fill(QColor("#141720"))
        painter = QPainter(canvas)
        x = (self.size - pixmap.width()) // 2
        y = (self.size - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)
        painter.end()
        self._cache[record.uri] = canvas
        return canvas

    @staticmethod
    def _load_preview(record: AssetRecord) -> QPixmap:
        if record.preview_path is None or not record.preview_path.is_file():
            return QPixmap()
        pixmap = QPixmap(str(record.preview_path))
        if pixmap.isNull() or record.rect is None:
            return pixmap
        x, y, width, height = record.rect
        clipped = pixmap.rect().intersected(
            pixmap.rect().adjusted(
                x,
                y,
                x + width - pixmap.width(),
                y + height - pixmap.height(),
            )
        )
        if clipped.isEmpty():
            return QPixmap()
        return pixmap.copy(clipped)

    def _placeholder(self, kind: str) -> QPixmap:
        colors = {
            "audio": "#8fcf72",
            "font": "#edb95f",
            "shader": "#c792ea",
            "scene": "#82aaff",
            "pattern": "#c792ea",
            "ui": "#89ddff",
            "background": "#f0c674",
            "resource": "#a7b0c0",
            "script": "#f78c6c",
            "json": "#89ddff",
            "text": "#a7b0c0",
            "animation": "#ffcb6b",
        }
        labels = {
            "audio": "SFX",
            "font": "Aa",
            "shader": "FX",
            "scene": "SCN",
            "pattern": "PAT",
            "ui": "UI",
            "background": "BG",
            "resource": "RES",
            "script": "PY",
            "json": "{}",
            "text": "TXT",
            "animation": "ANI",
        }
        pixmap = QPixmap(self.size, self.size)
        pixmap.fill(QColor("#202532"))
        painter = QPainter(pixmap)
        painter.setPen(QColor(colors.get(kind, "#9aa4b2")))
        painter.setFont(QFont("Microsoft YaHei UI", 13, QFont.Bold))
        painter.drawRoundedRect(8, 8, self.size - 16, self.size - 16, 7, 7)
        painter.drawText(
            pixmap.rect(),
            Qt.AlignCenter,
            labels.get(kind, kind[:3].upper()),
        )
        painter.end()
        return pixmap


class AssetListModel(QAbstractListModel):
    def __init__(
        self,
        records: tuple[AssetRecord, ...] = (),
        thumbnails: ThumbnailProvider | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.records = records
        self.thumbnails = thumbnails or ThumbnailProvider()

    def set_records(self, records: tuple[AssetRecord, ...]) -> None:
        self.beginResetModel()
        self.records = records
        self.thumbnails.clear()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.records)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        record = self.records[index.row()]
        if role == Qt.DisplayRole:
            return record.name
        if role == Qt.DecorationRole:
            return self.thumbnails.thumbnail(record)
        if role == Qt.ToolTipRole:
            return f"{record.kind}\n{record.resource_value}"
        if role == RECORD_ROLE:
            return record
        if role == Qt.SizeHintRole:
            return QSize(112, 116)
        return None

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        return flags | Qt.ItemIsDragEnabled if index.isValid() else flags

    def mimeTypes(self) -> list[str]:
        return [RESOURCE_MIME_TYPE]

    def mimeData(self, indexes) -> QMimeData:
        mime = QMimeData()
        if not indexes:
            return mime
        record = self.data(indexes[0], RECORD_ROLE)
        if record is None:
            return mime
        payload = {
            "uri": record.uri,
            "kind": record.kind,
            "name": record.name,
            "resource_value": record.resource_value,
        }
        mime.setData(
            RESOURCE_MIME_TYPE,
            QByteArray(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
        )
        return mime

    def supportedDragActions(self):
        return Qt.CopyAction


class AssetFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._query = ""
        self._kind = "all"
        self._folder = ""
        self.setDynamicSortFilter(True)

    def set_query(self, value: str) -> None:
        self._query = value.strip().casefold()
        self.invalidateFilter()

    def set_kind(self, value: str) -> None:
        self._kind = value
        self.invalidateFilter()

    def set_folder(self, value: str) -> None:
        self._folder = value.strip("/")
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        record = model.data(index, RECORD_ROLE)
        if record is None:
            return False
        if self._kind != "all" and record.kind != self._kind:
            return False
        if self._folder and not (
            record.project_path == self._folder
            or record.project_path.startswith(f"{self._folder}/")
        ):
            return False
        if self._query:
            haystack = (
                f"{record.name} {record.project_path} "
                f"{record.kind} {record.subresource or ''}"
            ).casefold()
            if self._query not in haystack:
                return False
        return True


class ResourceBrowserPanel(QWidget):
    resourceSelected = pyqtSignal(object)
    resourceActivated = pyqtSignal(object)

    def __init__(self, project: ProjectContext, parent=None):
        super().__init__(parent)
        self.project = project
        self.index = AssetIndex(project)
        self.thumbnails = ThumbnailProvider()
        self.model = AssetListModel(thumbnails=self.thumbnails)
        self.proxy = AssetFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("assetSearch")
        self.search.setPlaceholderText("Search resources…")
        self.search.textChanged.connect(self.proxy.set_query)
        self.kind_filter = QComboBox()
        self.kind_filter.setObjectName("assetKindFilter")
        self.kind_filter.addItem("All types", "all")
        for kind in (
            "image",
            "sprite",
            "animation",
            "audio",
            "scene",
            "pattern",
            "ui",
            "background",
            "resource",
            "script",
            "json",
            "font",
            "shader",
            "text",
        ):
            self.kind_filter.addItem(kind.title(), kind)
        self.kind_filter.currentIndexChanged.connect(
            lambda: self.proxy.set_kind(
                str(self.kind_filter.currentData() or "all")
            )
        )
        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("assetRefresh")
        refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.search, 1)
        controls.addWidget(self.kind_filter)
        controls.addWidget(refresh_button)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Horizontal)
        self.folder_tree = QTreeWidget()
        self.folder_tree.setObjectName("assetFolders")
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setMinimumWidth(150)
        self.folder_tree.setMaximumWidth(280)
        self.folder_tree.currentItemChanged.connect(self._folder_changed)
        splitter.addWidget(self.folder_tree)

        self.asset_view = QListView()
        self.asset_view.setObjectName("assetList")
        self.asset_view.setModel(self.proxy)
        self.asset_view.setViewMode(QListView.IconMode)
        self.asset_view.setResizeMode(QListView.Adjust)
        self.asset_view.setMovement(QListView.Static)
        self.asset_view.setWrapping(True)
        self.asset_view.setWordWrap(True)
        self.asset_view.setSpacing(5)
        self.asset_view.setIconSize(QSize(80, 80))
        self.asset_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.asset_view.setDragEnabled(True)
        self.asset_view.setDragDropMode(QAbstractItemView.DragOnly)
        self.asset_view.setDefaultDropAction(Qt.CopyAction)
        self.asset_view.selectionModel().currentChanged.connect(
            self._selection_changed
        )
        self.asset_view.doubleClicked.connect(self._activated)
        splitter.addWidget(self.asset_view)

        detail = QWidget()
        detail.setMinimumWidth(190)
        detail.setMaximumWidth(320)
        detail_layout = QVBoxLayout(detail)
        self.preview = QLabel("Select a resource")
        self.preview.setObjectName("assetPreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(170, 150)
        self.preview.setStyleSheet(
            "background:#141720; border:1px solid #353b49;"
        )
        self.detail_title = QLabel("")
        self.detail_title.setWordWrap(True)
        self.detail_text = QLabel("")
        self.detail_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_text.setWordWrap(True)
        detail_layout.addWidget(self.preview)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_text)
        detail_layout.addStretch()
        splitter.addWidget(detail)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([180, 700, 220])
        layout.addWidget(splitter, 1)

        self.summary = QLabel("")
        self.summary.setObjectName("assetSummary")
        layout.addWidget(self.summary)

    def refresh(self) -> None:
        records = self.index.scan()
        self.model.set_records(records)
        self._populate_folders(records)
        message = f"{len(records)} resources"
        if self.index.errors:
            message += f" · {len(self.index.errors)} invalid JSON files skipped"
        self.summary.setText(message)
        self._clear_details()

    def _populate_folders(self, records: tuple[AssetRecord, ...]) -> None:
        self.folder_tree.blockSignals(True)
        self.folder_tree.clear()
        all_item = QTreeWidgetItem(["All resources"])
        all_item.setData(0, Qt.UserRole, "")
        self.folder_tree.addTopLevelItem(all_item)
        nodes: dict[str, QTreeWidgetItem] = {"": all_item}
        folders = sorted(
            {
                part
                for record in records
                for part in self._folder_ancestors(record.folder)
            }
        )
        for folder in folders:
            parent_path = Path(folder).parent.as_posix()
            if parent_path == ".":
                parent_path = ""
            parent = nodes.get(parent_path, all_item)
            item = QTreeWidgetItem([Path(folder).name])
            item.setData(0, Qt.UserRole, folder)
            parent.addChild(item)
            nodes[folder] = item
        all_item.setExpanded(True)
        self.folder_tree.setCurrentItem(all_item)
        self.folder_tree.blockSignals(False)
        self.proxy.set_folder("")

    @staticmethod
    def _folder_ancestors(folder: str) -> tuple[str, ...]:
        if not folder or folder == ".":
            return ()
        parts = Path(folder).parts
        return tuple(Path(*parts[:index]).as_posix() for index in range(1, len(parts) + 1))

    def _folder_changed(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        del previous
        self.proxy.set_folder(
            str(current.data(0, Qt.UserRole) or "") if current else ""
        )

    def _record(self, proxy_index: QModelIndex) -> AssetRecord | None:
        if not proxy_index.isValid():
            return None
        return self.proxy.data(proxy_index, RECORD_ROLE)

    def _selection_changed(
        self,
        current: QModelIndex,
        previous: QModelIndex,
    ) -> None:
        del previous
        record = self._record(current)
        if record is None:
            self._clear_details()
            return
        self._show_details(record)
        self.resourceSelected.emit(record)

    def _activated(self, index: QModelIndex) -> None:
        record = self._record(index)
        if record is not None:
            self.resourceActivated.emit(record)

    def _show_details(self, record: AssetRecord) -> None:
        pixmap = self.thumbnails.thumbnail(record).scaled(
            150,
            150,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.preview.setPixmap(pixmap)
        self.detail_title.setText(f"<b>{record.name}</b>")
        lines = [
            f"Type: {record.kind}",
            f"Path: {record.resource_value}",
        ]
        if record.rect:
            lines.append("Rect: {}, {}, {}, {}".format(*record.rect))
        if record.metadata.get("size") is not None:
            lines.append(f"Size: {record.metadata['size']} bytes")
        if record.metadata.get("frames") is not None:
            lines.append(f"Frames: {record.metadata['frames']}")
        if record.metadata.get("fps") is not None:
            lines.append(f"FPS: {record.metadata['fps']}")
        self.detail_text.setText("\n".join(lines))

    def _clear_details(self) -> None:
        self.preview.clear()
        self.preview.setText("Select a resource")
        self.detail_title.clear()
        self.detail_text.clear()

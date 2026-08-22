"""UI document and Background document authoring workspaces.

Minimal M6 editor surfaces: a scene tree plus Inspector-driven property
editing for UI documents, a viewport preset strip, and a layer summary for
background documents. All mutations go through the shared CommandStack.
"""

from __future__ import annotations

import json

from src.qt_compat.QtCore import QMimeData, QRectF, QSignalBlocker, Qt, pyqtSignal
from src.qt_compat.QtGui import QColor, QPainter, QPen
from src.qt_compat.QtWidgets import (
    QComboBox,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.ui.document import UIDocument, UIDocumentNode

VIEWPORT_PRESETS = (
    ("384 x 448", 384, 448),
    ("640 x 360", 640, 360),
    ("960 x 540", 960, 540),
)


class UICanvas(QGraphicsView):
    """Preview the computed UI layout as authoring rectangles."""

    nodeGeometryCommitted = pyqtSignal(str, float, float, float, float)
    resourceDropped = pyqtSignal(str, str)
    nodeSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        # Parent the scene to the view itself; QGraphicsView accesses its
        # scene during destruction, so parenting it to an outer workspace can
        # cause a double-destruction crash on Windows Qt teardown.
        super().__init__(parent)
        self.graphics_scene = QGraphicsScene(self)
        self.setScene(self.graphics_scene)
        self.setObjectName("uiCanvas")
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setRenderHints(QPainter.Antialiasing)
        self._document: UIDocument | None = None
        self._items: dict[str, QGraphicsRectItem] = {}
        self._suppress_geometry = False
        self.setAcceptDrops(True)
        self.graphics_scene.selectionChanged.connect(self._selection_changed)

    def _selection_changed(self) -> None:
        selected = self.graphics_scene.selectedItems()
        if not selected:
            return
        node_id = str(selected[-1].data(0) or "")
        if node_id:
            self.nodeSelected.emit(node_id)

    def set_document(self, document: UIDocument, viewport: tuple[int, int]) -> None:
        self._document = document
        self._suppress_geometry = True
        try:
            self.graphics_scene.clear()
            self._items.clear()
            width, height = viewport
            self.graphics_scene.setSceneRect(0, 0, width, height)
            if document is None:
                return
            layout = document.calculate_layout(width, height)
            for node, _depth in document.root.walk():
                rect = layout.get(node.id)
                if rect is None:
                    continue
                x, y, w, h = rect
                item = _UICanvasItem(self, node.id, x, y, w, h)
                if node.node_type in {"text", "bar"}:
                    color = QColor("#3ddc84")
                elif node.node_type in {"image", "rect"}:
                    color = QColor("#f7c948")
                else:
                    color = QColor("#8fb4ff")
                pen = QPen(color, 1 if node is not document.root else 2)
                item.setPen(pen)
                item.setData(0, node.id)
                item.setFlag(QGraphicsItem.ItemIsSelectable, True)
                item.setFlag(QGraphicsItem.ItemIsMovable, True)
                item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
                self.graphics_scene.addItem(item)
                self._items[node.id] = item
        finally:
            self._suppress_geometry = False

    def _node_for_id(self, node_id: str) -> UIDocumentNode | None:
        if self._document is None:
            return None
        return next(
            (
                node
                for node, _depth in self._document.root.walk()
                if node.id == str(node_id)
            ),
            None,
        )

    def _commit_item_geometry(self, item: "_UICanvasItem") -> None:
        if self._suppress_geometry:
            return
        node = self._node_for_id(item.node_id)
        if node is None:
            return
        rect = item.rect()
        position = item.pos()
        x = float(position.x() + rect.x())
        y = float(position.y() + rect.y())
        width = float(rect.width())
        height = float(rect.height())
        if (
            float(node.x) == x
            and float(node.y) == y
            and float(node.width) == width
            and float(node.height) == height
        ):
            return
        self.nodeGeometryCommitted.emit(str(node.id), x, y, width, height)

    def item_for_node(self, node_id: str):
        return self._items.get(str(node_id))

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if mime.hasText():
            text = mime.text().strip()
            if text:
                item = self.graphics_scene.itemAt(
                    self.mapToScene(event.position().toPoint()), self.transform()
                )
                node_id = str(item.data(0) or "") if item is not None else ""
                self.resourceDropped.emit(node_id, text)
                event.acceptProposedAction()
                return
        event.ignore()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()
            return
        event.ignore()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._document is not None:
            self.fitInView(
                self.graphics_scene.sceneRect().adjusted(-8, -8, 8, 8),
                Qt.KeepAspectRatio,
            )


class _UICanvasItem(QGraphicsRectItem):
    """A movable UI node rectangle that reports authoring geometry changes."""

    def __init__(
        self,
        canvas: UICanvas,
        node_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        super().__init__(x, y, width, height)
        self._canvas = canvas
        self.node_id = str(node_id)
        self._resize_corner: str | None = None
        self._resize_start = None
        self._resize_rect = None
        self._move_active = False
        self.setAcceptHoverEvents(True)

    @staticmethod
    def _handle_radius() -> float:
        return 8.0

    def _corner_at(self, point) -> str | None:
        rect = self.rect()
        radius = self._handle_radius()
        corners = {
            "nw": rect.topLeft(),
            "ne": rect.topRight(),
            "sw": rect.bottomLeft(),
            "se": rect.bottomRight(),
        }
        for name, corner in corners.items():
            if abs(point.x() - corner.x()) <= radius and abs(point.y() - corner.y()) <= radius:
                return name
        return None

    def hoverMoveEvent(self, event) -> None:
        corner = self._corner_at(event.pos())
        if corner in {"nw", "se"}:
            self.setCursor(Qt.SizeFDiagCursor)
        elif corner in {"ne", "sw"}:
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        corner = self._corner_at(event.pos())
        if corner is not None and event.button() == Qt.LeftButton:
            self._resize_corner = corner
            self._resize_start = event.pos()
            self._resize_rect = QRectF(self.rect())
            event.accept()
            return
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self._move_active = True

    def mouseMoveEvent(self, event) -> None:
        if self._resize_corner is None or self._resize_start is None or self._resize_rect is None:
            super().mouseMoveEvent(event)
            return
        delta = event.pos() - self._resize_start
        rect = QRectF(self._resize_rect)
        minimum = 2.0
        if "w" in self._resize_corner:
            new_x = min(rect.right() - minimum, rect.left() + delta.x())
            rect.setLeft(new_x)
        else:
            rect.setRight(max(rect.left() + minimum, rect.right() + delta.x()))
        if "n" in self._resize_corner:
            new_y = min(rect.bottom() - minimum, rect.top() + delta.y())
            rect.setTop(new_y)
        else:
            rect.setBottom(max(rect.top() + minimum, rect.bottom() + delta.y()))
        self.setRect(rect)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._resize_corner is not None:
            self._resize_corner = None
            self._resize_start = None
            self._resize_rect = None
            self._canvas._commit_item_geometry(self)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._move_active:
            self._move_active = False
            self._canvas._commit_item_geometry(self)

    def itemChange(self, change, value):
        return super().itemChange(change, value)


def _populate_tree(document: UIDocument, widget: QTreeWidget) -> None:
    widget.clear()

    def add_node(node: UIDocumentNode, parent_item: QTreeWidgetItem | None) -> QTreeWidgetItem:
        item = QTreeWidgetItem(
            [f"{node.name}  [{node.node_type}]", node.id]
        )
        item.setData(0, Qt.UserRole, node.id)
        if parent_item is None:
            widget.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
        for child in node.children:
            add_node(child, item)
        return item

    add_node(document.root, None)


class UIWorkspace(QWidget):
    nodeSelected = pyqtSignal(str)
    nodePropertyRequested = pyqtSignal(str, object)
    nodeCreateRequested = pyqtSignal(str, str, str)
    nodeRemoveRequested = pyqtSignal(str)
    viewportChanged = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("uiWorkspace")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        toolbar = QHBoxLayout()
        self.title = QLabel("UI")
        self.title.setObjectName("uiWorkspaceTitle")
        self.title.setStyleSheet("font-size:16px; font-weight:600;")
        toolbar.addWidget(self.title)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("Viewport"))
        self.preset = QComboBox()
        self.preset.setObjectName("uiViewportPreset")
        for label, _width, _height in VIEWPORT_PRESETS:
            self.preset.addItem(label, (label,))
        self.preset.setCurrentIndex(0)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        toolbar.addWidget(self.preset)
        toolbar.addWidget(QLabel("Node"))
        self.node_type = QComboBox()
        self.node_type.setObjectName("uiNodeTypePicker")
        for node_type in ("text", "rect", "bar", "image", "panel", "container_v", "container_h", "container_grid"):
            self.node_type.addItem(node_type, node_type)
        toolbar.addWidget(self.node_type)
        add_node = QPushButton("Add")
        add_node.setObjectName("uiAddNode")
        add_node.clicked.connect(self._request_add_node)
        toolbar.addWidget(add_node)
        remove_node = QPushButton("Delete")
        remove_node.setObjectName("uiDeleteNode")
        remove_node.clicked.connect(self._request_remove_node)
        toolbar.addWidget(remove_node)
        layout.addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setObjectName("uiSceneTree")
        self.tree.setHeaderLabels(["Node", "id"])
        self.tree.setColumnWidth(0, 200)
        self.tree.currentItemChanged.connect(self._tree_selection_changed)
        layout.addWidget(self.tree, 1)
        self.canvas = UICanvas()
        self.canvas.nodeSelected.connect(self._canvas_node_selected)
        layout.addWidget(self.canvas, 2)
        self._document: UIDocument | None = None
        self._viewport: tuple[int, int] = (384, 448)

    def _preset_changed(self) -> None:
        index = max(0, self.preset.currentIndex())
        _label, width, height = VIEWPORT_PRESETS[index]
        self._viewport = (width, height)
        self.canvas.set_document(self._document, self._viewport)
        self.viewportChanged.emit(width, height)

    def _tree_selection_changed(self, current, _previous) -> None:
        if current is None:
            return
        node_id = str(current.data(0, Qt.UserRole) or "")
        if node_id:
            self.nodeSelected.emit(node_id)

    def _canvas_node_selected(self, node_id: str) -> None:
        self.select_node(node_id)
        self.nodeSelected.emit(str(node_id))

    def _selected_node_id(self) -> str:
        item = self.tree.currentItem()
        return str(item.data(0, Qt.UserRole) or "") if item is not None else ""

    def _request_add_node(self) -> None:
        parent_id = self._selected_node_id()
        if not parent_id and self._document is not None:
            parent_id = self._document.root.id
        node_type = str(self.node_type.currentData() or self.node_type.currentText())
        self.nodeCreateRequested.emit(parent_id, node_type, f"New {node_type}")

    def _request_remove_node(self) -> None:
        node_id = self._selected_node_id()
        if node_id:
            self.nodeRemoveRequested.emit(node_id)

    def set_document(self, document: UIDocument) -> None:
        self._document = document
        self.title.setText(f"UI: {document.name}")
        _populate_tree(document, self.tree)
        self.canvas.set_document(document, self._viewport)
        if self.tree.topLevelItemCount():
            with QSignalBlocker(self.tree):
                self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def select_node(self, node_id: str) -> None:
        def find(item: QTreeWidgetItem) -> bool:
            if str(item.data(0, Qt.UserRole) or "") == node_id:
                with QSignalBlocker(self.tree):
                    self.tree.setCurrentItem(item)
                return True
            for index in range(item.childCount()):
                if find(item.child(index)):
                    return True
            return False

        for index in range(self.tree.topLevelItemCount()):
            if find(self.tree.topLevelItem(index)):
                break

    def refresh_canvas(self) -> None:
        if self._document is not None:
            self.canvas.set_document(self._document, self._viewport)


class BackgroundWorkspace(QWidget):
    """Background authoring surface with layer transform gizmos.

    The canvas is an authoring/diagnostic view.  Formal background quads are
    produced by the resource registry's ``DataDrivenBackground`` preview
    handler, not by this QGraphicsScene.
    """

    layerSelected = pyqtSignal(int)
    layerTransformCommitted = pyqtSignal(int, float, float, float, float)
    layerCreateRequested = pyqtSignal()
    layerRemoveRequested = pyqtSignal(int)
    bindingRequested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("backgroundWorkspace")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        toolbar = QHBoxLayout()
        self.title = QLabel("Background")
        self.title.setObjectName("backgroundWorkspaceTitle")
        self.title.setStyleSheet("font-size:16px; font-weight:600;")
        toolbar.addWidget(self.title)
        toolbar.addStretch()
        add = QPushButton("Add Layer")
        add.setObjectName("backgroundAddLayer")
        add.clicked.connect(self.layerCreateRequested.emit)
        toolbar.addWidget(add)
        remove = QPushButton("Delete Layer")
        remove.setObjectName("backgroundDeleteLayer")
        remove.clicked.connect(self._request_remove_layer)
        toolbar.addWidget(remove)
        layout.addLayout(toolbar)
        self.layers = QListWidget()
        self.layers.setObjectName("backgroundLayerList")
        self.layers.currentRowChanged.connect(self._layer_row_changed)
        layout.addWidget(self.layers, 1)
        binding_row = QHBoxLayout()
        self.binding_target = QLineEdit()
        self.binding_target.setObjectName("backgroundBindingTarget")
        self.binding_target.setPlaceholderText("camera.fovy or layers.0.alpha")
        binding_row.addWidget(self.binding_target, 2)
        self.binding_expression = QLineEdit()
        self.binding_expression.setObjectName("backgroundBindingExpression")
        self.binding_expression.setPlaceholderText("frame * 0.01")
        binding_row.addWidget(self.binding_expression, 2)
        add_binding = QPushButton("Bind")
        add_binding.setObjectName("backgroundAddBinding")
        add_binding.clicked.connect(self._request_binding)
        binding_row.addWidget(add_binding)
        layout.addLayout(binding_row)
        self.bindings = QListWidget()
        self.bindings.setObjectName("backgroundBindingList")
        layout.addWidget(self.bindings, 1)
        # Parent both the view and its scene to the workspace so Qt destroys
        # the graphics items before the document tab/dock is torn down.
        self.canvas = BackgroundCanvas(self)
        self.canvas.layerSelected.connect(self._canvas_layer_selected)
        self.canvas.layerTransformCommitted.connect(self.layerTransformCommitted)
        layout.addWidget(self.canvas, 3)
        self._document = None

    def _layer_row_changed(self, row: int) -> None:
        if row >= 0:
            self.layerSelected.emit(int(row))
            self.canvas.select_layer(int(row))

    def _canvas_layer_selected(self, index: int) -> None:
        with QSignalBlocker(self.layers):
            self.layers.setCurrentRow(int(index))
        self.layerSelected.emit(int(index))

    def _request_remove_layer(self) -> None:
        row = self.layers.currentRow()
        if row >= 0:
            self.layerRemoveRequested.emit(int(row))

    def _request_binding(self) -> None:
        target = self.binding_target.text().strip()
        expression = self.binding_expression.text().strip()
        if target and expression:
            self.bindingRequested.emit(target, expression)

    def set_document(self, document) -> None:
        self._document = document
        self.title.setText(f"Background: {document.name}")
        self.layers.clear()
        for layer in document.body.get("layers") or []:
            self.layers.addItem(
                f"{layer.get('name', '')}  ·  {layer.get('blend_mode', 'normal')}"
                f"  ·  z {layer.get('z_order', 0)}  ·  "
                f"{'on' if layer.get('enabled', True) else 'off'}"
            )
        self.canvas.set_document(document)
        self.bindings.clear()
        for target, expression in (document.body.get("bindings") or {}).items():
            self.bindings.addItem(f"{target} = {expression}")
        if self.layers.count():
            self.layers.setCurrentRow(0)


class BackgroundCanvas(QGraphicsView):
    """Lightweight transform-gizmo canvas for authored background layers."""

    layerSelected = pyqtSignal(int)
    layerTransformCommitted = pyqtSignal(int, float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.graphics_scene = QGraphicsScene(self)
        self.setScene(self.graphics_scene)
        self.setObjectName("backgroundCanvas")
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setRenderHints(QPainter.Antialiasing)
        self._document = None
        self._items: dict[int, _BackgroundLayerItem] = {}
        self.graphics_scene.selectionChanged.connect(self._selection_changed)

    def set_document(self, document) -> None:
        self._document = document
        # ``QGraphicsScene.clear`` destroys native items synchronously.  Cut
        # their Python callback edge first so an ItemChange emitted during
        # destruction cannot call back through a deleted C++ wrapper.
        self.graphics_scene.blockSignals(True)
        for old_item in tuple(self._items.values()):
            old_item._canvas = None
        self.graphics_scene.clear()
        self._items.clear()
        self.graphics_scene.blockSignals(False)
        self.graphics_scene.setSceneRect(-6.0, -6.0, 12.0, 12.0)
        for index, layer in enumerate(document.body.get("layers") or []):
            transform = layer.get("transform") or {}
            item = _BackgroundLayerItem(
                self,
                index,
                float(transform.get("x", 0.0)),
                float(transform.get("y", 0.0)),
                float(transform.get("scale", 1.0)),
                float(transform.get("rotation", 0.0)),
            )
            item.setData(0, index)
            item.setFlag(QGraphicsItem.ItemIsSelectable, True)
            item.setFlag(QGraphicsItem.ItemIsMovable, True)
            item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            self.graphics_scene.addItem(item)
            self._items[index] = item
        self.fitInView(self.graphics_scene.sceneRect(), Qt.KeepAspectRatio)

    def dispose(self) -> None:
        """Detach Python callbacks before Qt destroys graphics items."""
        self.graphics_scene.blockSignals(True)
        for item in tuple(self._items.values()):
            item._canvas = None
        self.graphics_scene.clear()
        self._items.clear()
        self.graphics_scene.blockSignals(False)

    def closeEvent(self, event) -> None:
        self.dispose()
        super().closeEvent(event)

    def _selection_changed(self) -> None:
        selected = self.graphics_scene.selectedItems()
        if selected:
            self.layerSelected.emit(int(selected[-1].data(0)))

    def select_layer(self, index: int) -> None:
        item = self._items.get(int(index))
        if item is not None:
            item.setSelected(True)
            self.graphics_scene.setFocusItem(item)

    def _item_geometry_changed(self, item: "_BackgroundLayerItem") -> None:
        x, y, scale, rotation = item.transform_values()
        self.layerTransformCommitted.emit(item.layer_index, x, y, scale, rotation)


class _BackgroundLayerItem(QGraphicsRectItem):
    def __init__(
        self,
        canvas: BackgroundCanvas,
        layer_index: int,
        x: float,
        y: float,
        scale: float,
        rotation: float,
    ):
        super().__init__(-1.5, -1.0, 3.0, 2.0)
        self._canvas = canvas
        self.layer_index = int(layer_index)
        self.setPos(float(x), float(y))
        self.setScale(max(0.01, float(scale)))
        self.setRotation(float(rotation))
        self.setPen(QPen(QColor("#d9a441"), 0.03))
        self.setBrush(QColor(217, 164, 65, 55))

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change in {
            QGraphicsItem.ItemPositionHasChanged,
            QGraphicsItem.ItemScaleHasChanged,
            QGraphicsItem.ItemRotationHasChanged,
        } and self._canvas is not None:
            self._canvas._item_geometry_changed(self)
        return result

    def transform_values(self) -> tuple[float, float, float, float]:
        position = self.pos()
        return (
            float(position.x()),
            float(position.y()),
            float(self.scale()),
            float(self.rotation()),
        )

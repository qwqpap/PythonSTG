"""Scene hierarchy tree and node canvas widgets for the editor shell."""

from __future__ import annotations

import json
from src.qt_compat import sip
from src.qt_compat.QtCore import QPointF, QRectF, Qt, pyqtSignal
from src.qt_compat.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from src.qt_compat.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
)
from src.core.project_context import ProjectContext
from src.authoring.coordinates import CoordinateSpace
from .asset_index import load_subresource_preview
from .action_search import SpaceTapSearchMixin
from .document import EditorNode, SceneDocument
from .node_types import NODE_TYPES
from .resource_browser import RESOURCE_MIME_TYPE
from .i18n import LanguageManager


class SceneTreeWidget(QTreeWidget):
    nodeMoveRequested = pyqtSignal(str, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderLabels(["Scene", "Type"])
        self.header().setStretchLastSection(True)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.setColumnHidden(1, True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def dropEvent(self, event) -> None:
        item = self.currentItem()
        if item is None or item.parent() is None:
            event.ignore()
            return
        node_id = str(item.data(0, Qt.UserRole))
        super().dropEvent(event)

        moved = self._find_item(node_id)
        root_item = self.topLevelItem(0)
        if moved is None or root_item is None:
            return
        parent = moved.parent()
        if parent is None:
            index = self.indexOfTopLevelItem(moved)
            self.takeTopLevelItem(index)
            root_item.addChild(moved)
            parent = root_item
        target_index = parent.indexOfChild(moved)
        target_parent_id = str(parent.data(0, Qt.UserRole))
        self.nodeMoveRequested.emit(node_id, target_parent_id, target_index)

    def _find_item(self, node_id: str) -> QTreeWidgetItem | None:
        pending = [
            self.topLevelItem(index)
            for index in range(self.topLevelItemCount())
        ]
        while pending:
            item = pending.pop()
            if item is None:
                continue
            if str(item.data(0, Qt.UserRole)) == node_id:
                return item
            pending.extend(item.child(index) for index in range(item.childCount()))
        return None


class NodeGraphicsItem(QGraphicsObject):
    positionCommitted = pyqtSignal(str, float, float)

    def __init__(
        self,
        node: EditorNode,
        project: ProjectContext,
        grid_size: int,
        node_registry=None,
        language_manager: LanguageManager | None = None,
    ):
        super().__init__()
        self.node_id = node.id
        self.node_type = node.type
        self.node_name = node.name
        self.grid_size = max(1, grid_size)
        self._drag_start = QPointF()
        self._node_registry = node_registry
        self._spec = (
            node_registry.get(node.type)
            if node_registry is not None
            else NODE_TYPES.get(node.type)
        )
        self._language_manager = language_manager
        self._pixmap = self._load_pixmap(node, project, node_registry)
        self._runtime_pose = False
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.OpenHandCursor)
        self.setZValue(10)

    @staticmethod
    def _load_pixmap(node: EditorNode, project: ProjectContext, node_registry=None) -> QPixmap:
        spec = (
            node_registry.get(node.type)
            if node_registry is not None
            else NODE_TYPES.get(node.type)
        )
        preview_property = spec.viewport.preview_property if spec is not None else None
        if preview_property is None:
            return QPixmap()
        texture = str(node.properties.get(preview_property, "")).strip()
        if not texture:
            return QPixmap()
        candidate, rect = load_subresource_preview(project, texture)
        if candidate is None:
            return QPixmap()
        try:
            project.relative(candidate)
        except Exception:
            return QPixmap()
        if not candidate.is_file():
            return QPixmap()
        pixmap = QPixmap(str(candidate))
        if pixmap.isNull():
            return QPixmap()
        if rect is not None:
            x, y, width, height = rect
            clipped = pixmap.rect().intersected(QRectF(x, y, width, height).toRect())
            if clipped.isEmpty():
                return QPixmap()
            pixmap = pixmap.copy(clipped)
        return pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def boundingRect(self) -> QRectF:
        return QRectF(-38.0, -38.0, 76.0, 96.0)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        shape = self._spec.viewport.shape if self._spec is not None else "box"
        if shape == "circle":
            path.addEllipse(QRectF(-24, -24, 48, 48))
        elif shape == "diamond":
            polygon = [
                QPointF(0, -28),
                QPointF(28, 0),
                QPointF(0, 28),
                QPointF(-28, 0),
            ]
            path.moveTo(polygon[0])
            for point in polygon[1:]:
                path.lineTo(point)
            path.closeSubpath()
        else:
            path.addRoundedRect(QRectF(-28, -28, 56, 56), 5, 5)
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        spec = self._spec
        color = QColor(spec.color if spec else "#9aa4b2")
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(
            QPen(
                QColor("#54e1ff")
                if self._runtime_pose
                else QColor("#f5f7ff") if self.isSelected() else color,
                3 if self.isSelected() or self._runtime_pose else 2,
                Qt.DashLine if self._runtime_pose else Qt.SolidLine,
            )
        )
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 72)))

        shape = spec.viewport.shape if spec is not None else "box"
        label = spec.viewport.label if spec is not None else "NODE"
        if shape == "circle":
            painter.drawEllipse(QRectF(-24, -24, 48, 48))
            painter.drawText(QRectF(-21, -10, 42, 20), Qt.AlignCenter, label)
        elif shape == "diamond":
            path = self.shape()
            painter.drawPath(path)
            painter.drawText(QRectF(-25, -10, 50, 20), Qt.AlignCenter, label)
        else:
            painter.drawRoundedRect(QRectF(-28, -28, 56, 56), 5, 5)
            if not self._pixmap.isNull():
                target = QRectF(
                    -self._pixmap.width() / 2,
                    -self._pixmap.height() / 2,
                    self._pixmap.width(),
                    self._pixmap.height(),
                )
                painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
            else:
                painter.drawText(QRectF(-24, -10, 48, 20), Qt.AlignCenter, label)

        painter.setPen(QColor("#e8ecf5"))
        display_name = self.node_name
        if self._language_manager is not None and (
            self._spec is not None and self.node_name == self._spec.display_name
        ):
            display_name = self._language_manager.translate(display_name)
        painter.drawText(
            QRectF(-70, 34, 140, 22),
            Qt.AlignHCenter | Qt.AlignTop,
            display_name,
        )
        if self._runtime_pose:
            painter.setPen(QColor("#54e1ff"))
            painter.drawText(QRectF(-34, -48, 68, 14), Qt.AlignCenter, "RUNTIME")

    def set_runtime_position(self, x: float, y: float, *, active: bool) -> None:
        self._runtime_pose = bool(active)
        self.setFlag(QGraphicsItem.ItemIsMovable, not self._runtime_pose)
        self.setPos(float(x), float(y))
        self.update()

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.OpenHandCursor)
        snapped = QPointF(
            round(self.x() / self.grid_size) * self.grid_size,
            round(self.y() / self.grid_size) * self.grid_size,
        )
        self.setPos(snapped)
        if snapped != self._drag_start:
            self.positionCommitted.emit(self.node_id, snapped.x(), snapped.y())


class SceneViewport(SpaceTapSearchMixin, QGraphicsView):
    nodeSelected = pyqtSignal(str)
    nodePositionRequested = pyqtSignal(str, float, float)
    resourceDropped = pyqtSignal(object, float, float)
    actionSearchRequested = pyqtSignal(object)

    def __init__(
        self,
        project: ProjectContext,
        parent=None,
        node_registry=None,
        language_manager: LanguageManager | None = None,
    ):
        self.graphics_scene = QGraphicsScene(parent)
        super().__init__(self.graphics_scene, parent)
        self.project = project
        self.node_registry = node_registry
        self.language_manager = language_manager
        self._document: SceneDocument | None = None
        self._items: dict[str, NodeGraphicsItem] = {}
        self._grid_size = 16
        self._background = QColor("#171a24")
        self._runtime_state: dict[str, dict] = {}
        self.coordinate_space = CoordinateSpace()
        self._fit_on_next_resize = True
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self._init_space_tap()
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFrameShape(QFrame.NoFrame)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.graphics_scene.selectionChanged.connect(self._selection_changed)

    def rebuild(self, document: SceneDocument) -> None:
        self._document = document
        self.graphics_scene.clear()
        self._items.clear()

        root = document.root
        self.coordinate_space = document.coordinate_space
        width = max(64, int(self.coordinate_space.logical_width))
        height = max(64, int(self.coordinate_space.logical_height))
        self._grid_size = max(1, int(root.properties.get("grid_size", 16)))
        self._background = QColor(str(root.properties.get("background", "#171a24")))
        if not self._background.isValid():
            self._background = QColor("#171a24")
        self.graphics_scene.setSceneRect(0, 0, width, height)

        for node in root.walk():
            spec = (
                self.node_registry.get(node.type)
                if self.node_registry is not None
                else NODE_TYPES.get(node.type)
            )
            if spec is None or not spec.viewport_item:
                continue
            item = NodeGraphicsItem(
                node,
                self.project,
                self._grid_size,
                self.node_registry,
                self.language_manager,
            )
            item.setPos(
                float(node.properties.get("x", width / 2)),
                float(node.properties.get("y", height / 2)),
            )
            item.positionCommitted.connect(self.nodePositionRequested)
            self.graphics_scene.addItem(item)
            self._items[node.id] = item

        self.viewport().update()
        if self._runtime_state:
            self._apply_runtime_state()
        if self._fit_on_next_resize:
            self.fit_canvas()

    def fit_canvas(self) -> None:
        rect = self.graphics_scene.sceneRect()
        if not rect.isEmpty():
            self.fitInView(rect.adjusted(-24, -24, 24, 24), Qt.KeepAspectRatio)

    def select_node(self, node_id: str) -> None:
        for item_id, item in self._items.items():
            item.setSelected(item_id == node_id)

    def runtime_position(self, x: float, y: float) -> tuple[float, float]:
        """Convert a gizmo position through the formal authoring contract."""
        return self.coordinate_space.authoring_to_runtime(x, y)

    def set_runtime_state(self, node_state: dict | None) -> None:
        self._runtime_state = dict(node_state or {})
        self._apply_runtime_state()

    def clear_runtime_state(self) -> None:
        self._runtime_state = {}
        if self._document is None:
            return
        nodes = {node.id: node for node in self._document.root.walk()}
        width = self.coordinate_space.logical_width
        height = self.coordinate_space.logical_height
        for node_id, item in self._items.items():
            node = nodes.get(node_id)
            if node is None:
                continue
            item.set_runtime_position(
                float(node.properties.get("x", width / 2)),
                float(node.properties.get("y", height / 2)),
                active=False,
            )
        self.viewport().update()

    def _apply_runtime_state(self) -> None:
        if self._document is None:
            return
        nodes = {node.id: node for node in self._document.root.walk()}
        for node_id, item in self._items.items():
            state = self._runtime_state.get(node_id)
            x = state.get("x") if isinstance(state, dict) else None
            y = state.get("y") if isinstance(state, dict) else None
            if (
                isinstance(x, (int, float))
                and not isinstance(x, bool)
                and isinstance(y, (int, float))
                and not isinstance(y, bool)
            ):
                authoring_x, authoring_y = self.coordinate_space.runtime_to_authoring(x, y)
                item.set_runtime_position(authoring_x, authoring_y, active=True)
                continue
            node = nodes.get(node_id)
            if node is not None:
                item.set_runtime_position(
                    float(node.properties.get("x", self.coordinate_space.logical_width / 2)),
                    float(node.properties.get("y", self.coordinate_space.logical_height / 2)),
                    active=False,
                )
        self.viewport().update()

    def _selection_changed(self) -> None:
        # Qt can deliver a queued selectionChanged after the scene's C++ side is
        # gone (window teardown, document swap).  Touching it then aborts the
        # process, so confirm both halves are alive before reading selection.
        if sip.isdeleted(self) or sip.isdeleted(self.graphics_scene):
            return
        selected = self.graphics_scene.selectedItems()
        if selected and isinstance(selected[0], NodeGraphicsItem):
            self.nodeSelected.emit(selected[0].node_id)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self._background)
        scene_rect = self.graphics_scene.sceneRect()
        painter.setPen(QPen(QColor("#303644"), 0))
        left = max(scene_rect.left(), int(rect.left()) - (int(rect.left()) % self._grid_size))
        top = max(scene_rect.top(), int(rect.top()) - (int(rect.top()) % self._grid_size))
        x = left
        while x <= min(rect.right(), scene_rect.right()):
            painter.drawLine(QPointF(x, max(rect.top(), scene_rect.top())), QPointF(x, min(rect.bottom(), scene_rect.bottom())))
            x += self._grid_size
        y = top
        while y <= min(rect.bottom(), scene_rect.bottom()):
            painter.drawLine(QPointF(max(rect.left(), scene_rect.left()), y), QPointF(min(rect.right(), scene_rect.right()), y))
            y += self._grid_size
        painter.setPen(QPen(QColor("#68748c"), 1))
        painter.drawRect(scene_rect)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(RESOURCE_MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(RESOURCE_MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(RESOURCE_MIME_TYPE):
            super().dropEvent(event)
            return
        try:
            payload = json.loads(
                bytes(event.mimeData().data(RESOURCE_MIME_TYPE)).decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            event.ignore()
            return
        scene_position = self.mapToScene(event.position().toPoint())
        self.resourceDropped.emit(
            payload,
            float(scene_position.x()),
            float(scene_position.y()),
        )
        event.acceptProposedAction()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_on_next_resize:
            self.fit_canvas()
            self._fit_on_next_resize = False

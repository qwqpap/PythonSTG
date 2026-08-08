"""Graph authoring canvas and Recipe/Graph mode switching in PatternWorkspace."""

from __future__ import annotations

from typing import Any

from src.qt_compat import sip
from src.qt_compat.QtCore import QPointF, QRectF, Qt, pyqtSignal
from src.qt_compat.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from src.qt_compat.QtWidgets import (
    QComboBox,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.pattern import BehaviorGraph, BehaviorGraphNode, PatternDocument
from src.pattern.graph import PORT_TYPES

from .pattern_workspace import PatternCanvas

GRAPH_CATEGORY_COLORS = {
    "source": "#4ade80",
    "shape": "#60a5fa",
    "aim": "#c084fc",
    "schedule": "#fbbf24",
    "motion": "#f87171",
    "modifier": "#facc15",
    "condition": "#94a3b8",
    "event": "#94a3b8",
    "script": "#94a3b8",
}

#: Human-readable label / editor kind / default for graph node properties.
#: The internal ``binding`` property stays hidden; ``speed_expression`` is the
#: exposed expression surface.
GRAPH_NODE_PROPERTY_SPECS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "source": (
        ("bullet_type", "Bullet Type", "text"),
        ("color", "Color", "text"),
        ("resource", "Resource", "text"),
    ),
    "shape": (
        ("count", "Count", "int"),
        ("origin_x", "Origin X", "float"),
        ("origin_y", "Origin Y", "float"),
        ("angle_span", "Angle Span", "float"),
        ("line_length", "Line Length", "float"),
        ("line_angle", "Line Angle", "float"),
    ),
    "aim": (("angle", "Angle", "float"),),
    "schedule": (
        ("delay_frames", "Delay Frames", "int"),
        ("interval_frames", "Interval Frames", "int"),
        ("burst_count", "Burst Count", "int"),
        ("loop_count", "Loop Count", "int"),
    ),
    "motion": (
        ("speed", "Speed", "float"),
        ("friction", "Friction", "float"),
        ("spin", "Spin", "float"),
        ("time_scale", "Time Scale", "float"),
        ("max_lifetime", "Max Lifetime", "float"),
        ("render_scale", "Render Scale", "float"),
        ("bounce_x", "Bounce X", "bool"),
        ("bounce_y", "Bounce Y", "bool"),
        ("speed_expression", "Speed Expression", "text"),
    ),
    "modifier": (
        ("angle_offset_per_burst", "Angle Offset / Burst", "float"),
        ("speed_offset_per_burst", "Speed Offset / Burst", "float"),
        ("random_speed_variation", "Random Speed Var", "float"),
    ),
    "condition": (),
    "event": (),
    "script": (),
}

#: Categories with no runtime semantics yet; hidden from the create menu but
#: preserved by the model and validation.
HIDDEN_NODE_CATEGORIES = {"condition", "event", "script"}
CREATABLE_NODE_CATEGORIES = (
    ("source", "bullet"),
    ("shape", "ring"),
    ("aim", "fixed"),
    ("schedule", "interval"),
    ("motion", "constant"),
    ("modifier", "angle_offset"),
)

NODE_WIDTH = 150.0
NODE_HEIGHT = 64.0
PORT_RADIUS = 7.0


def can_connect(source_category: str, target_category: str) -> bool:
    """Port-type check used by the canvas and the add-edge command."""
    output_type = PORT_TYPES.get(source_category, (None, None))[1]
    input_type = PORT_TYPES.get(target_category, (None, None))[0]
    return output_type is not None and output_type == input_type


class GraphPortItem(QGraphicsObject):
    """One typed in/out port dot attached to a graph node item."""

    portDrag = pyqtSignal(object, QPointF)
    portDragMove = pyqtSignal(object, QPointF)
    portDragRelease = pyqtSignal(object)

    def __init__(
        self,
        owner_id: str,
        kind: str,
        port_type: str,
        position: QPointF,
        parent=None,
    ):
        super().__init__(parent)
        self.owner_id = owner_id
        self.kind = kind  # "in" | "out"
        self.port_type = port_type
        self.setPos(position)
        self.setCursor(Qt.CrossCursor)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"{kind} port · {port_type}")
        self._hovered = False
        self._drag = False
        self._error_visual = False

    def boundingRect(self) -> QRectF:
        return QRectF(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2)

    def set_error_visual(self, error: bool) -> None:
        self._error_visual = bool(error)
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setRenderHint(QPainter.Antialiasing)
        if self._error_visual:
            painter.setPen(QPen(QColor("#ff4d4d"), 2))
            painter.setBrush(QColor("#ff4d4d"))
        elif self._drag:
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor("#ffffff"))
        elif self._hovered:
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor("#ffd166"))
        else:
            painter.setPen(QPen(QColor("#0b1220"), 1))
            painter.setBrush(QColor("#8b9bb4"))
        painter.drawEllipse(
            QRectF(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2)
        )

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag = True
            self.update()
            self.portDrag.emit(
                self, self.mapToScene(QPointF(0.0, 0.0))
            )
            event.accept()
            if sip.isdeleted(self):
                return
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag:
            self.portDragMove.emit(self, self.mapToScene(QPointF(0.0, 0.0)))
            event.accept()
            if sip.isdeleted(self):
                return
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag and event.button() == Qt.LeftButton:
            self._drag = False
            self.update()
            self.portDragRelease.emit(self)
            event.accept()
            if sip.isdeleted(self):
                return
            return
        super().mouseReleaseEvent(event)


class GraphNodeItem(QGraphicsObject):
    nodePositionCommitted = pyqtSignal(str, float, float)
    nodeSelected = pyqtSignal(str)

    def __init__(self, node: BehaviorGraphNode):
        super().__init__()
        self.node_id = node.id
        self.category = node.category
        self.node_type = node.node_type
        self._name = node.name
        self._properties = dict(node.properties)
        self._error = False
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.SizeAllCursor)
        self.setZValue(2)
        color = QColor(GRAPH_CATEGORY_COLORS.get(self.category, "#94a3b8"))
        self._color = color

    def add_port(self, kind: str, port_type: str, position: QPointF) -> GraphPortItem:
        port = GraphPortItem(self.node_id, kind, port_type, position, parent=self)
        port.setZValue(3)
        return port

    def boundingRect(self) -> QRectF:
        return QRectF(-NODE_WIDTH / 2, -NODE_HEIGHT / 2, NODE_WIDTH, NODE_HEIGHT)

    def set_error(self, error: bool) -> None:
        self._error = bool(error)
        self.update()

    def summary(self) -> str:
        if self.category == "shape":
            return f"{self.node_type} · {self._properties.get('count', 24)}"
        if self.category == "aim":
            return f"{self.node_type} · {self._properties.get('angle', 270.0)}°"
        if self.category == "schedule":
            return (
                f"every {self._properties.get('interval_frames', 20)}f · "
                f"x{self._properties.get('burst_count', 1)}"
            )
        if self.category == "motion":
            return f"speed {self._properties.get('speed', 2.0)}"
        if self.category == "modifier":
            return "rotate bursts"
        return self.node_type

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = self.boundingRect()
        selected = self.isSelected()
        pen_color = QColor("#ffffff") if selected else self._color
        pen = QPen(pen_color, 2 if selected else 1)
        if self._error:
            pen.setColor(QColor("#ff4d4d"))
            pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(QColor("#1b2436"))
        painter.drawRoundedRect(bounds, 10, 10)
        painter.setPen(QPen(self._color.lighter(150), 1))
        painter.drawText(
            QRectF(bounds.left(), bounds.top() + 6, bounds.width(), 18),
            Qt.AlignHCenter | Qt.AlignTop,
            self._name,
        )
        painter.setPen(QPen(QColor("#c7d2e4"), 1))
        painter.drawText(
            QRectF(bounds.left() + 6, bounds.center().y(), bounds.width() - 12, 18),
            Qt.AlignHCenter | Qt.AlignVCenter,
            self.summary(),
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            point = QPointF(value)
            bounds = self.scene().sceneRect()
            margin = 40.0
            return QPointF(
                min(max(point.x(), bounds.left() - margin), bounds.right() + margin),
                min(max(point.y(), bounds.top() - margin), bounds.bottom() + margin),
            )
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event) -> None:
        self.nodePositionCommitted.emit(
            self.node_id, float(self.pos().x()), float(self.pos().y())
        )
        if sip.isdeleted(self):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event) -> None:
        self.nodeSelected.emit(self.node_id)
        if sip.isdeleted(self):
            event.accept()
            return
        super().mousePressEvent(event)


class GraphEdgeItem(QGraphicsObject):
    def __init__(self, edge_id: str, source: GraphNodeItem, target: GraphNodeItem):
        super().__init__()
        self.edge_id = edge_id
        self._source = source
        self._target = target
        self._error = False
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(1)
        self.setAcceptHoverEvents(True)

    def set_error(self, error: bool) -> None:
        self._error = bool(error)
        self.update()

    def _endpoints(self) -> tuple[QPointF, QPointF]:
        start = self._source.mapToScene(QPointF(NODE_WIDTH / 2, 0.0))
        end = self._target.mapToScene(QPointF(-NODE_WIDTH / 2, 0.0))
        return start, end

    def boundingRect(self) -> QRectF:
        start, end = self._endpoints()
        return QRectF(start, end).normalized().adjusted(-12, -12, 12, 12)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        start, end = self._endpoints()
        painter.setRenderHint(QPainter.Antialiasing)
        if self._error:
            pen = QPen(QColor("#ff4d4d"), 3)
        elif self.isSelected():
            pen = QPen(QColor("#ffffff"), 2)
        else:
            pen = QPen(QColor("#7c8aa5"), 2)
        painter.setPen(pen)
        mid = QPointF(
            (start.x() + end.x()) / 2.0,
            (start.y() + end.y()) / 2.0 - 40.0,
        )
        path = QPainterPath(start)
        path.cubicTo(
            QPointF((start.x() + mid.x()) / 2.0, start.y()),
            QPointF((mid.x() + end.x()) / 2.0, end.y()),
            end,
        )
        painter.drawPath(path)
        angle = 25.0
        arrow = QPolygonF(
            [
                end,
                end
                + QPointF(
                    -12.0 * _cos(angle), 12.0 * _sin(angle)
                ),
                end
                + QPointF(
                    -12.0 * _cos(angle), -12.0 * _sin(angle)
                ),
            ]
        )
        painter.setBrush(pen.color())
        painter.drawPolygon(arrow)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        start, end = self._endpoints()
        path.moveTo(start)
        path.lineTo(end)
        stroker = QPainterPathStroker()
        stroker.setWidth(14.0)
        return stroker.createStroke(path)


def _cos(degrees: float) -> float:
    import math

    return math.cos(math.radians(degrees))


def _sin(degrees: float) -> float:
    import math

    return math.sin(math.radians(degrees))


class GraphCanvas(QGraphicsView):
    nodeSelected = pyqtSignal(str)
    nodePositionCommitted = pyqtSignal(str, float, float)
    edgeRequested = pyqtSignal(str, str)
    nodeRemoveRequested = pyqtSignal(str)
    edgeRemoveRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        self.graphics_scene = QGraphicsScene(parent)
        super().__init__(self.graphics_scene, parent)
        self.setObjectName("graphCanvas")
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setRenderHints(QPainter.Antialiasing)
        self._graph: BehaviorGraph | None = None
        self._node_items: dict[str, GraphNodeItem] = {}
        self._edge_items: dict[str, GraphEdgeItem] = {}
        self._drag_line: QGraphicsItem | None = None
        self._drag_port: GraphPortItem | None = None
        self._drag_target: GraphPortItem | None = None

    # -- document binding ---------------------------------------------------

    def set_graph(self, graph: BehaviorGraph | None) -> None:
        self._graph = graph
        self.graphics_scene.clear()
        self._node_items = {}
        self._edge_items = {}
        self._drag_line = None
        self._drag_port = None
        self._drag_target = None
        if graph is None:
            return
        for node in graph.nodes:
            item = GraphNodeItem(node)
            item.nodePositionCommitted.connect(self._node_moved)
            item.nodeSelected.connect(self.nodeSelected)
            if node.position is not None:
                item.setPos(*node.position)
            self.graphics_scene.addItem(item)
            self._node_items[node.id] = item
            input_type = PORT_TYPES.get(node.category, (None, None))[0]
            output_type = PORT_TYPES.get(node.category, (None, None))[1]
            if input_type is not None:
                port = item.add_port(
                    "in",
                    input_type,
                    QPointF(-NODE_WIDTH / 2, 0.0),
                )
                port.portDrag.connect(self._port_drag_started)
                port.portDragMove.connect(self._port_drag_moved)
                port.portDragRelease.connect(self._port_drag_released)
            if output_type is not None:
                port = item.add_port(
                    "out",
                    output_type,
                    QPointF(NODE_WIDTH / 2, 0.0),
                )
                port.portDrag.connect(self._port_drag_started)
                port.portDragMove.connect(self._port_drag_moved)
                port.portDragRelease.connect(self._port_drag_released)
        for edge in graph.edges:
            source = self._node_items.get(edge.from_node)
            target = self._node_items.get(edge.to_node)
            if source is None or target is None:
                continue
            item = GraphEdgeItem(edge.id, source, target)
            self.graphics_scene.addItem(item)
            self._edge_items[edge.id] = item
        self._fit_to_content()

    def _node_moved(self, node_id: str, x: float, y: float) -> None:
        for edge_item in self._edge_items.values():
            if not sip.isdeleted(edge_item):
                edge_item.update()
        if not sip.isdeleted(self):
            self.viewport().update()
        self.nodePositionCommitted.emit(node_id, x, y)

    def set_diagnostics(self, node_ids: tuple[str, ...], edge_ids: tuple[str, ...]) -> None:
        for node_id, item in self._node_items.items():
            item.set_error(node_id in node_ids)
        for edge_id, item in self._edge_items.items():
            item.set_error(edge_id in edge_ids)

    def clear_diagnostics(self) -> None:
        for item in self._node_items.values():
            item.set_error(False)
        for item in self._edge_items.values():
            item.set_error(False)

    def select_node(self, node_id: str) -> None:
        item = self._node_items.get(node_id)
        if item is not None:
            for other in self._node_items.values():
                other.setSelected(False)
            item.setSelected(True)
            self.centerOn(item)

    def _fit_to_content(self) -> None:
        bounds = self.graphics_scene.itemsBoundingRect()
        self.graphics_scene.setSceneRect(
            bounds.adjusted(-80, -80, 80, 80)
        )
        self.fitInView(
            self.graphics_scene.sceneRect(),
            Qt.KeepAspectRatio,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._graph is not None:
            self.fitInView(
                self.graphics_scene.sceneRect(),
                Qt.KeepAspectRatio,
            )

    # -- port drag wiring ---------------------------------------------------

    def _port_drag_started(self, port: GraphPortItem, scene_pos: QPointF) -> None:
        self._drag_port = port
        self._drag_target = None
        line = QGraphicsLineItem()
        line.setPen(QPen(QColor("#ffffff"), 2, Qt.DashLine))
        line.setZValue(10)
        line.setLine(scene_pos.x(), scene_pos.y(), scene_pos.x(), scene_pos.y())
        self.graphics_scene.addItem(line)
        self._drag_line = line

    def _port_drag_moved(self, port: GraphPortItem, scene_pos: QPointF) -> None:
        if self._drag_line is None:
            return
        line = self._drag_line
        old = line.line()
        line.setLine(old.x1(), old.y1(), scene_pos.x(), scene_pos.y())
        if self._drag_target is not None:
            self._drag_target.set_error_visual(False)
            self._drag_target = None
        target = self._hit_port_at(scene_pos, exclude=port)
        if target is not None:
            compatible = _drag_can_connect_pair(port, target)
            target.set_error_visual(not compatible)
            self._drag_target = target

    def _port_drag_released(self, port: GraphPortItem) -> None:
        if self._drag_line is not None:
            self.graphics_scene.removeItem(self._drag_line)
            self._drag_line = None
        target = self._drag_target
        self._drag_target = None
        self._drag_port = None
        if target is None:
            return
        if sip.isdeleted(target):
            return
        target.set_error_visual(False)
        if _drag_can_connect_pair(port, target):
            if port.kind == "out":
                self.edgeRequested.emit(
                    port.owner_id, target.owner_id
                )
            else:
                self.edgeRequested.emit(
                    target.owner_id, port.owner_id
                )

    def _hit_port_at(self, scene_pos: QPointF, exclude: GraphPortItem) -> GraphPortItem | None:
        items = self.graphics_scene.items(scene_pos)
        for item in items:
            if isinstance(item, GraphPortItem) and item is not exclude:
                return item
        return None

    def _update_node_item(self, node_id: str) -> None:
        item = self._node_items.get(node_id)
        if item is not None:
            item.update()
        for edge_item in self._edge_items.values():
            edge_item.update()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            selected = self.graphics_scene.selectedItems()
            for item in selected:
                if isinstance(item, GraphNodeItem):
                    self.nodeRemoveRequested.emit(item.node_id)
                    event.accept()
                    return
                if isinstance(item, GraphEdgeItem):
                    self.edgeRemoveRequested.emit(item.edge_id)
                    event.accept()
                    return
        super().keyPressEvent(event)


def _drag_can_connect(source: GraphPortItem, target: GraphPortItem) -> bool:
    """True when ``source -> target`` is a valid out-to-in connection."""
    if source.kind != "out" or target.kind != "in":
        return False
    return source.port_type == target.port_type


def _drag_can_connect_pair(drag: GraphPortItem, target: GraphPortItem) -> bool:
    """Orientation-aware check for a drag started from either port kind."""
    if drag.kind == "out":
        return _drag_can_connect(drag, target)
    return _drag_can_connect(target, drag)


class GraphPlaceholder(QWidget):
    """Shown in graph mode when the document is still in recipe mode."""

    expandRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        hint = QLabel(
            "This pattern is in Recipe mode. Expand it into the typed "
            "behavior graph to edit nodes, ports, and connections."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        expand = QPushButton("Expand to Graph")
        expand.setObjectName("graphExpandButton")
        expand.clicked.connect(self.expandRequested)
        layout.addWidget(expand, 0, Qt.AlignLeft)
        layout.addStretch(1)

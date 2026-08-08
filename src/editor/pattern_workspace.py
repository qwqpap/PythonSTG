"""First-class M3 Pattern authoring context and diagnostic gizmos."""

from __future__ import annotations

import json
import math

from src.qt_compat.QtCore import QPointF, QRectF, Qt, pyqtSignal
from src.qt_compat.QtGui import QColor, QPainter, QPainterPath, QPen
from src.qt_compat.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGraphicsItem,
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

from src.authoring.coordinates import CoordinateSpace
from src.pattern import PatternDocument

from .resource_browser import RESOURCE_MIME_TYPE


class PatternGizmoItem(QGraphicsObject):
    positionCommitted = pyqtSignal(str, float, float)

    def __init__(self, role: str, color: str, label: str, parent=None):
        super().__init__(parent)
        self.role = role
        self.color = QColor(color)
        self.label = label
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.SizeAllCursor)
        self.setZValue(5)

    def boundingRect(self) -> QRectF:
        return QRectF(-18, -18, 36, 36)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QRectF(-12, -12, 24, 24))
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.color.lighter(140), 2 if self.isSelected() else 1))
        painter.setBrush(self.color)
        painter.drawEllipse(QRectF(-10, -10, 20, 20))
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawText(QRectF(-18, -7, 36, 14), Qt.AlignCenter, self.label)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            point = QPointF(value)
            bounds = self.scene().sceneRect()
            return QPointF(
                min(max(point.x(), bounds.left()), bounds.right()),
                min(max(point.y(), bounds.top()), bounds.bottom()),
            )
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.positionCommitted.emit(self.role, float(self.x()), float(self.y()))


class PatternCanvas(QGraphicsView):
    originPositionRequested = pyqtSignal(float, float)
    playerPositionRequested = pyqtSignal(float, float)
    bulletResourceDropped = pyqtSignal(str)

    def __init__(self, parent=None):
        self.graphics_scene = QGraphicsScene(parent)
        super().__init__(self.graphics_scene, parent)
        self.coordinate_space = CoordinateSpace()
        self._document: PatternDocument | None = None
        self._player_position = (0.0, -0.8)
        self._emitter: PatternGizmoItem | None = None
        self._player: PatternGizmoItem | None = None
        self._guides = True
        self.setObjectName("patternCanvas")
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setRenderHints(QPainter.Antialiasing)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.graphics_scene.setSceneRect(0, 0, 384, 448)

    def set_document(
        self,
        document: PatternDocument,
        *,
        player_position: tuple[float, float] = (0.0, -0.8),
    ) -> None:
        self._document = document
        self._player_position = player_position
        self.graphics_scene.clear()
        self._emitter = PatternGizmoItem("emitter", "#ffb45e", "E")
        self._player = PatternGizmoItem("player", "#65d6ff", "P")
        emitter_position = self.coordinate_space.runtime_to_authoring(
            document.shape.origin_x,
            document.shape.origin_y,
        )
        player_authoring = self.coordinate_space.runtime_to_authoring(*player_position)
        self._emitter.setPos(*emitter_position)
        self._player.setPos(*player_authoring)
        self._emitter.positionCommitted.connect(self._position_committed)
        self._player.positionCommitted.connect(self._position_committed)
        self.graphics_scene.addItem(self._emitter)
        self.graphics_scene.addItem(self._player)
        self.viewport().update()

    def set_guides(self, enabled: bool) -> None:
        self._guides = bool(enabled)
        self.viewport().update()

    def _position_committed(self, role: str, x: float, y: float) -> None:
        runtime_x, runtime_y = self.coordinate_space.authoring_to_runtime(x, y)
        if role == "emitter":
            self.originPositionRequested.emit(runtime_x, runtime_y)
        else:
            self._player_position = (runtime_x, runtime_y)
            self.playerPositionRequested.emit(runtime_x, runtime_y)
        self.viewport().update()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor("#111722"))
        bounds = self.graphics_scene.sceneRect()
        painter.setPen(QPen(QColor("#253044"), 0))
        for x in range(0, 385, 32):
            painter.drawLine(QPointF(x, bounds.top()), QPointF(x, bounds.bottom()))
        for y in range(0, 449, 32):
            painter.drawLine(QPointF(bounds.left(), y), QPointF(bounds.right(), y))
        painter.setPen(QPen(QColor("#5a6b84"), 1))
        painter.drawRect(bounds)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        del rect
        if not self._guides or self._document is None or self._emitter is None:
            return
        origin = self._emitter.pos()
        painter.setPen(QPen(QColor("#9ab6de"), 1, Qt.DashLine))
        if self._document.aim.mode == "player" and self._player is not None:
            target = self._player.pos()
        else:
            radians = math.radians(self._document.aim.angle)
            target = QPointF(
                origin.x() + math.cos(radians) * 130.0,
                origin.y() - math.sin(radians) * 130.0,
            )
        painter.drawLine(origin, target)
        painter.setPen(QPen(QColor("#8f9cff"), 1))
        radius = min(80.0, 16.0 + self._document.shape.count * 0.8)
        painter.drawEllipse(origin, radius, radius)

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
        if str(payload.get("kind")) != "sprite":
            event.ignore()
            return
        value = str(payload.get("resource_value") or "").strip()
        if not value:
            event.ignore()
            return
        self.bulletResourceDropped.emit(value)
        event.acceptProposedAction()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fitInView(
            self.graphics_scene.sceneRect().adjusted(-24, -24, 24, 24),
            Qt.KeepAspectRatio,
        )


class PatternWorkspace(QWidget):
    previewRequested = pyqtSignal()
    templateRequested = pyqtSignal(str)
    bulletResourceRequested = pyqtSignal(str)
    originPositionRequested = pyqtSignal(float, float)
    playerPositionRequested = pyqtSignal(float, float)
    graphModeChanged = pyqtSignal(str)
    graphExpandRequested = pyqtSignal()
    graphFoldRequested = pyqtSignal()
    graphNodeSelected = pyqtSignal(str)
    graphNodePropertyRequested = pyqtSignal(str, object)
    graphNodePositionRequested = pyqtSignal(str, float, float)
    graphNodeCreateRequested = pyqtSignal(str, str)
    graphEdgeRequested = pyqtSignal(str, str)
    graphNodeRemoveRequested = pyqtSignal(str)
    graphEdgeRemoveRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("patternWorkspace")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        primary_toolbar = QHBoxLayout()
        self.title = QLabel("Pattern")
        self.title.setObjectName("patternWorkspaceTitle")
        self.title.setStyleSheet("font-size:16px; font-weight:600;")
        primary_toolbar.addWidget(self.title)
        primary_toolbar.addStretch()
        self.mode_switch = QComboBox()
        self.mode_switch.setObjectName("patternModeSwitch")
        self.mode_switch.setToolTip(
            "Authoring mode: Recipe (fields) or Graph (behavior nodes)"
        )
        self.mode_switch.addItem("Recipe", "recipe")
        self.mode_switch.addItem("Graph", "graph")
        self.mode_switch.currentIndexChanged.connect(self._mode_changed)
        primary_toolbar.addWidget(self.mode_switch)
        self.fold_button = QPushButton("Fold back to Recipe")
        self.fold_button.setObjectName("graphFoldButton")
        self.fold_button.clicked.connect(self.graphFoldRequested)
        primary_toolbar.addWidget(self.fold_button)
        self.guides = QCheckBox("Guides")
        self.guides.setChecked(True)
        primary_toolbar.addWidget(self.guides)
        preview = QPushButton("Formal Preview")
        preview.setObjectName("patternFormalPreview")
        preview.clicked.connect(self.previewRequested)
        primary_toolbar.addWidget(preview)
        layout.addLayout(primary_toolbar)

        # Keep each authoring operation on its own row.  The central canvas is
        # intentionally narrow when both Scene and Inspector docks are visible
        # at the supported 960 px window width, so a single horizontal strip
        # would overlap its controls.
        authoring_toolbar = QGridLayout()
        authoring_toolbar.addWidget(QLabel("Bullet"), 0, 0)
        self.bullet_picker = QComboBox()
        self.bullet_picker.setObjectName("patternBulletPicker")
        # The field expands on desktop, but must still leave room for the
        # action button between the two persistent side docks at 960 px.
        self.bullet_picker.setMinimumWidth(100)
        self.bullet_picker.setToolTip("Bullet sprite resource (#fragment)")
        authoring_toolbar.addWidget(self.bullet_picker, 0, 1)
        assign = QPushButton("Assign Bullet")
        assign.setObjectName("patternAssignBullet")
        assign.clicked.connect(self._assign_bullet)
        authoring_toolbar.addWidget(assign, 0, 2)
        authoring_toolbar.addWidget(QLabel("Template"), 1, 0)
        self.template_picker = QComboBox()
        self.template_picker.setObjectName("patternTemplatePicker")
        self.template_picker.addItem("Starter Ring", "starter_ring")
        self.template_picker.addItem("Aimed Arc", "aimed_arc")
        self.template_picker.addItem("Spiral", "spiral")
        authoring_toolbar.addWidget(self.template_picker, 1, 1)
        apply_template = QPushButton("Apply Template")
        apply_template.setObjectName("patternApplyTemplate")
        apply_template.clicked.connect(
            lambda: self.templateRequested.emit(str(self.template_picker.currentData()))
        )
        authoring_toolbar.addWidget(apply_template, 1, 2)
        authoring_toolbar.setColumnStretch(1, 1)
        layout.addLayout(authoring_toolbar)

        self.graph_toolbar_widget = QWidget()
        self.graph_toolbar_widget.setObjectName("graphToolbar")
        self.graph_toolbar = QGridLayout(self.graph_toolbar_widget)
        self.graph_toolbar.setContentsMargins(0, 0, 0, 0)
        self.graph_toolbar.addWidget(QLabel("Add Node"), 0, 0)
        from .graph_workspace import CREATABLE_NODE_CATEGORIES, GraphCanvas, GraphPlaceholder

        self._creatable_node_categories = CREATABLE_NODE_CATEGORIES
        self.node_type_picker = QComboBox()
        self.node_type_picker.setObjectName("graphNodeTypePicker")
        for category, node_type in self._creatable_node_categories:
            self.node_type_picker.addItem(category.title(), (category, node_type))
        self.graph_toolbar.addWidget(self.node_type_picker, 0, 1)
        add_node = QPushButton("Add")
        add_node.setObjectName("graphAddNode")
        add_node.clicked.connect(self._request_add_node)
        self.graph_toolbar.addWidget(add_node, 0, 2)
        self.graph_toolbar.addWidget(QLabel("Tip"), 1, 0)
        tip = QLabel("Drag between ports to connect. Del removes selection.")
        tip.setObjectName("graphWorkspaceHint")
        tip.setWordWrap(True)
        self.graph_toolbar.addWidget(tip, 1, 1, 1, 2)
        self.graph_toolbar.setColumnStretch(1, 1)
        self.graph_toolbar_widget.setVisible(False)
        layout.addWidget(self.graph_toolbar_widget)

        hint = QLabel(
            "Drag E/P gizmos. Drop an Assets sprite to assign."
        )
        hint.setObjectName("patternWorkspaceHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.canvas = PatternCanvas()
        self.canvas.originPositionRequested.connect(self.originPositionRequested)
        self.canvas.playerPositionRequested.connect(self.playerPositionRequested)
        self.canvas.bulletResourceDropped.connect(self.bulletResourceRequested)
        self.guides.toggled.connect(self.canvas.set_guides)

        from .graph_workspace import GraphCanvas, GraphPlaceholder

        self.graph_canvas = GraphCanvas()
        self.graph_canvas.nodeSelected.connect(self.graphNodeSelected)
        self.graph_canvas.nodePositionCommitted.connect(
            self.graphNodePositionRequested
        )
        self.graph_canvas.edgeRequested.connect(self.graphEdgeRequested)
        self.graph_canvas.nodeRemoveRequested.connect(self.graphNodeRemoveRequested)
        self.graph_canvas.edgeRemoveRequested.connect(self.graphEdgeRemoveRequested)
        self.graph_placeholder = GraphPlaceholder()
        self.graph_placeholder.expandRequested.connect(self.graphExpandRequested)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.canvas)
        self.stack.addWidget(self.graph_canvas)
        self.stack.addWidget(self.graph_placeholder)
        layout.addWidget(self.stack, 1)
        self._mode = "recipe"
        self._document: PatternDocument | None = None
        self._player_position = (0.0, -0.8)
        self._mode_switching = False

    def _mode_changed(self) -> None:
        mode = str(self.mode_switch.currentData())
        if mode == self._mode:
            return
        self._mode = mode
        self._refresh_mode()
        self.graphModeChanged.emit(mode)

    def _refresh_mode(self) -> None:
        self._mode_switching = True
        try:
            document = self._document
            if self._mode == "graph":
                self.fold_button.setVisible(True)
                self.graph_toolbar_widget.setVisible(True)
                if document is not None and document.graph is not None:
                    self.graph_canvas.set_graph(document.graph)
                    self.stack.setCurrentWidget(self.graph_canvas)
                else:
                    self.stack.setCurrentWidget(self.graph_placeholder)
            else:
                self.fold_button.setVisible(False)
                self.graph_toolbar_widget.setVisible(False)
                self.stack.setCurrentWidget(self.canvas)
        finally:
            self._mode_switching = False

    def _request_add_node(self) -> None:
        category, node_type = self.node_type_picker.currentData()
        self.graphNodeCreateRequested.emit(str(category), str(node_type))

    def set_document(
        self,
        document: PatternDocument,
        *,
        player_position: tuple[float, float] = (0.0, -0.8),
    ) -> None:
        self._document = document
        self._player_position = player_position
        self.title.setText(document.name)
        self.canvas.set_document(document, player_position=player_position)
        index = self.bullet_picker.findData(document.bullet.resource)
        if index >= 0:
            self.bullet_picker.setCurrentIndex(index)
        self._refresh_mode()

    def set_mode(self, mode: str, *, emit: bool = True) -> None:
        mode = str(mode)
        if mode not in {"recipe", "graph"}:
            raise ValueError(f"unsupported pattern workspace mode: {mode!r}")
        if emit:
            index = self.mode_switch.findData(mode)
            if index >= 0 and index != self.mode_switch.currentIndex():
                self.mode_switch.setCurrentIndex(index)
            elif index == self.mode_switch.currentIndex():
                self._mode = mode
                self._refresh_mode()
        else:
            self._mode = mode
            self._refresh_mode()

    def mode(self) -> str:
        return self._mode

    def refresh_graph(self) -> None:
        if self._mode == "graph" and self._document is not None:
            if self._document.graph is not None:
                self.graph_canvas.set_graph(self._document.graph)
                self.stack.setCurrentWidget(self.graph_canvas)
            else:
                self.stack.setCurrentWidget(self.graph_placeholder)

    def select_graph_node(self, node_id: str) -> None:
        self.graph_canvas.select_node(node_id)

    def set_graph_diagnostics(self, node_ids: tuple[str, ...], edge_ids: tuple[str, ...]) -> None:
        if self._mode == "graph":
            self.graph_canvas.set_diagnostics(node_ids, edge_ids)

    def clear_graph_diagnostics(self) -> None:
        self.graph_canvas.clear_diagnostics()

    def set_available_bullets(self, records) -> None:
        current = self.bullet_picker.currentData()
        self.bullet_picker.clear()
        self.bullet_picker.addItem("Choose bullet sprite…", None)
        for record in records:
            if getattr(record, "kind", None) == "sprite":
                self.bullet_picker.addItem(record.name, record.resource_value)
        index = self.bullet_picker.findData(current)
        if index >= 0:
            self.bullet_picker.setCurrentIndex(index)

    def _assign_bullet(self) -> None:
        value = self.bullet_picker.currentData()
        if value:
            self.bulletResourceRequested.emit(str(value))

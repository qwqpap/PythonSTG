"""First-class M3 Pattern authoring context and diagnostic gizmos."""

from __future__ import annotations

import json
import math

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
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
        layout.addWidget(self.canvas, 1)

    def set_document(
        self,
        document: PatternDocument,
        *,
        player_position: tuple[float, float] = (0.0, -0.8),
    ) -> None:
        self.title.setText(document.name)
        self.canvas.set_document(document, player_position=player_position)
        index = self.bullet_picker.findData(document.bullet.resource)
        if index >= 0:
            self.bullet_picker.setCurrentIndex(index)

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

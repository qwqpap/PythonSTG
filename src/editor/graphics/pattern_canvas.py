"""Pattern authoring canvas and diagnostic gizmos (shared graphics primitive).

Moved out of ``pattern_workspace`` in ER6.0 so both ``pattern_workspace`` and
``graph_workspace`` can depend on it from below instead of importing each other.
The class bodies are unchanged from their original home; only the module they
live in moved, so author-document semantics and the Qt behaviour are identical.
"""

from __future__ import annotations

import json
import math

from src.qt_compat.QtCore import QPointF, QRectF, Qt, pyqtSignal
from src.qt_compat.QtGui import QColor, QPainter, QPainterPath, QPen
from src.qt_compat.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
)

from src.authoring.coordinates import CoordinateSpace
from src.pattern import PatternDocument

from ..resource_browser import RESOURCE_MIME_TYPE


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

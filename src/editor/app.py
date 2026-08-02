"""Godot-inspired PyQt scene editor shell for PySTG."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QPointF, QProcess, QRectF, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.project_context import ProjectContext
from src.authoring.coordinates import CoordinateSpace
from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.pattern import PatternDocument

from .asset_index import AssetRecord, load_subresource_preview
from .document import (
    DocumentError,
    EditorNode,
    SceneDocument,
    TimelineClip,
    TimelineKeyframe,
    TimelineTrack,
)
from .node_types import NODE_TYPES, PropertySpec, make_node, property_specs
from .preview_panel import PatternPreviewPanel
from .preview_process import PatternPreviewProcess
from .document_manager import (
    DocumentManager,
    DocumentManagerError,
    ManagedDocument,
)
from .pattern_commands import SetPatternPropertyCommand
from .pattern_workspace import PatternWorkspace
from .resource_browser import RESOURCE_MIME_TYPE, ResourceBrowserPanel
from .scene_commands import (
    AddNodeCommand,
    AssignResourceCommand,
    MoveNodeCommand,
    RemoveNodeCommand,
    RenameNodeCommand,
    SceneMutationError,
    SetNodePropertiesCommand,
    SetNodePropertyCommand,
    find_parent,
)
from .scene_compile import SceneSpellCompileError, compile_simple_spell
from .timeline_commands import (
    AddClipCommand,
    AddTrackCommand,
    MoveResizeClipCommand,
    RemoveClipCommand,
    SetClipPropertiesCommand,
    clone_clip_with_new_ids,
    find_clip,
    require_track,
)
from .timeline_workspace import TimelineEditor
from .workbench import EditorPlugin, PluginRegistry, default_external_plugins


APP_NAME = "PySTG Editor"
RESOURCE_FILTER = "PySTG Resources (*.pystg.json);;JSON (*.json)"
SCENE_FILTER = RESOURCE_FILTER


def build_preview_command(
    project: ProjectContext,
    document: SceneDocument,
    node: EditorNode | None,
) -> tuple[list[str], str]:
    if node is not None and node.type == "SpellCard":
        script_value = str(node.properties.get("script", "")).strip()
        if not script_value:
            raise ValueError("Selected SpellCard needs a script path.")
        try:
            reference = ResourceReference.parse(
                script_value,
                allow_legacy_project_path=True,
            )
            if reference.subresource is not None:
                raise ResourceDocumentError("script references cannot use fragments")
            script_path = reference.resolve(project)
        except ResourceDocumentError as exc:
            raise ValueError(str(exc)) from exc
        if not script_path.is_file():
            raise ValueError(f"SpellCard script does not exist: {script_path}")
        arguments = [
            str(project.root / "tools" / "preview_spell.py"),
            str(script_path),
        ]
        class_name = str(node.properties.get("class_name", "")).strip()
        if class_name:
            arguments.extend(["--spell", class_name])
        return arguments, f"spell preview: {script_path.name}"

    stage = str(document.metadata.get("preview_stage", "stage1"))
    return (
        [
            str(project.root / "main.py"),
            f"--stage={stage}",
            f"--project={project.root}",
            "--hot-reload",
        ],
        f"runtime preview: {stage}",
    )


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
    ):
        super().__init__()
        self.node_id = node.id
        self.node_type = node.type
        self.node_name = node.name
        self.grid_size = max(1, grid_size)
        self._drag_start = QPointF()
        self._spec = NODE_TYPES.get(node.type)
        self._pixmap = self._load_pixmap(node, project)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.OpenHandCursor)
        self.setZValue(10)

    @staticmethod
    def _load_pixmap(node: EditorNode, project: ProjectContext) -> QPixmap:
        spec = NODE_TYPES.get(node.type)
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
        painter.setPen(QPen(QColor("#f5f7ff") if self.isSelected() else color, 3 if self.isSelected() else 2))
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
        painter.drawText(QRectF(-70, 34, 140, 22), Qt.AlignHCenter | Qt.AlignTop, self.node_name)

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


class SceneViewport(QGraphicsView):
    nodeSelected = pyqtSignal(str)
    nodePositionRequested = pyqtSignal(str, float, float)
    resourceDropped = pyqtSignal(object, float, float)

    def __init__(self, project: ProjectContext, parent=None):
        self.graphics_scene = QGraphicsScene(parent)
        super().__init__(self.graphics_scene, parent)
        self.project = project
        self._document: SceneDocument | None = None
        self._items: dict[str, NodeGraphicsItem] = {}
        self._grid_size = 16
        self._background = QColor("#171a24")
        self.coordinate_space = CoordinateSpace()
        self._fit_on_next_resize = True
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
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
            spec = NODE_TYPES.get(node.type)
            if spec is None or not spec.viewport_item:
                continue
            item = NodeGraphicsItem(node, self.project, self._grid_size)
            item.setPos(
                float(node.properties.get("x", width / 2)),
                float(node.properties.get("y", height / 2)),
            )
            item.positionCommitted.connect(self.nodePositionRequested)
            self.graphics_scene.addItem(item)
            self._items[node.id] = item

        self.viewport().update()
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

    def _selection_changed(self) -> None:
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
        scene_position = self.mapToScene(event.pos())
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


class ResourceLineEdit(QLineEdit):
    """Line edit that accepts typed resource drags from the Assets panel."""

    def __init__(self, accepted_kinds: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.accepted_kinds = accepted_kinds
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(RESOURCE_MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

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
        if str(payload.get("kind")) not in self.accepted_kinds:
            event.ignore()
            return
        value = str(payload.get("resource_value") or "").strip()
        if not value:
            event.ignore()
            return
        self.setText(value)
        self.editingFinished.emit()
        event.acceptProposedAction()


class InspectorPanel(QScrollArea):
    renameRequested = pyqtSignal(str, str)
    propertyRequested = pyqtSignal(str, str, object)
    patternPropertyRequested = pyqtSignal(str, object)
    timelineClipPropertiesRequested = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._content = QWidget()
        self._form = QFormLayout(self._content)
        self._form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self._form.setContentsMargins(12, 12, 12, 12)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(self._content)
        self._node_id: str | None = None
        self._pattern_id: str | None = None
        self._timeline_clip_id: str | None = None

    def _clear_form(self) -> None:
        while self._form.count():
            item = self._form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_node(self, node: EditorNode | None) -> None:
        self._clear_form()
        self._node_id = node.id if node else None
        self._pattern_id = None
        self._timeline_clip_id = None
        if node is None:
            self._form.addRow(QLabel("No node selected"))
            return

        name_edit = QLineEdit(node.name)
        name_edit.setObjectName("inspectorName")
        name_edit.editingFinished.connect(
            lambda edit=name_edit, node_id=node.id: self.renameRequested.emit(
                node_id,
                edit.text(),
            )
        )
        self._form.addRow("Name", name_edit)

        type_edit = QLineEdit(node.type)
        type_edit.setReadOnly(True)
        self._form.addRow("Type", type_edit)

        for spec in property_specs(node.type):
            value = node.properties.get(spec.key, spec.default)
            editor = self._make_editor(node.id, spec, value)
            self._form.addRow(spec.label, editor)

        known = {spec.key for spec in property_specs(node.type)}
        extras = {
            key: value
            for key, value in node.properties.items()
            if key not in known
        }
        if extras:
            extra_label = QLabel(json.dumps(extras, ensure_ascii=False, indent=2))
            extra_label.setWordWrap(True)
            extra_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._form.addRow("Other", extra_label)

    def set_pattern(self, document: PatternDocument) -> None:
        """Show grouped recipe controls for the active Pattern document."""
        self._clear_form()
        self._node_id = None
        self._pattern_id = document.id
        self._timeline_clip_id = None
        title = QLabel(f"Pattern Preview: {document.name}")
        title.setObjectName("inspectorPatternTitle")
        self._form.addRow(title)
        payload = document.to_dict()
        seed_editor = self._make_pattern_editor("seed", payload["seed"])
        self._form.addRow(self._pattern_label("seed"), seed_editor)
        for section in ("bullet", "shape", "aim", "schedule", "motion", "modifiers"):
            section_title = QLabel(
                ("Advanced · " if section == "modifiers" else "")
                + section.replace("_", " ").title()
            )
            section_title.setObjectName(f"patternSection_{section}")
            section_title.setStyleSheet(
                "font-weight:600; color:#9fc5ff; margin-top:8px;"
            )
            self._form.addRow(section_title)
            section_fields = [
                (f"{section}.{key}", value)
                for key, value in payload[section].items()
            ]
            for path, value in section_fields:
                editor = self._make_pattern_editor(path, value)
                self._form.addRow(self._pattern_label(path), editor)

    def set_timeline_clip(
        self,
        track: TimelineTrack,
        clip: TimelineClip,
        nodes: list[EditorNode],
    ) -> None:
        self._clear_form()
        self._node_id = None
        self._pattern_id = None
        self._timeline_clip_id = clip.id
        title = QLabel(f"{track.name} / {clip.kind} Clip")
        title.setStyleSheet("font-weight:600; color:#9fc5ff;")
        self._form.addRow(title)

        name = QLineEdit(clip.name)
        name.setObjectName("timelineClipName")
        name.editingFinished.connect(
            lambda edit=name, clip_id=clip.id: self.timelineClipPropertiesRequested.emit(
                clip_id, {"name": edit.text().strip()}
            )
        )
        self._form.addRow("Name", name)
        kind = QLineEdit(clip.kind)
        kind.setReadOnly(True)
        self._form.addRow("Kind", kind)

        for label, key, value, minimum in (
            ("Start [frame]", "start_frame", clip.start_frame, 0),
            ("Duration [frame]", "duration_frames", clip.duration_frames, 1),
            ("Loop Count", "loop_count", clip.loop_count, 1),
            ("Order", "order", clip.order, 0),
        ):
            spin = QSpinBox()
            spin.setObjectName("timelineClip_" + key)
            spin.setRange(minimum, 1_000_000)
            spin.setValue(int(value))
            spin.editingFinished.connect(
                lambda editor=spin, clip_id=clip.id, field=key: self.timelineClipPropertiesRequested.emit(
                    clip_id, {field: editor.value()}
                )
            )
            self._form.addRow(label, spin)

        enabled = QCheckBox()
        enabled.setChecked(clip.enabled)
        enabled.toggled.connect(
            lambda checked, clip_id=clip.id: self.timelineClipPropertiesRequested.emit(
                clip_id, {"enabled": checked}
            )
        )
        self._form.addRow("Enabled", enabled)

        target = QComboBox()
        target.setObjectName("timelineClipTarget")
        target.addItem("(inherit / none)", None)
        for node in nodes:
            target.addItem(f"{node.name} [{node.type}]", node.id)
        target_index = target.findData(clip.target_id)
        target.setCurrentIndex(max(0, target_index))
        target.activated.connect(
            lambda _index, combo=target, clip_id=clip.id: self.timelineClipPropertiesRequested.emit(
                clip_id, {"target_id": combo.currentData()}
            )
        )
        self._form.addRow("Target", target)

        channel = QLineEdit(clip.channel)
        channel.setObjectName("timelineClipChannel")
        channel.editingFinished.connect(
            lambda edit=channel, clip_id=clip.id: self.timelineClipPropertiesRequested.emit(
                clip_id, {"channel": edit.text().strip()}
            )
        )
        self._form.addRow("Channel", channel)

        error = QLabel("")
        error.setObjectName("timelineClipJsonError")
        error.setStyleSheet("color:#ff9ca8;")
        error.setWordWrap(True)
        payload = QPlainTextEdit(json.dumps(clip.payload, ensure_ascii=False, indent=2))
        payload.setObjectName("timelineClipPayload")
        payload.setMinimumHeight(100)
        self._form.addRow("Payload [JSON]", payload)
        apply_payload = QPushButton("Apply Payload")

        def commit_payload() -> None:
            try:
                value = json.loads(payload.toPlainText())
                if not isinstance(value, dict):
                    raise ValueError("Payload must be a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                error.setText(str(exc))
                return
            error.clear()
            self.timelineClipPropertiesRequested.emit(clip.id, {"payload": value})

        apply_payload.clicked.connect(commit_payload)
        self._form.addRow(apply_payload)

        keyframes = QPlainTextEdit(
            json.dumps(
                [item.to_dict() for item in clip.keyframes],
                ensure_ascii=False,
                indent=2,
            )
        )
        keyframes.setObjectName("timelineClipKeyframes")
        keyframes.setMinimumHeight(120)
        self._form.addRow("Keyframes [JSON]", keyframes)
        apply_keyframes = QPushButton("Apply Keyframes")

        def commit_keyframes() -> None:
            try:
                value = json.loads(keyframes.toPlainText())
                if not isinstance(value, list):
                    raise ValueError("Keyframes must be a JSON array")
                parsed = [TimelineKeyframe.from_dict(item).to_dict() for item in value]
            except (json.JSONDecodeError, ValueError, DocumentError) as exc:
                error.setText(str(exc))
                return
            error.clear()
            self.timelineClipPropertiesRequested.emit(clip.id, {"keyframes": parsed})

        apply_keyframes.clicked.connect(commit_keyframes)
        self._form.addRow(apply_keyframes)
        self._form.addRow(error)

    @staticmethod
    def _pattern_label(path: str) -> str:
        units = {
            "shape.origin_x": "runtime",
            "shape.origin_y": "runtime",
            "shape.angle_span": "deg",
            "shape.line_length": "runtime",
            "shape.line_angle": "deg",
            "aim.angle": "deg",
            "schedule.delay_frames": "frame",
            "schedule.interval_frames": "frame",
            "motion.speed": "unit/s",
            "motion.spin": "deg/s",
            "motion.max_lifetime": "s",
            "modifiers.angle_offset_per_burst": "deg/burst",
        }
        label = path.split(".")[-1].replace("_", " ").title()
        unit = units.get(path)
        return f"{label} [{unit}]" if unit else label

    def _make_pattern_editor(self, path: str, value):
        choices = {
            "shape.kind": ("ring", "arc", "line", "spiral", "random", "flower"),
            "aim.mode": ("fixed", "player"),
        }
        if path in choices:
            editor = QComboBox()
            editor.addItems(list(choices[path]))
            editor.setCurrentText(str(value))
            editor.currentTextChanged.connect(
                lambda text, key=path: self.patternPropertyRequested.emit(key, text)
            )
        elif isinstance(value, bool):
            editor = QCheckBox()
            editor.setChecked(value)
            editor.toggled.connect(
                lambda checked, key=path: self.patternPropertyRequested.emit(key, checked)
            )
        elif isinstance(value, float):
            editor = QDoubleSpinBox()
            editor.setDecimals(6)
            editor.setRange(-1_000_000_000.0, 1_000_000_000.0)
            editor.setSingleStep(0.1)
            editor.setValue(value)
            editor.editingFinished.connect(
                lambda spin=editor, key=path: self.patternPropertyRequested.emit(key, spin.value())
            )
        else:
            text = "" if value is None else str(value)
            if path == "bullet.resource":
                editor = ResourceLineEdit(("sprite",))
                editor.setPlaceholderText("Drop a sprite from Assets")
                editor.setText(text)
            else:
                editor = QLineEdit(text)

            def commit(edit=editor, key=path, original=value):
                raw = edit.text().strip()
                if original is None:
                    parsed = None if raw in {"", "null", "None"} else raw
                elif isinstance(original, int):
                    try:
                        parsed = int(raw)
                    except ValueError:
                        return
                else:
                    parsed = raw
                self.patternPropertyRequested.emit(key, parsed)

            editor.editingFinished.connect(commit)
        editor.setObjectName("patternProperty_" + path.replace(".", "_"))
        return editor

    def _make_editor(self, node_id: str, spec: PropertySpec, value):
        if spec.value_type is bool:
            editor = QCheckBox()
            editor.setChecked(bool(value))
            editor.toggled.connect(
                lambda checked, nid=node_id, key=spec.key: self.propertyRequested.emit(
                    nid,
                    key,
                    checked,
                )
            )
            return editor
        if spec.value_type is int:
            editor = QSpinBox()
            editor.setRange(int(spec.minimum or -2_147_483_648), int(spec.maximum or 2_147_483_647))
            editor.setSingleStep(max(1, int(spec.step or 1)))
            editor.setValue(int(value))
            editor.editingFinished.connect(
                lambda spin=editor, nid=node_id, key=spec.key: self.propertyRequested.emit(
                    nid,
                    key,
                    spin.value(),
                )
            )
            return editor
        if spec.value_type is float:
            editor = QDoubleSpinBox()
            editor.setDecimals(3)
            editor.setRange(
                float(spec.minimum if spec.minimum is not None else -1_000_000_000),
                float(spec.maximum if spec.maximum is not None else 1_000_000_000),
            )
            editor.setSingleStep(float(spec.step or 0.1))
            editor.setValue(float(value))
            editor.editingFinished.connect(
                lambda spin=editor, nid=node_id, key=spec.key: self.propertyRequested.emit(
                    nid,
                    key,
                    spin.value(),
                )
            )
            return editor

        if spec.resource_types:
            kinds: list[str] = []
            for resource_type in spec.resource_types:
                if resource_type.startswith("pystg."):
                    kinds.append(resource_type.split(".", 1)[1])
                else:
                    kinds.append(resource_type)
            editor = ResourceLineEdit(tuple(kinds))
            editor.setPlaceholderText("Drop a compatible resource from Assets")
            editor.setText(str(value))
        else:
            editor = QLineEdit(str(value))
        editor.editingFinished.connect(
            lambda edit=editor, nid=node_id, key=spec.key: self.propertyRequested.emit(
                nid,
                key,
                edit.text(),
            )
        )
        return editor


class EditorMainWindow(QMainWindow):
    def __init__(self, project: ProjectContext):
        super().__init__()
        self.project = project
        self.document_manager = DocumentManager(project)
        self._fallback_selected_id = ""
        self._selected_id = self.session.document.root.id
        self._syncing_selection = False
        self._preview_process: QProcess | None = None
        self._pattern_preview_client = PatternPreviewProcess(project, parent=self)
        self._active_pattern_document: PatternDocument | None = None
        self._active_pattern_session: ManagedDocument | None = None
        self._active_pattern_resource = ""
        self._preview_pending_properties: dict[str, tuple[str, object]] = {}
        self._tool_processes: dict[str, QProcess] = {}
        self._plugin_widgets: dict[str, QWidget] = {}
        self._document_widgets: dict[str, QWidget] = {}
        self.plugin_registry = PluginRegistry(project)
        self._register_plugins()
        self._build_actions()
        self._build_ui()
        self._connect_pattern_preview()
        self._apply_theme()
        self._refresh()
        self.resize(1480, 920)
        self.setMinimumSize(960, 640)

    @property
    def session(self) -> ManagedDocument:
        session = self.document_manager.active
        if session is None:
            raise DocumentManagerError("No active document")
        return session

    @property
    def _selected_id(self) -> str:
        session = self.document_manager.active
        if session is None:
            return self._fallback_selected_id
        return session.selected_id or session.default_selection

    @_selected_id.setter
    def _selected_id(self, value: str) -> None:
        self._fallback_selected_id = str(value)
        session = self.document_manager.active
        if session is not None:
            session.selected_id = str(value)

    def _register_plugins(self) -> None:
        self.plugin_registry.register(
            EditorPlugin(
                id="resource_browser",
                title="Assets",
                description="Browse project files and JSON sprite/animation subresources.",
                mode="bottom",
                factory=lambda: ResourceBrowserPanel(self.project),
            )
        )
        self.plugin_registry.register(
            EditorPlugin(
                id="bullet_aliases",
                title="Bullet Aliases",
                description="Edit bullet type and color to sprite mappings.",
                mode="central",
                factory=self._create_bullet_alias_editor,
            )
        )
        for plugin in default_external_plugins(self.project):
            self.plugin_registry.register(plugin)

    @staticmethod
    def _create_bullet_alias_editor() -> QWidget:
        from tools.bullet.bullet_alias_manager import BulletAliasManager

        editor = BulletAliasManager()
        editor.setWindowFlags(Qt.Widget)
        return editor

    def _build_actions(self) -> None:
        self.action_new = self._action("New Scene", QKeySequence.New, self.new_scene)
        self.action_new_pattern = self._action("New Pattern", "Ctrl+Shift+N", self.new_pattern)
        self.action_open = self._action("Open Resource…", QKeySequence.Open, self.open_resource)
        self.action_save = self._action("Save", QKeySequence.Save, self.save_scene)
        self.action_save_as = self._action("Save As…", QKeySequence.SaveAs, self.save_scene_as)
        self.action_revert = self._action("Revert", None, self.revert_document)
        self.action_close_document = self._action("Close Document", QKeySequence.Close, self.close_active_document)
        self.action_undo = self._action("Undo", QKeySequence.Undo, self.undo)
        self.action_redo = self._action("Redo", QKeySequence.Redo, self.redo)
        self.action_delete = self._action("Delete Node", QKeySequence.Delete, self.delete_selected)
        self.action_rename = self._action("Rename Node", Qt.Key_F2, self.rename_selected)
        self.action_move_up = self._action("Move Up", "Alt+Up", lambda: self.move_selected(-1))
        self.action_move_down = self._action("Move Down", "Alt+Down", lambda: self.move_selected(1))
        self.action_outdent = self._action("Move to Parent", "Alt+Left", self.outdent_selected)
        self.action_indent = self._action("Make Child of Previous", "Alt+Right", self.indent_selected)
        self.action_run = self._action("Run / Preview", Qt.Key_F6, self.run_preview)
        self.action_fit = self._action("Frame Canvas", "F", self._fit_viewport)

    def _action(self, text: str, shortcut, callback: Callable) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        self.addAction(action)
        return action

    def _build_ui(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions([
            self.action_new,
            self.action_new_pattern,
            self.action_open,
            self.action_save,
            self.action_save_as,
            self.action_revert,
            self.action_close_document,
        ])
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([
            self.action_undo,
            self.action_redo,
            self.action_rename,
            self.action_delete,
            self.action_move_up,
            self.action_move_down,
            self.action_outdent,
            self.action_indent,
        ])
        run_menu = self.menuBar().addMenu("&Run")
        run_menu.addActions([self.action_run, self.action_fit])
        tools_menu = self.menuBar().addMenu("&Tools")
        for plugin in self.plugin_registry.all():
            action = tools_menu.addAction(plugin.title)
            action.setObjectName(f"pluginAction_{plugin.id}")
            action.setToolTip(plugin.description)
            if plugin.shortcut:
                action.setShortcut(plugin.shortcut)
            action.triggered.connect(
                lambda checked=False, plugin_id=plugin.id: self.open_plugin(plugin_id)
            )

        main_toolbar = QToolBar("Main", self)
        main_toolbar.setObjectName("mainToolbar")
        main_toolbar.setMovable(False)
        main_toolbar.addActions([
            self.action_new,
            self.action_open,
            self.action_save,
        ])
        main_toolbar.addSeparator()
        main_toolbar.addActions([self.action_undo, self.action_redo])
        main_toolbar.addSeparator()
        main_toolbar.addAction(self.action_run)
        self.addToolBar(main_toolbar)

        self.central_tabs = QTabWidget()
        self.central_tabs.setObjectName("centralWorkbench")
        self.central_tabs.setTabsClosable(True)
        self.central_tabs.tabCloseRequested.connect(self._close_central_tab)
        self.central_tabs.currentChanged.connect(self._central_tab_changed)
        initial_widget = self._add_document_tab(self.session)
        self.viewport = initial_widget
        self.setCentralWidget(self.central_tabs)

        self.tree = SceneTreeWidget()
        self.tree.currentItemChanged.connect(self._select_from_tree)
        self.tree.itemChanged.connect(self._tree_item_changed)
        self.tree.nodeMoveRequested.connect(self._move_from_tree)

        tree_content = QWidget()
        tree_layout = QVBoxLayout(tree_content)
        tree_layout.setContentsMargins(4, 4, 4, 4)
        tree_buttons = QHBoxLayout()
        add_button = QToolButton()
        add_button.setText("+ Add")
        add_button.setPopupMode(QToolButton.InstantPopup)
        add_menu = QMenu(add_button)
        quick_flow = add_menu.addAction("Simple Spell Setup")
        quick_flow.setObjectName("addSimpleSpellFlow")
        quick_flow.triggered.connect(self.create_simple_spell_flow)
        add_menu.addSeparator()
        for type_name, spec in NODE_TYPES.items():
            if type_name == "SceneRoot":
                continue
            action = add_menu.addAction(spec.display_name)
            action.triggered.connect(
                lambda checked=False, node_type=type_name: self.add_node(node_type)
            )
        add_button.setMenu(add_menu)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.delete_selected)
        tree_buttons.addWidget(add_button)
        tree_buttons.addWidget(delete_button)
        tree_buttons.addStretch()
        tree_layout.addLayout(tree_buttons)
        hierarchy_buttons = QHBoxLayout()
        for text, tooltip, action in (
            ("↑", "Move up (Alt+Up)", self.action_move_up),
            ("↓", "Move down (Alt+Down)", self.action_move_down),
            ("←", "Move to parent (Alt+Left)", self.action_outdent),
            ("→", "Make child of previous node (Alt+Right)", self.action_indent),
        ):
            button = QToolButton()
            button.setText(text)
            button.setFixedWidth(44)
            button.setToolTip(tooltip)
            button.clicked.connect(
                lambda checked=False, target=action: target.trigger()
            )
            hierarchy_buttons.addWidget(button)
        hierarchy_buttons.addStretch()
        tree_layout.addLayout(hierarchy_buttons)
        tree_layout.addWidget(self.tree)

        tree_dock = QDockWidget("Scene", self)
        tree_dock.setObjectName("sceneDock")
        tree_dock.setWidget(tree_content)
        tree_dock.setMinimumWidth(220)
        self.addDockWidget(Qt.LeftDockWidgetArea, tree_dock)

        self.inspector = InspectorPanel()
        self.inspector.renameRequested.connect(self.rename_node)
        self.inspector.propertyRequested.connect(self.set_node_property)
        self.inspector.patternPropertyRequested.connect(self._pattern_property_requested)
        self.inspector.timelineClipPropertiesRequested.connect(
            self._timeline_clip_properties_requested
        )
        inspector_dock = QDockWidget("Inspector", self)
        inspector_dock.setObjectName("inspectorDock")
        inspector_dock.setWidget(self.inspector)
        inspector_dock.setMinimumWidth(260)
        self.addDockWidget(Qt.RightDockWidgetArea, inspector_dock)

        self.output = QTextBrowser()
        self.output.setReadOnly(True)
        self.output.setOpenLinks(False)
        self.output.anchorClicked.connect(self._diagnostic_link_clicked)
        self.output.document().setMaximumBlockCount(1000)
        self.timeline = TimelineEditor()
        self.timeline.addTrackRequested.connect(self._timeline_add_track)
        self.timeline.addClipRequested.connect(self._timeline_add_clip)
        self.timeline.clipGeometryRequested.connect(self._timeline_clip_geometry)
        self.timeline.duplicateClipRequested.connect(self._timeline_duplicate_clip)
        self.timeline.deleteClipRequested.connect(self._timeline_delete_clip)
        self.timeline.clipSelected.connect(self._timeline_clip_selected)
        self.timeline.playheadChanged.connect(self._timeline_playhead_changed)
        self.timeline.zoomChanged.connect(self._timeline_zoom_changed)
        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.setObjectName("bottomWorkbench")
        self.bottom_tabs.addTab(self.output, "Output")
        self.bottom_tabs.addTab(self.timeline, "Timeline")
        self.preview_panel = PatternPreviewPanel()
        self.preview_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.preview_panel.launchRequested.connect(self._launch_active_preview)
        self.preview_panel.commandRequested.connect(self._send_pattern_preview_command)
        self.preview_panel.propertyRequested.connect(self._pattern_property_requested)
        self.bottom_tabs.addTab(self.preview_panel, "Preview")
        for plugin in self.plugin_registry.by_mode("bottom"):
            widget = plugin.factory()
            self._plugin_widgets[plugin.id] = widget
            self.bottom_tabs.addTab(widget, plugin.title)
            if plugin.id == "resource_browser":
                self.resource_browser = widget
                # Bottom pages must not impose their full content size hint on
                # the entire dock.  They remain vertically resizable and their
                # own scroll areas expose content at compact window sizes.
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
                widget.resourceSelected.connect(self._resource_selected)
                widget.resourceActivated.connect(self._resource_activated)
        self.bottom_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        bottom_dock = QDockWidget("Bottom Panel", self)
        self.bottom_dock = bottom_dock
        bottom_dock.setObjectName("bottomDock")
        bottom_dock.setWidget(self.bottom_tabs)
        bottom_dock.setMinimumHeight(180)
        self.addDockWidget(Qt.BottomDockWidgetArea, bottom_dock)
        self.resizeDocks([bottom_dock], [220], Qt.Vertical)

        self.statusBar().showMessage(str(self.project.root))

    def _add_document_tab(self, session: ManagedDocument) -> QWidget:
        existing = self._document_widgets.get(session.document.id)
        if existing is not None:
            self.central_tabs.setCurrentWidget(existing)
            return existing
        if isinstance(session.document, SceneDocument):
            widget: QWidget = SceneViewport(self.project)
            widget.nodeSelected.connect(self._select_from_viewport)
            widget.nodePositionRequested.connect(self._set_node_position)
            widget.resourceDropped.connect(self._resource_dropped)
        elif isinstance(session.document, PatternDocument):
            widget = PatternWorkspace()
            widget.previewRequested.connect(self._launch_active_preview)
            widget.templateRequested.connect(self._apply_pattern_template)
            widget.bulletResourceRequested.connect(
                lambda value: self._apply_pattern_properties(
                    {"bullet.resource": value},
                    "Assign bullet resource",
                )
            )
            widget.originPositionRequested.connect(self._pattern_origin_requested)
            widget.playerPositionRequested.connect(self._pattern_player_requested)
        else:
            raise DocumentManagerError(
                f"No editor workspace for {session.document.type!r}"
            )
        widget.setProperty("managedDocumentId", session.document.id)
        self._document_widgets[session.document.id] = widget
        index = self.central_tabs.addTab(widget, session.display_name)
        self.central_tabs.setCurrentIndex(index)
        return widget

    def _managed_for_widget(self, widget: QWidget | None) -> ManagedDocument | None:
        if widget is None:
            return None
        document_id = str(widget.property("managedDocumentId") or "")
        return next(
            (
                session
                for session in self.document_manager
                if session.document.id == document_id
            ),
            None,
        )

    def _central_tab_changed(self, index: int) -> None:
        session = self._managed_for_widget(self.central_tabs.widget(index))
        if session is None:
            return
        self.document_manager.activate(session)
        if isinstance(session.document, SceneDocument):
            self.viewport = self.central_tabs.widget(index)
            if session.document.tracks:
                self.preview_panel.set_resource(
                    session.resource_uri or f"unsaved://{session.document.id}"
                )
                self.preview_panel.set_mode("stage")
        else:
            self._active_pattern_session = session
            self._active_pattern_document = session.document
            self._active_pattern_resource = session.resource_uri or ""
            self.preview_panel.set_resource(
                self._active_pattern_resource or f"unsaved://{session.document.id}"
            )
            self.preview_panel.set_mode("pattern")
            if hasattr(self, "bottom_dock"):
                target_height = 210 if self.height() <= 700 else 250
                self.resizeDocks([self.bottom_dock], [target_height], Qt.Vertical)
        if not hasattr(self, "tree"):
            return
        self._refresh()

    def open_plugin(self, plugin_id: str) -> None:
        plugin = self.plugin_registry.get(plugin_id)
        if plugin.mode == "bottom":
            widget = self._plugin_widgets.get(plugin.id)
            if widget is not None:
                self.bottom_tabs.setCurrentWidget(widget)
            return
        if plugin.mode == "central":
            existing = self._plugin_widgets.get(plugin.id)
            if existing is not None:
                self.central_tabs.setCurrentWidget(existing)
                return
            widget = plugin.factory()
            widget.setProperty("editorPluginId", plugin.id)
            self._plugin_widgets[plugin.id] = widget
            index = self.central_tabs.addTab(widget, plugin.title)
            self.central_tabs.setCurrentIndex(index)
            self._log(f"[tool] opened {plugin.title}")
            return
        self._start_external_plugin(plugin)

    def _start_external_plugin(self, plugin: EditorPlugin) -> None:
        running = self._tool_processes.get(plugin.id)
        if running is not None and running.state() != QProcess.NotRunning:
            self.statusBar().showMessage(f"{plugin.title} is already running", 3000)
            return
        if plugin.script is None or not plugin.script.is_file():
            self._show_error(
                "Tool unavailable",
                ValueError(f"Tool script does not exist: {plugin.script}"),
            )
            return
        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments([str(plugin.script)])
        process.setWorkingDirectory(str(self.project.root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda plugin_id=plugin.id: self._read_tool_output(plugin_id)
        )
        process.finished.connect(
            lambda exit_code, exit_status, plugin_id=plugin.id: (
                self._tool_finished(plugin_id, exit_code, exit_status)
            )
        )
        process.errorOccurred.connect(
            lambda error, title=plugin.title: self._log(
                f"[tool:error] {title}: process error {int(error)}"
            )
        )
        self._tool_processes[plugin.id] = process
        process.start()
        if not process.waitForStarted(3000):
            self._tool_processes.pop(plugin.id, None)
            self._show_error("Tool failed", ValueError(process.errorString()))
            return
        self._log(f"[tool] started {plugin.title} (PID {process.processId()})")

    def _read_tool_output(self, plugin_id: str) -> None:
        process = self._tool_processes.get(plugin_id)
        if process is None:
            return
        data = bytes(process.readAllStandardOutput())
        output = data.decode("utf-8", errors="replace").rstrip()
        if output:
            self._log(output)

    def _tool_finished(self, plugin_id: str, exit_code: int, exit_status) -> None:
        del exit_status
        self._read_tool_output(plugin_id)
        plugin = self.plugin_registry.get(plugin_id)
        self._log(f"[tool] {plugin.title} exited with code {exit_code}")
        self._tool_processes.pop(plugin_id, None)

    def _close_central_tab(self, index: int) -> None:
        widget = self.central_tabs.widget(index)
        session = self._managed_for_widget(widget)
        if session is not None:
            if not self._confirm_discard(session):
                return
            self.document_manager.close(session, discard=True)
            if self._active_pattern_session is session:
                self._active_pattern_session = None
                self._active_pattern_document = None
                self._active_pattern_resource = ""
            self._document_widgets.pop(session.document.id, None)
            self.central_tabs.removeTab(index)
            widget.deleteLater()
            if self.document_manager.active is None and self.central_tabs.count() == 0:
                self.new_scene()
            elif self.document_manager.active is not None:
                active_widget = self._document_widgets.get(
                    self.document_manager.active.document.id
                )
                if active_widget is not None:
                    self.central_tabs.setCurrentWidget(active_widget)
            self._refresh()
            return
        if widget is None or not widget.close():
            return
        plugin_id = str(widget.property("editorPluginId") or "")
        self.central_tabs.removeTab(index)
        if plugin_id:
            self._plugin_widgets.pop(plugin_id, None)
        widget.deleteLater()

    def _resource_selected(self, record: AssetRecord) -> None:
        if self.document_manager.active is not None:
            self.session.selected_resource = record.resource_value
        self.statusBar().showMessage(record.resource_value, 3000)

    def _resource_activated(self, record: AssetRecord) -> None:
        selected = self.session.node(self._selected_id)
        if record.kind == "pattern":
            self._open_pattern_preview(record.resource_value)
            return
        if record.kind == "scene":
            self._open_document(record.resource_value)
            return
        if record.kind in {"image", "sprite"}:
            if not isinstance(self.session.document, SceneDocument):
                self.statusBar().showMessage(
                    "Open a Scene document before adding image resources", 3000
                )
                return
            if selected is not None and selected.type == "Sprite":
                self.set_node_property(
                    selected.id,
                    "texture",
                    record.resource_value,
                )
            else:
                self._add_sprite_resource(
                    record.resource_value,
                    record.name,
                )
            return
        if record.kind == "script":
            if selected is not None and selected.type == "SpellCard":
                self.set_node_property(
                    selected.id,
                    "script",
                    record.resource_value,
                )
            else:
                self._log(
                    "[assets] Select a SpellCard before assigning a script."
                )
            return
        if record.kind == "json":
            if record.path.name == "bullet_aliases.json":
                self.open_plugin("bullet_aliases")
            elif record.project_path.startswith("assets/images/"):
                self.open_plugin("texture_editor")

    def _resource_dropped(self, payload: dict, x: float, y: float) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        kind = str(payload.get("kind", ""))
        value = str(payload.get("resource_value", "")).strip()
        name = str(payload.get("name", "Sprite")).strip() or "Sprite"
        if not value:
            return
        if kind in {"image", "sprite"}:
            self._add_sprite_resource(value, name, x=x, y=y)
            return
        if kind == "script":
            selected = self.session.node(self._selected_id)
            if selected is not None and selected.type == "SpellCard":
                self.set_node_property(selected.id, "script", value)
            else:
                self._log(
                    "[assets] Drop scripts while a SpellCard is selected."
                )
            return
        if kind == "pattern":
            selected = self.session.node(self._selected_id)
            if selected is not None and selected.type == "PatternInstance":
                self._apply_command(
                    AssignResourceCommand(
                        self.session.document.root,
                        selected.id,
                        "pattern",
                        value,
                        label="Assign Pattern resource",
                    ),
                    select_id=selected.id,
                )
            self._open_pattern_preview(value)
            return

    def _add_sprite_resource(
        self,
        resource_value: str,
        name: str,
        *,
        x: float | None = None,
        y: float | None = None,
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        parent = self.session.node(self._selected_id) or self.session.document.root
        node = make_node("Sprite", name=Path(name).stem or "Sprite")
        node.properties["texture"] = resource_value
        if x is not None:
            node.properties["x"] = float(x)
        if y is not None:
            node.properties["y"] = float(y)
        self._apply_command(
            AddNodeCommand(
                self.session.document.root,
                parent.id,
                node,
                label=f"Add {node.name}",
            ),
            select_id=node.id,
        )

    def _apply_theme(self) -> None:
        QApplication.instance().setStyle("Fusion")
        self.setStyleSheet(
            """
            QMainWindow, QMenuBar, QMenu, QDockWidget, QWidget {
                background: #20232d;
                color: #d9deea;
            }
            QToolBar, QStatusBar {
                background: #191c24;
                color: #aeb7c8;
                border: 0;
            }
            QDockWidget::title {
                background: #191c24;
                padding: 7px;
                font-weight: 600;
            }
            QTreeWidget, QListView, QTextEdit, QTableWidget, QLineEdit,
            QComboBox, QSpinBox, QDoubleSpinBox, QScrollArea {
                background: #171a22;
                color: #dce2ee;
                border: 1px solid #353b49;
                selection-background-color: #315a82;
            }
            QPushButton, QToolButton {
                background: #303644;
                border: 1px solid #454d5e;
                border-radius: 3px;
                padding: 5px 9px;
            }
            QPushButton:hover, QToolButton:hover { background: #3a4252; }
            QHeaderView::section {
                background: #252a35;
                color: #bec7d8;
                border: 0;
                border-right: 1px solid #353b49;
                padding: 5px;
            }
            QTabBar::tab {
                background: #252a35;
                padding: 6px 14px;
            }
            QTabBar::tab:selected { background: #315a82; }
            """
        )

    def _populate_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        if not isinstance(self.session.document, SceneDocument):
            self.tree.blockSignals(False)
            return

        def add_item(node: EditorNode, parent: QTreeWidgetItem | None = None):
            item = QTreeWidgetItem([node.name, node.type])
            item.setData(0, Qt.UserRole, node.id)
            item.setToolTip(0, node.id)
            flags = item.flags() | Qt.ItemIsDropEnabled | Qt.ItemIsSelectable
            if parent is not None:
                flags |= Qt.ItemIsDragEnabled | Qt.ItemIsEditable
            else:
                flags &= ~Qt.ItemIsDragEnabled
            item.setFlags(flags)
            spec = NODE_TYPES.get(node.type)
            if spec:
                item.setForeground(1, QColor(spec.color))
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in node.children:
                add_item(child, item)
            return item

        add_item(self.session.document.root)
        self.tree.expandAll()
        selected = self.tree._find_item(self._selected_id)
        if selected is not None:
            self.tree.setCurrentItem(selected)
        self.tree.blockSignals(False)

    def _refresh(self) -> None:
        if self.document_manager.active is None:
            return
        document = self.session.document
        widget = self._document_widgets.get(document.id)
        if isinstance(document, SceneDocument):
            if self.session.node(self._selected_id) is None:
                self._selected_id = document.root.id
            self._populate_tree()
            self.tree.setEnabled(True)
            if isinstance(widget, SceneViewport):
                self.viewport = widget
                widget.rebuild(document)
                widget.select_node(self._selected_id)
            selected_clip_id = self.session.editor_context.get("selected_clip_id")
            clip_result = (
                find_clip(document, str(selected_clip_id))
                if selected_clip_id
                else None
            )
            if clip_result is not None:
                self.inspector.set_timeline_clip(
                    clip_result[0],
                    clip_result[1],
                    list(document.root.walk()),
                )
            else:
                self.session.editor_context.pop("selected_clip_id", None)
                self.inspector.set_node(self.session.node(self._selected_id))
            self.timeline.set_document(
                document,
                selected_clip_id=(clip_result[1].id if clip_result is not None else None),
                zoom=float(self.session.editor_context.get("timeline_zoom", 0.25)),
            )
            self.timeline.selected_track_id = self.session.editor_context.get(
                "selected_track_id"
            ) or self.timeline.selected_track_id
            self.timeline.set_playhead(
                int(self.session.editor_context.get("timeline_playhead", 0)),
                emit=False,
            )
        else:
            self.tree.blockSignals(True)
            self.tree.clear()
            self.tree.blockSignals(False)
            self.tree.setEnabled(False)
            self.inspector.set_pattern(document)
            self.timeline.clear_document()
            if isinstance(widget, PatternWorkspace):
                player = tuple(
                    self.session.editor_context.get("player_position", (0.0, -0.8))
                )
                widget.set_document(document, player_position=player)
                if hasattr(self, "resource_browser"):
                    widget.set_available_bullets(self.resource_browser.index.records)
        self._update_actions()
        self._update_title()

    def _update_actions(self) -> None:
        self.action_undo.setEnabled(self.session.commands.can_undo)
        self.action_redo.setEnabled(self.session.commands.can_redo)
        self.action_undo.setText(
            f"Undo {self.session.commands.undo_label}"
            if self.session.commands.undo_label
            else "Undo"
        )
        self.action_redo.setText(
            f"Redo {self.session.commands.redo_label}"
            if self.session.commands.redo_label
            else "Redo"
        )
        is_scene = isinstance(self.session.document, SceneDocument)
        is_root = is_scene and self._selected_id == self.session.document.root.id
        self.action_delete.setEnabled(is_scene and not is_root)
        self.action_rename.setEnabled(is_scene and not is_root)
        self.action_move_up.setEnabled(is_scene and not is_root)
        self.action_move_down.setEnabled(is_scene and not is_root)
        self.action_outdent.setEnabled(is_scene and not is_root)
        self.action_indent.setEnabled(is_scene and not is_root)
        self.action_revert.setEnabled(self.session.is_dirty or self.session.path is not None)

    def _update_title(self) -> None:
        name = self.session.display_name
        self.setWindowModified(self.session.is_dirty)
        self.setWindowTitle(f"{name}[*] — {APP_NAME}")
        for session in self.document_manager:
            widget = self._document_widgets.get(session.document.id)
            if widget is None:
                continue
            index = self.central_tabs.indexOf(widget)
            if index >= 0:
                suffix = " *" if session.is_dirty else ""
                self.central_tabs.setTabText(index, session.display_name + suffix)

    def _log(self, message: str) -> None:
        self.output.append(html.escape(str(message)))

    def _apply_command(
        self,
        command,
        *,
        select_id: str | None = None,
        coalesce: bool = False,
    ) -> bool:
        try:
            self.session.apply(command, coalesce=coalesce)
        except (DocumentError, ResourceDocumentError, SceneMutationError, ValueError) as exc:
            self._show_error("Edit failed", exc)
            self._refresh()
            return False
        if select_id is not None:
            self._selected_id = select_id
        self._log(command.label)
        self._refresh()
        return True

    def _select_from_tree(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        if (
            self._syncing_selection
            or current is None
            or not isinstance(self.session.document, SceneDocument)
        ):
            return
        self.session.editor_context.pop("selected_clip_id", None)
        self._selected_id = str(current.data(0, Qt.UserRole))
        self._syncing_selection = True
        self.viewport.select_node(self._selected_id)
        self.inspector.set_node(self.session.node(self._selected_id))
        self._syncing_selection = False
        self._update_actions()

    def _select_from_viewport(self, node_id: str) -> None:
        if self._syncing_selection or not isinstance(self.session.document, SceneDocument):
            return
        self.session.editor_context.pop("selected_clip_id", None)
        item = self.tree._find_item(node_id)
        if item is None:
            return
        self._selected_id = node_id
        self._syncing_selection = True
        self.tree.setCurrentItem(item)
        self.inspector.set_node(self.session.node(node_id))
        self._syncing_selection = False
        self._update_actions()

    def _tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0 or not isinstance(self.session.document, SceneDocument):
            return
        node_id = str(item.data(0, Qt.UserRole))
        self.rename_node(node_id, item.text(0))

    def _move_from_tree(self, node_id: str, parent_id: str, index: int) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        node = self.session.node(node_id)
        location = find_parent(self.session.document.root, node_id)
        if node is None or location is None:
            self._refresh()
            return
        if location[0].id == parent_id and location[1] == index:
            self._refresh()
            return
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node_id,
                parent_id,
                index,
                label=f"Move {node.name}",
            ),
            select_id=node_id,
        )

    def _set_node_position(self, node_id: str, x: float, y: float) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        node = self.session.node(node_id)
        if node is None:
            return
        if (
            float(node.properties.get("x", 0.0)) == float(x)
            and float(node.properties.get("y", 0.0)) == float(y)
        ):
            return
        self._apply_command(
            SetNodePropertiesCommand(
                self.session.document.root,
                node_id,
                {"x": float(x), "y": float(y)},
                label=f"Move {node.name}",
            ),
            select_id=node_id,
        )

    def add_node(self, node_type: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        parent = self.session.node(self._selected_id) or self.session.document.root
        node = make_node(node_type)
        from .node_types import NODE_TYPE_REGISTRY

        if not NODE_TYPE_REGISTRY.can_parent(parent.type, node.type):
            self._show_error(
                "Add node failed",
                ValueError(f"{node.type} cannot be added under {parent.type}"),
            )
            return
        self._apply_command(
            AddNodeCommand(
                self.session.document.root,
                parent.id,
                node,
                label=f"Add {node.name}",
            ),
            select_id=node.id,
        )

    def create_simple_spell_flow(self) -> None:
        """Create the M3 Stage→Boss→Spell→Emitter→Pattern chain."""

        if not isinstance(self.session.document, SceneDocument):
            self._show_error(
                "Create Spell failed",
                ValueError("Open a Scene document first"),
            )
            return
        root = self.session.document.root
        stage = next((node for node in root.children if node.type == "Stage"), None)
        created_stage = stage is None
        stage = stage or make_node("Stage", name="Stage")
        boss = make_node("Boss", name="Boss")
        spell = make_node("Spell", name="Spell")
        emitter = make_node("Emitter", name="Emitter")
        instance = make_node("PatternInstance", name="Pattern")
        selected_resource = str(self.session.selected_resource or "")
        record = (
            self.resource_browser.index.find(selected_resource)
            if selected_resource and hasattr(self, "resource_browser")
            else None
        )
        if record is None or record.kind != "pattern":
            selected_resource = ""

        self.session.commands.begin_transaction("Create simple Spell")
        try:
            if created_stage:
                self.session.apply(AddNodeCommand(root, root.id, stage))
            self.session.apply(AddNodeCommand(root, stage.id, boss))
            self.session.apply(AddNodeCommand(root, boss.id, spell))
            self.session.apply(AddNodeCommand(root, spell.id, emitter))
            self.session.apply(AddNodeCommand(root, emitter.id, instance))
            if selected_resource:
                self.session.apply(
                    AssignResourceCommand(
                        root,
                        instance.id,
                        "pattern",
                        selected_resource,
                        label="Assign Pattern resource",
                    )
                )
        except Exception as exc:
            self.session.commands.cancel_transaction()
            self._show_error("Create Spell failed", exc)
            self._refresh()
            return
        self.session.commands.end_transaction()
        self._selected_id = instance.id
        self._log("Created Stage/Boss/Spell/Emitter/PatternInstance flow")
        self._refresh()

    def delete_selected(self) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        if self._selected_id == self.session.document.root.id:
            return
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent_id = location[0].id
        self._apply_command(
            RemoveNodeCommand(
                self.session.document.root,
                node.id,
                label=f"Delete {node.name}",
            ),
            select_id=parent_id,
        )

    def rename_selected(self) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        item = self.tree.currentItem()
        if item is not None:
            self.tree.editItem(item, 0)

    def rename_node(self, node_id: str, name: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        node = self.session.node(node_id)
        if node is None or node.name == name:
            return
        self._apply_command(
            RenameNodeCommand(
                self.session.document.root,
                node_id,
                name,
                label=f"Rename {node.name}",
            ),
            select_id=node_id,
        )

    def set_node_property(self, node_id: str, key: str, value) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        node = self.session.node(node_id)
        if node is None or node.properties.get(key) == value:
            return
        spec = next(
            (item for item in property_specs(node.type) if item.key == key),
            None,
        )
        command_type = (
            AssignResourceCommand
            if spec is not None and spec.resource_types
            else SetNodePropertyCommand
        )
        label = f"Assign {key}" if command_type is AssignResourceCommand else f"Set {key}"
        self._apply_command(
            command_type(
                self.session.document.root,
                node_id,
                key,
                value,
                label=label,
            ),
            select_id=node_id,
        )

    def _timeline_default_target(self, kind: str) -> EditorNode | None:
        if not isinstance(self.session.document, SceneDocument):
            return None
        selected = self.session.node(self._selected_id)
        if kind == "Pattern":
            if selected is not None and selected.type == "PatternInstance":
                return selected
            return next(
                (
                    node
                    for node in self.session.document.root.walk()
                    if node.type == "PatternInstance"
                ),
                None,
            )
        if kind in {"Movement", "Property"}:
            return selected or self.session.document.root
        return None

    def _timeline_add_track(self, kind: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        target = self._timeline_default_target(kind)
        if kind == "Pattern" and target is None:
            self._show_error(
                "Add timeline track failed",
                ValueError("Create or select a PatternInstance before adding a Pattern track"),
            )
            return
        channels = {
            "Pattern": "danmaku",
            "Movement": "position",
            "Audio": "bgm",
            "Event": "event",
            "Property": "enabled",
            "ScriptEvent": "script",
        }
        track = TimelineTrack(
            name=f"{kind} Track",
            kind=kind,
            channel=channels[kind],
            target_id=target.id if target is not None else None,
            order=len(self.session.document.tracks),
        )
        try:
            self.session.apply(
                AddTrackCommand(
                    self.session.document,
                    track,
                    label=f"Add {kind} track",
                )
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Add timeline track failed", exc)
            return
        self.timeline.selected_track_id = track.id
        self.session.editor_context["selected_track_id"] = track.id
        self._log(f"Added {kind} timeline track")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_add_clip(self, track_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            track = require_track(self.session.document, track_id)
        except ValueError as exc:
            self._show_error("Add timeline clip failed", exc)
            return
        start = self.timeline.playhead_frame
        target_id = track.target_id
        duration = 1
        payload: dict[str, object] = {}
        keyframes: list[TimelineKeyframe] = []
        if track.kind == "Pattern":
            duration = self.session.document.timebase.tick_rate * 10
            if target_id is None:
                self._show_error(
                    "Add timeline clip failed",
                    ValueError("Pattern track needs a PatternInstance target"),
                )
                return
        elif track.kind == "Movement":
            duration = self.session.document.timebase.tick_rate * 2
            node = self.session.node(target_id)
            if node is None:
                self._show_error(
                    "Add timeline clip failed",
                    ValueError("Movement track needs a Scene node target"),
                )
                return
            x = float(node.properties.get("x", 192.0))
            y = float(node.properties.get("y", 224.0))
            keyframes = [
                TimelineKeyframe(0, {"x": x, "y": y}),
                TimelineKeyframe(
                    duration,
                    {"x": min(384.0, x + 64.0), "y": y},
                    interpolation="ease_in_out",
                ),
            ]
        elif track.kind == "Audio":
            duration = max(
                self.session.document.timebase.tick_rate * 30,
                self.session.document.duration_frames,
            )
            payload = {"action": "play", "name": "bgm", "loops": -1}
        elif track.kind == "Event":
            payload = {"event_type": "timeline_event", "data": {}}
        elif track.kind == "Property":
            node = self.session.node(target_id)
            if node is None:
                self._show_error(
                    "Add timeline clip failed",
                    ValueError("Property track needs a Scene node target"),
                )
                return
            payload = {
                "property": track.channel,
                "value": node.properties.get(track.channel, True),
            }
        elif track.kind == "ScriptEvent":
            payload = {"hook": "on_timeline_event", "data": {}}
        clip = TimelineClip(
            name=f"{track.kind} Clip",
            kind=track.kind,
            start_frame=start,
            duration_frames=duration,
            target_id=target_id,
            channel=track.channel,
            order=len(track.clips),
            payload=payload,
            keyframes=keyframes,
        )
        try:
            self.session.apply(
                AddClipCommand(
                    self.session.document,
                    track.id,
                    clip,
                    label=f"Add {track.kind} clip",
                )
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Add timeline clip failed", exc)
            return
        self.session.editor_context["selected_clip_id"] = clip.id
        self.timeline.selected_clip_id = clip.id
        self._log(f"Added {track.kind} clip at frame {start}")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_clip_geometry(
        self,
        clip_id: str,
        start_frame: int,
        duration_frames: int,
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                MoveResizeClipCommand(
                    self.session.document,
                    clip_id,
                    start_frame,
                    duration_frames,
                ),
                coalesce=True,
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Move timeline clip failed", exc)
            self._refresh()
            return
        self.session.editor_context["selected_clip_id"] = clip_id
        self._log(f"Moved timeline clip to frame {start_frame}")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_duplicate_clip(self, clip_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        result = find_clip(self.session.document, clip_id)
        if result is None:
            return
        track, clip, index = result
        duplicate = clone_clip_with_new_ids(clip)
        duplicate.start_frame = clip.end_frame
        try:
            self.session.apply(
                AddClipCommand(
                    self.session.document,
                    track.id,
                    duplicate,
                    index=index + 1,
                    label=f"Duplicate {clip.name}",
                )
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Duplicate timeline clip failed", exc)
            return
        self.session.editor_context["selected_clip_id"] = duplicate.id
        self._log(f"Duplicated {clip.name}")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_delete_clip(self, clip_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                RemoveClipCommand(
                    self.session.document,
                    clip_id,
                    label="Delete timeline clip",
                )
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Delete timeline clip failed", exc)
            return
        self.session.editor_context.pop("selected_clip_id", None)
        self.timeline.selected_clip_id = None
        self._log("Deleted timeline clip")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_clip_selected(self, track_id: str, clip_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        result = find_clip(self.session.document, clip_id)
        if result is None:
            return
        self.session.editor_context["selected_track_id"] = track_id
        self.session.editor_context["selected_clip_id"] = clip_id
        self.inspector.set_timeline_clip(
            result[0],
            result[1],
            list(self.session.document.root.walk()),
        )

    def _timeline_clip_properties_requested(
        self,
        clip_id: str,
        values: dict[str, object],
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                SetClipPropertiesCommand(
                    self.session.document,
                    clip_id,
                    values,
                    label="Edit timeline clip",
                ),
                coalesce=True,
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Edit timeline clip failed", exc)
            self._refresh()
            return
        self.session.editor_context["selected_clip_id"] = clip_id
        self._log("Edited timeline clip")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_playhead_changed(self, frame: int) -> None:
        if self.document_manager.active is None:
            return
        self.session.editor_context["timeline_playhead"] = int(frame)
        if self._pattern_preview_client.is_running:
            self._pattern_preview_client.send_command("seek", {"frame": int(frame)})

    def _timeline_zoom_changed(self, value: float) -> None:
        if self.document_manager.active is not None:
            self.session.editor_context["timeline_zoom"] = float(value)

    def move_selected(self, delta: int) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent, index = location
        target = index + delta
        if target < 0 or target >= len(parent.children):
            return
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node.id,
                parent.id,
                target,
                label=f"Reorder {node.name}",
            ),
            select_id=node.id,
        )

    def indent_selected(self) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent, index = location
        if index <= 0:
            return
        new_parent = parent.children[index - 1]
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node.id,
                new_parent.id,
                len(new_parent.children),
                label=f"Indent {node.name}",
            ),
            select_id=node.id,
        )

    def outdent_selected(self) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent, _ = location
        if parent.id == self.session.document.root.id:
            return
        parent_location = find_parent(self.session.document.root, parent.id)
        if parent_location is None:
            return
        grandparent, parent_index = parent_location
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node.id,
                grandparent.id,
                parent_index + 1,
                label=f"Outdent {node.name}",
            ),
            select_id=node.id,
        )

    def undo(self) -> None:
        if self.session.undo():
            self._log("Undo")
            self._refresh()
            self._sync_active_pattern_preview()
            self._sync_active_stage_preview()

    def redo(self) -> None:
        if self.session.redo():
            self._log("Redo")
            self._refresh()
            self._sync_active_pattern_preview()
            self._sync_active_stage_preview()

    def new_scene(self) -> None:
        session = self.document_manager.new_scene()
        self._add_document_tab(session)
        self._log("New scene")
        self._refresh()

    def new_pattern(self) -> None:
        session = self.document_manager.new_pattern()
        self._add_document_tab(session)
        self._active_pattern_session = session
        self._active_pattern_document = session.document
        self._active_pattern_resource = ""
        self._log("New Pattern")
        self._refresh()

    def open_resource(self) -> None:
        start = self.project.game_content / "scenes"
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PySTG Resource",
            str(start),
            RESOURCE_FILTER,
        )
        if not path:
            return
        self._open_document(path)

    def open_scene(self) -> None:
        """Compatibility alias retained for existing integrations."""

        self.open_resource()

    def _open_document(self, resource_value: str) -> ManagedDocument | None:
        try:
            if str(resource_value).startswith("res://"):
                reference = ResourceReference.parse(resource_value)
                if reference.subresource is not None:
                    raise ResourceDocumentError(
                        "Authoring documents cannot be opened from a fragment"
                    )
                path = reference.resolve(self.project, must_exist=True)
            else:
                path = self.project.resolve(resource_value)
            session = self.document_manager.open(path)
        except (
            OSError,
            DocumentError,
            DocumentManagerError,
            ResourceDocumentError,
            ValueError,
        ) as exc:
            self._show_error("Open failed", exc)
            return None
        self._add_document_tab(session)
        self._log(f"Opened {self.project.relative(path)}")
        self._refresh()
        return session

    def save_scene(self) -> bool:
        return self._save_document(self.session)

    def save_scene_as(self) -> bool:
        return self._save_document(self.session, save_as=True)

    def _save_document(
        self,
        session: ManagedDocument,
        *,
        save_as: bool = False,
    ) -> bool:
        if session.path is not None and not save_as:
            try:
                saved = self.document_manager.save(session)
            except (OSError, DocumentError, ResourceDocumentError, ValueError) as exc:
                self._show_error("Save failed", exc)
                return False
            self._log(f"Saved {self.project.relative(saved)}")
            if session is self._active_pattern_session:
                self._active_pattern_resource = session.resource_uri or ""
                self.preview_panel.set_resource(self._active_pattern_resource)
            if hasattr(self, "resource_browser"):
                self.resource_browser.refresh()
            self._refresh()
            return True
        folder = "patterns" if isinstance(session.document, PatternDocument) else "scenes"
        start = self.project.game_content / folder
        start.mkdir(parents=True, exist_ok=True)
        suggested = start / (
            session.path.name
            if session.path
            else ("new_pattern.pystg.json" if folder == "patterns" else "untitled.pystg.json")
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PySTG Resource",
            str(suggested),
            RESOURCE_FILTER,
        )
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".pystg.json"
        try:
            saved = self.document_manager.save(session, path)
        except (OSError, DocumentError, ResourceDocumentError, ValueError) as exc:
            self._show_error("Save failed", exc)
            return False
        self._log(f"Saved {self.project.relative(saved)}")
        if session is self._active_pattern_session:
            self._active_pattern_resource = session.resource_uri or ""
            self.preview_panel.set_resource(self._active_pattern_resource)
        if hasattr(self, "resource_browser"):
            self.resource_browser.refresh()
        self._refresh()
        return True

    def revert_document(self) -> None:
        session = self.session
        if session.is_dirty:
            result = QMessageBox.warning(
                self,
                "Revert document",
                f"Discard all changes to {session.display_name}?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if result != QMessageBox.Yes:
                return
        try:
            self.document_manager.revert(session)
        except (OSError, ValueError, ResourceDocumentError) as exc:
            self._show_error("Revert failed", exc)
            return
        self._selected_id = session.default_selection
        self._log(f"Reverted {session.display_name}")
        self._refresh()
        self._sync_active_pattern_preview()

    def close_active_document(self) -> None:
        widget = self._document_widgets.get(self.session.document.id)
        if widget is not None:
            self._close_central_tab(self.central_tabs.indexOf(widget))

    def _confirm_discard(self, session: ManagedDocument | None = None) -> bool:
        session = session or self.session
        if not session.is_dirty:
            return True
        # Programmatic/offscreen smoke windows are never user-owned interactive
        # surfaces, so closing them must not open a modal dialog during teardown.
        if not self.isVisible():
            return True
        result = QMessageBox.warning(
            self,
            "Unsaved changes",
            f"Save changes to {session.display_name}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if result == QMessageBox.Cancel:
            return False
        if result == QMessageBox.Save:
            return self._save_document(session)
        return True

    def _fit_viewport(self) -> None:
        self.viewport.fit_canvas()

    def _connect_pattern_preview(self) -> None:
        client = self._pattern_preview_client
        client.eventReceived.connect(self._handle_pattern_preview_event)
        client.protocolError.connect(self._handle_pattern_preview_issue)
        client.processLog.connect(
            lambda text: self._log(f"[pattern-preview:stderr] {text}")
        )
        client.runningChanged.connect(self.preview_panel.set_running)

    def _open_pattern_preview(self, resource_value: str) -> None:
        session = self._open_document(resource_value)
        if session is None:
            return
        if not isinstance(session.document, PatternDocument):
            self._show_error(
                "Pattern preview unavailable",
                ValueError("Selected resource is not a PatternDocument"),
            )
            return
        self._active_pattern_session = session
        self._active_pattern_document = session.document
        self._active_pattern_resource = session.resource_uri or ""
        self.preview_panel.set_resource(self._active_pattern_resource)
        self.bottom_tabs.setCurrentWidget(self.preview_panel)
        self._launch_active_pattern_preview()

    def _launch_active_preview(self) -> None:
        session = self.document_manager.active
        if (
            session is not None
            and isinstance(session.document, SceneDocument)
            and session.document.tracks
        ):
            self._launch_active_stage_preview(session)
            return
        self._launch_active_pattern_preview()

    def _launch_active_stage_preview(self, session: ManagedDocument) -> None:
        if not isinstance(session.document, SceneDocument) or not session.document.tracks:
            self.preview_panel.handle_issue(
                {
                    "code": "no_stage_timeline",
                    "message": "Add at least one Timeline track before launching Stage preview",
                }
            )
            return
        if not self._pattern_preview_client.start():
            return
        self.preview_panel.set_resource(
            session.resource_uri or f"unsaved://{session.document.id}"
        )
        self.preview_panel.set_mode("stage")
        self.bottom_tabs.setCurrentWidget(self.preview_panel)
        self._pattern_preview_client.send_command(
            "load",
            {"document": session.document.to_dict()},
        )
        self._pattern_preview_client.send_command("play")
        self._log(
            f"[stage-preview] opening {session.resource_uri or session.document.name}"
        )

    def _launch_active_pattern_preview(self) -> None:
        if self._active_pattern_document is None:
            self.preview_panel.handle_issue(
                {"code": "no_pattern", "message": "Select a Pattern resource first"}
            )
            return
        if not self._pattern_preview_client.start():
            return
        self._pattern_preview_client.send_command(
            "load",
            {"document": self._active_pattern_document.to_dict()},
        )
        self._pattern_preview_client.send_command("play")
        self.preview_panel.set_mode("pattern")
        label = self._active_pattern_resource or self._active_pattern_document.name
        self._log(f"[pattern-preview] opening {label}")

    def _send_pattern_preview_command(self, command: str, payload: dict) -> None:
        active_document = (
            self.document_manager.active.document
            if self.document_manager.active is not None
            else None
        )
        if command == "set-seed" and isinstance(active_document, PatternDocument):
            self._pattern_property_requested("seed", payload.get("seed"))
            return
        if command == "set-property" and isinstance(active_document, PatternDocument):
            self._pattern_property_requested(payload.get("path"), payload.get("value"))
            return
        if not self._pattern_preview_client.is_running:
            self._launch_active_preview()
        if not self._pattern_preview_client.is_running:
            return
        try:
            self._pattern_preview_client.send_command(command, payload)
        except RuntimeError as exc:
            self._handle_pattern_preview_issue(
                {"code": "command_failed", "message": str(exc)}
            )

    def _pattern_property_requested(self, path: str, value) -> None:
        session = self._active_pattern_session
        if session is None or not isinstance(session.document, PatternDocument):
            self.preview_panel.handle_issue(
                {"code": "no_pattern", "message": "Select a Pattern resource first"}
            )
            return
        if not path:
            return
        if not self._apply_pattern_properties({str(path): value}, f"Set {path}"):
            if self._pattern_preview_client.is_running:
                request_id = self._pattern_preview_client.send_command(
                    "set-property",
                    {"path": path, "value": value},
                )
                self._preview_pending_properties[request_id] = (str(path), value)
            return
        if not self._pattern_preview_client.is_running:
            self._launch_active_pattern_preview()
        elif self._pattern_preview_client.is_running:
            request_id = self._pattern_preview_client.send_command(
                "set-property",
                {"path": path, "value": value},
            )
            self._preview_pending_properties[request_id] = (str(path), value)

    @staticmethod
    def _pattern_with_property(
        document: PatternDocument,
        path: str,
        value,
    ) -> PatternDocument:
        from .pattern_commands import pattern_with_property

        return pattern_with_property(document, path, value)

    def _apply_pattern_properties(
        self,
        values: dict[str, object],
        label: str,
    ) -> bool:
        session = self._active_pattern_session
        if session is None or not isinstance(session.document, PatternDocument):
            return False
        session.commands.begin_transaction(label)
        try:
            for path, value in values.items():
                session.apply(
                    SetPatternPropertyCommand(
                        session.document,
                        path,
                        value,
                        label=f"Set {path}",
                    )
                )
        except Exception as exc:
            session.commands.cancel_transaction()
            self.preview_panel.handle_issue(
                {"code": "invalid_pattern_edit", "message": str(exc)}
            )
            self._log(f"[pattern-edit:error] {exc}")
            self._refresh()
            return False
        session.commands.end_transaction()
        self._active_pattern_document = session.document
        self._log(label)
        self._refresh()
        return True

    def _apply_pattern_template(self, template: str) -> None:
        templates = {
            "starter_ring": {
                "shape.kind": "ring",
                "shape.count": 24,
                "aim.mode": "fixed",
                "aim.angle": 270.0,
                "schedule.interval_frames": 12,
                "schedule.burst_count": 8,
                "schedule.loop_count": None,
                "motion.speed": 2.0,
                "motion.max_lifetime": 5.0,
            },
            "aimed_arc": {
                "shape.kind": "arc",
                "shape.count": 12,
                "shape.angle_span": 60.0,
                "aim.mode": "player",
                "schedule.interval_frames": 24,
                "schedule.burst_count": 4,
                "motion.speed": 2.5,
            },
            "spiral": {
                "shape.kind": "spiral",
                "shape.count": 18,
                "aim.mode": "fixed",
                "schedule.interval_frames": 8,
                "schedule.burst_count": 24,
                "modifiers.angle_offset_per_burst": 11.0,
                "motion.speed": 2.0,
            },
        }
        values = templates.get(template)
        if values is not None and self._apply_pattern_properties(
            values, f"Apply {template.replace('_', ' ')} template"
        ):
            self._sync_active_pattern_preview()

    def _pattern_origin_requested(self, x: float, y: float) -> None:
        if self._apply_pattern_properties(
            {"shape.origin_x": x, "shape.origin_y": y},
            "Move Pattern emitter",
        ):
            self._sync_active_pattern_preview()

    def _pattern_player_requested(self, x: float, y: float) -> None:
        if self._active_pattern_session is not None:
            self._active_pattern_session.editor_context["player_position"] = (x, y)
        self._send_pattern_preview_command(
            "set-player-position", {"x": float(x), "y": float(y)}
        )

    def _sync_active_pattern_preview(self) -> None:
        session = self.document_manager.active
        if (
            session is None
            or not isinstance(session.document, PatternDocument)
            or not self._pattern_preview_client.is_running
        ):
            return
        self._active_pattern_session = session
        self._active_pattern_document = session.document
        self._active_pattern_resource = session.resource_uri or ""
        self._pattern_preview_client.send_command(
            "load", {"document": session.document.to_dict()}
        )

    def _sync_active_stage_preview(self) -> None:
        session = self.document_manager.active
        if (
            session is None
            or not isinstance(session.document, SceneDocument)
            or not session.document.tracks
            or not self._pattern_preview_client.is_running
        ):
            return
        self._pattern_preview_client.send_command(
            "load", {"document": session.document.to_dict()}
        )

    def _handle_pattern_preview_event(self, message: dict) -> None:
        self.preview_panel.handle_event(message)
        request_id = message.get("request_id")
        payload = message.get("payload") or {}
        if message.get("event") == "response" and request_id in self._preview_pending_properties:
            self._preview_pending_properties.pop(request_id)
        event = message.get("event")
        if event == "program_loaded":
            mode = str(payload.get("mode") or "pattern")
            self._log(
                f"[{mode}-preview] loaded {payload.get('name')} "
                f"({str(payload.get('content_hash') or '')[:12]})"
            )
        elif event in {"compile_error", "runtime_error", "protocol_error"}:
            self._log(f"[pattern-preview:{event}] {payload}")

    def _handle_pattern_preview_issue(self, issue: dict) -> None:
        self.preview_panel.handle_issue(issue)
        self._log(
            f"[pattern-preview:error] {issue.get('code')}: {issue.get('message')}"
        )

    def _log_scene_diagnostics(self, error: SceneSpellCompileError) -> None:
        for diagnostic in error.diagnostics:
            href = (
                f"pystg-node:{diagnostic.resource_id}:{diagnostic.node_id}"
            )
            path = diagnostic.path
            if diagnostic.referenced_path:
                path += f" → {diagnostic.referenced_path}"
            self.output.append(
                f'<a href="{html.escape(href)}">'
                f'{html.escape(diagnostic.code)}: {html.escape(path)}</a> '
                f'{html.escape(diagnostic.message)}'
            )

    def _diagnostic_link_clicked(self, url: QUrl) -> None:
        value = url.toString()
        if not value.startswith("pystg-node:"):
            return
        parts = value.split(":", 2)
        if len(parts) != 3:
            return
        document_id, node_id = parts[1], parts[2]
        session = next(
            (
                item
                for item in self.document_manager
                if item.document.id == document_id
            ),
            None,
        )
        if session is None or not isinstance(session.document, SceneDocument):
            return
        self.document_manager.activate(session)
        widget = self._document_widgets.get(document_id)
        if widget is not None:
            self.central_tabs.setCurrentWidget(widget)
        session.selected_id = node_id
        self._refresh()

    def run_preview(self) -> None:
        if isinstance(self.session.document, PatternDocument):
            self._active_pattern_session = self.session
            self._active_pattern_document = self.session.document
            self._active_pattern_resource = self.session.resource_uri or ""
            self._launch_active_pattern_preview()
            return
        if isinstance(self.session.document, SceneDocument) and self.session.document.tracks:
            self._launch_active_stage_preview(self.session)
            return
        node = self.session.node(self._selected_id)
        if node is not None and node.type == "PatternInstance":
            resource = str(node.properties.get("pattern") or "").strip()
            if resource:
                self._open_pattern_preview(resource)
                return
        if node is not None and node.type == "Spell":
            try:
                preview = compile_simple_spell(
                    self.project,
                    self.session.document,
                    node.id,
                )
            except SceneSpellCompileError as exc:
                self._log_scene_diagnostics(exc)
                self._show_error("No-code Spell preview unavailable", exc)
                return
            self._active_pattern_session = None
            self._active_pattern_document = preview.document
            self._active_pattern_resource = preview.pattern_resource
            self.preview_panel.set_resource(preview.pattern_resource)
            self.bottom_tabs.setCurrentWidget(self.preview_panel)
            self._launch_active_pattern_preview()
            self._log(
                f"[scene-preview] Spell {node.name} compiled through PatternInstance "
                f"{preview.pattern_instance_id}"
            )
            return
        if self._preview_process is not None and self._preview_process.state() != QProcess.NotRunning:
            self.statusBar().showMessage("Preview is already running", 3000)
            return

        try:
            arguments, label = build_preview_command(
                self.project,
                self.session.document,
                node,
            )
        except (OSError, ValueError) as exc:
            self._show_error("Preview unavailable", exc)
            return

        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments(arguments)
        process.setWorkingDirectory(str(self.project.root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_preview_output)
        process.finished.connect(self._preview_finished)
        process.errorOccurred.connect(
            lambda error: self._log(f"[preview:error] process error {int(error)}")
        )
        self._preview_process = process
        process.start()
        if not process.waitForStarted(3000):
            self._show_error("Preview failed", ValueError(process.errorString()))
            self._preview_process = None
            return
        self._log(f"[preview] started {label} (PID {process.processId()})")
        self.statusBar().showMessage(f"Started {label}", 3000)

    def _read_preview_output(self) -> None:
        if self._preview_process is None:
            return
        data = bytes(self._preview_process.readAllStandardOutput())
        text = data.decode("utf-8", errors="replace").rstrip()
        if text:
            self._log(text)

    def _preview_finished(self, exit_code: int, exit_status) -> None:
        self._read_preview_output()
        self._log(f"[preview] exited with code {exit_code}")
        self.statusBar().showMessage(f"Preview exited ({exit_code})", 3000)

    def _show_error(self, title: str, error: Exception) -> None:
        self._log(f"[error] {title}: {error}")
        QMessageBox.critical(self, title, str(error))

    def closeEvent(self, event) -> None:
        for session in tuple(self.document_manager):
            if not self._confirm_discard(session):
                event.ignore()
                return
        for index in range(self.central_tabs.count() - 1, -1, -1):
            widget = self.central_tabs.widget(index)
            if self._managed_for_widget(widget) is not None:
                continue
            if widget is not None and not widget.close():
                event.ignore()
                return
        if self._preview_process is not None and self._preview_process.state() != QProcess.NotRunning:
            self._preview_process.terminate()
            if not self._preview_process.waitForFinished(1500):
                self._preview_process.kill()
        self._pattern_preview_client.close()
        for process in tuple(self._tool_processes.values()):
            if process.state() == QProcess.NotRunning:
                continue
            process.terminate()
            if not process.waitForFinished(1500):
                process.kill()
        event.accept()


def create_window(project: ProjectContext) -> EditorMainWindow:
    return EditorMainWindow(project)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--project", type=Path, help="PySTG project root")
    args, qt_args = parser.parse_known_args(argv)
    project = ProjectContext.discover(args.project or Path.cwd())
    project.activate()

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("PySTG")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    window = create_window(project)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())

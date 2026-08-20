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
    QLineEdit,
    QListWidget,
    QDoubleSpinBox,
    QSpinBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.authoring.coordinates import CoordinateSpace
from src.pattern import PatternDocument, PresetDescriptor, PresetResolver, VirtualPresetNode

from .i18n import LanguageManager
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


class PresetReactionSlotEditor(QWidget):
    """Structured editor for a preset ``reaction`` slot.

    The runtime accepts exactly one batch reaction -- ``split`` -- with a fixed
    field set, so this exposes those fields instead of a free-form payload the
    engine would reject at spawn time.
    """

    valueChanged = pyqtSignal(object)

    def __init__(self, slot_id: str, value, *, nullable: bool, parent=None):
        super().__init__(parent)
        self._slot_id = str(slot_id)
        self._nullable = bool(nullable)
        self._loading = True
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.enabled = QCheckBox("On")
        self.enabled.setObjectName(f"presetSlotEnabled_{self._slot_id}")
        self.enabled.setEnabled(self._nullable)
        layout.addWidget(self.enabled)
        self.reason = QComboBox()
        self.reason.setObjectName(f"presetSlotReason_{self._slot_id}")
        for label, data in (("Lifetime ended", "expired"), ("Left the field", "out_of_bounds")):
            self.reason.addItem(label, data)
        layout.addWidget(self.reason)
        self.count = QSpinBox()
        self.count.setObjectName(f"presetSlotCount_{self._slot_id}")
        self.count.setRange(1, 256)
        layout.addWidget(self.count)
        self.speed = QDoubleSpinBox()
        self.speed.setObjectName(f"presetSlotSpeed_{self._slot_id}")
        self.speed.setDecimals(3)
        self.speed.setRange(0.0, 100.0)
        layout.addWidget(self.speed)
        self.max_lifetime = QDoubleSpinBox()
        self.max_lifetime.setObjectName(f"presetSlotLifetime_{self._slot_id}")
        self.max_lifetime.setDecimals(3)
        self.max_lifetime.setRange(0.0, 60.0)
        layout.addWidget(self.max_lifetime)

        self.set_value(value)
        self._loading = False
        self.enabled.toggled.connect(self._commit)
        self.reason.currentIndexChanged.connect(self._commit)
        for spin in (self.count, self.speed, self.max_lifetime):
            spin.editingFinished.connect(self._commit)

    def set_value(self, value) -> None:
        """Load a slot value without emitting, so rebuilds do not look like edits."""

        previous = self._loading
        self._loading = True
        payload = dict(value) if isinstance(value, dict) else {}
        self.enabled.setChecked(bool(payload) or not self._nullable)
        index = self.reason.findData(str(payload.get("reason", "expired")))
        self.reason.setCurrentIndex(max(0, index))
        self.count.setValue(int(payload.get("count", 6)))
        self.speed.setValue(float(payload.get("speed", 1.5)))
        self.max_lifetime.setValue(float(payload.get("max_lifetime", 2.0)))
        self._update_enablement()
        self._loading = previous

    def value(self):
        """Return the slot override, or None when the author switched it off."""

        if self._nullable and not self.enabled.isChecked():
            return None
        return {
            "action": "split",
            "reason": str(self.reason.currentData()),
            "count": int(self.count.value()),
            "speed": float(self.speed.value()),
            "max_lifetime": float(self.max_lifetime.value()),
        }

    def _update_enablement(self) -> None:
        active = self.enabled.isChecked()
        for widget in (self.reason, self.count, self.speed, self.max_lifetime):
            widget.setEnabled(active)

    def _commit(self, *_args) -> None:
        self._update_enablement()
        if self._loading:
            return
        self.valueChanged.emit(self.value())


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
    presetParameterRequested = pyqtSignal(str, object)
    presetSlotRequested = pyqtSignal(str, object)
    presetMigrateRequested = pyqtSignal(str)
    presetMaterializeRequested = pyqtSignal()
    actionSearchRequested = pyqtSignal(object)
    authoringLevelRequested = pyqtSignal(str)
    patternBindingRequested = pyqtSignal(str, str, object)
    patternBindingRemoveRequested = pyqtSignal(str)
    sourceNavigateRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("patternWorkspace")
        # The pickers built below consult the language manager and the preset
        # availability flag, so both exist before any builder runs.
        self._language_manager: LanguageManager | None = None
        self._preset_mode_available = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(self._build_primary_toolbar())
        layout.addLayout(self._build_authoring_toolbar())
        layout.addWidget(self._build_graph_toolbar())
        hint = QLabel("Drag E/P gizmos. Drop an Assets sprite to assign.")
        hint.setObjectName("patternWorkspaceHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(self._build_view_stack(), 1)
        self._mode = "recipe"
        self._document: PatternDocument | None = None
        self._preset_descriptor: PresetDescriptor | None = None
        self._preset_nodes: tuple[VirtualPresetNode, ...] = ()
        self._player_position = (0.0, -0.8)
        self._level_switching = False
        self._authoring_level = "l1"
        self._source_resource = ""
        self._reset_binding_pickers()
        self._reset_level_picker(False)

    def _build_primary_toolbar(self) -> QHBoxLayout:
        """Title, authoring-task picker, guides toggle and the preview button."""

        primary_toolbar = QHBoxLayout()
        self.title = QLabel("Pattern")
        self.title.setObjectName("patternWorkspaceTitle")
        self.title.setStyleSheet("font-size:16px; font-weight:600;")
        primary_toolbar.addWidget(self.title)
        primary_toolbar.addStretch()
        self.level_picker = QComboBox()
        self.level_picker.setObjectName("patternAuthoringLevel")
        primary_toolbar.addWidget(self.level_picker)
        self.level_picker.currentIndexChanged.connect(self._level_changed)
        # Task names are the single author-facing progression.  The view mode is
        # internal state derived from the selected task, so it is plain data
        # instead of a hidden combo box carrying its own competing vocabulary.
        self.fold_button = QPushButton("Back to Parameters")
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
        return primary_toolbar

    def _build_authoring_toolbar(self) -> QGridLayout:
        """Bullet assignment and template application, one operation per row.

        The central canvas is intentionally narrow when both the Scene and
        Inspector docks are visible at the supported 960 px window width, so a
        single horizontal strip would overlap its controls.
        """

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
        return authoring_toolbar

    def _build_graph_toolbar(self) -> QWidget:
        """Node-creation strip, hidden until a graph view is on screen."""

        from .graph_workspace import CREATABLE_NODE_CATEGORIES

        self.graph_toolbar_widget = QWidget()
        self.graph_toolbar_widget.setObjectName("graphToolbar")
        self.graph_toolbar = QGridLayout(self.graph_toolbar_widget)
        self.graph_toolbar.setContentsMargins(0, 0, 0, 0)
        self.graph_toolbar.addWidget(QLabel("Add Node"), 0, 0)
        self._creatable_node_categories = CREATABLE_NODE_CATEGORIES
        self.node_type_picker = QComboBox()
        self.node_type_picker.setObjectName("graphNodeTypePicker")
        self._reset_node_type_picker()
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
        return self.graph_toolbar_widget

    def _build_view_stack(self) -> QStackedWidget:
        """The one central stack every authoring task switches between."""

        from .graph_workspace import GraphCanvas, GraphPlaceholder

        self.canvas = PatternCanvas()
        self.canvas.originPositionRequested.connect(self.originPositionRequested)
        self.canvas.playerPositionRequested.connect(self.playerPositionRequested)
        self.canvas.bulletResourceDropped.connect(self.bulletResourceRequested)
        self.guides.toggled.connect(self.canvas.set_guides)

        self.graph_canvas = GraphCanvas()
        self.graph_canvas.nodeSelected.connect(self.graphNodeSelected)
        self.graph_canvas.nodePositionCommitted.connect(
            self.graphNodePositionRequested
        )
        self.graph_canvas.edgeRequested.connect(self.graphEdgeRequested)
        self.graph_canvas.nodeRemoveRequested.connect(self.graphNodeRemoveRequested)
        self.graph_canvas.edgeRemoveRequested.connect(self.graphEdgeRemoveRequested)
        self.graph_canvas.actionSearchRequested.connect(self.actionSearchRequested)
        self.graph_placeholder = GraphPlaceholder()
        self.graph_placeholder.expandRequested.connect(self.graphExpandRequested)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.canvas)
        self.stack.addWidget(self.graph_canvas)
        self.stack.addWidget(self.graph_placeholder)
        self.stack.addWidget(self._build_preset_view())
        self.stack.addWidget(self._build_advanced_view())
        self.stack.addWidget(self._build_source_view())
        return self.stack

    def _build_preset_view(self) -> QWidget:
        """Read-only preset expansion plus its parameter, slot and version rows."""

        self.preset_view = QWidget()
        preset_layout = QVBoxLayout(self.preset_view)
        preset_layout.setContentsMargins(8, 8, 8, 8)
        self.preset_summary = QLabel("Preset Details")
        self.preset_summary.setObjectName("presetSummary")
        self.preset_summary.setWordWrap(True)
        preset_layout.addWidget(self.preset_summary)
        self.preset_nodes = QListWidget()
        self.preset_nodes.setObjectName("presetVirtualNodes")
        self.preset_nodes.setToolTip("Read-only virtual expansion; no nodes are copied into the Pattern")
        preset_layout.addWidget(self.preset_nodes, 1)
        self.preset_parameter_form = QGridLayout()
        preset_layout.addLayout(self.preset_parameter_form)
        self.preset_slot_form = QGridLayout()
        preset_layout.addLayout(self.preset_slot_form)
        migrate_row = QHBoxLayout()
        self.preset_version = QLabel("")
        self.preset_version.setObjectName("presetVersion")
        migrate_row.addWidget(self.preset_version)
        self.preset_migrate_target = QComboBox()
        self.preset_migrate_target.setObjectName("presetMigrateTarget")
        self.preset_migrate_target.setToolTip(
            "Only versions with an exact migration path are offered"
        )
        migrate_row.addWidget(self.preset_migrate_target)
        self.preset_migrate_button = QPushButton("Migrate")
        self.preset_migrate_button.setObjectName("presetMigrate")
        self.preset_migrate_button.clicked.connect(self._request_preset_migration)
        migrate_row.addWidget(self.preset_migrate_button)
        migrate_row.addStretch()
        preset_layout.addLayout(migrate_row)
        materialize = QPushButton("Make Local Copy")
        materialize.setObjectName("presetMaterialize")
        materialize.clicked.connect(self.presetMaterializeRequested)
        preset_layout.addWidget(materialize)
        return self.preset_view

    def _build_advanced_view(self) -> QWidget:
        """Explicit property bindings: constant, curve, variable or expression."""

        self.advanced_view = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_view)
        advanced_layout.addWidget(
            QLabel("Bind an exact Pattern property to a constant, curve, variable, or expression.")
        )
        binding_row = QHBoxLayout()
        self.binding_path = QComboBox()
        self.binding_path.setObjectName("patternBindingPath")
        binding_row.addWidget(self.binding_path)
        self.binding_kind = QComboBox()
        self.binding_kind.setObjectName("patternBindingKind")
        binding_row.addWidget(self.binding_kind)
        self.binding_value = QLineEdit()
        self.binding_value.setObjectName("patternBindingValue")
        self.binding_value.setPlaceholderText("2.0, res://curve…, rank, or expression")
        binding_row.addWidget(self.binding_value, 1)
        add_binding = QPushButton("Apply Binding")
        add_binding.setObjectName("patternApplyBinding")
        add_binding.clicked.connect(self._request_binding)
        binding_row.addWidget(add_binding)
        advanced_layout.addLayout(binding_row)
        self.binding_list = QListWidget()
        self.binding_list.setObjectName("patternBindingList")
        advanced_layout.addWidget(self.binding_list, 1)
        remove_binding = QPushButton("Remove Selected Binding")
        remove_binding.setObjectName("patternRemoveBinding")
        remove_binding.clicked.connect(self._request_remove_binding)
        advanced_layout.addWidget(remove_binding)
        return self.advanced_view

    def _build_source_view(self) -> QWidget:
        """Where a script-backed Pattern points the author at its own source."""

        self.source_view = QWidget()
        source_layout = QVBoxLayout(self.source_view)
        self.source_summary = QLabel()
        self.source_summary.setObjectName("patternRuntimeSourceSummary")
        self.source_summary.setWordWrap(True)
        source_layout.addWidget(self.source_summary)
        self.open_source = QPushButton("Open Script Source")
        self.open_source.setObjectName("patternOpenRuntimeSource")
        self.open_source.clicked.connect(self._request_source_navigation)
        source_layout.addWidget(self.open_source)
        source_layout.addStretch()
        return self.source_view

    def set_language_manager(self, manager: LanguageManager) -> None:
        self._language_manager = manager
        self.graph_canvas.set_language_manager(manager)
        self._reset_node_type_picker()
        self._reset_binding_pickers()

    def _tr(self, text: str) -> str:
        return (
            self._language_manager.translate(text)
            if self._language_manager is not None
            else text
        )

    def _reset_node_type_picker(self) -> None:
        current = self.node_type_picker.currentData()
        labels = {
            "source": "Bullet source",
            "shape": "Emission shape",
            "aim": "Aiming",
            "schedule": "Fire rhythm",
            "motion": "Bullet motion",
            "modifier": "Per-burst changes",
        }
        self.node_type_picker.blockSignals(True)
        self.node_type_picker.clear()
        for category, node_type in self._creatable_node_categories:
            self.node_type_picker.addItem(
                self._tr(labels[category]), (category, node_type)
            )
        index = self.node_type_picker.findData(current)
        self.node_type_picker.setCurrentIndex(max(0, index))
        self.node_type_picker.blockSignals(False)

    def _binding_path_label(self, path: str) -> str:
        labels = {
            "shape.count": "Bullet Count",
            "shape.angle_span": "Angle Span",
            "aim.angle": "Aim Angle",
            "schedule.interval_frames": "Fire Interval",
            "motion.speed": "Bullet Speed",
            "motion.spin": "Spin Speed",
            "modifiers.angle_offset_per_burst": "Angle Change per Burst",
        }
        return self._tr(labels.get(path, path))

    def _reset_binding_pickers(self) -> None:
        current_path = self.binding_path.currentData()
        current_kind = self.binding_kind.currentData()
        self.binding_path.clear()
        for path in (
            "shape.count", "shape.angle_span", "aim.angle",
            "schedule.interval_frames", "motion.speed", "motion.spin",
            "modifiers.angle_offset_per_burst",
        ):
            self.binding_path.addItem(self._binding_path_label(path), path)
        self.binding_kind.clear()
        for label, kind in (
            ("Fixed Value", "constant"),
            ("Curve", "curve"),
            ("Variable", "variable"),
            ("Expression", "expression"),
        ):
            self.binding_kind.addItem(self._tr(label), kind)
        path_index = self.binding_path.findData(current_path)
        kind_index = self.binding_kind.findData(current_kind)
        self.binding_path.setCurrentIndex(max(0, path_index))
        self.binding_kind.setCurrentIndex(max(0, kind_index))

    def _preset_slot_label(self, slot) -> str:
        labels = {"termination_reaction": "Lifecycle Reaction"}
        fallback = slot.id.replace("_", " ").title()
        return self._tr(labels.get(slot.id, fallback))

    def _request_preset_migration(self) -> None:
        target = self.preset_migrate_target.currentData()
        if target:
            self.presetMigrateRequested.emit(str(target))

    def _preset_parameter_label(self, parameter) -> str:
        labels = {
            "shape.count": "Bullet Count",
            "motion.speed": "Bullet Speed",
            "schedule.interval_frames": "Fire Interval",
            "schedule.burst_count": "Number of Bursts",
            "shape.angle_span": "Angle Span",
            "aim.angle": "Aim Angle",
            "motion.spin": "Spin Speed",
            "modifiers.angle_offset_per_burst": "Angle Change per Burst",
            "modifiers.speed_offset_per_burst": "Speed Change per Burst",
            "modifiers.random_speed_variation": "Random Speed Variation",
        }
        fallback = parameter.id.replace("_", " ").title()
        return self._tr(labels.get(parameter.target, fallback))

    def _reset_level_picker(self, has_preset: bool) -> None:
        from .progressive_authoring import AUTHORING_LEVELS

        current = self._authoring_level
        self._level_switching = True
        self.level_picker.clear()
        for level in AUTHORING_LEVELS:
            if level.id == "l0" and not has_preset:
                continue
            self.level_picker.addItem(level.label, level.id)
        index = self.level_picker.findData(current)
        if index < 0:
            current = "l1"
            index = self.level_picker.findData(current)
        self.level_picker.setCurrentIndex(max(0, index))
        self._authoring_level = current
        self._level_switching = False

    def _level_changed(self) -> None:
        if self._level_switching:
            return
        level = str(self.level_picker.currentData() or "l1")
        self.authoringLevelRequested.emit(level)

    def set_authoring_level(self, level: str, *, emit: bool = False) -> None:
        level = str(level)
        index = self.level_picker.findData(level)
        if index < 0:
            raise ValueError(f"unsupported available authoring level: {level}")
        self._authoring_level = level
        self._level_switching = True
        self.level_picker.setCurrentIndex(index)
        self._level_switching = False
        if level == "l0":
            self.set_mode("preset", emit=False)
        elif level == "l1":
            self.set_mode("recipe", emit=False)
        elif level == "l2":
            self._mode = "advanced"
            self._show_view(self.advanced_view)
        elif level == "l3":
            self.set_mode("graph", emit=False)
        else:
            self._mode = "source"
            self._show_view(self.source_view)
        if emit:
            self.authoringLevelRequested.emit(level)

    def _show_view(self, widget: QWidget, *, graph_chrome: bool = False) -> None:
        """Swap the central view; only the graph tasks carry the graph chrome."""

        self.fold_button.setVisible(graph_chrome)
        self.graph_toolbar_widget.setVisible(graph_chrome)
        self.stack.setCurrentWidget(widget)

    def authoring_level(self) -> str:
        return self._authoring_level

    def available_modes(self) -> tuple[str, ...]:
        """View modes the current document can reach, in navigation order."""

        modes = ["recipe", "graph"]
        if self._preset_mode_available:
            modes.insert(0, "preset")
        return tuple(modes)

    def _refresh_mode(self) -> None:
        document = self._document
        if self._mode == "preset":
            self._show_view(self.preset_view)
        elif self._mode == "graph":
            if document is not None and document.graph is not None:
                self.graph_canvas.set_graph(document.graph)
                self._show_view(self.graph_canvas, graph_chrome=True)
            else:
                self._show_view(self.graph_placeholder, graph_chrome=True)
        else:
            self._show_view(self.canvas)

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
        self.binding_list.clear()
        for binding in document.bindings:
            kind_label = {
                "constant": "Fixed Value",
                "curve": "Curve",
                "variable": "Variable",
                "expression": "Expression",
            }.get(binding.kind, binding.kind)
            item = (
                f"{self._binding_path_label(binding.path)} ← "
                f"{self._tr(kind_label)}: {binding.value}"
            )
            self.binding_list.addItem(item)
            self.binding_list.item(self.binding_list.count() - 1).setData(
                Qt.UserRole, binding.path
            )
        self._source_resource = (
            document.script.resource_uri if document.script is not None else ""
        )
        self.source_summary.setText(
            self._tr("Script extension: ") + self._source_resource
            if self._source_resource
            else self._tr(
                "No script extension is attached. This pattern uses the standard editor behavior."
            )
        )
        self.open_source.setEnabled(bool(self._source_resource))
        index = self.bullet_picker.findData(document.bullet.resource)
        if index >= 0:
            self.bullet_picker.setCurrentIndex(index)
        self._refresh_mode()

    def set_mode(self, mode: str, *, emit: bool = True) -> None:
        mode = str(mode)
        if mode not in {"recipe", "graph", "preset"}:
            raise ValueError(f"unsupported pattern workspace mode: {mode!r}")
        if emit:
            # A mode the document cannot reach is ignored rather than forced:
            # asking for the preset view of a local pattern is a no-op, not an
            # error, and callers rely on that.
            if mode not in self.available_modes():
                return
            changed = mode != self._mode
            self._mode = mode
            self._refresh_mode()
            if changed:
                self.graphModeChanged.emit(mode)
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

    def set_available_presets(
        self, descriptors: tuple[PresetDescriptor, ...]
    ) -> None:
        current = self.template_picker.currentData()
        self.template_picker.clear()
        for descriptor in descriptors:
            self.template_picker.addItem(
                f"{descriptor.display_name} · {self._tr(descriptor.category)}",
                f"{descriptor.preset_id}@{descriptor.version}",
            )
        index = self.template_picker.findData(current)
        if index >= 0:
            self.template_picker.setCurrentIndex(index)

    def set_preset_expansion(
        self,
        descriptor: PresetDescriptor | None,
        nodes: tuple[VirtualPresetNode, ...] = (),
        parameters: dict[str, object] | None = None,
        slots: dict[str, object] | None = None,
        migration_targets: tuple[str, ...] = (),
    ) -> None:
        self._preset_descriptor = descriptor
        self._preset_nodes = tuple(nodes)
        if descriptor is None:
            self._preset_mode_available = False
            if self._mode == "preset":
                self.set_mode("recipe", emit=False)
            self._reset_level_picker(False)
            self._clear_preset_slots()
            self.preset_version.setText("")
            self.preset_migrate_target.clear()
            self.preset_migrate_button.setEnabled(False)
            return
        self._preset_mode_available = True
        self._reset_level_picker(True)
        self.preset_summary.setText(
            f"{descriptor.display_name}\n"
            + self._tr(
                "Expand the structure below to learn how the preset works. Parameter changes remain editable."
            )
        )
        self.preset_nodes.clear()
        while self.preset_parameter_form.count():
            item = self.preset_parameter_form.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for node in self._preset_nodes:
            self.preset_nodes.addItem(node.label)
        values = dict(parameters or {})
        for row, parameter in enumerate(descriptor.parameters):
            value = values.get(parameter.id, parameter.default)
            label = QLabel(self._preset_parameter_label(parameter))
            label.setObjectName(f"presetParameterLabel_{parameter.id}")
            self.preset_parameter_form.addWidget(label, row, 0)
            if parameter.value_type == "int":
                editor = QSpinBox()
                editor.setRange(
                    int(parameter.minimum if parameter.minimum is not None else -1_000_000),
                    int(parameter.maximum if parameter.maximum is not None else 1_000_000),
                )
                editor.setValue(int(value))
                editor.editingFinished.connect(
                    lambda widget=editor, pid=parameter.id: self.presetParameterRequested.emit(
                        pid, widget.value()
                    )
                )
            else:
                editor = QDoubleSpinBox()
                editor.setDecimals(6)
                editor.setRange(
                    float(parameter.minimum if parameter.minimum is not None else -1_000_000),
                    float(parameter.maximum if parameter.maximum is not None else 1_000_000),
                )
                editor.setValue(float(value))
                editor.editingFinished.connect(
                    lambda widget=editor, pid=parameter.id: self.presetParameterRequested.emit(
                        pid, widget.value()
                    )
                )
            editor.setObjectName(f"presetParameter_{parameter.id}")
            self.preset_parameter_form.addWidget(editor, row, 1)
        self._populate_preset_slots(descriptor, dict(slots or {}))
        self._populate_preset_migration(descriptor, tuple(migration_targets))

    def _clear_preset_slots(self) -> None:
        while self.preset_slot_form.count():
            item = self.preset_slot_form.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _populate_preset_slots(
        self,
        descriptor: PresetDescriptor,
        overrides: dict[str, object],
    ) -> None:
        self._clear_preset_slots()
        for row, slot in enumerate(descriptor.slots):
            label = QLabel(self._preset_slot_label(slot))
            label.setObjectName(f"presetSlotLabel_{slot.id}")
            self.preset_slot_form.addWidget(label, row, 0)
            value = overrides.get(slot.id, slot.default)
            if slot.value_type == "reaction":
                editor = PresetReactionSlotEditor(
                    slot.id, value, nullable=slot.nullable
                )
                editor.valueChanged.connect(
                    lambda payload, sid=slot.id: self.presetSlotRequested.emit(
                        sid, payload
                    )
                )
            else:
                # Slots share the preset value-type vocabulary with parameters,
                # so anything non-structural reuses the same numeric editor.
                editor = QDoubleSpinBox()
                editor.setDecimals(6)
                editor.setRange(-1_000_000.0, 1_000_000.0)
                editor.setValue(float(value or 0.0))
                editor.editingFinished.connect(
                    lambda widget=editor, sid=slot.id: self.presetSlotRequested.emit(
                        sid, widget.value()
                    )
                )
            editor.setObjectName(f"presetSlot_{slot.id}")
            self.preset_slot_form.addWidget(editor, row, 1)

    def _populate_preset_migration(
        self,
        descriptor: PresetDescriptor,
        targets: tuple[str, ...],
    ) -> None:
        self.preset_version.setText(
            self._tr("Version") + f" {descriptor.version}"
        )
        self.preset_migrate_target.clear()
        for version in targets:
            self.preset_migrate_target.addItem(version, version)
        # Offering a disabled button beats hiding the control: an author who
        # looks for the upgrade path learns there is none for this version.
        self.preset_migrate_target.setEnabled(bool(targets))
        self.preset_migrate_button.setEnabled(bool(targets))

    @property
    def virtual_preset_nodes(self) -> tuple[VirtualPresetNode, ...]:
        return self._preset_nodes

    def _assign_bullet(self) -> None:
        value = self.bullet_picker.currentData()
        if value:
            self.bulletResourceRequested.emit(str(value))

    def _request_binding(self) -> None:
        path = str(self.binding_path.currentData())
        kind = str(self.binding_kind.currentData())
        text = self.binding_value.text().strip()
        value: object = text
        if kind == "constant":
            try:
                value = float(text)
            except ValueError:
                value = text
        self.patternBindingRequested.emit(path, kind, value)

    def _request_remove_binding(self) -> None:
        item = self.binding_list.currentItem()
        if item is not None:
            self.patternBindingRemoveRequested.emit(str(item.data(Qt.UserRole)))

    def _request_source_navigation(self) -> None:
        if self._source_resource:
            self.sourceNavigateRequested.emit(self._source_resource)

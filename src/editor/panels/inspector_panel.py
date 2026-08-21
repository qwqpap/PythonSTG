"""Inspector dock: per-selection property forms for every document kind."""

from __future__ import annotations

import json
from src.qt_compat.QtCore import Qt, pyqtSignal
from src.qt_compat.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)
from src.pattern import PatternDocument
from ..document import EditorNode, TimelineClip, TimelineTrack
from ..node_types import PropertySpec, property_specs
from ..resource_browser import RESOURCE_MIME_TYPE
from ..i18n import LanguageManager
from ..graphics.graph_canvas import GRAPH_NODE_PROPERTY_SPECS
from src.ui.document import ANIMATABLE_PROPERTIES


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


_GRAPH_NODE_DEFAULTS: dict[str, object] = {
    "count": 24,
    "origin_x": 0.0,
    "origin_y": 0.65,
    "angle_span": 360.0,
    "line_length": 1.0,
    "line_angle": 0.0,
    "angle": 270.0,
    "delay_frames": 0,
    "interval_frames": 20,
    "burst_count": 1,
    "loop_count": 1,
    "speed": 2.0,
    "friction": 0.0,
    "spin": 0.0,
    "time_scale": 1.0,
    "max_lifetime": 0.0,
    "render_scale": 1.0,
    "bounce_x": False,
    "bounce_y": False,
    "angle_offset_per_burst": 0.0,
    "speed_offset_per_burst": 0.0,
    "random_speed_variation": 0.0,
    "bullet_type": "ball_m",
    "color": "red",
    "resource": None,
}

_BULLET_TYPE_CHOICES = (
    "ball_s", "ball_m", "ball_l", "knife", "star_s", "star_m", "star_l",
    "arrow_s", "arrow_m", "arrow_l", "square", "butterfly", "ellipse",
    "kite", "heart", "grain_a", "grain_b", "grain_c", "gun", "mildew",
    "ball_light", "silence", "needle", "scale", "fire", "scale_s", "rice_s",
)
_BULLET_COLOR_CHOICES = (
    "black", "blue", "cyan", "darkblue", "darkcyan", "darkgreen", "darkorange",
    "darkpurple", "darkred", "darkyellow", "gray", "green", "orange", "pink",
    "purple", "red", "white", "yellow",
)


def _coerce_graph_value(original, text: str):
    """Parse an Inspector text edit back to the node property's type."""
    raw = str(text).strip()
    if original is None:
        return None if raw in {"", "null", "None"} else raw
    if isinstance(original, bool):
        return original
    if isinstance(original, int):
        try:
            return int(raw)
        except ValueError:
            return original
    if isinstance(original, float):
        try:
            return float(raw)
        except ValueError:
            return original
    return raw


def _coerce_ui_value(original, text: str):
    """Parse an Inspector text edit back to the UI node property's type."""
    raw = str(text).strip()
    if original is None:
        return None if raw in {"", "null", "None"} else raw
    if isinstance(original, bool):
        return raw.strip().lower() in {"true", "1", "yes"}
    if isinstance(original, int):
        try:
            return int(raw)
        except ValueError:
            return original
    if isinstance(original, float):
        try:
            return float(raw)
        except ValueError:
            return original
    return raw


class InspectorPanel(QScrollArea):
    renameRequested = pyqtSignal(str, str)
    propertyRequested = pyqtSignal(str, str, object)
    patternPropertyRequested = pyqtSignal(str, object)
    graphNodePropertyRequested = pyqtSignal(str, object)
    uiNodePropertyRequested = pyqtSignal(str, object)
    backgroundPropertyRequested = pyqtSignal(str, object)
    timelineClipPropertiesRequested = pyqtSignal(str, object)
    timelineTrackPropertiesRequested = pyqtSignal(str, object)
    timelineKeyframePropertiesRequested = pyqtSignal(str, str, object)

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
        self._timeline_track_id: str | None = None
        self.node_registry = None
        self._language_manager: LanguageManager | None = None

    def set_language_manager(self, manager: LanguageManager) -> None:
        self._language_manager = manager

    def _tr(self, text: object) -> str:
        value = str(text)
        return (
            self._language_manager.translate(value)
            if self._language_manager is not None
            else value
        )

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
        self._timeline_track_id = None
        if node is None:
            self._form.addRow(QLabel("No node selected"))
            return

        spec = (
            self.node_registry.get(node.type)
            if self.node_registry is not None
            else None
        )
        display_name = node.name
        if spec is not None and node.name == spec.display_name:
            display_name = self._tr(node.name)
        elif node.type == "SceneRoot" and node.name == "Untitled Scene":
            display_name = self._tr(node.name)
        name_edit = QLineEdit(display_name)
        name_edit.setObjectName("inspectorName")
        name_edit.editingFinished.connect(
            lambda edit=name_edit, node_id=node.id: self.renameRequested.emit(
                node_id,
                edit.text(),
            )
        )
        self._form.addRow("Name", name_edit)

        type_edit = QLineEdit(self._tr(node.type))
        type_edit.setReadOnly(True)
        self._form.addRow("Type", type_edit)

        specs = (
            self.node_registry.get(node.type).properties
            if self.node_registry is not None and self.node_registry.get(node.type) is not None
            else property_specs(node.type)
        )
        for spec in specs:
            value = node.properties.get(spec.key, spec.default)
            editor = self._make_editor(node.id, spec, value)
            self._form.addRow(spec.label, editor)

        known = {spec.key for spec in specs}
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
        self._timeline_track_id = None
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

    def set_graph_node(self, node) -> None:
        """Show property editors for one selected behavior graph node."""
        self._clear_form()
        self._node_id = None
        self._pattern_id = None
        self._timeline_clip_id = None
        self._timeline_track_id = None
        if node is None:
            self._form.addRow(QLabel("No node selected"))
            return
        title = QLabel(
            f"{self._tr(node.category.title())} · {self._tr(node.node_type)}"
        )
        title.setObjectName("inspectorGraphNodeTitle")
        title.setStyleSheet("font-weight:600; color:#9fc5ff;")
        self._form.addRow(title)
        type_edit = QLineEdit(
            f"{self._tr(node.category.title())} / {self._tr(node.node_type)}"
        )
        type_edit.setReadOnly(True)
        self._form.addRow("Type", type_edit)
        for key, label, kind in GRAPH_NODE_PROPERTY_SPECS.get(node.category, ()):
            value = node.properties.get(key, _GRAPH_NODE_DEFAULTS.get(key))
            editor = self._make_graph_property_editor(node.id, key, value)
            self._form.addRow(self._tr(label), editor)

    def set_ui_node(self, node) -> None:
        """Show property editors for one selected UI document node."""
        self._clear_form()
        self._node_id = None
        self._pattern_id = None
        self._timeline_clip_id = None
        self._timeline_track_id = None
        if node is None:
            self._form.addRow(QLabel("No UI node selected"))
            return
        title = QLabel(f"{node.node_type} · {node.name}")
        title.setObjectName("inspectorUiNodeTitle")
        title.setStyleSheet("font-weight:600; color:#9fc5ff;")
        self._form.addRow(title)
        for key in ("x", "y", "width", "height", "visible"):
            value = getattr(node, key)
            editor = self._make_ui_property_editor(node.id, key, value)
            self._form.addRow(key.title(), editor)
        for key in ANIMATABLE_PROPERTIES.get(node.node_type, ()):
            if key in {"x", "y", "width", "height"}:
                continue
            value = getattr(node, key, None)
            if isinstance(value, tuple):
                value = list(value)
            editor = self._make_ui_property_editor(node.id, key, value)
            self._form.addRow(key.replace("_", " ").title(), editor)

    def set_background_document(self, document) -> None:
        """Show editable camera/fog/scroll/layer properties.

        Values are emitted as property paths and are committed by the owning
        ``ManagedDocument`` through ``SetBackgroundPropertyCommand``.  The
        Inspector never mutates the document directly.
        """
        self._clear_form()
        self._node_id = None
        self._pattern_id = None
        self._timeline_clip_id = None
        self._timeline_track_id = None
        title = QLabel(f"Background: {document.name}")
        title.setObjectName("inspectorBackgroundTitle")
        title.setStyleSheet("font-weight:600; color:#9fc5ff;")
        self._form.addRow(title)
        body = document.body
        camera = body.get("camera") or {}
        for key in ("eye", "at", "up", "fovy", "z_near", "z_far"):
            value = camera.get(key)
            if value is None:
                continue
            editor = self._make_background_editor(f"camera.{key}", value)
            self._form.addRow(f"Camera {key}", editor)
        fog = body.get("fog") or {}
        for key in ("enabled", "color", "start", "end"):
            if key in fog:
                self._form.addRow(
                    f"Fog {key}",
                    self._make_background_editor(f"fog.{key}", fog[key]),
                )
        scroll = body.get("scroll") or {}
        for key in ("base_speed", "direction"):
            if key in scroll:
                self._form.addRow(
                    f"Scroll {key}",
                    self._make_background_editor(f"scroll.{key}", scroll[key]),
                )
        layers = body.get("layers") or []
        layer_label = QLabel(f"{len(layers)} layers")
        layer_label.setWordWrap(True)
        self._form.addRow("Layers", layer_label)
        for index, layer in enumerate(layers[:8]):
            prefix = f"layers.{index}"
            for key in ("name", "texture", "z_order", "z_depth", "blend_mode", "alpha", "scroll_multiplier", "enabled"):
                if key in layer:
                    self._form.addRow(
                        f"Layer {index} {key}",
                        self._make_background_editor(f"{prefix}.{key}", layer[key]),
                    )
            transform = layer.get("transform") or {}
            for key in ("x", "y", "scale", "rotation"):
                if key in transform:
                    self._form.addRow(
                        f"Layer {index} transform {key}",
                        self._make_background_editor(
                            f"{prefix}.transform.{key}", transform[key]
                        ),
                    )

    def _make_background_editor(self, path: str, value):
        if isinstance(value, bool):
            editor = QCheckBox()
            editor.setChecked(value)
            editor.toggled.connect(
                lambda checked, target=path: self.backgroundPropertyRequested.emit(
                    target, bool(checked)
                )
            )
            return editor
        if isinstance(value, int) and not isinstance(value, bool):
            editor = QSpinBox()
            editor.setRange(-1_000_000, 1_000_000)
            editor.setValue(value)
            editor.valueChanged.connect(
                lambda number, target=path: self.backgroundPropertyRequested.emit(
                    target, int(number)
                )
            )
            return editor
        if isinstance(value, float):
            editor = QDoubleSpinBox()
            editor.setDecimals(5)
            editor.setRange(-1_000_000.0, 1_000_000.0)
            editor.setValue(value)
            editor.valueChanged.connect(
                lambda number, target=path: self.backgroundPropertyRequested.emit(
                    target, float(number)
                )
            )
            return editor
        editor = QLineEdit(
            json.dumps(value, ensure_ascii=False)
            if isinstance(value, (list, tuple, dict))
            else str(value)
        )

        def commit(edit=editor, target=path, original=value):
            raw = edit.text().strip()
            parsed = raw
            if isinstance(original, (list, tuple, dict)):
                try:
                    parsed = json.loads(raw)
                except (TypeError, ValueError):
                    parsed = original
                if isinstance(original, tuple) and isinstance(parsed, list):
                    parsed = tuple(parsed)
            self.backgroundPropertyRequested.emit(target, parsed)

        editor.editingFinished.connect(commit)
        return editor

    def _make_ui_property_editor(self, node_id: str, key: str, value):
        if isinstance(value, bool):
            editor = QCheckBox()
            editor.setChecked(value)
            editor.toggled.connect(
                lambda checked, nid=node_id, k=key: self.uiNodePropertyRequested.emit(
                    nid, {k: checked}
                )
            )
        elif isinstance(value, (int, float)):
            editor = QDoubleSpinBox()
            editor.setDecimals(6)
            editor.setRange(-1_000_000_000.0, 1_000_000_000.0)
            editor.setSingleStep(0.1)
            editor.setValue(float(value))
            editor.editingFinished.connect(
                lambda spin=editor, nid=node_id, k=key, original=value: self.uiNodePropertyRequested.emit(
                    nid,
                    {
                        k: int(spin.value())
                        if isinstance(original, int)
                        else spin.value()
                    },
                )
            )
        elif isinstance(value, list):
            editor = QLineEdit(json.dumps(value))
            editor.editingFinished.connect(
                lambda edit=editor, nid=node_id, k=key: self.uiNodePropertyRequested.emit(
                    nid, {k: json.loads(edit.text()) if edit.text().strip() else []}
                )
            )
        else:
            editor = QLineEdit("" if value is None else str(value))
            editor.editingFinished.connect(
                lambda edit=editor, nid=node_id, k=key, original=value: self.uiNodePropertyRequested.emit(
                    nid, {k: _coerce_ui_value(original, edit.text())}
                )
            )
        editor.setObjectName("uiNodeProperty_" + key)
        return editor

    def _make_graph_property_editor(self, node_id: str, key: str, value):
        choices = {
            "bullet_type": _BULLET_TYPE_CHOICES,
            "color": _BULLET_COLOR_CHOICES,
        }
        if key in choices:
            editor = QComboBox()
            for choice in choices[key]:
                editor.addItem(self._tr(choice), choice)
            index = editor.findData(str(value))
            if index < 0:
                editor.addItem(str(value), str(value))
                index = editor.count() - 1
            editor.setCurrentIndex(index)
            editor.currentIndexChanged.connect(
                lambda _index, combo=editor, nid=node_id, k=key: self.graphNodePropertyRequested.emit(
                    nid, {k: str(combo.currentData())}
                )
            )
        elif isinstance(value, bool):
            editor = QCheckBox()
            editor.setChecked(value)
            editor.toggled.connect(
                lambda checked, nid=node_id, k=key: self.graphNodePropertyRequested.emit(
                    nid, {k: checked}
                )
            )
        elif isinstance(value, (int, float)):
            editor = QDoubleSpinBox()
            editor.setDecimals(6)
            editor.setRange(-1_000_000_000.0, 1_000_000_000.0)
            editor.setSingleStep(0.1)
            editor.setValue(float(value))
            editor.editingFinished.connect(
                lambda spin=editor, nid=node_id, k=key: self.graphNodePropertyRequested.emit(
                    nid,
                    {
                        k: int(spin.value())
                        if isinstance(value, int)
                        else spin.value()
                    },
                )
            )
        else:
            editor = QLineEdit("" if value is None else str(value))
            editor.editingFinished.connect(
                lambda edit=editor, nid=node_id, k=key, original=value: self.graphNodePropertyRequested.emit(
                    nid,
                    {k: _coerce_graph_value(original, edit.text())},
                )
            )
        editor.setObjectName("graphNodeProperty_" + key)
        return editor

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
        self._timeline_track_id = None
        self._build_clip_identity(track, clip)
        self._build_clip_fields(clip, nodes)
        self._build_clip_payload(clip)

    def _build_clip_identity(self, track: TimelineTrack, clip: TimelineClip) -> None:
        """Header, name/kind rows and the reactive-activation summary."""
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
        if clip.kind == "Reactive":
            activation = clip.payload.get("activation")
            reaction = clip.payload.get("reaction")
            activation_kind = (
                str(activation.get("kind"))
                if isinstance(activation, dict) and activation.get("kind")
                else "event"
            )
            activation_label = QLabel(activation_kind)
            activation_label.setObjectName("timelineReactiveActivation")
            self._form.addRow("Activation", activation_label)
            reaction_id = (
                str(reaction.get("id"))
                if isinstance(reaction, dict) and reaction.get("id")
                else ""
            )
            reaction_label = QLabel(reaction_id or "(inline reaction)")
            reaction_label.setObjectName("timelineReactiveReaction")
            self._form.addRow("Reaction", reaction_label)
            scope_label = QLabel(str(clip.payload.get("scope", "state")))
            scope_label.setObjectName("timelineReactiveScope")
            self._form.addRow("Scope", scope_label)
            owner_label = QLabel(str(clip.payload.get("owner_id") or "(track/state)"))
            owner_label.setObjectName("timelineReactiveOwner")
            self._form.addRow("Owner", owner_label)

    def _build_clip_fields(self, clip: TimelineClip, nodes: list[EditorNode]) -> None:
        """Timing spins, the enabled toggle, target picker and channel row."""
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
        property_name = str(clip.payload.get("property") or clip.channel)
        compatible_nodes = [
            node
            for node in nodes
            if (
                clip.kind != "Movement"
                or (
                    isinstance(node.properties.get("x"), (int, float))
                    and not isinstance(node.properties.get("x"), bool)
                    and isinstance(node.properties.get("y"), (int, float))
                    and not isinstance(node.properties.get("y"), bool)
                )
            )
            and (
                clip.kind != "Property"
                or property_name in node.properties
            )
        ]
        for node in compatible_nodes:
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

    def _build_clip_payload(self, clip: TimelineClip) -> None:
        """JSON payload editor and the editable keyframe table."""
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

        keyframes = QTableWidget(len(clip.keyframes), 3)
        keyframes.setObjectName("timelineKeyframeTable")
        keyframes.setHorizontalHeaderLabels(["Frame", "Value", "Interpolation"])
        keyframes.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        keyframes.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        keyframes.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        keyframes.setMinimumHeight(120)
        keyframes.blockSignals(True)
        for row, item in enumerate(clip.keyframes):
            frame_item = QTableWidgetItem(str(item.frame))
            frame_item.setData(Qt.UserRole, item.id)
            keyframes.setItem(row, 0, frame_item)
            keyframes.setItem(
                row,
                1,
                QTableWidgetItem(json.dumps(item.value, ensure_ascii=False)),
            )
            keyframes.setItem(row, 2, QTableWidgetItem(item.interpolation))
        keyframes.blockSignals(False)

        def commit_keyframe(item: QTableWidgetItem) -> None:
            frame_item = keyframes.item(item.row(), 0)
            if frame_item is None:
                return
            keyframe_id = str(frame_item.data(Qt.UserRole) or "")
            try:
                if item.column() == 0:
                    values = {"frame": int(item.text())}
                elif item.column() == 1:
                    values = {"value": json.loads(item.text())}
                else:
                    values = {"interpolation": item.text().strip()}
            except (ValueError, json.JSONDecodeError) as exc:
                error.setText(str(exc))
                return
            error.clear()
            self.timelineKeyframePropertiesRequested.emit(
                clip.id,
                keyframe_id,
                values,
            )

        keyframes.itemChanged.connect(commit_keyframe)
        self._form.addRow("Keyframes", keyframes)
        self._form.addRow(error)

    def set_timeline_track(
        self,
        track: TimelineTrack,
        nodes: list[EditorNode],
    ) -> None:
        self._clear_form()
        self._node_id = None
        self._pattern_id = None
        self._timeline_clip_id = None
        self._timeline_track_id = track.id
        title = QLabel(f"{track.name} / {track.kind} Track")
        title.setStyleSheet("font-weight:600; color:#9fc5ff;")
        self._form.addRow(title)

        name = QLineEdit(track.name)
        name.setObjectName("timelineTrackName")
        name.editingFinished.connect(
            lambda edit=name, track_id=track.id: self.timelineTrackPropertiesRequested.emit(
                track_id, {"name": edit.text().strip()}
            )
        )
        self._form.addRow("Name", name)
        kind = QLineEdit(track.kind)
        kind.setReadOnly(True)
        self._form.addRow("Kind", kind)

        order = QSpinBox()
        order.setObjectName("timelineTrackOrder")
        order.setRange(0, 1_000_000)
        order.setValue(track.order)
        order.editingFinished.connect(
            lambda editor=order, track_id=track.id: self.timelineTrackPropertiesRequested.emit(
                track_id, {"order": editor.value()}
            )
        )
        self._form.addRow("Order", order)

        muted = QCheckBox()
        muted.setObjectName("timelineTrackMuted")
        muted.setChecked(track.muted)
        muted.toggled.connect(
            lambda checked, track_id=track.id: self.timelineTrackPropertiesRequested.emit(
                track_id, {"muted": checked}
            )
        )
        self._form.addRow("Muted", muted)

        target = QComboBox()
        target.setObjectName("timelineTrackTarget")
        target.addItem("(none)", None)
        compatible_nodes = [
            node
            for node in nodes
            if (
                track.kind != "Movement"
                or (
                    isinstance(node.properties.get("x"), (int, float))
                    and not isinstance(node.properties.get("x"), bool)
                    and isinstance(node.properties.get("y"), (int, float))
                    and not isinstance(node.properties.get("y"), bool)
                )
            )
            and (track.kind != "Property" or track.channel in node.properties)
        ]
        for node in compatible_nodes:
            target.addItem(f"{node.name} [{node.type}]", node.id)
        target.setCurrentIndex(max(0, target.findData(track.target_id)))
        target.activated.connect(
            lambda _index, combo=target, track_id=track.id: self.timelineTrackPropertiesRequested.emit(
                track_id, {"target_id": combo.currentData()}
            )
        )
        self._form.addRow("Target", target)

        channel = QLineEdit(track.channel)
        channel.setObjectName("timelineTrackChannel")
        channel.editingFinished.connect(
            lambda edit=channel, track_id=track.id: self.timelineTrackPropertiesRequested.emit(
                track_id, {"channel": edit.text().strip()}
            )
        )
        self._form.addRow("Channel", channel)

    def _pattern_label(self, path: str) -> str:
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
        labels = {
            "shape.kind": "Emission shape",
            "aim.mode": "Aiming mode",
        }
        label = labels.get(path, path.split(".")[-1].replace("_", " ").title())
        unit = units.get(path)
        return self._tr(f"{label} [{unit}]" if unit else label)

    def _make_pattern_editor(self, path: str, value):
        choices = {
            "bullet.bullet_type": _BULLET_TYPE_CHOICES,
            "bullet.color": _BULLET_COLOR_CHOICES,
            "shape.kind": ("ring", "arc", "line", "spiral", "random", "flower"),
            "aim.mode": ("fixed", "player"),
        }
        if path in choices:
            editor = QComboBox()
            for choice in choices[path]:
                editor.addItem(self._tr(choice), choice)
            index = editor.findData(str(value))
            editor.setCurrentIndex(max(0, index))
            editor.currentIndexChanged.connect(
                lambda _index, combo=editor, key=path: self.patternPropertyRequested.emit(
                    key, str(combo.currentData())
                )
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

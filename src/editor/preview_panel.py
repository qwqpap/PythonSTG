"""Compact controls and diagnostics for the external formal preview."""

from __future__ import annotations

import json

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class PatternPreviewPanel(QWidget):
    launchRequested = pyqtSignal()
    commandRequested = pyqtSignal(str, dict)
    propertyRequested = pyqtSignal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("patternPreviewPanel")
        self._resource = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        header = QHBoxLayout()
        self.resource_label = QLabel("No authoring resource selected")
        self.resource_label.setObjectName("previewResource")
        self.resource_label.setTextInteractionFlags(self.resource_label.textInteractionFlags())
        launch = QPushButton("Launch Preview")
        launch.setObjectName("previewLaunch")
        launch.clicked.connect(self.launchRequested)
        header.addWidget(self.resource_label, 1)
        header.addWidget(launch)
        root.addLayout(header)

        controls = QHBoxLayout()
        for text, name, command in (
            ("Play", "previewPlay", "play"),
            ("Pause", "previewPause", "pause"),
            ("Step", "previewStep", "step"),
            ("Reset", "previewReset", "reset"),
            ("Stop", "previewStop", "stop"),
        ):
            button = QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(
                lambda checked=False, cmd=command: self.commandRequested.emit(cmd, {})
            )
            controls.addWidget(button)
        self.seek_frame = QSpinBox()
        self.seek_frame.setObjectName("previewSeekFrame")
        self.seek_frame.setRange(0, 1_000_000)
        seek = QPushButton("Seek")
        seek.setObjectName("previewSeek")
        seek.clicked.connect(
            lambda: self.commandRequested.emit("seek", {"frame": self.seek_frame.value()})
        )
        controls.addWidget(self.seek_frame)
        controls.addWidget(seek)
        controls.addStretch()
        root.addLayout(controls)

        body_container = QWidget()
        body_container.setObjectName("previewBody")
        body = QGridLayout(body_container)
        body.setContentsMargins(0, 0, 0, 0)
        stats_box = QGroupBox("Runtime")
        stats_form = QFormLayout(stats_box)
        self.stats_labels = {}
        for key, label in (
            ("mode", "Mode"),
            ("state", "State"),
            ("frame", "Frame"),
            ("duration_frames", "Duration"),
            ("active_clips", "Active Clips"),
            ("bullet_count", "Bullets"),
            ("seed", "Seed"),
            ("update_ms", "Update"),
            ("render_ms", "Render"),
        ):
            value = QLabel("—")
            value.setObjectName(f"previewStat_{key}")
            self.stats_labels[key] = value
            stats_form.addRow(label, value)
        body.addWidget(stats_box, 0, 0)

        target_box = QGroupBox("Target / diagnostics")
        target_form = QFormLayout(target_box)
        self.player_x = QDoubleSpinBox()
        self.player_y = QDoubleSpinBox()
        for widget, name, value in (
            (self.player_x, "previewPlayerX", 0.0),
            (self.player_y, "previewPlayerY", -0.8),
        ):
            widget.setObjectName(name)
            widget.setRange(-4.0, 4.0)
            widget.setDecimals(3)
            widget.setSingleStep(0.05)
            widget.setValue(value)
        player_apply = QPushButton("Set player")
        player_apply.clicked.connect(
            lambda: self.commandRequested.emit(
                "set-player-position",
                {"x": self.player_x.value(), "y": self.player_y.value()},
            )
        )
        player_row = QWidget()
        player_layout = QHBoxLayout(player_row)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.addWidget(self.player_x)
        player_layout.addWidget(self.player_y)
        player_layout.addWidget(player_apply)
        target_form.addRow("Player X/Y", player_row)
        self.seed_edit = QLineEdit("0")
        self.seed_edit.setObjectName("previewSeed")
        self.seed_apply = QPushButton("Set seed")
        self.seed_apply.clicked.connect(self._set_seed)
        seed_row = QWidget()
        seed_layout = QHBoxLayout(seed_row)
        seed_layout.setContentsMargins(0, 0, 0, 0)
        seed_layout.addWidget(self.seed_edit)
        seed_layout.addWidget(self.seed_apply)
        target_form.addRow("Seed", seed_row)
        self.gizmos = QCheckBox("Grid, emitter and player gizmos")
        self.gizmos.setObjectName("previewGizmos")
        self.gizmos.setChecked(True)
        self.gizmos.toggled.connect(
            lambda visible: self.commandRequested.emit("set-gizmos", {"visible": visible})
        )
        target_form.addRow(self.gizmos)
        body.addWidget(target_box, 0, 1)

        self.live_box = QGroupBox("Live Inspector property")
        live_form = QFormLayout(self.live_box)
        self.property_path = QLineEdit("shape.count")
        self.property_path.setObjectName("previewPropertyPath")
        self.property_value = QLineEdit("24")
        self.property_value.setObjectName("previewPropertyValue")
        apply_property = QPushButton("Apply / reload")
        apply_property.setObjectName("previewPropertyApply")
        apply_property.clicked.connect(self._apply_property)
        live_form.addRow("Path", self.property_path)
        live_form.addRow("JSON value", self.property_value)
        live_form.addRow(apply_property)
        body.addWidget(self.live_box, 0, 2)
        body.setColumnStretch(0, 1)
        body.setColumnStretch(1, 2)
        body.setColumnStretch(2, 2)
        body_scroll = QScrollArea()
        body_scroll.setObjectName("previewBodyScroll")
        body_scroll.setWidgetResizable(True)
        body_scroll.setFrameShape(QScrollArea.NoFrame)
        body_scroll.setMinimumHeight(72)
        body_scroll.setWidget(body_container)
        root.addWidget(body_scroll, 1)

        self.status_label = QLabel("Preview process is stopped")
        self.status_label.setObjectName("previewStatus")
        self.status_label.setWordWrap(True)
        self.error_label = QLabel("")
        self.error_label.setObjectName("previewError")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #ff9ca8;")
        root.addWidget(self.status_label)
        root.addWidget(self.error_label)

    def set_resource(self, resource: str) -> None:
        self._resource = resource
        self.resource_label.setText(resource or "No authoring resource selected")

    def set_mode(self, mode: str) -> None:
        is_stage = mode == "stage"
        self.seed_edit.setEnabled(not is_stage)
        self.seed_apply.setEnabled(not is_stage)
        self.live_box.setEnabled(not is_stage)
        self.live_box.setTitle(
            "Edit Scene clips in Timeline" if is_stage else "Live Inspector property"
        )

    def _set_seed(self) -> None:
        try:
            seed = int(self.seed_edit.text().strip())
        except ValueError:
            self.error_label.setText("Seed must be an integer")
            return
        self.propertyRequested.emit("seed", seed)

    def _apply_property(self) -> None:
        path = self.property_path.text().strip()
        raw = self.property_value.text().strip()
        if not path:
            self.error_label.setText("Property path is required")
            return
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        self.propertyRequested.emit(path, value)

    def set_running(self, running: bool) -> None:
        self.status_label.setText(
            "Starting preview process…" if running else "Preview process is stopped"
        )
        if running:
            self.error_label.clear()

    def handle_issue(self, issue: dict) -> None:
        self.error_label.setText(f'{issue.get("code", "preview")}: {issue.get("message", "")}'.strip())

    def handle_event(self, message: dict) -> None:
        event = message.get("event")
        payload = message.get("payload") or {}
        if event == "hello":
            self.status_label.setText(f'Connected (protocol {payload.get("protocol_version")})')
        elif event == "status":
            self.status_label.setText(str(payload.get("message") or payload.get("state") or ""))
            self._set_stat("state", payload.get("state"))
            self._set_stat("frame", payload.get("frame"))
        elif event == "statistics":
            for key in self.stats_labels:
                value = payload.get(key)
                if key == "active_clips" and isinstance(value, list):
                    value = len(value)
                if key in {"update_ms", "render_ms"} and value is not None:
                    value = f"{float(value):.3f} ms"
                self._set_stat(key, value)
            self.gizmos.blockSignals(True)
            self.gizmos.setChecked(bool(payload.get("gizmos", True)))
            self.gizmos.blockSignals(False)
            error = payload.get("last_error")
            if error:
                self._show_preview_error(error)
        elif event in {"compile_error", "runtime_error", "protocol_error"}:
            self._show_preview_error(payload)
        elif event == "response" and not payload.get("ok", False):
            self._show_preview_error(payload.get("error") or payload)
        elif event == "program_loaded":
            self.error_label.clear()
            self.set_mode(str(payload.get("mode") or "pattern"))
            self.seed_edit.setText(str(payload.get("seed", 0)))

    def _set_stat(self, key: str, value) -> None:
        if key in self.stats_labels:
            self.stats_labels[key].setText("—" if value is None else str(value))

    def _show_preview_error(self, error: dict) -> None:
        message = error.get("message")
        if not message and error.get("diagnostics"):
            diagnostic = error["diagnostics"][0]
            message = f'{diagnostic.get("path")}: {diagnostic.get("message")}'
        preserved = " Last valid program remains active." if error.get("active_program_preserved") else ""
        self.error_label.setText(f"{message or 'Preview error'}.{preserved}".strip())

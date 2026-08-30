"""Inspector fields derived from public DSL constructor signatures."""

from __future__ import annotations

import ast
import inspect
import types
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from src.authoring import dsl
from src.authoring.program import (
    Expr,
    Parameter,
    ProgramError,
    Ref,
    parse_author_value,
    reference_kinds_for_field,
)
from src.qt_compat.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from src.qt_compat.QtGui import QColor, QPainter, QPen
from src.qt_compat.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .session import EditorSession
from .sidebars import RESOURCE_MIME


_EXPR_TOGGLE_TIP = "把常量改为表达式"

# (owner_kind, field) takes precedence, then the field-name fallback.  The
# spinboxes enforce these bounds directly so out-of-range input is visible.
_FIELD_RANGES = {
    ("Wait", "frames"): (0, 100_000),
    ("At", "frame"): (0, 100_000),
    ("Repeat", "count"): (0, 100_000),
    ("MoveTo", "duration"): (0, 100_000),
    ("MoveLinear", "duration"): (0, 100_000),
    ("Spell", "time_limit"): (1, 3600),
    ("NonSpell", "time_limit"): (1, 3600),
    ("Spell", "hp"): (1, 1_000_000_000),
    ("NonSpell", "hp"): (1, 1_000_000_000),
    ("Enemy", "hp"): (1, 1_000_000_000),
    ("Enemy", "score"): (0, 1_000_000_000),
    ("Spell", "bonus"): (0, 1_000_000_000),
    ("NonSpell", "bonus"): (0, 1_000_000_000),
    ("Enemy", "hitbox_radius"): (0.0, 0.5),
    ("CreateLaser", "l1"): (0.0, 2.0),
    ("CreateLaser", "l2"): (0.0, 2.0),
    ("CreateLaser", "l3"): (0.0, 2.0),
    ("CreateLaser", "width"): (0.001, 0.2),
    ("CreateLaser", "on_time"): (0, 100_000),
    ("CreateBentLaser", "length"): (1, 100_000),
    ("CreateBentLaser", "width"): (0.001, 0.2),
    ("CreateBentLaser", "on_time"): (0, 100_000),
    ("RemoveLaser", "off_time"): (0, 100_000),
    ("FirePolar", "orbit_radius"): (0.0, 2.0),
    ("FireOrbit", "orbit_radius"): (0.0, 2.0),
}
_NAME_RANGES = {
    "x": (-2.0, 2.0), "y": (-2.0, 2.0),
    "dx": (-2.0, 2.0), "dy": (-2.0, 2.0),
    "theta": (-360.0, 360.0), "angle": (-360.0, 360.0),
    "radial_speed": (-2.0, 2.0), "angular_velocity": (-2.0, 2.0),
    "angle_offset": (-360.0, 360.0),
}


_POINT_NODE_KINDS = frozenset({
    "Fire", "FireCircle", "FireArc", "FireAtPlayer", "SpawnEnemy",
    "MoveTo", "SetPosition", "CreateLaser", "CreateBentLaser",
})


def _coordinate_spec_kind(node) -> str | None:
    """Which coordinate preview mode applies to this node, if any."""

    if node is None:
        return None
    if node.kind in {"MoveLinear"} and ("dx" in node.arguments or "dy" in node.arguments):
        return "delta"
    if node.kind in _POINT_NODE_KINDS and ("x" in node.arguments or "y" in node.arguments):
        x, y = node.arguments.get("x"), node.arguments.get("y")
        if isinstance(x, Expr) or isinstance(y, Expr):
            return "hint"
        return "point"
    if node.kind in {"Fire", "FireCircle", "FireArc", "FireAtPlayer"}:
        # x/y omitted entirely means the runtime uses the actor position.
        return "hint"
    return None


_UNSET = object()


def _values_equal(candidate: Any, original: Any) -> bool:
    """Type-aware equality so 60 never suppresses a float 60.0 edit."""

    if type(candidate) is not type(original):
        return False
    try:
        return bool(candidate == original)
    except Exception:
        return False


def _range_tooltip(owner_kind, name, annotation, value) -> str:
    kind = _field_type(annotation, value) if annotation is not None else None
    type_text = {int: "int", float: "float", str: "字符串", bool: "bool"}.get(kind)
    if type_text is None:
        type_text = "常量 | 表达式"
    lines = [str(name), f"类型: {type_text}"]
    if value is not None and not isinstance(value, Expr):
        lines.append(f"默认: {value!r}"[:80])
    bounds = _field_range(owner_kind or "", name or "")
    if bounds is not None:
        lines.append(f"范围: {bounds[0]} ~ {bounds[1]}")
    return chr(10).join(lines)


def _field_range(owner_kind: str, name: str) -> tuple[float, float] | None:
    if (owner_kind, name) in _FIELD_RANGES:
        return _FIELD_RANGES[(owner_kind, name)]
    if name in _NAME_RANGES:
        return _NAME_RANGES[name]
    return None


_Y_ASPECT = 384.0 / 448.0  # renderer.py:211 宽高比校正（x 保持 ±1，y × 384/448）


def marker_point(
    x: float, y: float, width: float, height: float
) -> tuple[float, float]:
    """Map authoring coordinates to pixels on a full play-field rectangle."""

    return (x + 1) / 2 * width, (1 - y * _Y_ASPECT) / 2 * height


class ResourceLineEdit(QLineEdit):
    resource_dropped = Signal(str)

    def __init__(self, accepts_resource, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accepts_resource = accepts_resource
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        uri = _resource_uri(event.mimeData())
        if uri and self._accepts_resource(uri):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        uri = _resource_uri(event.mimeData())
        if uri and self.drop_resource(uri):
            event.acceptProposedAction()
        else:
            event.ignore()

    def drop_resource(self, uri: str) -> bool:
        if not self._accepts_resource(uri):
            return False
        self.resource_dropped.emit(uri)
        return True


class LiteralTextEdit(QPlainTextEdit):
    """Light structured editor for list/dict literal values."""

    commit_requested = Signal()

    def focusOutEvent(self, event) -> None:
        if self.isVisible():
            self.commit_requested.emit()
        super().focusOutEvent(event)


class CoordinatePreview(QWidget):
    """Miniature of the visible play field for the node's edited point.

    Authoring coordinates are x ∈ [-1, 1] (right positive) and y upward with
    (0, 0) at the field centre; the shaders apply the 384/448 aspect
    correction, which this preview reproduces faithfully.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("coordinate_preview")
        self.setMinimumHeight(120)
        self._reader = lambda: None  # returns a paint spec each repaint

    def configure(self, reader) -> None:
        self._reader = reader
        self.update()

    def paintEvent(self, _event) -> None:
        from src.qt_compat.QtGui import QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#10141a"))
        spec = self._reader()
        border = QRectF(8.0, 6.0, self.width() - 16, self.height() - 12)
        painter.setPen(QPen(QColor("#3a414e"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(border, 4, 4)
        center = QPointF(border.center())
        painter.setPen(QPen(QColor("#262c34"), 1))
        painter.drawLine(
            QPointF(border.left(), center.y()),
            QPointF(border.right(), center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), border.top()),
            QPointF(center.x(), border.bottom()),
        )
        if spec is None or spec[0] == "none":
            painter.setPen(QColor("#6e7681"))
            painter.drawText(border, Qt.AlignmentFlag.AlignCenter, "无坐标参数")
            painter.end()
            return
        if spec[0] == "hint":
            painter.setPen(QColor("#f0883e"))
            painter.drawText(border, Qt.AlignmentFlag.AlignCenter, spec[1])
            painter.end()
            return
        if spec[0] == "delta":
            _kind, dx, dy = spec
            width = border.width() / 2
            height = border.height() / 2
            target = QPointF(
                center.x() + dx / 2 * width,
                center.y() - dy * _Y_ASPECT / 2 * height,
            )
            painter.setPen(QPen(QColor("#3fb950"), 2))
            painter.drawLine(center, target)
            painter.setBrush(QColor("#3fb950"))
            painter.drawEllipse(target, 4, 4)
            painter.setPen(QColor("#c9d1d9"))
            painter.drawText(
                QPointF(target.x() + 6, target.y() - 4), f"Δ({dx:g}, {dy:g})"
            )
            painter.end()
            return
        _kind, x, y = spec
        off_screen = abs(x) > 1.5 or abs(y) > 1.5
        u, v = marker_point(x, y, border.width(), border.height())
        marker = QPointF(border.left() + u, border.top() + v)
        inside = border.adjusted(6, 6, -6, -6).contains(marker)
        color = QColor("#f85149") if off_screen or not inside else QColor("#58a6e7")
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        radius = 6.0
        painter.drawEllipse(marker, radius, radius)
        painter.drawLine(
            QPointF(marker.x() - radius - 3, marker.y()),
            QPointF(marker.x() + radius + 3, marker.y()),
        )
        painter.drawLine(
            QPointF(marker.x(), marker.y() - radius - 3),
            QPointF(marker.x(), marker.y() + radius + 3),
        )
        painter.setPen(QColor(color))
        text = f"({x:g}, {y:g})" + ("（屏外）" if off_screen else "")
        painter.drawText(
            QPointF(min(marker.x() + 8, border.right() - 70), max(marker.y() - 6, border.top() + 12)),
            text,
        )
        painter.end()


class ParameterTable(QWidget):
    """Small explicit table for Task/Function signature parameters."""

    commit_requested = Signal(object)
    error = Signal(str)

    def __init__(self, values: tuple[Parameter, ...], editable: bool, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3, self)
        self.table.setObjectName("parameter_table")
        self.table.setHorizontalHeaderLabels(["名称", "类型", "默认值（留空=必填）"])
        for parameter in values:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(parameter.name))
            self.table.setItem(row, 1, QTableWidgetItem(parameter.annotation))
            default = "" if not parameter.has_default else repr(parameter.default)
            self.table.setItem(row, 2, QTableWidgetItem(default))
        self.table.setEnabled(editable)
        self.table.setMinimumHeight(110)
        layout.addWidget(self.table)
        controls = QHBoxLayout()
        add = QToolButton(self)
        add.setText("＋")
        remove = QToolButton(self)
        remove.setText("－")
        apply = QToolButton(self)
        apply.setText("应用")
        for button in (add, remove, apply):
            button.setEnabled(editable)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        add.clicked.connect(self._add_row)
        remove.clicked.connect(self._remove_row)
        apply.clicked.connect(self._apply)

    def _add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(f"arg{row + 1}"))
        self.table.setItem(row, 1, QTableWidgetItem("Any"))
        self.table.setItem(row, 2, QTableWidgetItem(""))
        self.table.setCurrentCell(row, 0)
        self.table.editItem(self.table.item(row, 0))

    def _remove_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def parameters(self) -> tuple[Parameter, ...]:
        values: list[Parameter] = []
        for row in range(self.table.rowCount()):
            name = (self.table.item(row, 0).text() if self.table.item(row, 0) else "").strip()
            annotation = (
                self.table.item(row, 1).text() if self.table.item(row, 1) else "Any"
            ).strip() or "Any"
            default = (
                self.table.item(row, 2).text() if self.table.item(row, 2) else ""
            ).strip()
            values.append(
                Parameter(name, annotation)
                if not default
                else Parameter(name, annotation, _parse_literal(default))
            )
        return tuple(values)

    def _apply(self) -> None:
        try:
            values = self.parameters()
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.error.emit("")
        self.commit_requested.emit(values)


class InspectorPanel(QWidget):
    """Use constructor annotations as the only field schema."""

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inspector_panel")
        self.session = session
        self.form = QFormLayout(self)
        self.form.setContentsMargins(8, 8, 8, 8)
        self._suggested_widget: QWidget | None = None
        self._coordinate_preview: CoordinatePreview | None = None
        self._commit_depth = 0
        self._rebuild_scheduled = False
        self.session.selection_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the field rows for the current selection.

        A commit that succeeds rebuilds this panel; deferring the rebuild until
        the widget's own signal dispatch has unwound is what keeps typing from
        crashing Qt (deleting the sender mid-signal is use-after-free).
        """

        if self._commit_depth > 0:
            if not self._rebuild_scheduled:
                self._rebuild_scheduled = True
                QTimer.singleShot(0, self._deferred_refresh)
            return
        self._do_refresh()

    def _deferred_refresh(self) -> None:
        self._rebuild_scheduled = False
        if self._commit_depth == 0:
            self._do_refresh()

    def _do_refresh(self) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self._suggested_widget = None
        node = self.session.current_node
        unit = self.session.current_unit
        if node is not None:
            constructor = dsl.NODE_CONSTRUCTORS.get(node.kind)
            annotations = get_type_hints(constructor) if constructor is not None else {}
            defaults = _constructor_defaults(constructor)
            self.form.addRow("节点类型", QLabel(node.kind))
            self.form.addRow("UID", QLabel(node.uid))
            self._add_coordinate_preview(node)
            suggested = self._suggested_field_name(node, constructor)
            for name, value in _node_fields(node, constructor):
                self._add_field(
                    name,
                    value,
                    annotations.get(name, Any),
                    node.kind,
                    defaults.get(name, inspect.Parameter.empty),
                    mark_suggested=name == suggested,
                    commit=lambda new_value, uid=node.uid, key=name: (
                        self.session.set_node_argument(uid, key, new_value)
                    ),
                )
            return
        if unit is not None:
            constructor = dsl.UNIT_CONSTRUCTORS[unit.kind]
            annotations = get_type_hints(constructor)
            defaults = _constructor_defaults(constructor)
            self.form.addRow("逻辑单元", QLabel(unit.kind))
            self._add_field(
                "名称",
                unit.name,
                annotations.get("name", str),
                unit.kind,
                defaults.get("name", inspect.Parameter.empty),
                mark_suggested=False,
                field_name="unit_name",
                commit=lambda value, unit_id=unit.id: self.session.set_unit_field(
                    unit_id, "name", value
                ),
            )
            if "parameters" in inspect.signature(constructor).parameters:
                self._add_parameter_field(unit)
            for name, value in _unit_fields(unit.metadata, constructor):
                self._add_field(
                    name,
                    value,
                    annotations.get(name, Any),
                    unit.kind,
                    defaults.get(name, inspect.Parameter.empty),
                    mark_suggested=False,
                    commit=lambda new_value, unit_id=unit.id, key=name: (
                        self.session.set_unit_field(unit_id, key, new_value)
                    ),
                )
            return
        self.form.addRow(QLabel("当前文件不可视化编辑"))

    def focus_suggested_field(self) -> None:
        """Focus the field the author most likely wants to change next."""

        widget = self._suggested_widget or self._first_editable_widget()
        if widget is None:
            return
        widget.setFocus(Qt.FocusReason.OtherFocusReason)
        scroll = self.window().findChild(QScrollArea, "inspector_scroll")
        container = self._editor_container(widget)
        if container is not None and scroll is not None:
            scroll.ensureWidgetVisible(container, 8, 8)

    def _first_editable_widget(self) -> QWidget | None:
        for editor in self.findChildren(QLineEdit):
            if editor.isVisible() and not editor.isReadOnly():
                return editor
        for editor in self.findChildren(QComboBox):
            if editor.isVisible():
                return editor
        return None

    def _editor_container(self, widget: QWidget) -> QWidget | None:
        current: QWidget | None = widget
        while current is not None and current.parentWidget() is not self:
            current = current.parentWidget()
        return current

    def _suggested_field_name(self, node, constructor) -> str | None:
        """The first field still holding its constructor default value."""

        if constructor is None:
            return None
        signature = inspect.signature(constructor)
        for name, value in _node_fields(node, constructor):
            parameter = signature.parameters.get(name)
            if parameter is None or parameter.default is inspect.Parameter.empty:
                continue
            try:
                if value == parameter.default and type(value) is type(parameter.default):
                    return name
            except Exception:
                continue
        return None

    # -- field construction ---------------------------------------------------

    def _add_field(
        self,
        name: str,
        value: Any,
        annotation: Any,
        owner_kind: str,
        default: Any,
        *,
        mark_suggested: bool,
        commit,
        field_name: str | None = None,
    ) -> None:
        del default  # defaults are resolved by _suggested_field_name
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        editor = self._editor(value, annotation, owner_kind, name, commit)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(editor, 1)
        if self._supports_expr(value, annotation, field_name or name):
            row.addWidget(
                self._expr_toggle(editor, value, annotation, name, commit)
            )
        if isinstance(editor, ResourceLineEdit):
            row.addWidget(self._browse_button(editor, name))
        layout.addLayout(row)
        error_label = QLabel("", container)
        error_label.setStyleSheet("color: #f85149;")
        error_label.setWordWrap(True)
        error_label.setObjectName(f"error_{name}")
        layout.addWidget(error_label)
        editor.setObjectName(f"argument_{field_name or name}")
        editor.setProperty("pystg_annotation", str(annotation))
        editor.setProperty("pystg_field", field_name or name)
        label = QLabel(name + (" ▸建议调整" if mark_suggested else ""), container)
        if mark_suggested:
            label.setStyleSheet("color: #f0883e;")
            self._suggested_widget = self._focus_proxy(editor)
        self.form.addRow(label, container)

    def _add_coordinate_preview(self, node) -> None:
        """Show a mini play field when the node edits a position-like value."""

        spec_kind = _coordinate_spec_kind(node)
        if spec_kind is None:
            self._coordinate_preview = None
            return
        preview = CoordinatePreview(self)
        preview.setObjectName("coordinate_preview_widget")
        preview.configure(lambda: self._coordinate_spec(node))
        self._coordinate_preview = preview
        labels = {"point": "位置", "delta": "增量", "actor": "位置"}
        self.form.addRow(QLabel(labels.get(spec_kind, "位置"), self), preview)

    def _coordinate_spec(self, node):
        """Current paint spec, reading live editor values when present."""

        kind = _coordinate_spec_kind(node)
        if kind is None:
            return None
        if kind == "hint":
            if node.kind in {
                "Fire", "FireCircle", "FireArc", "FireAtPlayer",
            } and "x" not in node.arguments:
                return ("hint", "未填 x/y = 使用发射者位置")
            return ("hint", "坐标含表达式，无法预览")
        fields = ("dx", "dy") if kind == "delta" else ("x", "y")
        values = []
        for field in fields:
            original = node.arguments.get(field)
            editor = self.findChild(QWidget, f"argument_{field}")
            value = (
                self._current_value(editor, original)
                if editor is not None
                else original
            )
            if isinstance(value, Expr) or not isinstance(value, (int, float)) or isinstance(value, bool):
                return ("hint", "坐标含表达式，无法预览")
            values.append(float(value))
        return (kind, values[0], values[1])

    def _add_parameter_field(self, unit) -> None:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        table = ParameterTable(tuple(unit.parameters), self.session.can_edit, container)
        table.setObjectName("argument_parameters")
        table.commit_requested.connect(
            lambda values, unit_id=unit.id: self._commit_after_event(
                lambda parsed: self.session.set_unit_field(unit_id, "parameters", parsed),
                values,
                "parameters",
            )
        )
        table.error.connect(lambda message: self._show_field_error("parameters", message))
        layout.addWidget(table)
        error = QLabel("", container)
        error.setObjectName("error_parameters")
        error.setStyleSheet("color: #f85149;")
        error.setWordWrap(True)
        layout.addWidget(error)
        self.form.addRow(QLabel("参数表", container), container)

    def _focus_proxy(self, editor: QWidget) -> QWidget:
        inner = (
            editor.findChild(QLineEdit)
            or editor.findChild(QPlainTextEdit)
            or editor.findChild(QComboBox)
        )
        return inner or editor

    def _editor(
        self,
        value: Any,
        annotation: Any,
        owner_kind: str,
        name: str,
        commit,
    ) -> QWidget:
        if isinstance(value, Ref):
            return self._ref_editor(value, owner_kind, name, commit)
        if isinstance(value, Expr):
            return self._expr_editor(value, name, commit)
        literal_options = _literal_options(annotation)
        if literal_options is not None:
            return self._literal_combo(value, literal_options, name, commit)
        field_type = _field_type(annotation, value)
        if field_type is bool:
            widget = QCheckBox(self)
            widget.setChecked(bool(value))
            widget.setEnabled(self.session.can_edit)
            widget.setToolTip(_range_tooltip(owner_kind, name, annotation, value))
            if self.session.can_edit:
                widget.toggled.connect(
                    lambda checked, original=bool(value): self._commit_after_event(
                        commit, checked, name, original
                    )
                )
            return widget
        if field_type is int:
            low, high = _field_range(owner_kind, name) or (-1_000_000, 1_000_000)
            widget = QSpinBox(self)
            widget.setRange(int(low), int(high))
            widget.setValue(int(value))
            widget.setReadOnly(not self.session.can_edit)
            widget.setToolTip(_range_tooltip(owner_kind, name, annotation, value))
            if self.session.can_edit:
                widget.editingFinished.connect(
                    lambda editor=widget, original=value: self._commit_after_event(
                        commit, editor.value(), name, original
                    )
                )
                widget.valueChanged.connect(self._refresh_coordinate_preview)
            return widget
        if field_type is float:
            low, high = _field_range(owner_kind, name) or (-1_000.0, 1_000.0)
            widget = QDoubleSpinBox(self)
            widget.setDecimals(6)
            widget.setRange(float(low), float(high))
            widget.setValue(float(value))
            widget.setReadOnly(not self.session.can_edit)
            widget.setToolTip(_range_tooltip(owner_kind, name, annotation, value))
            if self.session.can_edit:
                widget.editingFinished.connect(
                    lambda editor=widget, original=value: self._commit_after_event(
                        commit, editor.value(), name, original
                    )
                )
                widget.valueChanged.connect(self._refresh_coordinate_preview)
            return widget
        if isinstance(value, (list, tuple, dict)):
            return self._literal_text_editor(value, name, commit)
        is_resource = _is_resource_field(owner_kind, name)
        accepts = lambda uri: resource_field_accepts(owner_kind, name, uri)
        widget = ResourceLineEdit(accepts, self) if is_resource else QLineEdit(self)
        widget.setText(value if isinstance(value, str) else repr(value))
        widget.setReadOnly(not self.session.can_edit)
        if self.session.can_edit:
            widget.editingFinished.connect(
                lambda editor=widget, original=value: self._commit_after_event(
                    commit, _parse_text(editor.text(), original), name, original
                )
            )
            widget.textChanged.connect(self._refresh_coordinate_preview)
            if isinstance(widget, ResourceLineEdit):
                widget.resource_dropped.connect(
                    lambda uri, original=value: self._commit_after_event(
                        commit, uri, name, original
                    )
                )
        return widget

    def _literal_combo(self, value, options: tuple, name: str, commit) -> QWidget:
        widget = QComboBox(self)
        for option in options:
            widget.addItem(str(option), option)
        index = widget.findData(value)
        if index >= 0:
            widget.setCurrentIndex(index)
        widget.setEnabled(self.session.can_edit)
        widget.setToolTip(_range_tooltip(owner_kind=None, name=name, annotation=None, value=value) or name)
        if self.session.can_edit:
            widget.currentIndexChanged.connect(
                lambda _index, original=value: self._commit_after_event(
                    commit, widget.currentData(), name, original
                )
            )
        return widget

    def _ref_editor(self, value: Ref, owner_kind: str, name: str, commit) -> QWidget:
        """A searchable, explicit reference selector over existing logical units."""

        widget = QComboBox(self)
        expected = reference_kinds_for_field(owner_kind, name)
        candidates = [
            unit.id
            for unit in sorted(
                self.session.program.logical_units(), key=lambda item: (item.kind, item.id)
            )
            if not expected or unit.kind in expected
        ]
        if value.id not in candidates:
            candidates.insert(0, value.id)
        widget.addItems(candidates)
        widget.setCurrentText(value.id)
        widget.setEditable(True)
        widget.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        widget.setEnabled(self.session.can_edit)
        widget.setToolTip(f"{name}\n引用 {expected or '逻辑单元'}\n当前: {value.id}")
        if self.session.can_edit:
            # Dropdown selections commit once; typed identifiers commit on
            # Enter/focus-out so partial ids never hit the model.
            widget.currentIndexChanged.connect(
                lambda index, original=value: (
                    self._commit_after_event(
                        commit, Ref(widget.currentText()), name, original
                    )
                    if index >= 0
                    else None
                )
            )
            line_edit = widget.lineEdit()
            line_edit.editingFinished.connect(
                lambda original=value: self._commit_after_event(
                    commit, Ref(line_edit.text()), name, original
                )
            )
        return widget

    def _expr_editor(self, value: Expr, name: str, commit) -> QWidget:
        widget = QLineEdit(self)
        widget.setText(value.source)
        widget.setPlaceholderText("表达式，如 player_x")
        widget.setReadOnly(not self.session.can_edit)
        if self.session.can_edit:
            widget.editingFinished.connect(
                lambda editor=widget, original=value: self._commit_after_event(
                    commit, Expr(editor.text()), name, original
                )
            )
            widget.textChanged.connect(self._refresh_coordinate_preview)
        return widget

    def _expr_toggle(
        self,
        editor: QWidget,
        value: Any,
        annotation: Any,
        name: str,
        commit,
    ) -> QWidget:
        button = QToolButton(self)
        button.setObjectName(f"expression_toggle_{name}")
        button.setText("常" if isinstance(value, Expr) else "ƒ")
        button.setToolTip(
            "把表达式改回常量" if isinstance(value, Expr) else _EXPR_TOGGLE_TIP
        )
        button.setEnabled(self.session.can_edit)

        def switch() -> None:
            if isinstance(value, Expr):
                try:
                    constant = _parse_expr_constant(editor.text(), annotation)
                except ValueError as exc:
                    self._show_field_error(name, str(exc))
                    return
                self._commit_after_event(commit, constant, name, value)
                return
            current = self._current_value(editor, value)
            self._commit_after_event(commit, Expr(_expr_source(current)), name, value)

        button.clicked.connect(switch)
        return button

    def _supports_expr(self, value: Any, annotation: Any, field_name: str) -> bool:
        if field_name == "unit_name":
            return False
        if isinstance(value, (list, tuple, dict, Ref, bool)):
            return False
        if isinstance(value, Expr):
            return True
        return _field_type(annotation, value) in {int, float, str}

    def _current_value(self, editor: QWidget, original: Any) -> Any:
        if isinstance(editor, QSpinBox):
            return editor.value()
        if isinstance(editor, QDoubleSpinBox):
            return editor.value()
        if isinstance(editor, (QLineEdit, ResourceLineEdit)):
            return _parse_text(editor.text(), original)
        if isinstance(editor, QComboBox):
            data = editor.currentData()
            return data if data is not None else editor.currentText()
        return original

    def _browse_button(self, editor: ResourceLineEdit, name: str) -> QWidget:
        button = QToolButton(self)
        button.setText("…")
        button.setToolTip("选择工程内文件")

        def browse() -> None:
            context = self.session.project_context
            if context is None:
                return
            path, _filter = QFileDialog.getOpenFileName(self, "选择资源文件", str(context.root))
            if not path:
                return
            try:
                relative = Path(path).resolve().relative_to(context.root).as_posix()
            except ValueError:
                self._show_field_error(name, "文件必须在工程目录内")
                return
            uri = f"res://{relative}"
            editor.setText(uri)
            editor.resource_dropped.emit(uri)

        button.clicked.connect(browse)
        return button

    def _literal_text_editor(self, value: Any, name: str, commit) -> QWidget:
        widget = LiteralTextEdit(self)
        widget.setPlainText(repr(value))
        widget.setFixedHeight(64)
        widget.setReadOnly(not self.session.can_edit)
        widget.setPlaceholderText("Python 字面量，例如 ['a', 1] 或 {'x': 2}")
        if self.session.can_edit:
            widget.commit_requested.connect(
                lambda editor=widget, original=value: self._commit_literal_text(
                    editor, commit, name, original
                )
            )
            widget.textChanged.connect(self._refresh_coordinate_preview)
        return widget

    # -- commit with field-level errors ---------------------------------------

    def _commit_after_event(
        self, callback, value: Any, name: str, original: Any = _UNSET
    ) -> None:
        """Commit after a native editor finishes dispatching its input event.

        A successful commit replaces the immutable model and synchronously
        rebuilds this panel.  Destroying an editor from inside its own
        signal handler is use-after-free, so capture the value now and mutate
        only after control returns to the event loop.
        """

        QTimer.singleShot(
            0, lambda: self._commit(callback, value, name, original)
        )

    def _commit(
        self, callback, value: Any, name: str, original: Any = _UNSET
    ) -> None:
        if original is not _UNSET and _values_equal(value, original):
            self._show_field_error(name, "")
            return
        self._commit_depth += 1
        try:
            callback(value)
        except Exception as exc:
            self._commit_depth -= 1
            self._show_field_error(name, str(exc))
            return
        self._commit_depth -= 1
        self._show_field_error(name, "")

    def _refresh_coordinate_preview(self, *_args) -> None:
        if self._coordinate_preview is not None:
            self._coordinate_preview.update()

    def _commit_literal_text(
        self, editor: QPlainTextEdit, callback, name: str, original: Any = _UNSET
    ) -> None:
        try:
            value = _parse_literal(editor.toPlainText())
        except ValueError as exc:
            self._show_field_error(name, str(exc))
            return
        self._commit(callback, value, name, original)

    def _show_field_error(self, name: str, message: str) -> None:
        error_label = self.findChild(QLabel, f"error_{name}")
        if error_label is None:
            if message:
                window = self.window()
                if hasattr(window, "statusBar"):
                    window.statusBar().showMessage(f"参数未修改：{message}", 5000)
            return
        error_label.setText(message)


def resource_field_accepts(owner_kind: str, name: str, uri: str) -> bool:
    path = PurePosixPath(uri.removeprefix("res://").split("#", 1)[0])
    suffix = path.suffix.lower()
    return suffix in _RESOURCE_FIELD_SUFFIXES.get((owner_kind, name), frozenset())


_AUDIO_SUFFIXES = frozenset({".flac", ".mp3", ".ogg", ".wav"})
_IMAGE_SUFFIXES = frozenset({".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"})
_RESOURCE_FIELD_SUFFIXES = {
    ("Stage", "bgm"): _AUDIO_SUFFIXES,
    ("Stage", "boss_bgm"): _AUDIO_SUFFIXES,
    ("PlayBGM", "name"): _AUDIO_SUFFIXES,
    ("PlaySE", "name"): _AUDIO_SUFFIXES,
    ("Stage", "background"): frozenset({".json"}),
    ("SetBackground", "name"): frozenset({".json"}),
    ("Enemy", "sprite"): _IMAGE_SUFFIXES | {".json"},
    ("Boss", "texture"): _IMAGE_SUFFIXES | {".json"},
    ("PlayDialogue", "dialogue_list"): frozenset({".json"}),
}


def _is_resource_field(owner_kind: str, name: str) -> bool:
    return (owner_kind, name) in _RESOURCE_FIELD_SUFFIXES


def _constructor_defaults(constructor) -> dict[str, Any]:
    if constructor is None:
        return {}
    return {
        name: parameter.default
        for name, parameter in inspect.signature(constructor).parameters.items()
    }


def _literal_options(annotation: Any) -> tuple | None:
    if get_origin(annotation) is Literal:
        return tuple(get_args(annotation))
    return None


def _parse_text(text: str, original: Any) -> Any:
    if isinstance(original, str):
        return text
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return text


def _parse_literal(text: str) -> Any:
    try:
        return parse_author_value(text)
    except ProgramError as exc:
        raise ValueError(
            f"不是合法的作者值（字面量/Ref/Expr）：{exc.message}"
        ) from exc


def _expr_source(value: Any) -> str:
    if isinstance(value, str):
        return value if value else "0"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return repr(value)
    return repr(value)


def _parse_expr_constant(source: str, annotation: Any) -> Any:
    """Convert an expression editor back to a literal without executing it."""

    try:
        return ast.literal_eval(source)
    except (SyntaxError, ValueError):
        if _annotation_contains(annotation, str):
            return source
        raise ValueError("只有字面量表达式才能切回常量") from None


def _annotation_contains(annotation: Any, expected: type) -> bool:
    if annotation is expected:
        return True
    origin = get_origin(annotation)
    if origin in {types.UnionType, Union}:
        return any(_annotation_contains(item, expected) for item in get_args(annotation))
    return False


def _resource_uri(mime_data) -> str | None:
    if not mime_data.hasFormat(RESOURCE_MIME):
        return None
    return bytes(mime_data.data(RESOURCE_MIME)).decode("utf-8")


def _node_fields(node, constructor) -> tuple[tuple[str, Any], ...]:
    if constructor is None:
        return tuple(node.arguments.items())
    signature = inspect.signature(constructor)
    values: list[tuple[str, Any]] = []
    for name, parameter in signature.parameters.items():
        if name == "uid" or name in {"body", "else_body", "branches"}:
            continue
        if name in node.arguments:
            values.append((name, node.arguments[name]))
        elif parameter.default is not inspect.Parameter.empty:
            values.append((name, parameter.default))
    for name, value in node.arguments.items():
        if name not in signature.parameters:
            values.append((name, value))
    return tuple(values)


def _unit_fields(
    metadata: dict[str, Any], constructor
) -> tuple[tuple[str, Any], ...]:
    signature = inspect.signature(constructor)
    values: list[tuple[str, Any]] = []
    for name, parameter in signature.parameters.items():
        if name in {"id", "name", "body", "parameters"}:
            continue
        if name in metadata:
            values.append((name, metadata[name]))
        elif parameter.default is not inspect.Parameter.empty:
            values.append((name, parameter.default))
    for name, value in metadata.items():
        if name not in signature.parameters:
            values.append((name, value))
    return tuple(values)


def _field_type(annotation: Any, value: Any) -> type | None:
    """Choose a scalar Qt control from the DSL annotation, then the literal value."""

    if isinstance(value, (Expr, Ref)):
        return None
    if annotation in {bool, int, float, str}:
        return annotation
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in {types.UnionType, Union}:
        scalar_options = [item for item in arguments if item in {bool, int, float, str}]
        for scalar in scalar_options:
            if scalar is bool and type(value) is bool:
                return scalar
            if scalar is int and type(value) is int:
                return scalar
            if scalar is float and not isinstance(value, bool) and isinstance(value, (int, float)):
                return scalar
            if scalar is str and isinstance(value, str):
                return scalar
    if origin is Literal:
        literal_types = {type(item) for item in arguments}
        if len(literal_types) == 1:
            scalar = next(iter(literal_types))
            if scalar in {bool, int, float, str}:
                return scalar
    if type(value) in {bool, int, float, str}:
        return type(value)
    return None


__all__ = [
    "InspectorPanel",
    "ParameterTable",
    "ResourceLineEdit",
    "resource_field_accepts",
]

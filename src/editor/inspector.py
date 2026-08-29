"""Inspector fields derived from public DSL constructor signatures."""

from __future__ import annotations

import ast
import inspect
import types
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from src.authoring import dsl
from src.authoring.program import Expr, Ref
from src.qt_compat.QtCore import Qt, Signal
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .session import EditorSession
from .sidebars import RESOURCE_MIME


_REF_FIELD_KINDS = {
    ("RunWave", "wave_class"): ("Wave",),
    ("RunBoss", "boss_def"): ("Boss",),
    ("SpawnEnemy", "enemy_class"): ("Enemy",),
    ("Call", "function"): ("Function", "Task"),
    ("SpawnTask", "task"): ("Task",),
}
_EXPR_TOGGLE_TIP = "把常量改为表达式"


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


class InspectorPanel(QWidget):
    """Use constructor annotations as the only field schema."""

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inspector_panel")
        self.session = session
        self.form = QFormLayout(self)
        self.form.setContentsMargins(8, 8, 8, 8)
        self._suggested_widget: QWidget | None = None
        self.session.selection_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
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
        if self._supports_expr(value, annotation):
            row.addWidget(self._expr_toggle(editor, value, name))
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
            return self._ref_editor(value, name, commit)
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
            if self.session.can_edit:
                widget.toggled.connect(
                    lambda checked: self._commit(commit, checked, name)
                )
            return widget
        if field_type is int:
            widget = QSpinBox(self)
            widget.setRange(-1_000_000_000, 1_000_000_000)
            widget.setValue(int(value))
            widget.setReadOnly(not self.session.can_edit)
            if self.session.can_edit:
                widget.editingFinished.connect(
                    lambda editor=widget: self._commit(commit, editor.value(), name)
                )
            return widget
        if field_type is float:
            widget = QDoubleSpinBox(self)
            widget.setDecimals(6)
            widget.setRange(-1_000_000_000.0, 1_000_000_000.0)
            widget.setValue(float(value))
            widget.setReadOnly(not self.session.can_edit)
            if self.session.can_edit:
                widget.editingFinished.connect(
                    lambda editor=widget: self._commit(commit, editor.value(), name)
                )
            return widget
        if isinstance(value, (list, tuple, dict)):
            return self._literal_text_editor(value, name, commit)
        accepts = lambda uri: resource_field_accepts(owner_kind, name, uri)
        widget = ResourceLineEdit(accepts, self)
        widget.setText(value if isinstance(value, str) else repr(value))
        widget.setReadOnly(not self.session.can_edit)
        if self.session.can_edit:
            widget.editingFinished.connect(
                lambda editor=widget, original=value: self._commit(
                    commit, _parse_text(editor.text(), original), name
                )
            )
            widget.resource_dropped.connect(lambda uri: self._commit(commit, uri, name))
        return widget

    def _literal_combo(self, value, options: tuple, name: str, commit) -> QWidget:
        widget = QComboBox(self)
        for option in options:
            widget.addItem(str(option), option)
        index = widget.findData(value)
        if index >= 0:
            widget.setCurrentIndex(index)
        widget.setEnabled(self.session.can_edit)
        if self.session.can_edit:
            widget.currentIndexChanged.connect(
                lambda _index: self._commit(commit, widget.currentData(), name)
            )
        return widget

    def _ref_editor(self, value: Ref, name: str, commit) -> QWidget:
        """A searchable, explicit reference selector over existing logical units."""

        widget = QComboBox(self)
        expected = _REF_FIELD_KINDS.get(name, ())
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
        if self.session.can_edit:
            widget.currentTextChanged.connect(
                lambda text: self._commit(commit, Ref(text), name)
            )
        return widget

    def _expr_editor(self, value: Expr, name: str, commit) -> QWidget:
        widget = QLineEdit(self)
        widget.setText(value.source)
        widget.setPlaceholderText("表达式，如 player_x")
        widget.setReadOnly(not self.session.can_edit)
        if self.session.can_edit:
            widget.editingFinished.connect(
                lambda editor=widget: self._commit(commit, Expr(editor.text()), name)
            )
        return widget

    def _expr_toggle(self, editor: QWidget, value: Any, name: str) -> QWidget:
        button = QToolButton(self)
        button.setText("ƒ")
        button.setToolTip(_EXPR_TOGGLE_TIP)
        button.setEnabled(self.session.can_edit)

        def switch() -> None:
            current = self._current_value(editor, value)
            if isinstance(current, Expr):
                return
            self._commit(commit, Expr(_expr_source(current)), name)

        button.clicked.connect(switch)
        return button

    def _supports_expr(self, value: Any, annotation: Any) -> bool:
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
                lambda editor=widget: self._commit(
                    commit, _parse_literal(editor.toPlainText()), name
                )
            )
        return widget

    # -- commit with field-level errors ---------------------------------------

    def _commit(self, callback, value: Any, name: str) -> None:
        try:
            callback(value)
        except Exception as exc:
            self._show_field_error(name, str(exc))
            return
        self._show_field_error(name, "")

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
    audio = {".flac", ".mp3", ".ogg", ".wav"}
    images = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
    key = (owner_kind, name)
    if key in {("Stage", "bgm"), ("Stage", "boss_bgm"), ("PlayBGM", "name"), ("PlaySE", "name")}:
        return suffix in audio
    if key in {("Stage", "background"), ("SetBackground", "name")}:
        return suffix == ".json"
    if key in {("Enemy", "sprite"), ("Boss", "texture")}:
        return suffix in images | {".json"}
    if key == ("PlayDialogue", "dialogue_list"):
        return suffix == ".json"
    return False


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
        return ast.literal_eval(text)
    except (SyntaxError, ValueError) as exc:
        raise ValueError("不是合法的 Python 字面量") from exc


def _expr_source(value: Any) -> str:
    if isinstance(value, str):
        return value if value else "0"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return repr(value)
    return repr(value)


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


__all__ = ["InspectorPanel", "ResourceLineEdit", "resource_field_accepts"]

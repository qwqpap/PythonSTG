"""Inspector fields derived from public DSL constructor signatures."""

from __future__ import annotations

import ast
import inspect
import types
from pathlib import PurePosixPath
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from src.authoring import dsl
from src.authoring.program import Expr, Ref
from src.qt_compat.QtCore import Signal
from src.qt_compat.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from .session import EditorSession
from .sidebars import RESOURCE_MIME


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


class InspectorPanel(QWidget):
    """Use constructor annotations as the only field schema."""

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inspector_panel")
        self.session = session
        self.layout = QFormLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.session.selection_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        while self.layout.rowCount():
            self.layout.removeRow(0)
        node = self.session.current_node
        unit = self.session.current_unit
        if node is not None:
            constructor = dsl.NODE_CONSTRUCTORS.get(node.kind)
            annotations = get_type_hints(constructor) if constructor is not None else {}
            self.layout.addRow("节点类型", QLabel(node.kind))
            self.layout.addRow("UID", QLabel(node.uid))
            for name, value in _node_fields(node, constructor):
                widget = self._field(
                    value,
                    annotations.get(name, Any),
                    node.kind,
                    name,
                    lambda new_value, uid=node.uid, key=name: self.session.set_node_argument(
                        uid, key, new_value
                    ),
                )
                self.layout.addRow(name, widget)
            return
        if unit is not None:
            constructor = dsl.UNIT_CONSTRUCTORS[unit.kind]
            annotations = get_type_hints(constructor)
            signature = inspect.signature(constructor)
            self.layout.addRow("逻辑单元", QLabel(unit.kind))
            name_field = self._field(
                unit.name,
                annotations.get("name", str),
                unit.kind,
                "name",
                lambda value, unit_id=unit.id: self.session.set_unit_field(unit_id, "name", value),
            )
            name_field.setObjectName("unit_name")
            self.layout.addRow("名称", name_field)
            for name, value in _unit_fields(unit.metadata, signature):
                widget = self._field(
                    value,
                    annotations.get(name, Any),
                    unit.kind,
                    name,
                    lambda new_value, unit_id=unit.id, key=name: self.session.set_unit_field(
                        unit_id, key, new_value
                    ),
                )
                self.layout.addRow(name, widget)
            return
        self.layout.addRow(QLabel("当前文件不可视化编辑"))

    def _field(
        self,
        value: Any,
        annotation: Any,
        owner_kind: str,
        name: str,
        commit,
    ) -> QWidget:
        editable = self.session.can_edit and _is_literal_value(value)
        field_type = _field_type(annotation, value)
        if field_type is bool:
            widget = QCheckBox(self)
            widget.setChecked(bool(value))
            widget.setEnabled(editable)
            if editable:
                widget.toggled.connect(lambda checked: self._commit(commit, checked))
        elif field_type is int:
            widget = QSpinBox(self)
            widget.setRange(-1_000_000_000, 1_000_000_000)
            widget.setValue(int(value))
            widget.setReadOnly(not editable)
            if editable:
                widget.editingFinished.connect(
                    lambda editor=widget: self._commit(commit, editor.value())
                )
        elif field_type is float:
            widget = QDoubleSpinBox(self)
            widget.setDecimals(6)
            widget.setRange(-1_000_000_000.0, 1_000_000_000.0)
            widget.setValue(float(value))
            widget.setReadOnly(not editable)
            if editable:
                widget.editingFinished.connect(
                    lambda editor=widget: self._commit(commit, editor.value())
                )
        else:
            accepts = lambda uri: resource_field_accepts(owner_kind, name, uri)
            widget = ResourceLineEdit(accepts, self)
            widget.setText(value if isinstance(value, str) else repr(value))
            widget.setReadOnly(not editable)
            if editable:
                widget.editingFinished.connect(
                    lambda editor=widget, original=value: self._commit(
                        commit, _parse_text(editor.text(), original)
                    )
                )
                widget.resource_dropped.connect(lambda uri: self._commit(commit, uri))
        widget.setObjectName(f"argument_{name}")
        widget.setProperty("pystg_annotation", str(annotation))
        return widget

    def _commit(self, callback, value: Any) -> None:
        try:
            callback(value)
        except Exception as exc:
            window = self.window()
            if hasattr(window, "statusBar"):
                window.statusBar().showMessage(f"参数未修改：{exc}", 5000)
            self.refresh()


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


def _parse_text(text: str, original: Any) -> Any:
    if isinstance(original, str):
        return text
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return text


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
    metadata: dict[str, Any], signature: inspect.Signature
) -> tuple[tuple[str, Any], ...]:
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


def _is_literal_value(value: Any) -> bool:
    if isinstance(value, (Expr, Ref)):
        return False
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_literal_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_literal_value(item) for key, item in value.items())
    return False


__all__ = ["InspectorPanel", "ResourceLineEdit", "resource_field_accepts"]

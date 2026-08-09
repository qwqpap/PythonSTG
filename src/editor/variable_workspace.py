"""Compact variable declaration/overlay panel for Scene documents."""

from __future__ import annotations

import json

from src.authoring.variables import VARIABLE_SCOPES, VariableSpec
from src.qt_compat.QtCore import Qt, pyqtSignal
from src.qt_compat.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .document import SceneDocument


class VariableEditor(QWidget):
    """Authoring declarations are editable; runtime values are an overlay."""

    variableSelected = pyqtSignal(str)
    addVariableRequested = pyqtSignal(str, str, object, str)
    editVariableRequested = pyqtSignal(str, object)
    deleteVariableRequested = pyqtSignal(str)
    bindingRequested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("variableEditor")
        self.document: SceneDocument | None = None
        self.selected_state_id: str | None = None
        self.runtime_overlay: dict = {}
        self._rebuilding = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)
        header = QHBoxLayout()
        header.addWidget(QLabel("Variable"))
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("variableName")
        self.name_edit.setPlaceholderText("phase.enrage")
        header.addWidget(self.name_edit, 2)
        self.type_combo = QComboBox()
        self.type_combo.setObjectName("variableType")
        self.type_combo.addItems(["bool", "int", "float", "string", "vector2", "color", "resource", "complex"])
        header.addWidget(self.type_combo, 1)
        self.scope_combo = QComboBox()
        self.scope_combo.setObjectName("variableScope")
        self.scope_combo.addItems(list(VARIABLE_SCOPES))
        header.addWidget(self.scope_combo, 1)
        self.default_edit = QLineEdit("0")
        self.default_edit.setObjectName("variableDefault")
        self.default_edit.setPlaceholderText("JSON default")
        header.addWidget(self.default_edit, 2)
        add = QPushButton("Add")
        add.setObjectName("variableAdd")
        add.clicked.connect(self._add_requested)
        header.addWidget(add)
        layout.addLayout(header)

        self.table = QTableWidget(0, 7)
        self.table.setObjectName("variableTable")
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Scope", "Default", "Writer", "Reader", "Runtime"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.currentCellChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.runtime_label = QLabel("Runtime: none")
        self.runtime_label.setObjectName("variableRuntimeOverlay")
        footer.addWidget(self.runtime_label, 1)
        delete = QPushButton("Delete")
        delete.setObjectName("variableDelete")
        delete.clicked.connect(self._delete_requested)
        footer.addWidget(delete)
        bind = QPushButton("Bind")
        bind.setObjectName("variableBind")
        bind.clicked.connect(self._binding_requested)
        footer.addWidget(bind)
        layout.addLayout(footer)

    def set_document(self, document: SceneDocument | None, *, state_id: str | None = None) -> None:
        self.document = document
        self.selected_state_id = state_id
        self._rebuild()

    def clear_document(self) -> None:
        self.set_document(None)

    def set_runtime_overlay(self, overlay: dict) -> None:
        self.runtime_overlay = overlay if isinstance(overlay, dict) else {}
        self._rebuild()

    def _variables(self) -> list[VariableSpec]:
        if self.document is None:
            return []
        values = list(self.document.variables)
        if self.selected_state_id:
            state = self.document.state_graph.find_state(self.selected_state_id)
            if state is not None:
                values.extend(state.variables)
        return values

    def _rebuild(self) -> None:
        self._rebuilding = True
        try:
            self.table.setRowCount(0)
            for variable in self._variables():
                row = self.table.rowCount()
                self.table.insertRow(row)
                values = [
                    variable.name,
                    variable.type,
                    variable.scope,
                    json.dumps(variable.default, ensure_ascii=False, sort_keys=True),
                    ", ".join(variable.writable_by) or "read-only",
                    ", ".join(variable.readers) or "—",
                    self._runtime_value(variable),
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.UserRole, variable.id)
                    self.table.setItem(row, column, item)
            self.table.resizeColumnsToContents()
            count = sum(len(values) for values in self.runtime_overlay.values() if isinstance(values, dict))
            self.runtime_label.setText(f"Runtime overlay: {count} scopes (read-only)")
        finally:
            self._rebuilding = False

    def _runtime_value(self, variable: VariableSpec) -> str:
        scope = self.runtime_overlay.get(variable.scope, {})
        if not isinstance(scope, dict):
            return "—"
        owners = scope.values()
        for values in owners:
            if isinstance(values, dict) and variable.name in values:
                return json.dumps(values[variable.name], ensure_ascii=False, sort_keys=True)
        return "—"

    def _selection_changed(self, row: int, *_args) -> None:
        if self._rebuilding or row < 0:
            return
        item = self.table.item(row, 0)
        if item is not None and item.data(Qt.UserRole):
            self.variableSelected.emit(str(item.data(Qt.UserRole)))

    def _add_requested(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            return
        try:
            default = json.loads(self.default_edit.text() or "null")
        except json.JSONDecodeError:
            return
        self.addVariableRequested.emit(
            name,
            self.type_combo.currentText(),
            default,
            self.scope_combo.currentText(),
        )

    def _delete_requested(self) -> None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is not None and item.data(Qt.UserRole):
            self.deleteVariableRequested.emit(str(item.data(Qt.UserRole)))

    def _binding_requested(self) -> None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is not None and item.data(Qt.UserRole):
            self.bindingRequested.emit(str(item.data(Qt.UserRole)))


VariableWorkspace = VariableEditor


__all__ = ["VariableEditor", "VariableWorkspace"]

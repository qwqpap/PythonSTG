"""Variable declaration editor and read-only runtime overlay."""

from __future__ import annotations

import json

from src.authoring.variables import (
    DEFAULT_VARIABLE_TYPES,
    VARIABLE_REDUCERS,
    VARIABLE_SCOPES,
    VariableSpec,
)
from src.qt_compat.QtCore import Qt, pyqtSignal
from src.qt_compat.QtWidgets import (
    QCheckBox,
    QComboBox,
    QAbstractScrollArea,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.authoring.scene.document import SceneDocument


class VariableEditor(QWidget):
    """Edit declarations through signals; runtime values never become authoring data."""

    variableSelected = pyqtSignal(str)
    addVariableRequested = pyqtSignal(str, str, object, str)
    editVariableRequested = pyqtSignal(str, object)
    deleteVariableRequested = pyqtSignal(str)
    bindingRequested = pyqtSignal(str)
    mappingRequested = pyqtSignal()

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
        layout.addLayout(self._build_declaration_form())
        layout.addLayout(self._build_property_form())
        layout.addWidget(self._build_table(), 1)
        layout.addLayout(self._build_footer())

    def _build_declaration_form(self) -> QGridLayout:
        """Name/type/scope/default plus Add — everything a declaration needs.

        Keep authoring controls in a compact grid rather than one long
        horizontal strip.  The Variables dock is also used at the editor's
        960px minimum width; a single row silently clipped scope/writer
        controls in the native window.
        """

        header = QGridLayout()
        header.setHorizontalSpacing(6)
        header.setVerticalSpacing(4)
        header.addWidget(QLabel("Name"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("variableName")
        self.name_edit.setPlaceholderText("phase.enrage")
        self.name_edit.setMinimumWidth(0)
        self.name_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header.addWidget(self.name_edit, 0, 1, 1, 3)
        header.addWidget(QLabel("Type"), 1, 0)
        self.type_combo = QComboBox()
        self.type_combo.setObjectName("variableType")
        # Item text is author-facing and therefore translated; the declaration
        # written into the document must stay the internal token, so every entry
        # carries its own value as item data and is only ever read that way.
        # The type list comes from the registry that validates declarations, so
        # a plugin-registered type is offered here without a second edit.
        for variable_type in DEFAULT_VARIABLE_TYPES:
            self.type_combo.addItem(variable_type, variable_type)
        self.type_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        header.addWidget(self.type_combo, 1, 1)
        header.addWidget(QLabel("Scope"), 1, 2)
        self.scope_combo = QComboBox()
        self.scope_combo.setObjectName("variableScope")
        for scope in VARIABLE_SCOPES:
            self.scope_combo.addItem(scope, scope)
        self.scope_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        header.addWidget(self.scope_combo, 1, 3)
        header.addWidget(QLabel("Default"), 2, 0)
        self.default_edit = QLineEdit("0")
        self.default_edit.setObjectName("variableDefault")
        self.default_edit.setPlaceholderText("JSON default")
        self.default_edit.setMinimumWidth(0)
        self.default_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header.addWidget(self.default_edit, 2, 1, 1, 2)
        add = QPushButton("Add")
        add.setObjectName("variableAdd")
        add.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        add.clicked.connect(self._add_requested)
        header.addWidget(add, 2, 3)
        # Give the scope selector a little more room at the 300px dock width;
        # the type selector only needs a short token such as ``bool``.
        header.setColumnStretch(1, 1)
        header.setColumnStretch(3, 2)
        return header

    def _build_property_form(self) -> QGridLayout:
        """Access lists, reducer, the boolean options and Apply."""

        properties = QGridLayout()
        properties.setHorizontalSpacing(6)
        properties.setVerticalSpacing(4)
        properties.addWidget(QLabel("Writers"), 0, 0)
        self.writers_edit = QLineEdit()
        self.writers_edit.setObjectName("variableWriters")
        self.writers_edit.setPlaceholderText("writers: timeline,safe_action")
        self.writers_edit.setMinimumWidth(0)
        self.writers_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        properties.addWidget(self.writers_edit, 0, 1, 1, 3)
        properties.addWidget(QLabel("Readers"), 1, 0)
        self.readers_edit = QLineEdit()
        self.readers_edit.setObjectName("variableReaders")
        self.readers_edit.setPlaceholderText("readers: pattern,debugger")
        self.readers_edit.setMinimumWidth(0)
        self.readers_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        properties.addWidget(self.readers_edit, 1, 1, 1, 3)
        properties.addWidget(QLabel("Reducer"), 2, 0)
        self.reducer_combo = QComboBox()
        self.reducer_combo.setObjectName("variableReducer")
        self.reducer_combo.addItem("none", None)
        for reducer in VARIABLE_REDUCERS:
            self.reducer_combo.addItem(reducer, reducer)
        self.reducer_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        properties.addWidget(self.reducer_combo, 2, 1, 1, 3)
        options = QGridLayout()
        options.setContentsMargins(0, 0, 0, 0)
        options.setSpacing(2)
        self.animatable_check = QCheckBox("Animatable")
        self.animatable_check.setObjectName("variableAnimatable")
        options.addWidget(self.animatable_check, 0, 0)
        self.replay_check = QCheckBox("Replay")
        self.replay_check.setObjectName("variableRecordReplay")
        self.replay_check.setChecked(True)
        options.addWidget(self.replay_check, 0, 1)
        self.behavior_output_check = QCheckBox("Behavior output")
        self.behavior_output_check.setObjectName("variableBehaviorOutput")
        options.addWidget(self.behavior_output_check, 1, 0, 1, 2)
        properties.addLayout(options, 3, 0, 2, 4)
        edit = QPushButton("Apply properties")
        edit.setObjectName("variableEdit")
        edit.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        edit.clicked.connect(self._edit_requested)
        properties.addWidget(edit, 5, 1, 1, 3)
        properties.setColumnStretch(1, 2)
        properties.setColumnStretch(3, 1)
        return properties

    def _build_table(self) -> QTableWidget:
        """One row per declaration, last column carrying the runtime value."""

        self.table = QTableWidget(0, 10)
        self.table.setObjectName("variableTable")
        self.table.setHorizontalHeaderLabels(
            ["Name", "Type", "Scope", "Default", "Writer", "Reader", "Animatable", "Reducer", "Behavior output", "Runtime"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
        self.table.setMinimumWidth(0)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.currentCellChanged.connect(self._selection_changed)
        return self.table

    def _build_footer(self) -> QHBoxLayout:
        """Runtime readout, then the actions that need a selected row."""

        footer = QHBoxLayout()
        self.runtime_label = QLabel("Runtime: none")
        self.runtime_label.setObjectName("variableRuntimeOverlay")
        self.runtime_label.setWordWrap(True)
        self.runtime_label.setMinimumWidth(0)
        self.runtime_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        footer.addWidget(self.runtime_label, 1)
        delete = QPushButton("Delete")
        delete.setObjectName("variableDelete")
        delete.clicked.connect(self._delete_requested)
        footer.addWidget(delete)
        bind = QPushButton("Bind")
        bind.setObjectName("variableBind")
        bind.clicked.connect(self._binding_requested)
        footer.addWidget(bind)
        self.mapping_button = QPushButton("Map")
        self.mapping_button.setObjectName("variableMappings")
        self.mapping_button.setToolTip("Edit Behavior output mappings")
        self.mapping_button.clicked.connect(self.mappingRequested)
        footer.addWidget(self.mapping_button)
        return footer

    def set_document(self, document: SceneDocument | None, *, state_id: str | None = None) -> None:
        self.document = document
        self.selected_state_id = state_id
        self._rebuild()

    def clear_document(self) -> None:
        self.set_document(None)

    def set_runtime_overlay(self, overlay: dict) -> None:
        if isinstance(overlay, dict):
            try:
                self.runtime_overlay = json.loads(json.dumps(overlay, ensure_ascii=False))
            except (TypeError, ValueError):
                self.runtime_overlay = {}
        else:
            self.runtime_overlay = {}
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
                    "yes" if variable.animatable else "no",
                    variable.reducer or "—",
                    "yes" if variable.behavior_output else "no",
                    self._runtime_value(variable),
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.UserRole, variable.id)
                    self.table.setItem(row, column, item)
            self.table.resizeColumnsToContents()
            count = sum(len(values) for values in self.runtime_overlay.values() if isinstance(values, dict))
            self.runtime_label.setText(f"Runtime values: {count} scopes (read-only)")
        finally:
            self._rebuilding = False

    def _runtime_value(self, variable: VariableSpec) -> str:
        scope = self.runtime_overlay.get(variable.scope, {})
        if not isinstance(scope, dict):
            return "—"
        for values in scope.values():
            if isinstance(values, dict) and variable.name in values:
                return json.dumps(values[variable.name], ensure_ascii=False, sort_keys=True)
        return "—"

    def _selected_id(self) -> str | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return str(item.data(Qt.UserRole)) if item is not None and item.data(Qt.UserRole) else None

    def _selection_changed(self, row: int, *_args) -> None:
        if self._rebuilding or row < 0:
            return
        variable_id = self._selected_id()
        if variable_id is None:
            return
        self.variableSelected.emit(variable_id)
        variable = next((item for item in self._variables() if item.id == variable_id), None)
        if variable is None:
            return
        self.name_edit.setText(variable.name)
        self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(variable.type)))
        self.scope_combo.setCurrentIndex(max(0, self.scope_combo.findData(variable.scope)))
        self.default_edit.setText(json.dumps(variable.default, ensure_ascii=False, sort_keys=True))
        self.writers_edit.setText(",".join(variable.writable_by))
        self.readers_edit.setText(",".join(variable.readers))
        self.reducer_combo.setCurrentIndex(max(0, self.reducer_combo.findData(variable.reducer)))
        self.animatable_check.setChecked(variable.animatable)
        self.replay_check.setChecked(variable.record_in_replay)
        self.behavior_output_check.setChecked(variable.behavior_output)

    def _add_requested(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            return
        try:
            default = json.loads(self.default_edit.text() or "null")
        except json.JSONDecodeError:
            return
        self.addVariableRequested.emit(
            name, self.type_combo.currentData(), default, self.scope_combo.currentData()
        )

    def _edit_requested(self) -> None:
        variable_id = self._selected_id()
        if variable_id is None:
            return
        try:
            default = json.loads(self.default_edit.text() or "null")
        except json.JSONDecodeError:
            return
        self.editVariableRequested.emit(
            variable_id,
            {
                "name": self.name_edit.text().strip(),
                "type": self.type_combo.currentData(),
                "scope": self.scope_combo.currentData(),
                "default": default,
                "writable_by": tuple(item.strip() for item in self.writers_edit.text().split(",") if item.strip()),
                "readers": tuple(item.strip() for item in self.readers_edit.text().split(",") if item.strip()),
                "reducer": self.reducer_combo.currentData(),
                "animatable": self.animatable_check.isChecked(),
                "record_in_replay": self.replay_check.isChecked(),
                "behavior_output": self.behavior_output_check.isChecked(),
            },
        )

    def _delete_requested(self) -> None:
        variable_id = self._selected_id()
        if variable_id is not None:
            self.deleteVariableRequested.emit(variable_id)

    def _binding_requested(self) -> None:
        variable_id = self._selected_id()
        if variable_id is not None:
            self.bindingRequested.emit(variable_id)


VariableWorkspace = VariableEditor


__all__ = ["VariableEditor", "VariableWorkspace"]

"""Small, data-driven dialogs for variable bindings and output mappings.

The dialogs deliberately own only transient selection state.  The editor
window applies the accepted mapping diff through the document's CommandStack;
canceling a dialog therefore cannot mutate the authoring document or dirty
the session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.authoring.variables import (
    VARIABLE_OPERATIONS,
    VariableOutputMapping,
    VariableRef,
    VariableSpec,
)
from src.qt_compat.QtCore import Qt, pyqtSignal
from src.qt_compat.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def variable_display_name(variable: VariableSpec) -> str:
    """Return a stable, readable label used by binding controls."""

    owner = f" / {variable.owner_id}" if variable.owner_id else ""
    return f"{variable.name} / {variable.scope} / {variable.type}{owner}"


class VariableBindingDialog(QDialog):
    """Search and select one type/scope-compatible variable reference."""

    bindingSelected = pyqtSignal(str)

    def __init__(self, candidates: Iterable[VariableSpec], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("variableBindingDialog")
        self.setWindowTitle("Select compatible binding")
        self.resize(440, 320)
        self._candidates = tuple(candidates)
        self._selected_id: str | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Search compatible variables"))
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("bindingSearch")
        self.search_edit.setPlaceholderText("name, scope, type, owner")
        self.search_edit.textChanged.connect(self._filter)
        layout.addWidget(self.search_edit)

        self.results = QListWidget()
        self.results.setObjectName("bindingCandidates")
        self.results.setSelectionMode(QListWidget.SingleSelection)
        self.results.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.results, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.setObjectName("bindingDialogButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._filter("")

    @property
    def selected_id(self) -> str | None:
        return self._selected_id

    def _filter(self, text: str) -> None:
        query = str(text).strip().casefold()
        self.results.clear()
        for variable in self._candidates:
            label = variable_display_name(variable)
            if query and query not in label.casefold():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, variable.id)
            item.setToolTip(variable.id)
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def accept(self) -> None:
        item = self.results.currentItem()
        if item is None:
            return
        self._selected_id = str(item.data(Qt.UserRole) or "") or None
        if self._selected_id is not None:
            self.bindingSelected.emit(self._selected_id)
        super().accept()


@dataclass(frozen=True)
class _MappingRow:
    mapping_id: str
    source_id: str
    target_id: str
    operation: str
    unresolved: bool = False


class VariableMappingDialog(QDialog):
    """Edit Behavior-output mappings without mutating the document."""

    def __init__(
        self,
        variables: Iterable[VariableSpec],
        mappings: Iterable[VariableOutputMapping],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("variableMappingDialog")
        self.setWindowTitle("Edit output mappings")
        self.resize(680, 440)
        self._variables = tuple(variables)
        self._variables_by_id = {item.id: item for item in self._variables}
        self._rows: list[_MappingRow] = []
        self._editing_row: int | None = None
        self._unresolved_mapping = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Behavior output / writable variable"))
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("mappingSearch")
        self.search_edit.setPlaceholderText("Filter mappings by source, target or operation")
        self.search_edit.textChanged.connect(self._filter_rows)
        layout.addWidget(self.search_edit)

        self.mapping_table = QTableWidget(0, 3)
        self.mapping_table.setObjectName("mappingTable")
        self.mapping_table.setHorizontalHeaderLabels(["Source", "Target", "Operation"])
        self.mapping_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mapping_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mapping_table.currentCellChanged.connect(self._row_selected)
        layout.addWidget(self.mapping_table, 1)

        form = QGridLayout()
        form.addWidget(QLabel("Source"), 0, 0)
        self.source_combo = QComboBox()
        self.source_combo.setObjectName("mappingSource")
        self.source_combo.currentIndexChanged.connect(self._source_changed)
        form.addWidget(self.source_combo, 0, 1)
        form.addWidget(QLabel("Target"), 1, 0)
        self.target_combo = QComboBox()
        self.target_combo.setObjectName("mappingTarget")
        form.addWidget(self.target_combo, 1, 1)
        form.addWidget(QLabel("Operation"), 2, 0)
        self.operation_combo = QComboBox()
        self.operation_combo.setObjectName("mappingOperation")
        # Operation names are shown to the author and therefore translated, so
        # the internal token travels as item data instead of as display text.
        for operation in VARIABLE_OPERATIONS:
            self.operation_combo.addItem(operation, operation)
        form.addWidget(self.operation_combo, 2, 1)
        actions = QHBoxLayout()
        self.add_button = QPushButton("Add / update")
        self.add_button.setObjectName("mappingAdd")
        self.add_button.clicked.connect(self._add_or_update)
        actions.addWidget(self.add_button)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("mappingRemove")
        self.remove_button.clicked.connect(self._remove_selected)
        actions.addWidget(self.remove_button)
        form.addLayout(actions, 0, 2, 3, 1)
        layout.addLayout(form)

        self.diagnostic_label = QLabel("")
        self.diagnostic_label.setObjectName("mappingDiagnostic")
        self.diagnostic_label.setWordWrap(True)
        layout.addWidget(self.diagnostic_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.setObjectName("mappingDialogButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_mappings(mappings)
        self._populate_sources()

    @property
    def mappings(self) -> tuple[VariableOutputMapping, ...]:
        """Return the dialog's current mapping records as fresh values."""

        values: list[VariableOutputMapping] = []
        for row in self._rows:
            source = self._variables_by_id.get(row.source_id)
            target = self._variables_by_id.get(row.target_id)
            if source is None or target is None:
                continue
            values.append(
                VariableOutputMapping(
                    id=row.mapping_id,
                    source=self._ref(source),
                    target=self._ref(target),
                    operation=row.operation,
                )
            )
        return tuple(values)

    @staticmethod
    def _ref(variable: VariableSpec) -> VariableRef:
        return VariableRef(
            variable.name,
            scope=variable.scope,
            type=variable.type,
            owner_id=variable.owner_id,
        )

    def _load_mappings(self, mappings: Iterable[VariableOutputMapping]) -> None:
        for mapping in mappings:
            source = mapping.source
            target = mapping.target
            if not isinstance(source, VariableRef):
                source = VariableRef.from_dict(source)
            if not isinstance(target, VariableRef):
                target = VariableRef.from_dict(target)
            source_spec = self._find_spec(source)
            target_spec = self._find_spec(target)
            if source_spec is None or target_spec is None:
                self._unresolved_mapping = True
                self.diagnostic_label.setText(
                    f"Unresolved mapping {mapping.id}; save is blocked until it is repaired."
                )
                self._rows.append(_MappingRow(mapping.id, "", "", mapping.operation, unresolved=True))
                continue
            self._rows.append(
                _MappingRow(mapping.id, source_spec.id, target_spec.id, mapping.operation)
            )
        self._rebuild_table()

    def _find_spec(self, reference: VariableRef) -> VariableSpec | None:
        candidates = [item for item in self._variables if item.name == reference.name]
        if reference.scope is not None:
            candidates = [item for item in candidates if item.scope == reference.scope]
        if reference.owner_id is not None:
            candidates = [item for item in candidates if item.owner_id == reference.owner_id]
        if reference.type is not None:
            candidates = [item for item in candidates if item.type == reference.type]
        return candidates[0] if len(candidates) == 1 else None

    def _source_specs(self) -> tuple[VariableSpec, ...]:
        return tuple(item for item in self._variables if item.scope == "behavior" and item.behavior_output)

    def _target_specs(self, source: VariableSpec | None = None) -> tuple[VariableSpec, ...]:
        values = tuple(
            item
            for item in self._variables
            if item.scope != "engine_snapshot"
            and "behavior" in item.writable_by
            and (source is None or item.id != source.id)
        )
        if source is not None:
            values = tuple(item for item in values if item.type == source.type)
        return values

    def _populate_sources(self, selected_id: str | None = None) -> None:
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for variable in self._source_specs():
            self.source_combo.addItem(variable_display_name(variable), variable.id)
        self.source_combo.blockSignals(False)
        if selected_id:
            index = self.source_combo.findData(selected_id)
            if index >= 0:
                self.source_combo.setCurrentIndex(index)
        self._source_changed(self.source_combo.currentIndex())

    def _source_changed(self, _index: int) -> None:
        source = self._variables_by_id.get(self.source_combo.currentData())
        selected = self.target_combo.currentData()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        for variable in self._target_specs(source):
            self.target_combo.addItem(variable_display_name(variable), variable.id)
        self.target_combo.blockSignals(False)
        if selected:
            index = self.target_combo.findData(selected)
            if index >= 0:
                self.target_combo.setCurrentIndex(index)

    def _row_selected(self, row: int, *_args) -> None:
        if row < 0 or row >= len(self._rows):
            self._editing_row = None
            return
        self._editing_row = row
        value = self._rows[row]
        source_index = self.source_combo.findData(value.source_id)
        if source_index >= 0:
            self.source_combo.setCurrentIndex(source_index)
        target_index = self.target_combo.findData(value.target_id)
        if target_index >= 0:
            self.target_combo.setCurrentIndex(target_index)
        operation_index = self.operation_combo.findData(value.operation)
        if operation_index >= 0:
            self.operation_combo.setCurrentIndex(operation_index)

    def _add_or_update(self) -> None:
        source_id = self.source_combo.currentData()
        target_id = self.target_combo.currentData()
        operation = self.operation_combo.currentData()
        source = self._variables_by_id.get(source_id)
        target = self._variables_by_id.get(target_id)
        if source is None or target is None:
            self.diagnostic_label.setText("Choose a declared Behavior output and a writable target.")
            return
        if source.type != target.type:
            self.diagnostic_label.setText("Source and target types must match.")
            return
        if operation == "toggle" and target.type != "bool":
            self.diagnostic_label.setText("toggle requires a bool target.")
            return
        if operation == "add" and target.type not in {"int", "float", "vector2", "complex"}:
            self.diagnostic_label.setText(f"add is unsupported for {target.type} targets.")
            return
        value = _MappingRow(
            self._rows[self._editing_row].mapping_id if self._editing_row is not None else VariableOutputMapping(self._ref(source), self._ref(target), operation).id,
            str(source_id),
            str(target_id),
            operation,
        )
        if self._editing_row is None:
            self._rows.append(value)
            self._editing_row = len(self._rows) - 1
        else:
            self._rows[self._editing_row] = value
        self._unresolved_mapping = any(item.unresolved for item in self._rows)
        self.diagnostic_label.clear()
        self._rebuild_table()

    def _remove_selected(self) -> None:
        row = self.mapping_table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        self._rows.pop(row)
        self._editing_row = None
        self._unresolved_mapping = any(item.unresolved for item in self._rows)
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self.mapping_table.setRowCount(0)
        for row in self._rows:
            source = self._variables_by_id.get(row.source_id)
            target = self._variables_by_id.get(row.target_id)
            table_row = self.mapping_table.rowCount()
            self.mapping_table.insertRow(table_row)
            values = (
                variable_display_name(source) if source is not None else "<unresolved source>",
                variable_display_name(target) if target is not None else "<unresolved target>",
                row.operation,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row.mapping_id)
                self.mapping_table.setItem(table_row, column, item)
        self.mapping_table.resizeColumnsToContents()
        self._filter_rows(self.search_edit.text())

    def _filter_rows(self, text: str) -> None:
        query = str(text).strip().casefold()
        for row in range(self.mapping_table.rowCount()):
            value = " ".join(
                self.mapping_table.item(row, column).text()
                for column in range(self.mapping_table.columnCount())
                if self.mapping_table.item(row, column) is not None
            )
            self.mapping_table.setRowHidden(row, bool(query and query not in value.casefold()))

    def accept(self) -> None:
        if self._unresolved_mapping:
            self.diagnostic_label.setText(
                "Resolve the unresolved mapping before accepting this dialog."
            )
            return
        super().accept()


__all__ = ["VariableBindingDialog", "VariableMappingDialog", "variable_display_name"]

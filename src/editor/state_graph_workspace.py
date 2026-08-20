"""Native StateGraph authoring surface shared by StageFlow and PhaseFlow."""

from __future__ import annotations

from src.qt_compat.QtCore import Qt, pyqtSignal
from src.qt_compat.QtGui import QColor, QFont
from src.qt_compat.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .document import SceneDocument, StateGraphSpec, StateSpec
from .i18n import LANGUAGE_CHINESE, LanguageManager


class StateGraphEditor(QWidget):
    """One contextual view over the StateGraphSpec embedded in a Scene."""

    stateSelected = pyqtSignal(str)
    addStateRequested = pyqtSignal(str)
    renameStateRequested = pyqtSignal(str, str)
    duplicateStateRequested = pyqtSignal(str)
    deleteStateRequested = pyqtSignal(str)
    moveStateRequested = pyqtSignal(str, int)
    addTransitionRequested = pyqtSignal(str, str, str, int)
    editTransitionRequested = pyqtSignal(str, object)
    deleteTransitionRequested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("stateGraphEditor")
        self.setMinimumWidth(240)
        self.document: SceneDocument | None = None
        self.selected_state_id: str | None = None
        self.active_state_path: tuple[str, ...] = ()
        self.context_name = "StageFlow"
        self._language_manager: LanguageManager | None = None
        self._rebuilding = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 6)
        outer.setSpacing(4)
        outer.addLayout(self._build_header())
        self.tabs = QTabWidget()
        self.tabs.setObjectName("stateGraphTabs")
        self.tabs.setDocumentMode(True)
        outer.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_states_page(), "States")
        self.tabs.addTab(self._build_transitions_page(), "Transitions")
        self._trigger_changed()

    def _build_header(self) -> QHBoxLayout:
        """Context name plus the rename field for the selected state."""

        header = QHBoxLayout()
        self.context_label = QLabel(self.context_name)
        self.context_label.setObjectName("stateGraphContextLabel")
        font = QFont(self.context_label.font())
        font.setBold(True)
        self.context_label.setFont(font)
        header.addWidget(self.context_label)
        self.state_name = QLineEdit()
        self.state_name.setObjectName("stateGraphStateName")
        self.state_name.setPlaceholderText("State name")
        self.state_name.setFixedHeight(24)
        self.state_name.returnPressed.connect(self._request_rename)
        header.addWidget(self.state_name, 1)
        apply_name = QPushButton("Apply")
        apply_name.setObjectName("stateGraphApplyStateName")
        apply_name.setFixedHeight(24)
        apply_name.setStyleSheet("padding: 1px 5px;")
        apply_name.clicked.connect(self._request_rename)
        header.addWidget(apply_name)
        return header

    def _build_states_page(self) -> QWidget:
        """State tree with the add/copy/delete/reorder strip beneath it."""

        states_page = QWidget()
        states_page.setObjectName("stateGraphStatesPage")
        states_layout = QVBoxLayout(states_page)
        states_layout.setContentsMargins(2, 2, 2, 2)
        states_layout.setSpacing(2)

        self.tree = QTreeWidget()
        self.tree.setObjectName("stateGraphTree")
        self.tree.setMinimumHeight(48)
        self.tree.setMaximumHeight(120)
        self.tree.setHeaderLabels(["State", "Duration"])
        self.tree.setAlternatingRowColors(True)
        self.tree.currentItemChanged.connect(self._current_item_changed)
        states_layout.addWidget(self.tree, 1)

        state_buttons = QHBoxLayout()
        state_buttons.setSpacing(2)
        for text, name, callback, button_type in (
            ("Add", "stateGraphAddState", self._request_add, QPushButton),
            (
                "Copy",
                "stateGraphDuplicateState",
                self._request_duplicate,
                QPushButton,
            ),
            ("Delete", "stateGraphDeleteState", self._request_delete, QPushButton),
            ("↑", "stateGraphStateUp", lambda: self._request_move(-1), QToolButton),
            ("↓", "stateGraphStateDown", lambda: self._request_move(1), QToolButton),
        ):
            button = button_type()
            button.setText(text)
            button.setObjectName(name)
            button.setFixedHeight(24)
            if isinstance(button, QToolButton):
                button.setFixedWidth(24)
            button.setStyleSheet("padding: 1px 3px;")
            button.clicked.connect(callback)
            state_buttons.addWidget(button)
        states_layout.addLayout(state_buttons)
        return states_page

    def _build_transitions_page(self) -> QWidget:
        """Transition picker, target, trigger and the three edit actions."""

        transitions = QWidget()
        transitions.setObjectName("stateGraphTransitionsGroup")
        self.transitions_group = transitions
        transition_form = QGridLayout(transitions)
        transition_form.setContentsMargins(2, 2, 2, 2)
        transition_form.setHorizontalSpacing(4)
        transition_form.setVerticalSpacing(2)
        self.transition_picker = QComboBox()
        self.transition_picker.setObjectName("stateGraphTransitionPicker")
        self.transition_picker.setEditable(True)
        self.transition_picker.setToolTip(
            "Select a transition, or edit its name before pressing Set"
        )
        self.transition_picker.currentIndexChanged.connect(
            self._transition_selection_changed
        )
        transition_form.addWidget(QLabel("Transition"), 0, 0)
        transition_form.addWidget(self.transition_picker, 0, 1, 1, 2)
        self.transition_target = QComboBox()
        self.transition_target.setObjectName("stateGraphTransitionTarget")
        transition_form.addWidget(QLabel("Target"), 1, 0)
        transition_form.addWidget(self.transition_target, 1, 1, 1, 2)
        self.transition_trigger = QComboBox()
        self.transition_trigger.setObjectName("stateGraphTransitionTrigger")
        self.transition_trigger.addItem("After", "after")
        self.transition_trigger.addItem("On complete", "complete")
        self.transition_trigger.currentIndexChanged.connect(
            self._trigger_changed
        )
        transition_form.addWidget(QLabel("Trigger"), 2, 0)
        transition_form.addWidget(self.transition_trigger, 2, 1)
        self.transition_frames = QSpinBox()
        self.transition_frames.setObjectName("stateGraphTransitionFrames")
        self.transition_frames.setRange(1, 1_000_000)
        self.transition_frames.setValue(60)
        self.transition_frames.setSuffix(" fr")
        self.transition_frames.setToolTip("Frames after entering this state")
        transition_form.addWidget(self.transition_frames, 2, 2)
        transition_form.addLayout(self._build_transition_actions(), 3, 0, 1, 3)
        transition_form.setColumnStretch(1, 1)
        transition_form.setRowStretch(4, 1)
        return transitions

    def _build_transition_actions(self) -> QHBoxLayout:
        """Priority spin box, then add/apply/delete for the picked transition."""

        self.transition_priority = QSpinBox()
        self.transition_priority.setObjectName("stateGraphTransitionPriority")
        self.transition_priority.setRange(-1000, 1000)
        transition_buttons = QHBoxLayout()
        transition_buttons.setSpacing(2)
        transition_buttons.addWidget(QLabel("Prio"))
        self.transition_priority.setFixedWidth(46)
        transition_buttons.addWidget(self.transition_priority)
        transition_buttons.addStretch(1)
        add_transition = QPushButton("Add")
        add_transition.setObjectName("stateGraphAddTransition")
        add_transition.setToolTip("Add transition")
        add_transition.clicked.connect(self._request_add_transition)
        transition_buttons.addWidget(add_transition)
        apply_transition = QPushButton("Set")
        apply_transition.setObjectName("stateGraphApplyTransition")
        apply_transition.setToolTip("Apply transition changes")
        apply_transition.clicked.connect(self._request_edit_transition)
        transition_buttons.addWidget(apply_transition)
        delete_transition = QPushButton("Del")
        delete_transition.setObjectName("stateGraphDeleteTransition")
        delete_transition.setToolTip("Delete transition")
        delete_transition.clicked.connect(self._request_delete_transition)
        transition_buttons.addWidget(delete_transition)
        for button in (add_transition, apply_transition, delete_transition):
            button.setFixedSize(34, 24)
            button.setStyleSheet("padding: 1px 2px;")
        return transition_buttons

    def set_language_manager(self, manager: LanguageManager) -> None:
        self._language_manager = manager
        self.transition_frames.setSuffix(
            " 帧" if manager.language == LANGUAGE_CHINESE else " frames"
        )

    def _tr(self, text: str) -> str:
        return self._language_manager.translate(text) if self._language_manager else text

    def _duration_text(self, frames: int) -> str:
        if (
            self._language_manager is not None
            and self._language_manager.language == LANGUAGE_CHINESE
        ):
            return f"{frames} 帧"
        return f"{frames} frames"

    def _state_display_name(self, name: str) -> str:
        if (
            self._language_manager is not None
            and self._language_manager.language == LANGUAGE_CHINESE
        ):
            return {
                "Default": "默认阶段",
                "Intro": "登场",
                "Normal": "通常阶段",
                "Enrage": "强化阶段",
                "End": "结束",
                "Wave A": "第一波",
                "Wave B": "第二波",
            }.get(name, name)
        return name

    @staticmethod
    def _item_state_id(item: QTreeWidgetItem | None) -> str | None:
        if item is None:
            return None
        value = item.data(0, Qt.UserRole)
        return str(value) if value else None

    def set_document(
        self,
        document: SceneDocument,
        *,
        selected_state_id: str | None = None,
        active_state_path=(),
    ) -> None:
        self.document = document
        requested = selected_state_id or document.state_graph.initial_state_id
        if document.state_graph.find_state(requested) is None:
            requested = document.state_graph.initial_state_id
        self.selected_state_id = requested
        self.active_state_path = tuple(str(value) for value in active_state_path)
        self._rebuild()

    def clear_document(self) -> None:
        self.document = None
        self.selected_state_id = None
        self.active_state_path = ()
        self.context_name = "StageFlow"
        self.context_label.setText(self._tr(self.context_name))
        self.tree.clear()
        self.state_name.clear()
        self.transition_picker.clear()
        self.transition_target.clear()

    def set_active_state_path(self, state_ids) -> None:
        self.active_state_path = tuple(str(value) for value in state_ids)
        self._apply_active_style()

    def select_state(self, state_id: str, *, emit: bool = True) -> bool:
        iterator = self.tree.invisibleRootItem()

        def visit(parent: QTreeWidgetItem):
            for index in range(parent.childCount()):
                item = parent.child(index)
                if self._item_state_id(item) == state_id:
                    return item
                found = visit(item)
                if found is not None:
                    return found
            return None

        item = visit(iterator)
        if item is None:
            return False
        # App selection refreshes and rebuilds this tree. Keep the native item
        # alive until scrolling is complete, then emit the semantic selection.
        previous = self.tree.blockSignals(True)
        self.tree.setCurrentItem(item)
        self.tree.scrollToItem(item)
        self.tree.blockSignals(previous)
        self._set_selected_state(state_id, emit=emit)
        return True

    def _rebuild(self) -> None:
        self._rebuilding = True
        try:
            self.tree.clear()
            if self.document is None:
                return

            def add_graph(graph: StateGraphSpec, parent: QTreeWidgetItem | None) -> None:
                for state in sorted(graph.states, key=lambda item: (item.order, item.id)):
                    item = QTreeWidgetItem(
                        [
                            self._state_display_name(state.name),
                            self._duration_text(state.timeline_duration_frames),
                        ]
                    )
                    item.setData(0, Qt.UserRole, state.id)
                    item.setToolTip(0, state.id)
                    if parent is None:
                        self.tree.addTopLevelItem(item)
                    else:
                        parent.addChild(item)
                    if state.child_graph is not None:
                        add_graph(state.child_graph, item)

            add_graph(self.document.state_graph, None)
            self.tree.expandAll()
            self._apply_active_style()
            self.select_state(self.selected_state_id or "", emit=False)
            self._refresh_details()
        finally:
            self._rebuilding = False

    def _apply_active_style(self) -> None:
        root = self.tree.invisibleRootItem()

        def visit(parent: QTreeWidgetItem) -> None:
            for index in range(parent.childCount()):
                item = parent.child(index)
                active = self._item_state_id(item) in self.active_state_path
                font = QFont(item.font(0))
                font.setBold(active)
                item.setFont(0, font)
                item.setForeground(0, QColor("#8ee6a8") if active else QColor("#d6deeb"))
                visit(item)

        visit(root)

    def _current_item_changed(self, current, _previous) -> None:
        if self._rebuilding:
            return
        state_id = self._item_state_id(current)
        if state_id is not None:
            self._set_selected_state(state_id, emit=True)

    def _set_selected_state(self, state_id: str, *, emit: bool) -> None:
        if self.document is None:
            return
        state = self.document.state_graph.find_state(state_id)
        graph = self.document.state_graph.graph_for_state(state_id)
        if state is None or graph is None:
            return
        self.selected_state_id = state.id
        self.context_name = (
            "StageFlow" if graph is self.document.state_graph else "PhaseFlow"
        )
        self.context_label.setText(self._tr(self.context_name))
        self._refresh_details()
        if emit:
            self.stateSelected.emit(state.id)

    def _refresh_details(self) -> None:
        document = self.document
        state = (
            document.state_graph.find_state(self.selected_state_id or "")
            if document is not None
            else None
        )
        self.state_name.setText(state.name if state is not None else "")
        self.transition_target.blockSignals(True)
        self.transition_target.clear()
        if document is not None and state is not None:
            graph = document.state_graph.graph_for_state(state.id)
            if graph is not None:
                for sibling in sorted(
                    graph.states, key=lambda item: (item.order, item.id)
                ):
                    self.transition_target.addItem(
                        self._state_display_name(sibling.name), sibling.id
                    )
        self.transition_target.blockSignals(False)
        self.transition_picker.blockSignals(True)
        self.transition_picker.clear()
        if state is not None:
            for transition in state.transitions:
                self.transition_picker.addItem(transition.name, transition.id)
        self.transition_picker.blockSignals(False)
        self._transition_selection_changed()

    def _selected_state(self) -> StateSpec | None:
        if self.document is None:
            return None
        return self.document.state_graph.find_state(self.selected_state_id or "")

    def _request_add(self) -> None:
        if self.document is None:
            return
        graph = self.document.state_graph.graph_for_state(
            self.selected_state_id or ""
        ) or self.document.state_graph
        self.addStateRequested.emit(graph.id)

    def _request_rename(self) -> None:
        if self.selected_state_id is not None:
            self.renameStateRequested.emit(
                self.selected_state_id, self.state_name.text()
            )

    def _request_duplicate(self) -> None:
        if self.selected_state_id is not None:
            self.duplicateStateRequested.emit(self.selected_state_id)

    def _request_delete(self) -> None:
        if self.selected_state_id is not None:
            self.deleteStateRequested.emit(self.selected_state_id)

    def _request_move(self, delta: int) -> None:
        if self.selected_state_id is not None:
            self.moveStateRequested.emit(self.selected_state_id, int(delta))

    def _trigger_changed(self) -> None:
        self.transition_frames.setEnabled(
            self.transition_trigger.currentData() == "after"
        )

    def _request_add_transition(self) -> None:
        source = self.selected_state_id
        target = self.transition_target.currentData()
        trigger = str(self.transition_trigger.currentData() or "after")
        if source and target:
            self.addTransitionRequested.emit(
                source,
                str(target),
                trigger,
                self.transition_frames.value() if trigger == "after" else 0,
            )

    def _transition_selection_changed(self) -> None:
        state = self._selected_state()
        transition_id = self.transition_picker.currentData()
        transition = next(
            (
                item
                for item in state.transitions
                if item.id == transition_id
            ),
            None,
        ) if state is not None else None
        if transition is None:
            self.transition_priority.setValue(0)
            return
        target_index = self.transition_target.findData(transition.target_state_id)
        if target_index >= 0:
            self.transition_target.setCurrentIndex(target_index)
        trigger_index = self.transition_trigger.findData(transition.trigger)
        if trigger_index >= 0:
            self.transition_trigger.setCurrentIndex(trigger_index)
        if transition.after_frames is not None:
            self.transition_frames.setValue(transition.after_frames)
        self.transition_priority.setValue(transition.priority)
        self._trigger_changed()

    def _request_edit_transition(self) -> None:
        transition_id = self.transition_picker.currentData()
        target = self.transition_target.currentData()
        if not transition_id or not target:
            return
        trigger = str(self.transition_trigger.currentData() or "after")
        self.editTransitionRequested.emit(
            str(transition_id),
            {
                "name": self.transition_picker.currentText().strip(),
                "target_state_id": str(target),
                "trigger": trigger,
                "after_frames": (
                    self.transition_frames.value() if trigger == "after" else None
                ),
                "priority": self.transition_priority.value(),
            },
        )

    def _request_delete_transition(self) -> None:
        transition_id = self.transition_picker.currentData()
        if transition_id:
            self.deleteTransitionRequested.emit(str(transition_id))


__all__ = ["StateGraphEditor"]

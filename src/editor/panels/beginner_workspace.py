"""Task-first home and stage guide for beginning authors.

The widgets in this module are deliberately presentation-only.  They render a
read-only view of the active authoring document and emit stable signals; the
shell connects those signals to the existing services, typed intents and
formal preview session.
"""

from __future__ import annotations

from src.qt_compat.QtCore import Qt, pyqtSignal
from src.qt_compat.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.authoring.scene.document import SceneDocument
from ..i18n import LanguageManager


EXAMPLE_RESOURCES = (
    ("First Pattern", "res://game_content/examples/beginner_path/01_first_pattern.pystg.json"),
    ("Aimed Fan", "res://game_content/examples/beginner_path/02_aimed_fan.pystg.json"),
    ("Short Midstage", "res://game_content/examples/beginner_path/03_short_midstage.pystg.json"),
    ("Two-phase Boss Example", "res://game_content/examples/beginner_path/04_two_phase_boss.pystg.json"),
)


class BeginnerHomeWorkspace(QWidget):
    """The real application start page: ask for a goal before showing tools."""

    patternRequested = pyqtSignal()
    midstageRequested = pyqtSignal()
    bossRequested = pyqtSignal()
    openRequested = pyqtSignal()
    exampleRequested = pyqtSignal(str)
    fullWorkspaceRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("beginnerHomeWorkspace")
        self._language_manager: LanguageManager | None = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.addStretch(1)
        content = QFrame()
        content.setObjectName("beginnerHomeContent")
        content.setMaximumWidth(960)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Start creating")
        title.setObjectName("beginnerHomeTitle")
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        layout.addWidget(title)
        subtitle = QLabel(
            "Choose what you want to make. PySTG will create a runnable starting point."
        )
        subtitle.setObjectName("beginnerHomeSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 13px; color: #aeb7c8;")
        layout.addWidget(subtitle)

        task_grid = QGridLayout()
        task_grid.setHorizontalSpacing(12)
        task_grid.setVerticalSpacing(12)
        pattern = self._task_card(
            "Make a Pattern",
            "Start from a preset, adjust a few values, then preview it.",
            "beginnerCreatePattern",
            self.patternRequested.emit,
        )
        midstage = self._task_card(
            "Make a Midstage",
            "Begin with two editable waves and an all-clear continuation.",
            "beginnerCreateMidstage",
            self.midstageRequested.emit,
        )
        boss = self._task_card(
            "Make a Boss Battle",
            "Begin with an entrance and two editable Boss phases.",
            "beginnerCreateBoss",
            self.bossRequested.emit,
        )
        task_grid.addWidget(pattern, 0, 0)
        task_grid.addWidget(midstage, 0, 1)
        task_grid.addWidget(boss, 0, 2)
        task_grid.setColumnStretch(0, 1)
        task_grid.setColumnStretch(1, 1)
        task_grid.setColumnStretch(2, 1)
        layout.addLayout(task_grid)

        secondary = QHBoxLayout()
        open_button = QPushButton("Open Existing Work")
        open_button.setObjectName("beginnerOpenWork")
        open_button.clicked.connect(self.openRequested)
        secondary.addWidget(open_button)
        self.example_picker = QComboBox()
        self.example_picker.setObjectName("beginnerExamplePicker")
        for label, resource in EXAMPLE_RESOURCES:
            self.example_picker.addItem(label, resource)
        secondary.addWidget(self.example_picker, 1)
        example_button = QPushButton("Open Example")
        example_button.setObjectName("beginnerOpenExample")
        example_button.clicked.connect(self._open_example)
        secondary.addWidget(example_button)
        layout.addLayout(secondary)

        footer = QHBoxLayout()
        hint = QLabel(
            "You can switch to the full workspace at any time without changing your work."
        )
        hint.setObjectName("beginnerHomeFullHint")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8f9bad;")
        footer.addWidget(hint, 1)
        full = QPushButton("Use Full Workspace")
        full.setObjectName("beginnerUseFullWorkspace")
        full.clicked.connect(self.fullWorkspaceRequested)
        footer.addWidget(full)
        layout.addLayout(footer)
        layout.addStretch(1)

        outer.addWidget(content, 4)
        outer.addStretch(1)

    @staticmethod
    def _task_card(
        title: str,
        description: str,
        object_name: str,
        callback,
    ) -> QWidget:
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(
            "QFrame { background:#252a35; border:1px solid #3a4252; "
            "border-radius:6px; } QLabel { border:0; background:transparent; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        button = QPushButton(title)
        button.setObjectName(object_name)
        button.setMinimumHeight(42)
        button.setStyleSheet("font-size:14px; font-weight:600;")
        button.clicked.connect(callback)
        layout.addWidget(button)
        detail = QLabel(description)
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        detail.setMinimumHeight(42)
        layout.addWidget(detail)
        return card

    def set_language_manager(self, manager: LanguageManager) -> None:
        self._language_manager = manager

    def _open_example(self) -> None:
        resource = self.example_picker.currentData()
        if resource:
            self.exampleRequested.emit(str(resource))


class BeginnerTaskGuide(QWidget):
    """A phase-oriented view over one existing SceneDocument."""

    stateRequested = pyqtSignal(str)
    timelineRequested = pyqtSignal(str)
    previewRequested = pyqtSignal()
    homeRequested = pyqtSignal()
    fullWorkspaceRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("beginnerTaskGuide")
        self._language_manager: LanguageManager | None = None
        self._document: SceneDocument | None = None
        self._selected_state_id = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.title = QLabel("Beginner Guide")
        self.title.setObjectName("beginnerGuideTitle")
        self.title.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(self.title)
        self.summary = QLabel("Choose a phase, edit its timeline, then preview your work.")
        self.summary.setObjectName("beginnerGuideSummary")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.state_content = QWidget()
        self.state_layout = QVBoxLayout(self.state_content)
        self.state_layout.setContentsMargins(0, 0, 0, 0)
        self.state_layout.setSpacing(6)
        scroll = QScrollArea()
        scroll.setObjectName("beginnerStateScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(self.state_content)
        layout.addWidget(scroll, 1)

        self.current_hint = QLabel("")
        self.current_hint.setObjectName("beginnerCurrentTaskHint")
        self.current_hint.setWordWrap(True)
        self.current_hint.setStyleSheet(
            "background:#252a35; border:1px solid #3a4252; padding:8px;"
        )
        layout.addWidget(self.current_hint)
        timeline = QPushButton("Edit This Phase Timeline")
        timeline.setObjectName("beginnerEditTimeline")
        timeline.clicked.connect(self._open_timeline)
        layout.addWidget(timeline)
        preview = QPushButton("Preview This Work")
        preview.setObjectName("beginnerPreviewWork")
        preview.clicked.connect(self.previewRequested)
        layout.addWidget(preview)

        footer = QHBoxLayout()
        home = QPushButton("Back to Start")
        home.setObjectName("beginnerBackHome")
        home.clicked.connect(self.homeRequested)
        footer.addWidget(home)
        full = QPushButton("Full Workspace")
        full.setObjectName("beginnerGuideFullWorkspace")
        full.clicked.connect(self.fullWorkspaceRequested)
        footer.addWidget(full)
        layout.addLayout(footer)

    def set_language_manager(self, manager: LanguageManager) -> None:
        self._language_manager = manager

    def _tr(self, text: str) -> str:
        return (
            self._language_manager.translate(text)
            if self._language_manager is not None
            else text
        )

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def set_document(
        self,
        document: SceneDocument,
        *,
        selected_state_id: str | None = None,
    ) -> None:
        self._document = document
        kind = str((document.metadata.get("template") or {}).get("kind") or "")
        self.title.setText(
            self._tr("Boss Workflow")
            if kind == "two_phase_boss"
            else self._tr("Midstage Workflow")
            if kind == "midstage"
            else self._tr("Scene Workflow")
        )
        self._selected_state_id = str(
            selected_state_id or document.state_graph.initial_state_id
        )
        self._clear_layout(self.state_layout)
        for index, state in enumerate(document.state_graph.states):
            button = QPushButton(f"{index + 1}. {state.name}")
            button.setObjectName(f"beginnerPhase_{index}")
            button.setProperty("beginnerStateId", state.id)
            button.setCheckable(True)
            button.setChecked(state.id == self._selected_state_id)
            button.setStyleSheet("text-align:left; padding:8px;")
            button.clicked.connect(
                lambda checked=False, state_id=state.id: self._select_state(state_id)
            )
            self.state_layout.addWidget(button)
        self.state_layout.addStretch(1)
        self._update_hint(kind)

    def _select_state(self, state_id: str) -> None:
        self._selected_state_id = str(state_id)
        for button in self.findChildren(QPushButton):
            value = button.property("beginnerStateId")
            if value:
                button.setChecked(str(value) == self._selected_state_id)
        kind = str(
            ((self._document.metadata.get("template") if self._document else {}) or {}).get(
                "kind", ""
            )
        )
        self._update_hint(kind)
        self.stateRequested.emit(self._selected_state_id)

    def _selected_state(self):
        if self._document is None:
            return None
        return self._document.state_graph.find_state(self._selected_state_id)

    def _update_hint(self, kind: str) -> None:
        state = self._selected_state()
        if state is None:
            self.current_hint.setText(self._tr("Choose a phase to continue."))
            return
        if kind == "midstage":
            hint = "Adjust the enemy movement, main Pattern, and what happens after all enemies are defeated."
        elif kind == "two_phase_boss":
            hint = "Adjust this phase's movement, Pattern, background, and completion rule."
        else:
            hint = "Arrange this phase on the timeline, then preview it."
        self.current_hint.setText(f"{state.name}\n{self._tr(hint)}")

    def _open_timeline(self) -> None:
        if self._selected_state_id:
            self.timelineRequested.emit(self._selected_state_id)


__all__ = [
    "BeginnerHomeWorkspace",
    "BeginnerTaskGuide",
    "EXAMPLE_RESOURCES",
]

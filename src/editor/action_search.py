"""Contextual-search palette and the canvas gesture that opens it."""

from __future__ import annotations

from src.qt_compat.QtCore import Qt, pyqtSignal
from src.qt_compat.QtWidgets import (
    QDialog,
    QGraphicsView,
    QLabel,
    QLineEdit,
    QListWidget,
    QVBoxLayout,
)

from .action_catalog import ActionCatalog, ActionDescriptor, ActionQuery
from .i18n import LanguageManager


class SpaceTapSearchMixin:
    """Hold Space to hand-drag a canvas; tap it to ask for the search palette.

    The Scene viewport, the graph canvas and the timeline view all offer the
    same gesture, so the state machine that tells a pan apart from a tap lives
    here once.  A Qt signal cannot be declared on a plain mixin, so each canvas
    keeps its own ``actionSearchRequested`` and calls ``_init_space_tap()`` once
    its idle drag mode is configured -- that is the mode a release restores.

    Mix in before the view class.  A canvas with no other key handling inherits
    ``keyPressEvent`` as-is; one that handles further keys overrides it and
    short-circuits on ``_space_tap_press()`` first, so Space never falls through
    to a shortcut.
    """

    def _init_space_tap(self) -> None:
        self._space_pressed = False
        self._space_dragged = False
        self._drag_mode_before_space = self.dragMode()

    def _space_tap_press(self, event) -> bool:
        """Claim a Space press; True when the caller must stop handling it."""
        if event.key() != Qt.Key_Space or event.isAutoRepeat():
            return False
        self._space_pressed = True
        self._space_dragged = False
        self._drag_mode_before_space = self.dragMode()
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        event.accept()
        return True

    def keyPressEvent(self, event) -> None:
        if self._space_tap_press(event):
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._space_pressed and event.buttons() & Qt.LeftButton:
            self._space_dragged = True
        super().mouseMoveEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.setDragMode(self._drag_mode_before_space)
            should_search = self._space_pressed and not self._space_dragged
            self._space_pressed = False
            if should_search:
                self.actionSearchRequested.emit(None)
            event.accept()
            return
        super().keyReleaseEvent(event)


class ActionSearchDialog(QDialog):
    actionChosen = pyqtSignal(object)

    def __init__(
        self,
        catalog: ActionCatalog,
        query: ActionQuery,
        *,
        language_manager: LanguageManager | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("actionSearchDialog")
        self.language_manager = language_manager
        self.setWindowTitle(self._tr("Quick Add"))
        self.setModal(True)
        self.resize(520, 360)
        self.catalog = catalog
        self.query = query
        layout = QVBoxLayout(self)
        self.context_label = QLabel(self._context_text())
        self.context_label.setObjectName("actionSearchContext")
        layout.addWidget(self.context_label)
        self.search = QLineEdit(query.text)
        self.search.setObjectName("actionSearchInput")
        self.search.setPlaceholderText(self._tr("Search nodes, presets, tracks, or objects…"))
        layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.setObjectName("actionSearchResults")
        layout.addWidget(self.results, 1)
        self.empty_state = QLabel()
        self.empty_state.setObjectName("actionSearchEmptyState")
        self.empty_state.setWordWrap(True)
        layout.addWidget(self.empty_state)
        self.search.textChanged.connect(self._refresh)
        self.search.returnPressed.connect(self._accept_current)
        self.results.itemActivated.connect(lambda _item: self._accept_current())
        self._matches = ()
        self._refresh()
        self.search.setFocus(Qt.OtherFocusReason)

    def _tr(self, text: str) -> str:
        return self.language_manager.translate(text) if self.language_manager else text

    def _context_text(self) -> str:
        contexts = {
            "graph": "Node editor",
            "timeline": "Timeline",
            "scene": "Scene canvas",
            "inspector": "Inspector",
            "preset": "Preset library",
        }
        context = self._tr(contexts.get(self.query.context, self.query.context))
        if self.query.input_type:
            return self._tr("Available for: ") + self.query.input_type
        return context

    def _refresh(self) -> None:
        self._matches = self.catalog.search(
            ActionQuery(
                context=self.query.context,
                text=self.search.text(),
                input_type=self.query.input_type,
                parent_type=self.query.parent_type,
                timeline_kind=self.query.timeline_kind,
                required_capabilities=self.query.required_capabilities,
            )
        )
        self.results.clear()
        for match in self._matches:
            descriptor = match.descriptor
            suffix = (
                f"    {self._tr(descriptor.performance_hint)}"
                if descriptor.performance_hint
                else ""
            )
            self.results.addItem(f"{self._tr(descriptor.title)}{suffix}")
        if self.results.count():
            self.results.setCurrentRow(0)
            self.empty_state.clear()
            self.empty_state.hide()
        else:
            self.empty_state.setText(self._tr(
                "Nothing can be added here. Select a compatible object, track, or port and try again."
            ))
            self.empty_state.show()

    def selected_descriptor(self) -> ActionDescriptor | None:
        row = self.results.currentRow()
        return self._matches[row].descriptor if 0 <= row < len(self._matches) else None

    def _accept_current(self) -> None:
        descriptor = self.selected_descriptor()
        if descriptor is None:
            return
        self.actionChosen.emit(descriptor)
        self.accept()

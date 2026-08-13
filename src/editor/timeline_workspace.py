"""QGraphicsScene-based editable timeline for M4 Scene documents."""

from __future__ import annotations

from src.qt_compat.QtCore import QPointF, QRectF, Qt, pyqtSignal
from src.qt_compat.QtGui import QColor, QKeyEvent, QPainter, QPainterPath, QPen
from src.qt_compat.QtWidgets import (
    QComboBox,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .document import SceneDocument, TimelineClip, TimelineTrack
from .i18n import LanguageManager


RULER_HEIGHT = 28.0
TRACK_HEIGHT = 44.0
TRACK_HEADER_WIDTH = 138.0
CLIP_HEIGHT = 28.0
MIN_PIXELS_PER_FRAME = 0.04
MAX_PIXELS_PER_FRAME = 2.0

KIND_COLORS = {
    "Pattern": "#7058c7",
    "Movement": "#3686b8",
    "Audio": "#3f9a68",
    "Background": "#2f8797",
    "Event": "#b07a38",
    "Property": "#b34f7b",
    "ScriptEvent": "#a94a4a",
    "Reactive": "#d05a8d",
}


def _snap(value: int, step: int) -> int:
    step = max(1, int(step))
    return max(0, int(round(int(value) / step)) * step)


class TimelineClipItem(QGraphicsObject):
    geometryCommitted = pyqtSignal(str, int, int)
    keyframeGeometryCommitted = pyqtSignal(str, str, int)
    selectedRequested = pyqtSignal(str, str)

    def __init__(
        self,
        track: TimelineTrack,
        clip: TimelineClip,
        *,
        pixels_per_frame: float,
        snap_frames: int,
        row_y: float,
        display_name: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.track_id = track.id
        self.clip_id = clip.id
        self.clip_name = display_name or clip.name
        self.kind = clip.kind
        self.start_frame = clip.start_frame
        self.duration_frames = clip.duration_frames
        self.loop_count = clip.loop_count
        self.enabled = clip.enabled
        self.track_muted = track.muted
        self.activation = dict(clip.payload.get("activation") or {})
        self.reaction = dict(clip.payload.get("reaction") or {})
        self.reactive_overlay: dict = {}
        self.conflicts: tuple[str, ...] = ()
        self.active = False
        self.keyframe_frames = tuple(item.frame for item in clip.keyframes)
        self.pixels_per_frame = pixels_per_frame
        self.snap_frames = snap_frames
        self.row_y = row_y
        self._preview_duration = clip.duration_frames
        self._preview_start = clip.start_frame
        self._resize_edge: str | None = None
        self._drag_start = QPointF()
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.OpenHandCursor)
        self.setPos(
            TRACK_HEADER_WIDTH + clip.start_frame * pixels_per_frame,
            row_y + (TRACK_HEIGHT - CLIP_HEIGHT) / 2,
        )
        for keyframe in clip.keyframes:
            marker = TimelineKeyframeItem(
                clip.id,
                keyframe.id,
                keyframe.frame,
                clip.duration_frames,
                pixels_per_frame=pixels_per_frame,
                snap_frames=snap_frames,
                parent=self,
            )
            marker.geometryCommitted.connect(self.keyframeGeometryCommitted)
            marker.selectedRequested.connect(self.selectedRequested)

    def _width(self) -> float:
        return max(
            14.0,
            self._preview_duration * self.loop_count * self.pixels_per_frame,
        )

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, self._width(), CLIP_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        base = QColor(KIND_COLORS.get(self.kind, "#596579"))
        if not self.enabled or self.track_muted:
            base = QColor("#4b5360")
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(base.lighter(118) if self.isSelected() else base)
        outline = (
            QColor("#ffd166")
            if self.active
            else QColor("#dce7f5") if self.isSelected() else base.lighter(150)
        )
        painter.setPen(QPen(outline, 3 if self.active else 2 if self.isSelected() else 1))
        painter.drawRoundedRect(self.boundingRect().adjusted(1, 1, -1, -1), 4, 4)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            self.boundingRect().adjusted(7, 0, -10, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.clip_name,
        )
        if self.kind == "Reactive":
            activation_kind = str(self.activation.get("kind") or "event")
            badge = {
                "on_event": "event",
                "on_lifecycle": "life",
                "when_variable": "var",
                "at_frame": "frame",
            }.get(activation_kind, activation_kind)
            painter.setPen(QColor("#ffe6f1"))
            painter.drawText(
                self.boundingRect().adjusted(7, 0, -7, 0),
                Qt.AlignVCenter | Qt.AlignRight,
                badge,
            )
            if self.conflicts:
                painter.setBrush(QColor("#ff6b81"))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(self._width() - 10, 8), 3, 3)
        painter.fillRect(
            QRectF(max(0.0, self._width() - 6), 3, 3, CLIP_HEIGHT - 6),
            QColor("#e6edf7"),
        )
        painter.fillRect(QRectF(3, 3, 3, CLIP_HEIGHT - 6), QColor("#e6edf7"))
        single_loop_width = self._preview_duration * self.pixels_per_frame
        painter.setPen(QPen(base.lighter(175), 1, Qt.DashLine))
        for loop_index in range(1, self.loop_count):
            x = loop_index * single_loop_width
            painter.drawLine(QPointF(x, 3), QPointF(x, CLIP_HEIGHT - 3))
        painter.setBrush(QColor("#ffe08a"))
        painter.setPen(Qt.NoPen)
        # The first-loop markers are interactive child items. Repeated-loop
        # markers remain visual copies because they all edit the same local
        # keyframe.
        for loop_index in range(1, self.loop_count):
            offset = loop_index * single_loop_width
            for frame in self.keyframe_frames:
                x = offset + min(frame, self._preview_duration) * self.pixels_per_frame
                marker = QPainterPath()
                marker.moveTo(x, 3)
                marker.lineTo(x + 4, 7)
                marker.lineTo(x, 11)
                marker.lineTo(x - 4, 7)
                marker.closeSubpath()
                painter.drawPath(marker)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self._resize_edge is None:
            point = QPointF(value)
            # ItemPositionChange also fires for the initial setPos() call.  At
            # that point self.pos().y() is still zero, which used to pin every
            # clip to the ruler instead of its track row.
            fixed_y = self.row_y + (TRACK_HEIGHT - CLIP_HEIGHT) / 2
            return QPointF(max(TRACK_HEADER_WIDTH, point.x()), fixed_y)
        if change == QGraphicsItem.ItemSelectedHasChanged and bool(value):
            self.selectedRequested.emit(self.track_id, self.clip_id)
        return super().itemChange(change, value)

    def hoverMoveEvent(self, event) -> None:
        if event.pos().x() <= 10 or event.pos().x() >= self._width() - 10:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        self._preview_start = self.start_frame
        if event.pos().x() <= 10:
            self._resize_edge = "left"
        elif event.pos().x() >= self._width() - 10:
            self._resize_edge = "right"
        else:
            self._resize_edge = None
        self.setCursor(Qt.SizeHorCursor if self._resize_edge else Qt.ClosedHandCursor)
        if self._resize_edge:
            self.setSelected(True)
            self.selectedRequested.emit(self.track_id, self.clip_id)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resize_edge:
            original_end = self.start_frame + self.duration_frames * self.loop_count
            pointer_frame = _snap(
                int(round((event.scenePos().x() - TRACK_HEADER_WIDTH) / self.pixels_per_frame)),
                self.snap_frames,
            )
            if self._resize_edge == "left":
                latest_start = max(0, original_end - self.snap_frames * self.loop_count)
                start = min(pointer_frame, latest_start)
                span_frames = max(
                    self.snap_frames * self.loop_count,
                    original_end - start,
                )
                frames = max(
                    self.snap_frames,
                    _snap(int(round(span_frames / self.loop_count)), self.snap_frames),
                )
                start = max(0, original_end - frames * self.loop_count)
                if start != self._preview_start:
                    self._preview_start = start
                    self.setPos(
                        TRACK_HEADER_WIDTH + start * self.pixels_per_frame,
                        self.row_y + (TRACK_HEIGHT - CLIP_HEIGHT) / 2,
                    )
            else:
                span_frames = max(
                    self.snap_frames * self.loop_count,
                    pointer_frame - self.start_frame,
                )
                frames = max(
                    self.snap_frames,
                    _snap(int(round(span_frames / self.loop_count)), self.snap_frames),
                )
            if frames != self._preview_duration:
                self.prepareGeometryChange()
                self._preview_duration = frames
                self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._resize_edge:
            self._resize_edge = None
            self.setCursor(Qt.SizeHorCursor)
            self.geometryCommitted.emit(
                self.clip_id,
                self._preview_start,
                self._preview_duration,
            )
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.OpenHandCursor)
        start = _snap(
            int(round((self.x() - TRACK_HEADER_WIDTH) / self.pixels_per_frame)),
            self.snap_frames,
        )
        self.setPos(
            TRACK_HEADER_WIDTH + start * self.pixels_per_frame,
            self.row_y + (TRACK_HEIGHT - CLIP_HEIGHT) / 2,
        )
        if start != self.start_frame:
            self.geometryCommitted.emit(self.clip_id, start, self.duration_frames)


class TimelineKeyframeItem(QGraphicsObject):
    """Draggable first-loop keyframe marker backed by an undoable command."""

    geometryCommitted = pyqtSignal(str, str, int)
    selectedRequested = pyqtSignal(str, str)

    def __init__(
        self,
        clip_id: str,
        keyframe_id: str,
        frame: int,
        duration_frames: int,
        *,
        pixels_per_frame: float,
        snap_frames: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.clip_id = clip_id
        self.keyframe_id = keyframe_id
        self.frame = int(frame)
        self.duration_frames = int(duration_frames)
        self.pixels_per_frame = float(pixels_per_frame)
        self.snap_frames = int(snap_frames)
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.SizeHorCursor)
        self.setZValue(3)
        self.setPos(self.frame * self.pixels_per_frame, 7.0)

    def boundingRect(self) -> QRectF:
        return QRectF(-6.0, -6.0, 12.0, 12.0)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#fff1a8") if self.isSelected() else QColor("#ffe08a"))
        painter.setPen(QPen(QColor("#624c12"), 1))
        marker = QPainterPath()
        marker.moveTo(0, -5)
        marker.lineTo(5, 0)
        marker.lineTo(0, 5)
        marker.lineTo(-5, 0)
        marker.closeSubpath()
        painter.drawPath(marker)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            point = QPointF(value)
            maximum = self.duration_frames * self.pixels_per_frame
            return QPointF(min(maximum, max(0.0, point.x())), 7.0)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        parent = self.parentItem()
        if isinstance(parent, TimelineClipItem):
            self.selectedRequested.emit(parent.track_id, self.clip_id)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self._commit_position()

    def _commit_position(self) -> None:
        local_frame = min(
            self.duration_frames,
            _snap(int(round(self.x() / self.pixels_per_frame)), self.snap_frames),
        )
        self.setPos(local_frame * self.pixels_per_frame, 7.0)
        if local_frame != self.frame:
            self.geometryCommitted.emit(self.clip_id, self.keyframe_id, local_frame)


class TimelineGraphicsView(QGraphicsView):
    playheadRequested = pyqtSignal(int)
    trackSelected = pyqtSignal(str)
    nudgeRequested = pyqtSignal(str, int)
    deleteRequested = pyqtSignal()
    duplicateRequested = pyqtSignal()
    actionSearchRequested = pyqtSignal(object)
    zoomStepRequested = pyqtSignal(float)

    def __init__(self, parent=None) -> None:
        self.graphics_scene = QGraphicsScene(parent)
        super().__init__(self.graphics_scene, parent)
        self.setObjectName("timelineGraphicsView")
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setRenderHint(QPainter.Antialiasing)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.pixels_per_frame = 0.25
        self.snap_frames = 6
        self.track_ids: list[str] = []
        self._space_pressed = False
        self._space_dragged = False
        self._drag_mode_before_space = self.dragMode()

    def mousePressEvent(self, event) -> None:
        point = self.mapToScene(event.pos())
        item = self.itemAt(event.pos())
        clip_item = item
        while clip_item is not None and not isinstance(clip_item, TimelineClipItem):
            clip_item = clip_item.parentItem()
        if not isinstance(clip_item, TimelineClipItem):
            if point.y() >= RULER_HEIGHT:
                row = int((point.y() - RULER_HEIGHT) // TRACK_HEIGHT)
                if 0 <= row < len(self.track_ids):
                    self.trackSelected.emit(self.track_ids[row])
            if point.x() >= TRACK_HEADER_WIDTH:
                frame = _snap(
                    int(round((point.x() - TRACK_HEADER_WIDTH) / self.pixels_per_frame)),
                    self.snap_frames,
                )
                self.playheadRequested.emit(frame)
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoomStepRequested.emit(1.25 if delta > 0 else 1.0 / 1.25)
                event.accept()
                return
        if event.modifiers() & Qt.ShiftModifier:
            delta = event.angleDelta().y() or event.angleDelta().x()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta
            )
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pressed = True
            self._space_dragged = False
            self._drag_mode_before_space = self.dragMode()
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            event.accept()
            return
        selected = next(
            (
                item
                for item in self.graphics_scene.selectedItems()
                if isinstance(item, TimelineClipItem)
            ),
            None,
        )
        if event.key() == Qt.Key_Delete:
            self.deleteRequested.emit()
            event.accept()
            return
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_D:
            self.duplicateRequested.emit()
            event.accept()
            return
        if selected is not None and event.key() in {Qt.Key_Left, Qt.Key_Right}:
            delta = -self.snap_frames if event.key() == Qt.Key_Left else self.snap_frames
            self.nudgeRequested.emit(selected.clip_id, delta)
            event.accept()
            return
        if event.key() == Qt.Key_Home:
            self.playheadRequested.emit(0)
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._space_pressed and event.buttons() & Qt.LeftButton:
            self._space_dragged = True
        super().mouseMoveEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.setDragMode(self._drag_mode_before_space)
            should_search = self._space_pressed and not self._space_dragged
            self._space_pressed = False
            if should_search:
                self.actionSearchRequested.emit(None)
            event.accept()
            return
        super().keyReleaseEvent(event)


class TimelineEditor(QWidget):
    addTrackRequested = pyqtSignal(str)
    addClipRequested = pyqtSignal(str)
    clipGeometryRequested = pyqtSignal(str, int, int)
    duplicateClipRequested = pyqtSignal(str)
    deleteClipRequested = pyqtSignal(str)
    deleteTrackRequested = pyqtSignal(str)
    moveTrackRequested = pyqtSignal(str, int)
    muteTrackRequested = pyqtSignal(str, bool)
    addKeyframeRequested = pyqtSignal(str, int)
    deleteKeyframeRequested = pyqtSignal(str, int)
    keyframeGeometryRequested = pyqtSignal(str, str, int)
    trackSelected = pyqtSignal(str)
    clipSelected = pyqtSignal(str, str)
    playheadChanged = pyqtSignal(int)
    zoomChanged = pyqtSignal(float)
    reactiveNavigateRequested = pyqtSignal(str, str)
    actionSearchRequested = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("timelineEditor")
        self.document: SceneDocument | None = None
        self.state_id: str | None = None
        self.selected_track_id: str | None = None
        self.selected_clip_id: str | None = None
        self.playhead_frame = 0
        self.active_clip_ids: set[str] = set()
        self._reactive_overlay: dict = {}
        self.pixels_per_frame = 0.25
        self._language_manager: LanguageManager | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        track_toolbar = QHBoxLayout()
        self.kind_picker = QComboBox()
        self.kind_picker.setObjectName("timelineKindPicker")
        for kind in (
            "Pattern", "Movement", "Audio", "Background", "Event", "Property",
            "ScriptEvent", "Reactive",
        ):
            self.kind_picker.addItem(kind, kind)
        track_toolbar.addWidget(self.kind_picker)
        add_track = QPushButton("+ Track")
        add_track.setObjectName("timelineAddTrack")
        add_track.clicked.connect(
            lambda: self.addTrackRequested.emit(
                str(self.kind_picker.currentData() or self.kind_picker.currentText())
            )
        )
        track_toolbar.addWidget(add_track)
        delete_track = QPushButton("- Track")
        delete_track.setObjectName("timelineDeleteTrack")
        delete_track.clicked.connect(self._request_delete_track)
        track_toolbar.addWidget(delete_track)
        track_up = QPushButton("Track Up")
        track_up.setObjectName("timelineTrackUp")
        track_up.clicked.connect(lambda: self._request_move_track(-1))
        track_toolbar.addWidget(track_up)
        track_down = QPushButton("Track Down")
        track_down.setObjectName("timelineTrackDown")
        track_down.clicked.connect(lambda: self._request_move_track(1))
        track_toolbar.addWidget(track_down)
        mute_track = QPushButton("Mute")
        mute_track.setObjectName("timelineMuteTrack")
        mute_track.clicked.connect(self._request_toggle_mute)
        track_toolbar.addWidget(mute_track)
        track_toolbar.addStretch()
        self.playhead_label = QLabel("Frame 0")
        self.playhead_label.setObjectName("timelinePlayheadLabel")
        track_toolbar.addWidget(self.playhead_label)
        root.addLayout(track_toolbar)

        clip_toolbar = QHBoxLayout()
        add_clip = QPushButton("+ Clip")
        add_clip.setObjectName("timelineAddClip")
        add_clip.clicked.connect(self._request_add_clip)
        clip_toolbar.addWidget(add_clip)
        duplicate = QPushButton("Duplicate")
        duplicate.setObjectName("timelineDuplicateClip")
        duplicate.clicked.connect(self._request_duplicate)
        clip_toolbar.addWidget(duplicate)
        delete = QPushButton("Delete")
        delete.setObjectName("timelineDeleteClip")
        delete.clicked.connect(self._request_delete)
        clip_toolbar.addWidget(delete)
        add_key = QPushButton("+ Key")
        add_key.setObjectName("timelineAddKeyframe")
        add_key.clicked.connect(self._request_add_keyframe)
        clip_toolbar.addWidget(add_key)
        delete_key = QPushButton("- Key")
        delete_key.setObjectName("timelineDeleteKeyframe")
        delete_key.clicked.connect(self._request_delete_keyframe)
        clip_toolbar.addWidget(delete_key)
        clip_toolbar.addStretch()
        zoom_out = QPushButton("-")
        zoom_out.setObjectName("timelineZoomOut")
        zoom_out.clicked.connect(lambda: self.set_zoom(self.pixels_per_frame / 1.25))
        clip_toolbar.addWidget(zoom_out)
        zoom_in = QPushButton("+")
        zoom_in.setObjectName("timelineZoomIn")
        zoom_in.clicked.connect(lambda: self.set_zoom(self.pixels_per_frame * 1.25))
        clip_toolbar.addWidget(zoom_in)
        clip_toolbar.addWidget(QLabel("Snap"))
        self.snap_spin = QSpinBox()
        self.snap_spin.setObjectName("timelineSnapFrames")
        self.snap_spin.setRange(1, 600)
        self.snap_spin.setValue(6)
        self.snap_spin.setSuffix(" fr")
        self.snap_spin.valueChanged.connect(self._snap_changed)
        clip_toolbar.addWidget(self.snap_spin)
        root.addLayout(clip_toolbar)

        self.view = TimelineGraphicsView()
        self.view.playheadRequested.connect(self.set_playhead)
        self.view.trackSelected.connect(self._track_selected)
        self.view.nudgeRequested.connect(self._nudge_clip)
        self.view.deleteRequested.connect(self._request_delete)
        self.view.duplicateRequested.connect(self._request_duplicate)
        self.view.actionSearchRequested.connect(self.actionSearchRequested)
        self.view.zoomStepRequested.connect(
            lambda factor: self.set_zoom(self.pixels_per_frame * factor)
        )
        root.addWidget(self.view, 1)

    def set_language_manager(self, manager: LanguageManager) -> None:
        self._language_manager = manager

    def _tr(self, text: str) -> str:
        return (
            self._language_manager.translate(text)
            if self._language_manager is not None
            else text
        )

    def set_document(
        self,
        document: SceneDocument,
        *,
        state_id: str | None = None,
        selected_clip_id: str | None = None,
        zoom: float | None = None,
    ) -> None:
        self.document = document
        selected_state_id = state_id or document.state_graph.initial_state_id
        if document.state_graph.find_state(selected_state_id) is None:
            selected_state_id = document.state_graph.initial_state_id
        self.state_id = selected_state_id
        self.selected_clip_id = selected_clip_id
        if zoom is not None:
            self.pixels_per_frame = min(
                MAX_PIXELS_PER_FRAME,
                max(MIN_PIXELS_PER_FRAME, float(zoom)),
            )
        self._rebuild()

    def clear_document(self) -> None:
        self.document = None
        self.state_id = None
        self.selected_track_id = None
        self.selected_clip_id = None
        self.playhead_frame = 0
        self._rebuild()

    def set_zoom(self, value: float) -> None:
        value = min(MAX_PIXELS_PER_FRAME, max(MIN_PIXELS_PER_FRAME, float(value)))
        if abs(value - self.pixels_per_frame) < 1e-9:
            return
        self.pixels_per_frame = value
        self.zoomChanged.emit(value)
        self._rebuild()

    def _snap_changed(self, value: int) -> None:
        self.view.snap_frames = int(value)
        self._rebuild()

    def _track_selected(self, track_id: str) -> None:
        self.selected_track_id = track_id
        self.selected_clip_id = None
        self.view.graphics_scene.clearSelection()
        self.trackSelected.emit(track_id)

    def _clip_selected(self, track_id: str, clip_id: str) -> None:
        self.selected_track_id = track_id
        self.selected_clip_id = clip_id
        self.clipSelected.emit(track_id, clip_id)

    def _request_add_clip(self) -> None:
        if self.selected_track_id:
            self.addClipRequested.emit(self.selected_track_id)

    def _request_duplicate(self) -> None:
        if self.selected_clip_id:
            self.duplicateClipRequested.emit(self.selected_clip_id)

    def _request_delete(self) -> None:
        if self.selected_clip_id:
            self.deleteClipRequested.emit(self.selected_clip_id)

    def _request_delete_track(self) -> None:
        if self.selected_track_id:
            self.deleteTrackRequested.emit(self.selected_track_id)

    def _request_move_track(self, delta: int) -> None:
        if self.selected_track_id:
            self.moveTrackRequested.emit(self.selected_track_id, int(delta))

    def _request_toggle_mute(self) -> None:
        if self.document is None or not self.selected_track_id:
            return
        track = next(
            (item for item in self.tracks if item.id == self.selected_track_id),
            None,
        )
        if track is not None:
            self.muteTrackRequested.emit(track.id, not track.muted)

    def _request_add_keyframe(self) -> None:
        if self.selected_clip_id:
            self.addKeyframeRequested.emit(self.selected_clip_id, self.playhead_frame)

    def _request_delete_keyframe(self) -> None:
        if self.selected_clip_id:
            self.deleteKeyframeRequested.emit(self.selected_clip_id, self.playhead_frame)

    def set_active_clips(self, clip_ids) -> None:
        self.active_clip_ids = {str(value) for value in clip_ids}
        for item in self.view.graphics_scene.items():
            if isinstance(item, TimelineClipItem):
                item.active = item.clip_id in self.active_clip_ids
                item.update()

    def set_reactive_overlay(self, overlay: dict | None) -> None:
        """Apply read-only runtime reaction state to visible clip items."""

        payload = dict(overlay or {})
        active = {
            str(item.get("clip_id"))
            for item in payload.get("active_instances", [])
            if isinstance(item, dict) and item.get("clip_id")
        }
        diagnostics = payload.get("diagnostics", [])
        by_clip: dict[str, list[str]] = {}
        for item in diagnostics:
            if isinstance(item, dict) and item.get("clip_id"):
                by_clip.setdefault(str(item["clip_id"]), []).append(str(item.get("reason") or item.get("kind") or "diagnostic"))
        self._reactive_overlay = payload
        for item in self.view.graphics_scene.items():
            if not isinstance(item, TimelineClipItem):
                continue
            item.reactive_overlay = payload
            item.active = item.clip_id in self.active_clip_ids or item.clip_id in active
            item.conflicts = tuple(by_clip.get(item.clip_id, ()))
            item.update()

    def navigate_reactive_clip(self, clip_id: str) -> None:
        if self.document is None:
            return
        result = next(
            (
                (track, clip)
                for track in self.tracks
                for clip in track.clips
                if clip.id == clip_id and clip.kind == "Reactive"
            ),
            None,
        )
        if result is not None:
            self.reactiveNavigateRequested.emit("reaction", clip_id)

    def _nudge_clip(self, clip_id: str, delta: int) -> None:
        if self.document is None:
            return
        for track in self.tracks:
            for clip in track.clips:
                if clip.id == clip_id:
                    self.clipGeometryRequested.emit(
                        clip.id,
                        max(0, clip.start_frame + delta),
                        clip.duration_frames,
                    )
                    return

    def set_playhead(self, frame: int, *, emit: bool = True) -> None:
        self.playhead_frame = max(0, int(frame))
        self.playhead_label.setText(self._tr(f"Frame {self.playhead_frame}"))
        self._position_playhead()
        if emit:
            self.playheadChanged.emit(self.playhead_frame)

    def _position_playhead(self) -> None:
        item = getattr(self, "_playhead_item", None)
        if item is not None:
            x = TRACK_HEADER_WIDTH + self.playhead_frame * self.pixels_per_frame
            item.setLine(x, 0, x, self.view.graphics_scene.sceneRect().height())

    @property
    def tracks(self) -> list[TimelineTrack]:
        if self.document is None:
            return []
        state = self.document.state_graph.find_state(self.state_id or "")
        return state.tracks if state is not None else self.document.tracks

    def _rebuild(self) -> None:
        scene = self.view.graphics_scene
        scene.clear()
        self.view.pixels_per_frame = self.pixels_per_frame
        self.view.snap_frames = self.snap_spin.value()
        document = self.document
        tracks = self.tracks
        self.view.track_ids = [track.id for track in tracks]
        state = (
            document.state_graph.find_state(self.state_id or "")
            if document is not None
            else None
        )
        duration = max(state.timeline_duration_frames if state is not None else 0, 3600)
        width = TRACK_HEADER_WIDTH + duration * self.pixels_per_frame + 120
        height = max(120.0, RULER_HEIGHT + max(1, len(tracks)) * TRACK_HEIGHT)
        scene.setSceneRect(0, 0, width, height)
        scene.setBackgroundBrush(QColor("#111722"))

        scene.addRect(0, 0, width, RULER_HEIGHT, QPen(QColor("#44516a")), QColor("#182131"))
        tick_rate = document.timebase.tick_rate if document is not None else 60
        minor = max(1, tick_rate)
        for frame in range(0, duration + minor, minor):
            x = TRACK_HEADER_WIDTH + frame * self.pixels_per_frame
            major = frame % (tick_rate * 5) == 0
            scene.addLine(
                x,
                0,
                x,
                RULER_HEIGHT if major else RULER_HEIGHT * 0.55,
                QPen(QColor("#8292ad") if major else QColor("#536078")),
            )
            if major:
                label = QGraphicsSimpleTextItem(f"{frame / tick_rate:g}s")
                label.setBrush(QColor("#cbd6e7"))
                label.setPos(x + 3, 3)
                scene.addItem(label)

        if not tracks:
            empty = QGraphicsSimpleTextItem(
                self._tr("No tracks. Choose a kind and add the first track.")
            )
            empty.setBrush(QColor("#9aa9bd"))
            empty.setPos(18, RULER_HEIGHT + 22)
            scene.addItem(empty)

        for row, track in enumerate(tracks):
            y = RULER_HEIGHT + row * TRACK_HEIGHT
            scene.addRect(
                0,
                y,
                width,
                TRACK_HEIGHT,
                QPen(QColor("#2f3b50")),
                QColor("#151d2a") if row % 2 == 0 else QColor("#121a26"),
            )
            scene.addRect(
                0,
                y,
                TRACK_HEADER_WIDTH,
                TRACK_HEIGHT,
                QPen(QColor("#44516a")),
                QColor("#1d2737"),
            )
            label = QGraphicsSimpleTextItem(
                f"{self._tr(track.name)}\n{self._tr(track.kind)}"
            )
            label.setBrush(QColor("#d7e1ee") if not track.muted else QColor("#778397"))
            label.setPos(8, y + 5)
            scene.addItem(label)
            for clip in track.clips:
                item = TimelineClipItem(
                    track,
                    clip,
                    pixels_per_frame=self.pixels_per_frame,
                    snap_frames=self.snap_spin.value(),
                    row_y=y,
                    display_name=self._tr(clip.name),
                )
                item.geometryCommitted.connect(self.clipGeometryRequested)
                item.keyframeGeometryCommitted.connect(self.keyframeGeometryRequested)
                item.selectedRequested.connect(self._clip_selected)
                scene.addItem(item)
                item.active = clip.id in self.active_clip_ids
                if clip.id == self.selected_clip_id:
                    item.setSelected(True)
                    self.selected_track_id = track.id

        self._playhead_item = scene.addLine(
            TRACK_HEADER_WIDTH,
            0,
            TRACK_HEADER_WIDTH,
            height,
            QPen(QColor("#ff6d7a"), 2),
        )
        self._playhead_item.setZValue(20)
        self._position_playhead()
        if self._reactive_overlay:
            self.set_reactive_overlay(self._reactive_overlay)

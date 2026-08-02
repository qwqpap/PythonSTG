"""QGraphicsScene-based editable timeline for M4 Scene documents."""

from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QKeyEvent, QPainter, QPen
from PyQt5.QtWidgets import (
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
    "Event": "#b07a38",
    "Property": "#b34f7b",
    "ScriptEvent": "#a94a4a",
}


def _snap(value: int, step: int) -> int:
    step = max(1, int(step))
    return max(0, int(round(int(value) / step)) * step)


class TimelineClipItem(QGraphicsObject):
    geometryCommitted = pyqtSignal(str, int, int)
    selectedRequested = pyqtSignal(str, str)

    def __init__(
        self,
        track: TimelineTrack,
        clip: TimelineClip,
        *,
        pixels_per_frame: float,
        snap_frames: int,
        row_y: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.track_id = track.id
        self.clip_id = clip.id
        self.clip_name = clip.name
        self.kind = clip.kind
        self.start_frame = clip.start_frame
        self.duration_frames = clip.duration_frames
        self.pixels_per_frame = pixels_per_frame
        self.snap_frames = snap_frames
        self.row_y = row_y
        self._preview_duration = clip.duration_frames
        self._resizing = False
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

    def _width(self) -> float:
        return max(14.0, self._preview_duration * self.pixels_per_frame)

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, self._width(), CLIP_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        base = QColor(KIND_COLORS.get(self.kind, "#596579"))
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(base.lighter(118) if self.isSelected() else base)
        painter.setPen(QPen(QColor("#dce7f5") if self.isSelected() else base.lighter(150), 2 if self.isSelected() else 1))
        painter.drawRoundedRect(self.boundingRect().adjusted(1, 1, -1, -1), 4, 4)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            self.boundingRect().adjusted(7, 0, -10, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.clip_name,
        )
        painter.fillRect(
            QRectF(max(0.0, self._width() - 6), 3, 3, CLIP_HEIGHT - 6),
            QColor("#e6edf7"),
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and not self._resizing:
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
        if event.pos().x() >= self._width() - 9:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        self._resizing = event.pos().x() >= self._width() - 9
        self.setCursor(Qt.SizeHorCursor if self._resizing else Qt.ClosedHandCursor)
        if self._resizing:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resizing:
            frames = max(1, int(round(event.pos().x() / self.pixels_per_frame)))
            frames = max(self.snap_frames, _snap(frames, self.snap_frames))
            if frames != self._preview_duration:
                self.prepareGeometryChange()
                self._preview_duration = frames
                self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._resizing:
            self._resizing = False
            self.setCursor(Qt.SizeHorCursor)
            self.geometryCommitted.emit(
                self.clip_id,
                self.start_frame,
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


class TimelineGraphicsView(QGraphicsView):
    playheadRequested = pyqtSignal(int)
    trackSelected = pyqtSignal(str)
    nudgeRequested = pyqtSignal(str, int)
    deleteRequested = pyqtSignal()
    duplicateRequested = pyqtSignal()

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

    def mousePressEvent(self, event) -> None:
        point = self.mapToScene(event.pos())
        item = self.itemAt(event.pos())
        if not isinstance(item, TimelineClipItem):
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

    def keyPressEvent(self, event: QKeyEvent) -> None:
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


class TimelineEditor(QWidget):
    addTrackRequested = pyqtSignal(str)
    addClipRequested = pyqtSignal(str)
    clipGeometryRequested = pyqtSignal(str, int, int)
    duplicateClipRequested = pyqtSignal(str)
    deleteClipRequested = pyqtSignal(str)
    clipSelected = pyqtSignal(str, str)
    playheadChanged = pyqtSignal(int)
    zoomChanged = pyqtSignal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("timelineEditor")
        self.document: SceneDocument | None = None
        self.selected_track_id: str | None = None
        self.selected_clip_id: str | None = None
        self.playhead_frame = 0
        self.pixels_per_frame = 0.25
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        toolbar = QHBoxLayout()
        self.kind_picker = QComboBox()
        self.kind_picker.setObjectName("timelineKindPicker")
        self.kind_picker.addItems(
            ["Pattern", "Movement", "Audio", "Event", "Property", "ScriptEvent"]
        )
        toolbar.addWidget(self.kind_picker)
        add_track = QPushButton("+ Track")
        add_track.setObjectName("timelineAddTrack")
        add_track.clicked.connect(
            lambda: self.addTrackRequested.emit(self.kind_picker.currentText())
        )
        toolbar.addWidget(add_track)
        add_clip = QPushButton("+ Clip")
        add_clip.setObjectName("timelineAddClip")
        add_clip.clicked.connect(self._request_add_clip)
        toolbar.addWidget(add_clip)
        duplicate = QPushButton("Duplicate")
        duplicate.setObjectName("timelineDuplicateClip")
        duplicate.clicked.connect(self._request_duplicate)
        toolbar.addWidget(duplicate)
        delete = QPushButton("Delete")
        delete.setObjectName("timelineDeleteClip")
        delete.clicked.connect(self._request_delete)
        toolbar.addWidget(delete)
        toolbar.addSpacing(12)
        zoom_out = QPushButton("−")
        zoom_out.setObjectName("timelineZoomOut")
        zoom_out.clicked.connect(lambda: self.set_zoom(self.pixels_per_frame / 1.25))
        toolbar.addWidget(zoom_out)
        zoom_in = QPushButton("+")
        zoom_in.setObjectName("timelineZoomIn")
        zoom_in.clicked.connect(lambda: self.set_zoom(self.pixels_per_frame * 1.25))
        toolbar.addWidget(zoom_in)
        toolbar.addWidget(QLabel("Snap"))
        self.snap_spin = QSpinBox()
        self.snap_spin.setObjectName("timelineSnapFrames")
        self.snap_spin.setRange(1, 600)
        self.snap_spin.setValue(6)
        self.snap_spin.setSuffix(" fr")
        self.snap_spin.valueChanged.connect(self._snap_changed)
        toolbar.addWidget(self.snap_spin)
        toolbar.addStretch()
        self.playhead_label = QLabel("Frame 0")
        self.playhead_label.setObjectName("timelinePlayheadLabel")
        toolbar.addWidget(self.playhead_label)
        root.addLayout(toolbar)

        self.view = TimelineGraphicsView()
        self.view.playheadRequested.connect(self.set_playhead)
        self.view.trackSelected.connect(self._track_selected)
        self.view.nudgeRequested.connect(self._nudge_clip)
        self.view.deleteRequested.connect(self._request_delete)
        self.view.duplicateRequested.connect(self._request_duplicate)
        root.addWidget(self.view, 1)

    def set_document(
        self,
        document: SceneDocument,
        *,
        selected_clip_id: str | None = None,
        zoom: float | None = None,
    ) -> None:
        self.document = document
        self.selected_clip_id = selected_clip_id
        if zoom is not None:
            self.pixels_per_frame = min(
                MAX_PIXELS_PER_FRAME,
                max(MIN_PIXELS_PER_FRAME, float(zoom)),
            )
        self._rebuild()

    def clear_document(self) -> None:
        self.document = None
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

    def _nudge_clip(self, clip_id: str, delta: int) -> None:
        if self.document is None:
            return
        for track in self.document.tracks:
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
        self.playhead_label.setText(f"Frame {self.playhead_frame}")
        self._position_playhead()
        if emit:
            self.playheadChanged.emit(self.playhead_frame)

    def _position_playhead(self) -> None:
        item = getattr(self, "_playhead_item", None)
        if item is not None:
            x = TRACK_HEADER_WIDTH + self.playhead_frame * self.pixels_per_frame
            item.setLine(x, 0, x, self.view.graphics_scene.sceneRect().height())

    def _rebuild(self) -> None:
        scene = self.view.graphics_scene
        scene.clear()
        self.view.pixels_per_frame = self.pixels_per_frame
        self.view.snap_frames = self.snap_spin.value()
        document = self.document
        tracks = document.tracks if document is not None else []
        self.view.track_ids = [track.id for track in tracks]
        duration = max(document.duration_frames if document is not None else 0, 3600)
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
            empty = QGraphicsSimpleTextItem("No tracks. Choose a kind and add the first track.")
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
            label = QGraphicsSimpleTextItem(f"{track.name}\n{track.kind}")
            label.setBrush(QColor("#d7e1ee") if not track.muted else QColor("#778397"))
            label.setPos(8, y + 5)
            scene.addItem(label)
            if track.muted:
                continue
            for clip in track.clips:
                item = TimelineClipItem(
                    track,
                    clip,
                    pixels_per_frame=self.pixels_per_frame,
                    snap_frames=self.snap_spin.value(),
                    row_y=y,
                )
                item.geometryCommitted.connect(self.clipGeometryRequested)
                item.selectedRequested.connect(self._clip_selected)
                scene.addItem(item)
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

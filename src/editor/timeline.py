"""Qt view for the disposable static Timeline projection and runtime Trace."""

from __future__ import annotations

from dataclasses import dataclass

from src.authoring.program import ProgramError, find_node
from src.authoring.timeline import (
    TimelineInterval,
    TimelineProjection,
    Unknown,
    overlay_trace,
    project_timeline,
)
from src.qt_compat.QtCore import QRectF, Qt, Signal
from src.qt_compat.QtGui import QColor, QMouseEvent, QPainter, QPen
from src.qt_compat.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .session import EditorSession


_ORIGIN_X = 160
_RULER_HEIGHT = 24
_LANE_HEIGHT = 32
_LANE_GAP = 6


@dataclass(frozen=True)
class _PaintedInterval:
    rect: QRectF
    interval: TimelineInterval


class TimelineCanvas(QWidget):
    """Small lane renderer with only the three contract-approved drag edits."""

    interval_clicked = Signal(str)
    edit_requested = Signal(str, int)
    seek_requested = Signal(int)

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.projection: TimelineProjection | None = None
        self.pixels_per_frame = 0.5
        self.cursor_frame = 0
        self.selected_uid: str | None = None
        self.scrub_frame: int | None = None
        self._painted: list[_PaintedInterval] = []
        self._drag: tuple[str, str, float, QRectF] | None = None
        self._scrubbing = False
        self.setObjectName("timeline_canvas")
        self.setMouseTracking(True)
        self.setMinimumHeight(90)

    def set_projection(
        self,
        projection: TimelineProjection | None,
        *,
        selected_uid: str | None,
        cursor_frame: int,
    ) -> None:
        self.projection = projection
        self.selected_uid = selected_uid
        self.cursor_frame = max(0, int(cursor_frame))
        lanes = _lanes(projection)
        height = _RULER_HEIGHT + max(1, len(lanes)) * (_LANE_HEIGHT + _LANE_GAP) + 12
        maximum = _maximum_known_frame(projection)
        self.setMinimumSize(max(720, _ORIGIN_X + int(maximum * self.pixels_per_frame) + 180), height)
        self.updateGeometry()
        self.update()

    def set_cursor_frame(self, frame: int) -> None:
        self.cursor_frame = max(0, int(frame))
        self.update()

    def zoom(self, factor: float) -> None:
        self.pixels_per_frame = min(4.0, max(0.1, self.pixels_per_frame * factor))
        self.set_projection(
            self.projection,
            selected_uid=self.selected_uid,
            cursor_frame=self.cursor_frame,
        )

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e1f22"))
        self._painted.clear()
        projection = self.projection
        if projection is None or not projection.intervals:
            painter.setPen(QColor("#8b8d94"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "选择逻辑单元以查看代码时间投影")
            return

        intervals = projection.all_intervals()
        lanes = _lanes(projection)
        lane_index = {lane: index for index, lane in enumerate(lanes)}
        maximum = max(60, _maximum_known_frame(projection))
        painter.fillRect(0, 0, self.width(), _RULER_HEIGHT, QColor("#25272b"))
        painter.setPen(QColor("#858992"))
        step = _ruler_step(self.pixels_per_frame)
        for frame in range(0, maximum + step, step):
            x = _ORIGIN_X + frame * self.pixels_per_frame
            painter.drawLine(int(x), _RULER_HEIGHT - 6, int(x), _RULER_HEIGHT)
            painter.drawText(int(x + 3), 15, f"{frame}f")

        colors = {
            "static": QColor("#356a9a"),
            "branch": QColor("#8559a5"),
            "parallel": QColor("#347f72"),
            "spawned": QColor("#9a6b32"),
            "template": QColor("#a24f72"),
            "dynamic": QColor("#5f6269"),
        }
        dynamic_offset = _ORIGIN_X + maximum * self.pixels_per_frame + 24
        for lane, index in lane_index.items():
            y = _RULER_HEIGHT + index * (_LANE_HEIGHT + _LANE_GAP)
            painter.setPen(QColor("#c8cad0"))
            painter.drawText(6, y + 21, _lane_label(lane))
            painter.fillRect(_ORIGIN_X, y, self.width() - _ORIGIN_X, _LANE_HEIGHT, QColor("#292b30"))

        for interval in intervals:
            y = _RULER_HEIGHT + lane_index[interval.lane] * (_LANE_HEIGHT + _LANE_GAP)
            if isinstance(interval.start, Unknown):
                x = dynamic_offset
            else:
                x = _ORIGIN_X + interval.start * self.pixels_per_frame
            if isinstance(interval.start, int) and isinstance(interval.end, int):
                width = max(8.0, (interval.end - interval.start) * self.pixels_per_frame)
            else:
                width = 90.0
            rect = QRectF(x, y + 2, width, _LANE_HEIGHT - 4)
            self._painted.append(_PaintedInterval(rect, interval))
            color = colors[interval.kind]
            if interval.uid == self.selected_uid:
                color = QColor("#d5a928")
            painter.fillRect(rect, color)
            pen = QPen(QColor("#f4f4f4"), 2 if interval.editable != "none" else 1)
            if interval.kind == "dynamic":
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            painter.drawText(
                rect.adjusted(4, 0, -3, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                interval.label,
            )

        cursor_x = _ORIGIN_X + self.cursor_frame * self.pixels_per_frame
        painter.setPen(QPen(QColor("#ff4b4b"), 2))
        painter.drawLine(int(cursor_x), 0, int(cursor_x), self.height())
        if self.scrub_frame is not None:
            scrub_x = _ORIGIN_X + self.scrub_frame * self.pixels_per_frame
            painter.setPen(QPen(QColor("#f4c95d"), 2, Qt.PenStyle.DashLine))
            painter.drawLine(int(scrub_x), 0, int(scrub_x), self.height())
            painter.setPen(QColor("#f4c95d"))
            painter.drawText(
                QRectF(scrub_x + 4, 2, 90, _RULER_HEIGHT - 4),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                f"→ {self.scrub_frame}f",
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        position = event.position()
        if position.y() <= _RULER_HEIGHT and position.x() >= _ORIGIN_X:
            frame = max(0, round((position.x() - _ORIGIN_X) / self.pixels_per_frame))
            self.scrub_frame = frame
            self._scrubbing = True
            self.update()
            return
        painted = self._at(position.x(), position.y())
        if painted is None:
            if position.x() >= _ORIGIN_X:
                frame = max(0, round((position.x() - _ORIGIN_X) / self.pixels_per_frame))
                self.seek_requested.emit(frame)
            return
        uid = painted.interval.uid
        try:
            self.session.select_node(uid)
        except ProgramError:
            return
        self.interval_clicked.emit(uid)
        self.selected_uid = uid
        if painted.interval.editable != "none":
            self._drag = (
                uid,
                painted.interval.editable,
                event.position().x(),
                painted.rect,
            )
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._scrubbing:
            frame = max(
                0, round((event.position().x() - _ORIGIN_X) / self.pixels_per_frame)
            )
            if frame != self.scrub_frame:
                self.scrub_frame = frame
                self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._scrubbing and event.button() == Qt.MouseButton.LeftButton:
            frame = self.scrub_frame
            self._scrubbing = False
            self.scrub_frame = None
            self.update()
            if frame is not None:
                self.seek_requested.emit(frame)
            return
        drag = self._drag
        self._drag = None
        if drag is None or event.button() != Qt.MouseButton.LeftButton:
            return
        uid, mode, press_x, rect = drag
        release_x = event.position().x()
        if abs(release_x - press_x) < 3:
            return
        if mode == "at":
            value = round((release_x - _ORIGIN_X) / self.pixels_per_frame)
        else:
            value = round((release_x - rect.left()) / self.pixels_per_frame)
        self.edit_requested.emit(uid, max(0, value))

    def _at(self, x: float, y: float) -> _PaintedInterval | None:
        return next(
            (item for item in reversed(self._painted) if item.rect.contains(x, y)),
            None,
        )


class TimelinePanel(QWidget):
    """Permanent bottom panel owned by the window's one EditorSession."""

    seek_requested = Signal(int)
    pause_requested = Signal()
    resume_requested = Signal()

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("timeline_panel")
        self.session = session
        self.projection: TimelineProjection | None = None
        self._seek_target: int | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        toolbar = QWidget(self)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(6, 2, 6, 2)
        self.status_label = QLabel("时间线 · 代码投影", toolbar)
        self.status_label.setObjectName("timeline_status")
        toolbar_layout.addWidget(self.status_label)
        self.seek_progress = QProgressBar(toolbar)
        self.seek_progress.setObjectName("timeline_seek_progress")
        self.seek_progress.setRange(0, 100)
        self.seek_progress.setValue(0)
        self.seek_progress.setFormat("快进到目标帧 %p%")
        self.seek_progress.setVisible(False)
        self.seek_progress.setMaximumWidth(220)
        toolbar_layout.addWidget(self.seek_progress)
        toolbar_layout.addStretch(1)
        self.pause_button = QPushButton("暂停", toolbar)
        self.pause_button.setObjectName("timeline_pause")
        self.pause_button.clicked.connect(self.pause_requested)
        toolbar_layout.addWidget(self.pause_button)
        self.resume_button = QPushButton("继续", toolbar)
        self.resume_button.setObjectName("timeline_resume")
        self.resume_button.clicked.connect(self.resume_requested)
        toolbar_layout.addWidget(self.resume_button)
        zoom_out = QPushButton("−", toolbar)
        zoom_out.setObjectName("timeline_zoom_out")
        zoom_out.clicked.connect(lambda: self.canvas.zoom(1 / 1.5))
        toolbar_layout.addWidget(zoom_out)
        zoom_in = QPushButton("+", toolbar)
        zoom_in.setObjectName("timeline_zoom_in")
        zoom_in.clicked.connect(lambda: self.canvas.zoom(1.5))
        toolbar_layout.addWidget(zoom_in)
        layout.addWidget(toolbar)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("timeline_scroll")
        self.scroll.setWidgetResizable(True)
        self.canvas = TimelineCanvas(session, self.scroll)
        self.canvas.edit_requested.connect(self.edit_interval)
        self.canvas.seek_requested.connect(self.seek_requested)
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll)

        session.project_changed.connect(self.refresh)
        session.program_changed.connect(self.refresh)
        session.selection_changed.connect(self.refresh)
        session.trace_changed.connect(self.refresh)
        session.preview_changed.connect(self._preview_state_changed)
        self.refresh()

    def refresh(self) -> None:
        unit = self.session.current_unit
        if unit is None or not self.session.is_open:
            self.projection = None
        else:
            root = self.session.project_context.root if self.session.project_context else None
            self.projection = project_timeline(
                self.session.program,
                unit,
                project_root=root,
            )
            if self.session.trace_run_id:
                self.projection = overlay_trace(
                    self.projection,
                    self.session.trace_events,
                    self.session.trace_run_id,
                )
        self.canvas.set_projection(
            self.projection,
            selected_uid=self.session.current_node_uid,
            cursor_frame=self.session.preview_frame,
        )
        self._update_status()

    def handle_preview_event(self, message: dict) -> None:
        event = message.get("event")
        if event == "frame":
            frame = message.get("payload", {}).get("frame")
            if isinstance(frame, int) and not isinstance(frame, bool):
                self.canvas.set_cursor_frame(frame)
                self._update_seek_progress(frame)
        elif event == "state":
            state = message.get("payload", {}).get("state")
            if state == "seeking":
                target = message.get("payload", {}).get("frame")
                if isinstance(target, int) and not isinstance(target, bool):
                    self._seek_target = target
                self.seek_progress.setVisible(True)
                self._update_seek_progress(self.session.preview_frame)

    def _update_seek_progress(self, frame: int) -> None:
        if self._seek_target is None or self.session.preview_state != "seeking":
            self.seek_progress.setVisible(False)
            return
        target = max(1, self._seek_target)
        percent = int(max(0, min(100, frame * 100 / target)))
        self.seek_progress.setValue(percent)
        self.seek_progress.setVisible(True)

    def edit_interval(self, uid: str, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProgramError("timeline_edit", "Timeline value must be a non-negative integer")
        _unit, node, _location = find_node(self.session.program, uid)
        if node.kind == "Wait" and _is_literal_int(node.arguments.get("frames")):
            argument = "frames"
        elif node.kind == "At" and _is_literal_int(node.arguments.get("frame")):
            argument = "frame"
        elif "duration" in node.arguments and _is_literal_int(node.arguments.get("duration")):
            argument = "duration"
        else:
            raise ProgramError(
                "timeline_edit",
                "Timeline 只允许修改字面量 Wait、duration 或 At.frame",
            )
        self.session.set_node_argument(uid, argument, value)

    def _preview_state_changed(self, state: str) -> None:
        if state != "seeking":
            self._seek_target = None
            self.seek_progress.setVisible(False)

    def _update_status(self) -> None:
        projection = self.projection
        if projection is None:
            self.status_label.setText("时间线 · 请选择逻辑单元")
            return
        dynamic = sum(
            1
            for interval in projection.all_intervals()
            if isinstance(interval.start, Unknown) or isinstance(interval.end, Unknown)
        )
        trace = f" · Trace {projection.trace_run_id[:8]}" if projection.trace_run_id else ""
        self.status_label.setText(
            f"时间线 · {len(projection.all_intervals())} 个区间 · 动态未知 {dynamic}{trace}"
        )


def _is_literal_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _lanes(projection: TimelineProjection | None) -> tuple[str, ...]:
    if projection is None:
        return ()
    values: list[str] = []
    for interval in projection.all_intervals():
        if interval.lane not in values:
            values.append(interval.lane)
    return tuple(values)


def _maximum_known_frame(projection: TimelineProjection | None) -> int:
    if projection is None:
        return 0
    values = [0]
    for interval in projection.all_intervals():
        if isinstance(interval.start, int):
            values.append(interval.start)
        if isinstance(interval.end, int):
            values.append(interval.end)
    return max(values)


def _lane_label(lane: str) -> str:
    if lane == "main":
        return "主流程"
    if "/parallel:" in lane:
        return "并行 · " + lane.rsplit(":", 1)[-1]
    if "/spawn:" in lane:
        return "后台任务"
    if "/branch:" in lane:
        return "分支 · " + lane.rsplit(":", 1)[-1]
    if "/wave:" in lane:
        return "Wave"
    if "/boss:" in lane:
        return "Boss / 符卡"
    if "/call:" in lane:
        return "调用"
    return lane


def _ruler_step(scale: float) -> int:
    if scale >= 1.0:
        return 60
    if scale >= 0.35:
        return 120
    return 300


__all__ = ["TimelineCanvas", "TimelinePanel"]

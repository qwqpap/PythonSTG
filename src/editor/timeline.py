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
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .session import EditorSession


_ORIGIN_X = 160
_RULER_HEIGHT = 24
_LANE_HEIGHT = 32
_LANE_GAP = 6
_METRICS_HEIGHT = 58


@dataclass(frozen=True)
class _PaintedInterval:
    rect: QRectF
    interval: TimelineInterval


def _layout_timeline_intervals(
    projection: TimelineProjection,
    *,
    pixels_per_frame: float,
) -> tuple[_PaintedInterval, ...]:
    """Build transient paint geometry; no authoring or Timeline state is stored."""

    lanes = _lanes(projection)
    lane_index = {lane: index for index, lane in enumerate(lanes)}
    maximum = max(60, _maximum_known_frame(projection))
    dynamic_offset = _ORIGIN_X + maximum * pixels_per_frame + 24
    dynamic_per_lane: dict[str, int] = {}
    painted: list[_PaintedInterval] = []
    for interval in projection.all_intervals():
        y = _RULER_HEIGHT + lane_index[interval.lane] * (_LANE_HEIGHT + _LANE_GAP)
        if isinstance(interval.start, Unknown):
            index = dynamic_per_lane.get(interval.lane, 0)
            dynamic_per_lane[interval.lane] = index + 1
            x = dynamic_offset + index * 96
        else:
            x = _ORIGIN_X + interval.start * pixels_per_frame
        if interval.display == "milestone":
            rect = QRectF(x - 4, y + 8, 8, _LANE_HEIGHT - 16)
        elif isinstance(interval.start, int) and isinstance(interval.end, int):
            width = max(8.0, (interval.end - interval.start) * pixels_per_frame)
            rect = QRectF(x, y + 2, width, _LANE_HEIGHT - 4)
        else:
            rect = QRectF(x, y + 2, 90.0, _LANE_HEIGHT - 4)
        painted.append(_PaintedInterval(rect, interval))
    return tuple(painted)


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
        metrics_height = _METRICS_HEIGHT if projection and projection.metrics else 0
        height = (
            _RULER_HEIGHT
            + max(1, len(lanes)) * (_LANE_HEIGHT + _LANE_GAP)
            + metrics_height
            + 12
        )
        maximum = _maximum_known_frame(projection)
        content_right = _ORIGIN_X + int(maximum * self.pixels_per_frame) + 180
        if projection is not None:
            layout = _layout_timeline_intervals(
                projection,
                pixels_per_frame=self.pixels_per_frame,
            )
            content_right = max(
                [content_right, *(round(item.rect.right()) + 24 for item in layout)]
            )
        self.setMinimumSize(max(720, content_right), height)
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
        for lane, index in lane_index.items():
            y = _RULER_HEIGHT + index * (_LANE_HEIGHT + _LANE_GAP)
            painter.setPen(QColor("#c8cad0"))
            painter.drawText(6, y + 21, _lane_label(lane))
            painter.fillRect(_ORIGIN_X, y, self.width() - _ORIGIN_X, _LANE_HEIGHT, QColor("#292b30"))

        self._painted.extend(
            _layout_timeline_intervals(
                projection,
                pixels_per_frame=self.pixels_per_frame,
            )
        )
        for painted in self._painted:
            interval = painted.interval
            rect = painted.rect
            color = colors[interval.kind]
            if interval.uid == self.selected_uid:
                color = QColor("#d5a928")
            if interval.display == "aggregate":
                aggregate = QColor(color)
                aggregate.setAlpha(88)
                painter.fillRect(rect, aggregate)
            elif interval.display == "milestone":
                painter.setBrush(color)
                painter.setPen(QPen(QColor("#f4f4f4"), 1))
                painter.drawEllipse(rect)
            else:
                painter.fillRect(rect, color)
            pen = QPen(QColor("#f4f4f4"), 2 if interval.editable != "none" else 1)
            if interval.kind == "dynamic":
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            if interval.display != "milestone":
                painter.drawRect(rect)
            label = interval.label
            if interval.observed_branch == "then":
                label += " · 实际：条件成立"
            elif interval.observed_branch == "else":
                label += " · 实际：否则"
            painter.drawText(
                rect.adjusted(4, 0, -3, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                label,
            )
            self._paint_observation(painter, interval, rect)

        if projection.metrics:
            metrics_top = (
                _RULER_HEIGHT
                + max(1, len(lanes)) * (_LANE_HEIGHT + _LANE_GAP)
                + 4
            )
            self._paint_metrics(painter, projection, metrics_top)

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

    def _paint_observation(
        self,
        painter: QPainter,
        interval: TimelineInterval,
        static_rect: QRectF,
    ) -> None:
        if interval.observed_start is None and interval.observed_end is None:
            return
        observed_start = (
            interval.observed_start
            if interval.observed_start is not None
            else interval.observed_end
        )
        if observed_start is None:
            return
        observed_end = interval.observed_end
        x = _ORIGIN_X + observed_start * self.pixels_per_frame
        width = (
            max(3.0, (observed_end - observed_start) * self.pixels_per_frame)
            if observed_end is not None and observed_end >= observed_start
            else 5.0
        )
        observed = QRectF(x, static_rect.bottom() - 5, width, 4)
        painter.fillRect(observed, QColor("#ff9f43"))

    def _paint_metrics(
        self,
        painter: QPainter,
        projection: TimelineProjection,
        top: int,
    ) -> None:
        chart = QRectF(_ORIGIN_X, top, self.width() - _ORIGIN_X, _METRICS_HEIGHT - 8)
        painter.fillRect(chart, QColor("#25272b"))
        painter.setPen(QColor("#c8cad0"))
        painter.drawText(6, top + 17, "弹幕密度")
        samples = projection.metrics
        maxima = {
            "emitted": max(1, max(sample.emitted for sample in samples)),
            "live": max(1, max(sample.live for sample in samples)),
            "lasers": max(1, max(sample.lasers for sample in samples)),
        }
        colors = {
            "emitted": QColor("#f4c95d"),
            "live": QColor("#58a6ff"),
            "lasers": QColor("#ff7b72"),
        }
        for name in ("live", "emitted", "lasers"):
            painter.setPen(QPen(colors[name], 2))
            previous = None
            for sample in samples:
                x = _ORIGIN_X + sample.frame * self.pixels_per_frame
                value = getattr(sample, name)
                y = chart.bottom() - value / maxima[name] * max(1.0, chart.height() - 6)
                if previous is not None:
                    painter.drawLine(
                        round(previous[0]),
                        round(previous[1]),
                        round(x),
                        round(y),
                    )
                previous = (x, y)

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
        self._loop_seek_pending = False
        self._revealed_uid: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        toolbar = QWidget(self)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(6, 2, 6, 2)
        self.status_label = QLabel("时间线 · 代码投影", toolbar)
        self.status_label.setObjectName("timeline_status")
        toolbar_layout.addWidget(self.status_label)
        self.scope_combo = QComboBox(toolbar)
        self.scope_combo.setObjectName("timeline_scope")
        self.scope_combo.addItems(["当前单元", "当前 Stage"])
        self.scope_combo.setToolTip("时间线只切换代码投影范围，不保存独立时间文档")
        self.scope_combo.currentIndexChanged.connect(lambda _index: self.refresh())
        toolbar_layout.addWidget(self.scope_combo)
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
        navigation = QWidget(self)
        navigation_layout = QHBoxLayout(navigation)
        navigation_layout.setContentsMargins(6, 0, 6, 2)
        fit_all = QPushButton("适应全部", navigation)
        fit_all.setObjectName("timeline_fit_all")
        fit_all.clicked.connect(self.fit_all)
        navigation_layout.addWidget(fit_all)
        fit_selection = QPushButton("适应选择", navigation)
        fit_selection.setObjectName("timeline_fit_selection")
        fit_selection.clicked.connect(self.focus_selection)
        navigation_layout.addWidget(fit_selection)
        center_playhead = QPushButton("居中播放头", navigation)
        center_playhead.setObjectName("timeline_center_playhead")
        center_playhead.clicked.connect(self.center_playhead)
        navigation_layout.addWidget(center_playhead)
        navigation_layout.addStretch(1)
        self.loop_start = QSpinBox(navigation)
        self.loop_start.setObjectName("timeline_loop_start")
        self.loop_start.setRange(0, 10_000_000)
        self.loop_start.setSuffix("f")
        self.loop_start.setToolTip("循环起始帧")
        navigation_layout.addWidget(self.loop_start)
        self.loop_end = QSpinBox(navigation)
        self.loop_end.setObjectName("timeline_loop_end")
        self.loop_end.setRange(0, 10_000_000)
        self.loop_end.setSuffix("f")
        self.loop_end.setToolTip("循环结束帧")
        navigation_layout.addWidget(self.loop_end)
        self.loop_button = QPushButton("范围循环", navigation)
        self.loop_button.setObjectName("timeline_loop")
        self.loop_button.setCheckable(True)
        self.loop_button.toggled.connect(self._validate_loop_range)
        navigation_layout.addWidget(self.loop_button)
        layout.addWidget(navigation)
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
        if (
            unit is not None
            and self.scope_combo.currentIndex() == 1
            and self.session.current_stage_id is not None
        ):
            try:
                unit = self.session.program.get_unit(self.session.current_stage_id)
            except ProgramError:
                pass
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
        if self.projection is not None and self.loop_end.value() == 0:
            self.loop_end.setValue(max(1, _maximum_known_frame(self.projection)))
        if self.session.current_node_uid != self._revealed_uid:
            self._revealed_uid = self.session.current_node_uid
            self._reveal_selected(self.session.current_node_uid)
        self._update_status()

    def _reveal_selected(self, uid: str | None) -> None:
        """Scroll a program-flow selection into the visible Timeline viewport."""

        if uid is None or self.projection is None:
            return
        interval = self.projection.find(uid)
        if interval is None:
            return
        painted = next(
            (
                item
                for item in _layout_timeline_intervals(
                    self.projection,
                    pixels_per_frame=self.canvas.pixels_per_frame,
                )
                if item.interval.uid == uid
            ),
            None,
        )
        if painted is None:
            return
        rect = painted.rect
        horizontal = self.scroll.horizontalScrollBar()
        viewport_width = self.scroll.viewport().width()
        if rect.left() < horizontal.value():
            horizontal.setValue(round(max(0.0, rect.left() - 24)))
        elif rect.right() > horizontal.value() + viewport_width:
            horizontal.setValue(round(rect.right() - viewport_width + 24))
        vertical = self.scroll.verticalScrollBar()
        viewport_height = self.scroll.viewport().height()
        if rect.top() < vertical.value():
            vertical.setValue(round(max(0.0, rect.top() - 8)))
        elif rect.bottom() > vertical.value() + viewport_height:
            vertical.setValue(round(rect.bottom() - viewport_height + 8))

    def handle_preview_event(self, message: dict) -> None:
        event = message.get("event")
        if event == "frame":
            frame = message.get("payload", {}).get("frame")
            if isinstance(frame, int) and not isinstance(frame, bool):
                self.canvas.set_cursor_frame(frame)
                self._update_seek_progress(frame)
                if (
                    self.loop_button.isChecked()
                    and not self._loop_seek_pending
                    and self.session.preview_state == "running"
                    and self.loop_end.value() > self.loop_start.value()
                    and frame >= self.loop_end.value()
                ):
                    self._loop_seek_pending = True
                    self.seek_requested.emit(self.loop_start.value())
        elif event == "state":
            state = message.get("payload", {}).get("state")
            if state == "seeking":
                target = message.get("payload", {}).get("frame")
                if isinstance(target, int) and not isinstance(target, bool):
                    self._seek_target = target
                self.seek_progress.setVisible(True)
                self._update_seek_progress(self.session.preview_frame)
            elif state == "running":
                self._loop_seek_pending = False

    def fit_all(self) -> None:
        maximum = max(1, _maximum_known_frame(self.projection))
        available = max(180, self.scroll.viewport().width() - _ORIGIN_X - 36)
        self.canvas.pixels_per_frame = min(4.0, max(0.1, available / maximum))
        self.canvas.set_projection(
            self.projection,
            selected_uid=self.session.current_node_uid,
            cursor_frame=self.session.preview_frame,
        )
        self.scroll.horizontalScrollBar().setValue(0)

    def focus_selection(self) -> None:
        if self.projection is None or not self.session.current_node_uid:
            return
        interval = self.projection.find(self.session.current_node_uid)
        if interval is None:
            return
        if isinstance(interval.start, int) and isinstance(interval.end, int):
            duration = max(1, interval.end - interval.start)
            available = max(180, self.scroll.viewport().width() - _ORIGIN_X - 36)
            self.canvas.pixels_per_frame = min(4.0, max(0.1, available / duration))
            self.canvas.set_projection(
                self.projection,
                selected_uid=self.session.current_node_uid,
                cursor_frame=self.session.preview_frame,
            )
        frame = interval.observed_start
        if frame is None and isinstance(interval.start, int):
            frame = (
                round((interval.start + interval.end) / 2)
                if isinstance(interval.end, int)
                else interval.start
            )
        if frame is not None:
            self._center_frame(frame)

    def center_playhead(self) -> None:
        self._center_frame(self.session.preview_frame)

    def _center_frame(self, frame: int) -> None:
        x = _ORIGIN_X + max(0, int(frame)) * self.canvas.pixels_per_frame
        bar = self.scroll.horizontalScrollBar()
        bar.setValue(round(x - self.scroll.viewport().width() / 2))

    def _validate_loop_range(self, enabled: bool) -> None:
        if enabled and self.loop_end.value() <= self.loop_start.value():
            self.loop_end.setValue(self.loop_start.value() + 60)
        if not enabled:
            self._loop_seek_pending = False

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
        if state in {"stopped", "error"}:
            self._loop_seek_pending = False

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
        scope = "当前 Stage" if self.scope_combo.currentIndex() == 1 else "当前单元"
        metrics = f" · 密度采样 {len(projection.metrics)}" if projection.metrics else ""
        self.status_label.setText(
            f"时间线 · {scope} · {len(projection.all_intervals())} 个区间 · "
            f"动态未知 {dynamic}{metrics}{trace}"
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
        if interval.observed_start is not None:
            values.append(interval.observed_start)
        if interval.observed_end is not None:
            values.append(interval.observed_end)
    values.extend(sample.frame for sample in projection.metrics)
    return max(values)


def _lane_label(lane: str) -> str:
    if lane == "main":
        return "主流程"
    if "/parallel:" in lane:
        return "并行 · " + lane.rsplit(":", 1)[-1]
    if "/body:" in lane:
        return "内部 · " + lane.rsplit(":", 1)[-1]
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


__all__ = ["TimelineCanvas", "TimelinePanel", "_layout_timeline_intervals"]

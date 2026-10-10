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
from src.qt_compat.QtCore import QRectF, Qt, QTimer, Signal
from src.qt_compat.QtGui import QColor, QMouseEvent, QPainter, QPen
from src.qt_compat.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from .session import EditorSession
from .node_palette import PALETTE_ENTRIES


_ORIGIN_X = 196
_RULER_HEIGHT = 24
_LANE_HEIGHT = 32
_LANE_GAP = 6
_METRICS_HEIGHT = 76
_MIN_ZOOM = 0.000001
_MAX_ZOOM = 8.0
_MAX_CANVAS_WIDTH = 16_000_000
_NODE_LABELS = {entry.kind: entry.label for entry in PALETTE_ENTRIES}


@dataclass(frozen=True)
class _PaintedInterval:
    rect: QRectF
    interval: TimelineInterval
    depth: int = 0
    order: str = ""


@dataclass
class _IntervalDrag:
    uid: str
    mode: str
    press_x: float
    rect: QRectF
    original: int
    value: int


def _layout_timeline_intervals(
    projection: TimelineProjection,
    *,
    pixels_per_frame: float,
    maximum: int | None = None,
) -> tuple[_PaintedInterval, ...]:
    """Build transient paint geometry; no authoring or Timeline state is stored."""

    maximum = max(60, _maximum_known_frame(projection)) if maximum is None else maximum
    dynamic_offset = _ORIGIN_X + maximum * pixels_per_frame + 24
    painted: list[_PaintedInterval] = []

    def visit(interval: TimelineInterval, depth: int, order: str) -> None:
        # Source order, not a shared lane, owns a row.  Parent chapters and
        # simultaneous zero-duration actions therefore never cover a child.
        y = _RULER_HEIGHT + len(painted) * (_LANE_HEIGHT + _LANE_GAP)
        dynamic = isinstance(interval.start, Unknown) or isinstance(interval.end, Unknown)
        x = dynamic_offset if dynamic else _ORIGIN_X + _display_start(interval) * pixels_per_frame
        if interval.display == "milestone":
            rect = QRectF(x - 4, y + 8, 8, _LANE_HEIGHT - 16)
        elif not dynamic:
            # A subpixel span stays a subpixel span.  The separate hit handle
            # supplies input tolerance without inventing an authored duration.
            width = max(0.0, (interval.end - _display_start(interval)) * pixels_per_frame)
            rect = QRectF(x, y + 3, width, _LANE_HEIGHT - 6)
        else:
            rect = QRectF(x, y + 3, 112.0, _LANE_HEIGHT - 6)
        painted.append(_PaintedInterval(rect, interval, depth, order))
        for index, child in enumerate(interval.children, 1):
            visit(child, depth + 1, f"{order}.{index}")

    for index, interval in enumerate(projection.intervals, 1):
        visit(interval, 0, str(index))
    return tuple(painted)


class TimelineCanvas(QWidget):
    """Small lane renderer with only the three contract-approved drag edits."""

    edit_requested = Signal(str, int)
    seek_requested = Signal(int)
    drag_feedback = Signal(str)
    zoom_requested = Signal(float, float)

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.projection: TimelineProjection | None = None
        self.pixels_per_frame = 0.5
        self.cursor_frame = 0
        self.cursor_available = True
        self.selected_uid: str | None = None
        self.scrub_frame: int | None = None
        self._painted: list[_PaintedInterval] = []
        self._painted_by_uid: dict[str, _PaintedInterval] = {}
        self._layout_projection: TimelineProjection | None = None
        self._layout_scale: float | None = None
        self._layout_maximum: int | None = None
        self._row_labels: dict[str, str] = {}
        self._label_program = None
        self._maximum = 60
        self._drag: _IntervalDrag | None = None
        self._scrubbing = False
        self._selecting = False
        self.seek_enabled = False
        self.seek_reason = "请先运行预览，再定位播放时间。"
        self.setObjectName("timeline_canvas")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        maximum = max(60, _maximum_known_frame(projection))
        if self.cursor_available:
            maximum = max(maximum, (self.cursor_frame // 60 + 1) * 60)
        self.pixels_per_frame = min(
            self.pixels_per_frame, (_MAX_CANVAS_WIDTH - _ORIGIN_X - 512) / maximum
        )
        if (projection is not self._layout_projection
                or self.pixels_per_frame != self._layout_scale
                or maximum != self._layout_maximum):
            self._layout_projection = projection
            self._layout_scale = self.pixels_per_frame
            self._layout_maximum = maximum
            self._maximum = maximum
            self._painted = list(
                _layout_timeline_intervals(
                    projection, pixels_per_frame=self.pixels_per_frame, maximum=maximum
                )
            ) if projection is not None else []
            self._painted_by_uid.clear()
            for painted in self._painted:
                self._painted_by_uid.setdefault(painted.interval.uid, painted)
        if self.session.is_open and self.session.program is not self._label_program:
            self._label_program = self.session.program
            self._row_labels = {
                node.uid: _source_node_label(node)
                for _unit, node in self.session.program.walk_nodes()
            }
        metrics_height = _METRICS_HEIGHT if projection and projection.metrics else 0
        height = (
            _RULER_HEIGHT
            + max(1, len(self._painted)) * (_LANE_HEIGHT + _LANE_GAP)
            + metrics_height
            + 12
        )
        maximum = self._maximum
        content_right = _ORIGIN_X + int(maximum * self.pixels_per_frame) + 24
        if self._painted:
            content_right = max(
                [content_right, *(round(item.rect.right()) + 24 for item in self._painted)]
            )
        self.setMinimumSize(min(_MAX_CANVAS_WIDTH, max(320, content_right)), height)
        self.updateGeometry()
        self.update()

    def set_cursor_frame(self, frame: int) -> None:
        self.cursor_frame = max(0, int(frame))
        if self.cursor_frame > self._maximum:
            self.set_projection(self.projection, selected_uid=self.selected_uid, cursor_frame=self.cursor_frame)
        self.update()

    @property
    def is_interacting(self) -> bool:
        return self._selecting or self._drag is not None or self._scrubbing

    @property
    def timed_right(self) -> float:
        return _ORIGIN_X + self._maximum * self.pixels_per_frame

    def zoom(self, factor: float) -> None:
        self.pixels_per_frame = min(_MAX_ZOOM, max(_MIN_ZOOM, self.pixels_per_frame * factor))
        self.set_projection(
            self.projection,
            selected_uid=self.selected_uid,
            cursor_frame=self.cursor_frame,
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        exposed = QRectF(event.rect().adjusted(-2, -2, 2, 2))
        painter.fillRect(event.rect(), QColor("#1e1f22"))
        projection = self.projection
        if projection is None or not projection.intervals:
            painter.setPen(QColor("#8b8d94"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "选择内容以查看时间安排")
            return

        if any(isinstance(item.interval.start, Unknown) or isinstance(item.interval.end, Unknown) for item in self._painted):
            unknown_left = self.timed_right + 16
            painter.fillRect(QRectF(unknown_left, 0, max(0, self.width() - unknown_left), self.height()), QColor("#25222b"))
            painter.setPen(QPen(QColor("#9b8da8"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(round(unknown_left), 0, round(unknown_left), self.height())

        colors = {
            "static": QColor("#356a9a"),
            "branch": QColor("#8559a5"),
            "parallel": QColor("#347f72"),
            "spawned": QColor("#9a6b32"),
            "template": QColor("#a24f72"),
            "dynamic": QColor("#5f6269"),
        }
        for index, painted in enumerate(self._painted):
            y = _RULER_HEIGHT + index * (_LANE_HEIGHT + _LANE_GAP)
            if y + _LANE_HEIGHT < exposed.top() or y > exposed.bottom():
                continue
            background = QColor("#292b30") if index % 2 == 0 else QColor("#25272b")
            painter.fillRect(QRectF(_ORIGIN_X, y, self.width() - _ORIGIN_X, _LANE_HEIGHT), background)

        for painted in self._painted:
            interval = painted.interval
            rect = painted.rect
            if not rect.intersects(exposed):
                # Observed timing can be far away from the static estimate.
                self._paint_observation(painter, interval, rect, exposed)
                continue
            color = colors[interval.kind]
            selected = interval.uid == self.selected_uid
            if selected:
                color = QColor("#487eae")
            if interval.display == "aggregate":
                aggregate = QColor(color)
                aggregate.setAlpha(35)
                painter.fillRect(rect, aggregate)
                # Chapters occupy their own row.  A bracket means an aggregate,
                # not another playable clip laid over its leaf steps.
                painter.setPen(QPen(color.lighter(145), 2 if selected else 1))
                painter.drawLine(round(rect.left()), round(rect.top() + 6), round(rect.right()), round(rect.top() + 6))
                painter.drawLine(round(rect.left()), round(rect.top() + 6), round(rect.left()), round(rect.bottom() - 5))
                painter.drawLine(round(rect.right()), round(rect.top() + 6), round(rect.right()), round(rect.bottom() - 5))
            elif interval.display == "milestone":
                painter.setBrush(color)
                painter.setPen(QPen(QColor("#f4f4f4"), 1))
                painter.drawEllipse(rect)
            else:
                painter.fillRect(rect, color)
            mode = _drag_mode(interval)
            pen = QPen(QColor("#9bc8ed") if selected else color.lighter(140), 2 if selected else 1)
            if interval.kind == "dynamic":
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            if interval.display not in {"milestone", "aggregate"}:
                painter.drawRect(rect)
            if interval.display == "unknown":
                # Labels live in the source-order column; an unknown block has
                # no scale and says so instead of imitating a timed clip.
                painter.drawText(rect.adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter, "时间待定")
            self._paint_observation(painter, interval, rect, exposed)
            if mode in {"wait", "duration"}:
                painter.fillRect(QRectF(rect.right() - 3, rect.top(), 3, rect.height()), QColor("#f4f4f4"))
            elif mode == "at":
                painter.setPen(QColor("#f4f4f4"))
                painter.drawText(rect.adjusted(2, 0, -2, 0), Qt.AlignmentFlag.AlignRight, "↔")

        if self._drag is not None:
            drag = self._drag
            delta = (drag.value - drag.original) * self.pixels_per_frame
            ghost = QRectF(drag.rect)
            if drag.mode == "at":
                ghost.translate(delta, 0)
            else:
                ghost.setWidth(max(0.0, ghost.width() + delta))
            painter.setPen(QPen(QColor("#f4c95d"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(ghost)
            painter.drawText(
                QRectF(ghost.left(), ghost.top() - 20, 240, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{drag.original} → {drag.value} 帧",
            )

        if projection.metrics:
            metrics_top = (
                _RULER_HEIGHT
                + max(1, len(self._painted)) * (_LANE_HEIGHT + _LANE_GAP)
                + 4
            )
            self._paint_metrics(painter, projection, metrics_top, exposed)

        if self.cursor_available:
            cursor_x = _ORIGIN_X + self.cursor_frame * self.pixels_per_frame
            painter.setPen(QPen(QColor("#ff4b4b"), 2))
            painter.drawLine(int(cursor_x), 0, int(cursor_x), self.height())
        if self.scrub_frame is not None:
            scrub_x = _ORIGIN_X + self.scrub_frame * self.pixels_per_frame
            painter.setPen(QPen(QColor("#f4c95d"), 2, Qt.PenStyle.DashLine))
            painter.drawLine(int(scrub_x), 0, int(scrub_x), self.height())

        # Keep names visible when horizontally scrolling a long arrangement.
        # Elision is explicit; QPainter must never wrap Chinese into a column.
        label_left = self._label_left()
        header_top = self._header_top()
        viewport_bottom = header_top + self._viewport_height()
        painter.fillRect(QRectF(label_left, 0, _ORIGIN_X, self.height()), QColor("#202226"))
        for index, painted in enumerate(self._painted):
            y = _RULER_HEIGHT + index * (_LANE_HEIGHT + _LANE_GAP)
            if y + _LANE_HEIGHT < exposed.top() or y > exposed.bottom():
                continue
            # Judge text against the actual visible portion of the row, not
            # the dirty paint rectangle or the full source-row height. A
            # partially clipped row can still fit one complete line of text.
            visible_top = max(y, header_top + _RULER_HEIGHT)
            visible_bottom = min(y + _LANE_HEIGHT, viewport_bottom)
            if visible_bottom <= visible_top:
                continue
            selected = painted.interval.uid == self.selected_uid
            if selected:
                painter.fillRect(QRectF(label_left, y, _ORIGIN_X - 1, _LANE_HEIGHT), QColor("#2b4358"))
            elif painted.interval.children:
                painter.fillRect(QRectF(label_left, y, _ORIGIN_X - 1, _LANE_HEIGHT), QColor("#272b31"))
            text_left = label_left + 8 + min(4, painted.depth) * 12
            if painted.depth:
                painter.setPen(QColor("#606773"))
                painter.drawLine(round(text_left - 6), y + 9, round(text_left - 6), y + 23)
                painter.drawLine(round(text_left - 6), y + 16, round(text_left - 2), y + 16)
            if visible_bottom - visible_top < painter.fontMetrics().height() + 2:
                continue
            painter.setPen(QColor("#e0e4eb") if selected else QColor("#bdc4ce"))
            label = self._label_for(painted)
            label_rect = QRectF(text_left, visible_top, label_left + _ORIGIN_X - text_left - 8, visible_bottom - visible_top)
            text = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, max(0, round(label_rect.width())))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextSingleLine, text)
        painter.setPen(QColor("#3b4049"))
        painter.drawLine(round(label_left + _ORIGIN_X - 1), 0, round(label_left + _ORIGIN_X - 1), self.height())
        self._paint_ruler(painter, exposed, header_top, label_left)

    def _label_left(self) -> int:
        return max(0, -self.pos().x())

    def _header_top(self) -> int:
        return max(0, -self.pos().y())

    def _viewport_height(self) -> int:
        parent = self.parentWidget()
        return parent.height() if parent is not None else self.height()

    def _paint_ruler(self, painter: QPainter, exposed: QRectF, top: int, label_left: int) -> None:
        # The ruler and the source-order heading form one fixed top row while
        # the interval rows scroll beneath it. Frame coordinates stay absolute.
        painter.fillRect(QRectF(0, top, self.width(), _RULER_HEIGHT), QColor("#25272b"))
        painter.setPen(QColor("#858992"))
        step = _ruler_step(self.pixels_per_frame)
        first_tick = max(0, int((exposed.left() - _ORIGIN_X) / self.pixels_per_frame) // step * step)
        last_tick = min(self._maximum + 1, int((exposed.right() - _ORIGIN_X) / self.pixels_per_frame) + step)
        for frame in range(first_tick, max(first_tick, last_tick), step):
            x = _ORIGIN_X + frame * self.pixels_per_frame
            painter.drawLine(int(x), top + _RULER_HEIGHT - 6, int(x), top + _RULER_HEIGHT)
            painter.drawText(int(x + 3), top + 15, f"{frame} 帧")
        if any(isinstance(item.interval.start, Unknown) or isinstance(item.interval.end, Unknown) for item in self._painted):
            unknown_left = self.timed_right + 16
            painter.fillRect(QRectF(unknown_left, top, max(0, self.width() - unknown_left), _RULER_HEIGHT), QColor("#25222b"))
            painter.setPen(QColor("#9b8da8"))
            painter.drawText(QRectF(unknown_left + 8, top, 340, _RULER_HEIGHT), Qt.AlignmentFlag.AlignVCenter, "运行后确定时间")
        if self.cursor_available:
            x = _ORIGIN_X + self.cursor_frame * self.pixels_per_frame
            painter.setPen(QPen(QColor("#ff4b4b"), 2))
            painter.drawLine(round(x), top, round(x), top + _RULER_HEIGHT)
        if self.scrub_frame is not None:
            x = _ORIGIN_X + self.scrub_frame * self.pixels_per_frame
            painter.setPen(QPen(QColor("#f4c95d"), 2, Qt.PenStyle.DashLine))
            painter.drawLine(round(x), top, round(x), top + _RULER_HEIGHT)
            painter.drawText(QRectF(x + 4, top + 2, 90, _RULER_HEIGHT - 4), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"→ {self.scrub_frame} 帧")
        painter.fillRect(QRectF(label_left, top, _ORIGIN_X, _RULER_HEIGHT), QColor("#25272b"))
        painter.setPen(QColor("#a9adb5"))
        painter.drawText(QRectF(label_left + 8, top, _ORIGIN_X - 16, _RULER_HEIGHT), Qt.AlignmentFlag.AlignVCenter, "步骤顺序")
        painter.setPen(QColor("#3b4049"))
        painter.drawLine(label_left, top + _RULER_HEIGHT - 1, self.width(), top + _RULER_HEIGHT - 1)

    def _label_for(self, painted: _PaintedInterval) -> str:
        label = self._row_labels.get(painted.interval.uid, _interval_label(painted.interval.label))
        lane = painted.interval.lane.rsplit("/", 1)[-1]
        if lane.startswith("parallel:"):
            return f"并行 {lane.rsplit(':', 1)[-1]} · {label}"
        if lane.startswith("branch:"):
            branch = "成立" if lane.endswith(":then") else "否则"
            return f"{branch} · {label}"
        if lane.startswith("spawn:"):
            return f"后台 · {label}"
        return label

    def _paint_observation(
        self,
        painter: QPainter,
        interval: TimelineInterval,
        static_rect: QRectF,
        exposed: QRectF,
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
        if observed.intersects(exposed):
            painter.fillRect(observed, QColor("#ff9f43"))

    def _paint_metrics(
        self,
        painter: QPainter,
        projection: TimelineProjection,
        top: int,
        exposed: QRectF,
    ) -> None:
        chart = QRectF(_ORIGIN_X, top, self.timed_right - _ORIGIN_X, _METRICS_HEIGHT - 8)
        if not chart.intersects(exposed):
            return
        painter.fillRect(chart, QColor("#25272b"))
        painter.setPen(QColor("#c8cad0"))
        painter.drawText(6, top + 17, "弹幕密度")
        samples = projection.metrics
        maximum = max(
            1,
            *(sample.emitted for sample in samples),
            *(sample.live for sample in samples),
            *(sample.lasers for sample in samples),
        )
        colors = {
            "emitted": QColor("#f4c95d"),
            "live": QColor("#58a6ff"),
            "lasers": QColor("#ff7b72"),
        }
        labels = {
            "live": "存活",
            "emitted": "每 12 帧发射",
            "lasers": "激光",
        }
        painter.drawText(72, top + 17, f"共同刻度 0–{maximum}")
        legend_x = round(chart.left()) + 8
        for name in ("live", "emitted", "lasers"):
            painter.setPen(QPen(colors[name], 2))
            painter.drawLine(legend_x, top + 11, legend_x + 12, top + 11)
            painter.setPen(QColor("#c8cad0"))
            painter.drawText(legend_x + 16, top + 16, labels[name])
            legend_x += 76 if name != "emitted" else 126
        plot = chart.adjusted(0, 20, 0, 0)
        painter.setPen(QColor("#4b5059"))
        painter.drawLine(
            round(plot.left()),
            round(plot.bottom()),
            round(plot.right()),
            round(plot.bottom()),
        )
        for name in ("live", "emitted", "lasers"):
            painter.setPen(QPen(colors[name], 2))
            previous = None
            for sample in samples:
                x = _ORIGIN_X + sample.frame * self.pixels_per_frame
                value = getattr(sample, name)
                y = plot.bottom() - value / maximum * max(1.0, plot.height() - 6)
                if previous is not None and x >= exposed.left() and previous[0] <= exposed.right():
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
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        header_top = self._header_top()
        if header_top <= position.y() < header_top + _RULER_HEIGHT:
            if position.x() < self._label_left() + _ORIGIN_X:
                return
            if not self.seek_enabled or position.x() > self.timed_right:
                self.drag_feedback.emit(self.seek_reason if not self.seek_enabled else "动态区域只有源码顺序，不能按时间定位。")
                return
            frame = max(0, round((position.x() - _ORIGIN_X) / self.pixels_per_frame))
            self.scrub_frame = frame
            self._scrubbing = True
            self.update()
            return
        painted = self._at(position.x(), position.y())
        if painted is None:
            if self.seek_enabled and self._label_left() + _ORIGIN_X <= position.x() <= self.timed_right:
                frame = max(0, round((position.x() - _ORIGIN_X) / self.pixels_per_frame))
                self.seek_requested.emit(frame)
            return
        uid = painted.interval.uid
        self._selecting = True
        try:
            self.session.select_node(uid)
        except ProgramError:
            return
        finally:
            self._selecting = False
        self.selected_uid = uid
        mode = _drag_mode(painted.interval)
        if self.session.can_edit and position.x() >= self._label_left() + _ORIGIN_X and (
            mode == "at"
            or mode in {"wait", "duration"} and self.duration_handle(painted.rect).contains(position)
        ):
            node = self.session.current_node
            argument = {"wait": "frames", "duration": "duration", "at": "frame"}[mode]
            original = node.arguments.get(argument) if node is not None else None
            if _is_literal_int(original):
                self._drag = _IntervalDrag(uid, mode, position.x(), QRectF(painted.rect), original, original)
        self.update()

    @staticmethod
    def duration_handle(rect: QRectF) -> QRectF:
        return QRectF(rect.right() - 7, rect.top() - 2, 14, rect.height() + 4)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._scrubbing:
            if not self.seek_enabled:
                self._scrubbing = False
                self.scrub_frame = None
                return
            frame = max(
                0, min(self._maximum, round((event.position().x() - _ORIGIN_X) / self.pixels_per_frame))
            )
            if frame != self.scrub_frame:
                self.scrub_frame = frame
                self.update()
            return
        if self._drag is not None:
            drag = self._drag
            delta = round((event.position().x() - drag.press_x) / self.pixels_per_frame)
            drag.value = max(0, drag.original + delta)
            self.drag_feedback.emit(f"{'触发时间' if drag.mode == 'at' else '时长'}：{drag.original} → {drag.value} 帧；Esc 取消")
            self.update()
            return
        painted = self._at(event.position().x(), event.position().y())
        editable = (
            _drag_mode(painted.interval)
            if painted and event.position().x() >= self._label_left() + _ORIGIN_X else "none"
        )
        if painted and editable in {"wait", "duration"} and self.duration_handle(painted.rect).contains(event.position()):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif editable == "at":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()
        self.setToolTip(self._tooltip_for(painted) if painted else "左侧按步骤顺序排列；右侧按帧数显示时间。")
        super().mouseMoveEvent(event)

    def _tooltip_for(self, painted: _PaintedInterval) -> str:
        interval = painted.interval
        lines = [f"{painted.order} · {self._label_for(painted)}"]
        start = _display_start(interval)
        if _is_literal_int(start) and _is_literal_int(interval.end):
            lines.append(
                f"预计：{start}–{interval.end} 帧（{interval.end - start} 帧）"
                if interval.end != start else f"预计：第 {start} 帧瞬时执行"
            )
        else:
            lines.append("时间需运行后确定；右侧待定区没有时间刻度。")
        if interval.children:
            lines.append("章节括号包含子步骤；重复章节的子步骤仅展示一轮。" if interval.label == "Repeat" else "章节括号包含下方子步骤。")
        if interval.lane != "main":
            lines.append(_lane_label(interval.lane))
        if interval.observed_start is not None:
            end = interval.observed_end
            lines.append(f"实际：{interval.observed_start}–{end} 帧" if end is not None else f"实际：第 {interval.observed_start} 帧开始")
        if interval.observed_branch:
            lines.append("实际分支：条件成立" if interval.observed_branch == "then" else "实际分支：否则")
        mode = _drag_mode(interval)
        lines.append(
            "拖动白色右缘调整时长。" if mode in {"wait", "duration"}
            else "拖动时间区块调整触发帧。" if mode == "at"
            else "点击选择步骤，在右侧属性中修改。"
        )
        return "\n".join(lines)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._scrubbing and event.button() == Qt.MouseButton.LeftButton:
            frame = max(
                0, min(self._maximum, round((event.position().x() - _ORIGIN_X) / self.pixels_per_frame))
            )
            self._scrubbing = False
            self.scrub_frame = None
            self.update()
            if frame is not None and self.seek_enabled:
                self.seek_requested.emit(frame)
            return
        drag = self._drag
        self._drag = None
        if drag is None or event.button() != Qt.MouseButton.LeftButton:
            return
        release_x = event.position().x()
        self.update()
        self.drag_feedback.emit("")
        if abs(release_x - drag.press_x) < 3:
            return
        value = max(0, drag.original + round((release_x - drag.press_x) / self.pixels_per_frame))
        if value != drag.original:
            self.edit_requested.emit(drag.uid, value)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and (self._drag is not None or self._scrubbing):
            self._drag = None
            self._scrubbing = False
            self.scrub_frame = None
            self.drag_feedback.emit("")
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def _at(self, x: float, y: float) -> _PaintedInterval | None:
        if self._header_top() <= y < self._header_top() + _RULER_HEIGHT:
            return None
        if self._label_left() <= x < self._label_left() + _ORIGIN_X and y >= _RULER_HEIGHT:
            index = int((y - _RULER_HEIGHT) // (_LANE_HEIGHT + _LANE_GAP))
            return self._painted[index] if 0 <= index < len(self._painted) else None
        handle = min(
            (item for item in reversed(self._painted) if _drag_mode(item.interval) in {"wait", "duration"}
             and self.duration_handle(item.rect).contains(x, y)),
            key=lambda item: abs(item.rect.right() - x), default=None,
        )
        if handle is not None:
            return handle
        return next(
            (item for item in reversed(self._painted) if item.rect.contains(x, y)),
            None,
        )

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_requested.emit(1.25 if event.angleDelta().y() > 0 else 1 / 1.25, event.position().x())
            event.accept()
            return
        super().wheelEvent(event)

    def interval_geometry(self, uid: str) -> _PaintedInterval | None:
        """Read cached view geometry without re-projecting the source."""

        return self._painted_by_uid.get(uid)


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
        self._static_projection: TimelineProjection | None = None
        self._projection_key = None
        self._frame_payload: dict | None = None
        self._frame_run_id: str | None = None
        self._seek_target: int | None = None
        self._loop_seek_pending = False
        self._loop_bound_scope: tuple[str | None, str] | None = None
        self._loop_range_scope: tuple[object, str] | None = None
        self._auto_fit_pending = False
        self._preview_owner = None
        self._revealed_uid: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        toolbar = QWidget(self)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(6, 2, 6, 2)
        self.status_label = QLabel("时间安排", toolbar)
        self.status_label.setObjectName("timeline_status")
        self.status_label.setMinimumWidth(0)
        self.status_label.setWordWrap(False)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        toolbar_layout.addWidget(self.status_label)
        self.scope_combo = QComboBox(toolbar)
        self.scope_combo.setObjectName("timeline_scope")
        self.scope_combo.setMaximumWidth(150)
        self.scope_combo.addItems(["当前内容", "当前关卡"])
        self.scope_combo.setToolTip("查看当前内容或整关的执行顺序。拖动时长右缘，会修改对应节点的参数。")
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
        zoom_out = QPushButton("−", toolbar)
        zoom_out.setObjectName("timeline_zoom_out")
        zoom_out.setMaximumWidth(28)
        zoom_out.clicked.connect(lambda: self.zoom(1 / 1.5))
        toolbar_layout.addWidget(zoom_out)
        zoom_in = QPushButton("+", toolbar)
        zoom_in.setObjectName("timeline_zoom_in")
        zoom_in.setMaximumWidth(28)
        zoom_in.clicked.connect(lambda: self.zoom(1.5))
        toolbar_layout.addWidget(zoom_in)
        self.more_button = QToolButton(toolbar)
        self.more_button.setObjectName("timeline_more")
        self.more_button.setText("更多")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QMenu(self.more_button)
        self.more_button.setMenu(self.more_menu)
        toolbar_layout.addWidget(self.more_button)
        layout.addWidget(toolbar)
        fit_all = self.more_menu.addAction("适应全部")
        fit_all.setObjectName("timeline_fit_all")
        fit_all.triggered.connect(self.fit_all)
        fit_selection = self.more_menu.addAction("适应选择")
        fit_selection.setObjectName("timeline_fit_selection")
        fit_selection.triggered.connect(self.focus_selection)
        center_playhead = self.more_menu.addAction("居中播放头")
        center_playhead.setObjectName("timeline_center_playhead")
        center_playhead.triggered.connect(self.center_playhead)
        self.more_menu.addSeparator()
        navigation = QWidget(self.more_menu)
        navigation_layout = QFormLayout(navigation)
        navigation_layout.setContentsMargins(8, 4, 8, 8)
        self.loop_start = QSpinBox(navigation)
        self.loop_start.setObjectName("timeline_loop_start")
        self.loop_start.setRange(0, 10_000_000)
        self.loop_start.setSuffix(" 帧")
        self.loop_start.setToolTip("循环起始帧")
        navigation_layout.addRow("循环起点", self.loop_start)
        self.loop_end = QSpinBox(navigation)
        self.loop_end.setObjectName("timeline_loop_end")
        self.loop_end.setRange(0, 10_000_000)
        self.loop_end.setSuffix(" 帧")
        self.loop_end.setToolTip("循环结束帧")
        navigation_layout.addRow("循环终点", self.loop_end)
        self.loop_button = QPushButton("范围循环", navigation)
        self.loop_button.setObjectName("timeline_loop")
        self.loop_button.setCheckable(True)
        self.loop_button.setToolTip("使用此时间范围和正在运行的构建；每次循环均从头快进。")
        self.loop_button.toggled.connect(self._validate_loop_range)
        navigation_layout.addRow(self.loop_button)
        range_action = QWidgetAction(self.more_menu)
        range_action.setDefaultWidget(navigation)
        self.more_menu.addAction(range_action)
        self.loop_start.valueChanged.connect(self._loop_range_changed)
        self.loop_end.valueChanged.connect(self._loop_range_changed)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("timeline_scroll")
        self.scroll.setWidgetResizable(True)
        self.canvas = TimelineCanvas(session, self.scroll)
        self.canvas.edit_requested.connect(self._edit_interval_requested)
        self.canvas.drag_feedback.connect(self._show_drag_feedback)
        self.canvas.seek_requested.connect(self._request_seek)
        self.canvas.zoom_requested.connect(self.zoom)
        self.scroll.setWidget(self.canvas)
        self.scroll.horizontalScrollBar().valueChanged.connect(lambda _value: self.canvas.update())
        self.scroll.verticalScrollBar().valueChanged.connect(lambda _value: self.canvas.update())
        layout.addWidget(self.scroll)

        session.project_changed.connect(self.refresh)
        session.program_changed.connect(self.refresh)
        session.selection_changed.connect(self._selection_changed)
        session.trace_changed.connect(self._refresh_trace)
        session.preview_changed.connect(self._preview_state_changed)
        self.refresh()
        self._preview_state_changed(session.preview_state)

    def set_preview_owner(self, owner) -> None:
        """Bind controls to the one real preview owner, not the edited source."""

        if self._preview_owner is not owner:
            if self._preview_owner is not None:
                self._preview_owner.process_changed.disconnect(self._preview_process_changed)
            self._preview_owner = owner
            owner.process_changed.connect(self._preview_process_changed)
        self._preview_state_changed(self.session.preview_state)

    def _preview_process_changed(self) -> None:
        self._sync_seek_availability()
        self._update_status()

    def refresh(self) -> None:
        unit = self._projected_unit()
        root = self.session.project_context.root if self.session.project_context else None
        key = (id(self.session.program), unit.id, root) if unit is not None and self.session.is_open else None
        if key != self._projection_key:
            self._projection_key = key
            self._static_projection = (
                project_timeline(self.session.program, unit, project_root=root)
                if key is not None else None
            )
        self._refresh_trace()
        self._selection_changed()

    def _projected_unit(self):
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
        return unit

    def _refresh_trace(self) -> None:
        if self._frame_run_id != self.session.trace_run_id:
            self._frame_payload = None
            self._frame_run_id = self.session.trace_run_id
        self.projection = self._static_projection
        if self.projection is not None and self.session.trace_run_id:
            self.projection = overlay_trace(
                self.projection, self._trace_for_scope(), self.session.trace_run_id
            )
        frame = self._frame_for_scope(self._frame_payload or {})
        self.canvas.cursor_available = frame is not None
        self.canvas.set_projection(
            self.projection,
            selected_uid=self.session.current_node_uid,
            cursor_frame=frame or 0,
        )
        range_scope = (
            (self.session.source_project.root, self.projection.unit_id)
            if self.projection is not None else None
        )
        if range_scope != self._loop_range_scope:
            self._loop_range_scope = range_scope
            self.loop_button.setChecked(False)
            self.loop_start.setValue(0)
            self.loop_end.setValue(
                max(1, _maximum_known_frame(self.projection))
                if self.projection is not None else 0
            )
            self._auto_fit_pending = self.projection is not None
            if self._auto_fit_pending:
                QTimer.singleShot(0, self._fit_new_content)
        self._sync_seek_availability()
        self._update_status()

    def _trace_for_scope(self):
        unit = self._projected_unit()
        if unit is None:
            return ()
        values = []
        for event in self.session.trace_events:
            if unit.kind == "Stage":
                if event.get("stage_id") == unit.id:
                    values.append(event)
            elif event.get("unit_id") == unit.id:
                frame = event.get("unit_frame")
                if _is_literal_int(frame):
                    values.append({**event, "frame": frame})
        return tuple(values)

    def _frame_for_scope(self, payload: dict) -> int | None:
        unit = self._projected_unit()
        if unit is None:
            return None
        if unit.kind == "Stage":
            frame = payload.get("stage_frame") if payload.get("stage_id") == unit.id else None
        else:
            frame = payload.get("unit_frames", {}).get(unit.id)
        return frame if _is_literal_int(frame) else None

    def _selection_changed(self) -> None:
        unit = self._projected_unit()
        projected_id = self._static_projection.unit_id if self._static_projection else None
        if (unit.id if unit is not None else None) != projected_id:
            self.refresh()
            return
        self.canvas.selected_uid = self.session.current_node_uid
        self.canvas.update()
        if self.session.current_node_uid != self._revealed_uid:
            self._revealed_uid = self.session.current_node_uid
            if not self.canvas.is_interacting:
                self._reveal_selected(self.session.current_node_uid)
        self._update_status()

    def _show_drag_feedback(self, message: str) -> None:
        if message:
            self.status_label.setText(message)
        else:
            self._update_status()

    def _edit_interval_requested(self, uid: str, value: int) -> None:
        try:
            self.edit_interval(uid, value)
        except ProgramError as exc:
            self.status_label.setText(f"时间线未修改：{exc.message}")

    def _reveal_selected(self, uid: str | None) -> None:
        """Scroll a program-flow selection into the visible Timeline viewport."""

        if uid is None or self.projection is None or self.canvas.is_interacting:
            return
        painted = self.canvas.interval_geometry(uid)
        if painted is None:
            return
        rect = painted.rect
        horizontal = self.scroll.horizontalScrollBar()
        viewport_width = self.scroll.viewport().width()
        if rect.left() < horizontal.value() + _ORIGIN_X:
            horizontal.setValue(round(max(0.0, rect.left() - _ORIGIN_X - 24)))
        elif rect.right() > horizontal.value() + viewport_width:
            horizontal.setValue(round(rect.right() - viewport_width + 24))
        vertical = self.scroll.verticalScrollBar()
        viewport_height = self.scroll.viewport().height()
        row_top = _RULER_HEIGHT + int((rect.top() - _RULER_HEIGHT) // (_LANE_HEIGHT + _LANE_GAP)) * (_LANE_HEIGHT + _LANE_GAP)
        row_bottom = row_top + _LANE_HEIGHT
        if row_top < vertical.value() + _RULER_HEIGHT:
            vertical.setValue(max(0, row_top - _RULER_HEIGHT))
        elif row_bottom > vertical.value() + viewport_height:
            padding = min(8, max(0, viewport_height - _RULER_HEIGHT - _LANE_HEIGHT))
            vertical.setValue(max(0, row_bottom - viewport_height + padding))

    def handle_preview_event(self, message: dict) -> None:
        if message.get("run_id") != self.session.trace_run_id:
            return
        event = message.get("event")
        if event == "frame":
            self._frame_payload = dict(message.get("payload", {}))
            self._frame_run_id = self.session.trace_run_id
            frame = self._frame_for_scope(self._frame_payload)
            self.canvas.cursor_available = frame is not None
            if isinstance(frame, int) and not isinstance(frame, bool):
                self.canvas.set_cursor_frame(frame)
                self._update_seek_progress(frame)
                if (
                    self.loop_button.isChecked()
                    and not self._loop_seek_pending
                    and self.session.preview_state == "running"
                    and self.canvas.seek_enabled
                    and self._loop_bound_scope == self._scope_identity()
                    and self.loop_end.value() > self.loop_start.value()
                    and frame >= self.loop_end.value()
                ):
                    self._loop_seek_pending = True
                    self._request_seek(self.loop_start.value())
        elif event == "state":
            state = message.get("payload", {}).get("state")
            if state == "seeking":
                target = message.get("payload", {}).get("frame")
                if isinstance(target, int) and not isinstance(target, bool):
                    self._seek_target = target
                self.seek_progress.setVisible(True)
                self._update_seek_progress(self.canvas.cursor_frame)
            elif state == "running":
                self._loop_seek_pending = False

    def fit_all(self) -> None:
        self._auto_fit_pending = False
        maximum = max(60, _maximum_known_frame(self.projection), self.canvas._maximum)
        available = max(180, self.scroll.viewport().width() - _ORIGIN_X - 36)
        self.canvas.pixels_per_frame = min(_MAX_ZOOM, max(_MIN_ZOOM, available / maximum))
        self.canvas.set_projection(
            self.projection,
            selected_uid=self.session.current_node_uid,
            cursor_frame=self.canvas.cursor_frame,
        )
        self.scroll.horizontalScrollBar().setValue(0)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._auto_fit_pending:
            QTimer.singleShot(0, self._fit_new_content)

    def _fit_new_content(self) -> None:
        if not self._auto_fit_pending or not self.isVisible():
            return
        self.fit_all()
        self._reveal_selected(self.session.current_node_uid)

    def focus_selection(self) -> None:
        self._auto_fit_pending = False
        if self.projection is None or not self.session.current_node_uid:
            return
        interval = self.projection.find(self.session.current_node_uid)
        if interval is None:
            return
        if isinstance(interval.start, int) and isinstance(interval.end, int):
            duration = max(1, interval.end - _display_start(interval))
            available = max(180, self.scroll.viewport().width() - _ORIGIN_X - 36)
            self.canvas.pixels_per_frame = min(_MAX_ZOOM, max(_MIN_ZOOM, available / duration))
            self.canvas.set_projection(
                self.projection,
                selected_uid=self.session.current_node_uid,
                cursor_frame=self.canvas.cursor_frame,
            )
        frame = interval.observed_start
        if frame is None and isinstance(interval.start, int):
            frame = (
                round((_display_start(interval) + interval.end) / 2)
                if isinstance(interval.end, int)
                else interval.start
            )
        if frame is not None:
            self._center_frame(frame)

    def center_playhead(self) -> None:
        if self.canvas.cursor_available:
            self._center_frame(self.canvas.cursor_frame)

    def _center_frame(self, frame: int) -> None:
        x = _ORIGIN_X + max(0, int(frame)) * self.canvas.pixels_per_frame
        bar = self.scroll.horizontalScrollBar()
        bar.setValue(round(x - self.scroll.viewport().width() / 2))

    def zoom(self, factor: float, anchor_x: float | None = None) -> None:
        self._auto_fit_pending = False
        bar = self.scroll.horizontalScrollBar()
        old_scroll = bar.value()
        if anchor_x is None:
            anchor_x = old_scroll + self.scroll.viewport().width() / 2
        frame = max(0, (anchor_x - _ORIGIN_X) / self.canvas.pixels_per_frame)
        self.canvas.zoom(factor)
        bar.setValue(round(old_scroll + _ORIGIN_X + frame * self.canvas.pixels_per_frame - anchor_x))

    def _scope_identity(self) -> tuple[str | None, str] | None:
        return (self.session.trace_run_id, self.projection.unit_id) if self.projection is not None else None

    def _request_seek(self, frame: int) -> None:
        self._sync_seek_availability()
        if not self.canvas.seek_enabled:
            self.status_label.setText(self.canvas.seek_reason)
            self.status_label.setToolTip(self.canvas.seek_reason)
            self._loop_seek_pending = False
            return
        self.seek_requested.emit(frame)

    def _sync_seek_availability(self) -> None:
        unit_id = self.projection.unit_id if self.projection is not None else None
        reason = (self._preview_owner.seek_unavailable_reason(unit_id)
                  if self._preview_owner is not None and unit_id is not None
                  else "请先选择可运行的内容并运行预览。")
        self.canvas.seek_enabled = not reason
        self.canvas.seek_reason = reason
        self.loop_button.setEnabled(not reason)
        self.loop_button.setToolTip(reason or "循环此范围；使用正在运行的构建，每次从头快进。")
        if self.loop_button.isChecked() and (
            self._loop_bound_scope != self._scope_identity()
            or self.session.preview_state in {"stopped", "stopping", "error"}
        ):
            self.loop_button.setChecked(False)

    def _validate_loop_range(self, enabled: bool) -> None:
        if enabled and (not self.canvas.seek_enabled or self.loop_end.value() <= self.loop_start.value()):
            self.loop_button.setChecked(False)
            self.status_label.setText(self.canvas.seek_reason or "循环终点必须大于起点。")
            return
        self._loop_bound_scope = self._scope_identity() if enabled else None
        if not enabled:
            self._loop_seek_pending = False

    def _loop_range_changed(self, _value: int) -> None:
        self._loop_seek_pending = False
        if self.loop_button.isChecked() and self.loop_end.value() <= self.loop_start.value():
            self.loop_button.setChecked(False)
            self.status_label.setText("循环已关闭：终点必须大于起点。")

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
            raise ProgramError("timeline_edit", "帧数必须是大于或等于零的整数")
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
                "只能直接拖动固定帧数的等待、持续时间和定时执行；表达式请到属性中修改",
            )
        self.session.set_node_argument(uid, argument, value)

    def _preview_state_changed(self, state: str) -> None:
        self._sync_seek_availability()
        self._update_status()
        if state != "seeking":
            self._seek_target = None
            self.seek_progress.setVisible(False)
        if state in {"stopped", "error"}:
            self._loop_seek_pending = False

    def _update_status(self) -> None:
        projection = self.projection
        if projection is None:
            self.status_label.setText("时间安排 · 请选择内容")
            self.status_label.setToolTip("")
            return
        dynamic = sum(
            1
            for interval in projection.all_intervals()
            if isinstance(interval.start, Unknown) or isinstance(interval.end, Unknown)
        )
        actual = "旧构建" if self.session.preview_stale else "本次运行"
        if not projection.trace_run_id:
            actual = "尚未运行"
        scope = "当前关卡" if self.scope_combo.currentIndex() == 1 else "当前内容"
        metrics = " · 已记录弹幕密度" if projection.metrics else ""
        clock = " · 此内容当前不在运行" if not self.canvas.cursor_available else ""
        pending = f" · {dynamic} 项需运行确定时间" if dynamic else ""
        if not projection.trace_run_id:
            self.status_label.setText("预计时间 · 尚未预览")
        elif self.session.preview_stale:
            self.status_label.setText("预计时间 · 橙线为修改前的运行记录")
        else:
            self.status_label.setText("预计时间 · 橙线为实际运行")
        self.status_label.setToolTip(
            self.status_label.text() + "\n"
            "左列按源码步骤顺序排列，缩进表示章节；右侧按帧数显示时间。\n"
            "展开时间线可同时查看更多步骤；短时间块的完整信息见悬停提示。\n"
            f"{scope} · {len(projection.all_intervals())} 项{pending}{metrics}{clock}\n"
            f"区块显示当前源码预计；橙线显示{actual}的实际时间。\n"
            "条件分支、表达式和脚本的时间需要运行后才能确定。\n"
            f"运行记录 ID：{projection.trace_run_id or '尚未运行'}\n"
            f"弹幕密度记录：{len(projection.metrics)} 个采样"
            + (f"\n不能定位：{self.canvas.seek_reason}" if self.canvas.seek_reason else "")
        )


def _is_literal_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _drag_mode(interval: TimelineInterval) -> str:
    if not (_is_literal_int(interval.start) and _is_literal_int(interval.end)):
        return "none"
    return interval.editable


def _display_start(interval: TimelineInterval) -> int | Unknown:
    """Show a timed block at activation, not at the wait preceding At."""

    if interval.editable == "at" and _drag_mode(interval) == "at":
        if interval.children and _is_literal_int(interval.children[0].start):
            return interval.children[0].start
        if not interval.children:
            return interval.end
    return interval.start


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
    segment = lane.rsplit("/", 1)[-1]
    if segment.startswith("parallel:"):
        return "并行分支 " + segment.rsplit(":", 1)[-1]
    if segment.startswith("body:"):
        return "嵌套内容"
    if segment.startswith("spawn:"):
        return "后台任务"
    if segment.startswith("branch:"):
        return {"then": "条件成立", "else": "否则"}.get(segment.rsplit(":", 1)[-1], "条件分支")
    if segment.startswith("wave:"):
        return "波次"
    if segment.startswith("boss:"):
        return "Boss 阶段"
    if segment.startswith("call:"):
        return "调用"
    return "流程"


def _interval_label(label: str) -> str:
    kind, separator, detail = label.partition(" · ")
    return _NODE_LABELS.get(kind, kind) + separator + detail


def _source_node_label(node) -> str:
    label = _NODE_LABELS.get(node.kind, node.kind)
    if node.kind == "Wait" and _is_literal_int(node.arguments.get("frames")):
        return f"{label} {node.arguments['frames']} 帧"
    if node.kind == "Repeat":
        count = node.arguments.get("count")
        if _is_literal_int(count):
            return f"{label} {count} 次"
    if node.kind.startswith("Fire") and _is_literal_int(node.arguments.get("count")):
        return f"{label} {node.arguments['count']} 发"
    if node.kind == "At" and _is_literal_int(node.arguments.get("frame")):
        return f"{label} 第 {node.arguments['frame']} 帧"
    if _is_literal_int(node.arguments.get("duration")):
        return f"{label} {node.arguments['duration']} 帧"
    return label


def _ruler_step(scale: float) -> int:
    target = max(1, 80 / scale)
    if target <= 60:
        return next(value for value in (1, 2, 5, 10, 15, 30, 60) if value >= target)
    base = 60
    while base * 10 < target:
        base *= 10
    return next(base * multiplier for multiplier in (1, 2, 5, 10) if base * multiplier >= target)


__all__ = ["TimelineCanvas", "TimelinePanel", "_layout_timeline_intervals"]

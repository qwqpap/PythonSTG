"""Custom-painted vertical block flow with visible four-zone drag feedback.

The flow is a direct projection of the current :class:`LogicalUnit`; it owns no
second model and turns each accepted drop into exactly one model intent.
Parallel branches render side by side on wide viewports and stack vertically
when there is not enough width.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from src.authoring import dsl
from src.authoring.program import (
    DropCheck,
    DropPlacement,
    LogicalUnit,
    Node,
    Ref,
)
from src.qt_compat.QtCore import (
    QElapsedTimer,
    QMimeData,
    QPoint,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from src.qt_compat.QtGui import QColor, QDrag, QDragMoveEvent, QDropEvent, QPainter, QPen
from src.qt_compat.QtWidgets import QScrollArea, QWidget

from .node_palette import PROTOTYPE_MIME, _CATEGORY_COLORS, _DEFAULT_COLOR, entry_for_kind
from .sidebars import RESOURCE_MIME


NODE_MIME = "application/x-pystg-node"
_ZONE_LABELS = {
    DropPlacement.BEFORE: "放到之前",
    DropPlacement.AFTER: "放到之后",
    DropPlacement.CHILD: "作为子项",
    DropPlacement.WRAP: "包裹目标",
}
_SLOT_LABELS = {
    ("If", "body"): "条件成立",
    ("If", "else_body"): "否则",
    ("Parallel", "branches"): "并行分支",
    ("Branch", "body"): "分支内容",
    ("SpawnTask", "body"): "后台任务内容",
}
_SUMMARY_FIELDS = {
    "Wait": "frames", "At": "frame", "Repeat": "count", "RunWave": "wave_class",
    "RunBoss": "boss_def", "SpawnEnemy": "enemy_class", "PlayBGM": "name",
    "PlaySE": "name", "MoveTo": "duration", "FireCircle": "count",
    "Set": "name", "SpawnTask": "task", "ForEach": "target",
}
_COLLAPSE_DELAY_MS = 450
_AUTOSCROLL_INTERVAL_MS = 16
_AUTOSCROLL_EDGE_PX = 28
_AUTOSCROLL_STEP_PX = 10
_MIN_COLUMN_WIDTH = 230
_ZONE_PANEL_WIDTH = 280
_ZONE_PANEL_HEIGHT = 180
_ZONE_STRIP = 0.34

_MARGIN = 12
_CARD_HEIGHT = 34
_CARD_GAP = 8
_INDENT = 24
_HEAD_HEIGHT = 20
_LANDING_HEIGHT = 34
_NEW_BRANCH_HEIGHT = 28
_MIN_CONTENT_WIDTH = 520


# Palette ---------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceInsertAction:
    key: str
    label: str


def available_resource_actions(uri: str) -> tuple[ResourceInsertAction, ...]:
    path = PurePosixPath(uri.removeprefix("res://").split("#", 1)[0])
    suffix = path.suffix.lower()
    actions: list[ResourceInsertAction] = []
    if suffix in {".flac", ".mp3", ".ogg", ".wav"}:
        actions.extend(
            (
                ResourceInsertAction("play_bgm", "插入播放 BGM"),
                ResourceInsertAction("play_se", "插入播放音效"),
            )
        )
    if suffix == ".json":
        actions.extend(
            (
                ResourceInsertAction("set_background", "插入切换背景"),
                ResourceInsertAction("play_dialogue", "插入播放对话"),
            )
        )
    return tuple(actions)


def node_for_resource_action(action: str, uri: str) -> Node:
    factories = {
        "play_bgm": dsl.PlayBGM,
        "play_se": dsl.PlaySE,
        "set_background": dsl.SetBackground,
        "play_dialogue": dsl.PlayDialogue,
    }
    try:
        return factories[action](uri)
    except KeyError as exc:
        raise ValueError(f"unknown resource action: {action}") from exc


def node_label(node: Node) -> str:
    """The Chinese display label used on cards and in drop previews."""

    if node.kind == "Branch":
        return "并行分支"
    if node.kind == "TemplateCall":
        template = node.template
        name = (template.display_name or template.symbol) if template else "模板"
        return f"模板 · {name}"
    try:
        return entry_for_kind(node.kind).label
    except StopIteration:
        return node.kind


def node_summary(node: Node) -> str:
    """One short human-readable parameter digest; Exprs stay visible as code."""

    field_name = _SUMMARY_FIELDS.get(node.kind)
    value = node.arguments.get(field_name) if field_name else None
    if isinstance(value, Ref):
        return f"→ {value.id}"
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return repr(value)


def node_is_dynamic(node: Node) -> bool:
    stack: list = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dsl.Expr):
            return True
        if isinstance(current, Node):
            stack.extend(current.arguments.values())
            for children in current.children.values():
                stack.extend(children)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
        elif isinstance(current, dict):
            stack.extend(current.values())
    return False


# Layout ----------------------------------------------------------------------


@dataclass
class _Element:
    kind: str  # "card" | "head" | "landing" | "folded" | "branch_border" | "new_branch"
    rect: QRect
    node: Node | None = None
    uid: str | None = None
    slot: str | None = None
    label: str = ""
    depth: int = 0


@dataclass
class _Layout:
    elements: list[_Element] = field(default_factory=list)
    cards: dict[str, _Element] = field(default_factory=dict)
    root_landing: _Element | None = None


class _FlowCanvas(QWidget):
    """Paints node cards and owns all hit-testing and drag feedback."""

    node_selected = Signal(object)
    node_activated = Signal(str)
    move_requested = Signal(str, str, str, object)
    prototype_requested = Signal(str, object, str, object)
    resource_action_requested = Signal(str, str, str, object)
    drop_feedback = Signal(str)

    def __init__(self, flow: "ProgramFlow", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._flow = flow
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._unit: LogicalUnit | None = None
        self._layout = _Layout()
        self._collapsed: set[str] = set()
        self._diagnostics: dict[str, tuple[str, ...]] = {}
        self._drop_active = False
        self._drop_candidate: tuple[str | None, DropPlacement, str | None] | None = None
        self._drop_check = DropCheck(False, "")
        self._panel_uid: str | None = None
        self._panel_rect: QRect | None = None
        self._flash_uid: str | None = None
        self._press_card: str | None = None
        self._press_pos = QPoint()
        self._hover_uid: str | None = None
        self._hover_since = QElapsedTimer()
        self._autoscroll_direction = 0
        self._layout_width: int | None = None
        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(_AUTOSCROLL_INTERVAL_MS)
        self._autoscroll_timer.timeout.connect(self._autoscroll_step)
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._clear_flash)

    # -- public state ---------------------------------------------------------

    def set_unit(self, unit: LogicalUnit | None, selected_uid: str | None) -> None:
        self._unit = unit
        self._layout = _Layout()
        self._end_drop()
        if unit is not None:
            known = self._unit_uids(unit)
            self._collapsed &= known
        self.relayout()
        if selected_uid:
            self.reveal(selected_uid)
        self.update()

    def set_diagnostics(self, diagnostics: dict[str, tuple[str, ...]]) -> None:
        self._diagnostics = dict(diagnostics)
        self.update()

    def collapse(self, uid: str) -> None:
        if uid in self._collapsed:
            return
        self._collapsed.add(uid)
        self.relayout()
        self.update()

    def expand(self, uid: str) -> None:
        if uid not in self._collapsed:
            return
        self._collapsed.discard(uid)
        self.relayout()
        self.update()

    def flash(self, uid: str) -> None:
        self._flash_uid = uid
        self.reveal(uid)
        self._flash_timer.start(700)
        self.update()

    def _clear_flash(self) -> None:
        self._flash_uid = None
        self.update()

    def reveal(self, uid: str) -> None:
        element = self._layout.cards.get(uid)
        if element is None:
            return
        bar = self._flow.verticalScrollBar()
        visible = self._flow.viewport().height()
        target = element.rect.center().y() - visible // 2
        bar.setValue(max(0, min(bar.maximum(), target)))

    def rect_for_uid(self, uid: str) -> QRect | None:
        element = self._layout.cards.get(uid)
        return QRect(element.rect) if element else None

    def visible_rect(self) -> QRect:
        bar = self._flow.verticalScrollBar()
        return QRect(0, bar.value(), self.width(), self._flow.viewport().height())

    # -- layout ---------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        if self._layout_width != self.width():
            self.relayout()
            self.update()
        super().resizeEvent(event)

    def relayout(self) -> None:
        self._layout = _Layout()
        self._layout_width = self.width()
        width = max(self.width(), _MIN_CONTENT_WIDTH) - 2 * _MARGIN
        y = _MARGIN
        if self._unit is not None:
            if self._unit.body:
                y = self._layout_nodes(self._unit.body, _MARGIN, y, width, 0)
                y += _CARD_GAP
            visible = max(self._flow.viewport().height(), 320)
            landing_height = max(120, visible - y - _MARGIN)
            landing = _Element(
                "landing",
                QRect(_MARGIN, y, width, landing_height),
                label="拖到这里添加第一个节点",
            )
            self._layout.elements.append(landing)
            self._layout.root_landing = landing
            y += landing_height
        self.setMinimumHeight(y + _MARGIN)

    def _layout_nodes(
        self, nodes: list[Node], x: int, y: int, width: int, depth: int
    ) -> int:
        for node in nodes:
            y = self._layout_node(node, x, y, width, depth)
        return y

    def _layout_node(self, node: Node, x: int, y: int, width: int, depth: int) -> int:
        if node.kind == "Branch":
            return self._layout_branch_children(node, x, y, width, depth)
        card = _Element(
            "card",
            QRect(x, y, width, _CARD_HEIGHT),
            node=node,
            uid=node.uid,
            label=node_label(node),
            depth=depth,
        )
        self._layout.elements.append(card)
        self._layout.cards[node.uid] = card
        y += _CARD_HEIGHT + _CARD_GAP
        slots = self._child_slots(node)
        if not slots:
            return y
        if node.uid in self._collapsed:
            total = self._count_descendants(node)
            folded = _Element(
                "folded",
                QRect(x + _INDENT, y, width - _INDENT, _HEAD_HEIGHT),
                uid=node.uid,
                label=f"已折叠 {total} 个节点",
                depth=depth,
            )
            self._layout.elements.append(folded)
            return y + _HEAD_HEIGHT + _CARD_GAP
        inner_x = x + _INDENT
        inner_width = width - _INDENT
        for slot, label in slots:
            children = node.children.get(slot, [])
            header = _Element(
                "head",
                QRect(inner_x, y, inner_width, _HEAD_HEIGHT),
                node=node,
                uid=node.uid,
                slot=slot,
                label=label,
                depth=depth + 1,
            )
            self._layout.elements.append(header)
            y += _HEAD_HEIGHT
            if node.kind == "Parallel" and slot == "branches":
                y = self._layout_parallel(node, inner_x, y, inner_width, depth + 1)
            else:
                if children:
                    y = self._layout_nodes(children, inner_x, y, inner_width, depth + 1)
                    y += _CARD_GAP
                else:
                    landing_label = f"{label} · 拖到这里添加内容"
                    y = self._layout_landing(
                        node, slot, landing_label, inner_x, y, inner_width, depth + 1
                    )
        return y + _CARD_GAP

    def _layout_parallel(
        self, parallel: Node, x: int, y: int, width: int, depth: int
    ) -> int:
        branches = parallel.children.get("branches", [])
        # Column layout is decided by the real viewport width, not the floored
        # content width, so narrow windows stack branches vertically instead of
        # forcing horizontal scrolling.
        effective = min(width, self.width() - 2 * _MARGIN)
        column_mode = bool(branches) and effective // len(branches) >= _MIN_COLUMN_WIDTH
        if column_mode:
            column_width = width // len(branches)
            top = y
            bottom = y
            for index, branch in enumerate(branches):
                column_x = x + index * column_width
                branch_bottom = self._layout_branch(
                    parallel, branch, index, column_x, top, column_width, depth
                )
                bottom = max(bottom, branch_bottom)
            y = bottom
        else:
            for index, branch in enumerate(branches):
                y = self._layout_branch(parallel, branch, index, x, y, width, depth)
                y += _CARD_GAP
        landing = _Element(
            "new_branch",
            QRect(x, y, width, _NEW_BRANCH_HEIGHT),
            node=parallel,
            uid=parallel.uid,
            slot="new_branch",
            label="＋ 新建分支",
            depth=depth,
        )
        self._layout.elements.append(landing)
        return y + _NEW_BRANCH_HEIGHT + _CARD_GAP

    def _layout_branch(
        self, parallel: Node, branch: Node, index: int, x: int, y: int, width: int, depth: int
    ) -> int:
        head = _Element(
            "head",
            QRect(x, y, width, _HEAD_HEIGHT),
            node=branch,
            uid=branch.uid,
            slot="body",
            label=f"分支 {index + 1}",
            depth=depth,
        )
        self._layout.elements.append(head)
        children = branch.children.get("body", [])
        y += _HEAD_HEIGHT
        if children:
            y = self._layout_nodes(children, x, y, width, depth)
            y += _CARD_GAP
        else:
            y = self._layout_landing(
                branch, "body", "分支内容 · 拖到这里添加内容", x, y, width, depth
            )
        return y

    def _layout_landing(
        self, node: Node, slot: str, label: str, x: int, y: int, width: int, depth: int
    ) -> int:
        landing = _Element(
            "landing",
            QRect(x, y, width, _LANDING_HEIGHT),
            node=node,
            uid=node.uid,
            slot=slot,
            label=label,
            depth=depth,
        )
        self._layout.elements.append(landing)
        return y + _LANDING_HEIGHT + _CARD_GAP

    def _layout_branch_children(self, branch: Node, x: int, y: int, width: int, depth: int) -> int:
        """A Branch reached outside its Parallel column (defensive) renders inline."""

        children = branch.children.get("body", [])
        return self._layout_nodes(children, x, y, width, depth)

    def _child_slots(self, node: Node) -> tuple[tuple[str, str], ...]:
        if node.kind == "If":
            return (("body", "条件成立"), ("else_body", "否则"))
        if node.kind == "Parallel":
            return (("branches", "并行分支"),)
        slots = tuple(node.children)
        if not slots:
            return ()
        label = _SLOT_LABELS.get((node.kind, slots[0]), "内容")
        return tuple((slot, label) for slot in slots)

    def _count_descendants(self, node: Node) -> int:
        total = 0
        for children in node.children.values():
            for child in children:
                total += 1 + self._count_descendants(child)
        return total

    def _unit_uids(self, unit: LogicalUnit) -> set[str]:
        uids: set[str] = set()

        def walk(node: Node) -> None:
            uids.add(node.uid)
            for children in node.children.values():
                for child in children:
                    walk(child)

        for node in unit.body:
            walk(node)
        return uids

    # -- painting -------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#171a20"))
        painter.translate(0, -self._flow.verticalScrollBar().value())
        for element in self._layout.elements:
            if element.kind == "card":
                self._paint_card(painter, element)
            elif element.kind == "head":
                self._paint_head(painter, element)
            elif element.kind == "landing":
                self._paint_landing(painter, element, dashed=True)
            elif element.kind == "new_branch":
                self._paint_landing(painter, element, dashed=False)
            elif element.kind == "folded":
                self._paint_folded(painter, element)
        self._paint_drop_overlay(painter)
        self._paint_flash(painter)
        painter.end()

    def _paint_card(self, painter: QPainter, element: _Element) -> None:
        node = element.node
        assert node is not None
        selected = self._flow.selected_uid == element.uid
        background = QColor("#294d70" if selected else "#252a33")
        border = QColor("#58a6e7" if selected else "#3a414e")
        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(element.rect, 6, 6)
        accent = QColor(_CATEGORY_COLORS.get(entry_for_kind(node.kind).category, _DEFAULT_COLOR)) if node.kind not in {"Branch", "TemplateCall"} else QColor("#bc8cff")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(
            QRect(element.rect.left() + 2, element.rect.top() + 6, 3, element.rect.height() - 12),
            1, 1,
        )
        x = element.rect.left() + 8
        slots = self._child_slots(node)
        if slots:
            chevron_rect = self._chevron_rect(element)
            painter.setPen(QPen(QColor("#8b949e"), 1))
            painter.setFont(self._base_font(bold=False))
            painter.drawText(
                chevron_rect, Qt.AlignmentFlag.AlignCenter,
                "▾" if node.uid not in self._collapsed else "▸",
            )
            x = chevron_rect.right() + 4
        painter.setPen(QPen(QColor("#d0d7de"), 1))
        painter.setFont(self._base_font(bold=True))
        label = element.label
        summary = node_summary(node)
        text = f"{label}  {summary}" if summary else label
        badges = self._badges(node)
        available = element.rect.width() - (x - element.rect.left()) - 12
        for chip, color in reversed(badges):
            available -= self._draw_chip(painter, element.rect, chip, color)
        metrics = painter.fontMetrics()
        painter.setPen(QPen(QColor("#d0d7de"), 1))
        painter.drawText(
            QRect(x, element.rect.top(), max(10, available), element.rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(10, available)),
        )

    def _badges(self, node: Node) -> tuple[tuple[str, str], ...]:
        badges: list[tuple[str, str]] = []
        if node_is_dynamic(node):
            badges.append(("动态", "#d29922"))
        if node.kind == "TemplateCall":
            badges.append(("模板", "#a371f7"))
        if self._diagnostics.get(node.uid):
            badges.append(("错误", "#f85149"))
        return tuple(badges)

    def _draw_chip(self, painter: QPainter, rect: QRect, text: str, color: str) -> int:
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 12
        chip = QRect(rect.right() - width - 6, rect.center().y() - 9, width, 18)
        painter.setPen(QPen(QColor(color), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(chip, 4, 4)
        painter.setPen(QPen(QColor(color), 1))
        painter.setFont(self._base_font(bold=False))
        painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)
        return width + 4

    def _paint_head(self, painter: QPainter, element: _Element) -> None:
        painter.setPen(QPen(QColor("#8b949e"), 1))
        painter.setFont(self._base_font(bold=False))
        painter.drawText(
            element.rect.adjusted(2, 0, 0, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            element.label,
        )

    def _paint_landing(self, painter: QPainter, element: _Element, *, dashed: bool) -> None:
        active = (
            self._drop_candidate is not None
            and self._drop_candidate[0] == element.uid
            and self._drop_candidate[1] == DropPlacement.CHILD
            and self._drop_candidate[2] == element.slot
        )
        if active:
            allowed = self._drop_check.allowed
            painter.setPen(QPen(QColor("#238636" if allowed else "#8b1a1a"), 2, Qt.PenStyle.SolidLine))
            painter.setBrush(QColor(35, 134, 54, 70 if allowed else 60))
        else:
            pen = QPen(QColor("#58a6e7" if dashed else "#3a414e"), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(element.rect, 6, 6)
        painter.setPen(QPen(QColor("#8b949e"), 1))
        painter.setFont(self._base_font(bold=False))
        painter.drawText(element.rect, Qt.AlignmentFlag.AlignCenter, element.label)

    def _paint_folded(self, painter: QPainter, element: _Element) -> None:
        painter.setPen(QPen(QColor("#6e7681"), 1))
        painter.setFont(self._base_font(bold=False))
        painter.drawText(
            element.rect.adjusted(2, 0, 0, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"… {element.label}",
        )

    def _paint_drop_overlay(self, painter: QPainter) -> None:
        if not self._drop_active or self._drop_candidate is None:
            return
        uid, placement, _slot = self._drop_candidate
        element = self._layout.cards.get(uid) if uid else self._layout.root_landing
        if element is None:
            return
        allowed = self._drop_check.allowed
        if element.kind == "card":
            self._paint_card_indicator(painter, element, placement, allowed)
            self._paint_zone_panel(painter)
        elif not allowed:
            painter.setPen(QPen(QColor("#8b1a1a"), 2))
            painter.drawRoundedRect(element.rect.adjusted(-2, -2, 2, 2), 6, 6)

    def _paint_card_indicator(
        self, painter: QPainter, element: _Element, placement: DropPlacement, allowed: bool
    ) -> None:
        color = QColor("#238636" if allowed else "#8b1a1a")
        rect = element.rect
        if placement == DropPlacement.BEFORE:
            painter.fillRect(QRect(rect.left(), rect.top() - 2, rect.width(), 4), color)
        elif placement == DropPlacement.AFTER:
            painter.fillRect(QRect(rect.left(), rect.bottom() - 2, rect.width(), 4), color)
        elif placement == DropPlacement.CHILD:
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
        else:
            painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))

    def _paint_zone_panel(self, painter: QPainter) -> None:
        if self._panel_rect is None:
            return
        rect = self._panel_rect
        painter.setPen(QPen(QColor("#3a414e"), 1))
        painter.setBrush(QColor("#11151a"))
        painter.drawRoundedRect(rect, 8, 8)
        strip = int(rect.height() * _ZONE_STRIP)
        zones = {
            DropPlacement.BEFORE: QRect(rect.left(), rect.top(), rect.width(), strip),
            DropPlacement.AFTER: QRect(
                rect.left(), rect.bottom() - strip + 1, rect.width(), strip
            ),
            DropPlacement.CHILD: QRect(
                rect.left(), rect.top() + strip, rect.width() // 2,
                rect.height() - 2 * strip,
            ),
            DropPlacement.WRAP: QRect(
                rect.center().x(), rect.top() + strip,
                rect.width() - rect.width() // 2, rect.height() - 2 * strip,
            ),
        }
        painter.setFont(self._base_font(bold=True))
        for placement, zone in zones.items():
            active = (
                self._drop_candidate is not None
                and self._drop_candidate[0] == self._panel_uid
                and self._drop_candidate[1] == placement
            )
            if active:
                allowed = self._drop_check.allowed
                painter.setPen(QPen(QColor("#238636" if allowed else "#8b1a1a"), 1))
                painter.setBrush(QColor(35, 134, 54, 110 if allowed else 90))
            else:
                painter.setPen(QPen(QColor("#30363d"), 1))
                painter.setBrush(QColor(48, 54, 61, 130))
            painter.drawRect(zone)
            painter.setPen(QColor("#f0f6fc" if active else "#8b949e"))
            painter.drawText(zone, Qt.AlignmentFlag.AlignCenter, _ZONE_LABELS[placement])

    def _paint_flash(self, painter: QPainter) -> None:
        if self._flash_uid is None:
            return
        element = self._layout.cards.get(self._flash_uid)
        if element is None:
            return
        painter.setPen(QPen(QColor("#238636"), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(element.rect.adjusted(-2, -2, 2, 2), 8, 8)

    def _base_font(self, *, bold: bool):
        font = self.font()
        font.setBold(bold)
        return font

    def _chevron_rect(self, element: _Element) -> QRect:
        return QRect(element.rect.left() + 4, element.rect.top() + 6, 20, 20)

    # -- hit testing ----------------------------------------------------------

    def _card_at(self, position: QPoint) -> _Element | None:
        for element in reversed(self._layout.elements):
            if element.kind == "card" and element.rect.contains(position):
                return element
        return None

    def _landing_at(self, position: QPoint) -> _Element | None:
        for element in reversed(self._layout.elements):
            if element.kind in {"landing", "new_branch"} and element.rect.contains(position):
                return element
        return None

    def _drop_target(self, position: QPoint) -> tuple[str | None, DropPlacement, str | None]:
        # Aiming inside the anchored panel always wins, even when another card
        # happens to sit underneath it: the panel is what the author sees.
        panel_zone = self._zone_from_panel(position)
        if panel_zone is not None:
            return panel_zone
        card = self._card_at(position)
        if card is not None:
            self._anchor_zone_panel(card, position)
            return self._zone_from_panel(position) or (card.uid, DropPlacement.AFTER, None)
        landing = self._landing_at(position)
        if landing is not None:
            self._panel_uid = None
            self._panel_rect = None
            if landing.kind == "new_branch":
                return landing.uid, DropPlacement.CHILD, "new_branch"
            if landing.uid is None and landing.slot is None:
                return None, DropPlacement.AFTER, None
            return landing.uid, DropPlacement.CHILD, landing.slot
        if self._layout.root_landing is not None and self._layout.root_landing.rect.contains(position):
            return None, DropPlacement.AFTER, None
        return None, DropPlacement.AFTER, None

    def _anchor_zone_panel(self, card: _Element, position: QPoint) -> None:
        """Anchor the magnified four-zone panel on the hovered card."""

        if self._panel_uid != card.uid or self._panel_rect is None:
            visible = self.visible_rect()
            x = card.rect.center().x() - _ZONE_PANEL_WIDTH // 2
            y = card.rect.center().y() - _ZONE_PANEL_HEIGHT // 2
            x = max(4, min(x, self.width() - _ZONE_PANEL_WIDTH - 4))
            y = max(
                visible.top() + 4,
                min(y, visible.bottom() - _ZONE_PANEL_HEIGHT - 4),
            )
            self._panel_uid = card.uid
            self._panel_rect = QRect(x, y, _ZONE_PANEL_WIDTH, _ZONE_PANEL_HEIGHT)

    def _zone_from_panel(self, position: QPoint) -> tuple[str, DropPlacement, str | None] | None:
        if self._panel_uid is None or self._panel_rect is None:
            return None
        if not self._panel_rect.contains(position):
            return None
        rect = self._panel_rect
        rel_y = position.y() - rect.top()
        strip = int(rect.height() * _ZONE_STRIP)
        if rel_y < strip:
            return self._panel_uid, DropPlacement.BEFORE, None
        if rel_y > rect.height() - strip:
            return self._panel_uid, DropPlacement.AFTER, None
        placement = (
            DropPlacement.CHILD
            if position.x() < rect.center().x()
            else DropPlacement.WRAP
        )
        return self._panel_uid, placement, None

    # -- mouse and keyboard ---------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        position = event.position().toPoint()
        card = self._card_at(position)
        if card is None:
            self._press_card = None
            return
        if self._chevron_rect(card).contains(position):
            self._toggle_collapse(card.uid)
            self._press_card = None
            return
        self._press_card = card.uid
        self._press_pos = position
        self._flow.selected_uid = card.uid
        self.node_selected.emit(card.uid)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        position = event.position().toPoint()
        if event.buttons() & Qt.MouseButton.LeftButton:
            card = self._press_card
            if card is not None and (position - self._press_pos).manhattanLength() > 8:
                self._start_node_drag(card)
                return
        else:
            hovered = self._card_at(position)
            if hovered is not None and hovered.node is not None:
                tooltip = f"{hovered.node.kind}\nUID: {hovered.uid}"
                problems = self._diagnostics.get(hovered.uid)
                if problems:
                    tooltip += "\n" + "\n".join(problems)
                self.setToolTip(tooltip)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press_card = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        card = self._card_at(event.position().toPoint())
        if card is not None:
            self.node_activated.emit(card.uid)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape and self._drop_candidate is not None:
            self._end_drop()
            event.accept()
            return
        if key in {Qt.Key.Key_Up, Qt.Key.Key_Down} and self._layout.cards:
            self._move_selection(-1 if key == Qt.Key.Key_Up else 1)
            event.accept()
            return
        if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self._flow.selected_uid:
            self.node_activated.emit(self._flow.selected_uid)
            event.accept()
            return
        super().keyPressEvent(event)

    def _move_selection(self, offset: int) -> None:
        cards = [element for element in self._layout.elements if element.kind == "card"]
        if not cards:
            return
        index = next(
            (
                position
                for position, element in enumerate(cards)
                if element.uid == self._flow.selected_uid
            ),
            None,
        )
        target = 0 if index is None else max(0, min(len(cards) - 1, index + offset))
        self._flow.selected_uid = cards[target].uid
        self.node_selected.emit(cards[target].uid)
        self.reveal(cards[target].uid)
        self.update()

    def _toggle_collapse(self, uid: str) -> None:
        if uid in self._collapsed:
            self._collapsed.discard(uid)
        else:
            self._collapsed.add(uid)
        self.relayout()
        self.update()

    def _start_node_drag(self, uid: str) -> None:
        mime = QMimeData()
        mime.setData(NODE_MIME, uid.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        self._drop_active = True
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._end_drop()

    # -- drag and drop --------------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if any(
            event.mimeData().hasFormat(value)
            for value in (NODE_MIME, PROTOTYPE_MIME, RESOURCE_MIME)
        ):
            self._drop_active = True
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        position = event.position().toPoint()
        uid, placement, slot = self._drop_target(position)
        self._drop_candidate = (uid, placement, slot)
        self._drop_check = self._flow.validate(event.mimeData(), uid, placement, slot)
        if self._drop_check.allowed:
            event.acceptProposedAction()
        else:
            event.ignore()
        self.drop_feedback.emit(
            self._drop_check.reason or self._preview_text(event.mimeData(), uid, placement)
        )
        self._update_autoscroll(position)
        self._update_hover_expand(uid)
        self.update()

    def dragLeaveEvent(self, event) -> None:
        self._end_drop()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        position = event.position().toPoint()
        uid, placement, slot = self._drop_target(position)
        check = self._flow.validate(event.mimeData(), uid, placement, slot)
        mime = event.mimeData()
        if not check.allowed:
            self.drop_feedback.emit(check.reason)
            self._end_drop()
            event.ignore()
            return
        if mime.hasFormat(PROTOTYPE_MIME):
            kind = bytes(mime.data(PROTOTYPE_MIME)).decode("utf-8")
            self.prototype_requested.emit(kind, uid, placement.value, slot)
        elif mime.hasFormat(NODE_MIME):
            source_uid = bytes(mime.data(NODE_MIME)).decode("utf-8")
            self.move_requested.emit(source_uid, uid or "", placement.value, slot)
        elif mime.hasFormat(RESOURCE_MIME):
            uri = bytes(mime.data(RESOURCE_MIME)).decode("utf-8")
            self.resource_action_requested.emit(uri, uid or "", placement.value, slot)
        event.acceptProposedAction()
        self._end_drop()

    def _preview_text(self, mime: QMimeData, uid: str | None, placement: DropPlacement) -> str:
        subject = "节点"
        if mime.hasFormat(PROTOTYPE_MIME):
            kind = bytes(mime.data(PROTOTYPE_MIME)).decode("utf-8")
            try:
                subject = entry_for_kind(kind).label
            except StopIteration:
                subject = kind
        elif mime.hasFormat(NODE_MIME):
            source_uid = bytes(mime.data(NODE_MIME)).decode("utf-8")
            element = self._layout.cards.get(source_uid)
            if element is not None:
                subject = element.label
        elif mime.hasFormat(RESOURCE_MIME):
            subject = "资源"
        target = self._layout.cards.get(uid) if uid else None
        target_label = target.label if target is not None else "程序"
        if placement == DropPlacement.WRAP:
            return f"把 {target_label} 包裹在 {subject} 外层"
        if placement == DropPlacement.CHILD:
            return f"把 {subject} 放入 {target_label}"
        if placement == DropPlacement.BEFORE:
            return f"插入到 {target_label} 之前"
        return f"插入到 {target_label} 之后"

    def _end_drop(self) -> None:
        self._drop_active = False
        self._drop_candidate = None
        self._drop_check = DropCheck(False, "")
        self._panel_uid = None
        self._panel_rect = None
        self._hover_uid = None
        self._autoscroll_direction = 0
        self._autoscroll_timer.stop()
        self.update()

    # -- drag helpers ---------------------------------------------------------

    def _update_autoscroll(self, position: QPoint) -> None:
        visible = self.visible_rect()
        if position.y() < visible.top() + _AUTOSCROLL_EDGE_PX:
            self._autoscroll_direction = -1
        elif position.y() > visible.bottom() - _AUTOSCROLL_EDGE_PX:
            self._autoscroll_direction = 1
        else:
            self._autoscroll_direction = 0
        if self._autoscroll_direction:
            self._autoscroll_timer.start()
        else:
            self._autoscroll_timer.stop()

    def _autoscroll_step(self) -> None:
        if not self._autoscroll_direction:
            self._autoscroll_timer.stop()
            return
        bar = self._flow.verticalScrollBar()
        bar.setValue(max(0, min(bar.maximum(), bar.value() + self._autoscroll_direction * _AUTOSCROLL_STEP_PX)))

    def _update_hover_expand(self, uid: str | None) -> None:
        card = self._layout.cards.get(uid) if uid else None
        collapsible = card is not None and card.node is not None and self._child_slots(card.node)
        if not collapsible:
            self._hover_uid = None
            return
        if uid != self._hover_uid:
            self._hover_uid = uid
            self._hover_since.restart()
            return
        if uid in self._collapsed and self._hover_since.elapsed() >= _COLLAPSE_DELAY_MS:
            self.expand(uid)


class ProgramFlow(QScrollArea):
    """Scrollable custom-drawn block flow for the current logical unit."""

    node_selected = Signal(object)
    node_activated = Signal(str)
    move_requested = Signal(str, str, str, object)
    prototype_requested = Signal(str, object, str, object)
    resource_action_requested = Signal(str, str, str, object)
    drop_feedback = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("program_flow")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet(
            "QScrollArea { background: #171a20; border: 0; }"
            "QScrollBar:vertical { background: #171a20; width: 10px; }"
            "QScrollBar::handle:vertical { background: #3a414e; border-radius: 4px; "
            "min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self.selected_uid: str | None = None
        self._validator = None
        self.canvas = _FlowCanvas(self)
        self.setWidget(self.canvas)
        self.canvas.node_selected.connect(self._forward_selection)
        self.canvas.node_activated.connect(self.node_activated)
        self.canvas.move_requested.connect(self.move_requested)
        self.canvas.prototype_requested.connect(self.prototype_requested)
        self.canvas.resource_action_requested.connect(self.resource_action_requested)
        self.canvas.drop_feedback.connect(self.drop_feedback)

    def set_drop_validator(self, callback) -> None:
        self._validator = callback

    def validate(self, mime, uid, placement, slot) -> DropCheck:
        if self._validator is None:
            return DropCheck(True)
        return self._validator(mime, uid, placement, slot)

    def set_unit(self, unit: LogicalUnit | None, selected_uid: str | None = None) -> None:
        self.selected_uid = selected_uid
        self.canvas.set_unit(unit, selected_uid)

    def set_diagnostics(self, diagnostics) -> None:
        self.canvas.set_diagnostics(diagnostics)

    def flash(self, uid: str) -> None:
        self.canvas.flash(uid)

    def reveal(self, uid: str) -> None:
        self.canvas.reveal(uid)

    def collapse(self, uid: str) -> None:
        self.canvas.collapse(uid)

    def expand(self, uid: str) -> None:
        self.canvas.expand(uid)

    def _forward_selection(self, uid) -> None:
        self.node_selected.emit(uid)


__all__ = [
    "NODE_MIME",
    "ProgramFlow",
    "ResourceInsertAction",
    "available_resource_actions",
    "node_for_resource_action",
]

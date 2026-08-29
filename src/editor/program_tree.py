"""Vertical block projection with visible four-zone drag feedback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from src.authoring import dsl
from src.authoring.program import (
    DropCheck,
    DropPlacement,
    LogicalUnit,
    Node,
    Ref,
)
from src.qt_compat.QtCore import QMimeData, QPoint, QRect, QSize, Qt, Signal
from src.qt_compat.QtGui import QColor, QDragMoveEvent, QDropEvent, QPainter, QPen
from src.qt_compat.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from .node_palette import PROTOTYPE_MIME, entry_for_kind
from .sidebars import RESOURCE_MIME


NODE_MIME = "application/x-pystg-node"
_ROLE_UID = int(Qt.ItemDataRole.UserRole)
_ROLE_ACCEPTS_CHILD = _ROLE_UID + 1
_ROLE_SLOT = _ROLE_UID + 2
_ROLE_ROOT = _ROLE_UID + 3
_ZONE_LABELS = {
    DropPlacement.BEFORE: "放到之前", DropPlacement.AFTER: "放到之后",
    DropPlacement.CHILD: "作为子项", DropPlacement.WRAP: "包裹目标",
}


@dataclass(frozen=True)
class ResourceInsertAction:
    key: str
    label: str


class ProgramTree(QTreeWidget):
    """Render block-like rows and emit exactly one model operation per drop."""

    node_selected = Signal(object)
    move_requested = Signal(str, str, str, object)
    prototype_requested = Signal(str, object, str, object)
    resource_action_requested = Signal(str, str, str)
    drop_feedback = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("program_flow")
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setIndentation(22)
        self.setAnimated(True)
        self.setStyleSheet(
            "QTreeWidget { background: #171a20; border: 0; }"
            "QTreeWidget::item { min-height: 30px; margin: 2px; padding: 4px; "
            "background: #252a33; border: 1px solid #3a414e; border-radius: 5px; }"
            "QTreeWidget::item:selected { background: #294d70; border-color: #58a6e7; }"
        )
        self.itemSelectionChanged.connect(self._emit_selection)
        self.drop_candidate: tuple[str, DropPlacement] | None = None
        self.drop_check = DropCheck(False, "")
        self._drop_item: QTreeWidgetItem | None = None
        self._drop_slot: str | None = None
        self._validator = None

    def set_drop_validator(self, callback) -> None:
        self._validator = callback

    def set_unit(self, unit: LogicalUnit | None, selected_uid: str | None = None) -> None:
        self.blockSignals(True)
        self.clear()
        if unit is not None:
            root = QTreeWidgetItem([f"{unit.kind} · {unit.name}"])
            root.setData(0, _ROLE_ROOT, unit.id)
            root.setFlags(root.flags() | Qt.ItemFlag.ItemIsDropEnabled)
            root.setSizeHint(0, QSize(0, 38))
            self.addTopLevelItem(root)
            if unit.body:
                for node in unit.body:
                    root.addChild(self._node_item(node))
            else:
                placeholder = QTreeWidgetItem(["拖到这里添加第一个节点"])
                placeholder.setData(0, _ROLE_ROOT, unit.id)
                placeholder.setForeground(0, QColor("#8b949e"))
                placeholder.setFlags(placeholder.flags() | Qt.ItemFlag.ItemIsDropEnabled)
                root.addChild(placeholder)
            root.setExpanded(True)
            if selected_uid:
                item = self.item_for_uid(selected_uid)
                if item is not None:
                    self.setCurrentItem(item)
        self.blockSignals(False)

    def item_for_uid(self, uid: str) -> QTreeWidgetItem | None:
        root = self.invisibleRootItem()
        stack = [root.child(index) for index in range(root.childCount())]
        while stack:
            item = stack.pop()
            if item.data(0, _ROLE_UID) == uid:
                return item
            stack.extend(item.child(index) for index in range(item.childCount()))
        return None

    def placement_for_item(self, item: QTreeWidgetItem, position: QPoint) -> DropPlacement:
        if item.data(0, _ROLE_ROOT):
            return DropPlacement.AFTER
        if item.data(0, _ROLE_SLOT):
            return DropPlacement.CHILD
        rect = self.visualItemRect(item)
        if rect.height() <= 0:
            return DropPlacement.AFTER
        ratio = (position.y() - rect.top()) / rect.height()
        if ratio < 0.25:
            return DropPlacement.BEFORE
        if ratio > 0.75:
            return DropPlacement.AFTER
        accepts_child = bool(item.data(0, _ROLE_ACCEPTS_CHILD))
        if accepts_child and position.x() < rect.center().x():
            return DropPlacement.CHILD
        return DropPlacement.WRAP

    def mimeTypes(self) -> list[str]:
        return [NODE_MIME]

    def mimeData(self, items) -> QMimeData:
        data = QMimeData()
        if items:
            uid = items[0].data(0, _ROLE_UID)
            if uid:
                data.setData(NODE_MIME, str(uid).encode("utf-8"))
        return data

    def dragEnterEvent(self, event) -> None:
        if any(event.mimeData().hasFormat(value) for value in (NODE_MIME, PROTOTYPE_MIME, RESOURCE_MIME)):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        item, target_uid, placement, slot = self._drop_target(event.position().toPoint())
        self._drop_item, self._drop_slot = item, slot
        self.drop_candidate = ((str(target_uid) if target_uid else ""), placement)
        self.drop_check = self._check(event.mimeData(), target_uid, placement, slot)
        self.drop_feedback.emit(self.drop_check.reason or self._drop_preview(event.mimeData(), placement))
        self.viewport().update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._clear_drop()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        _item, target_uid, placement, slot = self._drop_target(event.position().toPoint())
        check = self._check(event.mimeData(), target_uid, placement, slot)
        if not check.allowed:
            self.drop_feedback.emit(check.reason)
            self._clear_drop()
            event.ignore()
            return
        if event.mimeData().hasFormat(PROTOTYPE_MIME):
            kind = bytes(event.mimeData().data(PROTOTYPE_MIME)).decode("utf-8")
            self.prototype_requested.emit(kind, target_uid, placement.value, slot)
            event.acceptProposedAction()
            self._clear_drop()
            return
        if event.mimeData().hasFormat(NODE_MIME):
            source_uid = bytes(event.mimeData().data(NODE_MIME)).decode("utf-8")
            if target_uid is None:
                event.ignore()
                self._clear_drop()
                return
            self.move_requested.emit(source_uid, str(target_uid), placement.value, slot)
            event.acceptProposedAction()
            self._clear_drop()
            return
        if event.mimeData().hasFormat(RESOURCE_MIME):
            if placement == DropPlacement.WRAP or target_uid is None:
                event.ignore()
                self._clear_drop()
                return
            uri = bytes(event.mimeData().data(RESOURCE_MIME)).decode("utf-8")
            self.resource_action_requested.emit(uri, str(target_uid), placement.value)
            event.acceptProposedAction()
            self._clear_drop()
            return
        event.ignore()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.drop_candidate is not None:
            self._clear_drop()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._drop_item is None:
            return
        rect = self.visualItemRect(self._drop_item)
        if rect.isEmpty():
            return
        painter = QPainter(self.viewport())
        painter.setPen(QPen(QColor("#d0d7de")))
        for placement, zone in self._zones(rect).items():
            active = self.drop_candidate and self.drop_candidate[1] == placement
            allowed = self.drop_check.allowed if active else True
            color = QColor("#238636" if active and allowed else "#8b1a1a" if active else "#30363d")
            color.setAlpha(210 if active else 130)
            painter.fillRect(zone, color)
            painter.drawText(zone, Qt.AlignmentFlag.AlignCenter, _ZONE_LABELS[placement])
        painter.end()

    def _node_item(self, node: Node) -> QTreeWidgetItem:
        item = QTreeWidgetItem([_node_summary(node)])
        item.setData(0, _ROLE_UID, node.uid)
        item.setData(0, _ROLE_ACCEPTS_CHILD, bool(node.children))
        item.setToolTip(0, f"{node.kind}\nUID: {node.uid}")
        item.setSizeHint(0, QSize(0, 38))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
        for slot, children in node.children.items():
            slot_item = QTreeWidgetItem([_slot_label(node.kind, slot, not children)])
            slot_item.setData(0, _ROLE_UID, node.uid)
            slot_item.setData(
                0, _ROLE_SLOT,
                "new_branch" if node.kind == "Parallel" and slot == "branches" else slot,
            )
            slot_item.setForeground(0, QColor("#8b949e"))
            slot_item.setFlags(slot_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            slot_item.setFlags(slot_item.flags() | Qt.ItemFlag.ItemIsDropEnabled)
            for child in children:
                slot_item.addChild(self._node_item(child))
            item.addChild(slot_item)
            slot_item.setExpanded(True)
        item.setExpanded(True)
        return item

    def _emit_selection(self) -> None:
        items = self.selectedItems()
        self.node_selected.emit(items[0].data(0, _ROLE_UID) if items else None)

    def _drop_target(self, point: QPoint):
        item = self.itemAt(point) or self.topLevelItem(0)
        if item is None:
            return None, None, DropPlacement.AFTER, None
        if item.data(0, _ROLE_ROOT):
            return item, None, DropPlacement.AFTER, None
        target_uid = item.data(0, _ROLE_UID)
        slot = item.data(0, _ROLE_SLOT)
        return item, target_uid, self.placement_for_item(item, point), slot

    def _check(self, mime, target_uid, placement, slot) -> DropCheck:
        if self._validator is None:
            return DropCheck(True)
        return self._validator(mime, target_uid, placement, slot)

    def _drop_preview(self, mime, placement: DropPlacement) -> str:
        subject = "节点"
        if mime.hasFormat(PROTOTYPE_MIME):
            kind = bytes(mime.data(PROTOTYPE_MIME)).decode("utf-8")
            subject = entry_for_kind(kind).label
        return f"{subject}：{_ZONE_LABELS[placement]}"

    def _clear_drop(self) -> None:
        self.drop_candidate = None
        self.drop_check = DropCheck(False, "")
        self._drop_item = None
        self._drop_slot = None
        self.viewport().update()

    def _zones(self, rect: QRect) -> dict[DropPlacement, QRect]:
        quarter = max(1, rect.height() // 4)
        middle = QRect(rect.left(), rect.top() + quarter, rect.width(), rect.height() - 2 * quarter)
        return {
            DropPlacement.BEFORE: QRect(rect.left(), rect.top(), rect.width(), quarter),
            DropPlacement.AFTER: QRect(rect.left(), rect.bottom() - quarter + 1, rect.width(), quarter),
            DropPlacement.CHILD: QRect(middle.left(), middle.top(), middle.width() // 2, middle.height()),
            DropPlacement.WRAP: QRect(middle.center().x(), middle.top(), middle.width() - middle.width() // 2, middle.height()),
        }


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


def _node_summary(node: Node) -> str:
    if node.kind == "Branch":
        return "并行分支"
    if node.kind == "TemplateCall":
        name = node.template.display_name or node.template.symbol if node.template else "模板"
        return f"模板 · {name}"
    try:
        label = entry_for_kind(node.kind).label
    except StopIteration:
        label = node.kind
    summary_fields = {
        "Wait": "frames", "At": "frame", "Repeat": "count", "RunWave": "wave_class",
        "RunBoss": "boss_def", "SpawnEnemy": "enemy_class", "PlayBGM": "name",
        "PlaySE": "name", "MoveTo": "duration", "FireCircle": "count",
    }
    field = summary_fields.get(node.kind)
    value = node.arguments.get(field) if field else None
    if isinstance(value, Ref):
        value = value.id
    return f"{label}  ·  {value}" if value not in {None, ""} else label


def _slot_label(kind: str, slot: str, empty: bool) -> str:
    labels = {
        ("If", "body"): "条件成立", ("If", "else_body"): "否则",
        ("Parallel", "branches"): "并行分支", ("Branch", "body"): "分支内容",
    }
    label = labels.get((kind, slot), "子节点")
    return f"{label} · 拖到这里" if empty else label


ProgramFlow = ProgramTree


__all__ = [
    "NODE_MIME",
    "ProgramFlow",
    "ProgramTree",
    "ResourceInsertAction",
    "available_resource_actions",
    "node_for_resource_action",
]

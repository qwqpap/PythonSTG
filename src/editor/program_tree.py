"""Current-unit node tree with deterministic four-zone drops."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from src.authoring.dsl import PlayBGM, PlayDialogue, PlaySE, SetBackground
from src.authoring.program import DropPlacement, LogicalUnit, Node
from src.qt_compat.QtCore import QMimeData, QPoint, Qt, Signal
from src.qt_compat.QtGui import QDragMoveEvent, QDropEvent
from src.qt_compat.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from .sidebars import RESOURCE_MIME


NODE_MIME = "application/x-pystg-node"
_ROLE_UID = int(Qt.ItemDataRole.UserRole)
_ROLE_ACCEPTS_CHILD = _ROLE_UID + 1


@dataclass(frozen=True)
class ResourceInsertAction:
    key: str
    label: str


class ProgramTree(QTreeWidget):
    """Emit one model intent per drop; never mutate a second tree model."""

    node_selected = Signal(object)
    move_requested = Signal(str, str, str)
    resource_action_requested = Signal(str, str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("program_tree")
        self.setHeaderLabels(["当前逻辑单元"])
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.itemSelectionChanged.connect(self._emit_selection)
        self.drop_candidate: tuple[str, DropPlacement] | None = None

    def set_unit(self, unit: LogicalUnit | None, selected_uid: str | None = None) -> None:
        self.blockSignals(True)
        self.clear()
        if unit is not None:
            root = QTreeWidgetItem([f"{unit.kind} · {unit.name}"])
            self.addTopLevelItem(root)
            for node in unit.body:
                root.addChild(self._node_item(node))
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
        if event.mimeData().hasFormat(NODE_MIME) or event.mimeData().hasFormat(RESOURCE_MIME):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        point = event.position().toPoint()
        item = self.itemAt(point)
        uid = item.data(0, _ROLE_UID) if item is not None else None
        if uid:
            placement = self.placement_for_item(item, point)
            if event.mimeData().hasFormat(RESOURCE_MIME) and placement == DropPlacement.WRAP:
                self.drop_candidate = None
                event.ignore()
                return
            self.drop_candidate = (str(uid), placement)
            event.acceptProposedAction()
            return
        self.drop_candidate = None
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        point = event.position().toPoint()
        item = self.itemAt(point)
        target_uid = item.data(0, _ROLE_UID) if item is not None else None
        if not target_uid:
            event.ignore()
            return
        placement = self.placement_for_item(item, point)
        if event.mimeData().hasFormat(NODE_MIME):
            source_uid = bytes(event.mimeData().data(NODE_MIME)).decode("utf-8")
            self.move_requested.emit(source_uid, str(target_uid), placement.value)
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat(RESOURCE_MIME):
            if placement == DropPlacement.WRAP:
                event.ignore()
                return
            uri = bytes(event.mimeData().data(RESOURCE_MIME)).decode("utf-8")
            self.resource_action_requested.emit(uri, str(target_uid), placement.value)
            event.acceptProposedAction()
            return
        event.ignore()

    def _node_item(self, node: Node) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.kind])
        item.setData(0, _ROLE_UID, node.uid)
        item.setData(0, _ROLE_ACCEPTS_CHILD, bool(node.children))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
        for slot, children in node.children.items():
            if not children:
                continue
            slot_item = QTreeWidgetItem([slot])
            slot_item.setFlags(slot_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            for child in children:
                slot_item.addChild(self._node_item(child))
            item.addChild(slot_item)
        return item

    def _emit_selection(self) -> None:
        items = self.selectedItems()
        self.node_selected.emit(items[0].data(0, _ROLE_UID) if items else None)


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
        "play_bgm": PlayBGM,
        "play_se": PlaySE,
        "set_background": SetBackground,
        "play_dialogue": PlayDialogue,
    }
    try:
        return factories[action](uri)
    except KeyError as exc:
        raise ValueError(f"unknown resource action: {action}") from exc


__all__ = [
    "NODE_MIME",
    "ProgramTree",
    "ResourceInsertAction",
    "available_resource_actions",
    "node_for_resource_action",
]

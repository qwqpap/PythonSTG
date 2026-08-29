"""Persistent, searchable drag source for declarative authoring nodes."""

from __future__ import annotations

from dataclasses import dataclass

from src.authoring import dsl
from src.authoring.program import (
    AuthoringProgram,
    DropPlacement,
    ProgramError,
    TemplateTarget,
    node_from_palette,
    validate_insert,
)
from src.qt_compat.QtCore import QMimeData, Qt, Signal
from src.qt_compat.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


PROTOTYPE_MIME = "application/x-pystg-node-prototype"
_ROLE_KIND = int(Qt.ItemDataRole.UserRole)


@dataclass(frozen=True)
class PaletteEntry:
    kind: str
    label: str
    category: str
    reference_kinds: tuple[str, ...] = ()
    template_target: TemplateTarget | None = None


_LABELS = {
    "Wait": "等待", "At": "定时执行", "Repeat": "重复", "While": "条件循环",
    "If": "条件分支", "Else": "否则块", "ForEach": "遍历", "Parallel": "并行",
    "SpawnTask": "启动 Task", "Break": "跳出循环", "Continue": "继续循环",
    "Return": "返回", "Set": "设置变量", "Call": "调用函数", "RawPython": "原始 Python",
    "RunWave": "运行 Wave", "RunBoss": "运行 Boss", "SetBackground": "切换背景",
    "PlayBGM": "播放 BGM", "PlayDialogue": "播放对话", "SpawnEnemy": "生成敌人",
    "MoveTo": "移动到", "MoveLinear": "线性移动", "SetPosition": "设置位置",
    "Fire": "发射子弹", "FireCircle": "环形发射", "FireArc": "扇形发射",
    "FireAtPlayer": "自机狙", "FirePolar": "极坐标弹幕", "FireOrbit": "环绕弹幕",
    "ClearBullets": "清除子弹", "Kill": "结束对象", "PlaySE": "播放音效",
    "CreateLaser": "创建激光", "CreateBentLaser": "创建曲线激光",
    "RemoveLaser": "移除激光", "ClearLasers": "清除激光",
}
_CATEGORIES = {
    **{kind: "时间与控制" for kind in (
        "Wait", "At", "Repeat", "While", "If", "Else", "ForEach", "Parallel",
        "SpawnTask", "Break", "Continue", "Return", "Set", "Call", "RawPython",
    )},
    **{kind: "关卡流程" for kind in (
        "RunWave", "RunBoss", "SetBackground", "PlayBGM", "PlayDialogue", "SpawnEnemy",
    )},
    **{kind: "移动" for kind in ("MoveTo", "MoveLinear", "SetPosition", "Kill")},
    **{kind: "弹幕" for kind in (
        "Fire", "FireCircle", "FireArc", "FireAtPlayer", "FirePolar", "FireOrbit",
        "ClearBullets", "PlaySE",
    )},
    **{kind: "激光" for kind in (
        "CreateLaser", "CreateBentLaser", "RemoveLaser", "ClearLasers",
    )},
}
_REFERENCE_KINDS = {
    "RunWave": ("Wave",), "RunBoss": ("Boss",), "SpawnEnemy": ("Enemy",),
    "Call": ("Function", "Task"), "SpawnTask": ("Task",),
}


PALETTE_ENTRIES = tuple(
    PaletteEntry(kind, _LABELS[kind], _CATEGORIES[kind], _REFERENCE_KINDS.get(kind, ()))
    for kind in dsl.NODE_CONSTRUCTORS
)


class _PaletteTree(QTreeWidget):
    def mimeTypes(self) -> list[str]:
        return [PROTOTYPE_MIME]

    def mimeData(self, items) -> QMimeData:
        data = QMimeData()
        if items:
            kind = items[0].data(0, _ROLE_KIND)
            if kind:
                data.setData(PROTOTYPE_MIME, str(kind).encode("utf-8"))
        return data


class NodePalette(QWidget):
    """One visible palette; compatibility is derived from the headless model."""

    insert_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("node_palette")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.search = QLineEdit(self)
        self.search.setObjectName("node_palette_search")
        self.search.setPlaceholderText("搜索节点…")
        self.show_all = QCheckBox("显示全部", self)
        self.show_all.setObjectName("node_palette_show_all")
        self.tree = _PaletteTree(self)
        self.tree.setObjectName("node_palette_tree")
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.itemDoubleClicked.connect(self._activate)
        self.search.textChanged.connect(self.refresh)
        self.show_all.toggled.connect(self.refresh)
        layout.addWidget(self.search)
        layout.addWidget(self.show_all)
        layout.addWidget(self.tree, 1)
        self._program: AuthoringProgram | None = None
        self._unit_id: str | None = None
        self._target_uid: str | None = None
        self._placement = DropPlacement.AFTER
        self._recent: list[str] = []
        self._templates: tuple[TemplateTarget, ...] = ()

    def set_context(
        self,
        program: AuthoringProgram | None,
        unit_id: str | None,
        target_uid: str | None,
        placement: DropPlacement | str,
        templates: tuple[TemplateTarget, ...] = (),
    ) -> None:
        self._program, self._unit_id, self._target_uid = program, unit_id, target_uid
        self._placement = DropPlacement(placement)
        self._templates = templates
        self.refresh()

    def refresh(self) -> None:
        query = self.search.text().strip().casefold()
        self.tree.clear()
        categories: dict[str, QTreeWidgetItem] = {}
        entries = [
            *PALETTE_ENTRIES,
            *(
                PaletteEntry(
                    f"template:{target.identity}",
                    target.display_name or target.symbol,
                    "模板",
                    template_target=target,
                )
                for target in self._templates
            ),
        ]
        if self._recent:
            recent = {kind: index for index, kind in enumerate(self._recent)}
            entries.sort(key=lambda item: (item.kind not in recent, recent.get(item.kind, 99)))
        for entry in entries:
            if query and query not in entry.kind.casefold() and query not in entry.label.casefold():
                continue
            allowed, reason = self.compatibility(entry)
            if not allowed and not self.show_all.isChecked():
                continue
            category_name = "最近使用" if entry.kind in self._recent[:8] and not query else entry.category
            category = categories.get(category_name)
            if category is None:
                category = QTreeWidgetItem([category_name])
                category.setFlags(category.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
                self.tree.addTopLevelItem(category)
                categories[category_name] = category
            item = QTreeWidgetItem([f"{entry.label}  {entry.kind}"])
            item.setData(0, _ROLE_KIND, entry.kind)
            item.setToolTip(0, reason or f"拖动以添加 {entry.label}")
            if not allowed:
                item.setDisabled(True)
            category.addChild(item)
            category.setExpanded(True)

    def compatibility(self, entry: PaletteEntry) -> tuple[bool, str]:
        if self._program is None or self._unit_id is None:
            return False, "请先选择可编辑逻辑单元"
        try:
            unit = self._program.get_unit(self._unit_id)
        except ProgramError as exc:
            return False, exc.message
        if unit.kind == "Project":
            return False, "Project 不包含执行节点"
        references = self.reference_candidates(entry.kind)
        if entry.reference_kinds and not references:
            return False, f"请先新建 {'/'.join(entry.reference_kinds)}"
        try:
            node = node_from_palette(
                entry.kind,
                self._program,
                unit.kind,
                references[0] if references else None,
                template_target=entry.template_target,
            )
        except ProgramError as exc:
            return False, exc.message
        check = validate_insert(
            self._program,
            self._unit_id,
            node,
            self._target_uid,
            self._placement,
        )
        return check.allowed, check.reason

    def reference_candidates(self, kind: str) -> tuple[str, ...]:
        expected = _REFERENCE_KINDS.get(kind, ())
        if self._program is None:
            return ()
        return tuple(
            unit.id
            for unit in sorted(self._program.logical_units(), key=lambda item: item.id)
            if unit.kind in expected
        )

    def remember(self, kind: str) -> None:
        self._recent = [kind, *(item for item in self._recent if item != kind)][:8]
        self.refresh()

    def current_kind(self) -> str | None:
        item = self.tree.currentItem()
        kind = item.data(0, _ROLE_KIND) if item is not None else None
        return str(kind) if kind and not item.isDisabled() else None

    def _activate(self, item: QTreeWidgetItem) -> None:
        kind = item.data(0, _ROLE_KIND)
        if kind and not item.isDisabled():
            self.insert_requested.emit(str(kind))

    def entry(self, kind: str) -> PaletteEntry:
        if kind.startswith("template:"):
            identity = kind.removeprefix("template:")
            for target in self._templates:
                if target.identity == identity:
                    return PaletteEntry(
                        kind,
                        target.display_name or target.symbol,
                        "模板",
                        template_target=target,
                    )
            raise ProgramError("template_missing", f"模板 {identity!r} 已不可用")
        return entry_for_kind(kind)

    def make_node(self, kind: str, reference_id: str | None = None):
        if self._program is None or self._unit_id is None:
            raise ProgramError("no_unit", "请先选择可编辑逻辑单元")
        unit = self._program.get_unit(self._unit_id)
        entry = self.entry(kind)
        return node_from_palette(
            kind if entry.template_target is None else "TemplateCall",
            self._program,
            unit.kind,
            reference_id,
            template_target=entry.template_target,
        )


def entry_for_kind(kind: str) -> PaletteEntry:
    return next(entry for entry in PALETTE_ENTRIES if entry.kind == kind)


__all__ = [
    "NodePalette", "PALETTE_ENTRIES", "PROTOTYPE_MIME", "PaletteEntry",
    "entry_for_kind", "node_from_palette",
]

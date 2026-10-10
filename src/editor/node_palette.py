"""Persistent, searchable drag source for declarative authoring nodes."""

from __future__ import annotations

from dataclasses import dataclass

from src.authoring import dsl
from src.authoring.program import (
    AuthoringProgram,
    DropCheck,
    DropPlacement,
    InsertContext,
    LogicalUnit,
    ProgramError,
    TemplateTarget,
    node_from_palette,
    node_kind_allowed_in_unit,
    prepare_insert_context,
    reference_kinds_for_node,
    unit_accepts_statements,
    validate_insert,
)
from src.qt_compat.QtCore import QEvent, QMimeData, QPoint, QRect, Qt, Signal
from src.qt_compat.QtGui import QColor, QGuiApplication, QPainter
from src.qt_compat.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QLineEdit,
    QLabel,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


PROTOTYPE_MIME = "application/x-pystg-node-prototype"
_ROLE_KIND = int(Qt.ItemDataRole.UserRole)
_ROLE_COLOR = _ROLE_KIND + 1
_CATEGORY_COLORS = {
    "时间与控制": "#58a6e7",
    "关卡流程": "#a371f7",
    "移动": "#3fb950",
    "弹幕": "#f85149",
    "激光": "#d29922",
    "模板": "#bc8cff",
}
_DEFAULT_COLOR = "#8b949e"
_ADVANCED_KINDS = frozenset({
    "At", "While", "If", "Else", "ForEach", "Parallel", "SpawnTask", "Break",
    "Continue", "Return", "Set", "Call", "RawPython", "FirePolar", "FireOrbit",
    "CreateBentLaser", "RemoveLaser",
})


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
    "SpawnTask": "启动后台任务", "Break": "跳出循环", "Continue": "继续循环",
    "Return": "返回", "Set": "设置变量", "Call": "调用函数", "RawPython": "原始 Python",
    "RunWave": "运行波次", "RunBoss": "运行 Boss", "SetBackground": "切换背景",
    "PlayBGM": "播放背景音乐", "PlayDialogue": "播放对话", "SpawnEnemy": "生成敌人",
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
PALETTE_ENTRIES = tuple(
    PaletteEntry(kind, _LABELS[kind], _CATEGORIES[kind], reference_kinds_for_node(kind))
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


class _PaletteDelegate(QStyledItemDelegate):
    """Draws one accent bar per category plus label and dim kind suffix."""

    _ACCENT_WIDTH = 3

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        rect = QRect(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect, QColor("#294d70"))
        elif index.data(Qt.ItemDataRole.DisplayRole) and not index.parent().isValid():
            painter.fillRect(rect, QColor("#16191f"))
        color = index.data(_ROLE_COLOR) or _DEFAULT_COLOR
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if text and not index.parent().isValid():
            # Category headers keep their plain look, slightly dimmed.
            painter.setPen(QColor("#8b949e"))
            painter.setFont(option.font)
            painter.drawText(
                rect.adjusted(8, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, text
            )
            painter.restore()
            return
        painter.fillRect(
            QRect(rect.left(), rect.top(), self._ACCENT_WIDTH, rect.height()),
            QColor(color),
        )
        font = option.font
        if selected:
            painter.setPen(QColor("#f0f6fc"))
        elif index.flags() & Qt.ItemFlag.ItemIsEnabled:
            painter.setPen(QColor("#c9d1d9"))
        else:
            painter.setPen(QColor("#6e7681"))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        painter.drawText(
            rect.adjusted(12, 0, -4, 0),
            Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(text, Qt.TextElideMode.ElideRight, rect.width() - 16),
        )
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(24)
        return size


class NodePalette(QWidget):
    """One visible palette; compatibility is derived from the headless model."""

    insert_requested = Signal(str)
    current_changed = Signal()
    create_reference_requested = Signal(tuple)
    refreshed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("node_palette")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.search = QLineEdit(self)
        self.search.setObjectName("node_palette_search")
        self.search.setPlaceholderText("搜索节点…")
        self.more_nodes = QCheckBox("更多动作（条件、并行、脚本等）", self)
        self.more_nodes.setObjectName("node_palette_more_nodes")
        self.more_nodes.toggled.connect(self.refresh)
        self.show_all = QCheckBox("显示当前不可用的动作", self)
        self.show_all.setObjectName("node_palette_show_all")
        self.tree = _PaletteTree(self)
        self.tree.setObjectName("node_palette_tree")
        self.tree.setHeaderHidden(True)
        self.tree.setItemDelegate(_PaletteDelegate(self.tree))
        self.tree.setStyleSheet("QTreeWidget { background: #171a20; border: 1px solid #3a414e; }")
        self.tree.setDragEnabled(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.itemDoubleClicked.connect(self._activate)
        self.tree.itemSelectionChanged.connect(self.current_changed)
        self.create_reference_button = QPushButton("新建所需逻辑单元…", self)
        self.create_reference_button.setObjectName("node_palette_create_reference")
        self.create_reference_button.hide()
        self.create_reference_button.clicked.connect(
            lambda: self.create_reference_requested.emit(self._missing_reference_kinds)
        )
        self.search.textChanged.connect(self.refresh)
        self.show_all.toggled.connect(self.refresh)
        layout.addWidget(self.search)
        layout.addWidget(self.more_nodes)
        layout.addWidget(self.show_all)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.create_reference_button)
        self._program: AuthoringProgram | None = None
        self._unit_id: str | None = None
        self._target_uid: str | None = None
        self._recent: list[str] = []
        self._templates: tuple[TemplateTarget, ...] = ()
        self._context: tuple | None = None
        self._missing_reference_kinds: tuple[str, ...] = ()
        self._insert_contexts: dict[tuple[str, str | None], InsertContext] = {}
        self._placement = DropPlacement.AFTER
        self._target_slot: str | None = None

    def set_context(
        self,
        program: AuthoringProgram | None,
        unit_id: str | None,
        target_uid: str | None,
        templates: tuple[TemplateTarget, ...] = (),
        *,
        placement: DropPlacement | str = DropPlacement.AFTER,
        target_slot: str | None = None,
    ) -> None:
        placement = DropPlacement(placement)
        context = (program, unit_id, target_uid, templates, placement, target_slot)
        if (
            self._context is not None and program is self._context[0]
            and context[1:] == self._context[1:]
        ):
            return
        self._context = context
        self._program, self._unit_id, self._target_uid = program, unit_id, target_uid
        self._templates = templates
        self._placement, self._target_slot = placement, target_slot
        self.refresh()

    def refresh(self) -> None:
        self._insert_contexts.clear()
        query = self.search.text().strip().casefold()
        # clear() emits itemSelectionChanged while items with a selection are
        # removed; blocking signals keeps the rebuild from re-entering the
        # window's refresh path (and crashing Qt's selection model).
        self.tree.blockSignals(True)
        try:
            self._rebuild(query)
        finally:
            self.tree.blockSignals(False)
        self.refreshed.emit()

    def _rebuild(self, query: str) -> None:
        selected_kind = self.current_kind()
        self.tree.clear()
        missing_reference_kinds: list[str] = []
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
            label = "连续环形弹幕" if entry.template_target and entry.template_target.symbol == "ring_burst" else entry.label
            if not query and not self.more_nodes.isChecked() and entry.kind in _ADVANCED_KINDS and entry.kind not in self._recent:
                continue
            if query and query not in entry.kind.casefold() and query not in label.casefold():
                continue
            allowed, reason = self.compatibility(entry)
            if allowed and entry.reference_kinds and not self.reference_candidates(entry.kind):
                for kind in entry.reference_kinds:
                    if kind not in missing_reference_kinds:
                        missing_reference_kinds.append(kind)
            if not allowed and not self.show_all.isChecked():
                continue
            category_name = "最近使用" if entry.kind in self._recent[:8] and not query else entry.category
            category = categories.get(category_name)
            if category is None:
                category = QTreeWidgetItem([category_name])
                category.setFlags(category.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
                self.tree.addTopLevelItem(category)
                categories[category_name] = category
            item = QTreeWidgetItem([label])
            item.setData(0, _ROLE_KIND, entry.kind)
            item.setData(0, _ROLE_COLOR, _CATEGORY_COLORS.get(entry.category, _DEFAULT_COLOR))
            item.setToolTip(0, f"{reason or f'双击添加{label}，也可拖到步骤之间'}\nPython API: {entry.kind}")
            if not allowed:
                item.setDisabled(True)
            category.addChild(item)
            if entry.kind == selected_kind and allowed:
                self.tree.setCurrentItem(item)
            category.setExpanded(True)
        self._missing_reference_kinds = tuple(missing_reference_kinds)
        if self._missing_reference_kinds:
            names = "/".join(_REFERENCE_LABELS.get(kind, kind) for kind in self._missing_reference_kinds)
            self.create_reference_button.setText(f"＋ 新建 {names}…")
            self.create_reference_button.show()
        else:
            self.create_reference_button.hide()

    def compatibility(self, entry: PaletteEntry) -> tuple[bool, str]:
        if self._program is None or self._unit_id is None:
            return False, "请先选择可编辑逻辑单元"
        try:
            unit = self._program.get_unit(self._unit_id)
        except ProgramError as exc:
            return False, exc.message
        if not unit_accepts_statements(unit.kind):
            return False, f"{unit.kind} 不包含执行节点"
        check = self.placement_check(
            entry.kind, self._target_uid, self._placement, target_slot=self._target_slot
        )
        if not check.allowed:
            return False, check.reason
        references = self.reference_candidates(entry.kind)
        if entry.reference_kinds and not references:
            names = "/".join(_REFERENCE_LABELS.get(kind, kind) for kind in entry.reference_kinds)
            return True, f"添加时新建{names}，然后插入引用"
        return True, ""

    def placement_check(
        self, kind: str, target_uid: str | None,
        placement: DropPlacement | str = DropPlacement.AFTER,
        *, target_slot: str | None = None,
    ) -> DropCheck:
        if self._program is None or self._unit_id is None:
            return DropCheck(False, "请先选择可编辑逻辑单元")
        try:
            unit = self._program.get_unit(self._unit_id)
            entry = self.entry(kind)
            references = self.reference_candidates(kind)
            program = self._program
            reference_id = references[0] if references else None
            if entry.reference_kinds and not references:
                if not node_kind_allowed_in_unit(kind, unit.kind):
                    return DropCheck(False, "该节点不能用于当前逻辑单元")
                # Check the insertion geometry before opening the creation UI.
                # This temporary typed target is never saved or used at runtime;
                # the real insertion validates the author's newly created unit.
                reference_id = "pending_reference"
                while reference_id in program.units:
                    reference_id += "_"
                program = AuthoringProgram({
                    **program.units,
                    reference_id: LogicalUnit(entry.reference_kinds[0], reference_id, "待创建引用"),
                })
            node = node_from_palette(
                kind,
                program,
                unit.kind,
                reference_id,
                template_target=entry.template_target,
            )
            context_key = (unit.id, target_uid)
            context = self._insert_contexts.get(context_key)
            if context is None:
                context = prepare_insert_context(self._program, unit.id, target_uid)
                self._insert_contexts[context_key] = context
            return validate_insert(
                program, unit.id, node, target_uid, placement,
                target_slot=target_slot,
                context=context,
            )
        except ProgramError as exc:
            return DropCheck(False, exc.message)

    def reference_candidates(self, kind: str) -> tuple[str, ...]:
        expected = reference_kinds_for_node(kind)
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


class NodeInsertPopup(QWidget):
    """Search an exact insertion position using the normal palette backend."""

    node_chosen = Signal(str)
    create_reference_requested = Signal(tuple)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("node_insert_popup")
        self.resize(360, 430)
        self.setMinimumSize(300, 240)
        self.setStyleSheet("#node_insert_popup { background: #1c2128; border: 1px solid #58a6e7; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        title = QLabel("在这里添加步骤", self)
        layout.addWidget(title)
        self.palette = NodePalette(self)
        self.palette.setObjectName("insert_popup_palette")
        self.palette.search.setPlaceholderText("搜索步骤，例如等待、环形、切换背景…")
        self.palette.tree.setDragEnabled(False)
        self.empty_label = QLabel("没有找到当前位置可用的步骤。换个词试试。", self)
        self.empty_label.setObjectName("node_insert_no_results")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.palette, 1)
        layout.addWidget(self.empty_label)
        self.palette.insert_requested.connect(self._choose_node)
        self.palette.create_reference_requested.connect(self._create_reference)
        self.palette.refreshed.connect(self._refresh_choices)
        self.palette.current_changed.connect(self._refresh_creation_button)
        self.palette.search.installEventFilter(self)
        self.palette.tree.installEventFilter(self)
        self.empty_label.hide()

    def set_context(
        self,
        program: AuthoringProgram | None,
        unit_id: str | None,
        target_uid: str | None,
        templates: tuple[TemplateTarget, ...] = (),
        *,
        placement: DropPlacement | str = DropPlacement.AFTER,
        target_slot: str | None = None,
    ) -> None:
        self.palette.set_context(
            program, unit_id, target_uid, templates,
            placement=placement, target_slot=target_slot,
        )

    def show_at(self, global_pos: QPoint) -> None:
        self.palette.search.clear()
        self._refresh_choices()
        screen = QGuiApplication.screenAt(global_pos) or self.screen()
        available = screen.availableGeometry()
        self.resize(min(360, available.width()), min(430, available.height()))
        self.move(
            max(available.left(), min(global_pos.x(), available.right() - self.width() + 1)),
            max(available.top(), min(global_pos.y(), available.bottom() - self.height() + 1)),
        )
        self.show()
        self.palette.search.setFocus(Qt.FocusReason.PopupFocusReason)

    def _usable_items(self):
        return [
            category.child(index)
            for category in (
                self.palette.tree.topLevelItem(index)
                for index in range(self.palette.tree.topLevelItemCount())
            )
            for index in range(category.childCount())
            if not category.child(index).isDisabled()
        ]

    def _refresh_choices(self) -> None:
        items = self._usable_items()
        if items and self.palette.current_kind() is None:
            self.palette.tree.setCurrentItem(items[0])
        self.empty_label.setVisible(not items)
        self._refresh_creation_button()

    def _refresh_creation_button(self) -> None:
        kind = self.palette.current_kind()
        expected = reference_kinds_for_node(kind) if kind else ()
        missing = bool(expected and not self.palette.reference_candidates(kind))
        self.palette.create_reference_button.setVisible(missing)
        if missing:
            names = "/".join(_REFERENCE_LABELS.get(value, value) for value in expected)
            self.palette.create_reference_button.setText(f"＋ 新建{names}并放到这里…")

    def _choose_node(self, kind: str) -> None:
        self.hide()
        self.node_chosen.emit(kind)

    def _create_reference(self, fallback: tuple[str, ...]) -> None:
        kind = self.palette.current_kind()
        expected = reference_kinds_for_node(kind) if kind else fallback
        self.hide()
        self.create_reference_requested.emit(expected)

    def eventFilter(self, watched, event) -> bool:
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(watched, event)
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide()
            return True
        if key in {Qt.Key.Key_Up, Qt.Key.Key_Down}:
            items = self._usable_items()
            if items:
                current = self.palette.tree.currentItem()
                index = items.index(current) if current in items else -1
                step = -1 if key == Qt.Key.Key_Up else 1
                index = max(0, min(len(items) - 1, index + step))
                self.palette.tree.setCurrentItem(items[index])
                self.palette.tree.scrollToItem(items[index])
            return True
        if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            kind = self.palette.current_kind()
            if kind:
                self._choose_node(kind)
            return True
        return super().eventFilter(watched, event)


def entry_for_kind(kind: str) -> PaletteEntry:
    return next(entry for entry in PALETTE_ENTRIES if entry.kind == kind)


_REFERENCE_LABELS = {
    "Wave": "波次", "Boss": "Boss", "Enemy": "敌人",
    "Task": "任务", "Function": "函数",
}


__all__ = [
    "NodePalette", "NodeInsertPopup", "PALETTE_ENTRIES", "PROTOTYPE_MIME", "PaletteEntry",
    "entry_for_kind", "node_from_palette",
]

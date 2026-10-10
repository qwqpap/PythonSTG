"""Fixed code-driven editor layout wired directly to one EditorSession."""

from __future__ import annotations

from pathlib import Path
from html import escape

from src.authoring import dsl
from src.authoring.program import (
    clone_node_with_new_uids,
    create_unit as create_program_unit,
    delete_node,
    DropCheck,
    DropPlacement,
    LogicalUnit,
    Node,
    Ref,
    ProgramError,
    find_node,
    insert_new_node,
    move_node,
    node_from_unit_reference,
    node_from_palette,
    node_kind_allowed_in_unit,
    reference_list_target_kinds,
    stage_reference_tree,
    set_unit_reference_list,
    unit_accepts_statements,
    unit_reference_actions,
    unit_reference_edges,
    unit_reference_locations,
    validate_insert,
)
from src.authoring.python_source import SourceConflictError, SourceSaveError
from src.qt_compat.QtCore import Qt, QTimer
from src.qt_compat.QtGui import QAction, QCloseEvent, QCursor
from src.qt_compat.QtWidgets import (
    QDockWidget,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .inspector import InspectorPanel
from .node_palette import NodePalette, NodeInsertPopup, PROTOTYPE_MIME
from .onboarding import AuthoringGuide, WelcomePanel
from .program_tree import (
    NODE_MIME,
    ProgramFlow,
    available_resource_actions,
    node_for_resource_action,
)
from .preview import PreviewHost, PreviewOwner, PreviewTarget
from .project_creation import NewProjectDialog, create_authoring_project
from .session import EditorSession
from .starter_content import STARTER_PATTERNS, make_starter_wave
from .sidebars import (
    ActivitySidebar,
    RESOURCE_MIME,
    ResourceBrowser,
    UNIT_REFERENCE_MIME,
    UnitReferenceListWidget,
    UnitTreeWidget,
)
from .timeline import TimelinePanel


_ROLE_VALUE = int(Qt.ItemDataRole.UserRole)
_UNIT_KIND_LABELS = {
    "Project": "工程",
    "Stage": "关卡",
    "Wave": "波次",
    "Enemy": "敌人",
    "Boss": "Boss",
    "Spell": "符卡",
    "NonSpell": "非符",
    "Task": "任务",
    "Function": "函数",
}
_REFERENCE_ACTION_LABELS = {
    "run_wave": "运行波次",
    "run_boss": "运行 Boss",
    "spawn_enemy": "生成敌人",
    "call": "调用",
    "spawn_task": "后台启动任务",
}


class _UnitDialog(QDialog):
    """Small creation/duplication form; paths remain derived from immutable IDs."""

    def __init__(
        self,
        program,
        parent=None,
        *,
        source=None,
        allowed_kinds: tuple[str, ...] | None = None,
        initial_kind: str | None = None,
        placement_label: str | None = None,
        placement_owner_kind: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("复制关卡内容" if source else "新建关卡内容")
        self._program = program
        self._source = source
        self._suggested_id = ""
        self._suggested_name = ""
        self._placement_owner_kind = placement_owner_kind
        form = QFormLayout(self)
        self._form = form
        self.kind = QComboBox(self)
        all_kinds = (
            "Stage", "Wave", "Enemy", "Boss", "Spell", "NonSpell", "Task", "Function"
        )
        kinds = tuple(dict.fromkeys(allowed_kinds or all_kinds))
        for kind in ([source.kind] if source else kinds):
            self.kind.addItem(_UNIT_KIND_LABELS.get(kind, kind), kind)
        self.unit_id = QLineEdit(self)
        self.name = QLineEdit(self)
        self.texture = QLineEdit("boss1", self)
        if source:
            self.unit_id.setText(f"{source.id}_copy")
            self.name.setText(f"{source.name} 副本")
            self.texture.setText(str(source.metadata.get("texture", "boss1")))
        self.register_stage = QCheckBox("加入工程关卡顺序", self)
        self.register_stage.setChecked(False if source else True)
        self.phase = QComboBox(self)
        self.phase.addItems(
            sorted(unit.id for unit in program.logical_units() if unit.kind in {"Spell", "NonSpell"})
        )
        self.phase_hint = QLabel("Boss 至少需要一个阶段，请先新建符卡或非符。", self)
        self.phase_hint.setWordWrap(True)
        self.phase_hint.setStyleSheet("color: #f0883e;")
        self.phase_hint.setVisible(self.phase.count() == 0)
        self.kind_hint = QLabel(self)
        self.kind_hint.setWordWrap(True)
        form.addRow("类型", self.kind)
        form.addRow(self.kind_hint)
        form.addRow("文件名", self.unit_id)
        self.unit_id.setToolTip("已自动填写；使用字母、数字和下划线。通常无需修改。")
        form.addRow("名称", self.name)
        form.addRow("纹理", self.texture)
        form.addRow("Boss 首个阶段", self.phase)
        form.addRow("", self.phase_hint)
        form.addRow("关卡", self.register_stage)
        self.place_here = QCheckBox("创建后放到当前步骤位置", self)
        self.place_here.setChecked(True)
        self.place_here.setVisible(placement_label is not None)
        self.place_here.setToolTip(placement_label or "只创建内容，不自动添加引用")
        form.addRow(self.place_here)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._confirm_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._confirm_button.setText("创建" if source is None else "复制")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        form.addRow(buttons)
        self.kind.currentIndexChanged.connect(lambda: self._sync(self.kind.currentData()))
        if initial_kind:
            index = self.kind.findData(initial_kind)
            if index >= 0:
                self.kind.setCurrentIndex(index)
        self._sync(self.kind.currentData())

    def _sync(self, kind: str) -> None:
        placeable = bool(self._placement_owner_kind and (
            any(node_kind_allowed_in_unit(action.node_kind, self._placement_owner_kind) for action in unit_reference_actions(kind)) and unit_accepts_statements(self._placement_owner_kind)
            or self._placement_owner_kind == "Boss" and kind in reference_list_target_kinds("Boss", "phases")
        ))
        self.place_here.setVisible(placeable)
        for field in (self.phase, self.texture):
            field.setVisible(kind == "Boss")
            self._form.labelForField(field).setVisible(kind == "Boss")
        self.register_stage.setVisible(kind == "Stage")
        self._form.labelForField(self.register_stage).setVisible(kind == "Stage")
        self.phase_hint.setVisible(kind == "Boss" and self.phase.count() == 0)
        self._confirm_button.setEnabled(kind != "Boss" or self.phase.count() > 0)
        self.kind_hint.setText({
            "Stage": "安排一整关的出场顺序：波次、背景、对话和 Boss。",
            "Wave": "安排一组敌人什么时候出场，也可以直接发射弹幕。",
            "Enemy": "编辑一个敌人的移动、发射和退场步骤。",
            "Boss": "按顺序组合非符和符卡。请先创建至少一个攻击阶段。",
            "Spell": "Boss 的一个符卡阶段，在这里编辑移动与弹幕。",
            "NonSpell": "Boss 的一个普通攻击阶段，在这里编辑移动与弹幕。",
            "Task": "可复用、可在后台运行的步骤；需要并行行为时再使用。",
            "Function": "可调用并返回结果的步骤；需要复用复杂行为时再使用。",
        }.get(kind, ""))
        if self._source is None:
            candidate = f"{kind.lower()}_1"
            index = 2
            while candidate in self._program.units:
                candidate = f"{kind.lower()}_{index}"
                index += 1
            name = f"新{_UNIT_KIND_LABELS.get(kind, kind)}"
            if self.unit_id.text() in {"", self._suggested_id}:
                self.unit_id.setText(candidate)
            if self.name.text() in {"", self._suggested_name}:
                self.name.setText(name)
            self._suggested_id, self._suggested_name = candidate, name

    def values(self) -> tuple[str, str, str, bool, str | None, str]:
        return (
            self.kind.currentData(),
            self.unit_id.text().strip(),
            self.name.text().strip(),
            self.register_stage.isChecked() and self.kind.currentData() == "Stage",
            self.phase.currentText() or None,
            self.texture.text().strip(),
        )


_WINDOW_STYLESHEET = """
    QWidget { font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif; font-size: 14px; }
    QMainWindow, QDialog { background: #1c2128; color: #c9d1d9; }
    QLabel { color: #c9d1d9; background: transparent; }
    QMenuBar { background: #16191f; color: #c9d1d9; border-bottom: 1px solid #3a414e; }
    QMenuBar::item { padding: 4px 10px; background: transparent; }
    QMenuBar::item:selected { background: #294d70; }
    QMenu { background: #1f242c; color: #c9d1d9; border: 1px solid #3a414e; }
    QMenu::item { padding: 4px 24px 4px 12px; }
    QMenu::item:selected { background: #294d70; }
    QMenu::separator { height: 1px; background: #3a414e; margin: 4px 6px; }
    QDockWidget { color: #c9d1d9; font-weight: 600; }
    QDockWidget::title { background: #16191f; padding: 5px 10px;
        border-bottom: 1px solid #3a414e; }
    QTabWidget::pane { border: 1px solid #3a414e; background: #171a20; top: -1px; }
    QTabBar::tab { background: #16191f; color: #8b949e; padding: 5px 14px;
        border: 1px solid #3a414e; border-bottom: none; }
    QTabBar::tab:selected { color: #f0f6fc; background: #171a20;
        border-bottom: 2px solid #58a6e7; }
    QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #3a414e;
        border-radius: 4px; padding: 4px 12px; }
    QPushButton:hover { background: #2d333b; border-color: #58a6e7; }
    QPushButton:pressed { background: #294d70; }
    QPushButton:checked { background: #1f4a73; border-color: #58a6e7;
        color: #f0f6fc; font-weight: 600; }
    QPushButton:disabled { background: #1a1e24; color: #484f58;
        border-color: #262c34; }
    QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QComboBox {
        background: #0f1216; color: #c9d1d9; border: 1px solid #3a414e;
        border-radius: 4px; padding: 2px 6px; selection-background-color: #294d70; }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #58a6e7; }
    QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
    QPlainTextEdit:disabled, QComboBox:disabled { color: #6e7681; }
    QComboBox QAbstractItemView { background: #1f242c; color: #c9d1d9;
        selection-background-color: #294d70; }
    QScrollArea { background: #171a20; border: none; }
    QScrollArea > QWidget > QWidget { background: transparent; }
    QScrollArea > QWidget > QScrollBar { background: #171a20; }
    QTreeWidget, QListWidget { background: #171a20; color: #c9d1d9;
        border: 1px solid #3a414e; }
    QTreeWidget::item, QListWidget::item { padding: 2px; }
    QTreeWidget::item:selected, QListWidget::item:selected { background: #294d70; }
    QHeaderView::section { background: #16191f; color: #8b949e; border: none;
        border-right: 1px solid #3a414e; padding: 4px 6px; }
    QScrollBar:vertical { background: #171a20; width: 10px; margin: 0; }
    QScrollBar::handle:vertical { background: #3a414e; border-radius: 4px;
        min-height: 24px; }
    QScrollBar:horizontal { background: #171a20; height: 10px; margin: 0; }
    QScrollBar::handle:horizontal { background: #3a414e; border-radius: 4px;
        min-width: 24px; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    QCheckBox { color: #c9d1d9; spacing: 6px; }
    QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #3a414e;
        border-radius: 3px; background: #0f1216; }
    QCheckBox::indicator:checked { background: #58a6e7;
        image: url(none); }
    QSplitter::handle { background: #12161b; }
    QSplitter::handle:horizontal { width: 3px; }
    QSplitter::handle:vertical { height: 3px; }
    QToolTip { background: #1f242c; color: #c9d1d9; border: 1px solid #3a414e;
        padding: 2px; }
    QStatusBar { background: #16191f; color: #8b949e; }
    QStatusBar::item { border: none; }
    QToolBar { background: #20242a; border: none; border-bottom: 1px solid #333941; spacing: 6px; padding: 4px 8px; }
    QToolButton { color: #c9d1d9; background: transparent; border: 1px solid transparent;
        border-radius: 5px; padding: 5px 8px; min-height: 22px; }
    QToolButton:hover { background: #30363e; }
    QToolButton:checked { color: #d4e9fb; background: #29475e; border-color: #47738f; }
    QToolButton:disabled { color: #656e78; }
    QTreeWidget, QListWidget { border: none; }
    QTreeWidget::item, QListWidget::item { padding: 5px 2px; }
    QTabWidget::pane { border: none; }
    QDockWidget::title { padding: 5px 10px; border: none; }
    QPushButton { min-height: 24px; }
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { min-height: 24px; }
    QWidget#workspace_navigation { background: #20242a; }
    QWidget#program_toolbar { background: #1c2128; }
    QToolButton#run_primary { background: #294d70; color: #f0f6fc; }
"""


class _CurrentPageStack(QStackedWidget):
    """Do not let hidden welcome/reference pages constrain the workspace."""

    def minimumSizeHint(self):
        current = self.currentWidget()
        return current.minimumSizeHint() if current else super().minimumSizeHint()


class EditorWindow(QMainWindow):
    """One window, one project, one session, and one undo history."""

    def __init__(
        self,
        session: EditorSession | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("code_editor_window")
        self.session = session or EditorSession(self)
        self._generated_root: Path | None = None
        self._node_clipboard: tuple[Node, ...] = ()
        self._refreshing_selection = False
        self._workspace_open: bool | None = None
        self._navigation_history: list[tuple[str, str | None, tuple[str, ...], int]] = []
        self._workspace_mode = "steps"
        self._show_help = False
        self._insert_location = (None, DropPlacement.AFTER, None)
        self._insert_owner_id: str | None = None
        self.setWindowTitle("PySTG 关卡编辑器")
        self.resize(1280, 800)
        self.setStyleSheet(_WINDOW_STYLESHEET)
        self._build_actions()
        self._build_layout()
        self._connect_session()
        self.refresh_project()
        self._preview_state_changed(self.session.preview_state)

    def open_project(self, root: str | Path, *, confirm_transition: bool = True) -> bool:
        if confirm_transition and self.session.is_open and not self._confirm_project_transition():
            return False
        if self.session.is_open:
            self.preview_owner.stop()
        self._navigation_history.clear()
        self._set_workspace_mode("steps")
        self.session.open_project(root)
        self._generated_root = None
        self.generated_file_selector.clear()
        self.generated_code_view.setPlainText("构建成功后可在此查看生成 Runtime Python。")
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        """Release the single project's file watcher with the window."""

        if not self._confirm_project_transition():
            event.ignore()
            return
        self.preview_owner.stop()
        if self.session.is_open:
            self.session.close_project()
        super().closeEvent(event)

    def _build_actions(self) -> None:
        def add_action(menu, attribute, text, object_name, callback, shortcut=None):
            action = QAction(text, self)
            action.setObjectName(object_name)
            if shortcut is not None:
                action.setShortcut(shortcut)
            action.triggered.connect(callback)
            menu.addAction(action)
            setattr(self, attribute, action)

        file_menu = self.menuBar().addMenu("文件")
        add_action(file_menu, "new_project_action", "新建工程…", "new_project_action", self._new_project, "Ctrl+N")
        add_action(file_menu, "open_action", "打开工程…", "open_project_action", self._choose_project)
        add_action(file_menu, "save_action", "全部保存", "save_all_action", self._save_all, "Ctrl+S")

        edit_menu = self.menuBar().addMenu("编辑")
        self.undo_action = self.session.undo_stack.createUndoAction(self, "撤销")
        self.undo_action.setObjectName("undo_action")
        self.undo_action.setShortcut("Ctrl+Z")
        edit_menu.addAction(self.undo_action)
        self.redo_action = self.session.undo_stack.createRedoAction(self, "重做")
        self.redo_action.setObjectName("redo_action")
        self.redo_action.setShortcut("Ctrl+Shift+Z")
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        add_action(
            edit_menu,
            "copy_node_action",
            "复制节点",
            "copy_node_action",
            self._copy_selected_nodes,
            "Ctrl+C",
        )
        add_action(
            edit_menu,
            "paste_node_action",
            "粘贴节点",
            "paste_node_action",
            self._paste_nodes,
            "Ctrl+V",
        )
        add_action(
            edit_menu,
            "delete_node_action",
            "删除节点",
            "delete_node_action",
            self._delete_selected_nodes,
            "Delete",
        )
        self.view_menu = self.menuBar().addMenu("视图")
        add_action(
            self.view_menu,
            "refresh_assets_action",
            "刷新资产",
            "refresh_assets_action",
            self._refresh_assets,
        )

        run_menu = self.menuBar().addMenu("运行")
        add_action(run_menu, "run_current_action", "运行当前单元", "run_current_action", self._run_current, "F5")
        add_action(run_menu, "run_project_action", "运行整个工程", "run_project_action",
                   lambda: self._run_target(PreviewTarget("project")))
        add_action(run_menu, "run_stage_action", "运行当前关卡", "run_stage_action", self._run_current_stage)
        run_menu.addSeparator()
        add_action(run_menu, "pause_preview_action", "暂停", "pause_preview_action", self._pause_preview)
        add_action(run_menu, "resume_preview_action", "继续", "resume_preview_action", self._resume_preview)
        add_action(run_menu, "restart_preview_action", "重新开始", "restart_preview_action", self._restart_preview)
        add_action(run_menu, "seek_preview_action", "跳转预览到帧…", "seek_preview_action", self._seek_preview)
        add_action(run_menu, "stop_preview_action", "停止", "stop_preview_action", self._stop_preview)

    def _build_layout(self) -> None:
        self.unit_list = UnitTreeWidget(self)
        self.unit_list.setObjectName("program_structure")
        self.unit_list.setHeaderLabels(["关卡内容"])
        self.unit_list.setHeaderHidden(True)
        self.unit_list.unit_activated.connect(self._activate_unit)
        self.unit_list.drag_finished.connect(
            lambda: self._select_unit(self.session.current_unit_id)
        )
        unit_panel = QWidget(self)
        unit_panel_layout = QVBoxLayout(unit_panel)
        unit_panel_layout.setContentsMargins(0, 0, 0, 0)
        unit_toolbar = QWidget(unit_panel)
        unit_toolbar_layout = QHBoxLayout(unit_toolbar)
        unit_toolbar_layout.setContentsMargins(2, 2, 2, 2)
        self.new_unit_button = QPushButton("新建内容…", unit_toolbar)
        self.duplicate_unit_button = QAction("复制当前内容…", self)
        self.delete_unit_button = QAction("删除当前内容…", self)
        self.structure_mode = QComboBox(unit_toolbar)
        self.structure_mode.setObjectName("program_structure_mode")
        self.structure_mode.addItem("这一关的内容", "stage_chain")
        self.structure_mode.addItem("全部内容", "all")
        self.new_unit_button.clicked.connect(self._create_unit)
        self.duplicate_unit_button.triggered.connect(self._duplicate_unit)
        self.delete_unit_button.triggered.connect(self._delete_unit)
        self.structure_mode.currentIndexChanged.connect(self._structure_mode_changed)
        unit_toolbar_layout.addWidget(self.new_unit_button, 1)
        unit_more = QToolButton(unit_toolbar)
        unit_more.setText("⋯")
        unit_more.setToolTip("管理当前内容")
        unit_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        unit_menu = QMenu(unit_more)
        unit_menu.addAction(self.duplicate_unit_button)
        unit_menu.addAction(self.delete_unit_button)
        unit_more.setMenu(unit_menu)
        unit_toolbar_layout.addWidget(unit_more)
        unit_panel_layout.addWidget(unit_toolbar)
        unit_panel_layout.addWidget(self.structure_mode)
        unit_panel_layout.addWidget(self.unit_list, 1)
        self.next_step_hint = QLabel("从“文件 → 新建工程”开始，或打开已有工程。", unit_panel)
        self.next_step_hint.setObjectName("authoring_next_step")
        self.next_step_hint.setWordWrap(True)
        self.next_step_hint.setStyleSheet("color: #8b949e; padding: 4px;")
        unit_panel_layout.addWidget(self.next_step_hint)
        self.next_step_hint.hide()
        self.file_list = QListWidget(self)
        self.file_list.setObjectName("file_sidebar")
        self.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.file_list.itemSelectionChanged.connect(self._file_selected)
        file_panel = QWidget(self)
        file_layout = QVBoxLayout(file_panel)
        file_layout.setContentsMargins(8, 6, 8, 6)
        file_hint = QLabel("作者源码（只读）\n点击查看对应文件。\n编写玩法请切换“内容”。", file_panel)
        file_hint.setWordWrap(True)
        file_layout.addWidget(file_hint)
        file_layout.addWidget(self.file_list, 1)
        self.global_asset_list = ResourceBrowser(self, scope="project")
        self.global_asset_list.setObjectName("global_asset_sidebar")
        self.stage_asset_list = ResourceBrowser(self, scope="stage")
        self.stage_asset_list.setObjectName("stage_asset_sidebar")
        activity = ActivitySidebar(
            unit_panel,
            file_panel,
            self.global_asset_list,
            self.stage_asset_list,
            self,
        )
        self.activity_sidebar = activity
        self.node_palette = NodePalette(self)
        self.node_palette.insert_requested.connect(self._insert_selected_prototype)
        self.node_palette.create_reference_requested.connect(self._offer_unit_creation)
        self.node_palette.current_changed.connect(self.refresh_selection)
        self.show_palette_action = QAction("显示完整动作库", self, checkable=True)
        self.show_palette_action.toggled.connect(self.refresh_selection)
        self.view_menu.addAction(self.show_palette_action)
        left_splitter = QSplitter(Qt.Orientation.Vertical, self)
        left_splitter.setObjectName("left_authoring_splitter")
        left_splitter.addWidget(activity)
        left_splitter.addWidget(self.node_palette)
        left_splitter.setStretchFactor(0, 2)
        left_splitter.setStretchFactor(1, 3)
        left_dock = QDockWidget("内容导航", self)
        left_dock.setObjectName("left_activity_dock")
        left_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        left_dock.setWidget(left_splitter)
        self.left_dock = left_dock
        self._allow_horizontal_compression(left_splitter)
        self._allow_horizontal_compression(activity)
        self._allow_horizontal_compression(self.node_palette)
        self._allow_horizontal_compression(left_dock, minimum_width=190)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left_dock)

        self.program_tree = ProgramFlow(self)
        self.program_tree.set_drop_validator(self._validate_program_drop)
        self.program_tree.node_selected.connect(self._node_selected)
        self.program_tree.node_activated.connect(self._focus_suggested_field)
        self.program_tree.move_requested.connect(self._move_node)
        self.program_tree.prototype_requested.connect(self._drop_prototype)
        self.program_tree.unit_reference_requested.connect(self._drop_unit_reference)
        self.program_tree.resource_action_requested.connect(self._resource_drop)
        self.program_tree.insert_requested.connect(self._show_insert_popup)
        self.program_tree.reference_open_requested.connect(self._select_referenced_unit)
        self.program_tree.drop_feedback.connect(
            lambda message: self.statusBar().showMessage(message, 2500)
        )
        program_panel = QWidget(self)
        program_panel.setObjectName("program_editor_panel")
        program_layout = QVBoxLayout(program_panel)
        program_layout.setContentsMargins(0, 0, 0, 0)
        self.authoring_guide = AuthoringGuide(program_panel)
        self.authoring_guide.action_requested.connect(self._guide_action)
        program_layout.addWidget(self.authoring_guide)
        program_toolbar = QWidget(program_panel)
        self.program_toolbar = program_toolbar
        program_toolbar.setObjectName("program_toolbar")
        program_toolbar_layout = QHBoxLayout(program_toolbar)
        program_toolbar_layout.setContentsMargins(8, 4, 8, 4)
        self.steps_title = QLabel("编辑步骤", program_toolbar)
        self.steps_title.setStyleSheet("font-weight: 600;")
        program_toolbar_layout.addWidget(self.steps_title)
        program_toolbar_layout.addStretch(1)
        self.add_node_button = QPushButton("＋ 添加步骤", program_toolbar)
        self.add_node_button.setObjectName("add_selected_node")
        self.add_node_button.setToolTip("在选中步骤之后添加；也可点击步骤之间的 + 精确选择位置")
        self.add_node_button.clicked.connect(self._show_insert_after_selection)
        program_toolbar_layout.addWidget(self.add_node_button)
        self.copy_node_button = QAction("复制步骤", self)
        self.copy_node_button.setObjectName("copy_node")
        self.copy_node_button.triggered.connect(self._copy_selected_nodes)
        self.paste_node_button = QAction("粘贴步骤", self)
        self.paste_node_button.setObjectName("paste_node")
        self.paste_node_button.triggered.connect(self._paste_nodes)
        self.delete_node_button = QAction("删除步骤", self)
        self.delete_node_button.setObjectName("delete_node")
        self.delete_node_button.triggered.connect(self._delete_selected_nodes)
        self.collapse_all_button = QAction("全部折叠", self)
        self.collapse_all_button.setObjectName("collapse_all_nodes")
        self.collapse_all_button.triggered.connect(self.program_tree.collapse_all)
        self.expand_all_button = QAction("全部展开", self)
        self.expand_all_button.setObjectName("expand_all_nodes")
        self.expand_all_button.triggered.connect(self.program_tree.expand_all)
        step_more = QToolButton(program_toolbar)
        step_more.setObjectName("step_more")
        step_more.setText("⋯")
        step_more.setToolTip("复制、粘贴、删除与折叠")
        step_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        step_menu = QMenu(step_more)
        for action in (self.copy_node_button, self.paste_node_button, self.delete_node_button):
            step_menu.addAction(action)
        step_menu.addSeparator()
        step_menu.addAction(self.collapse_all_button)
        step_menu.addAction(self.expand_all_button)
        step_more.setMenu(step_menu)
        program_toolbar_layout.addWidget(step_more)
        self.program_content_stack = _CurrentPageStack(program_panel)
        self.program_content_stack.setObjectName("program_content_stack")
        self.project_reference_panel = self._build_project_reference_panel(program_panel)
        self.boss_reference_panel = self._build_boss_reference_panel(program_panel)
        self.welcome_panel = WelcomePanel(program_panel)
        self.welcome_panel.new_project_requested.connect(self._new_project)
        self.welcome_panel.open_project_requested.connect(self._choose_project)
        self.program_content_stack.addWidget(self.program_tree)
        self.program_content_stack.addWidget(self.project_reference_panel)
        self.program_content_stack.addWidget(self.boss_reference_panel)
        self.program_content_stack.addWidget(self.welcome_panel)
        program_layout.addWidget(program_toolbar)
        program_layout.addWidget(self.program_content_stack, 1)
        self.code_view = QPlainTextEdit(self)
        self.code_view.setObjectName("source_code_view")
        self.code_view.setReadOnly(True)
        self.code_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        generated_panel = QWidget(self)
        generated_layout = QVBoxLayout(generated_panel)
        generated_layout.setContentsMargins(0, 0, 0, 0)
        self.generated_file_selector = QComboBox(generated_panel)
        self.generated_file_selector.setObjectName("generated_file_selector")
        self.generated_file_selector.setToolTip("选择本次构建生成的 Python 文件")
        self.generated_file_selector.currentTextChanged.connect(self._show_generated_file)
        generated_layout.addWidget(self.generated_file_selector)
        self.generated_code_view = QPlainTextEdit(generated_panel)
        self.generated_code_view.setObjectName("generated_code_view")
        self.generated_code_view.setReadOnly(True)
        self.generated_code_view.setPlainText("构建成功后可在此查看生成 Runtime Python。")
        generated_layout.addWidget(self.generated_code_view, 1)
        editor_tabs = QTabWidget(self)
        editor_tabs.setObjectName("editor_tabs")
        editor_tabs.addTab(program_panel, "编辑步骤")
        editor_tabs.addTab(self.code_view, "作者 Python（只读）")
        editor_tabs.addTab(generated_panel, "生成 Python（只读）")
        self.editor_tabs = editor_tabs
        self.show_source_action = QAction("显示 Python 源码标签", self, checkable=True)
        self.show_source_action.toggled.connect(self._set_source_tabs_visible)
        self.view_menu.addAction(self.show_source_action)
        self._set_source_tabs_visible(False)
        self.editor_group = editor_tabs
        self.editor_group.setObjectName("editor_group")

        self.preview_host = PreviewHost(self)
        self.preview_owner = PreviewOwner(self.session, self.preview_host, self)
        game_panel = QWidget(self)
        game_panel.setObjectName("game_preview_panel")
        game_layout = QVBoxLayout(game_panel)
        game_layout.setContentsMargins(0, 0, 0, 0)
        controls = QWidget(game_panel)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(10, 6, 10, 6)
        controls_layout.setSpacing(3)
        self.preview_target_label = QLabel("运行目标：尚未运行", controls)
        self.preview_target_label.setObjectName("preview_target")
        self.preview_target_label.setStyleSheet("color: #8b949e;")
        self.preview_target_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        controls_layout.addWidget(self.preview_target_label)
        self.build_status_label = QLabel("构建：空闲", controls)
        self.build_status_label.setObjectName("preview_build_status")
        self.build_status_label.setStyleSheet("color: #8b949e;")
        self.build_status_label.hide()
        controls_layout.addWidget(self.build_status_label)
        self.preview_error_label = QLabel("", controls)
        self.preview_error_label.setObjectName("preview_error")
        self.preview_error_label.setStyleSheet("color: #f85149;")
        self.preview_error_label.setWordWrap(True)
        self.preview_error_label.hide()
        controls_layout.addWidget(self.preview_error_label)
        game_layout.addWidget(controls)
        game_layout.addWidget(self.preview_host, 1)
        self.game_group = game_panel
        self.game_group.setObjectName("game_group")

        self.central_groups = QSplitter(Qt.Orientation.Horizontal, self)
        self.central_groups.setObjectName("central_groups")
        self.central_groups.addWidget(self.editor_group)
        self.central_groups.addWidget(self.game_group)
        self.central_groups.setStretchFactor(0, 3)
        self.central_groups.setStretchFactor(1, 2)
        self._allow_horizontal_compression(program_toolbar)
        self._allow_horizontal_compression(self.editor_group)
        self._allow_horizontal_compression(self.game_group)
        self._allow_horizontal_compression(self.central_groups)
        workspace = QWidget(self)
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        navigation = QWidget(workspace)
        navigation.setObjectName("workspace_navigation")
        navigation_layout = QHBoxLayout(navigation)
        navigation_layout.setContentsMargins(8, 3, 8, 3)
        self.back_button = QToolButton(navigation)
        self.back_button.setObjectName("navigate_back")
        self.back_button.setText("‹ 返回")
        self.back_button.setToolTip("返回上一处内容，并恢复步骤选择和滚动位置")
        self.back_button.clicked.connect(self._navigate_back)
        navigation_layout.addWidget(self.back_button)
        self.breadcrumb = QLabel("未打开工程", navigation)
        self.breadcrumb.setObjectName("content_breadcrumb")
        self.breadcrumb.setTextFormat(Qt.TextFormat.RichText)
        self.breadcrumb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.breadcrumb.setMinimumWidth(0)
        self.breadcrumb.linkActivated.connect(self._navigate_unit)
        navigation_layout.addWidget(self.breadcrumb, 1)
        self.help_button = QToolButton(navigation)
        self.help_button.setText("提示")
        self.help_button.setCheckable(True)
        self.help_button.setToolTip("展开当前内容的用途和常用操作")
        self.help_button.toggled.connect(self._toggle_help)
        navigation_layout.addWidget(self.help_button)
        workspace_layout.addWidget(navigation)
        workspace_layout.addWidget(self.central_groups, 1)
        self.setCentralWidget(workspace)

        self.show_editor_action = QAction("编辑步骤", self, checkable=True)
        self.show_editor_action.setChecked(True)
        self.show_editor_action.triggered.connect(lambda: self._set_workspace_mode("steps"))
        self.show_game_action = QAction("游戏画面", self, checkable=True)
        self.show_game_action.triggered.connect(lambda: self._set_workspace_mode("preview"))
        self.split_preview_action = QAction("并排预览", self, checkable=True)
        self.split_preview_action.triggered.connect(lambda: self._set_workspace_mode("split"))
        self.view_menu.addAction(self.show_editor_action)
        self.view_menu.addAction(self.show_game_action)
        self.view_menu.addAction(self.split_preview_action)

        transport = QToolBar("编辑与预览", self)
        transport.setObjectName("workspace_transport")
        transport.setMovable(False)
        self.addToolBar(transport)
        for action in (self.show_editor_action, self.show_game_action, self.split_preview_action):
            transport.addAction(action)
        transport.addSeparator()
        self.run_button = QToolButton(transport)
        self.run_button.setObjectName("run_primary")
        self.run_button.setDefaultAction(self.run_current_action)
        transport.addWidget(self.run_button)
        self.playback_action = QAction("暂停", self)
        self.playback_action.triggered.connect(self._toggle_playback)
        transport.addAction(self.playback_action)
        transport.addAction(self.stop_preview_action)
        self.preview_status = QLabel("已停止", transport)
        self.preview_status.setObjectName("preview_status")
        self.preview_status.setMinimumWidth(150)
        self.preview_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        transport.addWidget(self.preview_status)

        self.inspector = InspectorPanel(self.session, self)
        self.inspector.reference_open_requested.connect(self._navigate_unit)
        self.inspector_scroll = QScrollArea(self)
        self.inspector_scroll.setObjectName("inspector_scroll")
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setWidget(self.inspector)
        self.inspector_dock = QDockWidget("属性", self)
        self.inspector_dock.setObjectName("inspector_dock")
        self._allow_horizontal_compression(self.inspector_scroll)
        self._allow_horizontal_compression(self.inspector_dock, minimum_width=270)
        self.inspector_dock.setWidget(self.inspector_scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_dock)
        self.view_menu.addAction(self.inspector_dock.toggleViewAction())

        self.timeline_panel = TimelinePanel(self.session, self)
        self.timeline_panel.set_preview_owner(self.preview_owner)
        self.timeline_dock = QDockWidget("时间线", self)
        self.timeline_dock.setObjectName("timeline_dock")
        self.timeline_dock.setMinimumHeight(90)
        self.timeline_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.timeline_dock.setWidget(self.timeline_panel)
        timeline_title = QWidget(self.timeline_dock)
        timeline_title_layout = QHBoxLayout(timeline_title)
        timeline_title_layout.setContentsMargins(10, 0, 6, 0)
        timeline_title_layout.addWidget(QLabel("时间线", timeline_title))
        timeline_title_layout.addStretch(1)
        self.expand_timeline_button = QToolButton(timeline_title)
        self.expand_timeline_button.setObjectName("expand_timeline")
        self.expand_timeline_button.setText("展开时间线")
        self.expand_timeline_button.setCheckable(True)
        self.expand_timeline_button.toggled.connect(self._toggle_timeline_height)
        timeline_title_layout.addWidget(self.expand_timeline_button)
        self.timeline_dock.setTitleBarWidget(timeline_title)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.timeline_dock)

        self.problems_view = QPlainTextEdit(self)
        self.problems_view.setObjectName("problems_log")
        self.problems_view.setReadOnly(True)
        self.output_dock = QDockWidget("问题 / 日志", self)
        self.output_dock.setObjectName("output_dock")
        self.output_dock.setWidget(self.problems_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.output_dock)
        self.splitDockWidget(self.timeline_dock, self.output_dock, Qt.Orientation.Vertical)
        self.view_menu.addAction(self.output_dock.toggleViewAction())
        self.output_dock.hide()
        self.insert_popup = NodeInsertPopup(self)
        self.insert_popup.node_chosen.connect(self._insert_popup_node)
        self.insert_popup.create_reference_requested.connect(self._create_popup_reference)
        self.resizeDocks([self.left_dock, self.inspector_dock], [220, 300], Qt.Orientation.Horizontal)
        self.resizeDocks([self.timeline_dock], [160], Qt.Orientation.Vertical)
        self._set_workspace_mode("steps")

    @staticmethod
    def _allow_horizontal_compression(
        widget: QWidget, *, minimum_width: int = 0
    ) -> None:
        """Keep fixed panes usable without forcing the main window wider.

        Qt propagates the widest toolbar and form size hint through dock and
        splitter parents.  Treat those hints as preferred, not mandatory; the
        explicit dock minima preserve usable navigation and Inspector widths.
        """

        widget.setMinimumWidth(minimum_width)
        policy = widget.sizePolicy()
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, policy.verticalPolicy())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "split_preview_action"):
            self._apply_workspace_mode()

    def _set_workspace_mode(self, mode: str) -> None:
        if mode == "split" and self.width() < 1400:
            mode = "preview"
        if mode == "steps":
            self.editor_tabs.setCurrentIndex(0)
        self._workspace_mode = mode
        self._apply_workspace_mode()

    def _apply_workspace_mode(self) -> None:
        wide = self.width() >= 1400
        if self._workspace_mode == "split" and not wide:
            self._workspace_mode = "steps"
        mode = self._workspace_mode
        self.editor_group.setVisible(mode != "preview")
        self.game_group.setVisible(mode != "steps" and self.session.is_open)
        self.show_editor_action.setChecked(mode == "steps")
        self.show_game_action.setChecked(mode == "preview")
        self.split_preview_action.setChecked(mode == "split")
        self.split_preview_action.setEnabled(wide and self.session.is_open)
        self.split_preview_action.setToolTip("窗口宽度至少 1400 时可并排；小窗口请切换步骤与画面")
        if self._workspace_open:
            self.inspector_dock.setVisible(mode != "preview")
        if mode == "split":
            self.central_groups.setSizes([600, 380])

    def _toggle_playback(self) -> None:
        if self.session.preview_state == "paused":
            self._resume_preview()
        else:
            self._pause_preview()

    def _toggle_timeline_height(self, expanded: bool) -> None:
        self.expand_timeline_button.setText("收起时间线" if expanded else "展开时间线")
        self.resizeDocks([self.timeline_dock], [320 if expanded else 160], Qt.Orientation.Vertical)

    def _toggle_help(self, checked: bool) -> None:
        self._show_help = checked
        self._refresh_next_step_hint(self.session.current_unit)

    def _remember_location(self) -> None:
        unit_id = self.session.current_unit_id
        if unit_id:
            location = (
                unit_id,
                self.session.current_node_uid,
                tuple(self.session.selected_node_uids),
                self.program_tree.verticalScrollBar().value(),
            )
            self._navigation_history.append(location)
            del self._navigation_history[:-32]

    def _navigate_unit(self, unit_id: str) -> None:
        if unit_id == self.session.current_unit_id or not self._unit_exists(unit_id):
            return
        self._remember_location()
        self.session.select_unit(unit_id)
        self._set_workspace_mode("steps")
        if self._structure_mode() == "stage_chain":
            self.refresh_project()

    def _navigate_back(self) -> None:
        while self._navigation_history:
            unit_id, node_uid, selected_uids, scroll = self._navigation_history.pop()
            if not self._unit_exists(unit_id):
                continue
            self.session.select_unit(unit_id)
            if node_uid:
                try:
                    self.session.select_node(node_uid, selected_uids=selected_uids)
                except ProgramError:
                    pass
            self._set_workspace_mode("steps")
            QTimer.singleShot(0, lambda value=scroll: self.program_tree.verticalScrollBar().setValue(value))
            self._refresh_navigation()
            return
        self._refresh_navigation()

    def _refresh_navigation(self) -> None:
        unit = self.session.current_unit
        valid = [item for item in self._navigation_history if self._unit_exists(item[0])]
        self.back_button.setEnabled(bool(valid))
        self.help_button.setEnabled(unit is not None)
        parts = []
        for unit_id, *_location in valid[-2:]:
            previous = self.session.program.get_unit(unit_id)
            parts.append(f'<a style="color:#8eb8d8;" href="{escape(unit_id)}">{escape(previous.name)}</a>')
        if unit:
            parts.append(escape(self._unit_label(unit)))
        self.breadcrumb.setText(" › ".join(parts) if parts else "未打开工程")
        self.breadcrumb.setToolTip(" → ".join(self.session.program.get_unit(item[0]).name for item in valid) + (f" → {unit.name}" if unit else ""))
        if unit is not None:
            self.steps_title.setText({"Stage": "出场安排", "Wave": "出场与发射步骤"}.get(unit.kind, "移动与发射步骤"))
        target = self.preview_owner.current_target() if unit else None
        names = {"project": "工程", "stage": "关卡", "wave": "波次", "enemy": "敌人", "spell": "符卡"}
        self.run_current_action.setText(f"运行{names.get(target.kind, '内容')} · F5" if target else "运行 · F5")
        self.run_current_action.setToolTip(f"保存、构建并运行当前编辑目标：{unit.name}" if unit else "先打开工程")

    def _show_insert_after_selection(self) -> None:
        self._show_insert_popup(
            (self.session.current_node_uid, DropPlacement.AFTER, None),
            self.add_node_button.mapToGlobal(self.add_node_button.rect().bottomLeft()),
        )

    def _show_insert_popup(self, location, global_pos) -> None:
        if not self.session.can_edit or self.session.current_unit is None:
            return
        self._insert_location = location
        self._insert_owner_id = self.session.current_unit_id
        target_uid, placement, target_slot = location
        self.insert_popup.set_context(
            self.session.program, self.session.current_unit_id, target_uid,
            self._palette_templates_cache, placement=placement, target_slot=target_slot,
        )
        self.insert_popup.show_at(global_pos)

    def _insert_popup_node(self, kind: str) -> None:
        if self.session.current_unit_id != self._insert_owner_id:
            return
        target_uid, placement, target_slot = self._insert_location
        self.insert_palette_node(kind, placement, target_uid=target_uid, target_slot=target_slot, use_current_target=False)

    def _create_popup_reference(self, expected_kinds: tuple[str, ...]) -> None:
        if self.session.current_unit_id != self._insert_owner_id:
            return
        self._create_and_place(expected_kinds, self._insert_location, node_kind=self.insert_popup.palette.current_kind())

    def _build_project_reference_panel(self, parent: QWidget) -> QWidget:
        """Build the non-statement Project Stage-order surface."""

        panel = QWidget(parent)
        panel.setObjectName("project_stage_order_panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        title = QLabel("关卡顺序", panel)
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)
        hint = QLabel(
            "从左侧“全部单元”拖动关卡到这里以加入工程；拖动已有项目可调整顺序。",
            panel,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e;")
        layout.addWidget(hint)
        self.project_stage_list = UnitReferenceListWidget(panel)
        self.project_stage_list.setObjectName("project_stage_order")
        self.project_stage_list.reference_dropped.connect(
            lambda unit_id, index: self._drop_special_reference("stages", unit_id, index)
        )
        self.project_stage_list.unit_activated.connect(self._select_referenced_unit)
        self.project_stage_list.itemSelectionChanged.connect(
            self._sync_reference_remove_buttons
        )
        layout.addWidget(self.project_stage_list, 1)
        self.project_stage_remove_button = QPushButton("移除选中关卡", panel)
        self.project_stage_remove_button.setObjectName("remove_project_stage_reference")
        self.project_stage_remove_button.clicked.connect(
            lambda: self._remove_special_reference("stages")
        )
        layout.addWidget(self.project_stage_remove_button)
        start_row = QWidget(panel)
        start_layout = QHBoxLayout(start_row)
        start_layout.setContentsMargins(0, 0, 0, 0)
        start_layout.addWidget(QLabel("开始关卡", start_row))
        self.start_stage_combo = QComboBox(start_row)
        self.start_stage_combo.setObjectName("project_start_stage")
        self.start_stage_combo.currentIndexChanged.connect(self._set_project_start_stage)
        start_layout.addWidget(self.start_stage_combo, 1)
        layout.addWidget(start_row)
        return panel

    def _build_boss_reference_panel(self, parent: QWidget) -> QWidget:
        """Build the non-statement Boss phases surface."""

        panel = QWidget(parent)
        panel.setObjectName("boss_phases_panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        title = QLabel("Boss 阶段", panel)
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)
        hint = QLabel(
            "从左侧拖动非符或符卡到这里；拖动已有阶段可调整顺序。",
            panel,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e;")
        layout.addWidget(hint)
        self.boss_phase_list = UnitReferenceListWidget(panel)
        self.boss_phase_list.setObjectName("boss_phase_order")
        self.boss_phase_list.reference_dropped.connect(
            lambda unit_id, index: self._drop_special_reference("phases", unit_id, index)
        )
        self.boss_phase_list.unit_activated.connect(self._select_referenced_unit)
        self.boss_phase_list.itemSelectionChanged.connect(
            self._sync_reference_remove_buttons
        )
        layout.addWidget(self.boss_phase_list, 1)
        phase_actions = QHBoxLayout()
        self.new_phase_button = QPushButton("＋ 新建并添加阶段…", panel)
        self.new_phase_button.setObjectName("create_boss_phase")
        self.new_phase_button.clicked.connect(
            lambda: self._create_and_place(("Spell", "NonSpell"), (None, DropPlacement.AFTER, None))
        )
        phase_actions.addWidget(self.new_phase_button)
        open_phase = QPushButton("打开内容", panel)
        open_phase.clicked.connect(lambda: self._open_reference_item(self.boss_phase_list))
        phase_actions.addWidget(open_phase)
        layout.addLayout(phase_actions)
        self.boss_phase_remove_button = QPushButton("移除选中阶段", panel)
        self.boss_phase_remove_button.setObjectName("remove_boss_phase_reference")
        self.boss_phase_remove_button.clicked.connect(
            lambda: self._remove_special_reference("phases")
        )
        layout.addWidget(self.boss_phase_remove_button)
        return panel

    def _open_reference_item(self, widget) -> None:
        item = widget.currentItem()
        if item and item.data(_ROLE_VALUE):
            self._navigate_unit(str(item.data(_ROLE_VALUE)))

    def _connect_session(self) -> None:
        self.session.project_changed.connect(self.refresh_project)
        self.session.program_changed.connect(self._program_changed)
        self.session.selection_changed.connect(self.refresh_selection)
        self.session.source_changed.connect(self.refresh_source)
        self.session.problems_changed.connect(self.refresh_problems)
        self.session.dirty_changed.connect(self._dirty_changed)
        self.session.external_conflict.connect(self._ask_external_decision)
        self.session.preview_changed.connect(self._preview_state_changed)
        self.session.build_changed.connect(self._build_state_changed)
        self.session.log_changed.connect(self.refresh_problems)
        self.preview_owner.build_published.connect(self._show_generated_entry)
        self.preview_owner.event_received.connect(self.timeline_panel.handle_preview_event)
        self.timeline_panel.seek_requested.connect(self._seek_timeline)
        self.timeline_panel.pause_requested.connect(self._pause_preview)
        self.timeline_panel.resume_requested.connect(self._resume_preview)

    def refresh_project(self) -> None:
        is_open = self.session.is_open
        if self._workspace_open != is_open:
            self.left_dock.setVisible(is_open)
            self.inspector_dock.setVisible(is_open)
            self.timeline_dock.setVisible(is_open)
            self._workspace_open = is_open
        self.show_source_action.setEnabled(is_open)
        if not is_open:
            self.game_group.hide()
            self.show_game_action.setChecked(False)
        self._palette_templates_cache = self.session.palette_templates if self.session.is_open else ()
        self.unit_list.blockSignals(True)
        self.file_list.blockSignals(True)
        self.unit_list.clear()
        self.file_list.clear()
        if self.session.source_project is not None:
            if self._structure_mode() == "stage_chain":
                self._populate_stage_reference_tree()
            else:
                self._populate_all_units_tree()
            for relative, document in sorted(
                self.session.source_project.files.items(), key=lambda item: item[0].as_posix()
            ):
                label = (
                    self._unit_label(document.unit)
                    if document.unit is not None else relative.name
                )
                label += "（不支持编辑）" if document.read_only else ""
                item = QListWidgetItem(label)
                item.setData(_ROLE_VALUE, relative.as_posix())
                item.setToolTip(f"作者文件：{relative.as_posix()}\n单击查看 Python 源码（只读）")
                self.file_list.addItem(item)
            root = self.session.project_context.root
            self.global_asset_list.set_resources(self.session.global_assets, project_root=root)
            self.stage_asset_list.set_resources(self.session.stage_assets, project_root=root)
            self._stage_assets_id = self.session.current_stage_id
        else:
            self._stage_assets_id = None
            self.global_asset_list.clear()
            self.stage_asset_list.clear()
        self.unit_list.blockSignals(False)
        self.file_list.blockSignals(False)
        for action in (
            self.refresh_assets_action,
            self.run_current_action,
            self.run_project_action,
            self.run_stage_action,
        ):
            action.setEnabled(
                self.session.is_open and (
                    action is self.refresh_assets_action or self.session.build_state != "building"
                )
            )
        self.refresh_selection()
        self.refresh_problems()
        self._apply_workspace_mode()

    def _program_changed(self) -> None:
        self.refresh_project()
        self.refresh_source()

    def _refresh_assets(self) -> None:
        if self.session.source_project is None or self.session.project_context is None:
            return
        assets = self.session.refresh_global_assets()
        root = self.session.project_context.root
        self.global_asset_list.set_resources(assets, project_root=root)
        self.stage_asset_list.set_resources(self.session.stage_assets, project_root=root)
        self.statusBar().showMessage(f"已刷新资产：{len(assets)} 项", 3000)

    def _structure_mode(self) -> str:
        return str(self.structure_mode.currentData() or "all")

    def _structure_mode_changed(self, _index: int) -> None:
        self.refresh_project()

    def _populate_all_units_tree(self) -> None:
        """Show one navigable, drag-capable projection of every logical unit."""

        groups: dict[str, QTreeWidgetItem] = {}
        ordered_kinds = tuple(_UNIT_KIND_LABELS)
        for kind in ordered_kinds:
            values = sorted(
                (unit for unit in self.session.program.logical_units() if unit.kind == kind),
                key=lambda unit: (unit.name.casefold(), unit.id),
            )
            if not values:
                continue
            group = QTreeWidgetItem([_UNIT_KIND_LABELS.get(kind, kind)])
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self.unit_list.addTopLevelItem(group)
            groups[kind] = group
            for unit in values:
                item = QTreeWidgetItem([self._unit_label(unit)])
                item.setData(0, _ROLE_VALUE, unit.id)
                group.addChild(item)
            group.setExpanded(True)

    def _populate_stage_reference_tree(self) -> None:
        stage_id = self._structure_stage_id()
        if stage_id is None:
            item = QTreeWidgetItem(["请选择关卡，或在工程中设置有效开始关卡。"])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self.unit_list.addTopLevelItem(item)
            return
        projection = stage_reference_tree(self.session.program, stage_id)

        def add_item(node, parent: QTreeWidget | QTreeWidgetItem) -> QTreeWidgetItem:
            label = self._reference_tree_label(node)
            item = QTreeWidgetItem([label])
            if not node.missing:
                item.setData(0, _ROLE_VALUE, node.unit_id)
            else:
                item.setForeground(0, Qt.GlobalColor.red)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            if isinstance(parent, QTreeWidget):
                parent.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in node.children:
                add_item(child, item)
            if node.children:
                item.setExpanded(True)
            return item

        add_item(projection, self.unit_list)

    def _structure_stage_id(self) -> str | None:
        stage_id = self.session.current_stage_id
        if stage_id is not None:
            return stage_id
        project = next(
            (unit for unit in self.session.program.logical_units() if unit.kind == "Project"),
            None,
        )
        start = project.metadata.get("start_stage") if project is not None else None
        if isinstance(start, Ref):
            try:
                candidate = self.session.program.get_unit(start.id)
            except ProgramError:
                return None
            if candidate.kind == "Stage":
                return candidate.id
        return None

    @staticmethod
    def _unit_label(unit) -> str:
        return f"{_UNIT_KIND_LABELS.get(unit.kind, unit.kind)} · {unit.name}"

    @staticmethod
    def _reference_tree_label(node) -> str:
        if node.missing:
            return f"未解析引用 · {node.unit_id}"
        label = f"{_UNIT_KIND_LABELS.get(node.kind or '', node.kind or '未知')} · {node.name}"
        if node.cycle:
            return f"↩ 循环引用 · {label}"
        if node.link:
            return f"↗ 已在上方显示 · {label}"
        return label

    def refresh_selection(self) -> None:
        """Re-entrancy guard: palette and inspector updates can re-enter here."""

        if self._refreshing_selection:
            return
        self._refreshing_selection = True
        try:
            self._refresh_selection()
        finally:
            self._refreshing_selection = False

    def _refresh_selection(self) -> None:
        self.program_tree.set_unit_labels({
            unit.id: unit.name for unit in self.session.program.logical_units()
        } if self.session.is_open else {})
        self.program_tree.set_unit(
            self.session.current_unit,
            self.session.current_node_uid,
            self.session.selected_node_uids,
        )
        self._select_unit(self.session.current_unit_id)
        self.program_tree.set_diagnostics(self._node_error_messages())
        if self.session.source_project is not None and self._stage_assets_id != self.session.current_stage_id:
            self.stage_asset_list.set_resources(
                self.session.stage_assets,
                project_root=self.session.project_context.root,
            )
            self._stage_assets_id = self.session.current_stage_id
        unit = self.session.current_unit
        node = self.session.current_node
        statement_editable = bool(
            unit and unit_accepts_statements(unit.kind) and self.session.can_edit
        )
        self.program_toolbar.setVisible(statement_editable)
        self.node_palette.setVisible(statement_editable and self.show_palette_action.isChecked())
        unit_editable = bool(unit and unit.kind != "Project" and self.session.can_edit)
        has_selection = bool(self.program_tree.selected_node_uids())
        self.copy_node_button.setEnabled(statement_editable and has_selection)
        self.copy_node_action.setEnabled(statement_editable and has_selection)
        self.paste_node_button.setEnabled(statement_editable and bool(self._node_clipboard))
        self.paste_node_action.setEnabled(statement_editable and bool(self._node_clipboard))
        self.delete_node_button.setEnabled(statement_editable and has_selection)
        self.delete_node_action.setEnabled(statement_editable and has_selection)
        self.new_unit_button.setEnabled(self.session.is_open)
        self.duplicate_unit_button.setEnabled(unit_editable)
        self.delete_unit_button.setEnabled(unit_editable)
        self.node_palette.set_context(
            self.session.program if self.session.is_open else None,
            unit.id if unit is not None else None,
            node.uid if node is not None else None,
            self._palette_templates_cache,
        )
        self.add_node_button.setEnabled(statement_editable)
        self._refresh_special_reference_surface(unit)
        self._refresh_next_step_hint(unit)
        self._refresh_navigation()

    def _refresh_special_reference_surface(self, unit) -> None:
        if unit is None:
            self.program_content_stack.setCurrentWidget(
                self.welcome_panel if not self.session.is_open else self.program_tree
            )
            return
        if unit.kind == "Project":
            references = tuple(
                reference.id
                for reference in unit.metadata.get("stages", ())
                if isinstance(reference, Ref)
            )
            candidates = tuple(
                item
                for item in self.session.program.logical_units()
                if item.kind in reference_list_target_kinds("Project", "stages")
            )
            labels = tuple(
                (reference, self._unit_label(self.session.program.get_unit(reference)))
                for reference in references
                if self._unit_exists(reference)
            )
            self.project_stage_list.set_references(
                labels,
                allowed_ids=(item.id for item in candidates),
            )
            self._sync_reference_remove_buttons()
            start = unit.metadata.get("start_stage")
            self.start_stage_combo.blockSignals(True)
            try:
                self.start_stage_combo.clear()
                for reference in references:
                    if self._unit_exists(reference):
                        target = self.session.program.get_unit(reference)
                        self.start_stage_combo.addItem(self._unit_label(target), reference)
                if isinstance(start, Ref):
                    index = self.start_stage_combo.findData(start.id)
                    if index >= 0:
                        self.start_stage_combo.setCurrentIndex(index)
            finally:
                self.start_stage_combo.blockSignals(False)
            self.program_content_stack.setCurrentWidget(self.project_reference_panel)
            return
        if unit.kind == "Boss":
            references = tuple(
                reference.id
                for reference in unit.metadata.get("phases", ())
                if isinstance(reference, Ref)
            )
            candidates = tuple(
                item
                for item in self.session.program.logical_units()
                if item.kind in reference_list_target_kinds("Boss", "phases")
            )
            labels = tuple(
                (reference, self._unit_label(self.session.program.get_unit(reference)))
                for reference in references
                if self._unit_exists(reference)
            )
            self.boss_phase_list.set_references(
                labels,
                allowed_ids=(item.id for item in candidates),
            )
            self._sync_reference_remove_buttons()
            self.program_content_stack.setCurrentWidget(self.boss_reference_panel)
            return
        self.program_content_stack.setCurrentWidget(self.program_tree)

    def _drop_special_reference(self, field: str, unit_id: str, index: int) -> None:
        owner = self.session.current_unit
        if owner is None:
            return
        expected = reference_list_target_kinds(owner.kind, field)
        try:
            target = self.session.program.get_unit(unit_id)
            if target.kind not in expected:
                raise ProgramError(
                    "reference_type",
                    f"{field} 只能引用 {'/'.join(expected)}",
                )
            current = [
                reference.id
                for reference in owner.metadata.get(field, ())
                if isinstance(reference, Ref)
            ]
            if unit_id in current:
                old_index = current.index(unit_id)
                current.pop(old_index)
                if old_index < index:
                    index -= 1
            index = max(0, min(index, len(current)))
            current.insert(index, unit_id)
            if tuple(current) == tuple(
                reference.id
                for reference in owner.metadata.get(field, ())
                if isinstance(reference, Ref)
            ):
                return
            self.session.set_unit_references(owner.id, field, tuple(current))
            self.statusBar().showMessage("引用顺序已更新", 2500)
        except Exception as exc:
            self.statusBar().showMessage(f"引用未更新：{exc}", 5000)

    def _sync_reference_remove_buttons(self) -> None:
        """Enable a visible removal action only for an editable selected Ref."""

        editable = self.session.can_edit
        self.new_phase_button.setEnabled(editable)
        self.project_stage_remove_button.setEnabled(
            editable and self.project_stage_list.currentItem() is not None
        )
        self.boss_phase_remove_button.setEnabled(
            editable and self.boss_phase_list.currentItem() is not None
        )

    def _remove_special_reference(self, field: str) -> None:
        """Remove one Project Stage or Boss phase through the one Undo stack.

        A start Stage cannot disappear by accident: the author first chooses a
        different start Stage in the visible combobox, then removes the old
        registration.  The headless operation remains the final validator for
        empty or mistyped lists.
        """

        owner = self.session.current_unit
        expected = reference_list_target_kinds(owner.kind, field) if owner else ()
        list_widget = (
            self.project_stage_list if field == "stages" else self.boss_phase_list
        )
        item = list_widget.currentItem()
        if owner is None or not expected or item is None:
            self.statusBar().showMessage("请先选择要移除的引用", 4000)
            return
        unit_id = item.data(_ROLE_VALUE)
        if not unit_id:
            self.statusBar().showMessage("无法识别要移除的引用", 4000)
            return
        current = [
            reference.id
            for reference in owner.metadata.get(field, ())
            if isinstance(reference, Ref)
        ]
        if str(unit_id) not in current:
            self.statusBar().showMessage("该引用已不在当前列表中", 4000)
            return
        if (
            owner.kind == "Project"
            and owner.metadata.get("start_stage") == Ref(str(unit_id))
        ):
            self.statusBar().showMessage(
                "请先在“开始关卡”中明确选择另一个关卡", 5000
            )
            return
        try:
            current.remove(str(unit_id))
            self.session.set_unit_references(owner.id, field, tuple(current))
            self.statusBar().showMessage("引用已移除", 2500)
        except Exception as exc:
            self.statusBar().showMessage(f"引用未更新：{exc}", 5000)

    def _set_project_start_stage(self, _index: int) -> None:
        unit = self.session.current_unit
        stage_id = self.start_stage_combo.currentData()
        if unit is None or unit.kind != "Project" or not stage_id:
            return
        if unit.metadata.get("start_stage") == Ref(str(stage_id)):
            return
        try:
            self.session.set_unit_field(unit.id, "start_stage", Ref(str(stage_id)))
            self.statusBar().showMessage("开始关卡已更新", 2500)
        except Exception as exc:
            self.statusBar().showMessage(f"无法设置开始关卡：{exc}", 5000)

    def _select_referenced_unit(self, unit_id: str) -> None:
        try:
            self._navigate_unit(unit_id)
        except ProgramError:
            return

    def _refresh_next_step_hint(self, unit) -> None:
        if unit is None:
            message = "从“文件 → 新建工程”开始，或打开已有工程。"
        elif unit.kind == "Project":
            message = "下一步：拖动关卡到右侧关卡顺序，并选择开始关卡。"
        elif unit.kind == "Stage":
            message = "下一步：从左侧拖动波次或 Boss 到中间程序流。"
        elif unit.kind == "Wave":
            message = "下一步：从左侧拖动敌人，或从节点库加入生成与等待。"
        elif unit.kind == "Boss":
            message = "下一步：拖动非符或符卡到右侧 Boss 阶段列表。"
        elif unit.kind in {"Enemy", "Spell", "NonSpell"}:
            message = "下一步：从节点库组合移动、等待和弹幕。"
        else:
            message = "下一步：从节点库添加可执行节点，或把该单元拖入调用位置。"
        self.next_step_hint.setText(message)
        if unit is None:
            self.authoring_guide.configure("", "", ())
            return
        target = self.preview_owner.current_target()
        target_names = {"project": "整个工程", "stage": "这一关", "wave": "这一波内容", "enemy": "这只敌人", "spell": "这张符卡"}
        title = f"正在编辑：{_UNIT_KIND_LABELS.get(unit.kind, unit.kind)} · {unit.name}"
        preview_hint = f"F5 将运行{target_names.get(target.kind, '当前内容')}。"
        if unit.kind == "Stage":
            description = "关卡安排敌人和 Boss 的出场顺序。弹幕的具体形状在敌人或符卡中编辑。"
            actions = [("add_wave", "添加一波弹幕"), ("run_stage", "运行这一关")]
            if self._find_emitter_unit(unit):
                actions.insert(0, ("edit_emitter", "修改已有弹幕"))
        elif unit.kind == "Wave":
            description = "波次安排一组敌人的出场，也可以直接发射弹幕。打开这一波的发射步骤，再调整子弹的数量、速度和颜色。"
            emission_action = (
                ("edit_emitter", "修改这一波弹幕")
                if self._find_emitter_unit(unit)
                else ("focus_emission", "添加环形弹幕")
            )
            actions = [emission_action, ("run_current", "预览这一波"), ("open_stage", "回到关卡")]
        elif unit.kind in {"Enemy", "Spell", "NonSpell"}:
            description = "选中发射步骤，在右侧属性中改参数；等待控制间隔，重复控制轮数。想改变整关顺序，再回到关卡。"
            has_emission = any(node.kind.startswith("Fire") or node.kind == "TemplateCall" for node in unit.walk_nodes())
            actions = [("focus_emission", "修改发射参数" if has_emission else "添加环形发射"), ("run_current", "预览弹幕" if target.kind in {"enemy", "spell"} else "运行所属关卡"), ("open_stage", "回到关卡")]
        elif unit.kind == "Project":
            description = "工程只保存关卡顺序和开始关卡。打开第一关后，才能安排敌人和弹幕。"
            actions = [("open_stage", "打开开始关卡"), ("new_content", "新建关卡内容")]
        elif unit.kind == "Boss":
            description = "Boss 在这里排列符卡和非符阶段；选中具体阶段，再编辑它的移动与弹幕。"
            actions = [("edit_emitter", "打开弹幕阶段"), ("open_stage", "回到关卡")]
        else:
            description = "这里编辑可复用的步骤。参数、调用和后台任务在“更多动作”中；需要时可从“视图”打开源码。"
            actions = [("run_current", "运行所属关卡"), ("open_stage", "回到关卡")]
        self.authoring_guide.configure(title, f"{description} {preview_hint}", tuple(actions))
        empty = unit_accepts_statements(unit.kind) and not unit.body
        self.authoring_guide.setVisible(self._show_help or empty)

    def _set_source_tabs_visible(self, visible: bool) -> None:
        if not visible:
            self.editor_tabs.setCurrentIndex(0)
        for index in (1, 2):
            self.editor_tabs.setTabVisible(index, visible)
        self.editor_tabs.tabBar().setVisible(visible)

    def _find_emitter_unit(self, unit):
        pending = [unit]
        visited = set()
        while pending:
            candidate = pending.pop(0)
            if candidate.id in visited:
                continue
            visited.add(candidate.id)
            if candidate.kind in {"Enemy", "Spell", "NonSpell"}:
                return candidate
            if any(node.kind.startswith("Fire") or node.kind == "TemplateCall" for node in candidate.walk_nodes()):
                return candidate
            for edge in unit_reference_edges(self.session.program, candidate.id):
                reference_id = edge.target_id
                if self._unit_exists(reference_id):
                    pending.append(self.session.program.get_unit(reference_id))
        return None

    def _guide_action(self, action: str) -> None:
        if action == "open_stage":
            stage_id = self.session.current_stage_id or self._structure_stage_id()
            if stage_id:
                self._navigate_unit(stage_id)
        elif action == "edit_emitter":
            unit = self.session.current_unit
            emitter = self._find_emitter_unit(unit) if unit else None
            if emitter:
                self._navigate_unit(emitter.id)
                self._focus_emission()
            else:
                self.statusBar().showMessage("还没有发射步骤；回到关卡添加一波弹幕。", 5000)
        elif action == "focus_emission":
            self._focus_emission()
        elif action == "add_wave":
            self._add_starter_wave()
        elif action == "run_current":
            self._run_current()
        elif action == "run_stage":
            self._run_current_stage()
        elif action == "new_content":
            self._create_unit()

    def _focus_emission(self) -> None:
        unit = self.session.current_unit
        if unit is None:
            return
        node = next((item for item in unit.walk_nodes() if item.kind.startswith("Fire") or item.kind == "TemplateCall"), None)
        if node is None and unit.kind in {"Enemy", "Spell", "NonSpell", "Wave"} and self.session.can_edit:
            node = self.node_palette.make_node("FireCircle")
            if unit.body and unit.body[-1].kind == "Kill":
                self.session.insert_node_relative(unit.body[-1].uid, DropPlacement.BEFORE, node)
            else:
                self.session.append_node(node)
        if node is not None:
            self.session.select_node(node.uid)
            self.inspector_dock.show()
            self.inspector.focus_suggested_field()

    def _add_starter_wave(self) -> None:
        stage_id = self.session.current_stage_id
        if not stage_id or not self.session.can_edit:
            return
        labels = [label for _key, label in STARTER_PATTERNS]
        label, accepted = QInputDialog.getItem(self, "添加一波弹幕", "从哪种形状开始？（每个步骤都可修改）", labels, 0, False)
        if not accepted:
            return
        pattern = dict((label, key) for key, label in STARTER_PATTERNS)[label]
        enemy, wave = make_starter_wave(self.session.program.units.keys(), pattern)
        target_uid = self.session.current_node_uid if self.session.current_unit_id == stage_id else None
        run_node = dsl.RunWave(Ref(wave.id))
        candidate = create_program_unit(self.session.program, enemy)
        candidate = create_program_unit(candidate, wave)
        insert_new_node(candidate, stage_id, run_node, target_uid, DropPlacement.AFTER)
        self._remember_location()
        self.session.undo_stack.beginMacro(f"添加{label}出场")
        try:
            self.session.create_unit(enemy)
            self.session.create_unit(wave)
            self.session.select_unit(stage_id)
            if target_uid:
                self.session.insert_node_relative(target_uid, DropPlacement.AFTER, run_node)
            else:
                self.session.append_node(run_node)
        finally:
            self.session.undo_stack.endMacro()
        self.session.select_unit(enemy.id)
        self._focus_emission()

    def _unit_exists(self, unit_id: str) -> bool:
        try:
            self.session.program.get_unit(unit_id)
        except ProgramError:
            return False
        return True

    def refresh_source(self) -> None:
        text = self.session.source_text
        if self.code_view.toPlainText() != text:
            self.code_view.setPlainText(text)

    def refresh_problems(self) -> None:
        lines = []
        for diagnostic in self.session.diagnostics:
            location = diagnostic.source_path or "工程"
            if diagnostic.span is not None:
                location += f":{diagnostic.span.start_line}"
            lines.append(
                f"[{diagnostic.severity}] {diagnostic.code} · {location} · {diagnostic.message}"
            )
        if self.session.run_log:
            if lines:
                lines.append("")
            lines.append("—— 运行日志 ——")
            lines.extend(self.session.run_log)
        self.problems_view.setPlainText("\n".join(lines) if lines else "没有问题")

    def _activate_unit(self, unit_id: str) -> None:
        self._navigate_unit(unit_id)

    def _create_unit(self) -> None:
        self._create_and_place(None, (self.session.current_node_uid, DropPlacement.AFTER, None))

    def _create_and_place(self, expected_kinds, location, *, node_kind: str | None = None) -> str | None:
        if not self.session.is_open or not self.session.can_edit:
            return None
        owner = self.session.current_unit
        owner_id = owner.id if owner else None
        preferred = {"Project": "Stage", "Stage": "Wave", "Wave": "Enemy", "Boss": "Spell"}.get(owner.kind if owner else "", owner.kind if owner else "Stage")
        dialog = _UnitDialog(
            self.session.program, self, initial_kind=preferred, allowed_kinds=expected_kinds,
            placement_label="创建内容及其引用可用一次撤销恢复",
            placement_owner_kind=owner.kind if owner else None,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        kind, unit_id, name, register_stage, phase_id, texture = dialog.values()
        try:
            if not unit_id or not name:
                raise ProgramError("invalid_unit", "ID 和显示名不能为空")
            if not unit_id.isidentifier():
                raise ProgramError("invalid_unit", "ID 必须是 Python 标识符（字母、数字、下划线）")
            if kind == "Boss" and phase_id is None:
                raise ProgramError("missing_phase", "请先新建符卡或非符")
            unit = _new_logical_unit(kind, unit_id, name, phase_id, texture)
            candidate = create_program_unit(self.session.program, unit, register_stage=register_stage)
            node = None
            phase_refs = None
            place = not dialog.place_here.isHidden() and dialog.place_here.isChecked()
            target_uid, placement, target_slot = location
            if place and owner and owner.kind == "Boss":
                phase_refs = [item.id for item in owner.metadata.get("phases", ()) if isinstance(item, Ref)]
                phase_refs.append(unit_id)
                set_unit_reference_list(candidate, owner.id, "phases", phase_refs)
            elif place and owner:
                if node_kind:
                    node = node_from_palette(node_kind, candidate, owner.kind, unit_id)
                else:
                    options = [action for action in unit_reference_actions(kind) if node_kind_allowed_in_unit(action.node_kind, owner.kind)]
                    selected = options[0]
                    if len(options) > 1:
                        labels = [_REFERENCE_ACTION_LABELS.get(action.key, action.node_kind) for action in options]
                        label, accepted = QInputDialog.getItem(self, "如何使用新内容", "添加方式", labels, 0, False)
                        if not accepted:
                            return None
                        selected = options[labels.index(label)]
                    node = node_from_unit_reference(candidate, owner.kind, unit_id, selected.key)
                insert_new_node(candidate, owner.id, node, target_uid, placement, target_slot=target_slot)
            self._remember_location()
            self.session.undo_stack.beginMacro(f"新建并放置{name}" if place else f"新建{name}")
            try:
                self.session.create_unit(unit, register_stage=register_stage)
                if node and owner_id:
                    self.session.select_unit(owner_id)
                    if target_uid:
                        self.session.insert_node_relative(target_uid, placement, node, target_slot=target_slot)
                    else:
                        self.session.append_node(node)
                elif phase_refs and owner_id:
                    self.session.set_unit_references(owner_id, "phases", tuple(phase_refs))
            finally:
                self.session.undo_stack.endMacro()
            self.session.select_unit(unit_id)
            self._set_workspace_mode("steps")
            self.statusBar().showMessage("已创建并放到原位置；返回可继续安排出场。" if place else "内容已创建。", 4000)
            return unit_id
        except Exception as exc:
            QMessageBox.warning(self, "无法新建", str(exc))
            return None

    def _duplicate_unit(self) -> None:
        source = self.session.current_unit
        if source is None or source.kind == "Project":
            return
        dialog = _UnitDialog(self.session.program, self, source=source)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        _kind, unit_id, name, register_stage, _phase_id, _texture = dialog.values()
        try:
            if not unit_id.isidentifier():
                raise ProgramError("invalid_unit", "ID 必须是 Python 标识符（字母、数字、下划线）")
            self.session.duplicate_unit(
                source.id, unit_id, name, register_stage=register_stage
            )
        except Exception as exc:
            QMessageBox.warning(self, "无法复制", str(exc))

    def _delete_unit(self) -> None:
        unit = self.session.current_unit
        if unit is None or unit.kind == "Project":
            return
        replacement = None
        if unit.kind == "Stage":
            project = next(
                (item for item in self.session.program.logical_units() if item.kind == "Project"),
                None,
            )
            if project and project.metadata.get("start_stage") == Ref(unit.id):
                candidates = [
                    ref.id for ref in project.metadata.get("stages", ()) if ref.id != unit.id
                ]
                if not candidates:
                    QMessageBox.warning(self, "无法删除", "不能删除唯一的开始关卡")
                    return
                replacement, accepted = QInputDialog.getItem(
                    self, "选择新的开始关卡", "开始关卡：", candidates, 0, False
                )
                if not accepted:
                    return
        if QMessageBox.question(
            self, "删除逻辑单元", f"删除 {unit.kind} · {unit.name}？\n保存前可以撤销。"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.session.delete_unit(unit.id, replacement_start_stage=replacement)
        except ProgramError as exc:
            if exc.code == "unit_in_use":
                self._show_reference_block(unit.id)
            else:
                QMessageBox.warning(self, "无法删除", str(exc))
        except Exception as exc:
            QMessageBox.warning(self, "无法删除", str(exc))

    def _show_reference_block(self, unit_id: str) -> None:
        """List the blocking reference locations and let the author jump to them."""

        locations = unit_reference_locations(self.session.program, unit_id)
        dialog = QDialog(self)
        dialog.setWindowTitle("无法删除：仍被引用")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            f"{unit_id} 还被以下位置引用；删除会破坏它们，请先修改这些引用。"
        ))
        listing = QListWidget(dialog)
        for location in locations:
            listing.addItem(location)
        listing.itemDoubleClicked.connect(
            lambda item: self._jump_to_reference(item.text()) or dialog.close()
        )
        layout.addWidget(listing)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        buttons.clicked.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.resize(420, 260)
        dialog.exec()

    def _jump_to_reference(self, location: str) -> None:
        parts = location.split(".")
        unit_id = parts[0]
        node_uid = parts[1] if len(parts) > 1 else None
        try:
            self.session.select_unit(unit_id)
            if node_uid:
                self.session.select_node(node_uid)
        except Exception:
            pass

    def _file_selected(self) -> None:
        items = self.file_list.selectedItems()
        if items:
            self._remember_location()
            self.session.select_source(items[0].data(_ROLE_VALUE))
            self._set_workspace_mode("steps")
            self.show_source_action.setChecked(True)
            self.editor_tabs.setCurrentWidget(self.code_view)

    def _node_selected(self, uid) -> None:
        self.session.select_node(
            str(uid) if uid else None,
            selected_uids=self.program_tree.selected_node_uids(),
        )

    def _move_node(
        self, uid: str, target_uid: str, placement: str, target_slot=None
    ) -> None:
        try:
            self.session.move_node(
                uid, target_uid, placement, target_slot=target_slot
            )
            self.session.select_node(uid)
            self.program_tree.flash(uid)
        except Exception as exc:
            self.statusBar().showMessage(f"节点未移动：{exc}", 5000)

    def _unit_reference_drop_actions(
        self,
        target_id: str,
        target_uid: str | None,
        placement: DropPlacement | str,
        target_slot: str | None,
    ) -> list[tuple[object, DropCheck]]:
        """Derive every legal drop meaning without making a UI type table."""

        unit = self.session.current_unit
        if unit is None or not unit_accepts_statements(unit.kind):
            return []
        target = self.session.program.get_unit(target_id)
        results: list[tuple[object, DropCheck]] = []
        for action in unit_reference_actions(target.kind):
            node = node_from_unit_reference(
                self.session.program,
                unit.kind,
                target.id,
                action.key,
            )
            check = validate_insert(
                self.session.program,
                unit.id,
                node,
                target_uid,
                placement,
                target_slot=target_slot,
            )
            if check.allowed:
                results.append((action, check))
        return results

    def _drop_unit_reference(
        self,
        unit_id: str,
        target_uid,
        placement: str,
        target_slot,
    ) -> None:
        try:
            resolved_target = str(target_uid) if target_uid else None
            resolved_placement = DropPlacement(placement)
            options = self._unit_reference_drop_actions(
                unit_id,
                resolved_target,
                resolved_placement,
                target_slot,
            )
            if not options:
                raise ProgramError("invalid_unit_drop", "该逻辑单元不能放到当前位置")
            selected = options[0][0]
            if len(options) > 1:
                menu = QMenu(self)
                actions = {
                    menu.addAction(_REFERENCE_ACTION_LABELS.get(item.key, item.node_kind)): item
                    for item, _check in options
                }
                choice = menu.exec(QCursor.pos())
                if choice is None:
                    return
                selected = actions[choice]
            owner = self.session.current_unit
            assert owner is not None
            node = node_from_unit_reference(
                self.session.program,
                owner.kind,
                unit_id,
                selected.key,
            )
            if resolved_target is None:
                self.session.append_node(node)
            else:
                self.session.insert_node_relative(
                    resolved_target,
                    resolved_placement,
                    node,
                    target_slot=target_slot,
                )
            self.session.select_node(node.uid)
            self.program_tree.flash(node.uid)
            self.inspector.focus_suggested_field()
        except Exception as exc:
            self.statusBar().showMessage(f"逻辑单元未插入：{exc}", 6000)

    def _insert_selected_prototype(self, *args) -> None:
        kind = next(
            (value for value in args if isinstance(value, str) and value),
            self.node_palette.current_kind(),
        )
        if kind is None:
            self.statusBar().showMessage("请先在左侧节点库选择节点", 4000)
            return
        self.insert_palette_node(kind, DropPlacement.AFTER)

    def _drop_prototype(self, kind: str, target_uid, placement: str, target_slot) -> None:
        self.insert_palette_node(
            kind, placement, target_uid=target_uid, target_slot=target_slot,
            use_current_target=False,
        )

    def insert_palette_node(
        self,
        kind: str,
        placement: DropPlacement | str = DropPlacement.AFTER,
        *,
        target_uid: str | None = None,
        target_slot: str | None = None,
        use_current_target: bool = True,
    ) -> Node | None:
        placement = DropPlacement(placement)
        try:
            unit = self.session.current_unit
            if unit is None or not unit_accepts_statements(unit.kind):
                raise ProgramError("no_unit", "请先选择可编辑逻辑单元")
            if target_uid is None and use_current_target:
                target_uid = self.session.current_node_uid
            entry = self.node_palette.entry(kind)
            candidates = self.node_palette.reference_candidates(kind)
            reference_id = None
            if entry.reference_kinds and not candidates:
                self._create_and_place(entry.reference_kinds, (target_uid, placement, target_slot), node_kind=kind)
                return None
            if entry.reference_kinds and reference_id is None:
                reference_id, accepted = QInputDialog.getItem(
                    self, f"选择 {entry.label} 目标", "引用：", list(candidates), 0, False
                )
                if not accepted:
                    return None
            node = self.node_palette.make_node(kind, reference_id)
            if target_uid is None:
                if placement not in {DropPlacement.BEFORE, DropPlacement.AFTER}:
                    raise ProgramError("invalid_insert", "请先选择可包含内容的节点")
                self.session.append_node(node)
            else:
                self.session.insert_node_relative(
                    target_uid, placement, node, target_slot=target_slot
                )
            self.node_palette.remember(kind)
            self.session.select_node(node.uid)
            self.program_tree.flash(node.uid)
            self.inspector.focus_suggested_field()
            return node
        except Exception as exc:
            self.statusBar().showMessage(f"节点未添加：{exc}", 6000)
            return None

    def _offer_unit_creation(self, expected_kinds: tuple[str, ...]) -> str | None:
        return self._create_and_place(expected_kinds, (self.session.current_node_uid, DropPlacement.AFTER, None))

    def _copy_selected_nodes(self) -> None:
        uids = self.program_tree.selected_node_uids()
        if not uids and self.session.current_node_uid:
            uids = (self.session.current_node_uid,)
        if not uids:
            self.statusBar().showMessage("请先选择要复制的节点", 4000)
            return
        try:
            self._node_clipboard = tuple(
                find_node(self.session.program, uid)[1].clone() for uid in uids
            )
            self.statusBar().showMessage(f"已复制 {len(uids)} 个节点", 2500)
            self.refresh_selection()
        except Exception as exc:
            self.statusBar().showMessage(f"节点未复制：{exc}", 5000)

    def _paste_nodes(self) -> None:
        if not self._node_clipboard:
            self.statusBar().showMessage("剪贴板中没有节点", 4000)
            return
        unit = self.session.current_unit
        if unit is None or not unit_accepts_statements(unit.kind):
            self.statusBar().showMessage("请先选择可编辑逻辑单元", 4000)
            return
        clones = tuple(clone_node_with_new_uids(node) for node in self._node_clipboard)
        target_uid = self.session.current_node_uid
        try:
            simulated = self.session.program
            simulated_target = target_uid
            for node in clones:
                simulated = insert_new_node(
                    simulated,
                    unit.id,
                    node,
                    simulated_target,
                    DropPlacement.AFTER,
                )
                simulated_target = node.uid
        except Exception as exc:
            self.statusBar().showMessage(f"节点未粘贴：{exc}", 5000)
            return

        self.session.undo_stack.beginMacro(f"粘贴 {len(clones)} 个节点")
        try:
            target_uid = self.session.current_node_uid
            for node in clones:
                if target_uid is None:
                    self.session.append_node(node)
                else:
                    self.session.insert_node_relative(
                        target_uid, DropPlacement.AFTER, node
                    )
                target_uid = node.uid
        finally:
            self.session.undo_stack.endMacro()
        if target_uid:
            self.session.select_node(target_uid)
            self.program_tree.flash(target_uid)

    def _delete_selected_nodes(self) -> None:
        selected = self.program_tree.selected_node_uids()
        if not selected and self.session.current_node_uid:
            selected = (self.session.current_node_uid,)
        if not selected:
            self.statusBar().showMessage("请先选择要删除的节点", 4000)
            return
        selected_set = set(selected)
        roots: list[str] = []
        for uid in selected:
            _unit, _node, location = find_node(self.session.program, uid)
            parent_uid = location.parent_uid
            has_selected_ancestor = False
            while parent_uid is not None:
                if parent_uid in selected_set:
                    has_selected_ancestor = True
                    break
                _owner, _parent, parent_location = find_node(
                    self.session.program, parent_uid
                )
                parent_uid = parent_location.parent_uid
            if not has_selected_ancestor:
                roots.append(uid)
        try:
            simulated = self.session.program
            for uid in reversed(roots):
                simulated = delete_node(simulated, uid)
            self.session.undo_stack.beginMacro(f"删除 {len(roots)} 个节点")
            try:
                for uid in reversed(roots):
                    self.session.delete_node(uid)
            finally:
                self.session.undo_stack.endMacro()
        except Exception as exc:
            self.statusBar().showMessage(f"节点未删除：{exc}", 6000)

    def _duplicate_selected_node(self) -> None:
        """Retain the command-level duplicate helper without exposing old UI."""

        uid = self.session.current_node_uid
        if uid is not None:
            self.session.duplicate_node(uid)

    def _focus_suggested_field(self, uid: str) -> None:
        try:
            self.session.select_node(uid)
        except Exception:
            return
        self.inspector.focus_suggested_field()

    def _node_error_messages(self) -> dict[str, tuple[str, ...]]:
        messages: dict[str, list[str]] = {}
        for diagnostic in self.session.diagnostics:
            if diagnostic.severity == "error" and diagnostic.uid:
                messages.setdefault(diagnostic.uid, []).append(diagnostic.message)
        return {uid: tuple(items) for uid, items in messages.items()}

    def _validate_program_drop(self, mime, target_uid, placement, target_slot) -> DropCheck:
        unit = self.session.current_unit
        if unit is None or not unit_accepts_statements(unit.kind) or not self.session.can_edit:
            return DropCheck(False, "当前逻辑单元不可编辑")
        try:
            if mime.hasFormat(PROTOTYPE_MIME):
                kind = bytes(mime.data(PROTOTYPE_MIME)).decode("utf-8")
                return self.node_palette.placement_check(
                    kind, target_uid, placement,
                    target_slot=target_slot,
                )
            if mime.hasFormat(UNIT_REFERENCE_MIME):
                unit_id = bytes(mime.data(UNIT_REFERENCE_MIME)).decode("utf-8")
                options = self._unit_reference_drop_actions(
                    unit_id,
                    str(target_uid) if target_uid else None,
                    placement,
                    target_slot,
                )
                if options:
                    return options[0][1]
                return DropCheck(False, "该逻辑单元不能放到当前位置")
            if mime.hasFormat(NODE_MIME):
                source_uid = bytes(mime.data(NODE_MIME)).decode("utf-8")
                if target_uid is None:
                    return DropCheck(False, "已有节点不能放到逻辑单元标题")
                move_node(
                    self.session.program, source_uid, target_uid, placement,
                    target_slot=target_slot,
                )
                return DropCheck(True)
            if mime.hasFormat(RESOURCE_MIME):
                uri = bytes(mime.data(RESOURCE_MIME)).decode("utf-8")
                actions = available_resource_actions(uri)
                if not actions:
                    return DropCheck(False, "该资源只能拖到兼容的检查器字段")
                if placement == DropPlacement.WRAP or target_uid is None:
                    return DropCheck(False, "资源只能放到节点之间的插入线")
                checks = tuple(
                    validate_insert(
                        self.session.program,
                        unit.id,
                        node_for_resource_action(action.key, uri),
                        target_uid,
                        placement,
                        target_slot=target_slot,
                    )
                    for action in actions
                )
                allowed = next((check for check in checks if check.allowed), None)
                return allowed or checks[0]
            return DropCheck(False, "不支持的拖放内容")
        except Exception as exc:
            return DropCheck(False, str(exc))

    def _delete_selected_node(self) -> None:
        self._delete_selected_nodes()

    def _resource_drop(self, uri: str, target_uid: str, placement: str, target_slot=None) -> None:
        actions = available_resource_actions(uri)
        if not actions:
            self.statusBar().showMessage("该资源只能拖到兼容的检查器字段", 5000)
            return
        selected_action = self._choose_resource_action(actions)
        if selected_action is None:
            return
        try:
            self.insert_resource_action(
                selected_action, uri, target_uid, DropPlacement(placement),
                target_slot=target_slot,
            )
        except Exception as exc:
            self.statusBar().showMessage(f"资源未插入：{exc}", 5000)

    def _choose_resource_action(self, actions) -> str | None:
        menu = QMenu(self)
        action_by_qaction = {}
        for action in actions:
            qaction = menu.addAction(action.label)
            action_by_qaction[qaction] = action.key
        selected = menu.exec(QCursor.pos())
        return action_by_qaction.get(selected)

    def insert_resource_action(
        self,
        action: str,
        uri: str,
        target_uid: str,
        placement: DropPlacement | str,
        *,
        target_slot: str | None = None,
    ) -> Node:
        node = node_for_resource_action(action, uri)
        self.session.insert_node_relative(
            target_uid, placement, node, target_slot=target_slot
        )
        self.session.select_node(node.uid)
        self.program_tree.flash(node.uid)
        self.inspector.focus_suggested_field()
        return node

    def _select_unit(self, unit_id: str | None) -> None:
        if unit_id is None:
            return
        def visit(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if item.data(0, _ROLE_VALUE) == unit_id:
                return item
            for child_index in range(item.childCount()):
                found = visit(item.child(child_index))
                if found is not None:
                    return found
            return None

        for index in range(self.unit_list.topLevelItemCount()):
            item = self.unit_list.topLevelItem(index)
            found = visit(item)
            if found is not None:
                self.unit_list.blockSignals(True)
                self.unit_list.setCurrentItem(found)
                self.unit_list.scrollToItem(found)
                self.unit_list.blockSignals(False)
                return

    def _confirm_project_transition(self) -> bool:
        """Require an explicit decision before abandoning in-memory edits."""

        if not self.session.is_open or not (
            self.session.dirty or self.session.has_conflict
        ):
            return True
        box = QMessageBox(self)
        box.setWindowTitle("尚有未保存修改")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("当前工程还有未保存修改。")
        box.setInformativeText("保存后继续、放弃内存修改，或取消当前操作。")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        choice = QMessageBox.StandardButton(box.exec())
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Discard:
            return True
        if choice != QMessageBox.StandardButton.Save:
            return False

        for _attempt in range(2):
            try:
                self.session.save_all()
                return not self.session.dirty and not self.session.has_conflict
            except SourceConflictError:
                if not self.session.pending_external_paths:
                    QMessageBox.warning(self, "无法保存", "存在未解决的外部修改")
                    return False
                self._ask_external_decision(self.session.pending_external_paths)
            except SourceSaveError as exc:
                QMessageBox.warning(self, "无法保存", str(exc))
                return False
            except Exception as exc:
                QMessageBox.warning(self, "无法保存", str(exc))
                return False
        return False

    def _choose_project(self) -> None:
        root = QFileDialog.getExistingDirectory(self, "选择声明式 Python 工程")
        if root:
            try:
                self.open_project(root)
            except Exception as exc:
                QMessageBox.critical(self, "无法打开工程", str(exc))

    def _new_project(self) -> None:
        runtime_root = (
            self.session.project_context.root
            if self.session.project_context is not None
            else Path(__file__).resolve().parents[2]
        )
        dialog = NewProjectDialog(runtime_root, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not self._confirm_project_transition():
            return
        try:
            root = create_authoring_project(*dialog.values(), include_starter=dialog.include_starter.isChecked())
            self.open_project(root, confirm_transition=False)
            if dialog.include_starter.isChecked():
                emitter = self._find_emitter_unit(self.session.current_unit)
                if emitter:
                    self.session.select_unit(emitter.id)
                    self._focus_emission()
            self.statusBar().showMessage("工程已创建：先修改发射数量或速度，然后按 F5 看效果。", 6000)
        except FileExistsError:
            QMessageBox.warning(self, "无法创建工程", "已有同名工程，请更换 ID 或打开已有工程。")
        except Exception as exc:
            QMessageBox.warning(self, "无法创建工程", str(exc))

    def _save_all(self) -> None:
        try:
            saved = self.session.save_all()
        except SourceConflictError:
            if self.session.pending_external_paths:
                self._ask_external_decision(self.session.pending_external_paths)
            else:
                QMessageBox.warning(self, "无法保存", "存在未解决的外部修改")
            return
        except SourceSaveError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        self.statusBar().showMessage(f"已保存 {len(saved)} 个文件", 3000)

    def _run_current(self) -> None:
        self._run_target(self.preview_owner.current_target())

    def _run_current_stage(self) -> None:
        stage_id = self.session.current_stage_id
        if stage_id is None:
            self.statusBar().showMessage("当前单元不属于可运行的关卡", 4000)
            return
        self._run_target(PreviewTarget("stage", stage_id))

    def _run_target(self, target: PreviewTarget) -> None:
        self._set_workspace_mode("split" if self._workspace_mode == "split" else "preview")
        if not self.preview_owner.run(target):
            self.output_dock.show()
            self.statusBar().showMessage(self.session.preview_error or "无法开始预览", 5000)

    def _pause_preview(self) -> None:
        try:
            self.preview_owner.pause()
        except RuntimeError as exc:
            self.statusBar().showMessage(str(exc), 3000)

    def _resume_preview(self) -> None:
        try:
            self.preview_owner.resume()
        except RuntimeError as exc:
            self.statusBar().showMessage(str(exc), 3000)

    def _restart_preview(self) -> None:
        try:
            self.preview_owner.restart()
        except RuntimeError as exc:
            self.statusBar().showMessage(str(exc), 3000)

    def _seek_timeline(self, frame: int) -> None:
        projection = self.timeline_panel.projection
        if projection is None:
            self.statusBar().showMessage("请先选择要查看的关卡或逻辑单元", 3000)
            return
        try:
            self.preview_owner.seek(int(frame), unit_id=projection.unit_id)
            self.statusBar().showMessage(f"预览快进到第 {frame} 帧", 2500)
        except RuntimeError as exc:
            self.statusBar().showMessage(f"无法跳转：{exc}", 4000)

    def _seek_preview(self) -> None:
        frame, accepted = QInputDialog.getInt(
            self,
            "跳转预览到帧",
            "当前运行目标中的帧：",
            value=self.session.preview_frame,
            minValue=0,
            maxValue=10_000_000,
        )
        if accepted:
            try:
                self.preview_owner.seek(frame)
            except RuntimeError as exc:
                self.statusBar().showMessage(str(exc), 3000)

    def _stop_preview(self) -> None:
        self.preview_owner.stop()

    def _preview_state_changed(self, state: str) -> None:
        labels = {
            "stopped": "已停止",
            "starting": "正在启动…",
            "running": "运行中",
            "paused": "已暂停",
            "seeking": "正在快进到目标帧…",
            "stopping": "正在停止…",
            "error": "预览错误",
        }
        stale = self.preview_owner.is_stale
        status = labels.get(state, state)
        if stale:
            status += " · 源码已改，需重新运行"
        self.preview_status.setText(status)
        self.preview_status.setToolTip(status)
        target = self.session.preview_target
        target_labels = {
            "project": "整个工程",
            "stage": "关卡",
            "wave": "波次练习场",
            "enemy": "敌人练习场",
            "spell": "符卡练习场",
        }
        if target is None:
            self.preview_target_label.setText("运行目标：尚未运行")
        else:
            kind, unit_id = target
            suffix = f" · {self.session.program.get_unit(unit_id).name}" if unit_id and self._unit_exists(unit_id) else f" · {unit_id}" if unit_id else ""
            self.preview_target_label.setText(
                f"运行目标：{target_labels.get(kind, kind)}{suffix}"
            )
        error = self.session.preview_error
        if error:
            location = (
                f"（节点 {self.session.preview_error_uid}）"
                if self.session.preview_error_uid
                else ""
            )
            self.preview_error_label.setText(f"错误{location}：{error}")
            self.preview_error_label.show()
        else:
            self.preview_error_label.clear()
            self.preview_error_label.hide()
        active = state in {"running", "paused"}
        self.pause_preview_action.setEnabled(state == "running")
        self.resume_preview_action.setEnabled(state == "paused")
        self.playback_action.setText("继续" if state == "paused" else "暂停")
        self.playback_action.setEnabled(active)
        self.restart_preview_action.setEnabled(active)
        self.seek_preview_action.setEnabled(active)
        self.stop_preview_action.setEnabled(active or self.preview_owner.is_building)
        if state == "error":
            self.output_dock.show()

    def _build_state_changed(self, state: str) -> None:
        self.authoring_guide.set_busy(state == "building")
        labels = {
            "idle": "构建：空闲",
            "building": "构建：正在保存并验证…",
            "ready": "构建：成功",
            "error": "构建：失败",
        }
        self.build_status_label.setText(labels.get(state, f"构建：{state}"))
        self.build_status_label.setVisible(state in {"building", "error"})
        if state == "building":
            self.preview_status.setText("正在保存并构建…")
        else:
            self._preview_state_changed(self.session.preview_state)
        for action in (self.run_current_action, self.run_project_action, self.run_stage_action):
            action.setEnabled(self.session.is_open and state != "building")
        self.stop_preview_action.setEnabled(
            state == "building" or self.session.preview_state not in {"stopped", "error"}
        )
        if state == "building":
            self.statusBar().showMessage("正在保存并验证生成包…")
        elif state == "ready":
            self.statusBar().showMessage("构建成功，真实预览已启动", 3000)
        elif state == "error":
            self.output_dock.show()

    def _show_generated_entry(self, generated_root: str) -> None:
        root = Path(generated_root).resolve()
        self._generated_root = root
        files = tuple(
            sorted(
                path.relative_to(root).as_posix()
                for path in root.rglob("*.py")
                if path.is_file()
            )
        )
        self.generated_file_selector.blockSignals(True)
        try:
            self.generated_file_selector.clear()
            self.generated_file_selector.addItems(files)
            preferred = "entry.py" if "entry.py" in files else (files[0] if files else "")
            if preferred:
                self.generated_file_selector.setCurrentText(preferred)
        finally:
            self.generated_file_selector.blockSignals(False)
        if files:
            self._show_generated_file(self.generated_file_selector.currentText())
        else:
            self.generated_code_view.setPlainText("生成包中没有 Python 文件。")

    def _show_generated_file(self, relative_path: str) -> None:
        root = self._generated_root
        if root is None or not relative_path:
            return
        try:
            path = (root / relative_path).resolve()
            path.relative_to(root)
            if path.suffix.lower() != ".py" or not path.is_file():
                raise OSError("目标不是生成包中的 Python 文件")
            self.generated_code_view.setPlainText(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.generated_code_view.setPlainText(f"无法读取生成文件：{exc}")

    def _ask_external_decision(self, paths: tuple[Path, ...]) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("检测到外部修改")
        box.setText("磁盘文件已变化。请选择保留当前内存版本，或重载磁盘版本。")
        box.setInformativeText("\n".join(path.as_posix() for path in paths))
        reload_button = box.addButton("重载磁盘版本", QMessageBox.ButtonRole.AcceptRole)
        keep_button = box.addButton("保留内存版本", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is reload_button:
            self.session.resolve_external_changes("reload")
        elif clicked is keep_button:
            self.session.resolve_external_changes("keep")

    def _dirty_changed(self, dirty: bool) -> None:
        root = self.session.source_project.root.name if self.session.source_project else "未打开工程"
        self.setWindowTitle(f"PySTG 关卡编辑器 · {root}{' *' if dirty else ''}")
        self.save_action.setEnabled(
            self.session.is_open and (dirty or self.session.has_conflict)
        )


def _new_logical_unit(
    kind: str, unit_id: str, name: str, phase_id: str | None, texture: str | None
) -> LogicalUnit:
    """Build one fresh logical unit; required parameters come from the dialog."""

    if kind == "Stage":
        return dsl.Stage(unit_id, name)
    if kind == "Wave":
        return dsl.Wave(unit_id, name)
    if kind == "Enemy":
        return dsl.Enemy(unit_id, name)
    if kind == "Boss":
        if not texture:
            raise ProgramError("invalid_unit", "Boss 需要一个纹理名称")
        if phase_id is None:
            raise ProgramError("missing_phase", "请先新建符卡或非符")
        return dsl.Boss(unit_id, name, texture, [Ref(phase_id)])
    if kind == "Spell":
        return dsl.Spell(unit_id, name)
    if kind == "NonSpell":
        return dsl.NonSpell(unit_id, name)
    if kind == "Task":
        return dsl.Task(unit_id, name)
    if kind == "Function":
        return dsl.Function(unit_id, name)
    raise ProgramError("invalid_unit", f"unsupported unit kind {kind!r}")


__all__ = ["EditorWindow"]

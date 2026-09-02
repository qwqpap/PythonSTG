"""Fixed code-driven editor layout wired directly to one EditorSession."""

from __future__ import annotations

from pathlib import Path

from src.authoring import dsl
from src.authoring.program import (
    clone_node_with_new_uids,
    delete_node,
    DropCheck,
    DropPlacement,
    Node,
    Ref,
    ProgramError,
    find_node,
    insert_new_node,
    move_node,
    node_from_unit_reference,
    reference_list_target_kinds,
    stage_reference_tree,
    unit_accepts_statements,
    unit_reference_actions,
    unit_reference_locations,
    validate_insert,
)
from src.authoring.python_source import SourceConflictError, SourceSaveError
from src.qt_compat.QtCore import Qt, Signal
from src.qt_compat.QtGui import QAction, QCloseEvent, QCursor
from src.qt_compat.QtWidgets import (
    QDockWidget,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QFileDialog,
    QGridLayout,
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .inspector import InspectorPanel
from .node_palette import NodePalette, PROTOTYPE_MIME
from .program_tree import (
    NODE_MIME,
    ProgramFlow,
    available_resource_actions,
    node_for_resource_action,
)
from .preview import PreviewHost, PreviewOwner, PreviewTarget
from .session import EditorSession
from .sidebars import (
    ActivitySidebar,
    RESOURCE_MIME,
    ResourceListWidget,
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
    "run_wave": "运行 Wave",
    "run_boss": "运行 Boss",
    "spawn_enemy": "生成 Enemy",
    "call": "调用",
    "spawn_task": "后台启动 Task",
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
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("复制逻辑单元" if source else "新建逻辑单元")
        form = QFormLayout(self)
        self.kind = QComboBox(self)
        all_kinds = (
            "Stage", "Wave", "Enemy", "Boss", "Spell", "NonSpell", "Task", "Function"
        )
        kinds = tuple(dict.fromkeys(allowed_kinds or all_kinds))
        self.kind.addItems([source.kind] if source else kinds)
        self.unit_id = QLineEdit(self)
        self.name = QLineEdit(self)
        self.texture = QLineEdit("boss1", self)
        if source:
            self.unit_id.setText(f"{source.id}_copy")
            self.name.setText(f"{source.name} 副本")
            self.texture.setText(str(source.metadata.get("texture", "boss1")))
        self.register_stage = QCheckBox("加入 Project 关卡顺序", self)
        self.register_stage.setChecked(False if source else True)
        self.phase = QComboBox(self)
        self.phase.addItems(
            sorted(unit.id for unit in program.logical_units() if unit.kind in {"Spell", "NonSpell"})
        )
        self.phase_hint = QLabel("Boss 至少需要一个符卡阶段，请先新建 Spell 或 NonSpell。", self)
        self.phase_hint.setWordWrap(True)
        self.phase_hint.setStyleSheet("color: #f0883e;")
        self.phase_hint.setVisible(self.phase.count() == 0)
        form.addRow("类型", self.kind)
        form.addRow("ID", self.unit_id)
        form.addRow("显示名", self.name)
        form.addRow("纹理", self.texture)
        form.addRow("Boss 首个阶段", self.phase)
        form.addRow("", self.phase_hint)
        form.addRow("Stage", self.register_stage)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._confirm_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        form.addRow(buttons)
        self.kind.currentTextChanged.connect(self._sync)
        self._sync(self.kind.currentText())

    def _sync(self, kind: str) -> None:
        self.phase.setEnabled(kind == "Boss")
        self.texture.setEnabled(kind == "Boss")
        self.register_stage.setEnabled(kind == "Stage")
        self._confirm_button.setEnabled(kind != "Boss" or self.phase.count() > 0)

    def values(self) -> tuple[str, str, str, bool, str | None, str]:
        return (
            self.kind.currentText(),
            self.unit_id.text().strip(),
            self.name.text().strip(),
            self.register_stage.isChecked(),
            self.phase.currentText() or None,
            self.texture.text().strip(),
        )


_WINDOW_STYLESHEET = """
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
"""


class ClosableGroup(QWidget):
    """A splitter child that can be hidden and restored from the View menu."""

    closed = Signal()

    def __init__(self, title: str, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(6, 2, 2, 2)
        header_layout.addWidget(QLabel(title, header))
        header_layout.addStretch(1)
        close_button = QToolButton(header)
        close_button.setObjectName(f"close_{title.lower()}_group")
        close_button.setText("×")
        close_button.setToolTip(f"关闭{title}组")
        close_button.clicked.connect(self.close_group)
        header_layout.addWidget(close_button)
        layout.addWidget(header)
        layout.addWidget(content, 1)

    def close_group(self) -> None:
        self.hide()
        self.closed.emit()

    def restore(self) -> None:
        self.show()
        self.setFocus(Qt.FocusReason.OtherFocusReason)


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
        self._node_clipboard: tuple[Node, ...] = ()
        self._refreshing_selection = False
        self.setWindowTitle("PySTG 关卡编辑器")
        self.resize(1280, 800)
        self.setStyleSheet(_WINDOW_STYLESHEET)
        self._build_actions()
        self._build_layout()
        self._connect_session()
        self.refresh_project()
        self._preview_state_changed(self.session.preview_state)

    def open_project(self, root: str | Path) -> None:
        self.session.open_project(root)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Release the single project's file watcher with the window."""

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

        run_menu = self.menuBar().addMenu("运行")
        add_action(run_menu, "run_current_action", "运行当前单元", "run_current_action", self._run_current, "F5")
        add_action(run_menu, "run_project_action", "运行整个工程", "run_project_action",
                   lambda: self._run_target(PreviewTarget("project")))
        add_action(run_menu, "run_stage_action", "运行当前 Stage", "run_stage_action", self._run_current_stage)
        run_menu.addSeparator()
        add_action(run_menu, "pause_preview_action", "暂停", "pause_preview_action", self._pause_preview)
        add_action(run_menu, "resume_preview_action", "继续", "resume_preview_action", self._resume_preview)
        add_action(run_menu, "restart_preview_action", "重新开始", "restart_preview_action", self._restart_preview)
        add_action(run_menu, "seek_preview_action", "跳转到帧…", "seek_preview_action", self._seek_preview)
        add_action(run_menu, "stop_preview_action", "停止", "stop_preview_action", self._stop_preview)

    def _build_layout(self) -> None:
        self.unit_list = UnitTreeWidget(self)
        self.unit_list.setObjectName("program_structure")
        self.unit_list.setHeaderLabels(["程序结构"])
        self.unit_list.itemSelectionChanged.connect(self._unit_selected)
        unit_panel = QWidget(self)
        unit_panel_layout = QVBoxLayout(unit_panel)
        unit_panel_layout.setContentsMargins(0, 0, 0, 0)
        unit_toolbar = QWidget(unit_panel)
        unit_toolbar_layout = QGridLayout(unit_toolbar)
        unit_toolbar_layout.setContentsMargins(2, 2, 2, 2)
        self.new_unit_button = QPushButton("新建", unit_toolbar)
        self.duplicate_unit_button = QPushButton("复制", unit_toolbar)
        self.delete_unit_button = QPushButton("删除", unit_toolbar)
        self.structure_mode = QComboBox(unit_toolbar)
        self.structure_mode.setObjectName("program_structure_mode")
        self.structure_mode.addItem("全部单元", "all")
        self.structure_mode.addItem("当前 Stage 调用链", "stage_chain")
        self.new_unit_button.clicked.connect(self._create_unit)
        self.duplicate_unit_button.clicked.connect(self._duplicate_unit)
        self.delete_unit_button.clicked.connect(self._delete_unit)
        self.structure_mode.currentIndexChanged.connect(self._structure_mode_changed)
        unit_toolbar_layout.addWidget(self.new_unit_button, 0, 0)
        unit_toolbar_layout.addWidget(self.duplicate_unit_button, 0, 1)
        unit_toolbar_layout.addWidget(self.delete_unit_button, 0, 2)
        unit_toolbar_layout.addWidget(self.structure_mode, 1, 0, 1, 3)
        unit_panel_layout.addWidget(unit_toolbar)
        unit_panel_layout.addWidget(self.unit_list, 1)
        self.next_step_hint = QLabel("打开工程后可从这里管理逻辑单元。", unit_panel)
        self.next_step_hint.setObjectName("authoring_next_step")
        self.next_step_hint.setWordWrap(True)
        self.next_step_hint.setStyleSheet("color: #8b949e; padding: 4px;")
        unit_panel_layout.addWidget(self.next_step_hint)
        self.file_list = QListWidget(self)
        self.file_list.setObjectName("file_sidebar")
        self.file_list.itemSelectionChanged.connect(self._file_selected)
        self.global_asset_list = ResourceListWidget(self)
        self.global_asset_list.setObjectName("global_asset_sidebar")
        self.stage_asset_list = ResourceListWidget(self)
        self.stage_asset_list.setObjectName("stage_asset_sidebar")
        activity = ActivitySidebar(
            unit_panel,
            self.file_list,
            self.global_asset_list,
            self.stage_asset_list,
            self,
        )
        self.activity_sidebar = activity
        self.node_palette = NodePalette(self)
        self.node_palette.insert_requested.connect(self._insert_selected_prototype)
        self.node_palette.create_reference_requested.connect(self._offer_unit_creation)
        self.node_palette.current_changed.connect(self.refresh_selection)
        left_splitter = QSplitter(Qt.Orientation.Vertical, self)
        left_splitter.setObjectName("left_authoring_splitter")
        left_splitter.addWidget(activity)
        left_splitter.addWidget(self.node_palette)
        left_splitter.setStretchFactor(0, 2)
        left_splitter.setStretchFactor(1, 3)
        left_dock = QDockWidget("工程", self)
        left_dock.setObjectName("left_activity_dock")
        left_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        left_dock.setWidget(left_splitter)
        self._allow_horizontal_compression(left_splitter)
        self._allow_horizontal_compression(activity)
        self._allow_horizontal_compression(self.node_palette)
        self._allow_horizontal_compression(left_dock, minimum_width=200)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left_dock)

        self.program_tree = ProgramFlow(self)
        self.program_tree.set_drop_validator(self._validate_program_drop)
        self.program_tree.node_selected.connect(self._node_selected)
        self.program_tree.node_activated.connect(self._focus_suggested_field)
        self.program_tree.move_requested.connect(self._move_node)
        self.program_tree.prototype_requested.connect(self._drop_prototype)
        self.program_tree.unit_reference_requested.connect(self._drop_unit_reference)
        self.program_tree.resource_action_requested.connect(self._resource_drop)
        self.program_tree.drop_feedback.connect(
            lambda message: self.statusBar().showMessage(message, 2500)
        )
        program_panel = QWidget(self)
        program_panel.setObjectName("program_editor_panel")
        program_layout = QVBoxLayout(program_panel)
        program_layout.setContentsMargins(0, 0, 0, 0)
        program_toolbar = QWidget(program_panel)
        program_toolbar.setObjectName("program_toolbar")
        program_toolbar_layout = QGridLayout(program_toolbar)
        program_toolbar_layout.setContentsMargins(4, 2, 4, 2)
        self.add_node_button = QPushButton("添加到当前节点后", program_toolbar)
        self.add_node_button.setObjectName("add_selected_node")
        self.add_node_button.setToolTip("也可以直接从左侧节点库拖到程序流中的插入线")
        self.add_node_button.clicked.connect(self._insert_selected_prototype)
        program_toolbar_layout.addWidget(self.add_node_button, 0, 0)
        self.copy_node_button = QPushButton("复制", program_toolbar)
        self.copy_node_button.setObjectName("copy_node")
        self.copy_node_button.clicked.connect(self._copy_selected_nodes)
        program_toolbar_layout.addWidget(self.copy_node_button, 0, 1)
        self.paste_node_button = QPushButton("粘贴", program_toolbar)
        self.paste_node_button.setObjectName("paste_node")
        self.paste_node_button.clicked.connect(self._paste_nodes)
        program_toolbar_layout.addWidget(self.paste_node_button, 0, 2)
        self.delete_node_button = QPushButton("删除", program_toolbar)
        self.delete_node_button.setObjectName("delete_node")
        self.delete_node_button.clicked.connect(self._delete_selected_nodes)
        program_toolbar_layout.addWidget(self.delete_node_button, 0, 3)
        self.collapse_all_button = QPushButton("全部折叠", program_toolbar)
        self.collapse_all_button.setObjectName("collapse_all_nodes")
        self.collapse_all_button.clicked.connect(self.program_tree.collapse_all)
        program_toolbar_layout.addWidget(self.collapse_all_button, 1, 0, 1, 2)
        self.expand_all_button = QPushButton("全部展开", program_toolbar)
        self.expand_all_button.setObjectName("expand_all_nodes")
        self.expand_all_button.clicked.connect(self.program_tree.expand_all)
        program_toolbar_layout.addWidget(self.expand_all_button, 1, 2, 1, 2)
        program_toolbar_layout.setColumnStretch(4, 1)
        self.program_content_stack = QStackedWidget(program_panel)
        self.program_content_stack.setObjectName("program_content_stack")
        self.project_reference_panel = self._build_project_reference_panel(program_panel)
        self.boss_reference_panel = self._build_boss_reference_panel(program_panel)
        self.program_content_stack.addWidget(self.program_tree)
        self.program_content_stack.addWidget(self.project_reference_panel)
        self.program_content_stack.addWidget(self.boss_reference_panel)
        program_layout.addWidget(program_toolbar)
        program_layout.addWidget(self.program_content_stack, 1)
        self.code_view = QPlainTextEdit(self)
        self.code_view.setObjectName("source_code_view")
        self.code_view.setReadOnly(True)
        self.code_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.generated_code_view = QPlainTextEdit(self)
        self.generated_code_view.setObjectName("generated_code_view")
        self.generated_code_view.setReadOnly(True)
        self.generated_code_view.setPlainText("构建成功后可在此查看生成 Runtime Python。")
        editor_tabs = QTabWidget(self)
        editor_tabs.setObjectName("editor_tabs")
        editor_tabs.addTab(program_panel, "可视化程序")
        editor_tabs.addTab(self.code_view, "作者 Python（只读）")
        editor_tabs.addTab(self.generated_code_view, "生成 Python（只读）")
        self.editor_group = ClosableGroup("编辑器", editor_tabs, self)
        self.editor_group.setObjectName("editor_group")

        self.preview_host = PreviewHost(self)
        self.preview_owner = PreviewOwner(self.session, self.preview_host, self)
        game_panel = QWidget(self)
        game_panel.setObjectName("game_preview_panel")
        game_layout = QVBoxLayout(game_panel)
        game_layout.setContentsMargins(0, 0, 0, 0)
        controls = QWidget(game_panel)
        controls_layout = QGridLayout(controls)
        controls_layout.setContentsMargins(4, 2, 4, 2)
        self.preview_status = QLabel("已停止", controls)
        self.preview_status.setObjectName("preview_status")
        controls_layout.addWidget(self.preview_status, 0, 0, 1, 4)
        self.preview_target_label = QLabel("运行目标：尚未运行", controls)
        self.preview_target_label.setObjectName("preview_target")
        self.preview_target_label.setStyleSheet("color: #8b949e;")
        controls_layout.addWidget(self.preview_target_label, 1, 0, 1, 4)
        self.build_status_label = QLabel("构建：空闲", controls)
        self.build_status_label.setObjectName("preview_build_status")
        self.build_status_label.setStyleSheet("color: #8b949e;")
        controls_layout.addWidget(self.build_status_label, 2, 0, 1, 4)
        self.preview_error_label = QLabel("", controls)
        self.preview_error_label.setObjectName("preview_error")
        self.preview_error_label.setStyleSheet("color: #f85149;")
        self.preview_error_label.setWordWrap(True)
        self.preview_error_label.hide()
        controls_layout.addWidget(self.preview_error_label, 3, 0, 1, 4)
        for column, (label, slot, object_name) in enumerate((
            ("运行", self._run_current, "preview_run_button"),
            ("暂停", self._pause_preview, "preview_pause_button"),
            ("继续", self._resume_preview, "preview_resume_button"),
            ("停止", self._stop_preview, "preview_stop_button"),
        )):
            button = QPushButton(label, controls)
            button.setObjectName(object_name)
            button.clicked.connect(slot)
            controls_layout.addWidget(button, 4, column)
        game_layout.addWidget(controls)
        game_layout.addWidget(self.preview_host, 1)
        game_tabs = QTabWidget(self)
        game_tabs.addTab(game_panel, "游戏画面")
        self.game_group = ClosableGroup("游戏", game_tabs, self)
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
        self.setCentralWidget(self.central_groups)

        self.show_editor_action = QAction("显示编辑器组", self, checkable=True)
        self.show_editor_action.setChecked(True)
        self.show_editor_action.triggered.connect(
            lambda visible: self._set_group_visible(self.editor_group, visible)
        )
        self.show_game_action = QAction("显示游戏组", self, checkable=True)
        self.show_game_action.setChecked(True)
        self.show_game_action.triggered.connect(
            lambda visible: self._set_group_visible(self.game_group, visible)
        )
        self.editor_group.closed.connect(lambda: self.show_editor_action.setChecked(False))
        self.game_group.closed.connect(lambda: self.show_game_action.setChecked(False))
        self.view_menu.addAction(self.show_editor_action)
        self.view_menu.addAction(self.show_game_action)

        self.inspector = InspectorPanel(self.session, self)
        self.inspector_scroll = QScrollArea(self)
        self.inspector_scroll.setObjectName("inspector_scroll")
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setWidget(self.inspector)
        self.inspector_dock = QDockWidget("检查器", self)
        self.inspector_dock.setObjectName("inspector_dock")
        self._allow_horizontal_compression(self.inspector_scroll)
        self._allow_horizontal_compression(self.inspector_dock, minimum_width=220)
        self.inspector_dock.setWidget(self.inspector_scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_dock)
        self.view_menu.addAction(self.inspector_dock.toggleViewAction())

        self.timeline_panel = TimelinePanel(self.session, self)
        self.timeline_dock = QDockWidget("时间线", self)
        self.timeline_dock.setObjectName("timeline_dock")
        self.timeline_dock.setMinimumHeight(90)
        self.timeline_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.timeline_dock.setWidget(self.timeline_panel)
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
            "从左侧“全部单元”拖动 Stage 到这里以加入工程；拖动已有项目可调整顺序。",
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
            "从左侧拖动 NonSpell 或 Spell 到这里；拖动已有阶段可调整顺序。",
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
        self.boss_phase_remove_button = QPushButton("移除选中阶段", panel)
        self.boss_phase_remove_button.setObjectName("remove_boss_phase_reference")
        self.boss_phase_remove_button.clicked.connect(
            lambda: self._remove_special_reference("phases")
        )
        layout.addWidget(self.boss_phase_remove_button)
        return panel

    def _connect_session(self) -> None:
        self.session.project_changed.connect(self.refresh_project)
        self.session.program_changed.connect(self.refresh_project)
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
                label = relative.as_posix() + ("  [只读]" if document.read_only else "")
                item = QListWidgetItem(label)
                item.setData(_ROLE_VALUE, relative.as_posix())
                self.file_list.addItem(item)
            root = self.session.project_context.root
            self.global_asset_list.set_resources(self.session.global_assets, project_root=root)
            self.stage_asset_list.set_resources(self.session.stage_assets, project_root=root)
        else:
            self.global_asset_list.clear()
            self.stage_asset_list.clear()
        self.unit_list.blockSignals(False)
        self.file_list.blockSignals(False)
        for action in (
            self.run_current_action,
            self.run_project_action,
            self.run_stage_action,
        ):
            action.setEnabled(self.session.is_open)
        self.refresh_selection()
        self.refresh_problems()

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
            item = QTreeWidgetItem(["请选择 Stage 或在 Project 中设置有效开始关卡。"])
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
        self.program_tree.set_unit(self.session.current_unit, self.session.current_node_uid)
        self._select_unit(self.session.current_unit_id)
        self.program_tree.set_diagnostics(self._node_error_messages())
        if self.session.source_project is not None:
            self.stage_asset_list.set_resources(
                self.session.stage_assets,
                project_root=self.session.project_context.root,
            )
        self.inspector.refresh()
        unit = self.session.current_unit
        node = self.session.current_node
        statement_editable = bool(
            unit and unit_accepts_statements(unit.kind) and self.session.can_edit
        )
        unit_editable = bool(unit and unit.kind != "Project" and self.session.can_edit)
        self.add_node_button.setEnabled(statement_editable and self._palette_kind_is_addable())
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
            self.session.palette_templates,
        )
        self._refresh_special_reference_surface(unit)
        self._refresh_next_step_hint(unit)
        self.refresh_source()

    def _refresh_special_reference_surface(self, unit) -> None:
        if unit is None:
            self.program_content_stack.setCurrentWidget(self.program_tree)
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
            self.session.select_unit(unit_id)
            if self._structure_mode() == "stage_chain":
                self.refresh_project()
        except ProgramError:
            return

    def _refresh_next_step_hint(self, unit) -> None:
        if unit is None:
            message = "打开工程后可从这里管理逻辑单元。"
        elif unit.kind == "Project":
            message = "下一步：拖动 Stage 到右侧关卡顺序，并明确选择开始关卡。"
        elif unit.kind == "Stage":
            message = "下一步：从左侧拖动 Wave 或 Boss 到中间程序流。"
        elif unit.kind == "Wave":
            message = "下一步：从左侧拖动 Enemy，或从节点库加入生成与等待。"
        elif unit.kind == "Boss":
            message = "下一步：拖动 NonSpell 或 Spell 到右侧 Boss 阶段列表。"
        elif unit.kind in {"Enemy", "Spell", "NonSpell"}:
            message = "下一步：从节点库组合移动、等待和弹幕。"
        else:
            message = "下一步：从节点库添加可执行节点，或把该单元拖入调用位置。"
        self.next_step_hint.setText(message)

    def _unit_exists(self, unit_id: str) -> bool:
        try:
            self.session.program.get_unit(unit_id)
        except ProgramError:
            return False
        return True

    def refresh_source(self) -> None:
        self.code_view.setPlainText(self.session.source_text)

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

    def _unit_selected(self) -> None:
        items = self.unit_list.selectedItems()
        if items:
            unit_id = items[0].data(0, _ROLE_VALUE)
            if not unit_id:
                return
            self.session.select_unit(str(unit_id))
            if self._structure_mode() == "stage_chain":
                self.refresh_project()

    def _create_unit(self) -> None:
        if not self.session.is_open:
            return
        dialog = _UnitDialog(self.session.program, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        kind, unit_id, name, register_stage, phase_id, texture = dialog.values()
        try:
            if not unit_id or not name:
                raise ProgramError("invalid_unit", "ID 和显示名不能为空")
            if not unit_id.isidentifier():
                raise ProgramError("invalid_unit", "ID 必须是 Python 标识符（字母、数字、下划线）")
            if kind == "Boss" and phase_id is None:
                raise ProgramError("missing_phase", "请先新建 Spell 或 NonSpell")
            unit = _new_logical_unit(kind, unit_id, name, phase_id, texture)
            self.session.create_unit(unit, register_stage=register_stage)
        except Exception as exc:
            QMessageBox.warning(self, "无法新建", str(exc))

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
            self.session.select_source(items[0].data(_ROLE_VALUE))

    def _node_selected(self, uid) -> None:
        self.session.select_node(str(uid) if uid else None)

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
            entry = self.node_palette.entry(kind)
            candidates = self.node_palette.reference_candidates(kind)
            reference_id = None
            if entry.reference_kinds and not candidates:
                if not self._offer_unit_creation(entry.reference_kinds):
                    return None
                candidates = self.node_palette.reference_candidates(kind)
                if not candidates:
                    return None
            if entry.reference_kinds:
                reference_id, accepted = QInputDialog.getItem(
                    self, f"选择 {entry.label} 目标", "引用：", list(candidates), 0, False
                )
                if not accepted:
                    return None
            node = self.node_palette.make_node(kind, reference_id)
            if target_uid is None and use_current_target:
                target_uid = self.session.current_node_uid
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

    def _offer_unit_creation(self, expected_kinds: tuple[str, ...]) -> bool:
        """Guide the author to create a missing referenced unit first."""

        box = QMessageBox(self)
        box.setWindowTitle("缺少可引用对象")
        box.setText(f"还没有可引用的 {'/'.join(expected_kinds)}。可以现在新建一个。")
        create_button = box.addButton(
            f"新建 {expected_kinds[0]}", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not create_button:
            return False
        dialog = _UnitDialog(
            self.session.program,
            self,
            allowed_kinds=expected_kinds,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        kind, unit_id, name, register_stage, phase_id, texture = dialog.values()
        try:
            if not unit_id or not name:
                raise ProgramError("invalid_unit", "ID 和显示名不能为空")
            if not unit_id.isidentifier():
                raise ProgramError(
                    "invalid_unit", "ID 必须是 Python 标识符（字母、数字、下划线）"
                )
            if kind == "Boss" and phase_id is None:
                raise ProgramError("missing_phase", "请先新建 Spell 或 NonSpell")
            self.session.create_unit(
                _new_logical_unit(kind, unit_id, name, phase_id, texture),
                register_stage=register_stage,
            )
            return True
        except Exception as exc:
            QMessageBox.warning(self, "无法新建", str(exc))
            return False

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

    def _palette_kind_is_addable(self) -> bool:
        """Enable the generic add action only for a compatible palette selection."""

        unit = self.session.current_unit
        kind = self.node_palette.current_kind()
        if (
            unit is None
            or not unit_accepts_statements(unit.kind)
            or not self.session.can_edit
            or not kind
        ):
            return False
        try:
            entry = self.node_palette.entry(kind)
            candidates = self.node_palette.reference_candidates(kind)
            if entry.reference_kinds and not candidates:
                return False
            node = self.node_palette.make_node(kind, candidates[0] if candidates else None)
            target = self.session.current_node_uid
            check = validate_insert(
                self.session.program, unit.id, node, target, DropPlacement.AFTER
            )
            return check.allowed
        except Exception:
            return False

    def _validate_program_drop(self, mime, target_uid, placement, target_slot) -> DropCheck:
        unit = self.session.current_unit
        if unit is None or not unit_accepts_statements(unit.kind) or not self.session.can_edit:
            return DropCheck(False, "当前逻辑单元不可编辑")
        try:
            if mime.hasFormat(PROTOTYPE_MIME):
                kind = bytes(mime.data(PROTOTYPE_MIME)).decode("utf-8")
                candidates = self.node_palette.reference_candidates(kind)
                entry = self.node_palette.entry(kind)
                if entry.reference_kinds and not candidates:
                    return DropCheck(False, f"请先新建 {'/'.join(entry.reference_kinds)}")
                node = self.node_palette.make_node(
                    kind, candidates[0] if candidates else None
                )
                return validate_insert(
                    self.session.program, unit.id, node, target_uid, placement,
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

    def _set_group_visible(self, group: ClosableGroup, visible: bool) -> None:
        if visible:
            group.restore()
        else:
            group.close_group()

    def _choose_project(self) -> None:
        root = QFileDialog.getExistingDirectory(self, "选择声明式 Python 工程")
        if root:
            try:
                self.open_project(root)
            except Exception as exc:
                QMessageBox.critical(self, "无法打开工程", str(exc))

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
            self.statusBar().showMessage("当前单元不属于可运行的 Stage", 4000)
            return
        self._run_target(PreviewTarget("stage", stage_id))

    def _run_target(self, target: PreviewTarget) -> None:
        self.show_game_action.setChecked(True)
        self.game_group.restore()
        if not self.preview_owner.run(target):
            self.output_dock.show()
            self.statusBar().showMessage("构建失败；旧预览未被替换", 5000)

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
        try:
            self.preview_owner.seek(int(frame))
            self.statusBar().showMessage(f"预览快进到第 {frame} 帧", 2500)
        except RuntimeError as exc:
            self.statusBar().showMessage(f"无法跳转：{exc}", 4000)

    def _seek_preview(self) -> None:
        frame, accepted = QInputDialog.getInt(
            self,
            "跳转到帧",
            "目标帧：",
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
            "stale": "运行中 · 预览已过期",
            "stopping": "正在停止…",
            "error": "预览错误",
        }
        self.preview_status.setText(labels.get(state, state))
        target = self.session.preview_target
        target_labels = {
            "project": "整个工程",
            "stage": "Stage",
            "wave": "Wave 练习场",
            "enemy": "Enemy 练习场",
            "spell": "Spell 练习场",
        }
        if target is None:
            self.preview_target_label.setText("运行目标：尚未运行")
        else:
            kind, unit_id = target
            suffix = f" · {unit_id}" if unit_id else ""
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
        active = state not in {"stopped", "error"}
        self.pause_preview_action.setEnabled(active and state != "paused")
        self.resume_preview_action.setEnabled(active)
        self.restart_preview_action.setEnabled(active)
        self.seek_preview_action.setEnabled(active)
        self.stop_preview_action.setEnabled(active)
        if state == "error":
            self.output_dock.show()

    def _build_state_changed(self, state: str) -> None:
        labels = {
            "idle": "构建：空闲",
            "building": "构建：正在保存并验证…",
            "ready": "构建：成功",
            "error": "构建：失败（上次成功版本保持不变）",
        }
        self.build_status_label.setText(labels.get(state, f"构建：{state}"))
        if state == "building":
            self.statusBar().showMessage("正在保存并验证生成包…")
        elif state == "ready":
            self.statusBar().showMessage("构建成功，正在启动真实预览", 3000)
        elif state == "error":
            self.output_dock.show()

    def _show_generated_entry(self, generated_root: str) -> None:
        path = Path(generated_root) / "entry.py"
        try:
            self.generated_code_view.setPlainText(path.read_text(encoding="utf-8"))
        except OSError as exc:
            self.generated_code_view.setPlainText(f"无法读取生成入口：{exc}")

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
) -> Node:
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
            raise ProgramError("missing_phase", "请先新建 Spell 或 NonSpell")
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


def _placeholder(text: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    label = QLabel(text, widget)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    layout.addWidget(label)
    return widget


__all__ = ["ClosableGroup", "EditorWindow"]

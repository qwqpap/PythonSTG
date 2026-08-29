"""Fixed code-driven editor layout wired directly to one EditorSession."""

from __future__ import annotations

from pathlib import Path

from src.authoring import dsl
from src.authoring.program import (
    DropCheck,
    DropPlacement,
    Node,
    Ref,
    ProgramError,
    find_node,
    move_node,
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
    QSplitter,
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
    ProgramTree,
    available_resource_actions,
    node_for_resource_action,
)
from .preview import PreviewHost, PreviewOwner, PreviewTarget
from .session import EditorSession
from .sidebars import ActivitySidebar, ResourceListWidget
from .timeline import TimelinePanel


_ROLE_VALUE = int(Qt.ItemDataRole.UserRole)


class _UnitDialog(QDialog):
    """Small creation/duplication form; paths remain derived from immutable IDs."""

    def __init__(self, program, parent=None, *, source=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("复制逻辑单元" if source else "新建逻辑单元")
        form = QFormLayout(self)
        self.kind = QComboBox(self)
        kinds = ("Stage", "Wave", "Enemy", "Boss", "Spell", "NonSpell", "Task", "Function")
        self.kind.addItems([source.kind] if source else kinds)
        self.unit_id = QLineEdit(self)
        self.name = QLineEdit(self)
        if source:
            self.unit_id.setText(f"{source.id}_copy")
            self.name.setText(f"{source.name} 副本")
        self.register_stage = QCheckBox("加入 Project 关卡顺序", self)
        self.register_stage.setChecked(False if source else True)
        self.phase = QComboBox(self)
        self.phase.addItems(
            sorted(unit.id for unit in program.logical_units() if unit.kind in {"Spell", "NonSpell"})
        )
        form.addRow("类型", self.kind)
        form.addRow("ID", self.unit_id)
        form.addRow("显示名", self.name)
        form.addRow("Boss 首个阶段", self.phase)
        form.addRow("Stage", self.register_stage)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.kind.currentTextChanged.connect(self._sync)
        self._sync(self.kind.currentText())

    def _sync(self, kind: str) -> None:
        self.phase.setEnabled(kind == "Boss")
        self.register_stage.setEnabled(kind == "Stage")

    def values(self) -> tuple[str, str, str, bool, str | None]:
        return (
            self.kind.currentText(),
            self.unit_id.text().strip(),
            self.name.text().strip(),
            self.register_stage.isChecked(),
            self.phase.currentText() or None,
        )


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
        self._insertion_mode = DropPlacement.AFTER
        self.setWindowTitle("PySTG 关卡编辑器")
        self.resize(1280, 800)
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
        self.unit_list = QTreeWidget(self)
        self.unit_list.setObjectName("program_structure")
        self.unit_list.setHeaderLabels(["程序结构"])
        self.unit_list.itemSelectionChanged.connect(self._unit_selected)
        unit_panel = QWidget(self)
        unit_panel_layout = QVBoxLayout(unit_panel)
        unit_panel_layout.setContentsMargins(0, 0, 0, 0)
        unit_toolbar = QWidget(unit_panel)
        unit_toolbar_layout = QHBoxLayout(unit_toolbar)
        unit_toolbar_layout.setContentsMargins(2, 2, 2, 2)
        self.new_unit_button = QPushButton("新建", unit_toolbar)
        self.duplicate_unit_button = QPushButton("复制", unit_toolbar)
        self.delete_unit_button = QPushButton("删除", unit_toolbar)
        self.new_unit_button.clicked.connect(self._create_unit)
        self.duplicate_unit_button.clicked.connect(self._duplicate_unit)
        self.delete_unit_button.clicked.connect(self._delete_unit)
        unit_toolbar_layout.addWidget(self.new_unit_button)
        unit_toolbar_layout.addWidget(self.duplicate_unit_button)
        unit_toolbar_layout.addWidget(self.delete_unit_button)
        unit_panel_layout.addWidget(unit_toolbar)
        unit_panel_layout.addWidget(self.unit_list, 1)
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
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left_dock)

        self.program_tree = ProgramTree(self)
        self.program_tree.set_drop_validator(self._validate_program_drop)
        self.program_tree.node_selected.connect(self._node_selected)
        self.program_tree.move_requested.connect(self._move_node)
        self.program_tree.prototype_requested.connect(self._drop_prototype)
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
        program_toolbar_layout = QHBoxLayout(program_toolbar)
        program_toolbar_layout.setContentsMargins(4, 2, 4, 2)
        self.insert_mode_buttons = {}
        for placement, label in (
            (DropPlacement.BEFORE, "之前"), (DropPlacement.AFTER, "之后"),
            (DropPlacement.CHILD, "子项"), (DropPlacement.WRAP, "包裹"),
        ):
            button = QPushButton(label, program_toolbar)
            button.setCheckable(True)
            button.setChecked(placement == self._insertion_mode)
            button.clicked.connect(
                lambda _checked=False, value=placement: self._set_insertion_mode(value)
            )
            self.insert_mode_buttons[placement] = button
            program_toolbar_layout.addWidget(button)
        self.add_node_button = QPushButton("添加", program_toolbar)
        self.add_node_button.setObjectName("add_selected_node")
        self.add_node_button.clicked.connect(self._insert_selected_prototype)
        program_toolbar_layout.addWidget(self.add_node_button)
        self.delete_node_button = QPushButton("删除", program_toolbar)
        self.delete_node_button.setObjectName("delete_node")
        self.delete_node_button.clicked.connect(self._delete_selected_node)
        program_toolbar_layout.addWidget(self.delete_node_button)
        program_toolbar_layout.addStretch(1)
        program_layout.addWidget(program_toolbar)
        program_layout.addWidget(self.program_tree, 1)
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
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(4, 2, 4, 2)
        self.preview_status = QLabel("已停止", controls)
        self.preview_status.setObjectName("preview_status")
        controls_layout.addWidget(self.preview_status)
        controls_layout.addStretch(1)
        for label, slot, object_name in (
            ("运行", self._run_current, "preview_run_button"),
            ("暂停", self._pause_preview, "preview_pause_button"),
            ("继续", self._resume_preview, "preview_resume_button"),
            ("停止", self._stop_preview, "preview_stop_button"),
        ):
            button = QPushButton(label, controls)
            button.setObjectName(object_name)
            button.clicked.connect(slot)
            controls_layout.addWidget(button)
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
        self.inspector_dock.setMinimumWidth(120)
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

    def _connect_session(self) -> None:
        self.session.project_changed.connect(self.refresh_project)
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

    def refresh_project(self) -> None:
        self.unit_list.blockSignals(True)
        self.file_list.blockSignals(True)
        self.unit_list.clear()
        self.file_list.clear()
        if self.session.source_project is not None:
            for unit in sorted(
                self.session.program.logical_units(), key=lambda item: (item.kind, item.id)
            ):
                item = QTreeWidgetItem([f"{unit.kind} · {unit.name}"])
                item.setData(0, _ROLE_VALUE, unit.id)
                self.unit_list.addTopLevelItem(item)
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

    def refresh_selection(self) -> None:
        self.program_tree.set_unit(self.session.current_unit, self.session.current_node_uid)
        self._select_unit(self.session.current_unit_id)
        if self.session.source_project is not None:
            self.stage_asset_list.set_resources(
                self.session.stage_assets,
                project_root=self.session.project_context.root,
            )
        self.inspector.refresh()
        unit = self.session.current_unit
        node = self.session.current_node
        editable = bool(unit and unit.kind != "Project" and self.session.can_edit)
        self.add_node_button.setEnabled(editable)
        self.delete_node_button.setEnabled(editable and node is not None)
        self.new_unit_button.setEnabled(self.session.is_open)
        self.duplicate_unit_button.setEnabled(editable)
        self.delete_unit_button.setEnabled(editable)
        self.node_palette.set_context(
            self.session.program if self.session.is_open else None,
            unit.id if unit is not None else None,
            node.uid if node is not None else None,
            self._insertion_mode,
            self.session.palette_templates,
        )
        self.refresh_source()

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
            self.session.select_unit(items[0].data(0, _ROLE_VALUE))

    def _create_unit(self) -> None:
        if not self.session.is_open:
            return
        dialog = _UnitDialog(self.session.program, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        kind, unit_id, name, register_stage, phase_id = dialog.values()
        try:
            if not unit_id or not name:
                raise ProgramError("invalid_unit", "ID 和显示名不能为空")
            if kind == "Boss" and phase_id is None:
                raise ProgramError("missing_phase", "请先新建 Spell 或 NonSpell")
            unit = _new_logical_unit(kind, unit_id, name, phase_id)
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
        _kind, unit_id, name, register_stage, _phase_id = dialog.values()
        try:
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
        except Exception as exc:
            QMessageBox.warning(self, "无法删除", str(exc))

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
        except Exception as exc:
            self.statusBar().showMessage(f"节点未移动：{exc}", 5000)

    def _set_insertion_mode(self, placement: DropPlacement) -> None:
        self._insertion_mode = placement
        for value, button in self.insert_mode_buttons.items():
            button.setChecked(value == placement)
        self.refresh_selection()

    def _insert_selected_prototype(self, *_args) -> None:
        kind = self.node_palette.current_kind()
        if kind is None:
            self.statusBar().showMessage("请先在左侧节点库选择节点", 4000)
            return
        self.insert_palette_node(kind, self._insertion_mode)

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
            if unit is None or unit.kind == "Project":
                raise ProgramError("no_unit", "请先选择可编辑逻辑单元")
            entry = self.node_palette.entry(kind)
            candidates = self.node_palette.reference_candidates(kind)
            reference_id = None
            if entry.reference_kinds:
                if not candidates:
                    raise ProgramError(
                        "missing_reference", f"请先新建 {'/'.join(entry.reference_kinds)}"
                    )
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
            return node
        except Exception as exc:
            self.statusBar().showMessage(f"节点未添加：{exc}", 6000)
            return None

    def _validate_program_drop(self, mime, target_uid, placement, target_slot) -> DropCheck:
        unit = self.session.current_unit
        if unit is None or unit.kind == "Project" or not self.session.can_edit:
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
            if mime.hasFormat(NODE_MIME):
                source_uid = bytes(mime.data(NODE_MIME)).decode("utf-8")
                if target_uid is None:
                    return DropCheck(False, "已有节点不能放到逻辑单元标题")
                move_node(
                    self.session.program, source_uid, target_uid, placement,
                    target_slot=target_slot,
                )
                return DropCheck(True)
            if placement == DropPlacement.WRAP or target_uid is None:
                return DropCheck(False, "资源不能包裹节点")
            return DropCheck(True)
        except Exception as exc:
            return DropCheck(False, str(exc))

    def _delete_selected_node(self) -> None:
        uid = self.session.current_node_uid
        if uid is None:
            self.statusBar().showMessage("请先选择要删除的节点", 4000)
            return
        try:
            self.session.delete_node(uid)
        except Exception as exc:
            self.statusBar().showMessage(f"节点未删除：{exc}", 6000)

    def _resource_drop(self, uri: str, target_uid: str, placement: str) -> None:
        actions = available_resource_actions(uri)
        if not actions:
            self.statusBar().showMessage("该资源只能拖到兼容的检查器字段", 5000)
            return
        selected_action = self._choose_resource_action(actions)
        if selected_action is None:
            return
        try:
            self.insert_resource_action(
                selected_action, uri, target_uid, DropPlacement(placement)
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
    ) -> Node:
        node = node_for_resource_action(action, uri)
        self.session.insert_node_relative(target_uid, placement, node)
        return node

    def _select_unit(self, unit_id: str | None) -> None:
        if unit_id is None:
            return
        for index in range(self.unit_list.topLevelItemCount()):
            item = self.unit_list.topLevelItem(index)
            if item.data(0, _ROLE_VALUE) == unit_id:
                self.unit_list.blockSignals(True)
                self.unit_list.setCurrentItem(item)
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
            "stale": "运行中 · 预览已过期",
            "stopping": "正在停止…",
            "error": "预览错误",
        }
        self.preview_status.setText(labels.get(state, state))
        active = state not in {"stopped", "error"}
        self.pause_preview_action.setEnabled(active and state != "paused")
        self.resume_preview_action.setEnabled(active)
        self.restart_preview_action.setEnabled(active)
        self.seek_preview_action.setEnabled(active)
        self.stop_preview_action.setEnabled(active)
        if state == "error":
            self.output_dock.show()

    def _build_state_changed(self, state: str) -> None:
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


def _placeholder(text: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    label = QLabel(text, widget)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    layout.addWidget(label)
    return widget


__all__ = ["ClosableGroup", "EditorWindow"]

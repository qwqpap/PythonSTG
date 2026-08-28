"""Simplified-Chinese Qt shell wired directly to :class:`EditorSession`."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from src.authoring.program import Expr, Node, Ref
from src.authoring.python_source import SourceConflictError, SourceSaveError
from src.qt_compat.QtCore import Qt
from src.qt_compat.QtGui import QAction
from src.qt_compat.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .session import EditorSession


_ROLE_VALUE = int(Qt.ItemDataRole.UserRole)


class InspectorPanel(QWidget):
    """Minimal literal argument editor; richer typed widgets belong to CD5."""

    def __init__(self, session: EditorSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inspector_panel")
        self.session = session
        self.layout = QFormLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.session.selection_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        while self.layout.rowCount():
            self.layout.removeRow(0)
        node = self.session.current_node
        unit = self.session.current_unit
        if node is not None:
            self.layout.addRow("节点类型", QLabel(node.kind))
            self.layout.addRow("UID", QLabel(node.uid))
            for name, value in node.arguments.items():
                field = QLineEdit(_display_value(value), self)
                field.setObjectName(f"argument_{name}")
                editable = _is_literal_value(value) and self.session.can_edit
                field.setReadOnly(not editable)
                if editable:
                    field.editingFinished.connect(
                        lambda uid=node.uid, key=name, editor=field: self._commit(uid, key, editor)
                    )
                self.layout.addRow(name, field)
            return
        if unit is not None:
            self.layout.addRow("逻辑单元", QLabel(unit.kind))
            name_field = QLineEdit(unit.name, self)
            name_field.setObjectName("unit_name")
            name_field.setReadOnly(not self.session.can_edit)
            if self.session.can_edit:
                name_field.editingFinished.connect(
                    lambda unit_id=unit.id, editor=name_field: self._commit_unit_name(
                        unit_id, editor
                    )
                )
            self.layout.addRow("名称", name_field)
            return
        self.layout.addRow(QLabel("当前文件不可视化编辑"))

    def _commit(self, uid: str, name: str, field: QLineEdit) -> None:
        try:
            value = ast.literal_eval(field.text())
            self.session.set_node_argument(uid, name, value)
        except Exception as exc:
            self.window().statusBar().showMessage(f"参数未修改：{exc}", 5000)
            self.refresh()

    def _commit_unit_name(self, unit_id: str, field: QLineEdit) -> None:
        try:
            self.session.set_unit_field(unit_id, "name", field.text())
        except Exception as exc:
            self.window().statusBar().showMessage(f"名称未修改：{exc}", 5000)
            self.refresh()


class EditorWindow(QMainWindow):
    """One window, one session, and no secondary document owner."""

    def __init__(
        self,
        session: EditorSession | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("code_editor_window")
        self.session = session or EditorSession(self)
        self.setWindowTitle("PySTG 关卡编辑器")
        self.resize(1280, 800)
        self._build_actions()
        self._build_layout()
        self._connect_session()
        self.refresh_project()

    def open_project(self, root: str | Path) -> None:
        self.session.open_project(root)

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        open_action = QAction("打开工程…", self)
        open_action.setObjectName("open_project_action")
        open_action.triggered.connect(self._choose_project)
        file_menu.addAction(open_action)
        save_action = QAction("全部保存", self)
        save_action.setObjectName("save_all_action")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_all)
        file_menu.addAction(save_action)
        self.save_action = save_action

        edit_menu = self.menuBar().addMenu("编辑")
        self.undo_action = self.session.undo_stack.createUndoAction(self, "撤销")
        self.undo_action.setObjectName("undo_action")
        self.undo_action.setShortcut("Ctrl+Z")
        edit_menu.addAction(self.undo_action)
        self.redo_action = self.session.undo_stack.createRedoAction(self, "重做")
        self.redo_action.setObjectName("redo_action")
        self.redo_action.setShortcut("Ctrl+Shift+Z")
        edit_menu.addAction(self.redo_action)

    def _build_layout(self) -> None:
        self.unit_list = QTreeWidget(self)
        self.unit_list.setObjectName("program_structure")
        self.unit_list.setHeaderLabels(["程序结构"])
        self.unit_list.itemSelectionChanged.connect(self._unit_selected)

        self.file_list = QListWidget(self)
        self.file_list.setObjectName("file_sidebar")
        self.file_list.itemSelectionChanged.connect(self._file_selected)

        sidebars = QTabWidget(self)
        sidebars.setObjectName("activity_sidebars")
        sidebars.addTab(self.unit_list, "程序")
        sidebars.addTab(self.file_list, "文件")
        sidebars.addTab(_placeholder("全局资产将在 CD5 接入"), "全局资产")
        sidebars.addTab(_placeholder("当前关卡资产将在 CD5 接入"), "关卡资产")
        left_dock = QDockWidget("工程", self)
        left_dock.setObjectName("left_activity_dock")
        left_dock.setWidget(sidebars)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left_dock)

        self.program_tree = QTreeWidget(self)
        self.program_tree.setObjectName("program_tree")
        self.program_tree.setHeaderLabels(["当前逻辑单元"])
        self.program_tree.itemSelectionChanged.connect(self._node_selected)

        self.code_view = QPlainTextEdit(self)
        self.code_view.setObjectName("source_code_view")
        self.code_view.setReadOnly(True)
        self.code_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        editor_group = QTabWidget(self)
        editor_group.setObjectName("editor_group")
        editor_group.addTab(self.program_tree, "可视化程序")
        editor_group.addTab(self.code_view, "作者 Python（只读）")

        self.game_placeholder = _placeholder("游戏画面将在 CD6 接入真实运行窗口")
        self.game_placeholder.setObjectName("game_view_placeholder")
        game_group = QTabWidget(self)
        game_group.setObjectName("game_group")
        game_group.addTab(self.game_placeholder, "游戏画面")

        center = QSplitter(Qt.Orientation.Horizontal, self)
        center.setObjectName("central_groups")
        center.addWidget(editor_group)
        center.addWidget(game_group)
        center.setStretchFactor(0, 3)
        center.setStretchFactor(1, 2)
        self.setCentralWidget(center)

        self.inspector = InspectorPanel(self.session, self)
        inspector_dock = QDockWidget("检查器", self)
        inspector_dock.setObjectName("inspector_dock")
        inspector_dock.setWidget(self.inspector)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, inspector_dock)

        self.timeline_placeholder = _placeholder("时间线将在 CD7 显示代码投影与运行 Trace")
        self.timeline_placeholder.setObjectName("timeline_placeholder")
        timeline_dock = QDockWidget("时间线", self)
        timeline_dock.setObjectName("timeline_dock")
        timeline_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        timeline_dock.setWidget(self.timeline_placeholder)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, timeline_dock)

        self.problems_view = QPlainTextEdit(self)
        self.problems_view.setObjectName("problems_log")
        self.problems_view.setReadOnly(True)
        output_dock = QDockWidget("问题 / 日志", self)
        output_dock.setObjectName("output_dock")
        output_dock.setWidget(self.problems_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, output_dock)
        self.tabifyDockWidget(timeline_dock, output_dock)
        timeline_dock.raise_()

    def _connect_session(self) -> None:
        self.session.project_changed.connect(self.refresh_project)
        self.session.selection_changed.connect(self.refresh_selection)
        self.session.source_changed.connect(self.refresh_source)
        self.session.problems_changed.connect(self.refresh_problems)
        self.session.dirty_changed.connect(self._dirty_changed)
        self.session.external_conflict.connect(self._ask_external_decision)

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
        self.unit_list.blockSignals(False)
        self.file_list.blockSignals(False)
        self.refresh_selection()
        self.refresh_problems()

    def refresh_selection(self) -> None:
        self.program_tree.blockSignals(True)
        self.program_tree.clear()
        unit = self.session.current_unit
        if unit is not None:
            root = QTreeWidgetItem([f"{unit.kind} · {unit.name}"])
            root.setData(0, _ROLE_VALUE, None)
            self.program_tree.addTopLevelItem(root)
            for node in unit.body:
                root.addChild(self._node_item(node))
            root.setExpanded(True)
            self._select_tree_value(self.unit_list, self.session.current_unit_id)
            self._select_tree_value(self.program_tree, self.session.current_node_uid)
        self.program_tree.blockSignals(False)
        self.inspector.refresh()
        self.refresh_source()

    def refresh_source(self) -> None:
        self.code_view.setPlainText(self.session.source_text)

    def refresh_problems(self) -> None:
        lines = []
        for diagnostic in self.session.diagnostics:
            location = diagnostic.source_path or "工程"
            if diagnostic.span is not None:
                location += f":{diagnostic.span.start_line}"
            lines.append(f"[{diagnostic.severity}] {diagnostic.code} · {location} · {diagnostic.message}")
        self.problems_view.setPlainText("\n".join(lines) if lines else "没有问题")

    def _node_item(self, node: Node) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.kind])
        item.setData(0, _ROLE_VALUE, node.uid)
        for slot, children in node.children.items():
            if not children:
                continue
            slot_item = QTreeWidgetItem([slot])
            for child in children:
                slot_item.addChild(self._node_item(child))
            item.addChild(slot_item)
        return item

    def _unit_selected(self) -> None:
        items = self.unit_list.selectedItems()
        if items:
            self.session.select_unit(items[0].data(0, _ROLE_VALUE))

    def _file_selected(self) -> None:
        items = self.file_list.selectedItems()
        if items:
            self.session.select_source(items[0].data(_ROLE_VALUE))

    def _node_selected(self) -> None:
        items = self.program_tree.selectedItems()
        if not items:
            return
        uid = items[0].data(0, _ROLE_VALUE)
        if uid is not None:
            self.session.select_node(uid)

    def _select_tree_value(self, tree: QTreeWidget, value: str | None) -> None:
        if value is None:
            return
        iterator = tree.invisibleRootItem()
        stack = [iterator.child(index) for index in range(iterator.childCount())]
        while stack:
            item = stack.pop()
            if item.data(0, _ROLE_VALUE) == value:
                tree.setCurrentItem(item)
                return
            stack.extend(item.child(index) for index in range(item.childCount()))

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


def _display_value(value: Any) -> str:
    return repr(value)


def _is_literal_value(value: Any) -> bool:
    if isinstance(value, (Expr, Ref)):
        return False
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_literal_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_literal_value(item) for key, item in value.items())
    return False


__all__ = ["EditorWindow", "InspectorPanel"]

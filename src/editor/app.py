"""Godot-inspired PyQt scene editor shell for PySTG."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QPointF, QProcess, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.project_context import ProjectContext

from .document import DocumentError, EditorNode, SceneDocument
from .node_types import NODE_TYPES, PropertySpec, make_node, property_specs
from .scene_commands import (
    AddNodeCommand,
    MoveNodeCommand,
    RemoveNodeCommand,
    RenameNodeCommand,
    SceneMutationError,
    SetNodePropertiesCommand,
    SetNodePropertyCommand,
    find_parent,
)
from .session import SceneEditorSession
from .storage import DocumentStore


APP_NAME = "PySTG Scene Editor"
SCENE_FILTER = "PySTG Scene (*.pystg.json);;JSON (*.json)"


def build_preview_command(
    project: ProjectContext,
    document: SceneDocument,
    node: EditorNode | None,
) -> tuple[list[str], str]:
    if node is not None and node.type == "SpellCard":
        script_value = str(node.properties.get("script", "")).strip()
        if not script_value:
            raise ValueError("Selected SpellCard needs a script path.")
        script_path = project.resolve(script_value)
        project.relative(script_path)
        if not script_path.is_file():
            raise ValueError(f"SpellCard script does not exist: {script_path}")
        arguments = [
            str(project.root / "tools" / "preview_spell.py"),
            str(script_path),
        ]
        class_name = str(node.properties.get("class_name", "")).strip()
        if class_name:
            arguments.extend(["--spell", class_name])
        return arguments, f"spell preview: {script_path.name}"

    stage = str(document.metadata.get("preview_stage", "stage1"))
    return (
        [
            str(project.root / "main.py"),
            f"--stage={stage}",
            f"--project={project.root}",
            "--hot-reload",
        ],
        f"runtime preview: {stage}",
    )


class SceneTreeWidget(QTreeWidget):
    nodeMoveRequested = pyqtSignal(str, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderLabels(["Scene", "Type"])
        self.header().setStretchLastSection(True)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.setColumnHidden(1, True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def dropEvent(self, event) -> None:
        item = self.currentItem()
        if item is None or item.parent() is None:
            event.ignore()
            return
        node_id = str(item.data(0, Qt.UserRole))
        super().dropEvent(event)

        moved = self._find_item(node_id)
        root_item = self.topLevelItem(0)
        if moved is None or root_item is None:
            return
        parent = moved.parent()
        if parent is None:
            index = self.indexOfTopLevelItem(moved)
            self.takeTopLevelItem(index)
            root_item.addChild(moved)
            parent = root_item
        target_index = parent.indexOfChild(moved)
        target_parent_id = str(parent.data(0, Qt.UserRole))
        self.nodeMoveRequested.emit(node_id, target_parent_id, target_index)

    def _find_item(self, node_id: str) -> QTreeWidgetItem | None:
        pending = [
            self.topLevelItem(index)
            for index in range(self.topLevelItemCount())
        ]
        while pending:
            item = pending.pop()
            if item is None:
                continue
            if str(item.data(0, Qt.UserRole)) == node_id:
                return item
            pending.extend(item.child(index) for index in range(item.childCount()))
        return None


class NodeGraphicsItem(QGraphicsObject):
    positionCommitted = pyqtSignal(str, float, float)

    def __init__(
        self,
        node: EditorNode,
        project: ProjectContext,
        grid_size: int,
    ):
        super().__init__()
        self.node_id = node.id
        self.node_type = node.type
        self.node_name = node.name
        self.grid_size = max(1, grid_size)
        self._drag_start = QPointF()
        self._pixmap = self._load_pixmap(node, project)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.OpenHandCursor)
        self.setZValue(10)

    @staticmethod
    def _load_pixmap(node: EditorNode, project: ProjectContext) -> QPixmap:
        if node.type != "Sprite":
            return QPixmap()
        texture = str(node.properties.get("texture", "")).strip()
        if not texture:
            return QPixmap()
        candidate = project.resolve(texture)
        try:
            project.relative(candidate)
        except Exception:
            return QPixmap()
        if not candidate.is_file():
            return QPixmap()
        pixmap = QPixmap(str(candidate))
        if pixmap.isNull():
            return QPixmap()
        return pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def boundingRect(self) -> QRectF:
        return QRectF(-38.0, -38.0, 76.0, 96.0)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        if self.node_type == "EnemySpawner":
            path.addEllipse(QRectF(-24, -24, 48, 48))
        elif self.node_type == "SpellCard":
            polygon = [
                QPointF(0, -28),
                QPointF(28, 0),
                QPointF(0, 28),
                QPointF(-28, 0),
            ]
            path.moveTo(polygon[0])
            for point in polygon[1:]:
                path.lineTo(point)
            path.closeSubpath()
        else:
            path.addRoundedRect(QRectF(-28, -28, 56, 56), 5, 5)
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        spec = NODE_TYPES.get(self.node_type)
        color = QColor(spec.color if spec else "#9aa4b2")
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#f5f7ff") if self.isSelected() else color, 3 if self.isSelected() else 2))
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 72)))

        if self.node_type == "EnemySpawner":
            painter.drawEllipse(QRectF(-24, -24, 48, 48))
            painter.drawLine(-30, 0, 30, 0)
            painter.drawLine(0, -30, 0, 30)
        elif self.node_type == "SpellCard":
            path = self.shape()
            painter.drawPath(path)
            painter.drawText(QRectF(-25, -10, 50, 20), Qt.AlignCenter, "SC")
        else:
            painter.drawRoundedRect(QRectF(-28, -28, 56, 56), 5, 5)
            if not self._pixmap.isNull():
                target = QRectF(
                    -self._pixmap.width() / 2,
                    -self._pixmap.height() / 2,
                    self._pixmap.width(),
                    self._pixmap.height(),
                )
                painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
            else:
                painter.drawText(QRectF(-24, -10, 48, 20), Qt.AlignCenter, "SPR")

        painter.setPen(QColor("#e8ecf5"))
        painter.drawText(QRectF(-70, 34, 140, 22), Qt.AlignHCenter | Qt.AlignTop, self.node_name)

    def mousePressEvent(self, event) -> None:
        self._drag_start = self.pos()
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.OpenHandCursor)
        snapped = QPointF(
            round(self.x() / self.grid_size) * self.grid_size,
            round(self.y() / self.grid_size) * self.grid_size,
        )
        self.setPos(snapped)
        if snapped != self._drag_start:
            self.positionCommitted.emit(self.node_id, snapped.x(), snapped.y())


class SceneViewport(QGraphicsView):
    nodeSelected = pyqtSignal(str)
    nodePositionRequested = pyqtSignal(str, float, float)

    def __init__(self, project: ProjectContext, parent=None):
        self.graphics_scene = QGraphicsScene(parent)
        super().__init__(self.graphics_scene, parent)
        self.project = project
        self._document: SceneDocument | None = None
        self._items: dict[str, NodeGraphicsItem] = {}
        self._grid_size = 16
        self._background = QColor("#171a24")
        self._fit_on_next_resize = True
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFrameShape(QFrame.NoFrame)
        self.graphics_scene.selectionChanged.connect(self._selection_changed)

    def rebuild(self, document: SceneDocument) -> None:
        self._document = document
        self.graphics_scene.clear()
        self._items.clear()

        root = document.root
        width = max(64, int(root.properties.get("width", 768)))
        height = max(64, int(root.properties.get("height", 896)))
        self._grid_size = max(1, int(root.properties.get("grid_size", 16)))
        self._background = QColor(str(root.properties.get("background", "#171a24")))
        if not self._background.isValid():
            self._background = QColor("#171a24")
        self.graphics_scene.setSceneRect(0, 0, width, height)

        for node in root.walk():
            spec = NODE_TYPES.get(node.type)
            if spec is None or not spec.viewport_item:
                continue
            item = NodeGraphicsItem(node, self.project, self._grid_size)
            item.setPos(
                float(node.properties.get("x", width / 2)),
                float(node.properties.get("y", height / 2)),
            )
            item.positionCommitted.connect(self.nodePositionRequested)
            self.graphics_scene.addItem(item)
            self._items[node.id] = item

        self.viewport().update()
        if self._fit_on_next_resize:
            self.fit_canvas()

    def fit_canvas(self) -> None:
        rect = self.graphics_scene.sceneRect()
        if not rect.isEmpty():
            self.fitInView(rect.adjusted(-24, -24, 24, 24), Qt.KeepAspectRatio)

    def select_node(self, node_id: str) -> None:
        for item_id, item in self._items.items():
            item.setSelected(item_id == node_id)

    def _selection_changed(self) -> None:
        selected = self.graphics_scene.selectedItems()
        if selected and isinstance(selected[0], NodeGraphicsItem):
            self.nodeSelected.emit(selected[0].node_id)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self._background)
        scene_rect = self.graphics_scene.sceneRect()
        painter.setPen(QPen(QColor("#303644"), 0))
        left = max(scene_rect.left(), int(rect.left()) - (int(rect.left()) % self._grid_size))
        top = max(scene_rect.top(), int(rect.top()) - (int(rect.top()) % self._grid_size))
        x = left
        while x <= min(rect.right(), scene_rect.right()):
            painter.drawLine(QPointF(x, max(rect.top(), scene_rect.top())), QPointF(x, min(rect.bottom(), scene_rect.bottom())))
            x += self._grid_size
        y = top
        while y <= min(rect.bottom(), scene_rect.bottom()):
            painter.drawLine(QPointF(max(rect.left(), scene_rect.left()), y), QPointF(min(rect.right(), scene_rect.right()), y))
            y += self._grid_size
        painter.setPen(QPen(QColor("#68748c"), 1))
        painter.drawRect(scene_rect)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_on_next_resize:
            self.fit_canvas()
            self._fit_on_next_resize = False


class InspectorPanel(QScrollArea):
    renameRequested = pyqtSignal(str, str)
    propertyRequested = pyqtSignal(str, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._content = QWidget()
        self._form = QFormLayout(self._content)
        self._form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._form.setContentsMargins(12, 12, 12, 12)
        self.setWidget(self._content)
        self._node_id: str | None = None

    def set_node(self, node: EditorNode | None) -> None:
        while self._form.count():
            item = self._form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._node_id = node.id if node else None
        if node is None:
            self._form.addRow(QLabel("No node selected"))
            return

        name_edit = QLineEdit(node.name)
        name_edit.setObjectName("inspectorName")
        name_edit.editingFinished.connect(
            lambda edit=name_edit, node_id=node.id: self.renameRequested.emit(
                node_id,
                edit.text(),
            )
        )
        self._form.addRow("Name", name_edit)

        type_edit = QLineEdit(node.type)
        type_edit.setReadOnly(True)
        self._form.addRow("Type", type_edit)

        for spec in property_specs(node.type):
            value = node.properties.get(spec.key, spec.default)
            editor = self._make_editor(node.id, spec, value)
            self._form.addRow(spec.label, editor)

        known = {spec.key for spec in property_specs(node.type)}
        extras = {
            key: value
            for key, value in node.properties.items()
            if key not in known
        }
        if extras:
            extra_label = QLabel(json.dumps(extras, ensure_ascii=False, indent=2))
            extra_label.setWordWrap(True)
            extra_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._form.addRow("Other", extra_label)

    def _make_editor(self, node_id: str, spec: PropertySpec, value):
        if spec.value_type is bool:
            editor = QCheckBox()
            editor.setChecked(bool(value))
            editor.toggled.connect(
                lambda checked, nid=node_id, key=spec.key: self.propertyRequested.emit(
                    nid,
                    key,
                    checked,
                )
            )
            return editor
        if spec.value_type is int:
            editor = QSpinBox()
            editor.setRange(int(spec.minimum or -2_147_483_648), int(spec.maximum or 2_147_483_647))
            editor.setSingleStep(max(1, int(spec.step or 1)))
            editor.setValue(int(value))
            editor.editingFinished.connect(
                lambda spin=editor, nid=node_id, key=spec.key: self.propertyRequested.emit(
                    nid,
                    key,
                    spin.value(),
                )
            )
            return editor
        if spec.value_type is float:
            editor = QDoubleSpinBox()
            editor.setDecimals(3)
            editor.setRange(
                float(spec.minimum if spec.minimum is not None else -1_000_000_000),
                float(spec.maximum if spec.maximum is not None else 1_000_000_000),
            )
            editor.setSingleStep(float(spec.step or 0.1))
            editor.setValue(float(value))
            editor.editingFinished.connect(
                lambda spin=editor, nid=node_id, key=spec.key: self.propertyRequested.emit(
                    nid,
                    key,
                    spin.value(),
                )
            )
            return editor

        editor = QLineEdit(str(value))
        editor.editingFinished.connect(
            lambda edit=editor, nid=node_id, key=spec.key: self.propertyRequested.emit(
                nid,
                key,
                edit.text(),
            )
        )
        return editor


class TimelinePanel(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, 3, parent)
        self.setHorizontalHeaderLabels(["Frame", "Type", "Properties"])
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

    def set_document(self, document: SceneDocument) -> None:
        self.setRowCount(len(document.timeline))
        for row, event in enumerate(document.timeline):
            self.setItem(row, 0, QTableWidgetItem(str(event.frame)))
            self.setItem(row, 1, QTableWidgetItem(event.type))
            self.setItem(
                row,
                2,
                QTableWidgetItem(json.dumps(event.properties, ensure_ascii=False)),
            )


class EditorMainWindow(QMainWindow):
    def __init__(self, project: ProjectContext):
        super().__init__()
        self.project = project
        self.session = SceneEditorSession(DocumentStore(project))
        self._selected_id = self.session.document.root.id
        self._syncing_selection = False
        self._preview_process: QProcess | None = None
        self._build_actions()
        self._build_ui()
        self._apply_theme()
        self._refresh()
        self.resize(1480, 920)
        self.setMinimumSize(960, 640)

    def _build_actions(self) -> None:
        self.action_new = self._action("New Scene", QKeySequence.New, self.new_scene)
        self.action_open = self._action("Open Scene…", QKeySequence.Open, self.open_scene)
        self.action_save = self._action("Save", QKeySequence.Save, self.save_scene)
        self.action_save_as = self._action("Save As…", QKeySequence.SaveAs, self.save_scene_as)
        self.action_undo = self._action("Undo", QKeySequence.Undo, self.undo)
        self.action_redo = self._action("Redo", QKeySequence.Redo, self.redo)
        self.action_delete = self._action("Delete Node", QKeySequence.Delete, self.delete_selected)
        self.action_rename = self._action("Rename Node", Qt.Key_F2, self.rename_selected)
        self.action_move_up = self._action("Move Up", "Alt+Up", lambda: self.move_selected(-1))
        self.action_move_down = self._action("Move Down", "Alt+Down", lambda: self.move_selected(1))
        self.action_outdent = self._action("Move to Parent", "Alt+Left", self.outdent_selected)
        self.action_indent = self._action("Make Child of Previous", "Alt+Right", self.indent_selected)
        self.action_run = self._action("Run / Preview", Qt.Key_F6, self.run_preview)
        self.action_fit = self._action("Frame Canvas", "F", self._fit_viewport)

    def _action(self, text: str, shortcut, callback: Callable) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        self.addAction(action)
        return action

    def _build_ui(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions([
            self.action_new,
            self.action_open,
            self.action_save,
            self.action_save_as,
        ])
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([
            self.action_undo,
            self.action_redo,
            self.action_rename,
            self.action_delete,
            self.action_move_up,
            self.action_move_down,
            self.action_outdent,
            self.action_indent,
        ])
        run_menu = self.menuBar().addMenu("&Run")
        run_menu.addActions([self.action_run, self.action_fit])

        main_toolbar = QToolBar("Main", self)
        main_toolbar.setObjectName("mainToolbar")
        main_toolbar.setMovable(False)
        main_toolbar.addActions([
            self.action_new,
            self.action_open,
            self.action_save,
        ])
        main_toolbar.addSeparator()
        main_toolbar.addActions([self.action_undo, self.action_redo])
        main_toolbar.addSeparator()
        main_toolbar.addAction(self.action_run)
        self.addToolBar(main_toolbar)

        self.viewport = SceneViewport(self.project)
        self.viewport.nodeSelected.connect(self._select_from_viewport)
        self.viewport.nodePositionRequested.connect(self._set_node_position)
        self.setCentralWidget(self.viewport)

        self.tree = SceneTreeWidget()
        self.tree.currentItemChanged.connect(self._select_from_tree)
        self.tree.itemChanged.connect(self._tree_item_changed)
        self.tree.nodeMoveRequested.connect(self._move_from_tree)

        tree_content = QWidget()
        tree_layout = QVBoxLayout(tree_content)
        tree_layout.setContentsMargins(4, 4, 4, 4)
        tree_buttons = QHBoxLayout()
        add_button = QToolButton()
        add_button.setText("+ Add")
        add_button.setPopupMode(QToolButton.InstantPopup)
        add_menu = QMenu(add_button)
        for type_name, spec in NODE_TYPES.items():
            if type_name == "SceneRoot":
                continue
            action = add_menu.addAction(spec.display_name)
            action.triggered.connect(
                lambda checked=False, node_type=type_name: self.add_node(node_type)
            )
        add_button.setMenu(add_menu)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.delete_selected)
        tree_buttons.addWidget(add_button)
        tree_buttons.addWidget(delete_button)
        tree_buttons.addStretch()
        tree_layout.addLayout(tree_buttons)
        hierarchy_buttons = QHBoxLayout()
        for text, tooltip, action in (
            ("↑", "Move up (Alt+Up)", self.action_move_up),
            ("↓", "Move down (Alt+Down)", self.action_move_down),
            ("←", "Move to parent (Alt+Left)", self.action_outdent),
            ("→", "Make child of previous node (Alt+Right)", self.action_indent),
        ):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tooltip)
            button.clicked.connect(
                lambda checked=False, target=action: target.trigger()
            )
            hierarchy_buttons.addWidget(button)
        hierarchy_buttons.addStretch()
        tree_layout.addLayout(hierarchy_buttons)
        tree_layout.addWidget(self.tree)

        tree_dock = QDockWidget("Scene", self)
        tree_dock.setObjectName("sceneDock")
        tree_dock.setWidget(tree_content)
        tree_dock.setMinimumWidth(270)
        self.addDockWidget(Qt.LeftDockWidgetArea, tree_dock)

        self.inspector = InspectorPanel()
        self.inspector.renameRequested.connect(self.rename_node)
        self.inspector.propertyRequested.connect(self.set_node_property)
        inspector_dock = QDockWidget("Inspector", self)
        inspector_dock.setObjectName("inspectorDock")
        inspector_dock.setWidget(self.inspector)
        inspector_dock.setMinimumWidth(300)
        self.addDockWidget(Qt.RightDockWidgetArea, inspector_dock)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.document().setMaximumBlockCount(1000)
        self.timeline = TimelinePanel()
        bottom_tabs = QTabWidget()
        bottom_tabs.addTab(self.output, "Output")
        bottom_tabs.addTab(self.timeline, "Timeline")
        bottom_dock = QDockWidget("Bottom Panel", self)
        bottom_dock.setObjectName("bottomDock")
        bottom_dock.setWidget(bottom_tabs)
        bottom_dock.setMinimumHeight(180)
        self.addDockWidget(Qt.BottomDockWidgetArea, bottom_dock)

        self.statusBar().showMessage(str(self.project.root))

    def _apply_theme(self) -> None:
        QApplication.instance().setStyle("Fusion")
        self.setStyleSheet(
            """
            QMainWindow, QMenuBar, QMenu, QDockWidget, QWidget {
                background: #20232d;
                color: #d9deea;
            }
            QToolBar, QStatusBar {
                background: #191c24;
                color: #aeb7c8;
                border: 0;
            }
            QDockWidget::title {
                background: #191c24;
                padding: 7px;
                font-weight: 600;
            }
            QTreeWidget, QTextEdit, QTableWidget, QLineEdit,
            QSpinBox, QDoubleSpinBox, QScrollArea {
                background: #171a22;
                color: #dce2ee;
                border: 1px solid #353b49;
                selection-background-color: #315a82;
            }
            QPushButton, QToolButton {
                background: #303644;
                border: 1px solid #454d5e;
                border-radius: 3px;
                padding: 5px 9px;
            }
            QPushButton:hover, QToolButton:hover { background: #3a4252; }
            QHeaderView::section {
                background: #252a35;
                color: #bec7d8;
                border: 0;
                border-right: 1px solid #353b49;
                padding: 5px;
            }
            QTabBar::tab {
                background: #252a35;
                padding: 6px 14px;
            }
            QTabBar::tab:selected { background: #315a82; }
            """
        )

    def _populate_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()

        def add_item(node: EditorNode, parent: QTreeWidgetItem | None = None):
            item = QTreeWidgetItem([node.name, node.type])
            item.setData(0, Qt.UserRole, node.id)
            item.setToolTip(0, node.id)
            flags = item.flags() | Qt.ItemIsDropEnabled | Qt.ItemIsSelectable
            if parent is not None:
                flags |= Qt.ItemIsDragEnabled | Qt.ItemIsEditable
            else:
                flags &= ~Qt.ItemIsDragEnabled
            item.setFlags(flags)
            spec = NODE_TYPES.get(node.type)
            if spec:
                item.setForeground(1, QColor(spec.color))
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in node.children:
                add_item(child, item)
            return item

        add_item(self.session.document.root)
        self.tree.expandAll()
        selected = self.tree._find_item(self._selected_id)
        if selected is not None:
            self.tree.setCurrentItem(selected)
        self.tree.blockSignals(False)

    def _refresh(self) -> None:
        if self.session.node(self._selected_id) is None:
            self._selected_id = self.session.document.root.id
        self._populate_tree()
        self.viewport.rebuild(self.session.document)
        self.viewport.select_node(self._selected_id)
        self.inspector.set_node(self.session.node(self._selected_id))
        self.timeline.set_document(self.session.document)
        self._update_actions()
        self._update_title()

    def _update_actions(self) -> None:
        self.action_undo.setEnabled(self.session.commands.can_undo)
        self.action_redo.setEnabled(self.session.commands.can_redo)
        self.action_undo.setText(
            f"Undo {self.session.commands.undo_label}"
            if self.session.commands.undo_label
            else "Undo"
        )
        self.action_redo.setText(
            f"Redo {self.session.commands.redo_label}"
            if self.session.commands.redo_label
            else "Redo"
        )
        is_root = self._selected_id == self.session.document.root.id
        self.action_delete.setEnabled(not is_root)
        self.action_move_up.setEnabled(not is_root)
        self.action_move_down.setEnabled(not is_root)
        self.action_outdent.setEnabled(not is_root)
        self.action_indent.setEnabled(not is_root)

    def _update_title(self) -> None:
        name = self.session.path.name if self.session.path else self.session.document.name
        marker = "*" if self.session.is_dirty else ""
        self.setWindowModified(self.session.is_dirty)
        self.setWindowTitle(f"{marker}{name} — {APP_NAME}")

    def _log(self, message: str) -> None:
        self.output.append(message)

    def _apply_command(self, command, *, select_id: str | None = None) -> bool:
        try:
            self.session.apply(command)
        except (DocumentError, SceneMutationError, ValueError) as exc:
            self._show_error("Edit failed", exc)
            self._refresh()
            return False
        if select_id is not None:
            self._selected_id = select_id
        self._log(command.label)
        self._refresh()
        return True

    def _select_from_tree(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        if self._syncing_selection or current is None:
            return
        self._selected_id = str(current.data(0, Qt.UserRole))
        self._syncing_selection = True
        self.viewport.select_node(self._selected_id)
        self.inspector.set_node(self.session.node(self._selected_id))
        self._syncing_selection = False
        self._update_actions()

    def _select_from_viewport(self, node_id: str) -> None:
        if self._syncing_selection:
            return
        item = self.tree._find_item(node_id)
        if item is None:
            return
        self._selected_id = node_id
        self._syncing_selection = True
        self.tree.setCurrentItem(item)
        self.inspector.set_node(self.session.node(node_id))
        self._syncing_selection = False
        self._update_actions()

    def _tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        node_id = str(item.data(0, Qt.UserRole))
        self.rename_node(node_id, item.text(0))

    def _move_from_tree(self, node_id: str, parent_id: str, index: int) -> None:
        node = self.session.node(node_id)
        location = find_parent(self.session.document.root, node_id)
        if node is None or location is None:
            self._refresh()
            return
        if location[0].id == parent_id and location[1] == index:
            self._refresh()
            return
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node_id,
                parent_id,
                index,
                label=f"Move {node.name}",
            ),
            select_id=node_id,
        )

    def _set_node_position(self, node_id: str, x: float, y: float) -> None:
        node = self.session.node(node_id)
        if node is None:
            return
        if (
            float(node.properties.get("x", 0.0)) == float(x)
            and float(node.properties.get("y", 0.0)) == float(y)
        ):
            return
        self._apply_command(
            SetNodePropertiesCommand(
                self.session.document.root,
                node_id,
                {"x": float(x), "y": float(y)},
                label=f"Move {node.name}",
            ),
            select_id=node_id,
        )

    def add_node(self, node_type: str) -> None:
        parent = self.session.node(self._selected_id) or self.session.document.root
        node = make_node(node_type)
        self._apply_command(
            AddNodeCommand(
                self.session.document.root,
                parent.id,
                node,
                label=f"Add {node.name}",
            ),
            select_id=node.id,
        )

    def delete_selected(self) -> None:
        if self._selected_id == self.session.document.root.id:
            return
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent_id = location[0].id
        self._apply_command(
            RemoveNodeCommand(
                self.session.document.root,
                node.id,
                label=f"Delete {node.name}",
            ),
            select_id=parent_id,
        )

    def rename_selected(self) -> None:
        item = self.tree.currentItem()
        if item is not None:
            self.tree.editItem(item, 0)

    def rename_node(self, node_id: str, name: str) -> None:
        node = self.session.node(node_id)
        if node is None or node.name == name:
            return
        self._apply_command(
            RenameNodeCommand(
                self.session.document.root,
                node_id,
                name,
                label=f"Rename {node.name}",
            ),
            select_id=node_id,
        )

    def set_node_property(self, node_id: str, key: str, value) -> None:
        node = self.session.node(node_id)
        if node is None or node.properties.get(key) == value:
            return
        self._apply_command(
            SetNodePropertyCommand(
                self.session.document.root,
                node_id,
                key,
                value,
                label=f"Set {key}",
            ),
            select_id=node_id,
        )

    def move_selected(self, delta: int) -> None:
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent, index = location
        target = index + delta
        if target < 0 or target >= len(parent.children):
            return
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node.id,
                parent.id,
                target,
                label=f"Reorder {node.name}",
            ),
            select_id=node.id,
        )

    def indent_selected(self) -> None:
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent, index = location
        if index <= 0:
            return
        new_parent = parent.children[index - 1]
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node.id,
                new_parent.id,
                len(new_parent.children),
                label=f"Indent {node.name}",
            ),
            select_id=node.id,
        )

    def outdent_selected(self) -> None:
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent, _ = location
        if parent.id == self.session.document.root.id:
            return
        parent_location = find_parent(self.session.document.root, parent.id)
        if parent_location is None:
            return
        grandparent, parent_index = parent_location
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node.id,
                grandparent.id,
                parent_index + 1,
                label=f"Outdent {node.name}",
            ),
            select_id=node.id,
        )

    def undo(self) -> None:
        if self.session.undo():
            self._log("Undo")
            self._refresh()

    def redo(self) -> None:
        if self.session.redo():
            self._log("Redo")
            self._refresh()

    def new_scene(self) -> None:
        if not self._confirm_discard():
            return
        self.session.reset()
        self._selected_id = self.session.document.root.id
        self._log("New scene")
        self._refresh()

    def open_scene(self) -> None:
        if not self._confirm_discard():
            return
        start = self.project.game_content / "scenes"
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PySTG Scene",
            str(start),
            SCENE_FILTER,
        )
        if not path:
            return
        try:
            self.session.open(path)
        except (OSError, DocumentError, ValueError) as exc:
            self._show_error("Open failed", exc)
            return
        self._selected_id = self.session.document.root.id
        self._log(f"Opened {self.project.relative(path)}")
        self._refresh()

    def save_scene(self) -> bool:
        if self.session.path is None:
            return self.save_scene_as()
        try:
            path = self.session.save()
        except (OSError, DocumentError, ValueError) as exc:
            self._show_error("Save failed", exc)
            return False
        self._log(f"Saved {self.project.relative(path)}")
        self._refresh()
        return True

    def save_scene_as(self) -> bool:
        start = self.project.game_content / "scenes"
        start.mkdir(parents=True, exist_ok=True)
        suggested = start / (
            self.session.path.name
            if self.session.path
            else "untitled.pystg.json"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PySTG Scene",
            str(suggested),
            SCENE_FILTER,
        )
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".pystg.json"
        try:
            saved = self.session.save(path)
        except (OSError, DocumentError, ValueError) as exc:
            self._show_error("Save failed", exc)
            return False
        self._log(f"Saved {self.project.relative(saved)}")
        self._refresh()
        return True

    def _confirm_discard(self) -> bool:
        if not self.session.is_dirty:
            return True
        result = QMessageBox.warning(
            self,
            "Unsaved changes",
            "Save changes to the current scene?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if result == QMessageBox.Cancel:
            return False
        if result == QMessageBox.Save:
            return self.save_scene()
        return True

    def _fit_viewport(self) -> None:
        self.viewport.fit_canvas()

    def run_preview(self) -> None:
        if self._preview_process is not None and self._preview_process.state() != QProcess.NotRunning:
            self.statusBar().showMessage("Preview is already running", 3000)
            return

        node = self.session.node(self._selected_id)
        try:
            arguments, label = build_preview_command(
                self.project,
                self.session.document,
                node,
            )
        except (OSError, ValueError) as exc:
            self._show_error("Preview unavailable", exc)
            return

        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments(arguments)
        process.setWorkingDirectory(str(self.project.root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_preview_output)
        process.finished.connect(self._preview_finished)
        process.errorOccurred.connect(
            lambda error: self._log(f"[preview:error] process error {int(error)}")
        )
        self._preview_process = process
        process.start()
        if not process.waitForStarted(3000):
            self._show_error("Preview failed", ValueError(process.errorString()))
            self._preview_process = None
            return
        self._log(f"[preview] started {label} (PID {process.processId()})")
        self.statusBar().showMessage(f"Started {label}", 3000)

    def _read_preview_output(self) -> None:
        if self._preview_process is None:
            return
        data = bytes(self._preview_process.readAllStandardOutput())
        text = data.decode("utf-8", errors="replace").rstrip()
        if text:
            self._log(text)

    def _preview_finished(self, exit_code: int, exit_status) -> None:
        self._read_preview_output()
        self._log(f"[preview] exited with code {exit_code}")
        self.statusBar().showMessage(f"Preview exited ({exit_code})", 3000)

    def _show_error(self, title: str, error: Exception) -> None:
        self._log(f"[error] {title}: {error}")
        QMessageBox.critical(self, title, str(error))

    def closeEvent(self, event) -> None:
        if not self._confirm_discard():
            event.ignore()
            return
        if self._preview_process is not None and self._preview_process.state() != QProcess.NotRunning:
            self._preview_process.terminate()
            if not self._preview_process.waitForFinished(1500):
                self._preview_process.kill()
        event.accept()


def create_window(project: ProjectContext) -> EditorMainWindow:
    return EditorMainWindow(project)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--project", type=Path, help="PySTG project root")
    args, qt_args = parser.parse_known_args(argv)
    project = ProjectContext.discover(args.project or Path.cwd())
    project.activate()

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("PySTG")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    window = create_window(project)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())

"""
敌人别名管理器 — Enemy Alias Manager

管理敌人贴图的别名映射（alias → 精灵名）。
支持：
  - 可视化预览敌人精灵
  - 拖拽 / 点选分配别名
  - 从 PNG 自动识别精灵（整图或图集 JSON）
  - 保存到 assets/enemy_aliases.json，引擎运行时加载

使用:
    python tools/enemy/enemy_alias_manager.py
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.qt_compat.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QPushButton, QLineEdit, QScrollArea,
    QGridLayout, QDialog, QDialogButtonBox, QComboBox,
    QMessageBox, QStatusBar, QToolBar, QAction, QGroupBox,
    QFormLayout, QFrame, QInputDialog, QMenu, QSizePolicy,
    QListWidget, QListWidgetItem, QFileDialog, QSpinBox
)
from src.qt_compat.QtCore import Qt, QSize, pyqtSignal, QMimeData
from src.qt_compat.QtGui import (
    QPixmap, QPainter, QColor, QFont, QPen, QBrush, QIcon,
    QDrag, QImage
)

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.editor_common import (
    DARK_THEME, ENEMY_IMAGE_DIR, ENEMY_ALIASES_PATH,
    SpriteEntry, PixmapCache, apply_dark_theme,
    load_all_enemy_sprites, load_enemy_aliases, save_enemy_aliases,
    get_all_sprite_names, get_sprite_entry_map,
)

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


# ═══════════════════════════════════════════════════════════════
# SpriteThumb — 精灵缩略图（用于精灵面板中的每个精灵）
# ═══════════════════════════════════════════════════════════════

class SpriteThumb(QFrame):
    """精灵缩略图格子。点击选中，双击分配给当前别名。"""

    THUMB_SIZE = 64
    selected = pyqtSignal(str)       # sprite_name
    double_clicked = pyqtSignal(str) # sprite_name

    def __init__(self, sprite_name: str, entry: SpriteEntry, parent=None):
        super().__init__(parent)
        self.sprite_name = sprite_name
        self.entry = entry
        self._hover = False
        self._selected = False

        self.setFixedSize(self.THUMB_SIZE + 8, self.THUMB_SIZE + 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{sprite_name}\n{entry.atlas} — {entry.rect}")

    def set_selected(self, sel: bool):
        self._selected = sel
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 背景
        if self._selected:
            bg = QColor(80, 60, 120)
            border = QColor(180, 130, 255)
        elif self._hover:
            bg = QColor(50, 52, 66)
            border = QColor(100, 110, 140)
        else:
            bg = QColor(35, 37, 48)
            border = QColor(60, 62, 78)

        p.setBrush(bg)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(1, 1, self.width()-2, self.height()-2, 4, 4)

        # 精灵图
        pm = PixmapCache.get_sprite(self.entry)
        if pm and not pm.isNull():
            scaled = pm.scaled(self.THUMB_SIZE, self.THUMB_SIZE,
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = 4
            p.drawPixmap(x, y, scaled)
        else:
            p.setPen(QColor(180, 60, 60))
            p.setFont(QFont("Consolas", 10))
            p.drawText(4, 4, self.THUMB_SIZE, self.THUMB_SIZE,
                       Qt.AlignCenter, "?")

        # 标签
        p.setPen(QColor(180, 185, 200))
        p.setFont(QFont("Microsoft YaHei UI", 7))
        label = self.sprite_name
        if len(label) > 12:
            label = label[:10] + "…"
        p.drawText(0, self.THUMB_SIZE + 4, self.width(), 16,
                   Qt.AlignHCenter, label)
        p.end()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.sprite_name)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.sprite_name)
        super().mouseDoubleClickEvent(event)


# ═══════════════════════════════════════════════════════════════
# AliasRow — 别名列表中的一行
# ═══════════════════════════════════════════════════════════════

class AliasRow(QFrame):
    """一个别名条目：别名名称 + 分配的精灵预览。"""

    PREVIEW_SIZE = 48
    clicked = pyqtSignal(str)          # alias_name
    clear_requested = pyqtSignal(str)  # alias_name

    def __init__(self, alias_name: str, sprite_name: str = "",
                 sprite_map: Dict[str, SpriteEntry] = None,
                 parent=None):
        super().__init__(parent)
        self.alias_name = alias_name
        self.sprite_name = sprite_name
        self._sprite_map = sprite_map or {}
        self._hover = False
        self._selected = False

        self.setFixedHeight(self.PREVIEW_SIZE + 12)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def set_selected(self, sel: bool):
        self._selected = sel
        self.update()

    def set_sprite(self, sprite_name: str):
        self.sprite_name = sprite_name
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # 背景
        if self._selected:
            bg = QColor(55, 55, 80)
            border = QColor(137, 180, 250)
        elif self._hover:
            bg = QColor(45, 47, 58)
            border = QColor(80, 83, 100)
        else:
            bg = QColor(30, 30, 46)
            border = QColor(49, 50, 68)

        p.setBrush(bg)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(1, 1, w-2, h-2, 4, 4)

        # 精灵预览
        pm = None
        if self.sprite_name and self.sprite_name in self._sprite_map:
            entry = self._sprite_map[self.sprite_name]
            pm = PixmapCache.get_sprite(entry)

        preview_x = 6
        preview_y = (h - self.PREVIEW_SIZE) // 2
        if pm and not pm.isNull():
            scaled = pm.scaled(self.PREVIEW_SIZE, self.PREVIEW_SIZE,
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(preview_x + (self.PREVIEW_SIZE - scaled.width()) // 2,
                         preview_y + (self.PREVIEW_SIZE - scaled.height()) // 2,
                         scaled)
        else:
            p.setPen(QPen(QColor(80, 60, 60), 1, Qt.DashLine))
            p.setBrush(QColor(40, 30, 30))
            p.drawRect(preview_x, preview_y, self.PREVIEW_SIZE, self.PREVIEW_SIZE)
            p.setPen(QColor(140, 80, 80))
            p.setFont(QFont("Consolas", 8))
            if self.sprite_name:
                p.drawText(preview_x, preview_y, self.PREVIEW_SIZE,
                           self.PREVIEW_SIZE, Qt.AlignCenter, "✗")
            else:
                p.drawText(preview_x, preview_y, self.PREVIEW_SIZE,
                           self.PREVIEW_SIZE, Qt.AlignCenter, "空")

        # 别名文本
        text_x = preview_x + self.PREVIEW_SIZE + 10
        p.setPen(QColor(137, 180, 250))
        p.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        p.drawText(text_x, 6, w - text_x - 6, 20, Qt.AlignVCenter, self.alias_name)

        # 精灵名
        p.setPen(QColor(166, 173, 200) if self.sprite_name else QColor(108, 112, 134))
        p.setFont(QFont("Microsoft YaHei UI", 8))
        sprite_label = self.sprite_name if self.sprite_name else "(未分配)"
        p.drawText(text_x, 26, w - text_x - 6, 20, Qt.AlignVCenter, sprite_label)
        p.end()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.alias_name)
        super().mousePressEvent(event)

    def _context_menu(self, pos):
        menu = QMenu(self)
        clear_action = menu.addAction("清除分配")
        remove_action = menu.addAction("删除别名")
        action = menu.exec(self.mapToGlobal(pos))
        if action == clear_action:
            self.clear_requested.emit(self.alias_name)
        elif action == remove_action:
            # 发送一个特殊信号由父组件处理
            parent = self.parent()
            while parent and not isinstance(parent, EnemyAliasManager):
                parent = parent.parent()
            if parent:
                parent._remove_alias(self.alias_name)


# ═══════════════════════════════════════════════════════════════
# SpritePalettePanel — 精灵面板（右侧）
# ═══════════════════════════════════════════════════════════════

class SpritePalettePanel(QWidget):
    """显示所有可用敌人精灵的面板。"""

    sprite_selected = pyqtSignal(str)       # sprite_name
    sprite_double_clicked = pyqtSignal(str) # sprite_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sprite_map: Dict[str, SpriteEntry] = {}
        self._thumbs: Dict[str, SpriteThumb] = {}
        self._current: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # 搜索栏
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("输入精灵名称...")
        self._search_edit.textChanged.connect(self._filter)
        search_layout.addWidget(self._search_edit)
        layout.addLayout(search_layout)

        # 精灵网格
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(4)
        scroll.setWidget(self._grid_widget)
        layout.addWidget(scroll)

    def set_sprites(self, sprite_map: Dict[str, SpriteEntry]):
        self._sprite_map = sprite_map
        self._rebuild()

    def _rebuild(self):
        # 清除旧的
        for thumb in self._thumbs.values():
            thumb.setParent(None)
            thumb.deleteLater()
        self._thumbs.clear()

        cols = 4
        row = 0
        col = 0
        for name in sorted(self._sprite_map.keys()):
            entry = self._sprite_map[name]
            thumb = SpriteThumb(name, entry)
            thumb.selected.connect(self._on_thumb_selected)
            thumb.double_clicked.connect(self.sprite_double_clicked.emit)
            self._grid_layout.addWidget(thumb, row, col)
            self._thumbs[name] = thumb
            col += 1
            if col >= cols:
                col = 0
                row += 1

    def _on_thumb_selected(self, name: str):
        if self._current and self._current in self._thumbs:
            self._thumbs[self._current].set_selected(False)
        self._current = name
        if name in self._thumbs:
            self._thumbs[name].set_selected(True)
        self.sprite_selected.emit(name)

    def _filter(self, text: str):
        text = text.strip().lower()
        for name, thumb in self._thumbs.items():
            thumb.setVisible(not text or text in name.lower())


# ═══════════════════════════════════════════════════════════════
# SpritePreview — 精灵大预览
# ═══════════════════════════════════════════════════════════════

class SpritePreviewPanel(QGroupBox):
    """精灵详情预览面板。"""

    PREVIEW_SIZE = 128

    def __init__(self, parent=None):
        super().__init__("精灵预览", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 8)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setFixedSize(self.PREVIEW_SIZE + 8, self.PREVIEW_SIZE + 8)
        self._preview_label.setStyleSheet(
            "background: #11111b; border: 1px solid #313244; border-radius: 4px;")
        layout.addWidget(self._preview_label, alignment=Qt.AlignCenter)

        self._info_label = QLabel("选择一个精灵查看详情")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: #a6adc8;")
        layout.addWidget(self._info_label)
        layout.addStretch()

    def show_sprite(self, name: str, entry: Optional[SpriteEntry]):
        if entry is None:
            self._preview_label.clear()
            self._info_label.setText(f"精灵「{name}」未找到")
            return

        pm = PixmapCache.get_sprite(entry)
        if pm and not pm.isNull():
            scaled = pm.scaled(self.PREVIEW_SIZE, self.PREVIEW_SIZE,
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._preview_label.setPixmap(scaled)
        else:
            self._preview_label.setText("?")

        info = (f"名称: {name}\n"
                f"图集: {entry.atlas}\n"
                f"区域: {entry.rect}\n"
                f"纹理: {Path(entry.texture_path).name}")
        self._info_label.setText(info)

    def clear(self):
        self._preview_label.clear()
        self._info_label.setText("选择一个精灵查看详情")


# ═══════════════════════════════════════════════════════════════
# EnemyAliasManager — 主窗口
# ═══════════════════════════════════════════════════════════════

class EnemyAliasManager(QMainWindow):
    """敌人别名管理器主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("敌人别名管理器 — Enemy Alias Manager")
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)

        self._atlases: Dict[str, List[SpriteEntry]] = {}
        self._sprite_map: Dict[str, SpriteEntry] = {}
        self._mapping: Dict[str, str] = {}       # alias → sprite_name
        self._saved_mapping: Dict[str, str] = {}
        self._current_alias: Optional[str] = None
        self._alias_rows: Dict[str, AliasRow] = {}

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        apply_dark_theme(self)
        self._load_data()

    # ───── UI ─────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)

        # 左: 别名列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)

        alias_header = QHBoxLayout()
        alias_header.addWidget(QLabel("别名列表"))
        alias_header.addStretch()
        btn_add_alias = QPushButton("+ 添加别名")
        btn_add_alias.clicked.connect(self._add_alias)
        alias_header.addWidget(btn_add_alias)
        left_layout.addLayout(alias_header)

        # 别名滚动区
        self._alias_scroll = QScrollArea()
        self._alias_scroll.setWidgetResizable(True)
        self._alias_container = QWidget()
        self._alias_layout = QVBoxLayout(self._alias_container)
        self._alias_layout.setSpacing(4)
        self._alias_layout.setContentsMargins(2, 2, 2, 2)
        self._alias_layout.addStretch()
        self._alias_scroll.setWidget(self._alias_container)
        left_layout.addWidget(self._alias_scroll)
        splitter.addWidget(left_widget)

        # 中: 精灵面板
        self._sprite_palette = SpritePalettePanel()
        self._sprite_palette.sprite_selected.connect(self._on_sprite_selected)
        self._sprite_palette.sprite_double_clicked.connect(self._on_sprite_assign)
        splitter.addWidget(self._sprite_palette)

        # 右: 预览面板
        self._preview_panel = SpritePreviewPanel()
        self._preview_panel.setMaximumWidth(260)
        splitter.addWidget(self._preview_panel)

        splitter.setSizes([320, 580, 260])
        main_layout.addWidget(splitter)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

    def _setup_menu(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("文件(&F)")

        save_action = QAction("保存 (&S)", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save)
        file_menu.addAction(save_action)

        reload_action = QAction("重新加载 (&R)", self)
        reload_action.setShortcut("Ctrl+R")
        reload_action.triggered.connect(self._load_data)
        file_menu.addAction(reload_action)

        file_menu.addSeparator()
        quit_action = QAction("退出 (&Q)", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = mb.addMenu("编辑(&E)")

        add_alias_action = QAction("添加别名 (&A)", self)
        add_alias_action.triggered.connect(self._add_alias)
        edit_menu.addAction(add_alias_action)

        auto_detect_action = QAction("自动检测别名", self)
        auto_detect_action.triggered.connect(self._auto_detect)
        edit_menu.addAction(auto_detect_action)

        edit_menu.addSeparator()
        add_sprite_json_action = QAction("创建精灵图集配置…", self)
        add_sprite_json_action.triggered.connect(self._create_sprite_atlas)
        edit_menu.addAction(add_sprite_json_action)

        view_menu = mb.addMenu("视图(&V)")
        refresh_action = QAction("刷新 (&F)", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._refresh)
        view_menu.addAction(refresh_action)

    def _setup_toolbar(self):
        toolbar = QToolBar("工具栏")
        self.addToolBar(toolbar)

        save_btn = QPushButton("💾 保存")
        save_btn.setToolTip("保存到 enemy_aliases.json (Ctrl+S)")
        save_btn.clicked.connect(self._save)
        toolbar.addWidget(save_btn)

        toolbar.addSeparator()

        add_btn = QPushButton("+ 别名")
        add_btn.setToolTip("添加新的敌人别名")
        add_btn.clicked.connect(self._add_alias)
        toolbar.addWidget(add_btn)

        auto_btn = QPushButton("🔍 自动检测")
        auto_btn.setToolTip("自动从精灵名生成别名")
        auto_btn.clicked.connect(self._auto_detect)
        toolbar.addWidget(auto_btn)

        toolbar.addSeparator()

        atlas_btn = QPushButton("📐 创建图集")
        atlas_btn.setToolTip("为敌人纹理创建精灵图集 JSON 配置")
        atlas_btn.clicked.connect(self._create_sprite_atlas)
        toolbar.addWidget(atlas_btn)

        toolbar.addSeparator()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setToolTip("重新加载 (F5)")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)

    # ───── 数据加载 ─────

    def _load_data(self):
        self._atlases = load_all_enemy_sprites(ENEMY_IMAGE_DIR)
        PixmapCache.ensure_all_loaded(self._atlases)
        self._sprite_map = get_sprite_entry_map(self._atlases)

        self._mapping = load_enemy_aliases(ENEMY_ALIASES_PATH)
        if not self._mapping:
            # 自动检测：每个精灵名自身作为别名
            self._mapping = {name: name for name in sorted(self._sprite_map.keys())}
            if self._mapping:
                self._status.showMessage("未找到别名配置，已从精灵名自动生成", 5000)
            else:
                self._status.showMessage("未找到敌人精灵，请在 assets/images/enemy/ 添加纹理", 5000)
        else:
            self._status.showMessage(
                f"已加载 {len(self._mapping)} 个敌人别名", 5000)

        self._saved_mapping = dict(self._mapping)

        # 更新 UI
        self._sprite_palette.set_sprites(self._sprite_map)
        self._rebuild_alias_list()

    def _refresh(self):
        # 保留当前编辑
        current_mapping = dict(self._mapping)
        self._atlases = load_all_enemy_sprites(ENEMY_IMAGE_DIR)
        PixmapCache.clear()
        PixmapCache.ensure_all_loaded(self._atlases)
        self._sprite_map = get_sprite_entry_map(self._atlases)
        self._mapping = current_mapping
        self._sprite_palette.set_sprites(self._sprite_map)
        self._rebuild_alias_list()
        self._status.showMessage("已刷新", 3000)

    # ───── 别名列表 ─────

    def _rebuild_alias_list(self):
        # 清除旧的
        for row in self._alias_rows.values():
            row.setParent(None)
            row.deleteLater()
        self._alias_rows.clear()

        # 移除 stretch
        while self._alias_layout.count():
            item = self._alias_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        for alias_name in sorted(self._mapping.keys()):
            sprite_name = self._mapping.get(alias_name, "")
            row = AliasRow(alias_name, sprite_name, self._sprite_map)
            row.clicked.connect(self._on_alias_clicked)
            row.clear_requested.connect(self._on_alias_clear)
            self._alias_layout.addWidget(row)
            self._alias_rows[alias_name] = row

        self._alias_layout.addStretch()

        # 恢复选中
        if self._current_alias and self._current_alias in self._alias_rows:
            self._alias_rows[self._current_alias].set_selected(True)

    def _on_alias_clicked(self, alias_name: str):
        # 取消旧选中
        if self._current_alias and self._current_alias in self._alias_rows:
            self._alias_rows[self._current_alias].set_selected(False)

        self._current_alias = alias_name
        if alias_name in self._alias_rows:
            self._alias_rows[alias_name].set_selected(True)

        # 显示分配的精灵
        sprite_name = self._mapping.get(alias_name, "")
        if sprite_name:
            entry = self._sprite_map.get(sprite_name)
            self._preview_panel.show_sprite(sprite_name, entry)
        else:
            self._preview_panel.clear()

    def _on_alias_clear(self, alias_name: str):
        self._mapping[alias_name] = ""
        if alias_name in self._alias_rows:
            self._alias_rows[alias_name].set_sprite("")
        self._status.showMessage(f"已清除 {alias_name} 的分配", 3000)

    # ───── 精灵选中 / 分配 ─────

    def _on_sprite_selected(self, sprite_name: str):
        entry = self._sprite_map.get(sprite_name)
        self._preview_panel.show_sprite(sprite_name, entry)

    def _on_sprite_assign(self, sprite_name: str):
        """双击精灵 → 分配给当前选中的别名。"""
        if not self._current_alias:
            self._status.showMessage("请先在左侧选择一个别名", 3000)
            return

        self._mapping[self._current_alias] = sprite_name
        if self._current_alias in self._alias_rows:
            self._alias_rows[self._current_alias].set_sprite(sprite_name)

        entry = self._sprite_map.get(sprite_name)
        self._preview_panel.show_sprite(sprite_name, entry)
        self._status.showMessage(
            f"已分配: {self._current_alias} → {sprite_name}", 3000)

    # ───── 编辑操作 ─────

    def _add_alias(self):
        name, ok = QInputDialog.getText(
            self, "添加敌人别名",
            "新别名 (如 enemy_fairy_red):")
        if ok and name.strip():
            name = name.strip()
            if name in self._mapping:
                QMessageBox.warning(self, "重复", f"别名 {name} 已存在")
                return
            self._mapping[name] = ""
            self._rebuild_alias_list()
            self._on_alias_clicked(name)
            self._status.showMessage(f"已添加别名: {name}", 3000)

    def _remove_alias(self, alias_name: str):
        reply = QMessageBox.question(
            self, "删除别名",
            f"确认删除别名 {alias_name}？",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._mapping.pop(alias_name, None)
            if self._current_alias == alias_name:
                self._current_alias = None
            self._rebuild_alias_list()
            self._status.showMessage(f"已删除别名: {alias_name}", 3000)

    def _auto_detect(self):
        """自动检测：为所有未分配的精灵创建同名别名。"""
        added = 0
        for name in sorted(self._sprite_map.keys()):
            if name not in self._mapping:
                self._mapping[name] = name
                added += 1
        if added:
            self._rebuild_alias_list()
            self._status.showMessage(f"已自动添加 {added} 个别名", 5000)
        else:
            self._status.showMessage("没有新精灵需要添加", 3000)

    # ───── 图集创建 ─────

    def _create_sprite_atlas(self):
        """为敌人纹理创建精灵图集 JSON 配置（区域式）。"""
        png_path, _ = QFileDialog.getOpenFileName(
            self, "选择敌人纹理",
            str(ENEMY_IMAGE_DIR),
            "图片 (*.png *.jpg)")
        if not png_path:
            return

        png_path = Path(png_path)
        atlas_name = png_path.stem
        json_path = png_path.parent / f"{atlas_name}.json"

        if json_path.exists():
            reply = QMessageBox.question(
                self, "文件已存在",
                f"{json_path.name} 已存在，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        dialog = _AtlasZoneDialog(str(png_path), json_path, self)
        if dialog.exec() == QDialog.Accepted:
            sprites, animations = dialog.get_result()
            zones_meta = dialog.get_zones_meta()
            import json
            data = {
                "__image_filename": png_path.name,
                "sprites": sprites,
                "animations": animations,
                "zones": zones_meta,
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            n_spr = len(sprites)
            n_anim = len(animations)
            self._status.showMessage(
                f"已生成 {json_path.name} ({n_spr} 精灵, {n_anim} 动画)", 5000)
            self._refresh()

    # ───── 保存 ─────

    def _save(self):
        try:
            save_enemy_aliases(self._mapping, ENEMY_ALIASES_PATH)
            self._saved_mapping = dict(self._mapping)
            self._status.showMessage(
                f"✅ 已保存到 {ENEMY_ALIASES_PATH.name}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入文件失败:\n{e}")

    # ───── 关闭 ─────

    def _is_dirty(self) -> bool:
        return self._mapping != self._saved_mapping

    def closeEvent(self, event):
        if self._is_dirty():
            reply = QMessageBox.question(
                self, "未保存",
                "别名映射已修改但未保存，确认退出？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()


# ═══════════════════════════════════════════════════════════════
# AtlasGridDialog — 网格切割对话框
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# Zone-Based Atlas — 区域式精灵图集切割
# ═══════════════════════════════════════════════════════════════

class _ZoneInfo:
    """一个区域：对应一种敌人的动画帧区域。"""

    def __init__(self, name: str, x: int, y: int, w: int, h: int,
                 frame_w: int = 0, frame_h: int = 0):
        self.name = name
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.frame_w = frame_w if frame_w > 0 else w
        self.frame_h = frame_h if frame_h > 0 else h

    @property
    def frame_cols(self) -> int:
        return max(1, self.w // self.frame_w) if self.frame_w > 0 else 0

    @property
    def frame_rows(self) -> int:
        return max(1, self.h // self.frame_h) if self.frame_h > 0 else 0

    @property
    def total_frames(self) -> int:
        return self.frame_cols * self.frame_rows


class _TextureCanvas(QWidget):
    """可交互纹理画布：显示纹理 + 区域叠加层，支持拖拽绘制新区域。"""

    zone_drawn  = pyqtSignal(int, int, int, int)   # x, y, w, h (tex coords)
    zone_clicked = pyqtSignal(int)                  # zone index

    _COLORS = [
        (255, 80, 80),  (80, 200, 80),  (80, 120, 255),
        (255, 220, 50), (255, 80, 220), (80, 220, 220),
        (255, 150, 50), (180, 80, 255),
    ]

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._pm = pixmap
        self._scale = 1.0
        self._zones: List[_ZoneInfo] = []
        self._sel = -1
        self._drawing = False
        self._d_start = None
        self._d_cur   = None
        self.setMouseTracking(True)
        self._sync_size()

    # ── helpers ────────────────────────────────────────────
    def _sync_size(self):
        if self._pm and not self._pm.isNull():
            w = int(self._pm.width()  * self._scale)
            h = int(self._pm.height() * self._scale)
            self.setFixedSize(max(w, 1), max(h, 1))

    def _t2w(self, tx, ty):
        return int(tx * self._scale), int(ty * self._scale)

    def _w2t(self, wx, wy):
        s = self._scale if self._scale else 1
        return int(wx / s), int(wy / s)

    # ── public API ─────────────────────────────────────────
    def set_scale(self, s: float):
        self._scale = max(0.25, min(4.0, s))
        self._sync_size()
        self.update()

    def set_zones(self, zones: List[_ZoneInfo]):
        self._zones = zones
        self.update()

    def set_selected(self, idx: int):
        self._sel = idx
        self.update()

    # ── paint ──────────────────────────────────────────────
    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        # 纹理
        if self._pm and not self._pm.isNull():
            w = int(self._pm.width()  * self._scale)
            h = int(self._pm.height() * self._scale)
            p.drawPixmap(0, 0, w, h, self._pm)

        # 区域
        for i, z in enumerate(self._zones):
            r, g, b = self._COLORS[i % len(self._COLORS)]
            sel = (i == self._sel)
            wx, wy = self._t2w(z.x, z.y)
            ww = int(z.w * self._scale)
            wh = int(z.h * self._scale)

            # 背景填充
            p.setBrush(QBrush(QColor(r, g, b, 90 if sel else 35)))
            p.setPen(QPen(QColor(r, g, b, 255), 2 if sel else 1))
            p.drawRect(wx, wy, ww, wh)

            # 选中区域画帧分割线 + 帧序号
            if sel and z.frame_w > 0 and z.frame_h > 0:
                fw_s = int(z.frame_w * self._scale)
                fh_s = int(z.frame_h * self._scale)
                cols = z.frame_cols
                rows = z.frame_rows

                p.setPen(QPen(QColor(255, 255, 255, 140), 1, Qt.DashLine))
                for c in range(1, cols):
                    lx = wx + c * fw_s
                    p.drawLine(lx, wy, lx, wy + wh)
                for rr in range(1, rows):
                    ly = wy + rr * fh_s
                    p.drawLine(wx, ly, wx + ww, ly)

                fnt = max(7, min(fw_s, fh_s) // 5)
                p.setFont(QFont("Consolas", fnt))
                p.setPen(QColor(255, 255, 100, 220))
                for rr in range(rows):
                    for c in range(cols):
                        idx = rr * cols + c
                        p.drawText(wx + c * fw_s, wy + rr * fh_s,
                                   fw_s, fh_s, Qt.AlignCenter, str(idx))

            # 区域名称标签
            p.setFont(QFont("Microsoft YaHei UI", 8, QFont.Bold))
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(z.name) + 6
            p.fillRect(wx, wy, tw, 16, QColor(0, 0, 0, 160))
            p.setPen(QColor(255, 255, 255, 240))
            p.drawText(wx + 3, wy + 12, z.name)

        # 正在拖拽绘制的矩形
        if self._drawing and self._d_start and self._d_cur:
            sx, sy = self._d_start
            cx, cy = self._d_cur
            rx, ry = min(sx, cx), min(sy, cy)
            rw, rh = abs(cx - sx), abs(cy - sy)
            p.setBrush(QBrush(QColor(255, 200, 50, 40)))
            p.setPen(QPen(QColor(255, 200, 50, 200), 2, Qt.DashLine))
            p.drawRect(rx, ry, rw, rh)
            # 尺寸提示
            tx1, ty1 = self._w2t(rx, ry)
            tx2, ty2 = self._w2t(rx + rw, ry + rh)
            p.setPen(QColor(255, 200, 50))
            p.setFont(QFont("Consolas", 10))
            p.drawText(rx + 4, ry - 4, f"{tx2-tx1}×{ty2-ty1}")

        p.end()

    # ── mouse ──────────────────────────────────────────────
    def mousePressEvent(self, evt):
        if evt.button() != Qt.LeftButton:
            return
        tx, ty = self._w2t(evt.x(), evt.y())
        # 点击已有区域 → 选中
        for i in range(len(self._zones) - 1, -1, -1):
            z = self._zones[i]
            if z.x <= tx <= z.x + z.w and z.y <= ty <= z.y + z.h:
                self.zone_clicked.emit(i)
                return
        # 空白处 → 开始绘制
        self._drawing = True
        self._d_start = (evt.x(), evt.y())
        self._d_cur   = self._d_start

    def mouseMoveEvent(self, evt):
        if self._drawing:
            self._d_cur = (evt.x(), evt.y())
            self.update()

    def mouseReleaseEvent(self, evt):
        if evt.button() != Qt.LeftButton or not self._drawing:
            return
        self._drawing = False
        if self._d_start and self._d_cur:
            sx, sy = self._d_start
            cx, cy = self._d_cur
            tx1, ty1 = self._w2t(min(sx, cx), min(sy, cy))
            tx2, ty2 = self._w2t(max(sx, cx), max(sy, cy))
            tw, th = tx2 - tx1, ty2 - ty1
            if tw > 4 and th > 4:
                self.zone_drawn.emit(tx1, ty1, tw, th)
        self._d_start = self._d_cur = None
        self.update()


# ═══════════════════════════════════════════════════════════════
# Alpha-Channel Auto-Detection — 基于 Alpha 通道的自动精灵检测
# ═══════════════════════════════════════════════════════════════

_HSV_COLOR_TABLE = [
    ((0, 10),   "red"),
    ((10, 25),  "orange"),
    ((25, 35),  "yellow"),
    ((35, 80),  "green"),
    ((80, 130), "blue"),
    ((130, 160), "purple"),
    ((160, 180), "red"),
]


def _detect_color_name(img_bgra, x: int, y: int, w: int, h: int) -> str:
    """基于 HSV 色相识别区域的主色调名称。"""
    roi = img_bgra[y:y+h, x:x+w]
    if roi.size == 0:
        return ""
    alpha = roi[:, :, 3]
    mask = alpha > 20
    if not mask.any():
        return ""
    hsv = cv2.cvtColor(roi[:, :, :3], cv2.COLOR_BGR2HSV)
    h_vals = hsv[:, :, 0][mask]
    s_vals = hsv[:, :, 1][mask]
    v_vals = hsv[:, :, 2][mask]
    avg_s = float(s_vals.mean())
    avg_v = float(v_vals.mean())
    if avg_s < 40:
        return "white" if avg_v > 180 else ("gray" if avg_v > 80 else "black")
    avg_h = float(h_vals.mean())
    for (lo, hi), name in _HSV_COLOR_TABLE:
        if lo <= avg_h < hi:
            return name
    return "red"


def _column_projection_frames(
    full_alpha: np.ndarray,
    row_y: int, row_h: int,
    scan_x: int, scan_end_x: int,
    min_frame_px: int = 6,
) -> Tuple[int, int, int]:
    """
    列投影法检测帧数和帧宽。

    对行条带的 Alpha 做列求和，找出内容段（不透明列的连续区间），
    根据段间距判定帧宽、帧数。比轮廓法更适合密集多帧场景。

    Returns:
        (frame_w, n_frames, content_start_x)
    """
    strip = full_alpha[row_y:row_y + row_h, scan_x:scan_end_x]
    if strip.size == 0:
        return (scan_end_x - scan_x, 1, scan_x)

    col_sum = strip.sum(axis=0).astype(np.float64)
    thresh = max(row_h * 2.0, 10.0)
    is_content = col_sum > thresh

    # ── 找连续内容段 ──
    segments: List[Tuple[int, int]] = []  # (start_col, end_col)
    in_seg = False
    seg_start = 0
    for i in range(len(is_content)):
        if is_content[i] and not in_seg:
            seg_start = i
            in_seg = True
        elif not is_content[i] and in_seg:
            if i - seg_start >= min_frame_px:
                segments.append((seg_start, i))
            in_seg = False
    if in_seg:
        seg_end = len(is_content)
        if seg_end - seg_start >= min_frame_px:
            segments.append((seg_start, seg_end))

    if not segments:
        return (scan_end_x - scan_x, 1, scan_x)

    n = len(segments)
    if n == 1:
        seg_w = segments[0][1] - segments[0][0]
        return (seg_w, 1, scan_x + segments[0][0])

    # 段间步长
    strides = [segments[j + 1][0] - segments[j][0] for j in range(n - 1)]
    strides_sorted = sorted(strides)
    median_stride = strides_sorted[len(strides_sorted) // 2]

    max_seg_w = max(s[1] - s[0] for s in segments)
    frame_w = max(median_stride, max_seg_w)

    return (frame_w, n, scan_x + segments[0][0])


def _align_zones(zones: List[_ZoneInfo]) -> List[_ZoneInfo]:
    """
    对齐一组 zone：统一 frame_w / frame_h / x / w。

    同一次框选产生的多行应保持一致的帧尺寸、起始位置和总宽度。
    """
    if len(zones) <= 1:
        return zones

    from statistics import median as _median

    # 帧宽：中位数，四舍五入到偶数
    raw_fw = _median([z.frame_w for z in zones])
    med_fw = max(4, int(round(raw_fw / 2.0)) * 2)

    # 帧高：取最大值（防裁剪）
    max_fh = max(z.frame_h for z in zones)

    # 公共 X 起点（最小值）
    min_x = min(z.x for z in zones)

    # 帧数：各行帧数取最大
    max_cols = max(max(1, round(z.w / med_fw)) for z in zones)
    zone_w = med_fw * max_cols

    zones.sort(key=lambda z: z.y)

    for z in zones:
        z.frame_w = med_fw
        z.frame_h = max_fh
        z.x = min_x
        z.w = zone_w
        z.h = max_fh

    return zones


def _group_align_zones(zones: List[_ZoneInfo]) -> List[_ZoneInfo]:
    """
    按相似帧尺寸分组，组内对齐。

    整图检测时不同敌人类型有不同帧大小，不能全局对齐。
    先把 frame_w 和 frame_h 相近的行归为一组，再组内调用 _align_zones。
    """
    if len(zones) <= 1:
        return zones

    # 按 (frame_w, frame_h) 相似度归组
    # 允许 ±30% 的偏差视为同组
    groups: List[List[_ZoneInfo]] = []
    used = [False] * len(zones)

    for i in range(len(zones)):
        if used[i]:
            continue
        group = [zones[i]]
        used[i] = True
        fw_ref = zones[i].frame_w
        fh_ref = zones[i].frame_h
        for j in range(i + 1, len(zones)):
            if used[j]:
                continue
            fw_ratio = zones[j].frame_w / fw_ref if fw_ref else 0
            fh_ratio = zones[j].frame_h / fh_ref if fh_ref else 0
            if 0.7 <= fw_ratio <= 1.4 and 0.7 <= fh_ratio <= 1.4:
                group.append(zones[j])
                used[j] = True
        groups.append(group)

    # 组内对齐
    result: List[_ZoneInfo] = []
    for group in groups:
        if len(group) > 1:
            group = _align_zones(group)
        result.extend(group)

    # 按 y 排序 + 重新编号
    result.sort(key=lambda z: z.y)
    for idx, z in enumerate(result):
        parts = z.name.rsplit("_", 1)
        color_sfx = parts[1] if len(parts) == 2 and parts[1] in (
            "red", "orange", "yellow", "green",
            "blue", "purple", "white", "gray", "black") else ""
        z.name = f"anim_{idx}_{color_sfx}" if color_sfx else f"anim_{idx}"

    return result


def _auto_detect_zones_in_region(
    png_path: str,
    region: Optional[Tuple[int, int, int, int]] = None,
    alpha_thresh: int = 10,
    min_sprite_px: int = 6,
    align: bool = True,
) -> List[_ZoneInfo]:
    """
    基于 Alpha 通道连通域 + 列投影法，自动识别精灵行。

    算法:
      1. Alpha 掩码 → cv2.findContours → 包围盒
      2. 按 Y 邻近度分组为行
      3. 列投影法细化每行的帧宽/帧数（解决密集多帧问题）
      4. 对齐：统一 frame_w / frame_h / x（解决行间不齐问题）
      5. HSV 色相命名

    Returns:
        按从上到下排列的 _ZoneInfo 列表
    """
    if not _HAS_CV2:
        return []

    img = cv2.imread(png_path, cv2.IMREAD_UNCHANGED)
    if img is None or len(img.shape) < 3 or img.shape[2] < 4:
        return []

    full_img = img
    full_alpha = img[:, :, 3]
    ox, oy = 0, 0
    if region:
        rx, ry, rw, rh = region
        ox, oy = rx, ry
        img = img[ry:ry + rh, rx:rx + rw]

    alpha = img[:, :, 3]
    _, mask = cv2.threshold(alpha, alpha_thresh, 255, cv2.THRESH_BINARY)

    # 连通域包围盒
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    bboxes = []
    for cnt in contours:
        bx, by, bw, bh = cv2.boundingRect(cnt)
        if bw >= min_sprite_px and bh >= min_sprite_px:
            bboxes.append((bx + ox, by + oy, bw, bh))

    if not bboxes:
        return []

    bboxes.sort(key=lambda b: (b[1], b[0]))

    # ── 分行（Y 邻近度） ──
    rows: List[List[Tuple[int, int, int, int]]] = []
    cur_row = [bboxes[0]]
    for bb in bboxes[1:]:
        ref_y = sum(b[1] for b in cur_row) / len(cur_row)
        ref_h = sum(b[3] for b in cur_row) / len(cur_row)
        if abs(bb[1] - ref_y) < ref_h * 0.5:
            cur_row.append(bb)
        else:
            rows.append(cur_row)
            cur_row = [bb]
    rows.append(cur_row)

    # ── 每行 → zone ──
    zones: List[_ZoneInfo] = []
    for i, row_bbs in enumerate(rows):
        row_bbs.sort(key=lambda b: b[0])
        min_x = min(b[0] for b in row_bbs)
        min_y = min(b[1] for b in row_bbs)
        max_r = max(b[0] + b[2] for b in row_bbs)
        max_b = max(b[1] + b[3] for b in row_bbs)
        row_h = max_b - min_y

        # 列投影法精确检测帧宽/帧数
        proj_fw, proj_n, proj_x = _column_projection_frames(
            full_alpha, min_y, row_h, min_x, max_r, min_sprite_px)

        # contour 法作为参考
        n_contour = len(row_bbs)

        # 当列投影和轮廓法都给出结果时，优先信任帧数更多的一方
        # （轮廓可能合并 → 帧数少；投影可能误切 → 但很少）
        if proj_n >= n_contour:
            frame_w = proj_fw
            n_frames = proj_n
            start_x = proj_x
        else:
            # 轮廓法检测到更多帧 → 用轮廓法步长
            max_bw = max(b[2] for b in row_bbs)
            if n_contour >= 2:
                strides = [row_bbs[j + 1][0] - row_bbs[j][0]
                           for j in range(n_contour - 1)]
                strides_sorted = sorted(strides)
                stride = strides_sorted[len(strides_sorted) // 2]
                frame_w = max(stride, max_bw)
            else:
                frame_w = max_bw
            n_frames = n_contour
            start_x = min_x

        zone_w = frame_w * n_frames
        frame_h = row_h

        # 颜色
        color = ""
        try:
            color = _detect_color_name(full_img, min_x, min_y,
                                       max_r - min_x, max_b - min_y)
        except Exception:
            pass

        name = f"anim_{i}_{color}" if color else f"anim_{i}"

        zones.append(_ZoneInfo(
            name=name, x=start_x, y=min_y,
            w=zone_w, h=frame_h,
            frame_w=frame_w, frame_h=frame_h,
        ))

    # ── 过滤噪声行 ──
    # 高度远小于中位数的行通常是误检（比如边缘伪影）
    if len(zones) >= 2:
        from statistics import median as _med
        med_h = _med([z.frame_h for z in zones])
        zones = [z for z in zones if z.frame_h >= med_h * 0.3]

    # ── 对齐 ──
    if align and len(zones) > 1:
        zones = _align_zones(zones)
        # 重新赋名（对齐后 index 不变，仅更新名称里的编号）
        for idx, z in enumerate(zones):
            # 保留颜色后缀
            parts = z.name.rsplit("_", 1)
            color_sfx = parts[1] if len(parts) == 2 and parts[1] in (
                "red", "orange", "yellow", "green",
                "blue", "purple", "white", "gray", "black") else ""
            z.name = f"anim_{idx}_{color_sfx}" if color_sfx else f"anim_{idx}"

    return zones


class _AtlasZoneDialog(QDialog):
    """
    区域式精灵图集切割对话框。

    在纹理上拖拽绘制矩形区域来定义敌人类型。每个区域包含该敌人
    的水平动画帧行，用户可调整帧大小 (frame_w × frame_h)。

    支持基于 Alpha 通道的自动检测：
      - 框选区域 → 自动识别行 → 自动分割帧 + 颜色标注
      - 一键检测整图

    输出::
        sprites   {sprite_name: {rect, center}}
        animations {anim_name: {frames, fps, loop}}
    """

    def __init__(self, png_path: str, json_path: Path = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("敌人精灵图集 — 区域定义")
        self.setMinimumSize(900, 600)
        self.resize(1100, 750)

        self._png_path = png_path
        self._json_path = json_path
        self._pm = QPixmap(png_path)
        self._zones: List[_ZoneInfo] = []
        self._sel = -1
        self._suppress = False

        root = QVBoxLayout(self)

        # ── toolbar ───────────────────────────────────────
        bar = QHBoxLayout()
        bar.addWidget(QLabel(
            f"<b>{Path(png_path).name}</b>  "
            f"({self._pm.width()}×{self._pm.height()})"))
        bar.addStretch()
        bar.addWidget(QLabel("缩放:"))
        self._zoom_cb = QComboBox()
        for z in ("50%", "100%", "150%", "200%"):
            self._zoom_cb.addItem(z)
        self._zoom_cb.setCurrentText("100%")
        self._zoom_cb.currentTextChanged.connect(self._on_zoom)
        bar.addWidget(self._zoom_cb)

        bar.addWidget(QLabel("  "))
        auto_full_btn = QPushButton("🔮 自动检测整图")
        auto_full_btn.setToolTip(
            "基于 Alpha 通道自动检测整张纹理中所有精灵行")
        auto_full_btn.clicked.connect(self._auto_detect_full)
        bar.addWidget(auto_full_btn)

        clear_all_btn = QPushButton("🗑 清空全部")
        clear_all_btn.clicked.connect(self._clear_all_zones)
        bar.addWidget(clear_all_btn)

        root.addLayout(bar)

        # ── main split ────────────────────────────────────
        split = QSplitter(Qt.Horizontal)

        # LEFT: 纹理画布
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setStyleSheet("QScrollArea{background:#11111b;}")
        self._canvas = _TextureCanvas(self._pm)
        self._canvas.zone_drawn.connect(self._on_zone_drawn)
        self._canvas.zone_clicked.connect(self._select_zone)
        scroll.setWidget(self._canvas)
        split.addWidget(scroll)

        # RIGHT: 区域列表 + 编辑
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 4, 0)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("<b>区域列表</b>"))
        hdr.addStretch()
        del_btn = QPushButton("✕ 删除")
        del_btn.clicked.connect(self._delete_zone)
        hdr.addWidget(del_btn)
        rl.addLayout(hdr)

        self._zone_list = QListWidget()
        self._zone_list.currentRowChanged.connect(self._on_list_row)
        rl.addWidget(self._zone_list)

        # 区域参数编辑
        grp = QGroupBox("区域参数")
        form = QFormLayout(grp)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("fairy_red")
        self._name_edit.textChanged.connect(self._on_param)
        form.addRow("名称:", self._name_edit)

        row_xy = QHBoxLayout()
        self._x_sp = QSpinBox(); self._x_sp.setRange(0, 9999)
        self._y_sp = QSpinBox(); self._y_sp.setRange(0, 9999)
        row_xy.addWidget(QLabel("X:")); row_xy.addWidget(self._x_sp)
        row_xy.addWidget(QLabel("Y:")); row_xy.addWidget(self._y_sp)
        self._x_sp.valueChanged.connect(self._on_param)
        self._y_sp.valueChanged.connect(self._on_param)
        form.addRow("位置:", row_xy)

        row_wh = QHBoxLayout()
        self._w_sp = QSpinBox(); self._w_sp.setRange(1, 9999)
        self._h_sp = QSpinBox(); self._h_sp.setRange(1, 9999)
        row_wh.addWidget(QLabel("W:")); row_wh.addWidget(self._w_sp)
        row_wh.addWidget(QLabel("H:")); row_wh.addWidget(self._h_sp)
        self._w_sp.valueChanged.connect(self._on_param)
        self._h_sp.valueChanged.connect(self._on_param)
        form.addRow("区域大小:", row_wh)

        row_f = QHBoxLayout()
        self._fw_sp = QSpinBox(); self._fw_sp.setRange(1, 9999)
        self._fh_sp = QSpinBox(); self._fh_sp.setRange(1, 9999)
        row_f.addWidget(QLabel("W:")); row_f.addWidget(self._fw_sp)
        row_f.addWidget(QLabel("H:")); row_f.addWidget(self._fh_sp)
        self._fw_sp.valueChanged.connect(self._on_param)
        self._fh_sp.valueChanged.connect(self._on_param)
        form.addRow("帧大小:", row_f)

        self._info = QLabel()
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color: #a6adc8; font-size: 10px;")
        form.addRow(self._info)

        rl.addWidget(grp)
        right.setMaximumWidth(320)
        split.addWidget(right)
        split.setSizes([750, 300])
        root.addWidget(split)

        # hint
        hint_text = (
            "💡 操作方式:\n"
            "  ① 点击「自动检测整图」一键识别所有精灵行\n"
            "  ② 或在纹理上拖拽框选区域 → 自动检测该区域内的精灵行\n"
            "  ③ 检测基于 Alpha 通道，每行 = 一个动画序列，自动标注颜色"
        )
        hint = QLabel(hint_text)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #89b4fa; font-size: 11px;")
        root.addWidget(hint)

        # buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        apply_dark_theme(self)
        self._set_editor_enabled(False)

        # 如果已有 JSON 配置，尝试加载
        self._try_load_existing()

    # ── 加载已有配置 ──────────────────────────────────────
    def _try_load_existing(self):
        """若 JSON 已存在，从中恢复区域定义。"""
        if self._json_path is None or not self._json_path.exists():
            return
        try:
            import json as _json
            with open(self._json_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            zones_data = data.get("zones", [])
            for zd in zones_data:
                z = _ZoneInfo(
                    name=zd.get("name", ""),
                    x=zd.get("x", 0), y=zd.get("y", 0),
                    w=zd.get("w", 32), h=zd.get("h", 32),
                    frame_w=zd.get("frame_w", 32),
                    frame_h=zd.get("frame_h", 32),
                )
                self._zones.append(z)
            if self._zones:
                self._refresh_list()
                self._select_zone(0)
        except Exception:
            pass

    # ── zoom ──────────────────────────────────────────────
    def _on_zoom(self, text: str):
        val = int(text.replace("%", "")) / 100.0
        self._canvas.set_scale(val)

    # ── zone 绘制 (含自动检测) ────────────────────────────
    def _on_zone_drawn(self, x, y, w, h):
        """框选区域时自动检测其中的精灵行。"""
        if _HAS_CV2:
            detected = _auto_detect_zones_in_region(
                self._png_path, region=(x, y, w, h))
            if detected:
                start = len(self._zones)
                # 重编号名称前缀
                base_idx = start
                for dz in detected:
                    dz.name = f"anim_{base_idx}_{dz.name.split('_', 2)[-1]}" \
                        if '_' in dz.name else f"anim_{base_idx}"
                    # 保留颜色后缀，简化前缀
                    parts = dz.name.rsplit('_', 1)
                    if len(parts) == 2 and parts[1] in (
                        'red', 'orange', 'yellow', 'green',
                        'blue', 'purple', 'white', 'gray', 'black',
                    ):
                        dz.name = f"anim_{base_idx}_{parts[1]}"
                    else:
                        dz.name = f"anim_{base_idx}"
                    base_idx += 1
                self._zones.extend(detected)
                self._refresh_list()
                self._select_zone(start)
                return

        # Fallback: 手动创建单区域
        idx = len(self._zones)
        name = f"enemy_type_{idx}"
        zone = _ZoneInfo(name, x, y, w, h, frame_w=w, frame_h=h)
        self._zones.append(zone)
        self._refresh_list()
        self._select_zone(idx)

    def _auto_detect_full(self):
        """自动检测整张纹理中所有精灵行。"""
        if not _HAS_CV2:
            QMessageBox.warning(
                self, "缺少依赖",
                "自动检测需要 OpenCV。\n"
                "请安装: pip install opencv-python")
            return

        # 整图检测不做全局对齐（不同敌人类型帧大小本就不同）
        # 改为按相似帧尺寸分组后，组内对齐
        detected = _auto_detect_zones_in_region(
            self._png_path, align=False)
        if not detected:
            QMessageBox.information(
                self, "未检测到",
                "未在纹理中检测到精灵（Alpha 通道无不透明区域）。")
            return

        # 按相似 frame_w/frame_h 分组，组内对齐
        detected = _group_align_zones(detected)

        if self._zones:
            reply = QMessageBox.question(
                self, "替换确认",
                f"已有 {len(self._zones)} 个区域，"
                f"检测到 {len(detected)} 个新区域。\n替换全部？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        self._zones = detected
        self._refresh_list()
        if self._zones:
            self._select_zone(0)

    def _clear_all_zones(self):
        """清空所有区域。"""
        if not self._zones:
            return
        reply = QMessageBox.question(
            self, "确认清空",
            f"确认删除全部 {len(self._zones)} 个区域？",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._zones.clear()
            self._sel = -1
            self._refresh_list()
            self._canvas.set_selected(-1)
            self._set_editor_enabled(False)

    # ── 选择 ──────────────────────────────────────────────
    def _select_zone(self, idx: int):
        if idx < 0 or idx >= len(self._zones):
            self._sel = -1
            self._canvas.set_selected(-1)
            self._set_editor_enabled(False)
            return
        self._sel = idx
        self._zone_list.blockSignals(True)
        self._zone_list.setCurrentRow(idx)
        self._zone_list.blockSignals(False)
        self._canvas.set_selected(idx)
        self._load_to_editor(self._zones[idx])

    def _on_list_row(self, row: int):
        self._select_zone(row)

    # ── 编辑器 ↔ zone 同步 ────────────────────────────────
    def _load_to_editor(self, z: _ZoneInfo):
        self._suppress = True
        self._name_edit.setText(z.name)
        self._x_sp.setValue(z.x)
        self._y_sp.setValue(z.y)
        self._w_sp.setValue(z.w)
        self._h_sp.setValue(z.h)
        self._fw_sp.setValue(z.frame_w)
        self._fh_sp.setValue(z.frame_h)
        self._suppress = False
        self._set_editor_enabled(True)
        self._update_info()

    def _on_param(self):
        if self._suppress:
            return
        idx = self._sel
        if idx < 0 or idx >= len(self._zones):
            return
        z = self._zones[idx]
        z.name    = self._name_edit.text().strip() or f"zone_{idx}"
        z.x       = self._x_sp.value()
        z.y       = self._y_sp.value()
        z.w       = self._w_sp.value()
        z.h       = self._h_sp.value()
        z.frame_w = self._fw_sp.value()
        z.frame_h = self._fh_sp.value()
        self._refresh_list_labels()
        self._canvas.set_zones(self._zones)
        self._update_info()

    def _update_info(self):
        idx = self._sel
        if idx < 0 or idx >= len(self._zones):
            self._info.setText("")
            return
        z = self._zones[idx]
        cols = z.frame_cols
        rows = z.frame_rows
        if rows <= 1:
            anim_text = f"动画 «{z.name}»: {cols} 帧"
        else:
            parts = [f"{rows} 行 × {cols} 列 = {z.total_frames} 帧"]
            for r in range(min(rows, 8)):
                parts.append(f"  行{r}: «{z.name}_row{r}» ({cols} 帧)")
            if rows > 8:
                parts.append(f"  …共 {rows} 行")
            anim_text = "\n".join(parts)
        self._info.setText(
            f"区域: ({z.x}, {z.y}) {z.w}×{z.h}\n"
            f"帧: {z.frame_w}×{z.frame_h}\n"
            f"{anim_text}")

    def _set_editor_enabled(self, on: bool):
        for w in (self._name_edit, self._x_sp, self._y_sp,
                  self._w_sp, self._h_sp, self._fw_sp, self._fh_sp):
            w.setEnabled(on)
        if not on:
            self._info.setText("在纹理上拖拽绘制区域，或在列表中选择已有区域。")

    # ── 列表管理 ──────────────────────────────────────────
    def _refresh_list(self):
        self._zone_list.blockSignals(True)
        self._zone_list.clear()
        for z in self._zones:
            self._zone_list.addItem(self._zone_label(z))
        self._zone_list.blockSignals(False)
        self._canvas.set_zones(self._zones)

    def _refresh_list_labels(self):
        for i, z in enumerate(self._zones):
            item = self._zone_list.item(i)
            if item:
                item.setText(self._zone_label(z))

    @staticmethod
    def _zone_label(z: _ZoneInfo) -> str:
        return f"{z.name}  ({z.w}×{z.h}, {z.frame_cols}×{z.frame_rows}帧)"

    def _delete_zone(self):
        idx = self._sel
        if idx < 0 or idx >= len(self._zones):
            return
        self._zones.pop(idx)
        self._sel = -1
        self._refresh_list()
        self._canvas.set_selected(-1)
        self._set_editor_enabled(False)
        if self._zones:
            self._select_zone(min(idx, len(self._zones) - 1))

    # ── 输出 ──────────────────────────────────────────────
    def get_result(self) -> Tuple[Dict, Dict]:
        """
        返回 (sprites, animations)。

        sprites = {
            "fairy_red_0": {"rect": [x,y,w,h], "center": [cx,cy]},
            ...
        }
        animations = {
            "fairy_red": {"frames": [...], "fps": 8, "loop": true},
            ...
        }
        zones 元数据也会嵌入 JSON 以便下次重新编辑。
        """
        sprites: Dict[str, dict] = {}
        animations: Dict[str, dict] = {}

        for z in self._zones:
            cols = z.frame_cols
            rows = z.frame_rows

            for r in range(rows):
                anim_name = z.name if rows <= 1 else f"{z.name}_row{r}"
                frame_names: List[str] = []

                for c in range(cols):
                    spr_name = f"{anim_name}_{c}"
                    rx = z.x + c * z.frame_w
                    ry = z.y + r * z.frame_h
                    sprites[spr_name] = {
                        "rect": [rx, ry, z.frame_w, z.frame_h],
                        "center": [z.frame_w // 2, z.frame_h // 2],
                    }
                    frame_names.append(spr_name)

                animations[anim_name] = {
                    "frames": frame_names,
                    "fps": 8,
                    "loop": True,
                }

        return sprites, animations

    def get_zones_meta(self) -> List[dict]:
        """返回区域元数据用于 JSON 持久化。"""
        return [
            {"name": z.name, "x": z.x, "y": z.y,
             "w": z.w, "h": z.h,
             "frame_w": z.frame_w, "frame_h": z.frame_h}
            for z in self._zones
        ]


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    window = EnemyAliasManager()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

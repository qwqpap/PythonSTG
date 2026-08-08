"""
弹幕别名管理器 v2 — Bullet Alias Manager

核心改进:
  - 每个弹幕类型独立的颜色→精灵映射（不再假设统一后缀）
  - 点击任意格子 → 弹出精灵选取器，可视化挑选
  - 缺失/错误的精灵一目了然
  - 保存到 assets/bullet_aliases.json，引擎运行时加载

使用:
    python tools/bullet_alias_manager.py
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.qt_compat.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QPushButton, QLineEdit, QScrollArea,
    QGridLayout, QDialog, QDialogButtonBox, QComboBox,
    QMessageBox, QStatusBar, QToolBar, QAction, QGroupBox,
    QFormLayout, QFrame, QInputDialog, QMenu, QSizePolicy
)
from src.qt_compat.QtCore import Qt, QSize, pyqtSignal
from src.qt_compat.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QBrush, QIcon

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.editor_common import (
    DARK_THEME, BULLET_IMAGE_DIR, BULLET_ALIASES_PATH, COLOR_CSS,
    SpriteEntry, PixmapCache, apply_dark_theme,
    load_all_bullet_sprites, load_bullet_aliases, save_bullet_aliases,
    generate_default_aliases, get_all_sprite_names, get_sprite_entry_map,
)


# ═══════════════════════════════════════════════════════════════
# SpriteCell — 别名网格中的单个格子
# ═══════════════════════════════════════════════════════════════

class SpriteCell(QFrame):
    """
    网格中的一个 (弹幕类型, 颜色) 格子。

    显示已分配的精灵缩略图，或"缺失"指示器。
    点击打开精灵选择器。
    """
    clicked = pyqtSignal(str, str)  # (bullet_type, color)

    CELL_SIZE = 54

    def __init__(self, bullet_type: str, color: str,
                 sprite_name: str = "", parent=None):
        super().__init__(parent)
        self.bullet_type = bullet_type
        self.color = color
        self.sprite_name = sprite_name
        self._pixmap: Optional[QPixmap] = None
        self._hover = False

        self.setFixedSize(self.CELL_SIZE, self.CELL_SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self._make_tooltip())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def set_sprite(self, sprite_name: str):
        self.sprite_name = sprite_name
        self._pixmap = None  # 强制重新获取
        self.setToolTip(self._make_tooltip())
        self.update()

    def _make_tooltip(self) -> str:
        if self.sprite_name:
            return f"{self.bullet_type} + {self.color}\n→ {self.sprite_name}"
        return f"{self.bullet_type} + {self.color}\n(未设置 — 点击分配)"

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        s = self.CELL_SIZE

        # 背景
        if self.sprite_name:
            # 已分配
            pm = self._get_pixmap()
            if pm and not pm.isNull():
                # 有效精灵
                bg = QColor(30, 35, 50)
                border = QColor(80, 180, 80) if not self._hover else QColor(120, 220, 120)
            else:
                # 有名称但精灵不存在
                bg = QColor(60, 40, 20)
                border = QColor(200, 150, 50) if not self._hover else QColor(240, 200, 80)
        else:
            # 未分配
            bg = QColor(40, 25, 25)
            border = QColor(100, 50, 50) if not self._hover else QColor(160, 80, 80)

        p.fillRect(0, 0, s, s, bg)
        p.setPen(QPen(border, 2 if self._hover else 1))
        p.drawRect(1, 1, s - 2, s - 2)

        if self.sprite_name:
            pm = self._get_pixmap()
            if pm and not pm.isNull():
                # 绘制精灵缩略图
                scaled = pm.scaled(s - 8, s - 8, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
                x = (s - scaled.width()) // 2
                y = (s - scaled.height()) // 2
                p.drawPixmap(x, y, scaled)
            else:
                # 精灵不存在
                p.setPen(QColor(220, 160, 50))
                p.setFont(QFont("Consolas", 9, QFont.Bold))
                p.drawText(0, 0, s, s, Qt.AlignCenter, "⚠")
        else:
            # 未分配
            p.setPen(QColor(120, 60, 60))
            p.setFont(QFont("Consolas", 14))
            p.drawText(0, 0, s, s, Qt.AlignCenter, "—")

        p.end()

    def _get_pixmap(self) -> Optional[QPixmap]:
        if self._pixmap is None and self.sprite_name:
            self._pixmap = PixmapCache.get_sprite_by_name(self.sprite_name)
        return self._pixmap

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.bullet_type, self.color)

    def _context_menu(self, pos):
        menu = QMenu(self)
        if self.sprite_name:
            clear_action = menu.addAction("清除分配")
            clear_action.triggered.connect(lambda: self.set_sprite(""))
        menu.exec(self.mapToGlobal(pos))


# ═══════════════════════════════════════════════════════════════
# SpritePickerDialog — 精灵选择对话框
# ═══════════════════════════════════════════════════════════════

class SpritePickerDialog(QDialog):
    """
    弹出式精灵选取器。

    显示所有可用的子弹精灵，支持搜索和图集过滤。
    点击精灵确认选择。
    """

    THUMB_SIZE = 48
    COLUMNS = 10

    def __init__(self, all_sprites: Dict[str, SpriteEntry],
                 current_sprite: str = "",
                 suggested_base: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择精灵")
        self.setMinimumSize(680, 520)
        self.resize(720, 560)

        self._all_sprites = all_sprites  # {name: SpriteEntry}
        self._selected_name = current_sprite
        self._suggested_base = suggested_base

        self._setup_ui()
        apply_dark_theme(self)
        self._populate()

        # 预选当前精灵
        if current_sprite:
            self._search.setText(current_sprite.rstrip("0123456789"))

    def selected_sprite(self) -> str:
        return self._selected_name

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 过滤栏
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("搜索:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("输入精灵名称过滤...")
        self._search.textChanged.connect(self._populate)
        filter_bar.addWidget(self._search, 1)

        filter_bar.addWidget(QLabel("图集:"))
        self._atlas_combo = QComboBox()
        self._atlas_combo.setMinimumWidth(120)
        self._atlas_combo.addItem("全部")
        atlases = sorted(set(e.atlas for e in self._all_sprites.values()))
        for a in atlases:
            self._atlas_combo.addItem(a)
        self._atlas_combo.currentTextChanged.connect(self._populate)
        filter_bar.addWidget(self._atlas_combo)
        layout.addLayout(filter_bar)

        # 精灵网格
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(3)
        self._scroll.setWidget(self._grid_container)
        layout.addWidget(self._scroll, 1)

        # 底栏: 预览 + 按钮
        bottom = QHBoxLayout()
        self._preview_label = QLabel()
        self._preview_label.setFixedSize(64, 64)
        self._preview_label.setStyleSheet("border: 1px solid #45475a; background: #181825;")
        self._preview_label.setAlignment(Qt.AlignCenter)
        bottom.addWidget(self._preview_label)

        self._name_label = QLabel("未选择")
        self._name_label.setFont(QFont("Consolas", 10))
        bottom.addWidget(self._name_label, 1)

        buttons = QDialogButtonBox()
        self._ok_btn = buttons.addButton("确定", QDialogButtonBox.AcceptRole)
        self._clear_btn = buttons.addButton("清除", QDialogButtonBox.ResetRole)
        buttons.addButton("取消", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._clear_btn.clicked.connect(self._clear_selection)
        bottom.addWidget(buttons)
        layout.addLayout(bottom)

    def _populate(self):
        # 清理旧内容
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        search = self._search.text().lower()
        atlas_filter = self._atlas_combo.currentText()
        if atlas_filter == "全部":
            atlas_filter = ""

        # 如果有建议的 base name，优先排序
        names = sorted(self._all_sprites.keys())
        if self._suggested_base:
            prefix = self._suggested_base.lower()
            names.sort(key=lambda n: (0 if n.lower().startswith(prefix) else 1, n))

        col = 0
        row = 0
        shown = 0
        for name in names:
            entry = self._all_sprites[name]
            if search and search not in name.lower():
                continue
            if atlas_filter and entry.atlas != atlas_filter:
                continue

            pm = PixmapCache.get_sprite(entry)
            btn = _SpriteThumbButton(name, pm, self.THUMB_SIZE,
                                     selected=(name == self._selected_name))
            btn.clicked_name.connect(self._on_sprite_clicked)
            self._grid_layout.addWidget(btn, row, col)

            col += 1
            if col >= self.COLUMNS:
                col = 0
                row += 1
            shown += 1

        # 填充空白
        if shown == 0:
            lbl = QLabel("无匹配精灵")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #585b70; font-size: 14px;")
            self._grid_layout.addWidget(lbl, 0, 0, 1, self.COLUMNS)

    def _on_sprite_clicked(self, name: str):
        self._selected_name = name
        self._name_label.setText(name)
        pm = PixmapCache.get_sprite_by_name(name)
        if pm and not pm.isNull():
            self._preview_label.setPixmap(
                pm.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._populate()  # 刷新选中状态

    def _clear_selection(self):
        self._selected_name = ""
        self._name_label.setText("(已清除)")
        self._preview_label.clear()
        self.accept()


class _SpriteThumbButton(QFrame):
    """精灵选取器中的缩略图按钮。"""
    clicked_name = pyqtSignal(str)

    def __init__(self, name: str, pixmap: Optional[QPixmap],
                 size: int, selected: bool = False, parent=None):
        super().__init__(parent)
        self.sprite_name = name
        self._pixmap = pixmap
        self._size = size
        self._selected = selected
        self._hover = False
        self.setFixedSize(size + 4, size + 16)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(name)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        # 背景
        if self._selected:
            p.fillRect(0, 0, w, h, QColor(50, 60, 90))
            p.setPen(QPen(QColor(130, 170, 255), 2))
        elif self._hover:
            p.fillRect(0, 0, w, h, QColor(45, 45, 60))
            p.setPen(QPen(QColor(100, 100, 130), 1))
        else:
            p.fillRect(0, 0, w, h, QColor(30, 30, 45))
            p.setPen(QPen(QColor(60, 60, 80), 1))
        p.drawRect(0, 0, w - 1, h - 1)

        # 精灵
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(self._size - 4, self._size - 4,
                                         Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)
            sx = (w - scaled.width()) // 2
            p.drawPixmap(sx, 2, scaled)

        # 名称
        p.setPen(QColor(180, 180, 200))
        p.setFont(QFont("Consolas", 6))
        p.drawText(0, self._size, w, 14, Qt.AlignHCenter | Qt.AlignTop,
                   self.sprite_name[-12:])  # 只显示末尾
        p.end()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked_name.emit(self.sprite_name)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked_name.emit(self.sprite_name)
            # 双击直接确认
            dialog = self.window()
            if isinstance(dialog, QDialog):
                dialog.accept()


# ═══════════════════════════════════════════════════════════════
# AliasGridPanel — 别名编辑主网格
# ═══════════════════════════════════════════════════════════════

class AliasGridPanel(QWidget):
    """
    别名编辑的核心: 弹幕类型(行) × 颜色(列) 的网格。

    每个格子是一个 SpriteCell，点击可以分配精灵。
    """
    cell_selected = pyqtSignal(str, str, str)  # (type, color, sprite_name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._types: List[str] = []
        self._colors: List[str] = []
        self._cells: Dict[Tuple[str, str], SpriteCell] = {}
        self._all_sprites: Dict[str, SpriteEntry] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(2)
        self._scroll.setWidget(self._grid_container)
        layout.addWidget(self._scroll)

    def set_sprites(self, sprites: Dict[str, SpriteEntry]):
        self._all_sprites = sprites

    def rebuild(self, mapping: Dict[str, Dict[str, str]],
                types: List[str], colors: List[str]):
        """根据映射数据重建整个网格。"""
        self._types = types
        self._colors = colors
        self._cells.clear()

        # 清理
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not types or not colors:
            return

        # 列头 (颜色)
        corner = QLabel("")
        corner.setFixedSize(90, 28)
        self._grid_layout.addWidget(corner, 0, 0)

        for ci, color in enumerate(colors):
            lbl = QLabel(color)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Consolas", 8, QFont.Bold))
            css_color = COLOR_CSS.get(color, "#ccc")
            lbl.setStyleSheet(f"color: {css_color}; padding: 2px;")
            lbl.setFixedHeight(28)
            self._grid_layout.addWidget(lbl, 0, ci + 1)

        # 行
        for ri, btype in enumerate(types):
            # 行头 (类型名)
            type_lbl = QLabel(btype)
            type_lbl.setFont(QFont("Consolas", 9, QFont.Bold))
            type_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            type_lbl.setFixedWidth(90)
            type_lbl.setStyleSheet("padding-right: 6px;")
            self._grid_layout.addWidget(type_lbl, ri + 1, 0)

            type_mapping = mapping.get(btype, {})
            for ci, color in enumerate(colors):
                sprite_name = type_mapping.get(color, "")
                cell = SpriteCell(btype, color, sprite_name)
                cell.clicked.connect(self._on_cell_clicked)
                self._grid_layout.addWidget(cell, ri + 1, ci + 1)
                self._cells[(btype, color)] = cell

    def get_mapping(self) -> Dict[str, Dict[str, str]]:
        """从网格当前状态提取映射。"""
        mapping = {}
        for (btype, color), cell in self._cells.items():
            if cell.sprite_name:
                if btype not in mapping:
                    mapping[btype] = {}
                mapping[btype][color] = cell.sprite_name
        return mapping

    def get_types(self) -> List[str]:
        return list(self._types)

    def get_colors(self) -> List[str]:
        return list(self._colors)

    def _on_cell_clicked(self, btype: str, color: str):
        cell = self._cells.get((btype, color))
        if not cell:
            return

        # 获得建议的基名
        # 例如 btype="ball_m", 映射中其他颜色用的是 ball_mid → 建议 "ball_mid"
        suggested_base = self._guess_base_name(btype)

        dialog = SpritePickerDialog(
            all_sprites=self._all_sprites,
            current_sprite=cell.sprite_name,
            suggested_base=suggested_base,
            parent=self.window()
        )
        if dialog.exec() == QDialog.Accepted:
            new_name = dialog.selected_sprite()
            cell.set_sprite(new_name)
            self.cell_selected.emit(btype, color, new_name)

    def _guess_base_name(self, btype: str) -> str:
        """猜测某个弹幕类型对应的精灵基名（用于 picker 预排序）。"""
        type_map = self.get_mapping()
        if btype in type_map:
            # 从已有映射中推测
            for sprite_name in type_map[btype].values():
                # ball_mid1 → ball_mid
                base = sprite_name.rstrip("0123456789")
                if base:
                    return base
        return ""

    def add_type(self, name: str):
        if name and name not in self._types:
            self._types.append(name)
            self.rebuild(self.get_mapping(), self._types, self._colors)

    def remove_type(self, name: str):
        if name in self._types:
            self._types.remove(name)
            self.rebuild(self.get_mapping(), self._types, self._colors)

    def add_color(self, name: str):
        if name and name not in self._colors:
            self._colors.append(name)
            self.rebuild(self.get_mapping(), self._types, self._colors)

    def remove_color(self, name: str):
        if name in self._colors:
            self._colors.remove(name)
            self.rebuild(self.get_mapping(), self._types, self._colors)


# ═══════════════════════════════════════════════════════════════
# InfoPanel — 右侧信息面板
# ═══════════════════════════════════════════════════════════════

class InfoPanel(QWidget):
    """显示选中格子的详情、统计、验证结果。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 统计
        stats_group = QGroupBox("统计")
        stats_layout = QFormLayout()
        self._lbl_types = QLabel("0")
        self._lbl_colors = QLabel("0")
        self._lbl_assigned = QLabel("0")
        self._lbl_missing = QLabel("0")
        self._lbl_invalid = QLabel("0")
        stats_layout.addRow("弹幕类型:", self._lbl_types)
        stats_layout.addRow("颜色数:", self._lbl_colors)
        stats_layout.addRow("已分配:", self._lbl_assigned)
        stats_layout.addRow("未分配:", self._lbl_missing)
        stats_layout.addRow("精灵不存在:", self._lbl_invalid)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # 选中格子详情
        detail_group = QGroupBox("选中详情")
        detail_layout = QVBoxLayout()
        self._detail_preview = QLabel()
        self._detail_preview.setFixedSize(128, 128)
        self._detail_preview.setAlignment(Qt.AlignCenter)
        self._detail_preview.setStyleSheet("background: #181825; border: 1px solid #313244;")
        detail_layout.addWidget(self._detail_preview, 0, Qt.AlignCenter)
        self._detail_text = QLabel("点击格子查看详情")
        self._detail_text.setFont(QFont("Consolas", 9))
        self._detail_text.setWordWrap(True)
        detail_layout.addWidget(self._detail_text)
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)

        # 操作说明
        help_group = QGroupBox("操作")
        help_layout = QVBoxLayout()
        help_layout.addWidget(QLabel("• 左键点击格子：分配精灵"))
        help_layout.addWidget(QLabel("• 右键点击格子：清除分配"))
        help_layout.addWidget(QLabel("• 双击精灵选取器：快速确认"))
        help_layout.addWidget(QLabel("• Ctrl+S：保存"))
        help_layout.addWidget(QLabel("• F5：刷新"))
        help_group.setLayout(help_layout)
        layout.addWidget(help_group)

        layout.addStretch()

    def update_stats(self, types: int, colors: int,
                     assigned: int, missing: int, invalid: int):
        self._lbl_types.setText(str(types))
        self._lbl_colors.setText(str(colors))
        self._lbl_assigned.setText(f"<b style='color:#a6e3a1'>{assigned}</b>")
        self._lbl_missing.setText(
            f"<b style='color:#f38ba8'>{missing}</b>" if missing
            else "<b style='color:#a6e3a1'>0</b>")
        self._lbl_invalid.setText(
            f"<b style='color:#fab387'>{invalid}</b>" if invalid
            else "<b style='color:#a6e3a1'>0</b>")

    def show_detail(self, btype: str, color: str, sprite_name: str,
                    entry: Optional[SpriteEntry]):
        if not sprite_name:
            self._detail_preview.clear()
            self._detail_preview.setText("—")
            self._detail_text.setText(f"{btype} + {color}\n未分配")
            return

        pm = PixmapCache.get_sprite_by_name(sprite_name)
        if pm and not pm.isNull():
            self._detail_preview.setPixmap(
                pm.scaled(120, 120, Qt.KeepAspectRatio, Qt.FastTransformation))
        else:
            self._detail_preview.clear()
            self._detail_preview.setText("⚠ 不存在")

        info_lines = [
            f"<b>{btype}</b> + <b>{color}</b>",
            f"精灵: <code>{sprite_name}</code>",
        ]
        if entry:
            info_lines.append(f"图集: {entry.atlas}")
            info_lines.append(f"Rect: {entry.rect}")
            info_lines.append(f"半径: {entry.radius}")
        elif sprite_name:
            info_lines.append("<span style='color:#fab387'>⚠ 精灵不存在</span>")
        self._detail_text.setText("<br>".join(info_lines))


# ═══════════════════════════════════════════════════════════════
# BulletAliasManager — 主窗口
# ═══════════════════════════════════════════════════════════════

class BulletAliasManager(QMainWindow):
    """弹幕别名管理器主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("弹幕别名管理器 v2 — Bullet Alias Manager")
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)

        self._atlases: Dict[str, List[SpriteEntry]] = {}
        self._sprite_map: Dict[str, SpriteEntry] = {}
        self._mapping: Dict[str, Dict[str, str]] = {}
        self._saved_mapping: Dict[str, Dict[str, str]] = {}

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        apply_dark_theme(self)
        self._load_data()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)

        # 左: 别名网格 (主编辑区)
        self._grid_panel = AliasGridPanel()
        self._grid_panel.cell_selected.connect(self._on_cell_selected)
        splitter.addWidget(self._grid_panel)

        # 右: 信息面板
        self._info_panel = InfoPanel()
        self._info_panel.setMaximumWidth(300)
        splitter.addWidget(self._info_panel)

        splitter.setSizes([850, 280])
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

        reset_action = QAction("重置为自动检测", self)
        reset_action.triggered.connect(self._reset_to_defaults)
        file_menu.addAction(reset_action)

        file_menu.addSeparator()

        quit_action = QAction("退出 (&Q)", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = mb.addMenu("编辑(&E)")

        add_type_action = QAction("添加弹幕类型 (&T)", self)
        add_type_action.triggered.connect(self._add_type)
        edit_menu.addAction(add_type_action)

        remove_type_action = QAction("删除弹幕类型", self)
        remove_type_action.triggered.connect(self._remove_type)
        edit_menu.addAction(remove_type_action)

        edit_menu.addSeparator()

        add_color_action = QAction("添加颜色 (&C)", self)
        add_color_action.triggered.connect(self._add_color)
        edit_menu.addAction(add_color_action)

        remove_color_action = QAction("删除颜色", self)
        remove_color_action.triggered.connect(self._remove_color)
        edit_menu.addAction(remove_color_action)

        view_menu = mb.addMenu("视图(&V)")
        refresh_action = QAction("刷新 (&F)", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._refresh)
        view_menu.addAction(refresh_action)

    def _setup_toolbar(self):
        toolbar = QToolBar("工具栏")
        self.addToolBar(toolbar)

        save_btn = QPushButton("💾 保存")
        save_btn.setToolTip("保存到 bullet_aliases.json (Ctrl+S)")
        save_btn.clicked.connect(self._save)
        toolbar.addWidget(save_btn)

        toolbar.addSeparator()

        add_type_btn = QPushButton("+ 类型")
        add_type_btn.setToolTip("添加新的弹幕类型别名")
        add_type_btn.clicked.connect(self._add_type)
        toolbar.addWidget(add_type_btn)

        add_color_btn = QPushButton("+ 颜色")
        add_color_btn.setToolTip("添加新的颜色")
        add_color_btn.clicked.connect(self._add_color)
        toolbar.addWidget(add_color_btn)

        toolbar.addSeparator()

        validate_btn = QPushButton("✅ 验证")
        validate_btn.setToolTip("检查所有分配是否指向有效精灵")
        validate_btn.clicked.connect(self._validate)
        toolbar.addWidget(validate_btn)

        toolbar.addSeparator()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setToolTip("重新加载精灵数据 (F5)")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)

    # ───── 数据加载 ─────

    def _load_data(self):
        # 加载精灵
        self._atlases = load_all_bullet_sprites(BULLET_IMAGE_DIR)
        PixmapCache.ensure_all_loaded(self._atlases)
        self._sprite_map = get_sprite_entry_map(self._atlases)

        # 加载别名 (或自动生成)
        self._mapping = load_bullet_aliases(BULLET_ALIASES_PATH)
        if not self._mapping:
            self._mapping = generate_default_aliases(self._atlases)
            self._status.showMessage("未找到别名配置，已自动生成默认映射", 5000)
        else:
            self._status.showMessage(
                f"已加载 {sum(len(v) for v in self._mapping.values())} 个别名", 5000)

        self._saved_mapping = self._deep_copy_mapping(self._mapping)

        # 构建类型和颜色列表
        types = list(self._mapping.keys())
        colors = self._collect_all_colors()

        # 设置网格
        self._grid_panel.set_sprites(self._sprite_map)
        self._grid_panel.rebuild(self._mapping, types, colors)
        self._update_stats()

    def _collect_all_colors(self) -> List[str]:
        """从映射中收集所有颜色，保持合理排序。"""
        PREFERRED_ORDER = [
            "red", "blue", "green", "yellow", "purple", "white",
            "darkblue", "orange", "cyan", "pink",
            "darkred", "darkgreen", "darkpurple", "darkorange",
            "darkyellow", "darkcyan", "black",
        ]
        found = set()
        for type_map in self._mapping.values():
            found.update(type_map.keys())
        ordered = [c for c in PREFERRED_ORDER if c in found]
        extras = sorted(found - set(PREFERRED_ORDER))
        return ordered + extras

    def _refresh(self):
        """刷新网格（保留当前编辑状态）。"""
        current = self._grid_panel.get_mapping()
        types = self._grid_panel.get_types()
        colors = self._grid_panel.get_colors()

        # 重加载精灵
        self._atlases = load_all_bullet_sprites(BULLET_IMAGE_DIR)
        PixmapCache.clear()
        PixmapCache.ensure_all_loaded(self._atlases)
        self._sprite_map = get_sprite_entry_map(self._atlases)

        self._grid_panel.set_sprites(self._sprite_map)
        self._grid_panel.rebuild(current, types, colors)
        self._update_stats()
        self._status.showMessage("已刷新", 3000)

    # ───── 统计 ─────

    def _update_stats(self):
        mapping = self._grid_panel.get_mapping()
        types = self._grid_panel.get_types()
        colors = self._grid_panel.get_colors()
        sprite_names = get_all_sprite_names(self._atlases)

        total = len(types) * len(colors)
        assigned = 0
        invalid = 0
        for btype in types:
            for color in colors:
                sn = mapping.get(btype, {}).get(color, "")
                if sn:
                    assigned += 1
                    if sn not in sprite_names:
                        invalid += 1

        self._info_panel.update_stats(
            len(types), len(colors), assigned, total - assigned, invalid)

    # ───── 格子选中 ─────

    def _on_cell_selected(self, btype: str, color: str, sprite_name: str):
        entry = self._sprite_map.get(sprite_name)
        self._info_panel.show_detail(btype, color, sprite_name, entry)
        self._update_stats()

    # ───── 保存 ─────

    def _save(self):
        mapping = self._grid_panel.get_mapping()
        try:
            save_bullet_aliases(mapping, BULLET_ALIASES_PATH)
            self._saved_mapping = self._deep_copy_mapping(mapping)
            self._status.showMessage(
                f"✅ 已保存到 {BULLET_ALIASES_PATH.name}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入文件失败:\n{e}")

    # ───── 编辑操作 ─────

    def _add_type(self):
        name, ok = QInputDialog.getText(self, "添加弹幕类型",
                                        "新弹幕类型别名 (如 grain_a):")
        if ok and name.strip():
            self._grid_panel.add_type(name.strip())
            self._update_stats()

    def _remove_type(self):
        types = self._grid_panel.get_types()
        if not types:
            return
        name, ok = QInputDialog.getItem(self, "删除弹幕类型",
                                        "选择要删除的类型:", types, 0, False)
        if ok and name:
            self._grid_panel.remove_type(name)
            self._update_stats()

    def _add_color(self):
        name, ok = QInputDialog.getText(self, "添加颜色",
                                        "新颜色名 (如 magenta):")
        if ok and name.strip():
            self._grid_panel.add_color(name.strip())
            self._update_stats()

    def _remove_color(self):
        colors = self._grid_panel.get_colors()
        if not colors:
            return
        name, ok = QInputDialog.getItem(self, "删除颜色",
                                        "选择要删除的颜色:", colors, 0, False)
        if ok and name:
            self._grid_panel.remove_color(name)
            self._update_stats()

    def _validate(self):
        mapping = self._grid_panel.get_mapping()
        types = self._grid_panel.get_types()
        colors = self._grid_panel.get_colors()
        sprite_names = get_all_sprite_names(self._atlases)

        issues = []
        ok_count = 0
        for btype in types:
            for color in colors:
                sn = mapping.get(btype, {}).get(color, "")
                if not sn:
                    issues.append(f"  ⬜ {btype} + {color} → 未分配")
                elif sn not in sprite_names:
                    issues.append(f"  ⚠️ {btype} + {color} → {sn} (不存在)")
                else:
                    ok_count += 1

        total = len(types) * len(colors)
        if ok_count == total:
            QMessageBox.information(self, "验证通过",
                                    f"✅ 全部 {total} 个组合均有效！")
        else:
            msg = (f"共 {total} 个组合，{ok_count} 个有效，"
                   f"{total - ok_count} 个需要修复：\n\n")
            msg += "\n".join(issues[:60])
            if len(issues) > 60:
                msg += f"\n... 还有 {len(issues) - 60} 个"
            QMessageBox.warning(self, "验证结果", msg)

    def _reset_to_defaults(self):
        reply = QMessageBox.question(
            self, "重置别名",
            "将丢弃当前所有映射，根据精灵名自动检测重新生成。确认？",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._mapping = generate_default_aliases(self._atlases)
        types = list(self._mapping.keys())
        colors = self._collect_all_colors()
        self._grid_panel.rebuild(self._mapping, types, colors)
        self._update_stats()
        self._status.showMessage("已重置为自动检测映射", 5000)

    # ───── 工具方法 ─────

    @staticmethod
    def _deep_copy_mapping(m: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
        return {k: dict(v) for k, v in m.items()}

    def _is_dirty(self) -> bool:
        return self._grid_panel.get_mapping() != self._saved_mapping

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
# 入口
# ═══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    window = BulletAliasManager()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

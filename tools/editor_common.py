"""
编辑器公共模块 - pystg 可视化工具链共享基础

提供:
  - 项目路径常量
  - 统一暗色主题 (Catppuccin Mocha)
  - 精灵数据加载 (从 bullet JSON configs)
  - QPixmap 缓存 (纹理 & 裁剪精灵)
  - 弹幕别名 JSON 读写
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PyQt5.QtGui import QPixmap, QColor, QFont, QPainter, QPen
from PyQt5.QtCore import Qt, QRect

# ═══════════════════════════════════════════════════════════════
# 路径常量
# ═══════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSET_ROOT = PROJECT_ROOT / "assets"
BULLET_IMAGE_DIR = ASSET_ROOT / "images" / "bullet"
BULLET_ALIASES_PATH = ASSET_ROOT / "bullet_aliases.json"
CONTEXT_PY_PATH = PROJECT_ROOT / "src" / "game" / "stage" / "context.py"
PLAYERS_ROOT = ASSET_ROOT / "players"


# ═══════════════════════════════════════════════════════════════
# 暗色主题 (Catppuccin Mocha)
# ═══════════════════════════════════════════════════════════════

DARK_THEME = """
QMainWindow, QDialog { background: #1e1e2e; color: #cdd6f4; }
QWidget { background: #1e1e2e; color: #cdd6f4; }
QMenuBar { background: #181825; color: #cdd6f4; }
QMenuBar::item:selected { background: #313244; }
QMenu { background: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a; }
QMenu::item:selected { background: #313244; }
QToolBar { background: #181825; border-bottom: 1px solid #313244; spacing: 6px; }
QPushButton {
    background: #313244; color: #cdd6f4; border: 1px solid #45475a;
    padding: 4px 12px; border-radius: 4px;
}
QPushButton:hover { background: #45475a; }
QPushButton:pressed { background: #585b70; }
QPushButton:disabled { background: #1e1e2e; color: #585b70; border-color: #313244; }
QTableWidget, QTreeWidget, QListWidget {
    background: #181825; alternate-background-color: #1e1e30;
    color: #cdd6f4; gridline-color: #313244; border: 1px solid #313244;
}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {
    background: #45475a;
}
QTreeWidget::item:hover { background: #313244; }
QHeaderView::section {
    background: #313244; color: #cdd6f4; border: 1px solid #45475a; padding: 4px;
}
QTabWidget::pane { border: 1px solid #313244; }
QTabBar::tab {
    background: #181825; color: #a6adc8; padding: 6px 16px;
    border: 1px solid #313244; border-bottom: none;
}
QTabBar::tab:selected { background: #1e1e2e; color: #cdd6f4; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #181825; color: #cdd6f4; border: 1px solid #45475a;
    padding: 4px; border-radius: 3px;
}
QScrollArea { border: none; }
QSplitter::handle { background: #313244; width: 3px; }
QStatusBar { background: #181825; color: #a6adc8; }
QLabel { background: transparent; }
QGroupBox {
    border: 1px solid #313244; margin-top: 12px; padding-top: 12px;
    color: #89b4fa; font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QScrollBar:vertical {
    background: #181825; width: 10px; border: none;
}
QScrollBar::handle:vertical {
    background: #45475a; min-height: 20px; border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #181825; height: 10px; border: none;
}
QScrollBar::handle:horizontal {
    background: #45475a; min-width: 20px; border-radius: 4px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""

# 颜色的 CSS 表示
COLOR_CSS = {
    "red": "#ff4444", "blue": "#4488ff", "green": "#44cc44",
    "yellow": "#ffcc00", "purple": "#cc44ff", "white": "#eeeeee",
    "darkblue": "#2244aa", "orange": "#ff8800", "cyan": "#00cccc",
    "pink": "#ff88cc",
}


def apply_dark_theme(widget):
    """应用暗色主题到 QWidget。"""
    widget.setStyleSheet(DARK_THEME)


# ═══════════════════════════════════════════════════════════════
# 精灵数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class SpriteEntry:
    """一个精灵条目（来自 bullet JSON 配置）。"""
    name: str
    atlas: str                          # JSON 文件名（不含扩展名）
    texture_path: str                   # 纹理 PNG 的完整路径
    rect: Tuple[int, int, int, int]     # (x, y, w, h)
    center: Tuple[float, float] = (0, 0)
    radius: float = 0
    rotate: bool = False


def load_all_bullet_sprites(bullet_dir: Path = BULLET_IMAGE_DIR
                            ) -> Dict[str, List[SpriteEntry]]:
    """
    加载所有子弹 JSON 配置中的精灵。
    
    Returns:
        {atlas_name: [SpriteEntry, ...]}
    """
    atlases: Dict[str, List[SpriteEntry]] = {}

    if not bullet_dir.is_dir():
        return atlases

    for json_path in sorted(bullet_dir.glob("*.json")):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        atlas_name = json_path.stem
        image_filename = (data.get("__image_filename")
                          or data.get("texture") or "")
        if not image_filename:
            image_filename = atlas_name + ".png"
        texture_path = str(bullet_dir / image_filename)

        entries: List[SpriteEntry] = []
        for spr_name, spr_info in data.get("sprites", {}).items():
            entries.append(SpriteEntry(
                name=spr_name,
                atlas=atlas_name,
                texture_path=texture_path,
                rect=tuple(spr_info.get("rect", [0, 0, 16, 16])),
                center=tuple(spr_info.get("center", [0, 0])),
                radius=spr_info.get("radius", 0),
                rotate=spr_info.get("rotate", False),
            ))
        atlases[atlas_name] = entries

    return atlases


# ═══════════════════════════════════════════════════════════════
# QPixmap 缓存
# ═══════════════════════════════════════════════════════════════

class PixmapCache:
    """
    全局 QPixmap 缓存（纹理图集 + 裁剪精灵）。
    
    必须在 QApplication 创建后使用。
    """
    _textures: Dict[str, QPixmap] = {}
    _sprites: Dict[str, QPixmap] = {}

    @classmethod
    def get_texture(cls, path: str) -> Optional[QPixmap]:
        if path in cls._textures:
            return cls._textures[path]
        if not os.path.exists(path):
            return None
        try:
            pm = QPixmap(path)
            if pm.isNull():
                return None
            cls._textures[path] = pm
            return pm
        except Exception:
            return None

    @classmethod
    def get_sprite(cls, entry: SpriteEntry) -> Optional[QPixmap]:
        if entry.name in cls._sprites:
            return cls._sprites[entry.name]
        tex = cls.get_texture(entry.texture_path)
        if tex is None:
            return None
        x, y, w, h = entry.rect
        if w <= 0 or h <= 0:
            return None
        pm = tex.copy(x, y, w, h)
        cls._sprites[entry.name] = pm
        return pm

    @classmethod
    def get_sprite_by_name(cls, name: str) -> Optional[QPixmap]:
        return cls._sprites.get(name)

    @classmethod
    def ensure_all_loaded(cls, atlases: Dict[str, List[SpriteEntry]]):
        """预加载所有精灵到缓存。"""
        for entries in atlases.values():
            for entry in entries:
                cls.get_sprite(entry)

    @classmethod
    def clear(cls):
        cls._textures.clear()
        cls._sprites.clear()

    @classmethod
    def make_placeholder(cls, size: int = 32, text: str = "?") -> QPixmap:
        """创建一个占位符精灵。"""
        pm = QPixmap(size, size)
        pm.fill(QColor(60, 20, 20))
        p = QPainter(pm)
        p.setPen(QPen(QColor(180, 60, 60)))
        p.drawRect(0, 0, size - 1, size - 1)
        p.setPen(QColor(180, 60, 60))
        p.setFont(QFont("Consolas", max(8, size // 4)))
        p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, text)
        p.end()
        return pm


# ═══════════════════════════════════════════════════════════════
# 弹幕别名 JSON 读写
# ═══════════════════════════════════════════════════════════════

def load_bullet_aliases(path: Path = BULLET_ALIASES_PATH
                        ) -> Dict[str, Dict[str, str]]:
    """
    读取弹幕别名配置。
    
    Returns:
        {bullet_type: {color: sprite_name}}
    """
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("mapping", {})
    except Exception:
        return {}


def save_bullet_aliases(mapping: Dict[str, Dict[str, str]],
                        path: Path = BULLET_ALIASES_PATH):
    """
    保存弹幕别名配置到 JSON。
    
    格式:
        {
          "version": "1.0",
          "mapping": {
            "ball_m": {"red": "ball_mid1", "blue": "ball_mid2", ...},
            ...
          }
        }
    """
    data = {"version": "1.0", "mapping": mapping}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def generate_default_aliases(atlases: Dict[str, List[SpriteEntry]]
                             ) -> Dict[str, Dict[str, str]]:
    """
    根据已有精灵自动生成初始别名映射。
    
    逻辑: 对每个 base_name (如 ball_mid), 找出它有几个数字变体,
    然后为已知颜色名分配尽可能多的后缀。
    """
    # 收集所有精灵名
    all_sprites = set()
    for entries in atlases.values():
        for e in entries:
            all_sprites.add(e.name)

    # 预定义别名
    ALIAS_DEFS = [
        ("ball_s", "ball_small"),
        ("ball_m", "ball_mid"),
        ("ball_l", "ball_huge"),
        ("knife", "knife"),
        ("star_s", "star_small"),
        ("star_l", "star_big"),
        ("arrow_s", "arrow_small"),
        ("arrow_m", "arrow_mid"),
        ("arrow_l", "arrow_big"),
        ("square", "square"),
        ("butterfly", "butterfly"),
        ("ellipse", "ellipse"),
        ("kite", "kite"),
        ("heart", "heart"),
        ("grain_a", "grain_a"),
        ("grain_b", "grain_b"),
        ("grain_c", "grain_c"),
        ("gun", "gun_bullet"),
        ("mildew", "mildew"),
        ("ball_light", "ball_light"),
        ("silence", "silence"),
    ]

    # 8色和16色的标准颜色顺序（LuaSTG 约定）
    COLORS_8 = ["red", "blue", "green", "purple", "orange", "darkblue", "white", "yellow"]
    COLORS_16 = [
        "red", "darkred", "blue", "darkblue",
        "green", "darkgreen", "purple", "darkpurple",
        "orange", "darkorange", "yellow", "darkyellow",
        "cyan", "darkcyan", "white", "black",
    ]

    mapping: Dict[str, Dict[str, str]] = {}

    for alias, base in ALIAS_DEFS:
        # 检测这个 base 有多少变体
        variants = {}
        for suffix in range(0, 20):
            sprite_name = f"{base}{suffix}"
            if sprite_name in all_sprites:
                variants[suffix] = sprite_name

        if not variants:
            continue

        max_suffix = max(variants.keys())
        colors = COLORS_8 if max_suffix <= 8 else COLORS_16

        type_map = {}
        for i, color in enumerate(colors):
            idx = i + 1  # 后缀从1开始
            sprite_name = f"{base}{idx}"
            if sprite_name in all_sprites:
                type_map[color] = sprite_name

        if type_map:
            mapping[alias] = type_map

    return mapping


def get_all_sprite_names(atlases: Dict[str, List[SpriteEntry]]) -> set:
    """获取所有已加载精灵名称的集合。"""
    names = set()
    for entries in atlases.values():
        for e in entries:
            names.add(e.name)
    return names


def get_sprite_entry_map(atlases: Dict[str, List[SpriteEntry]]
                         ) -> Dict[str, SpriteEntry]:
    """获取 {sprite_name: SpriteEntry} 映射。"""
    result = {}
    for entries in atlases.values():
        for e in entries:
            result[e.name] = e
    return result

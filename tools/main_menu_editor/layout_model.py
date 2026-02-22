"""
主菜单布局数据模型

封装 default、load、save，供编辑器使用。
"""

import os
import sys

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root not in sys.path:
    sys.path.insert(0, root)

from src.ui.main_menu_layout import default_layout as _default_layout
from src.ui.main_menu_layout import load_layout as _load_layout
from src.ui.main_menu_layout import save_layout as _save_layout

DEFAULT_LAYOUT_PATH = os.path.join(root, "assets", "ui", "main_menu_layout.json")


def get_default_path() -> str:
    return DEFAULT_LAYOUT_PATH


def default_layout():
    return _default_layout()


def load(path=None):
    return _load_layout(path or DEFAULT_LAYOUT_PATH)


def save(layout, path=None):
    return _save_layout(path or DEFAULT_LAYOUT_PATH, layout)


# Aliases for editor_main imports
load_layout = load
save_layout = save

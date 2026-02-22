"""
UI模块 - 游戏界面渲染

包含:
- BitmapFont: HGE格式位图字体
- HUD: 游戏信息显示（分数、生命、Power等）
- UIRenderer: UI元素的OpenGL渲染器
- FontAtlas: freetype-py 字形图集
- UINode / UITree: 统一 UI 组件树模型
"""

from .bitmap_font import BitmapFont
from .hud import HUD
from .ui_renderer import UIRenderer
from .font_atlas import FontAtlas
from .components import UINode, TextNode, RectNode, BarNode, ImageNode, PanelNode
from .ui_tree import UITree

__all__ = [
    'BitmapFont', 'HUD', 'UIRenderer',
    'FontAtlas',
    'UINode', 'TextNode', 'RectNode', 'BarNode', 'ImageNode', 'PanelNode',
    'UITree',
]

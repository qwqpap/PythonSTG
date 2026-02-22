"""
主菜单渲染器

纯文字 + 背景，无素材依赖。
使用 FontRenderer → SoftwareSurface → GL texture → quad 方式渲染。
支持从 JSON 布局配置渲染 (render_from_layout)。
"""

import moderngl
import numpy as np
import os
from typing import Dict, Any, Optional

from ..core.image_loader import SoftwareSurface, FontRenderer
from .main_menu_layout import default_layout


class MainMenuRenderer:
    """主菜单渲染器（ModernGL）"""

    def __init__(self, ctx: moderngl.Context, screen_width: int, screen_height: int):
        self.ctx = ctx
        self.screen_width = screen_width
        self.screen_height = screen_height

        # 字体路径
        font_path = os.path.join("assets", "fonts", "SourceHanSansCN-Bold.otf")
        if not os.path.exists(font_path):
            font_path = os.path.join("assets", "fonts", "wqy-microhei-mono.ttf")
        if not os.path.exists(font_path):
            font_path = None
        self._font_path = font_path

        # 字体缓存: size -> FontRenderer
        self._font_cache: Dict[int, FontRenderer] = {}

        # GL shader（与 LoadingScreenRenderer 相同）
        vertex_shader = """
        #version 330
        uniform vec2 u_screen_size;
        in vec2 in_position;
        in vec2 in_uv;
        out vec2 v_uv;
        void main() {
            vec2 ndc = (in_position / u_screen_size) * 2.0 - 1.0;
            ndc.y = -ndc.y;
            gl_Position = vec4(ndc, 0.0, 1.0);
            v_uv = in_uv;
        }
        """
        fragment_shader = """
        #version 330
        uniform sampler2D u_texture;
        in vec2 v_uv;
        out vec4 f_color;
        void main() {
            f_color = texture(u_texture, v_uv);
        }
        """
        self.program = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        self.program['u_texture'].value = 0
        self.program['u_screen_size'].value = (float(screen_width), float(screen_height))

        self.vbo = self.ctx.buffer(reserve=6 * 4 * 4)
        self.vao = self.ctx.vertex_array(
            self.program,
            [(self.vbo, '2f 2f', 'in_position', 'in_uv')]
        )
        self._texture = None

    def _get_font(self, size: int) -> FontRenderer:
        """按字号获取字体，带缓存。"""
        if size not in self._font_cache:
            self._font_cache[size] = FontRenderer(self._font_path, size)
        return self._font_cache[size]

    def render(self, selected_index: int = 0, layout: Optional[Dict[str, Any]] = None):
        """
        渲染主菜单

        Args:
            selected_index: 当前选中的菜单项索引（0=开始游戏, 1=退出）
            layout: 布局配置 dict，为 None 时使用 default_layout()
        """
        if layout is None:
            layout = default_layout()
        surface = self._render_to_surface(layout, selected_index)
        self._upload_texture(surface)
        self._draw_fullscreen_quad()

    def render_from_layout(self, layout: Dict[str, Any], selected_index: int = 0):
        """
        从 layout 配置渲染主菜单。供编辑器或自定义布局使用。

        Args:
            layout: 布局配置 dict（见 main_menu_layout.default_layout）
            selected_index: 当前选中的菜单项索引
        """
        self.render(selected_index=selected_index, layout=layout)

    def _render_to_surface(self, layout: Dict[str, Any], selected_index: int) -> SoftwareSurface:
        sw, sh = self.screen_width, self.screen_height
        surface = SoftwareSurface(sw, sh)

        bg = layout.get("bg_gradient", {"top": [12, 8, 28], "bottom": [20, 20, 44]})
        top = bg.get("top", [12, 8, 28])
        bot = bg.get("bottom", [20, 20, 44])
        for y in range(sh):
            t = y / sh
            r = int(top[0] + (bot[0] - top[0]) * t)
            g = int(top[1] + (bot[1] - top[1]) * t)
            b = int(top[2] + (bot[2] - top[2]) * t)
            surface.draw_line((r, g, b), (0, y), (sw, y))

        center_x = sw // 2
        opt_colors = layout.get("option_colors", {"normal": [160, 160, 180], "selected": [255, 255, 200]})
        col_norm = tuple(opt_colors.get("normal", [160, 160, 180]))
        col_sel = tuple(opt_colors.get("selected", [255, 255, 200]))

        # 标题
        title_cfg = layout.get("title", {"text": "弹幕游戏", "font_size": 56, "color": [220, 220, 255], "y_ratio": 0.25})
        title_text = title_cfg.get("text", "弹幕游戏")
        title_size = int(title_cfg.get("font_size", 56))
        title_color = tuple(title_cfg.get("color", [220, 220, 255]))
        y_ratio = float(title_cfg.get("y_ratio", 0.25))
        y = int(sh * y_ratio)
        font_title = self._get_font(title_size)
        s_title = font_title.render(title_text, True, title_color)
        surface.blit(s_title, (center_x - s_title.get_width() // 2, y))
        y += s_title.get_height() + 60

        # 菜单项
        options = layout.get("options", [{"text": "开始游戏"}, {"text": "退出"}])
        option_spacing = int(layout.get("option_spacing", 48))
        font_option = self._get_font(32)  # 选项使用 32 号字
        for i, opt in enumerate(options):
            opt_text = opt.get("text", "") if isinstance(opt, dict) else str(opt)
            color = col_sel if i == selected_index else col_norm
            prefix = "> " if i == selected_index else "  "
            s = font_option.render(prefix + opt_text, True, color)
            surface.blit(s, (center_x - s.get_width() // 2, y))
            y += option_spacing

        # 底部提示
        hint_cfg = layout.get("hint", {"text": "方向键 ↑↓ 选择  Z 确认  ESC 退出", "font_size": 18, "color": [100, 100, 120], "y_offset": -50})
        hint_text = hint_cfg.get("text", "方向键 ↑↓ 选择  Z 确认  ESC 退出")
        hint_size = int(hint_cfg.get("font_size", 18))
        hint_color = tuple(hint_cfg.get("color", [100, 100, 120]))
        hint_y_offset = int(hint_cfg.get("y_offset", -50))
        font_hint = self._get_font(hint_size)
        s_hint = font_hint.render(hint_text, True, hint_color)
        hint_y = sh + hint_y_offset if hint_y_offset < 0 else hint_y_offset
        surface.blit(s_hint, (center_x - s_hint.get_width() // 2, hint_y))

        return surface

    def _upload_texture(self, surface: SoftwareSurface):
        data = surface.to_bytes("RGBA", flip_y=True)
        w, h = surface.get_size()
        if self._texture is not None:
            if self._texture.size == (w, h):
                self._texture.write(data)
            else:
                self._texture.release()
                self._texture = self.ctx.texture((w, h), 4, data)
                self._texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        else:
            self._texture = self.ctx.texture((w, h), 4, data)
            self._texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

    def _draw_fullscreen_quad(self):
        if self._texture is None:
            return

        x0, y0 = 0.0, 0.0
        x1 = float(self.screen_width)
        y1 = float(self.screen_height)

        vertices = np.array([
            x0, y0, 0.0, 1.0,
            x0, y1, 0.0, 0.0,
            x1, y0, 1.0, 1.0,
            x1, y0, 1.0, 1.0,
            x0, y1, 0.0, 0.0,
            x1, y1, 1.0, 0.0,
        ], dtype='f4')

        self.vbo.write(vertices.tobytes())
        self._texture.use(0)
        self.vao.render(moderngl.TRIANGLES)

    def cleanup(self):
        if self._texture:
            self._texture.release()
            self._texture = None

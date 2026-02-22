"""
暂停菜单渲染器
"""

import moderngl
import numpy as np
import os
from typing import Dict, Any, Optional

from ..core.image_loader import SoftwareSurface, FontRenderer


class PauseMenuRenderer:
    """暂停菜单渲染器（ModernGL）"""

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

        # GL shader
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
        self._last_selected_index = -1
        self._cached_surface = None

    def _get_font(self, size: int) -> FontRenderer:
        if size not in self._font_cache:
            self._font_cache[size] = FontRenderer(self._font_path, size)
        return self._font_cache[size]

    def render(self, selected_index: int = 0):
        if self._cached_surface is None or self._last_selected_index != selected_index:
            self._cached_surface = self._render_to_surface(selected_index)
            self._upload_texture(self._cached_surface)
            self._last_selected_index = selected_index
            
        self._draw_fullscreen_quad()

    def _render_to_surface(self, selected_index: int) -> SoftwareSurface:
        sw, sh = self.screen_width, self.screen_height
        surface = SoftwareSurface(sw, sh)

        # 半透明黑色背景遮罩
        surface.fill((0, 0, 0, 150))

        center_x = sw // 2
        col_norm = (160, 160, 180, 255)
        col_sel = (255, 255, 200, 255)

        # 标题 PAUSED
        title_text = "PAUSED"
        title_size = 56
        title_color = (220, 220, 255, 255)
        y = int(sh * 0.3)
        font_title = self._get_font(title_size)
        s_title = font_title.render(title_text, True, title_color)
        surface.blit(s_title, (center_x - s_title.get_width() // 2, y))
        y += s_title.get_height() + 60

        # 菜单项
        options = ["继续游戏", "重新开始", "回到主菜单"]
        option_spacing = 48
        font_option = self._get_font(32)
        for i, opt_text in enumerate(options):
            color = col_sel if i == selected_index else col_norm
            prefix = "> " if i == selected_index else "  "
            s = font_option.render(prefix + opt_text, True, color)
            surface.blit(s, (center_x - s.get_width() // 2, y))
            y += option_spacing

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
        self.ctx.enable(moderngl.BLEND)
        self.vao.render(moderngl.TRIANGLES)

    def cleanup(self):
        if self._texture:
            self._texture.release()
            self._texture = None

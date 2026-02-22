"""
主菜单渲染器

纯文字 + 背景，无素材依赖。
使用 FontRenderer → SoftwareSurface → GL texture → quad 方式渲染。
"""

import moderngl
import numpy as np
import os

from ..core.image_loader import SoftwareSurface, FontRenderer


class MainMenuRenderer:
    """主菜单渲染器（ModernGL）"""

    def __init__(self, ctx: moderngl.Context, screen_width: int, screen_height: int):
        self.ctx = ctx
        self.screen_width = screen_width
        self.screen_height = screen_height

        # 字体
        font_path = os.path.join("assets", "fonts", "SourceHanSansCN-Bold.otf")
        if not os.path.exists(font_path):
            font_path = os.path.join("assets", "fonts", "wqy-microhei-mono.ttf")
        if not os.path.exists(font_path):
            font_path = None

        self.font_title = FontRenderer(font_path, 56)
        self.font_option = FontRenderer(font_path, 32)
        self.font_hint = FontRenderer(font_path, 18)

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

    def render(self, selected_index: int = 0):
        """
        渲染主菜单

        Args:
            selected_index: 当前选中的菜单项索引（0=开始游戏, 1=退出）
        """
        surface = self._render_to_surface(selected_index)
        self._upload_texture(surface)
        self._draw_fullscreen_quad()

    def _render_to_surface(self, selected_index: int) -> SoftwareSurface:
        sw, sh = self.screen_width, self.screen_height
        surface = SoftwareSurface(sw, sh)

        # 背景：深色渐变（上深下浅）
        for y in range(sh):
            t = y / sh
            r = int(12 + 8 * t)
            g = int(8 + 12 * t)
            b = int(28 + 16 * t)
            surface.draw_line((r, g, b), (0, y), (sw, y))

        center_x = sw // 2
        y = sh // 4

        # 标题
        title = "弹幕游戏"
        s_title = self.font_title.render(title, True, (220, 220, 255))
        surface.blit(s_title, (center_x - s_title.get_width() // 2, y))
        y += s_title.get_height() + 60

        # 菜单项
        options = ["开始游戏", "退出"]
        option_spacing = 48
        for i, opt in enumerate(options):
            color = (255, 255, 200) if i == selected_index else (160, 160, 180)
            prefix = "> " if i == selected_index else "  "
            s = self.font_option.render(prefix + opt, True, color)
            surface.blit(s, (center_x - s.get_width() // 2, y))
            y += option_spacing

        # 底部提示
        hint = "方向键 ↑↓ 选择  Z 确认  ESC 退出"
        s_hint = self.font_hint.render(hint, True, (100, 100, 120))
        surface.blit(s_hint, (center_x - s_hint.get_width() // 2, sh - 50))

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

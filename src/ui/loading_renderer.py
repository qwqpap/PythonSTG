"""
加载画面渲染器

在关卡加载期间显示黑屏 + 关卡信息。
使用 pygame.font → Surface → GL texture → quad 方式渲染。
"""

import moderngl
import numpy as np
import pygame
import os


class LoadingScreenRenderer:
    """加载画面渲染器（ModernGL）"""

    def __init__(self, ctx: moderngl.Context, screen_width: int, screen_height: int):
        self.ctx = ctx
        self.screen_width = screen_width
        self.screen_height = screen_height

        # 字体
        pygame.font.init()
        font_path = os.path.join("assets", "fonts", "SourceHanSansCN-Bold.otf")
        if not os.path.exists(font_path):
            font_path = os.path.join("assets", "fonts", "wqy-microhei-mono.ttf")
        if not os.path.exists(font_path):
            font_path = None

        self.font_stage = pygame.font.Font(font_path, 48)
        self.font_title = pygame.font.Font(font_path, 36)
        self.font_subtitle = pygame.font.Font(font_path, 22)
        self.font_hint = pygame.font.Font(font_path, 20)

        # GL shader（与 DialogGLRenderer 相同的 textured quad）
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

    def render(self, loading_info: dict):
        """
        渲染加载画面

        Args:
            loading_info: {
                "stage_name": "Stage 1",
                "title": "赤より紅い夢",        (optional)
                "subtitle": "A Dream ...",       (optional)
                "hint": "Loading...",            (optional)
                "progress": 0.5,                 (optional, 0.0~1.0)
            }
        """
        surface = self._render_to_surface(loading_info)
        self._upload_texture(surface)
        self._draw_fullscreen_quad()

    def _render_to_surface(self, info: dict) -> pygame.Surface:
        sw, sh = self.screen_width, self.screen_height
        surface = pygame.Surface((sw, sh), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 255))

        stage_name = info.get("stage_name", "")
        title = info.get("title", "")
        subtitle = info.get("subtitle", "")
        hint = info.get("hint", "")
        progress = info.get("progress")

        # 垂直排列：stage_name → title → subtitle　居中偏上
        center_x = sw // 2
        y = sh // 3

        if stage_name:
            s = self.font_stage.render(stage_name, True, (255, 255, 255))
            surface.blit(s, (center_x - s.get_width() // 2, y))
            y += s.get_height() + 20

        if title:
            s = self.font_title.render(title, True, (200, 200, 255))
            surface.blit(s, (center_x - s.get_width() // 2, y))
            y += s.get_height() + 12

        if subtitle:
            s = self.font_subtitle.render(subtitle, True, (160, 160, 200))
            surface.blit(s, (center_x - s.get_width() // 2, y))

        # hint 在底部
        if hint:
            s = self.font_hint.render(hint, True, (140, 140, 140))
            surface.blit(s, (center_x - s.get_width() // 2, sh - 80))

        # 进度条（可选）
        if progress is not None:
            bar_w = 400
            bar_h = 6
            bar_x = center_x - bar_w // 2
            bar_y = sh - 50
            # 底色
            pygame.draw.rect(surface, (60, 60, 60), (bar_x, bar_y, bar_w, bar_h))
            # 填充
            fill_w = int(bar_w * max(0.0, min(1.0, progress)))
            if fill_w > 0:
                pygame.draw.rect(surface, (180, 180, 255), (bar_x, bar_y, fill_w, bar_h))

        return surface

    def _upload_texture(self, surface: pygame.Surface):
        data = pygame.image.tobytes(surface, "RGBA", True)
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

"""
ModernGL 对话渲染器

使用 pygame.font 渲染中文文本到 Surface，
然后上传为 GL 纹理并绘制 textured quad。

支持:
- 中文文本（通过 TrueType 字体）
- 半透明背景
- 角色名显示
- 打字机效果
- 自动换行
- [按 Z 继续] 提示
"""

import moderngl
import numpy as np
import pygame
import os


class DialogGLRenderer:
    """基于 ModernGL 的对话框渲染器"""

    def __init__(self, ctx: moderngl.Context, screen_width: int, screen_height: int, game_viewport: tuple):
        """
        Args:
            ctx: ModernGL 上下文
            screen_width: 窗口宽度（像素）
            screen_height: 窗口高度（像素）
            game_viewport: 游戏区域 (x, y, width, height)
        """
        self.ctx = ctx
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.game_viewport = game_viewport

        # 对话框尺寸（窗口像素坐标）
        gx, gy, gw, gh = game_viewport
        self.box_margin = 20
        self.box_width = gw - self.box_margin * 2
        self.box_height = 180
        self.box_x = gx + self.box_margin
        self.box_y = gy + gh - self.box_height - self.box_margin

        # 加载中文字体
        pygame.font.init()
        font_path = os.path.join("assets", "fonts", "SourceHanSansCN-Bold.otf")
        if not os.path.exists(font_path):
            font_path = os.path.join("assets", "fonts", "wqy-microhei-mono.ttf")
        if not os.path.exists(font_path):
            font_path = None  # 使用 pygame 默认字体

        self.font = pygame.font.Font(font_path, 28)
        self.name_font = pygame.font.Font(font_path, 22)

        # GL 资源
        self._init_shader()
        self._dialog_texture = None

    def _init_shader(self):
        """初始化 textured quad 着色器"""
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
        self.program['u_screen_size'].value = (float(self.screen_width), float(self.screen_height))

        # 顶点缓冲区（6 vertices * 4 floats * 4 bytes）
        self.vbo = self.ctx.buffer(reserve=6 * 4 * 4)
        self.vao = self.ctx.vertex_array(
            self.program,
            [(self.vbo, '2f 2f', 'in_position', 'in_uv')]
        )

    def render(self, dialog_state):
        """
        渲染对话框

        Args:
            dialog_state: SimpleDialogTextRenderer 实例，
                         包含 current_sentence 和 visible_chars 属性
        """
        if dialog_state is None:
            return
        if not hasattr(dialog_state, 'current_sentence') or dialog_state.current_sentence is None:
            return

        # 渲染文本到 pygame Surface
        surface = self._render_to_surface(dialog_state)

        # 上传为 GL 纹理
        self._upload_texture(surface)

        # 绘制 quad
        self._draw_quad()

    def _render_to_surface(self, dialog_state):
        """将对话内容渲染到 pygame Surface"""
        surface = pygame.Surface((self.box_width, self.box_height), pygame.SRCALPHA)

        # 半透明黑色背景
        surface.fill((0, 0, 0, 180))

        sentence = dialog_state.current_sentence

        # 角色名（黄色）
        if sentence.character:
            name_surface = self.name_font.render(
                sentence.character, True, (255, 255, 100)
            )
            surface.blit(name_surface, (15, 10))

        # 对话文本（白色，打字机效果）
        visible_text = sentence.text[:dialog_state.visible_chars]
        lines = self._wrap_text(visible_text, self.font, self.box_width - 30)
        y = 45
        for line in lines:
            text_surface = self.font.render(line, True, (255, 255, 255))
            surface.blit(text_surface, (15, y))
            y += 35

        # [按 Z 继续] 提示（打字完成后显示）
        if dialog_state.visible_chars >= len(sentence.text):
            hint = self.name_font.render("[按 Z 继续]", True, (200, 200, 200))
            surface.blit(hint, (self.box_width - 150, self.box_height - 30))

        return surface

    def _wrap_text(self, text, font, max_width):
        """逐字换行"""
        lines = []
        current_line = ""
        for char in text:
            test_line = current_line + char
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
        return lines

    def _upload_texture(self, surface):
        """将 pygame Surface 上传为 ModernGL 纹理"""
        data = pygame.image.tobytes(surface, "RGBA", True)
        w, h = surface.get_size()

        if self._dialog_texture is not None:
            if self._dialog_texture.size == (w, h):
                self._dialog_texture.write(data)
            else:
                self._dialog_texture.release()
                self._dialog_texture = self.ctx.texture((w, h), 4, data)
                self._dialog_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        else:
            self._dialog_texture = self.ctx.texture((w, h), 4, data)
            self._dialog_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

    def _draw_quad(self):
        """绘制对话框 quad"""
        if self._dialog_texture is None:
            return

        x0 = float(self.box_x)
        y0 = float(self.box_y)
        x1 = float(self.box_x + self.box_width)
        y1 = float(self.box_y + self.box_height)

        # tobytes(flip=True)：v=0 对应 Surface 底部，v=1 对应 Surface 顶部
        vertices = np.array([
            # 三角形 1
            x0, y0, 0.0, 1.0,   # 左上 → 纹理顶部
            x0, y1, 0.0, 0.0,   # 左下 → 纹理底部
            x1, y0, 1.0, 1.0,   # 右上 → 纹理顶部
            # 三角形 2
            x1, y0, 1.0, 1.0,   # 右上
            x0, y1, 0.0, 0.0,   # 左下
            x1, y1, 1.0, 0.0,   # 右下 → 纹理底部
        ], dtype='f4')

        self.vbo.write(vertices.tobytes())
        self._dialog_texture.use(0)
        self.vao.render(moderngl.TRIANGLES)

    def cleanup(self):
        """释放 GL 资源"""
        if self._dialog_texture:
            self._dialog_texture.release()
            self._dialog_texture = None

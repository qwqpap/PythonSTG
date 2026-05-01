"""
Continue / Game Over 渲染器

两种模式：
  mode="continue"  → 「CONTINUE?」标题 + YES/NO 选项 + 剩余 continues 数
  mode="game_over" → 大写「GAME OVER」+ 「Returning to title...」副标题

与 PauseMenuRenderer 同一套 FontRenderer→SoftwareSurface→GL texture→fullscreen quad 套路，
半透明黑遮罩盖在游戏画面之上。
"""

from __future__ import annotations

import os
from typing import Dict, Optional

import moderngl
import numpy as np

from ..core.image_loader import SoftwareSurface, FontRenderer


class ContinueMenuRenderer:
    """Continue / Game Over 渲染器（ModernGL）"""

    def __init__(self, ctx: moderngl.Context, screen_width: int, screen_height: int):
        self.ctx = ctx
        self.screen_width = screen_width
        self.screen_height = screen_height

        font_path = os.path.join("assets", "fonts", "SourceHanSansCN-Bold.otf")
        if not os.path.exists(font_path):
            font_path = os.path.join("assets", "fonts", "wqy-microhei-mono.ttf")
        if not os.path.exists(font_path):
            font_path = None
        self._font_path = font_path
        self._font_cache: Dict[int, FontRenderer] = {}

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
            fragment_shader=fragment_shader,
        )
        self.program['u_texture'].value = 0
        self.program['u_screen_size'].value = (float(screen_width), float(screen_height))

        self.vbo = self.ctx.buffer(reserve=6 * 4 * 4)
        self.vao = self.ctx.vertex_array(
            self.program,
            [(self.vbo, '2f 2f', 'in_position', 'in_uv')],
        )
        self._texture: Optional[moderngl.Texture] = None

        # 画面缓存：相同 model 不重画
        self._cached_key: Optional[tuple] = None
        self._cached_surface: Optional[SoftwareSurface] = None

    # ===== 公共渲染入口 =====

    def render(self, model: dict) -> None:
        """渲染。
        model:
            {
                "mode": "continue" | "game_over",
                "selected": 0|1,            # 0=YES, 1=NO  （仅 continue 模式）
                "continues_left": int,      # 剩余 continues 数（仅 continue 模式）
                "game_over_progress": float (0..1),  # 仅 game_over 模式，淡出进度
            }
        """
        if not model:
            return

        key = (
            model.get("mode"),
            model.get("selected"),
            model.get("continues_left"),
            round(float(model.get("game_over_progress", 0.0)) * 60),  # 60 帧粒度
        )
        if key != self._cached_key:
            self._cached_surface = self._compose(model)
            self._upload_texture(self._cached_surface)
            self._cached_key = key

        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.disable(moderngl.DEPTH_TEST)
        self._draw_fullscreen_quad()

    # ===== 内部 =====

    def _get_font(self, size: int) -> FontRenderer:
        if size not in self._font_cache:
            self._font_cache[size] = FontRenderer(self._font_path, size)
        return self._font_cache[size]

    def _compose(self, model: dict) -> SoftwareSurface:
        sw, sh = self.screen_width, self.screen_height
        surface = SoftwareSurface(sw, sh)

        mode = model.get("mode", "continue")

        if mode == "game_over":
            # 完全黑屏（progress 控制覆盖深度，可做淡入）
            progress = max(0.0, min(1.0, float(model.get("game_over_progress", 1.0))))
            bg_alpha = int(180 + 75 * progress)
            surface.fill((0, 0, 0, bg_alpha))

            cx, cy = sw // 2, sh // 2

            # GAME OVER 大字
            font_big = self._get_font(96)
            s = font_big.render(
                "GAME OVER", True, (255, 80, 80, 255),
                stroke_width=2, stroke_color=(0, 0, 0, 255),
            )
            surface.blit(s, (cx - s.get_width() // 2, cy - s.get_height()))

            # 副标题
            font_sub = self._get_font(24)
            s2 = font_sub.render(
                "Returning to title...", True, (200, 200, 220, 255),
                stroke_width=1, stroke_color=(0, 0, 0, 255),
            )
            surface.blit(s2, (cx - s2.get_width() // 2, cy + 40))
            return surface

        # ===== mode == "continue" =====
        # 半透明黑色遮罩
        surface.fill((0, 0, 0, 170))

        cx = sw // 2
        cy = sh // 2

        # 大标题 CONTINUE?
        font_title = self._get_font(72)
        s_title = font_title.render(
            "CONTINUE?", True, (255, 230, 100, 255),
            stroke_width=2, stroke_color=(0, 0, 0, 255),
        )
        surface.blit(s_title, (cx - s_title.get_width() // 2, cy - 180))

        # 副标题：继续后分数无效 / 不解锁
        font_warn = self._get_font(20)
        s_warn = font_warn.render(
            "Using a continue invalidates score & stage unlock.",
            True, (200, 200, 200, 255),
            stroke_width=1, stroke_color=(0, 0, 0, 255),
        )
        surface.blit(s_warn, (cx - s_warn.get_width() // 2, cy - 80))

        # YES / NO
        selected = int(model.get("selected", 0))
        continues_left = int(model.get("continues_left", 0))
        yes_disabled = continues_left <= 0

        font_opt = self._get_font(40)
        col_norm = (180, 180, 200, 255)
        col_sel = (255, 255, 200, 255)
        col_disabled = (120, 80, 80, 255)

        def opt_color(idx: int, disabled: bool = False) -> tuple:
            if disabled:
                return col_disabled
            return col_sel if idx == selected else col_norm

        yes_text = ("> YES <" if (selected == 0 and not yes_disabled) else "  YES  ")
        no_text = ("> NO <" if selected == 1 else "  NO  ")

        s_yes = font_opt.render(yes_text, True, opt_color(0, yes_disabled),
                                stroke_width=1, stroke_color=(0, 0, 0, 255))
        s_no = font_opt.render(no_text, True, opt_color(1),
                               stroke_width=1, stroke_color=(0, 0, 0, 255))

        # 横排
        gap = 100
        total_w = s_yes.get_width() + gap + s_no.get_width()
        start_x = cx - total_w // 2
        opt_y = cy + 0
        surface.blit(s_yes, (start_x, opt_y))
        surface.blit(s_no, (start_x + s_yes.get_width() + gap, opt_y))

        # Continues 剩余
        font_meta = self._get_font(22)
        meta_text = f"Continues remaining: {continues_left}"
        s_meta = font_meta.render(
            meta_text, True,
            (200, 220, 255, 255) if continues_left > 0 else (255, 120, 120, 255),
            stroke_width=1, stroke_color=(0, 0, 0, 255),
        )
        surface.blit(s_meta, (cx - s_meta.get_width() // 2, opt_y + s_yes.get_height() + 30))

        # 操作提示
        font_hint = self._get_font(18)
        s_hint = font_hint.render(
            "← →  select        Z  confirm        ESC  cancel = NO",
            True, (140, 140, 160, 255),
        )
        surface.blit(s_hint, (cx - s_hint.get_width() // 2, sh - 80))

        return surface

    def _upload_texture(self, surface: SoftwareSurface):
        data = surface.to_bytes("RGBA", flip_y=True)
        w, h = surface.get_size()
        if self._texture is not None:
            if self._texture.size == (w, h):
                self._texture.write(data)
                return
            self._texture.release()
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
        if self._texture is not None:
            self._texture.release()
            self._texture = None
        self._cached_surface = None
        self._cached_key = None

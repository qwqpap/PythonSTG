"""
Staff Roll 渲染器（结局滚动名单）

接收一个 StaffRollState（src/game/stage/staff_roll.py），
按其 scroll_y 把整页名单画到全屏，文字从屏底往上滚。

本渲染器与 PauseMenuRenderer / LoadingScreenRenderer 同样的
"FontRenderer → SoftwareSurface → GL texture → fullscreen quad" 套路，
所以 main.py 只要每帧 render(state) 即可。
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import moderngl
import numpy as np

from ..core.image_loader import SoftwareSurface, FontRenderer


# 默认字号（一行 entry 的子级条目） - 可被 entry["size"] 覆盖
_DEFAULT_BODY_SIZE = 24

# 不同 type 的视觉风格
_TYPE_STYLES = {
    "title":    {"size": 56, "color": (255, 240, 200, 255), "spacing_after": 32},
    "section":  {"size": 36, "color": (200, 220, 255, 255), "spacing_after": 16, "spacing_before": 36},
    "role":     {"size": 22, "color": (170, 180, 210, 255), "spacing_after": 4},
    "name":     {"size": 30, "color": (255, 255, 255, 255), "spacing_after": 14},
    "text":     {"size": _DEFAULT_BODY_SIZE, "color": (220, 220, 230, 255), "spacing_after": 10},
    "spacer":   {"size": 0, "color": None, "spacing_after": 0},  # 仅占位
    "end":      {"size": 32, "color": (255, 230, 180, 255), "spacing_after": 0},
}


class StaffRollRenderer:
    """Staff Roll 渲染器（ModernGL）"""

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

        # entry 渲染缓存：避免每帧重新画文字
        # key: (entry_index, font_size, text) → SoftwareSurface
        self._entry_surface_cache: Dict[tuple, SoftwareSurface] = {}
        self._cached_state_id: Optional[int] = None

    # ===== 公共渲染入口 =====

    def render(self, state) -> None:
        """渲染一帧 staff roll；state 由 StageScript.run_staff_roll() 提供。"""
        if state is None:
            return

        # state 切换时清理 entry 文字缓存（不同 staff roll）
        sid = id(state)
        if sid != self._cached_state_id:
            self._entry_surface_cache.clear()
            self._cached_state_id = sid

        surface = self._compose(state)
        self._upload_texture(surface)

        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.disable(moderngl.DEPTH_TEST)
        self._draw_fullscreen_quad()

    # ===== 内部 =====

    def _get_font(self, size: int) -> FontRenderer:
        if size not in self._font_cache:
            self._font_cache[size] = FontRenderer(self._font_path, size)
        return self._font_cache[size]

    def _compose(self, state) -> SoftwareSurface:
        sw, sh = self.screen_width, self.screen_height
        surface = SoftwareSurface(sw, sh)

        # 纯黑背景
        surface.fill((0, 0, 0, 255))

        center_x = sw // 2
        scroll_y = float(getattr(state, "scroll_y", 0.0))
        entries = list(getattr(state, "entries", []) or [])

        # 第一条从屏幕底部开始往上滚 → 起始 y = sh - scroll_y
        cursor_y = sh - scroll_y

        for idx, entry in enumerate(entries):
            etype = entry.get("type", "text")
            text = entry.get("text", "")
            style = _TYPE_STYLES.get(etype, _TYPE_STYLES["text"])

            size = int(entry.get("size") or style.get("size") or _DEFAULT_BODY_SIZE)
            color = tuple(entry.get("color") or style.get("color") or (220, 220, 230, 255))
            spacing_before = int(entry.get("spacing_before") or style.get("spacing_before") or 0)
            spacing_after = int(entry.get("spacing_after") or style.get("spacing_after") or 8)

            cursor_y += spacing_before

            if etype == "spacer" or not text:
                cursor_y += int(entry.get("height", 24)) + spacing_after
                continue

            # 文字 surface（带缓存）
            cache_key = (idx, size, text, color)
            text_surface = self._entry_surface_cache.get(cache_key)
            if text_surface is None:
                font = self._get_font(size)
                text_surface = font.render(text, True, color, stroke_width=1, stroke_color=(0, 0, 0, 255))
                self._entry_surface_cache[cache_key] = text_surface

            tw = text_surface.get_width()
            th = text_surface.get_height()

            # 仅当 entry 有可能在可见区时才 blit（裁剪优化）
            if cursor_y + th >= 0 and cursor_y <= sh:
                surface.blit(text_surface, (center_x - tw // 2, int(cursor_y)))

            cursor_y += th + spacing_after

        # 把"内容总高度"回写给 state，以便它判断滚动是否结束
        try:
            state.total_height = float(cursor_y - (sh - scroll_y))
        except Exception:
            pass

        # 顶部/底部羽化（视觉柔和），用一个浅色覆盖层
        # 这里偷懒不做，需要时可以再加 PIL gradient overlay。

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
        self._entry_surface_cache.clear()

"""
设置菜单渲染器

渲染一个含分类卡片的设置面板，支持三种控件类型：
- slider:  值条 [█████░░░░░] 75%
- toggle:  开/关
- cycle:   < value >  (字符串枚举)
- action:  纯文字（如"返回"/"重置"）

使用 SoftwareSurface 离屏合成 → 上传 GL 纹理 → 全屏 quad 绘制，
风格与 PauseMenuRenderer / MainMenuRenderer 一致。
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import moderngl
import numpy as np

from ..core.image_loader import SoftwareSurface, FontRenderer


# ------------- 颜色常量（淡紫蓝色调，与游戏主菜单呼应） -------------

_BG_TOP = (10, 8, 24)
_BG_BOT = (28, 22, 56)
_PANEL_BG = (24, 22, 50, 220)
_PANEL_BORDER = (120, 110, 180, 255)
_SECTION_BAR = (60, 50, 110, 200)
_SECTION_TEXT = (210, 200, 255, 255)

_LABEL_NORMAL = (200, 200, 220, 255)
_LABEL_SELECTED = (255, 240, 140, 255)
_VALUE_NORMAL = (240, 240, 255, 255)
_VALUE_SELECTED = (255, 255, 200, 255)
_VALUE_DIM = (130, 130, 150, 255)

_SLIDER_TRACK = (60, 60, 90, 255)
_SLIDER_TRACK_BORDER = (140, 140, 180, 255)
_SLIDER_FILL_NORMAL = (130, 150, 220, 255)
_SLIDER_FILL_SELECTED = (240, 200, 100, 255)

_TITLE_COLOR = (220, 220, 255, 255)
_HINT_COLOR = (160, 160, 200, 255)


def _round_to_int(x: float) -> int:
    return int(round(x))


class SettingsMenuRenderer:
    """设置菜单渲染器（ModernGL）。"""

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
        self._text_cache: Dict[Tuple, SoftwareSurface] = {}
        self._last_signature: Optional[Tuple] = None

        # GL 资源（与其它菜单渲染器同样的全屏 quad shader）
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

    # ---------- public ----------

    def render(self, model: Dict[str, Any]):
        """
        渲染。model 字段：
          title:    str
          items:    list[dict]  每项 {label, type, value?, options?, section?}
          selected: int
          hint:     str
        """
        sig = self._signature(model)
        if self._texture is None or sig != self._last_signature:
            surface = self._render_to_surface(model)
            self._upload(surface)
            self._last_signature = sig
        self._draw_quad()

    def cleanup(self):
        if self._texture is not None:
            self._texture.release()
            self._texture = None
        self._text_cache.clear()
        self._last_signature = None

    # ---------- internals ----------

    def _font(self, size: int) -> FontRenderer:
        if size not in self._font_cache:
            self._font_cache[size] = FontRenderer(self._font_path, size)
        return self._font_cache[size]

    def _text(self, font: FontRenderer, text: str, color, stroke=1) -> SoftwareSurface:
        key = (id(font), text, tuple(color), stroke)
        s = self._text_cache.get(key)
        if s is None:
            s = font.render(text, True, color, stroke_width=stroke, stroke_color=(0, 0, 0, 255))
            self._text_cache[key] = s
        return s

    def _signature(self, model: Dict[str, Any]) -> Tuple:
        items_sig = tuple(
            (
                it.get("label", ""),
                it.get("type", ""),
                # value 可能是 float / bool / str
                it.get("value"),
                it.get("section"),
            )
            for it in model.get("items", [])
        )
        return (
            model.get("title", ""),
            items_sig,
            int(model.get("selected", 0)),
            model.get("hint", ""),
        )

    def _render_to_surface(self, model: Dict[str, Any]) -> SoftwareSurface:
        sw, sh = self.screen_width, self.screen_height
        surface = SoftwareSurface(sw, sh)

        # 1) 背景渐变
        for y in range(sh):
            t = y / max(1, sh - 1)
            r = int(_BG_TOP[0] + (_BG_BOT[0] - _BG_TOP[0]) * t)
            g = int(_BG_TOP[1] + (_BG_BOT[1] - _BG_TOP[1]) * t)
            b = int(_BG_TOP[2] + (_BG_BOT[2] - _BG_TOP[2]) * t)
            surface.draw_line((r, g, b), (0, y), (sw, y))

        # 2) 中央面板
        panel_w = min(720, sw - 80)
        panel_h = min(560, sh - 120)
        panel_x = (sw - panel_w) // 2
        panel_y = (sh - panel_h) // 2 + 20  # 略微下移给标题留位

        # 半透明面板（先填实色，再模拟阴影）
        # SoftwareSurface 不支持复合 alpha 矩形，用 fill 一块再 blit 实现
        panel_surface = SoftwareSurface(panel_w, panel_h)
        panel_surface.fill(_PANEL_BG)
        # 边框
        panel_surface.draw_rect(_PANEL_BORDER, (0, 0, panel_w - 1, panel_h - 1), width=2)
        surface.blit(panel_surface, (panel_x, panel_y))

        # 3) 标题（在面板上方居中）
        title = model.get("title", "设置")
        title_font = self._font(36)
        s_title = self._text(title_font, title, _TITLE_COLOR, stroke=2)
        surface.blit(
            s_title,
            (sw // 2 - s_title.get_width() // 2, panel_y - s_title.get_height() - 12),
        )

        # 4) 渲染每个 item
        items: List[Dict[str, Any]] = model.get("items", [])
        selected = int(model.get("selected", 0))

        item_font = self._font(22)
        section_font = self._font(20)

        # 布局：左右内边距 32，顶部 24，行高 44，section bar 高 32
        pad_x = 32
        pad_top = 24
        row_h = 44
        section_bar_h = 32

        cur_y = panel_y + pad_top
        cur_section: Optional[str] = None

        # 布局阶段：先确定每行的 (kind=item|section, idx, y) — 简化为顺序渲染
        for i, it in enumerate(items):
            section = it.get("section")
            if section and section != cur_section:
                # 上一节与本节之间留一点呼吸
                if cur_section is not None:
                    cur_y += 8
                # 绘制 section bar（左侧高亮竖条 + 半透明长条 + 文字）
                bar_x = panel_x + pad_x // 2
                bar_w = panel_w - pad_x
                bar_h = section_bar_h - 6
                surface.draw_rect(_SECTION_BAR, (bar_x, cur_y, bar_w, bar_h), width=0)
                # 左侧高亮竖条
                surface.draw_rect(
                    (180, 160, 240, 255), (bar_x, cur_y, 4, bar_h), width=0,
                )
                s_section = self._text(section_font, section, _SECTION_TEXT, stroke=1)
                surface.blit(
                    s_section,
                    (bar_x + 16, cur_y + (bar_h - s_section.get_height()) // 2),
                )
                cur_y += section_bar_h
                cur_section = section

            is_sel = (i == selected)

            # 行背景（仅选中时）
            if is_sel:
                row_bg_rect = (panel_x + 8, cur_y - 4, panel_w - 16, row_h - 4)
                surface.draw_rect((80, 70, 140, 110), row_bg_rect, width=0)

            label = ("> " if is_sel else "  ") + str(it.get("label", ""))
            label_color = _LABEL_SELECTED if is_sel else _LABEL_NORMAL
            s_label = self._text(item_font, label, label_color, stroke=1)
            surface.blit(s_label, (panel_x + pad_x, cur_y + (row_h - s_label.get_height()) // 2 - 4))

            # 右侧控件
            self._render_control(
                surface,
                item=it,
                is_selected=is_sel,
                right_edge=panel_x + panel_w - pad_x,
                y_top=cur_y,
                row_h=row_h,
                font=item_font,
            )

            cur_y += row_h

        # 5) 提示
        hint = model.get("hint", "")
        if hint:
            hint_font = self._font(16)
            s_hint = self._text(hint_font, hint, _HINT_COLOR, stroke=1)
            surface.blit(
                s_hint,
                (sw // 2 - s_hint.get_width() // 2, sh - s_hint.get_height() - 24),
            )

        return surface

    def _render_control(
        self,
        surface: SoftwareSurface,
        *,
        item: Dict[str, Any],
        is_selected: bool,
        right_edge: int,
        y_top: int,
        row_h: int,
        font: FontRenderer,
    ):
        kind = item.get("type", "action")
        value_color = _VALUE_SELECTED if is_selected else _VALUE_NORMAL

        if kind == "slider":
            value = float(item.get("value", 0.0))
            value = max(0.0, min(1.0, value))

            # 布局：[track 220px][gap 10px][pct 50px right-aligned to right_edge]
            pct_text = f"{int(value * 100):3d}%"
            s_pct = self._text(font, pct_text, value_color, stroke=1)
            pct_w = max(s_pct.get_width(), 48)
            gap = 10
            track_w = 220
            track_h = 12
            track_x = right_edge - pct_w - gap - track_w
            track_y = y_top + (row_h - track_h) // 2 - 2

            # track 背景
            surface.draw_rect(_SLIDER_TRACK, (track_x, track_y, track_w, track_h), width=0)
            # 已填充
            fill_w = max(1, _round_to_int(track_w * value))
            fill_color = _SLIDER_FILL_SELECTED if is_selected else _SLIDER_FILL_NORMAL
            surface.draw_rect(fill_color, (track_x, track_y, fill_w, track_h), width=0)
            # 边框
            surface.draw_rect(
                _SLIDER_TRACK_BORDER,
                (track_x, track_y, track_w - 1, track_h - 1),
                width=1,
            )
            # 选中时在拇指处加一个亮点
            if is_selected:
                thumb_x = track_x + fill_w
                thumb_y = track_y + track_h // 2
                surface.draw_circle((255, 255, 220, 255), (thumb_x, thumb_y), 5)
                surface.draw_circle((255, 200, 80, 255), (thumb_x, thumb_y), 5, width=1)

            # 百分比文本（右侧对齐）
            pct_y = y_top + (row_h - s_pct.get_height()) // 2 - 4
            surface.blit(s_pct, (right_edge - s_pct.get_width(), pct_y))

        elif kind == "toggle":
            on = bool(item.get("value", False))
            txt = "● 开" if on else "○ 关"
            color = (160, 240, 160, 255) if on else (200, 120, 120, 255)
            if is_selected:
                # 选中时混合提亮
                color = (
                    min(255, color[0] + 30),
                    min(255, color[1] + 30),
                    min(255, color[2] + 30),
                    255,
                )
            s = self._text(font, txt, color, stroke=1)
            surface.blit(s, (right_edge - s.get_width(), y_top + (row_h - s.get_height()) // 2 - 4))

        elif kind == "cycle":
            value = str(item.get("value", ""))
            display = item.get("display") or value
            txt = f"<  {display}  >" if is_selected else f"   {display}   "
            s = self._text(font, txt, value_color, stroke=1)
            surface.blit(s, (right_edge - s.get_width(), y_top + (row_h - s.get_height()) // 2 - 4))

        elif kind == "info":
            value = str(item.get("value", ""))
            s = self._text(font, value, _VALUE_DIM, stroke=1)
            surface.blit(s, (right_edge - s.get_width(), y_top + (row_h - s.get_height()) // 2 - 4))

        # action 类型不画右侧控件

    def _upload(self, surface: SoftwareSurface):
        data = surface.to_bytes("RGBA", flip_y=True)
        w, h = surface.get_size()
        if self._texture is not None:
            if self._texture.size == (w, h):
                self._texture.write(data)
                return
            self._texture.release()
        self._texture = self.ctx.texture((w, h), 4, data)
        self._texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

    def _draw_quad(self):
        if self._texture is None:
            return
        x1 = float(self.screen_width)
        y1 = float(self.screen_height)
        vertices = np.array([
            0.0, 0.0, 0.0, 1.0,
            0.0, y1,  0.0, 0.0,
            x1,  0.0, 1.0, 1.0,
            x1,  0.0, 1.0, 1.0,
            0.0, y1,  0.0, 0.0,
            x1,  y1,  1.0, 0.0,
        ], dtype='f4')
        self.vbo.write(vertices.tobytes())
        self._texture.use(0)
        self.ctx.enable(moderngl.BLEND)
        self.vao.render(moderngl.TRIANGLES)

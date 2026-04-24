"""
符卡宣言（SpellCard Declaration）

每张有名字的符卡开始时播放的装饰动画。时间线（单位：秒）：

    0.00 - 0.80  符卡名出现在游戏区域中下方：
                 - 比例 3.0 → 1.2（越变越小）
                 - 透明度 0.2 → 1.0（越变越清晰）
    0.80 - 1.25  符卡名从"中下方"滑到"右下角"；
                 名字下方出现一条红色下划线。
    1.25 - 2.05  符卡名 + 下划线保持同一 X 坐标，竖直上移到"右上角"。
    2.05 - 2.45  锁定：符卡名轻微收尾，交给 HUD 接管。

同时整个动画期间游戏区域内显示多行倾斜的
"SpellCard Attack!!"带状文字（方向交替），自上而下滚动。

本模块包含三部分：
    SpellDeclaration          —— 纯状态机（无 GL 依赖）
    DeclarationRenderState    —— 每帧插值状态
    SpellDeclarationRenderer  —— 共享 GL 资源，由主循环调用渲染
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    import moderngl  # noqa: F401


# ---------- 时间线常量 ----------
PHASE_INTRO_END = 0.80     # 中央缩放/透明化结束
PHASE_TO_BR_END = 1.25     # 到达右下角 + 红线落定
PHASE_TO_TR_END = 2.05     # 到达右上角
PHASE_LOCK_END  = 2.45     # 宣言全部结束
TOTAL_DURATION  = PHASE_LOCK_END


# ---------- 缓动函数 ----------
def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0


def _lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


# ---------- 渲染状态 ----------
@dataclass
class DeclarationRenderState:
    """一帧的插值结果（由 SpellDeclaration.get_state 生成，由渲染器消费）。

    所有坐标均为窗口像素坐标（原点左上）。
    """
    # 符卡名锚点。name_anchor_right=0 时为中心锚点，=1 时为右边缘锚点。
    name_cx: float
    name_cy: float
    name_scale: float
    name_alpha: float
    name_anchor_right: float

    # 红色下划线
    line_visible: bool
    line_p0: Tuple[float, float]   # 起点
    line_p1: Tuple[float, float]   # 控制点 1
    line_p2: Tuple[float, float]   # 控制点 2
    line_p3: Tuple[float, float]   # 终点（连在符卡名下方）
    line_alpha: float
    line_reveal: float             # 0.0~1.0 生长比例（曲线绘制的终止参数）

    # 带状文字
    band_alpha: float
    band_scroll: float             # 0.0~1.0 自上而下的滚动进度


# ---------- 状态机 ----------
class SpellDeclaration:
    """一张符卡的宣言动画状态。纯逻辑，不含 GL 资源。"""

    def __init__(self, name: str):
        self.name: str = name or ""
        self.time: float = 0.0
        self._active: bool = True

    @property
    def active(self) -> bool:
        return self._active

    @property
    def blocks_spell_update(self) -> bool:
        """True while the opening declaration should pause spellcard logic."""
        return self._active and self.time < TOTAL_DURATION

    def finish(self) -> None:
        """Stop rendering this declaration. BossBase calls this when the spell ends."""
        self._active = False

    def update(self, dt: float) -> bool:
        """Advance time. The badge stays active until the owning spell ends."""
        if not self._active:
            return False
        self.time += max(0.0, dt)
        return self._active

    def get_state(self,
                  game_viewport_px: Tuple[int, int, int, int],
                  window_size: Tuple[int, int]) -> DeclarationRenderState:
        """生成当前帧的插值状态。

        Args:
            game_viewport_px: 游戏视口在窗口中的位置，**窗口左上为原点**
                              (x, y_from_top, w, h)。
            window_size: (window_w, window_h)
        """
        gx, gy, gw, gh = game_viewport_px
        win_w, win_h = window_size
        t = self.time

        # 三个锚点（窗口像素坐标）
        # 中下方 —— 游戏视口 50% 宽, 75% 高
        center_cx = gx + gw * 0.5
        center_cy = gy + gh * 0.76

        # 右下角 —— 使用右边缘锚点，避免长符卡名超出游戏区域右侧
        right_anchor_x = gx + gw - 18
        br_cx = right_anchor_x
        br_cy = gy + gh - 38

        # 右上角 —— 与右下角保持同一 x，竖直上移
        tr_cx = right_anchor_x
        tr_cy = gy + 38

        def _underline_placeholder(cx: float, cy: float, scale: float):
            y = cy + 23.0 * scale
            return (cx, y), (cx, y)

        if t < PHASE_INTRO_END:
            # 原地放大→收缩 + 渐显
            k = t / PHASE_INTRO_END
            ks = _smoothstep(k)
            name_scale = _lerp(3.0, 1.2, ks)
            name_alpha = _lerp(0.18, 1.0, ks)
            name_cx = center_cx
            name_cy = center_cy
            name_anchor_right = 0.0
            line_visible = True
            line_p0, line_p3 = _underline_placeholder(name_cx, name_cy, name_scale)
            line_reveal = _smoothstep(max(0.0, (k - 0.20) / 0.80))
            line_alpha = name_alpha * 0.9

        elif t < PHASE_TO_BR_END:
            # 中央 → 右下；锚点逐渐从中心过渡为右边缘
            k = (t - PHASE_INTRO_END) / (PHASE_TO_BR_END - PHASE_INTRO_END)
            ke = _ease_in_out_cubic(k)
            name_scale = _lerp(1.2, 0.95, ke)
            name_alpha = 1.0
            name_cx = _lerp(center_cx, br_cx, ke)
            name_cy = _lerp(center_cy, br_cy, ke)
            name_anchor_right = _smoothstep(k)
            line_visible = True
            line_reveal = 1.0
            line_alpha = 1.0
            line_p0, line_p3 = _underline_placeholder(name_cx, name_cy, name_scale)

        elif t < PHASE_TO_TR_END:
            # 右下 → 右上；右边缘对齐并保持同一 x 坐标竖直上移
            k = (t - PHASE_TO_BR_END) / (PHASE_TO_TR_END - PHASE_TO_BR_END)
            ke = _ease_in_out_cubic(k)
            name_scale = _lerp(0.95, 0.85, ke)
            name_alpha = 1.0
            name_cx = _lerp(br_cx, tr_cx, ke)
            name_cy = _lerp(br_cy, tr_cy, ke)
            name_anchor_right = 1.0
            line_visible = True
            line_reveal = 1.0
            line_alpha = 1.0
            line_p0, line_p3 = _underline_placeholder(name_cx, name_cy, name_scale)

        else:
            # 锁定在右上角，直到符卡结束时由 BossBase 清掉
            name_scale = 0.85
            name_alpha = 1.0
            name_cx = tr_cx
            name_cy = tr_cy
            name_anchor_right = 1.0
            line_visible = True
            line_alpha = 1.0
            line_reveal = 1.0
            line_p0, line_p3 = _underline_placeholder(name_cx, name_cy, name_scale)

        line_p1 = line_p0
        line_p2 = line_p3

        # 带状文字
        if t < PHASE_INTRO_END:
            band_alpha = (t / PHASE_INTRO_END) * 0.65
        elif t < PHASE_TO_TR_END:
            band_alpha = 0.65
        elif t < PHASE_LOCK_END:
            band_alpha = 0.65 * max(0.0, 1.0 - (t - PHASE_TO_TR_END) / (PHASE_LOCK_END - PHASE_TO_TR_END))
        else:
            band_alpha = 0.0
        band_scroll = min(1.0, t / max(1e-4, PHASE_TO_TR_END))

        return DeclarationRenderState(
            name_cx=name_cx, name_cy=name_cy,
            name_scale=name_scale, name_alpha=name_alpha,
            name_anchor_right=name_anchor_right,
            line_visible=line_visible,
            line_p0=line_p0, line_p1=line_p1,
            line_p2=line_p2, line_p3=line_p3,
            line_alpha=line_alpha, line_reveal=line_reveal,
            band_alpha=band_alpha, band_scroll=band_scroll,
        )


# ---------- GL 渲染器（共享资源） ----------
class SpellDeclarationRenderer:
    """符卡宣言的 GL 渲染器。

    - 拥有字体、shader、字形纹理缓存。
    - 单个实例可服务多个 SpellDeclaration（每张符卡重用同一套资源）。

    使用方法：
        renderer = SpellDeclarationRenderer(ctx, win_size, game_viewport_window_coord)
        每帧：
            if boss.declaration and boss.declaration.active:
                renderer.render(boss.declaration, game_viewport_window_coord)
    """

    BAND_TEXT = "SpellCard  Attack !!"
    BAND_ROWS = 5
    BAND_ANGLE_MAIN = 20.0   # 倾斜角度（度）
    NAME_BASE_SIZE = 38      # 符卡名字体点数（渲染时固定，渲染 quad 时按 scale 放大）

    def __init__(self,
                 ctx,
                 window_size: Tuple[int, int],
                 game_viewport_win: Tuple[int, int, int, int]):
        """
        Args:
            ctx: ModernGL 上下文 (moderngl.Context)
            window_size: 窗口 (w, h)
            game_viewport_win: 游戏区域 (x, y_from_top, w, h)，窗口坐标
        """
        # 延迟导入，使状态机（SpellDeclaration）可在无 GL 环境单元测试
        import moderngl  # noqa: F811
        import numpy as np  # noqa: F811
        from ...core.image_loader import FontRenderer
        self._moderngl = moderngl
        self._np = np

        self.ctx = ctx
        self.window_size = window_size
        self.game_viewport_win = game_viewport_win

        # 字体（中文 + 英文）
        font_path = os.path.join("assets", "fonts", "SourceHanSansCN-Bold.otf")
        if not os.path.exists(font_path):
            font_path = os.path.join("assets", "fonts", "wqy-microhei-mono.ttf")
        if not os.path.exists(font_path):
            font_path = None
        self._name_font = FontRenderer(font_path, self.NAME_BASE_SIZE)
        self._band_font = FontRenderer(font_path, 34)

        # 纹理缓存
        self._name_texture = None
        self._name_text: str = ""
        self._name_tex_size: Tuple[int, int] = (1, 1)

        self._band_texture = None
        self._band_tex_size: Tuple[int, int] = (1, 1)

        # 初始化 shader
        self._init_textured_quad_shader()
        self._init_colored_quad_shader()

        # 预渲染一次带状文字纹理
        self._ensure_band_texture()

    # ----- shader -----
    def _init_textured_quad_shader(self):
        """支持旋转 + 缩放 + 中心锚点的 textured quad shader。"""
        vs = """
        #version 330
        uniform vec2 u_screen_size;
        uniform vec2 u_center;          // 中心点（像素、y 从上）
        uniform vec2 u_half_size;       // 半宽高（像素）
        uniform float u_angle;          // 弧度
        in vec2 in_offset;              // 每个顶点的本地偏移（-1..1）
        in vec2 in_uv;
        out vec2 v_uv;
        void main() {
            float c = cos(u_angle);
            float s = sin(u_angle);
            vec2 local = in_offset * u_half_size;
            vec2 rotated = vec2(local.x * c - local.y * s,
                                local.x * s + local.y * c);
            vec2 px = u_center + rotated;
            vec2 ndc = (px / u_screen_size) * 2.0 - 1.0;
            ndc.y = -ndc.y;
            gl_Position = vec4(ndc, 0.0, 1.0);
            v_uv = in_uv;
        }
        """
        fs = """
        #version 330
        uniform sampler2D u_texture;
        uniform vec4 u_tint;
        in vec2 v_uv;
        out vec4 f_color;
        void main() {
            vec4 c = texture(u_texture, v_uv);
            f_color = vec4(c.rgb * u_tint.rgb, c.a * u_tint.a);
        }
        """
        self._quad_prog = self.ctx.program(vertex_shader=vs, fragment_shader=fs)
        self._quad_prog['u_texture'].value = 0
        self._quad_prog['u_screen_size'].value = (float(self.window_size[0]), float(self.window_size[1]))

        # 固定顶点：两三角形，offset 从 (-1,-1) 到 (1,1)
        verts = self._np.array([
            # offset.xy   uv.xy
            -1.0, -1.0,   0.0, 1.0,
            -1.0,  1.0,   0.0, 0.0,
             1.0, -1.0,   1.0, 1.0,
             1.0, -1.0,   1.0, 1.0,
            -1.0,  1.0,   0.0, 0.0,
             1.0,  1.0,   1.0, 0.0,
        ], dtype='f4')
        self._quad_vbo = self.ctx.buffer(verts.tobytes())
        self._quad_vao = self.ctx.vertex_array(
            self._quad_prog,
            [(self._quad_vbo, '2f 2f', 'in_offset', 'in_uv')]
        )

    def _init_colored_quad_shader(self):
        """用于红线：一批独立的细长矩形（逐 VBO 写入）。"""
        vs = """
        #version 330
        uniform vec2 u_screen_size;
        in vec2 in_position;
        in vec4 in_color;
        out vec4 v_color;
        void main() {
            vec2 ndc = (in_position / u_screen_size) * 2.0 - 1.0;
            ndc.y = -ndc.y;
            gl_Position = vec4(ndc, 0.0, 1.0);
            v_color = in_color;
        }
        """
        fs = """
        #version 330
        in vec4 v_color;
        out vec4 f_color;
        void main() { f_color = v_color; }
        """
        self._col_prog = self.ctx.program(vertex_shader=vs, fragment_shader=fs)
        self._col_prog['u_screen_size'].value = (float(self.window_size[0]), float(self.window_size[1]))
        # 动态 VBO，足够绘制 ~500 个顶点
        self._col_vbo = self.ctx.buffer(reserve=4096 * 6 * 4)
        self._col_vao = self.ctx.vertex_array(
            self._col_prog,
            [(self._col_vbo, '2f 4f', 'in_position', 'in_color')]
        )

    # ----- 资源上传 -----
    def _ensure_name_texture(self, name: str):
        """懒加载/更新符卡名纹理。"""
        if name == self._name_text and self._name_texture is not None:
            return
        surf = self._name_font.render(
            name if name else " ",
            antialias=True,
            color=(255, 255, 255),
            stroke_width=2,
            stroke_color=(12, 12, 24),
        )
        data = surf.to_bytes("RGBA", flip_y=True)
        w, h = surf.get_size()
        if self._name_texture is not None:
            try:
                self._name_texture.release()
            except Exception:
                pass
        tex = self.ctx.texture((w, h), 4, data)
        tex.filter = (self._moderngl.LINEAR, self._moderngl.LINEAR)
        self._name_texture = tex
        self._name_tex_size = (w, h)
        self._name_text = name

    def _ensure_band_texture(self):
        """预渲染带状文字（一整行 "SpellCard Attack!! SpellCard Attack!! …"）。"""
        # 一行重复若干次，用空格隔开
        repeated = (self.BAND_TEXT + "   ") * 6
        surf = self._band_font.render(
            repeated,
            antialias=True,
            color=(255, 255, 255),
            stroke_width=2,
            stroke_color=(40, 0, 40),
        )
        data = surf.to_bytes("RGBA", flip_y=True)
        w, h = surf.get_size()
        tex = self.ctx.texture((w, h), 4, data)
        tex.filter = (self._moderngl.LINEAR, self._moderngl.LINEAR)
        self._band_texture = tex
        self._band_tex_size = (w, h)

    # ----- 渲染入口 -----
    def render(self,
               declaration: SpellDeclaration,
               game_viewport_win: Optional[Tuple[int, int, int, int]] = None):
        """渲染一次宣言动画。

        需要调用方已切换到窗口全屏 viewport。内部会自适应管理 scissor。
        """
        if declaration is None or not declaration.active:
            return

        if game_viewport_win is None:
            game_viewport_win = self.game_viewport_win

        state = declaration.get_state(game_viewport_win, self.window_size)
        if declaration.name:
            self._ensure_name_texture(declaration.name)

        # 开启混合
        mgl = self._moderngl
        self.ctx.enable(mgl.BLEND)
        self.ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA
        self.ctx.disable(mgl.DEPTH_TEST)

        # 1) 带状文字（在游戏视口内，用 scissor 裁剪）
        if state.band_alpha > 0.003 and self._band_texture is not None:
            self._render_bands(state, game_viewport_win)

        # 2) 跟随符卡名的红色下划线
        if state.line_visible and state.line_alpha > 0.003 and state.line_reveal > 0.002:
            self._render_straight_line(state)

        # 3) 符卡名
        if state.name_alpha > 0.003 and declaration.name:
            self._render_name(state)

    # ----- 带状文字 -----
    def _render_bands(self, state: DeclarationRenderState, game_viewport_win):
        """
        所有行使用同一倾斜方向（右上 → 左下，视觉上是 "/" ）。
        每行沿着这条对角线方向整体平移；相邻行沿对角线方向相反（奇偶交替），
        产生"上/下两股文字相向而行"的效果。
        """
        gx, gy, gw, gh = game_viewport_win
        win_h = self.window_size[1]
        # OpenGL scissor 的 y 从窗口底部
        sc_y = win_h - (gy + gh)
        prev_scissor = self.ctx.scissor
        self.ctx.scissor = (gx, sc_y, gw, gh)

        bw, bh = self._band_tex_size

        # 尺寸
        target_half_w = gw * 0.85
        target_half_h = bh * 0.9
        scale_x = target_half_w / (bw / 2.0)
        scale_y = target_half_h / (bh / 2.0)
        scale = min(scale_x, scale_y) * 0.8
        hw = (bw / 2.0) * scale
        hh = (bh / 2.0) * scale

        # 所有行采用统一倾斜角度：负角度 = 绕 y-down 空间逆时针 = "/" 方向
        # （在屏幕上看文字自左下抬升到右上；整条带子从右上延伸到左下）
        angle_rad = math.radians(-self.BAND_ANGLE_MAIN)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # 对角线方向（沿带子"长轴"）；在 y-down 空间
        dir_x = cos_a
        dir_y = sin_a
        # 垂直于带子（用于行间距）
        perp_x = -sin_a
        perp_y = cos_a

        # 中心
        cx0 = gx + gw * 0.5
        cy0 = gy + gh * 0.5

        # 行间距：沿垂直于带子的方向展开
        row_gap = gh / (self.BAND_ROWS + 1)

        # 总平移距离（沿对角线方向，0 → scroll_total）
        scroll_total = gh * 1.15
        along_base = state.band_scroll * scroll_total

        self._band_texture.use(0)
        self._quad_prog['u_tint'].value = (1.0, 0.95, 0.98, state.band_alpha)

        mgl = self._moderngl
        for i in range(self.BAND_ROWS):
            # 相邻行沿对角线方向相反（奇偶交替）
            along_sign = 1.0 if (i % 2 == 0) else -1.0
            # 每行初始相位错开，让两组交错出现
            phase = (i * 0.37) * row_gap
            along = along_sign * along_base + phase - scroll_total * 0.5

            # 行基准位置：沿垂直方向排布
            row_offset = (i - (self.BAND_ROWS - 1) * 0.5) * row_gap
            base_x = cx0 + perp_x * row_offset
            base_y = cy0 + perp_y * row_offset

            # 加上沿对角线方向的平移
            cx_row = base_x + dir_x * along
            cy_row = base_y + dir_y * along

            # 粗略视锥剔除（scissor 会二次裁剪，但省一次 draw 更好）
            pad = max(hw, hh) * 1.2
            if (cx_row < gx - pad or cx_row > gx + gw + pad or
                cy_row < gy - pad or cy_row > gy + gh + pad):
                continue

            self._quad_prog['u_center'].value = (float(cx_row), float(cy_row))
            self._quad_prog['u_half_size'].value = (float(hw), float(hh))
            self._quad_prog['u_angle'].value = float(angle_rad)
            self._quad_vao.render(mgl.TRIANGLES, vertices=6)

        self.ctx.scissor = prev_scissor

    # ----- 贝塞尔红线 -----
    def _name_quad_metrics(self, state: DeclarationRenderState):
        tw, th = self._name_tex_size
        if tw <= 0:
            return state.name_cx, 0.0, 0.0
        max_width = max(16.0, self.game_viewport_win[2] - 36.0)
        scale = min(state.name_scale, max_width / float(tw))
        hw = (tw * 0.5) * scale
        hh = (th * 0.5) * scale
        cx = state.name_cx - hw * max(0.0, min(1.0, state.name_anchor_right))
        return cx, hw, hh

    def _render_straight_line(self, state: DeclarationRenderState):
        if self._name_texture is None:
            return
        cx, hw, hh = self._name_quad_metrics(state)
        x0 = cx - hw
        x1 = cx + hw
        y0 = state.name_cy + hh + 4.0
        y1 = y0
        reveal = max(0.0, min(1.0, state.line_reveal))
        x1 = x0 + (x1 - x0) * reveal
        y1 = y0 + (y1 - y0) * reveal

        dx = x1 - x0
        dy = y1 - y0
        length = max(1e-4, math.hypot(dx, dy))
        nx = -dy / length
        ny = dx / length
        half_w = 2.0
        ox = nx * half_w
        oy = ny * half_w
        r, g, b, a = 1.0, 0.18, 0.22, state.line_alpha

        verts = [
            x0 - ox, y0 - oy, r, g, b, a,
            x0 + ox, y0 + oy, r, g, b, a,
            x1 - ox, y1 - oy, r, g, b, a,
            x1 - ox, y1 - oy, r, g, b, a,
            x0 + ox, y0 + oy, r, g, b, a,
            x1 + ox, y1 + oy, r, g, b, a,
        ]
        arr = self._np.array(verts, dtype='f4')
        self._col_vbo.write(arr.tobytes())
        self._col_vao.render(self._moderngl.TRIANGLES, vertices=6)

    def _render_bezier(self, state: DeclarationRenderState):
        p0 = state.line_p0
        p1 = state.line_p1
        p2 = state.line_p2
        p3 = state.line_p3
        # 采样曲线
        n_samples = 32
        reveal = max(0.0, min(1.0, state.line_reveal))
        pts = []
        for i in range(n_samples + 1):
            tt = (i / n_samples) * reveal
            u = 1.0 - tt
            x = (u ** 3) * p0[0] + 3 * (u ** 2) * tt * p1[0] + 3 * u * (tt ** 2) * p2[0] + (tt ** 3) * p3[0]
            y = (u ** 3) * p0[1] + 3 * (u ** 2) * tt * p1[1] + 3 * u * (tt ** 2) * p2[1] + (tt ** 3) * p3[1]
            pts.append((x, y))
        if len(pts) < 2:
            return

        # 线宽
        line_half_w = 1.6

        # 每个线段生成一个矩形（两个三角形），矩形的方向由相邻点连线决定
        # 由于段之间相邻，为了接缝美观这里简单用段方向挤出，不做 miter
        r, g, b = 1.0, 0.18, 0.22
        a = state.line_alpha

        verts = []
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            dx = x1 - x0
            dy = y1 - y0
            length = max(1e-4, math.hypot(dx, dy))
            # 法线
            nx = -dy / length
            ny = dx / length
            ox = nx * line_half_w
            oy = ny * line_half_w
            # 段头缘（越靠近终点越亮）——alpha 按 i 比例调节，使线有生长感
            seg_a = a * (0.75 + 0.25 * (i / max(1, len(pts) - 2)))
            # 四角
            ax0, ay0 = x0 - ox, y0 - oy
            bx0, by0 = x0 + ox, y0 + oy
            ax1, ay1 = x1 - ox, y1 - oy
            bx1, by1 = x1 + ox, y1 + oy
            verts.extend([
                ax0, ay0, r, g, b, seg_a,
                bx0, by0, r, g, b, seg_a,
                ax1, ay1, r, g, b, seg_a,
                ax1, ay1, r, g, b, seg_a,
                bx0, by0, r, g, b, seg_a,
                bx1, by1, r, g, b, seg_a,
            ])

        # 尾部加一个小圆点（一个边长略大的正方形）作为"连接点"
        end_x, end_y = pts[-1]
        half = 3.0
        bright = (1.0, 0.4, 0.45, a)
        br, bg, bb, ba = bright
        verts.extend([
            end_x - half, end_y - half, br, bg, bb, ba,
            end_x - half, end_y + half, br, bg, bb, ba,
            end_x + half, end_y - half, br, bg, bb, ba,
            end_x + half, end_y - half, br, bg, bb, ba,
            end_x - half, end_y + half, br, bg, bb, ba,
            end_x + half, end_y + half, br, bg, bb, ba,
        ])

        if not verts:
            return
        arr = self._np.array(verts, dtype='f4')
        # 缓冲区可能不够，这里数量可控：n_samples * 6 vertices * 6 floats = ~1152 floats < 4096*6*4 bytes
        self._col_vbo.write(arr.tobytes())
        self._col_vao.render(self._moderngl.TRIANGLES, vertices=len(verts) // 6)

    # ----- 符卡名 -----
    def _render_name(self, state: DeclarationRenderState):
        if self._name_texture is None:
            return
        cx, hw, hh = self._name_quad_metrics(state)

        self._name_texture.use(0)
        self._quad_prog['u_center'].value = (float(cx), float(state.name_cy))
        self._quad_prog['u_half_size'].value = (float(hw), float(hh))
        self._quad_prog['u_angle'].value = 0.0
        self._quad_prog['u_tint'].value = (1.0, 1.0, 1.0, state.name_alpha)
        self._quad_vao.render(self._moderngl.TRIANGLES, vertices=6)

    # ----- 清理 -----
    def cleanup(self):
        try:
            if self._name_texture is not None:
                self._name_texture.release()
            if self._band_texture is not None:
                self._band_texture.release()
        except Exception:
            pass
        self._name_texture = None
        self._band_texture = None

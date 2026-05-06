"""
src/game/emoji_danmaku
─────────────────────
QQ 群弹幕 emoji 子系统外观类。

用法（main.py 中）：
    from src.game.emoji_danmaku import EmojiDanmakuSystem

    # 初始化（在 GL 上下文建立后）
    emoji_sys = EmojiDanmakuSystem(
        ctx=ctx,
        screen_size=screen_size,
        game_viewport=game_viewport,
        panel_origin=(panel_origin_x, panel_origin_y),
    )
    emoji_sys.start()           # 启动 UDP 监听线程

    # 每帧更新（update 阶段）
    emoji_sys.update(dt, player)

    # 渲染（render 阶段）
    emoji_sys.render_game()               # 飘落 emoji + 发射弹（游戏区域层）
    emoji_sys.render_ui(ui_renderer)      # 热度条 + 抽奖文字（UI 层）

    # 退出时
    emoji_sys.stop()
"""

from typing import TYPE_CHECKING

# emoji_gl_renderer 依赖 moderngl，延迟到运行时导入（主进程有 GL 上下文）
from .emoji_pool import BASE_RENDER_PX_SIZE, EMOJI_LIST, EmojiObjectPool
from .heat_system import HeatSystem
from .udp_receiver import UDPReceiver

if TYPE_CHECKING:
    import moderngl
    from src.ui.ui_renderer import UIRenderer
    from .emoji_gl_renderer import EmojiGLRenderer

# ── 热度条 UI 配置 ────────────────────────────────────────────────────────────
# 与 assets/ui/hud_layout.json 中 section_heat_bg = [8, 386, 304, 182] 保持一致：
# 4 行：起始 y=402, 行距 40 → 402, 442, 482, 522（全部落在 section_heat_bg 内）
_BAR_WIDTH = 228       # 热度条宽度（像素）——加宽与面板内宽度协调
_BAR_HEIGHT = 12       # 热度条高度
_BAR_GAP = 40          # 行间距（给图标足够高度 + 行间呼吸）
_BAR_MARGIN_TOP = 402  # 相对 panel_origin_y 的顶部偏移（在 Graze/Point 的下方卡片内）
_ICON_SIZE = 28        # 图标显示尺寸（像素）
_ICON_OFFSET_X = 30    # 图标中心相对 panel_origin_x 的 X 偏移（bar 在图标右侧）

_HEAT_COLORS = {       # 每个 emoji 对应热度条填充色
    "😂": (255, 220, 50),
    "😡": (255, 70, 70),
    "💩": (160, 110, 50),
    "😅": (80, 200, 255),
}

# 抽奖大字显示的坐标（相对屏幕，居中于游戏区域）
_DRAW_TEXT_ALPHA_BG = 0.55   # 抽奖背景遮罩透明度

_GAME_Y_SCALE = 384.0 / 448.0


def _game_to_screen(
    gx: float, gy: float, gvx: int, gvy: int, gvw: int, gvh: int
) -> tuple[float, float]:
    """
    游戏坐标 → 屏幕像素坐标（中心）。

    游戏坐标：x ∈ [-1, 1]（左负右正），y ∈ [0, ~1]（底为 0，顶为 ~1）
    Y 轴：需要应用 y_scale_factor = 384/448，然后映射到视口高度。
    """
    sx = gvx + (gx + 1.0) / 2.0 * gvw
    # NDC_y = gy * Y_SCALE；NDC +1 → 视口顶部，-1 → 视口底部
    ndc_y = gy * _GAME_Y_SCALE
    sy = gvy + (1.0 - ndc_y) / 2.0 * gvh
    return sx, sy


def _screen_to_game(
    sx: float, sy: float, gvx: int, gvy: int, gvw: int, gvh: int
) -> tuple[float, float]:
    gx = (sx - gvx) / gvw * 2.0 - 1.0
    gy = (1.0 - (sy - gvy) / gvh * 2.0) / _GAME_Y_SCALE
    return gx, gy


def _emoji_radius_game(obj, gvw: int) -> float:
    px_radius = BASE_RENDER_PX_SIZE * float(getattr(obj, "scale", 1.0))
    px_radius *= float(getattr(obj, "hitbox_factor", 0.42))
    return px_radius / (gvw / 2.0)


class EmojiDanmakuSystem:
    """QQ 群 emoji 弹幕子系统。"""

    def __init__(
        self,
        ctx: "moderngl.Context",
        screen_size: tuple[int, int],
        game_viewport: tuple[int, int, int, int],
        panel_origin: tuple[int, int],
        udp_host: str = "127.0.0.1",
        udp_port: int = 9999,
    ) -> None:
        self.ctx = ctx
        self.screen_size = screen_size
        self.game_viewport = game_viewport
        self.gvx, self.gvy, self.gvw, self.gvh = game_viewport
        self.panel_origin = panel_origin

        self._receiver = UDPReceiver(host=udp_host, port=udp_port)
        self._pool = EmojiObjectPool(game_viewport)
        self._heat = HeatSystem()
        # 延迟导入：避免模块级 import moderngl 在无 GL 环境崩溃
        from .emoji_gl_renderer import EmojiGLRenderer  # noqa: PLC0415
        self._gl: "EmojiGLRenderer" = EmojiGLRenderer(ctx, screen_size, EMOJI_LIST)

    # ── 生命周期 ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """启动 UDP 监听后台线程。"""
        self._receiver.start()

    def stop(self) -> None:
        """停止 UDP 监听，释放 GL 资源。"""
        self._receiver.stop()
        self._gl.cleanup()

    def clear(self) -> None:
        """清空所有飘落 emoji 和发射弹（不清空热度状态）。
        Continue 复活时调用，避免一复活就被残余 emoji 弹打死。
        """
        self._pool.falling.clear()
        self._pool.projectiles.clear()

    # ── 主循环接口 ────────────────────────────────────────────────────────────

    def update(self, dt: float, player) -> None:
        """
        每帧调用（在 bullet_pool.update 之后）。

        player: 拥有 pos 属性 ([x, y] 游戏坐标) 的玩家对象。
        """
        # 1. 处理 UDP 事件
        for ev in self._receiver.poll():
            emoji = ev["emoji"]
            self._heat.add_heat(emoji)
            self._pool.spawn_falling(emoji)

        # 2. 更新池（飘落 + 发射弹）
        self._pool.update(dt)

        # 3. 推进热度状态机
        self._heat.update(dt)

        # 4. 若本帧触发发射 → 生成弹幕
        if self._heat.fire_ready:
            self._do_fire(player)

    def render_game(self) -> None:
        """渲染飘落 emoji 和发射弹（在游戏区域层，位于 HUD 之前调用）。"""
        import moderngl as mgl
        self.ctx.enable(mgl.BLEND)
        self.ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA
        all_objs = self._pool.falling + self._pool.projectiles
        self._gl.render_list(all_objs, clip_rect=self.game_viewport)

    def render_ui(self, ui_renderer: "UIRenderer") -> None:
        """
        渲染热度条 + 抽奖动画文字（在 ui_renderer.render_hud 之后调用）。
        """
        ox, oy = self.panel_origin
        import moderngl as mgl
        self.ctx.enable(mgl.BLEND)
        self.ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA

        for i, emoji in enumerate(EMOJI_LIST):
            # 图标居中对齐热度条中线
            icon_cx = ox + _ICON_OFFSET_X
            bar_x = icon_cx + _ICON_SIZE // 2 + 4   # bar 紧接图标右侧
            bar_y = oy + _BAR_MARGIN_TOP + i * _BAR_GAP
            icon_cy = bar_y + _BAR_HEIGHT // 2       # 图标垂直居中于 bar

            heat_r = self._heat.heat_ratio(emoji)
            fill_color = _HEAT_COLORS.get(emoji, (200, 200, 200))

            # ── 热度条 ────────────────────────────────────────────────────────
            ui_renderer.render_bar(
                x=bar_x, y=bar_y,
                width=_BAR_WIDTH, height=_BAR_HEIGHT,
                value=heat_r,
                color_bg=(30, 30, 30),
                color_fill=fill_color,
                alpha=0.88,
            )

            # ── emoji 图标（GL 渲染，支持真实纹理）────────────────────────────
            is_drawing_this = (self._heat.drawing_emoji == emoji and self._heat.is_drawing())
            icon_alpha = 1.0
            icon_scale = _ICON_SIZE / BASE_RENDER_PX_SIZE

            if is_drawing_this:
                # 闪烁效果
                flash = 0.9 if (int(self._heat.draw_timer * 8) % 2 == 0) else 0.4
                icon_alpha = flash
                icon_scale *= 1.25   # 轻微放大强调

            self._gl.render_object(
                emoji,
                x=icon_cx,
                y=icon_cy,
                scale=icon_scale,
                rotation_deg=0.0,
                alpha=icon_alpha,
            )

            # 满热度时热度条外框高亮
            if is_drawing_this:
                flash = 0.85 if (int(self._heat.draw_timer * 8) % 2 == 0) else 0.2
                ui_renderer.render_rect(
                    x=bar_x - 1, y=bar_y - 1,
                    width=_BAR_WIDTH + 2, height=_BAR_HEIGHT + 2,
                    color=fill_color, alpha=flash * 0.45,
                )

        # 抽奖大字（显示在游戏区域中央偏上）
        if self._heat.is_drawing():
            self._render_draw_overlay(ui_renderer)

    # ── 内部 ─────────────────────────────────────────────────────────────────

    def check_player_collision(self, player) -> bool:
        """
        检测外部 emoji 飘落弹/发射弹与玩家判定点的碰撞，在游戏坐标系中进行。
        若命中则消弹 + 返回 True（由 main.py 负责调用 player.take_damage()）。

        坐标系：
          player.get_hit_position() → 游戏坐标 (x ∈[-1,1], y ∈[-1,~1])
          emoji 弹储存的是屏幕像素坐标，先逆变换到游戏坐标再比较，
          避免 Y_SCALE 带来的误差。
        """
        collidable = self._pool.falling + self._pool.projectiles
        if not collidable:
            return False

        hit_x, hit_y = player.get_hit_position()

        # ── 屏幕像素 → 游戏坐标的逆变换 ─────────────────────────────────────
        # 正变换（_game_to_screen）：
        #   sx = gvx + (gx + 1) / 2 * gvw
        #   ndc_y = gy * Y_SCALE
        #   sy = gvy + (1 - ndc_y) / 2 * gvh
        # 逆变换：
        #   gx = (sx - gvx) / gvw * 2 - 1
        #   gy = (1 - (sy - gvy) / gvh * 2) / Y_SCALE
        gvx, gvy, gvw, gvh = self.gvx, self.gvy, self.gvw, self.gvh

        hit_occurred = False
        for obj in collidable:
            if not obj.alive:
                continue
            # 逆变换
            gx, gy = _screen_to_game(obj.x, obj.y, gvx, gvy, gvw, gvh)
            dx = gx - hit_x
            dy = gy - hit_y
            threshold_sq = (player.hit_radius + _emoji_radius_game(obj, gvw)) ** 2
            if dx * dx + dy * dy < threshold_sq:
                obj.alive = False
                hit_occurred = True
                break

        if hit_occurred:
            self._pool.falling = [p for p in self._pool.falling if p.alive]
            self._pool.projectiles = [p for p in self._pool.projectiles if p.alive]
        return hit_occurred

    def _do_fire(self, player) -> None:
        """根据抽奖结果生成发射弹。"""
        emoji = self._heat.fire_emoji
        pattern = self._heat.fire_pattern

        # 发射弹的起始位置：游戏区上方中央
        ox = self.gvx + self.gvw / 2.0
        oy = float(self.gvy + 30)

        # 玩家屏幕坐标（用于自机狙）
        px_g, py_g = float(player.pos[0]), float(player.pos[1])
        player_sx, player_sy = _game_to_screen(
            px_g, py_g, self.gvx, self.gvy, self.gvw, self.gvh
        )

        if pattern == "开花":
            self._pool.spawn_bloom(emoji, ox, oy, count=16)
        elif pattern == "自机狙":
            self._pool.spawn_aimed(emoji, ox, oy, player_sx, player_sy)
        elif pattern == "散射弹":
            self._pool.spawn_scatter(emoji, ox, oy)

    def _render_draw_overlay(self, ui_renderer: "UIRenderer") -> None:
        """在游戏区域中央渲染抽奖动画文字覆盖层。"""
        label = self._heat.current_draw_label()
        if not label:
            return
        alpha = self._heat.draw_alpha()
        emoji = self._heat.drawing_emoji or ""

        # 半透明黑色背景条
        overlay_w = 180
        overlay_h = 60
        cx = self.gvx + self.gvw // 2
        cy = self.gvy + int(self.gvh * 0.35)

        ui_renderer.render_rect(
            x=cx - overlay_w // 2,
            y=cy - overlay_h // 2,
            width=overlay_w,
            height=overlay_h,
            color=(0, 0, 0),
            alpha=_DRAW_TEXT_ALPHA_BG,
        )

        # 上方小字"抽奖中 / 触发者 emoji"
        ui_renderer.render_text(
            f"DRAW  [{emoji}]",
            x=cx, y=cy - overlay_h // 2 + 6,
            font_name="score", scale=0.9,
            color=(220, 220, 220), alpha=alpha * 0.8,
            align="center",
        )

        # 大字结果
        ui_renderer.render_text(
            label,
            x=cx, y=cy - overlay_h // 2 + 26,
            font_name="score", scale=2.0,
            color=(255, 240, 80), alpha=alpha,
            align="center",
        )

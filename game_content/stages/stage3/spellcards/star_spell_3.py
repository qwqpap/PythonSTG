"""
华丽星地「周口店：星辰坠落的沉积层」

三层弹幕设计：
  第一层（背景）：Boss在最上方连续乱射极细快速蓝色针弹（星雨氛围）
  第二层（核心）：从顶部落下带有重力加速的大型彩色圆球（沉积岩）
  第三层（触地）：大球落到底部时在原位爆发出碎石扇形（地壳沉积爆发）
"""

import random
import math
from src.game.stage.spellcard import SpellCard
from src.game.bullet.optimized_pool import CURVE_LINEAR_SPEED


# 沉积岩的颜色序列（模拟不同地质年代的岩层）
_STRATA_COLORS = [
    "orange",   # 志留纪
    "red",      # 泥盆纪
    "darkred",  # 石炭纪
    "purple",   # 二叠纪
    "blue",     # 三叠纪
    "cyan",     # 侏罗纪
    "green",    # 白垩纪
    "yellow",   # 古近纪
]


class StarSpell3(SpellCard):
    """
    华丽星地「周口店：星辰坠落的沉积层」
    """

    def __init__(self):
        super().__init__()
        # 追踪落石的 bullet_idx → 发射时刻（用于估算何时触底）
        self._rocks = []          # list of (idx, launch_frame, x_pos, color)
        self._pending_impacts = []  # list of (x, color) 等待主循环处理的触底爆炸

    async def run(self):
        # Boss 飞到最顶部中央
        await self.boss.move_to(0.0, 0.94, duration=60)
        await self.wait(20)

        self.play_se("lazer", volume=0.3)

        frame = 0
        strata_index = 0
        rock_cd = 0          # 落石冷却
        needle_cd = 0        # 针弹冷却

        while True:
            bx = self.boss.x
            by = self.boss.y

            # ============================================================
            # 第一层：背景星雨（极快极细的针弹，随机全方位发射）
            # ============================================================
            needle_cd += 1
            if needle_cd >= 3:
                needle_cd = 0
                # 随机选一个向下半球方向
                angle = random.uniform(-175, -5)
                self.fire(
                    x=bx + random.uniform(-0.3, 0.3),
                    y=by,
                    angle=angle,
                    speed=22.0,           # 极高速，瞬间穿过屏幕
                    bullet_type="needle",
                    color="blue",
                )

            # ============================================================
            # 第二层：重力沉积岩（带加速度的大球）
            # ============================================================
            rock_cd += 1
            rock_interval = max(40, 90 - frame // 60)  # 随时间越来越密集
            if rock_cd >= rock_interval:
                rock_cd = 0

                rock_x = random.uniform(-0.85, 0.85)
                rock_color = _STRATA_COLORS[strata_index % len(_STRATA_COLORS)]
                strata_index += 1

                # 使用 CURVE_LINEAR_SPEED 模拟重力加速
                # context.py 把 speed 除以 60 再存储，curve_params 也需同步：
                # stored_speed = base + amp * t（t 为秒）
                # base = script_speed / 60, amp = 加速度 / 60
                # 初速 4.0 NDC/s，加速 8.0 NDC/s²
                idx = self.fire(
                    x=rock_x,
                    y=1.1,
                    angle=-90,
                    speed=4.0,
                    bullet_type="ball_l",
                    color=rock_color,
                    curve_type=CURVE_LINEAR_SPEED,
                    curve_params=(8.0/60, 0.0, 0.0, 4.0/60),
                )
                if idx >= 0:
                    self._rocks.append((idx, frame, rock_x, rock_color))

            # ============================================================
            # 检测落石是否触底（y < -0.9）→ 加入爆炸队列
            # ============================================================
            still_alive = []
            for (idx, lf, rx, rc) in self._rocks:
                if not self.ctx.bullet_pool.data['alive'][idx]:
                    # 已死亡（飞出屏幕边界），触发触底爆炸
                    self._pending_impacts.append((rx, rc))
                else:
                    # 检查当前 y 坐标
                    cy = float(self.ctx.bullet_pool.data['pos'][idx][1])
                    if cy < -1.14:  # 真实屏幕底部 ≈ -1.167 (y_scale=384/448)
                        # 触底爆炸：取当前实际 x 位置
                        cx = float(self.ctx.bullet_pool.data['pos'][idx][0])
                        self.ctx.bullet_pool.data['alive'][idx] = 0
                        self._pending_impacts.append((cx, rc))
                    else:
                        still_alive.append((idx, lf, rx, rc))
            self._rocks = still_alive

            # ============================================================
            # 第三层：触底爆炸（碎石向上扇形散射）
            # ============================================================
            for (ex, ec) in self._pending_impacts:
                self.play_se("tan00", volume=0.1)
                # 第一圈：贴地的低速碎石，向上半圆扇形
                for i in range(10):
                    angle = random.uniform(5, 175)
                    self.fire(
                        x=ex, y=-1.14,
                        angle=angle,
                        speed=random.uniform(4.0, 9.0),
                        bullet_type="ball_m",
                        color=ec,
                    )
                # 第二圈：少量极速碎石弹高
                for _ in range(4):
                    angle = random.uniform(40, 140)
                    self.fire(
                        x=ex, y=-1.14,
                        angle=angle,
                        speed=random.uniform(12.0, 18.0),
                        bullet_type="grain_a",
                        color=ec,
                    )
            self._pending_impacts.clear()

            # ============================================================
            # Boss 本体左右轻微漂移（让星雨覆盖更宽的区域）
            # ============================================================
            if frame % 120 == 0:
                target_x = random.uniform(-0.6, 0.6)
                # 一帧内只微移，不 await（非阻塞）
                self.boss.x += (target_x - self.boss.x) * 0.15

            frame += 1
            await self.wait(1)

"""
月符「月光回廊」

Boss 以椭圆轨道绕场心公转，
同时向外辐射等距子弹（形成旋臂螺旋），
并定期向玩家发射刀形三连击，逼迫玩家在弧形走廊里穿行。
"""

import math
import random
from src.game.stage.spellcard import SpellCard


class LunaSpell4(SpellCard):
    """月符「月光回廊」"""

    # ── 轨道参数 ───────────────────────
    ORBIT_CX      = 0.0        # 椭圆圆心 x
    ORBIT_CY      = 0.58       # 椭圆圆心 y
    ORBIT_RX      = 0.50       # 椭圆 x 半轴
    ORBIT_RY      = 0.28       # 椭圆 y 半轴（纵向压缩，保持在屏幕内）
    ORBIT_SPEED   = 1.0        # 度/帧，约6秒一圈
    # ── 旋臂参数 ───────────────────────
    ARM_COUNT     = 3          # 螺旋臂数量
    ARM_INTERVAL  = 6          # 每几帧打一排旋臂子弹
    ARM_SPEED     = 4.2        # 提高旋臂压迫感，减少慢速悬空层
    # ── 压制参数 ───────────────────────
    AIM_INTERVAL  = 55         # 每几帧打一次三连刀
    AIM_SPREAD    = 16         # 三连刀扩散角度
    AIM_SPEED     = 6.5
    # ── 尾迹参数 ───────────────────────
    TRAIL_INTERVAL = 12        # 每几帧在 Boss 身后留一颗漂浮弹
    # ────────────────────────────────────

    async def setup(self):
        # 移动到公转起点（椭圆最右端）
        sx = self.ORBIT_CX + self.ORBIT_RX
        sy = self.ORBIT_CY
        await self.boss.move_to(sx, sy, duration=70)

    async def run(self):
        orbit_angle = 0.0   # 公转角度（度），0=最右端
        arm_phase   = 0.0   # 旋臂相位（随时间旋转，制造螺旋感）
        frame = 0

        while True:
            # ── Boss 公转 ──────────────────────────────────
            rad = math.radians(orbit_angle)
            bx = self.ORBIT_CX + self.ORBIT_RX * math.cos(rad)
            by = self.ORBIT_CY + self.ORBIT_RY * math.sin(rad)
            self.boss.x = bx
            self.boss.y = by

            # ── 旋臂辐射（以 boss 为中心向外打 ARM_COUNT 方向） ──
            if frame % self.ARM_INTERVAL == 0:
                for i in range(self.ARM_COUNT):
                    a = arm_phase + (360.0 / self.ARM_COUNT) * i
                    self.fire(
                        angle=a,
                        speed=self.ARM_SPEED,
                        bullet_type='ball_s',
                        color='blue',
                    )
                    # 同臂反向（内旋），让玩家有来自两侧的压力
                    self.fire(
                        angle=a + 180,
                        speed=self.ARM_SPEED * 0.65,
                        bullet_type='ball_s',
                        color='cyan',
                    )
                arm_phase = (arm_phase + 4.5) % 360   # 每次偏转，螺旋渐密

            # ── 三连刀追机 ──────────────────────────────────
            if frame % self.AIM_INTERVAL == 0:
                self.play_se('tan01', volume=0.4)
                for offset in (-self.AIM_SPREAD, 0, self.AIM_SPREAD):
                    self.fire_at_player(
                        speed=self.AIM_SPEED,
                        offset_angle=offset,
                        bullet_type='knife',
                        color='white',
                    )

            # ── 公转尾迹（球形漂浮） ────────────────────────
            if frame % self.TRAIL_INTERVAL == 0:
                # 在 Boss 正后方（切线方向）留一颗低速球
                tang_angle = orbit_angle + 90   # 切线方向
                self.fire(
                    angle=tang_angle + 180,     # 向后
                    speed=random.uniform(1.8, 2.8),
                    bullet_type='ball_m',
                    color='purple',
                )

            orbit_angle = (orbit_angle + self.ORBIT_SPEED) % 360
            frame += 1
            await self.wait(1)

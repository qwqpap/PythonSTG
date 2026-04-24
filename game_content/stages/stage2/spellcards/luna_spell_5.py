"""
幻符「月归昌平」（Last Spellcard）

三层弹幕叠加的最终符卡：
  Layer A  花瓣环：每 45 帧发一圈 butterfly 子弹，相位每圈偏转
           形成慢速但逐渐填满屏幕的花瓣幕墙。
  Layer B  追机流星：每 5 帧发一发 arrow_s 自机狙，速度偏快，
           三连尖扩散，强迫玩家持续微移（无法固定站位）。
  Layer C  交叉刀雨：左右两侧定期射出对角刀流，在场中形成
           移动的"X"型死亡网格，切断玩家常用路径。
Boss 本体在上方缓慢做 8 字形游移，让子弹发射原点不断变化。
"""

import math
import random
from src.game.stage.spellcard import SpellCard


class LunaSpell5(SpellCard):
    """幻符「月归昌平」"""

    async def setup(self):
        await self.boss.move_to(0.0, 0.82, duration=70)

    async def run(self):
        frame = 0
        petal_phase = 0.0       # 花瓣环相位，每圈旋转

        # 8 字形游移参数
        LISSAJOUS_AX = 0.32
        LISSAJOUS_AY = 0.08
        LISSAJOUS_FREQ_X = 0.012
        LISSAJOUS_FREQ_Y = 0.024

        while True:
            # ── Boss 8 字游移 ─────────────────────────────
            bx = LISSAJOUS_AX * math.sin(frame * LISSAJOUS_FREQ_X)
            by = 0.82 + LISSAJOUS_AY * math.sin(frame * LISSAJOUS_FREQ_Y)
            self.boss.x = bx
            self.boss.y = by

            # ── Layer A：花瓣环 ────────────────────────────
            # 每 45 帧一圈，慢速花瓣铺屏
            if frame % 45 == 0:
                PETAL_N = 20
                for i in range(PETAL_N):
                    a = petal_phase + (360.0 / PETAL_N) * i
                    self.fire(
                        angle=a,
                        speed=1.4,
                        bullet_type='butterfly',
                        color='purple',
                        render_angle=a,
                    )
                petal_phase = (petal_phase + 9.0) % 360   # 每圈转 9°

            # 每 90 帧额外补一圈小球（错相位），加密间隙
            if frame % 90 == 45:
                PETAL_N2 = 16
                for i in range(PETAL_N2):
                    a = petal_phase + (360.0 / PETAL_N2) * i + 11
                    self.fire(
                        angle=a,
                        speed=1.1,
                        bullet_type='ball_s',
                        color='white',
                    )

            # ── Layer B：追机流星 ──────────────────────────
            if frame % 5 == 0:
                for offset in (-14, 0, 14):
                    self.fire_at_player(
                        speed=6.5,
                        offset_angle=offset,
                        bullet_type='arrow_s',
                        color='yellow',
                    )

            # ── Layer C：交叉刀雨（每 48 帧左右交替） ────────
            #  左侧 → 右下；右侧 → 左下；形成 X 形交叉网
            if frame % 48 == 0:
                self.play_se('tan00', volume=0.25)
                for i in range(7):
                    self.fire(
                        x=-1.15,
                        y=1.0 - i * 0.10,
                        angle=-45 + i * 1.5,
                        speed=22.0,
                        bullet_type='knife',
                        color='cyan',
                    )
            if frame % 48 == 24:
                self.play_se('tan00', volume=0.25)
                for i in range(7):
                    self.fire(
                        x=1.15,
                        y=1.0 - i * 0.10,
                        angle=-135 - i * 1.5,
                        speed=22.0,
                        bullet_type='knife',
                        color='cyan',
                    )

            # ── 每 120 帧一次大爆发（阶段性压制高潮） ────────
            if frame % 120 == 90:
                self.play_se('tan01', volume=0.6)
                # 32 颗心形弹全方位散开
                for i in range(32):
                    a = (360.0 / 32) * i
                    self.fire(
                        angle=a,
                        speed=2.8 + random.uniform(-0.3, 0.3),
                        bullet_type='heart',
                        color='purple',
                        render_angle=a,
                    )

            frame += 1
            await self.wait(1)

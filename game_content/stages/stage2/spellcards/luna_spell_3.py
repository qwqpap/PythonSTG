import random
from src.game.stage.spellcard import SpellCard
from src.game.bullet.optimized_pool import CURVE_LINEAR_SPEED
from src.game.bullet.tags import TAG_BOMB_PROTECTED_GRID

class LunaSpell3(SpellCard):
    """
    网符「交织的死亡菱形」
    - 屏幕左右两侧各有一个固定发射源持续散发子弹，在中央交织成快速下移的菱形无伤孔径网格。
    - Boss沿着上面左右缓慢平移，向下抛洒有重力的红色随机散弹。
    """

    async def setup(self):
        # LunaSpell2 uses its own cpline.png background; restore the shared boss
        # background for the remaining Stage 2 boss phases.
        self.ctx.set_background("luastg_gzz_stage04bg")
        await self.boss.move_to(0.0, 0.8, duration=60)
        
    async def run(self):
        frame = 0
        boss_target_x = 1.2
        boss_speed = 0.012
        
        while True:
            # 1. 左右两侧固定发射源：制造菱形网格
            # 定时发射，间隙足够宽以供自机躲避。蓝色表示极具规律的边界网格墙。
            if frame % 36 == 0:
                # 左侧发射源：(-1.4, 1.4)，向右下方 (-45度)
                self.fire_arc(
                    x=-1.5, y=1.4,
                    count=6, speed=24.5,
                    center_angle=-45, arc_angle=60,
                    bullet_type="knife", color="cyan",
                    tag=TAG_BOMB_PROTECTED_GRID,
                )
                
                # 右侧发射源：(1.4, 1.4)，向左下方 (-135度)
                self.fire_arc(
                    x=1.5, y=1.4,
                    count=6, speed=24.5,
                    center_angle=-135, arc_angle=60,
                    bullet_type="knife", color="cyan",
                    tag=TAG_BOMB_PROTECTED_GRID,
                )
                
            # 2. Boss 本体的运动：缓慢在顶部左右巡逻
            if self.boss.x < boss_target_x:
                self.boss.x += boss_speed
            elif self.boss.x > boss_target_x:
                self.boss.x -= boss_speed
            
            # 转弯判定
            if abs(self.boss.x - boss_target_x) < 0.05:
                boss_target_x = -boss_target_x
                
            # 3. Boss 本体的攻击：具有重力加速度的红色散弹盲投掷
            if frame % 6 == 0:
                self.play_se("tan00", volume=0.15)
                # 微量发射，但随着时间的积累会因为重力不同产生交错
                for _ in range(2):
                    self.fire(
                        x=self.boss.x + random.uniform(-0.15, 0.15),
                        y=self.boss.y - 0.1,
                        angle=random.uniform(-110, -70), # 垂直向下展开一些偏差
                        speed=2.8,      # 提高初速，避免长时间悬在上半区
                        bullet_type="ball_m", 
                        color="red",    # 与青色交叉网格产生绝对的区别
                        curve_type=CURVE_LINEAR_SPEED,
                        curve_params=(0.16, 0.0, 0.0, 2.8) # 更快压向玩家区
                    )

            # 4. Boss 附加压迫判定：低频自机狙，逼迫玩家产生位移
            if frame % 50 == 0:
                self.play_se("tan01", volume=0.3)
                # 发射一组判定明显的黄色追踪锥弹
                self.fire_arc(
                    x=self.boss.x,
                    y=self.boss.y,
                    count=3,
                    speed=15.5,
                    center_angle=self.angle_to_player(),
                    arc_angle=20, 
                    bullet_type="arrow_m",
                    color="yellow"
                )

            frame += 1
            await self.wait(1)

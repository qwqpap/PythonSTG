import math
import random
from src.game.stage.enemy_script import EnemyScript
from src.content_api import CURVE_LINEAR_SPEED


class StressYinYang(EnemyScript):
    """
    应力阴阳玉
    模拟构造应力释放的机制：它会在半空中停留较长时间，缓慢掉落震荡晶体（积聚），
    最后一次性释放极具压迫感的多向强力扫射（断层破裂）。
    """
    def __init__(self):
        super().__init__()
        self.sprite = "enemy2"
        self.hp = 35
        self.score = 2500

    async def run(self):
        # 1. 缓缓降入场中
        start_x = self.x
        target_y = random.uniform(0.6, 0.9)
        
        await self.move_to(start_x, target_y, duration=50)
        
        # 2. 积聚应力：发出低哑的摩擦声和掉落小碎片
        for _ in range(4):
            self.fire_arc(
                x=self.x, y=self.y,
                count=6, speed=11.2,
                center_angle=-90, arc_angle=120, # 向下半圆散落
                bullet_type="grain_a", color="darkred"
            )
            await self.wait(20)
            
        # 3. 应力断层爆发！
        self.play_se("tan01", volume=0.4)
        base_angle = self.angle_to_player()
        
        # 发射连续极速的交叉破片列阵
        for i in range(8):
            self.fire_circle(
                x=self.x, y=self.y,
                count=10, 
                speed=12.0 + i * 1.5,     # 速度疯狂递进，形成恐怖的鞭打感
                start_angle=base_angle + i * 8, # 带有小幅旋转
                bullet_type="arrow_l",   # 巨大的箭头破片
                color="red"
            )
            await self.wait(4)
            
        await self.wait(30)
        
        # 4. 断裂后失重坠毁
        self.speed = 16.0
        self.angle = -90 # PySTG 中 -90 或 270 是向下
        await self.wait(45)
        self.kill()

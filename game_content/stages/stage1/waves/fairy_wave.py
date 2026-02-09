"""
妖精编队波次 - Stage 1

几个妖精从屏幕两侧飞入，发射散布弹后飞走。
比开场稍难，开始出现需要走位的弹幕。
"""

from src.game.stage.wave_base import Wave
import random


class FairyWave(Wave):
    """妖精编队 - 散布弹"""
    
    async def run(self):
        # 5组散布弹，从随机位置发射
        for group in range(5):
            x = random.uniform(-0.7, 0.7)
            
            # 每组发射一个小圆
            self.fire_circle(
                x=x, y=0.9,
                count=8, speed=5.2,
                start_angle=random.uniform(0, 45),
                bullet_type="ball_s", color="green"
            )
            
            await self.wait(20)  # 间隔约 0.33 秒
        
        # 等待子弹飞出
        await self.wait(60)


wave = FairyWave

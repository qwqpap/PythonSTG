"""
道中 Boss 后收尾波次 - Stage 1

道中 Boss 击破后到关底 Boss 之前的过渡。
中等密度的弹幕，让玩家回收道具后继续保持紧张感。
"""

from src.game.stage.wave_base import Wave


class PostMidbossWave(Wave):
    """道中 Boss 后的收尾"""
    
    async def run(self):
        # 中等密度的黄色弹幕，从中央扩散
        for burst in range(6):
            self.fire_circle(
                x=0.0, y=0.8,
                count=12, speed=5.0,
                start_angle=burst * 15,
                bullet_type="ball_m", color="yellow"
            )
            
            await self.wait(15)
        
        # 等待
        await self.wait(90)


wave = PostMidbossWave

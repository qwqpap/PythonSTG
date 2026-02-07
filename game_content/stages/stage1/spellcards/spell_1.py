"""
月符「Moonlight Ray」- 露米娅的第一张符卡

特点：圆形扩散 + 自机狙射线 + 后期螺旋弹

设计思路：
  - 前 15 秒：圆形弹幕 + 自机狙，节奏稳定
  - 15 秒后加入螺旋弹，难度提升
  - 旋转角度每帧递增，产生"月光旋转"效果
"""

from src.game.stage.spellcard import SpellCard


class MoonlightRay(SpellCard):
    """月符「Moonlight Ray」"""
    
    name = "月符「Moonlight Ray」"
    hp = 1200
    time_limit = 60
    bonus = 1000000
    
    async def setup(self):
        """Boss 移动到中央上方"""
        await self.boss.move_to(0, 0.5, duration=60)
    
    async def run(self):
        """主弹幕逻辑"""
        angle_offset = 0
        
        while True:
            # === 第一层：圆形扩散 ===
            self.fire_circle(
                count=20,
                speed=2.5,
                start_angle=angle_offset,
                bullet_type="ball_m",
                color="blue"
            )
            angle_offset += 10
            
            await self.wait(8)
            
            # === 第二层：自机狙射线 ===
            if self.time % 60 < 30:
                for i in range(5):
                    self.fire_at_player(
                        speed=3.0 + i * 0.2,
                        bullet_type="ball_l",
                        color="white"
                    )
                    await self.wait(3)
            
            await self.wait(20)
            
            # === 第三层：螺旋弹幕（15秒后增加难度）===
            if self.time_seconds > 15:
                for arm in range(3):
                    base_angle = angle_offset + arm * 120
                    for i in range(6):
                        self.fire(
                            angle=base_angle + i * 5,
                            speed=1.5 + i * 0.1,
                            bullet_type="scale",
                            color="purple"
                        )
                    await self.wait(2)
            
            await self.wait(30)


spellcard = MoonlightRay

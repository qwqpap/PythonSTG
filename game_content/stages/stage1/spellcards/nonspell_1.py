"""
非符攻击 1

露米娅的第一段非符
特点：简单的圆形弹幕
"""

from src.game.stage.spellcard import NonSpell


class NonSpell1(NonSpell):
    """第一段通常攻击"""
    
    hp = 800
    time_limit = 30
    
    async def setup(self):
        await self.boss.move_to(0, 0.5, duration=30)
    
    async def run(self):
        angle = 0
        
        while True:
            # 简单的圆形弹幕
            self.fire_circle(
                count=16,
                speed=2.0,
                start_angle=angle,
                bullet_type="ball_m",
                color="red"
            )
            angle += 15
            
            await self.wait(20)
            
            # 偶尔自机狙
            if self.time % 120 < 60:
                self.fire_at_player(
                    speed=2.5,
                    bullet_type="rice",
                    color="white"
                )
            
            await self.wait(10)


spellcard = NonSpell1

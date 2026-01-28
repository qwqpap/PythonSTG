"""
月符「Moonlight Ray」

露米娅的第一张符卡
特点：月光射线 + 圆形弹幕

注意：使用 yield from self.wait() 风格，不是 await
"""

from src.game.stage.spellcard import SpellCard
import math


class MoonlightRay(SpellCard):
    """月符「Moonlight Ray」"""
    
    name = "月符「Moonlight Ray」"
    hp = 1200
    time_limit = 60
    bonus = 1000000
    
    def setup(self):
        """Boss 移动到中央上方"""
        yield from self.boss.move_to(0, 0.5, duration=60)
    
    def run(self):
        """主弹幕逻辑"""
        angle_offset = 0
        
        while True:
            # === 第一阶段：圆形扩散 ===
            # 发射36发蓝色圆弹
            self.fire_circle(
                count=20,
                speed=2.5,
                start_angle=angle_offset,
                bullet_type="ball_m",
                color="blue"
            )
            angle_offset += 10  # 每次旋转
            
            yield from self.wait(8)
            
            # === 第二阶段：自机狙射线 ===
            # 每隔一段时间发射指向玩家的射线
            if self.time % 60 < 30:  # 前半段
                for i in range(5):
                    self.fire_at_player(
                        speed=3.0 + i * 0.2,
                        bullet_type="ball_l",
                        color="white"
                    )
                    yield from self.wait(3)
            
            yield from self.wait(20)
            
            # === 第三阶段：螺旋弹幕 ===
            if self.time_seconds > 15:  # 15秒后增加难度
                for arm in range(3):
                    base_angle = angle_offset + arm * 120
                    for i in range(6):
                        self.fire(
                            angle=base_angle + i * 5,
                            speed=1.5 + i * 0.1,
                            bullet_type="scale",
                            color="purple"
                        )
                    yield from self.wait(2)
            
            yield from self.wait(30)


# 注册符卡（用于动态加载）
spellcard = MoonlightRay

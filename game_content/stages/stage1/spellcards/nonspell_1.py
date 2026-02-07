"""
非符攻击 1 - 露米娅

第一段通常攻击（非符）。
特点：简单的圆形弹幕 + 偶尔自机狙。

这是最简单的 SpellCard 示例。
学习要点：
  1. 继承 NonSpell（非符基类）
  2. setup() 中移动 Boss
  3. run() 中用 while True 循环发弹
  4. 用 self.fire_circle / self.fire_at_player 发射弹幕
  5. 用 await self.wait(frames) 控制节奏
"""

from src.game.stage.spellcard import NonSpell


class NonSpell1(NonSpell):
    """第一段通常攻击"""
    
    hp = 800
    time_limit = 30
    
    async def setup(self):
        """Boss 移动到上方中央"""
        await self.boss.move_to(0, 0.5, duration=30)
    
    async def run(self):
        """主弹幕逻辑"""
        angle = 0
        
        while True:
            # ——— 圆形弹幕 ———
            # 发射 16 发红色中弹，旋转展开
            self.fire_circle(
                count=16,
                speed=2.0,
                start_angle=angle,
                bullet_type="ball_m",
                color="red"
            )
            angle += 15  # 每次旋转 15 度
            
            await self.wait(20)
            
            # ——— 自机狙 ———
            # 每 2 秒中的前 1 秒发射白色米弹指向玩家
            if self.time % 120 < 60:
                self.fire_at_player(
                    speed=2.5,
                    bullet_type="rice",
                    color="white"
                )
            
            await self.wait(10)


# 注册符卡（boss.json 的 script 字段会自动查找这个变量）
spellcard = NonSpell1

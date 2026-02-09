"""
红色妖精 - Stage 1 基础杂兵

最简单的敌人脚本示例。
飞入 → 发射几发弹幕 → 飞走。
"""

from src.game.stage.enemy_script import EnemyScript


class RedFairy(EnemyScript):
    """红色妖精 - 从上方飞入，发射散弹后飞走"""
    
    hp = 30
    sprite = "enemy_fairy_red"
    score = 100
    
    async def run(self):
        # 从当前位置飞到 y=0.3
        await self.move_to(self.x, 0.3, duration=60)
        
        # 发射 3 轮 8-way 圆弹
        for _ in range(3):
            self.fire_circle(
                count=8, speed=2.0,
                bullet_type="ball_s", color="red"
            )
            await self.wait(20)
        
        # 飞出屏幕
        await self.move_to(self.x, -0.2, duration=60)


class BlueFairy(EnemyScript):
    """蓝色妖精 - 从侧面飞入，发射自机狙后飞走"""
    
    hp = 30
    sprite = "enemy_fairy_blue"
    score = 100
    
    async def run(self):
        # 横向飞入到目标位置
        target_x = -self.x  # 从左到右或从右到左
        await self.move_to(target_x, self.y, duration=90)
        
        # 每隔 10 帧发射自机狙
        for _ in range(5):
            self.fire_at_player(
                speed=2.5,
                bullet_type="ball_s", color="blue"
            )
            await self.wait(10)
        
        # 继续飞走
        await self.move_linear(dx=target_x * 0.5, dy=-0.3, duration=60)

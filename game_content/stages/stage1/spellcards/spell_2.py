"""
夜符「Night Bird」- 露米娅的第二张符卡

特点：V字鸟群弹幕 + Boss 随机移动 + 大波攻击

设计思路：
  - Boss 在场上随机移动，边移动边发射 V 字形弹幕
  - 移动结束后释放一次大波圆形扩散
  - 通过随机移动增加不确定性
  
高级技巧演示：
  - 在 run() 中同时驱动移动和火力
  - 抽取辅助方法 _fire_bird_pattern / _fire_wave_attack
"""

from src.game.stage.spellcard import SpellCard
import random


class NightBird(SpellCard):
    """夜符「Night Bird」"""
    
    name = "夜符「Night Bird」"
    hp = 1500
    time_limit = 60
    bonus = 1500000
    
    async def setup(self):
        """初始位置"""
        await self.boss.move_to(0, 0.6, duration=45)
    
    async def run(self):
        """主弹幕逻辑 - 夜鸟飞舞"""
        
        while True:
            # 随机移动
            target_x = random.uniform(-0.6, 0.6)
            target_y = random.uniform(0.3, 0.7)
            
            # 边移动边发射
            move_coro = self.boss.move_to(target_x, target_y, duration=90)
            
            for _ in range(90):
                # 推进移动
                try:
                    next(move_coro)
                except StopIteration:
                    pass
                
                # 每隔几帧发射一组"鸟形"弹幕
                if self.time % 6 == 0:
                    await self._fire_bird_pattern()
                
                yield
            
            # 短暂休息
            await self.wait(30)
            
            # 大波攻击
            await self._fire_wave_attack()
            
            await self.wait(45)
    
    async def _fire_bird_pattern(self):
        """发射鸟形弹幕"""
        base_angle = self.angle_to_player()
        
        # V字形
        for i in range(-2, 3):
            offset = abs(i) * 15
            speed = 2.0 + abs(i) * 0.3
            
            self.fire(
                angle=base_angle + i * 8,
                speed=speed,
                bullet_type="arrowhead",
                color="darkblue"
            )
    
    async def _fire_wave_attack(self):
        """大波攻击"""
        # 从Boss位置向四周扩散
        for wave in range(5):
            count = 24 + wave * 4
            speed = 1.5 + wave * 0.2
            
            self.fire_circle(
                count=count,
                speed=speed,
                start_angle=wave * 7,
                bullet_type="ball_s",
                color="purple"
            )
            
            await self.wait(6)


spellcard = NightBird

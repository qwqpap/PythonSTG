import random
from src.game.stage.enemy_script import EnemyScript

class SpeedYinYang(EnemyScript):
    """
    极速掠过的子弹头型阴阳玉
    不发射常规子弹，而是在飞行轨迹上留下大片长时间滞留的“尾气”烟雾弹
    """
    hp = 50
    sprite = "enemy3"  # 阴阳玉通常是 enemy3
    score = 300
    drops = {"point": 1}
    
    # 动态参数，在 Wave 中生成时覆盖
    target_x: float = 1.1
    target_y: float = -1.5
    fly_duration: int = 60

    async def run(self):
        move_coro = self.move_linear(self.target_x - self.x, self.target_y - self.y, duration=self.fly_duration)
        frame = 0
        while True:
            moving = True
            try:
                next(move_coro)
            except StopIteration:
                moving = False
                
            # 每 4 帧释放一团烟雾（尾气），只有在屏幕内时才释放
            if frame % 4 == 0 and -1.0 <= self.x <= 1.0 and -1.0 <= self.y <= 1.0:
                speed = random.uniform(10.5, 15.5)
                self.fire(
                    angle=random.uniform(0, 360),
                    speed=speed,
                    bullet_type="ball_s",
                    color="black"  # 取消 friction，让弹幕缓慢匀速飘散，防止停滞卡住
                )
            
            # 超出边界自动销毁
            if not moving or self.y < -1.5 or self.x > 1.8 or self.x < -1.8:
                break
            
            await self.wait(1)
            frame += 1


class CenterSniper(EnemyScript):
    """
    突发刷出的炮塔，瞬间降临后发射一轮高初速的 5-Way 自机狙，封死玩家退路
    """
    hp = 60
    sprite = "enemy3"
    score = 800
    drops = {"power": 2}

    target_x: float = 0.0
    target_y: float = 0.4

    async def run(self):
        # 快速落位
        await self.move_to(self.target_x, self.target_y, duration=20)
        
        # 短促停滞与预热
        await self.wait(10)
        
        # 连续发射 5 波 5-Way 狙击，封锁较长时间
        for _ in range(5):
            self.play_se("tan01", volume=0.5)
            self.fire_arc(
                count=5,
                speed=25.0,  # 在连发情况下初速度稍微下调一点，保持压制力
                center_angle=self.angle_to_player(),
                arc_angle=40,
                bullet_type="arrow_m",
                color="red"
            )
            await self.wait(20) # 波次连发的间隔
        
        # 稍作停留后极速向上逃离屏幕
        await self.wait(15)
        await self.move_linear(0, 1.5, duration=30)

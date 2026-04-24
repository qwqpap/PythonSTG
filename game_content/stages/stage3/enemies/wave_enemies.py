import math
import random
from src.game.stage.enemy_script import EnemyScript
from src.game.bullet.optimized_pool import CURVE_SIN_ANGLE

class SeismicFairy(EnemyScript):
    """
    发射地震波弹性形变弹幕的小妖精
    沿着抛物线或波浪线飞行，发射蛇形正弦弹幕
    """
    def __init__(self):
        super().__init__()
        self.hp = 18
        self.score = 500
        self.sprite = "enemy1"
        self.side = 1  # 1 for left to right, -1 for right to left

    async def run(self):
        # 1. 入场
        visible_x_margin = 0.98
        for i in range(120):
            # 基础向侧边飞行，带一点上下浮动
            self.x += self.side * 0.015
            self.y += math.sin(i * 0.1) * 0.005

            if i % 25 == 0 and -visible_x_margin <= self.x <= visible_x_margin:
                # 只在进入可见区域后开火，避免侧边场外弹先有判定后入屏。
                for angle_offset in [-15, 0, 15]:
                    self.fire(
                        x=self.x, y=self.y,
                        angle=-90 + angle_offset,
                        speed=13.5,
                        bullet_type="knife", color="yellow",
                        curve_type=CURVE_SIN_ANGLE,
                        # amp(弧度/帧), freq(弧度/帧), phase, base
                        # 0.04 * 60 = 2.4 rad/s 每帧最大偏转角度
                        # 0.1 freq 表示一个周期大概 60 帧
                        curve_params=(0.05, 0.1, 0.0, 0.0)
                    )
            
            await self.wait(1)
            
        # 2. 加速撤离
        while self.y > -1.2 and self.x > -1.2 and self.x < 1.2:
            self.x += self.side * 0.02
            self.y -= 0.01
            await self.wait(1)
            
        self.kill()

class VaultLeader(EnemyScript):
    """
    断层精英怪：缓慢下降，召唤沉重的落石，以及全方位无死角的断层网格
    """
    def __init__(self):
        super().__init__()
        self.hp = 260
        self.score = 5000
        self.sprite = "enemy3"
        self._angle_acc = 0.0
        
    async def run(self):
        await self.move_to(self.x, 0.75, duration=60)
        await self.wait(10)
        
        # 持续 10 秒的压制攻击
        for i in range(600):
            # 每隔 60 帧发射一组厚重的"落石"
            if i % 60 == 0:
                for _ in range(8):
                    self.fire(
                        x=self.x + random.uniform(-0.1, 0.1),
                        y=self.y,
                        angle=random.uniform(-110, -70),
                        speed=random.uniform(11.2, 12.5),
                        bullet_type="ball_l", color="orange"
                    )
            
            # 每隔 15 帧发射旋转断层封路网格（偶数发，留出安全缝隙）
            if i % 15 == 0:
                self.fire_circle(
                    x=self.x, y=self.y,
                    count=12, speed=12.5,
                    start_angle=self._angle_acc,
                    bullet_type="square", color="darkred"
                )
                self._angle_acc += 7.3  # 故意是个非整数，形成螺旋交叉缝隙
                
            await self.wait(1)
            
        # 撤退
        await self.move_to(self.x, 1.3, duration=80)
        self.kill()

class MagmaOrb(EnemyScript):
    """
    地幔岩浆球：从下方升起，缓慢爬升，到达顶部前引爆成环形扩散弹幕
    """
    def __init__(self):
        super().__init__()
        self.hp = 25
        self.score = 800
        self.sprite = "enemy2" # 借用阴阳灵
        
    async def run(self):
        # 1. 缓慢上升
        for i in range(120):
            self.y += 0.01
            
            # 上升过程掉落小火球
            if i % 10 == 0:
                self.fire(
                    x=self.x, y=self.y,
                    angle=random.uniform(-135, -45),
                    speed=random.uniform(12.5, 14.5),
                    bullet_type="grain_a", color="red"
                )
            await self.wait(1)
            
        # 2. 停顿，膨胀预警（这里因为没有缩放API，我们用发弹来预警）
        for i in range(30):
            if i % 5 == 0:
                self.fire_circle(
                    x=self.x, y=self.y,
                    count=8, speed=12.5,
                    start_angle=i * 12,
                    bullet_type="mildew", color="orange"
                )
            await self.wait(1)
            
        # 3. 爆炸！
        for speed in [13.5, 15.0, 17.0]:
            self.fire_circle(
                x=self.x, y=self.y,
                count=20, speed=speed,
                start_angle=0,
                bullet_type="fire", color="red" # 如果没有fire，会自动回退
            )
            
        # 4. 爆炸后继续向上飞，直到飞出屏幕
        while self.y <= 1.2:
            self.y += 0.015
            await self.wait(1)
            
        self.kill()

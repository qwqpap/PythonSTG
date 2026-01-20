from boss import Boss, BossPhase
import numpy as np

# 游戏基础尺寸（与boli.py一致）
BASE_WIDTH = 384
BASE_HEIGHT = 448

# 坐标转换函数：像素坐标转归一化坐标（与boli.py一致）
def pixel_to_normalized(x, y):
    """
    将像素坐标转换为归一化坐标
    :param x: 像素X坐标（0到BASE_WIDTH）
    :param y: 像素Y坐标（0到BASE_HEIGHT）
    :return: 归一化坐标元组（-1到1）
    """
    norm_x = (x / BASE_WIDTH) * 2 - 1
    norm_y = (y / BASE_HEIGHT) * 2 - 1
    return norm_x, norm_y

# 坐标转换函数：归一化坐标转像素坐标（与boli.py一致）
def normalized_to_pixel(norm_x, norm_y):
    """
    将归一化坐标转换为像素坐标
    :param norm_x: 归一化X坐标（-1到1）
    :param norm_y: 归一化Y坐标（-1到1）
    :return: 像素坐标元组（0到BASE_WIDTH, 0到BASE_HEIGHT）
    """
    pixel_x = (norm_x + 1) / 2 * BASE_WIDTH
    pixel_y = (norm_y + 1) / 2 * BASE_HEIGHT
    return pixel_x, pixel_y

class ExampleBossPhase0(BossPhase):
    """
    示例Boss的第0阶段（非符卡）
    """
    def __init__(self, boss):
        super().__init__(boss, 0)
    
    def _pattern(self):
        """
        阶段0的弹幕模式：圆形扩散
        """
        boss = self.boss
        bullet_pool = yield
        
        # 阶段0：圆形扩散弹幕
        for i in range(5):
            # 生成圆形扩散弹幕
            angle_step = 2 * np.pi / 18
            for j in range(18):
                angle = j * angle_step
                bullet_pool.spawn_bullet(
                    boss.pos[0], boss.pos[1],
                    angle, 0.01,
                    color=(1.0, 0.0, 0.0),
                    sprite_id='bullet1'
                )
            # 等待60帧
            for _ in range(60):
                yield

class ExampleBossPhase1(BossPhase):
    """
    示例Boss的第1阶段（符卡）
    """
    def __init__(self, boss):
        super().__init__(boss, 1)
    
    def on_enter(self):
        super().on_enter()
        # 进入阶段1时，Boss移动到屏幕中央
        self.boss.add_behavior(
            self.boss.move_to(np.array([0.0, 0.5], dtype='f4'), 2.0)
        )
    
    def _pattern(self):
        """
        阶段1的弹幕模式：螺旋弹幕
        """
        boss = self.boss
        bullet_pool = yield
        
        # 阶段1：螺旋弹幕
        angle = 0.0
        for i in range(200):
            bullet_pool.spawn_bullet(
                boss.pos[0], boss.pos[1],
                angle, 0.008,
                color=(0.0, 1.0, 0.0),
                sprite_id='bullet2'
            )
            angle += 0.15  # 旋转速度
            yield
            
        # 等待120帧
        for _ in range(120):
            yield

class ExampleBossPhase2(BossPhase):
    """
    示例Boss的第2阶段（终符）
    """
    def __init__(self, boss):
        super().__init__(boss, 2)
    
    def on_enter(self):
        super().on_enter()
        # 进入阶段2时，Boss移动到屏幕上方
        self.boss.add_behavior(
            self.boss.move_to(np.array([0.0, 0.7], dtype='f4'), 1.5)
        )
    
    def _pattern(self):
        """
        阶段2的弹幕模式：环形弹幕
        """
        boss = self.boss
        bullet_pool = yield
        
        # 阶段2：环形弹幕
        for ring in range(8):
            angle_step = 2 * np.pi / 24
            for j in range(24):
                angle = j * angle_step
                speed = 0.006 + ring * 0.002
                bullet_pool.spawn_bullet(
                    boss.pos[0], boss.pos[1],
                    angle, speed,
                    color=(1.0, 1.0, 0.0),
                    sprite_id='bullet3'
                )
            # 等待45帧
            for _ in range(45):
                yield

class ExampleBoss(Boss):
    """
    示例Boss实现
    """
    def __init__(self):
        # 初始位置在屏幕上方中央
        super().__init__(np.array([0.0, 0.8], dtype='f4'))
        
        # 设置Boss属性
        self.hp = 1500.0
        self.max_hp = 1500.0
        self.hit_radius = 0.08
        
        # 添加阶段
        self.add_phase(0, ExampleBossPhase0(self))
        self.add_phase(1, ExampleBossPhase1(self))
        self.add_phase(2, ExampleBossPhase2(self))
    
    def update(self, dt, bullet_pool):
        """
        自定义更新逻辑
        """
        super().update(dt, bullet_pool)
        
        # 可以在这里添加额外的Boss行为逻辑
        # 例如：根据玩家位置调整移动策略
    
    def draw(self, renderer):
        """
        自定义绘制逻辑
        """
        if not self.is_alive():
            return
        
        # 这里可以添加更复杂的Boss绘制逻辑
        # 例如：绘制Boss立绘、特效等
        super().draw(renderer)

# 示例使用方法
def create_example_boss():
    """
    创建示例Boss
    :return: ExampleBoss实例
    """
    boss = ExampleBoss()
    return boss

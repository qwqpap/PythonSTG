import math
import random

# 多种华丽弹幕模式集合：螺旋、扇形波、花朵环

class ExplosionManager:
    """管理延迟爆炸的子弹"""
    def __init__(self):
        self.pending_explosions = []  # 存储待爆炸的子弹信息：(爆炸时间, x, y)

    def add_explosion(self, explode_frame, x, y):
        """添加一个待爆炸的子弹"""
        self.pending_explosions.append((explode_frame, x, y))

    def check_explosions(self, current_frame, bullet_pool):
        """检查并处理已到爆炸时间的子弹"""
        exploded = []
        for i, (explode_frame, x, y) in enumerate(self.pending_explosions):
            if current_frame >= explode_frame:
                # 爆炸效果：生成多个子弹
                for _ in range(8):  # 爆炸生成8颗子弹
                    angle = random.uniform(0, 2 * math.pi)
                    speed = random.uniform(0.3, 1.0)
                    bullet_pool.spawn_bullet(x, y, angle, speed, sprite_id='grain_a2')
                exploded.append(i)
        
        # 移除已爆炸的记录
        for i in reversed(exploded):
            self.pending_explosions.pop(i)


explosion_manager = ExplosionManager()

def explosion_manager_coroutine(stage_manager, bullet_pool):
    """管理延迟爆炸的协程"""
    while True:
        current_frame = stage_manager.get_frame_count()
        explosion_manager.check_explosions(current_frame, bullet_pool)
        yield 1

def spawn_delayed_explosion_bullet(bp, stage_manager, x, y, angle, speed, delay_frames, sprite_id='grain_a4'):
    """生成延迟爆炸的子弹"""
    # 生成初始子弹
    bullet_idx = bp.spawn_bullet(x, y, angle, speed, sprite_id=sprite_id)
    
    # 计算爆炸时间
    explode_frame = stage_manager.get_frame_count() + delay_frames
    
    # 添加到爆炸管理器
    explosion_manager.add_explosion(explode_frame, x, y)
    
    return bullet_idx

def spiral_coroutine_original(bp, player, origin=(0, 0.5)):
    """持续螺旋弹幕：每帧发射1颗子弹，角度逐渐旋转并形成彩色螺旋。"""
    x, y = origin
    angle = 0.0
    speed = 0.8
    hue = 0
    while True:
        # 每帧发一颗，少量抖动让轨迹更有机
        jitter = (random.random() - 0.5) * math.radians(2)
        bp.spawn_bullet(x, y, angle + jitter, speed, sprite_id='grain_a4')
        angle += math.radians(8)  # 每帧旋转8度
        speed += 0.0008  # 慢慢加速，制造密集外圈
        hue = (hue + 5) % 360
        yield 1


def fan_wave_coroutine(bp, player, origin=(0, 0.5)):
    """间歇扇形波：每隔若干帧发射多层扇形，层与层之间角度微移，形成流动感。"""
    x, y = origin
    base_angle = 0.0
    frames_between_bursts = 40
    bullets_per_burst = 14
    spread = math.radians(80)
    layer_count = 3
    while True:
        # 发射多层扇形
        for layer in range(layer_count):
            radius_speed = 0.9 + 0.15 * layer
            angle_offset = base_angle + layer * math.radians(6)
            for i in range(bullets_per_burst):
                t = i / (bullets_per_burst - 1) if bullets_per_burst > 1 else 0
                a = angle_offset - spread / 2 + t * spread
                bp.spawn_bullet(x, y, a, radius_speed, sprite_id='grain_a3')
        # 轻微旋转基角，制造波动
        base_angle += math.radians(6)
        for _ in range(frames_between_bursts):
            yield 1


def flower_bloom_coroutine(bp, player, origin=(0, 0.5)):
    """花朵绽放：周期性发出多圈环形，环内子弹速度不同形成层次感。"""
    x, y = origin
    for _ in range(6):  # 弹幕执行6*(120+3*8)个循环后结束这个协程之函数
        ring_counts = [10, 16, 22]
        speeds = [0.6, 1.0, 1.6]
        for ring_idx, count in enumerate(ring_counts):
            a0 = random.random() * math.radians(360)
            for i in range(count):
                a = a0 + (i / count) * 2 * math.pi
                bp.spawn_bullet(x, y, a, speeds[ring_idx], sprite_id='grain_a5')
            # 环与环之间短暂停顿
            for _ in range(8):
                yield 1
        # 大花朵冷却一段时间
        for _ in range(120):
            yield 1

def spiral_coroutine_with_explosions(bp, player, stage_manager):
    """带延迟爆炸效果的螺旋弹幕"""
    for i in range(200, 50, -5):
        for j in range(50, -50, -5):
            # 转换坐标到游戏坐标系
            x = i / 100.0  # 调整缩放因子
            y = j / 100.0
            spawn_delayed_explosion_bullet(bp, stage_manager, x, y, 0, 0, 120, 'grain_a4')
            yield 1  # 每生成一颗子弹等待1帧


def level_1(stage_manager, bullet_pool, player):   
    """第一关：组合三种华丽弹幕，形成叠加效果。"""
    # 添加爆炸管理器协程
    stage_manager.add_coroutine(lambda: explosion_manager_coroutine(stage_manager, bullet_pool))

    # 添加带爆炸效果的螺旋弹幕
    stage_manager.add_coroutine(lambda: spiral_coroutine_with_explosions(bullet_pool, player, stage_manager))

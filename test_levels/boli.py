import math
import random

# 多种华丽弹幕模式集合：螺旋、扇形波、花朵环

def explosion_handler(bp, event):
    """爆炸处理函数"""
    # 爆炸效果：生成多个子弹
    for _ in range(8):  # 爆炸生成8颗子弹
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(0.3, 1.0)
        bp.spawn_bullet(event.x, event.y, angle, speed, sprite_id='grain_a2')

def test_explosion_array_coroutine(bp, stage_manager):
    """测试弹幕：生成延迟三秒爆炸的子弹阵列"""
    # 生成3x3的子弹阵列
    positions = [
        (-1.0, 1.0), (0.0, 1.0), (1.0, 1.0),
        (-1.0, 0.0), (0.0, 0.0), (1.0, 0.0),
        (-1.0, -1.0), (0.0, -1.0), (1.0, -1.0)
    ]
    
    # 三秒 = 60帧/秒 * 3秒 = 180帧
    delay_frames = 180
    
    # 生成子弹
    bullet_indices = []
    for x, y in positions:
        # 生成静止的子弹
        bullet_idx = bp.spawn_bullet(x, y, 0, 0, sprite_id='grain_a4')
        if bullet_idx != -1:
            bullet_indices.append((bullet_idx, x, y))
        yield 1  # 每生成一颗子弹等待1帧
    
    # 等待三秒
    for _ in range(delay_frames):
        yield 1
    
    # 触发所有子弹爆炸
    for bullet_idx, x, y in bullet_indices:
        bp.kill_bullet(bullet_idx, explosion_handler)

def level_1(stage_manager, bullet_pool, player):   
    """第一关：测试延迟爆炸弹幕"""
    # 添加测试爆炸阵列弹幕
    stage_manager.add_coroutine(lambda: test_explosion_array_coroutine(bullet_pool, stage_manager))

import math
import random

# 游戏基础尺寸
BASE_WIDTH = 384
BASE_HEIGHT = 448

# 坐标转换函数：像素坐标转归一化坐标
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

# 多种华丽弹幕模式集合：螺旋、扇形波、花朵环

def explosion_handler(bp, event):
    """爆炸处理函数"""
    # 爆炸效果：生成多个子弹
    for _ in range(8):  # 爆炸生成8颗子弹
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(0.2, 1.0)
        bp.spawn_bullet(event.x, event.y, angle, speed, sprite_id='grain_a2')

def test_explosion_array_coroutine(bp, stage_manager):
    """测试弹幕：生成延迟三秒爆炸的子弹阵列"""
    # 生成10x10的子弹阵列（使用像素坐标）
    grid_size = 13
    # 计算阵列大小（占屏幕的70%）
    array_width = BASE_WIDTH * 0.7
    array_height = BASE_HEIGHT * 0.7
    # 计算起始位置（使阵列居中）
    start_x = (BASE_WIDTH - array_width) // 2
    start_y = (BASE_HEIGHT - array_height) // 2
    # 计算每个子弹之间的间隔
    step_x = array_width / (grid_size - 1)
    step_y = array_height / (grid_size - 1)
    
    # 生成子弹（使用新的死亡处理机制）
    for i in range(grid_size):
        for j in range(grid_size):
            # 计算当前子弹的像素坐标
            x = start_x + i * step_x
            y = start_y + j * step_y
            # 转换为归一化坐标
            norm_x, norm_y = pixel_to_normalized(x, y)
            # 生成静止的子弹，直接传递死亡处理函数，生命周期为3秒
            bp.spawn_bullet(norm_x, norm_y, 0, 0, sprite_id='grain_a4', on_death=explosion_handler, max_lifetime=3.0)
            yield 1  # 每生成一颗子弹等待1帧
    
    # 这里不再需要手动触发爆炸，子弹会在离开屏幕时自动爆炸
    # 让子弹存在一段时间
    for _ in range(180):
        yield 1

def level_1(stage_manager, bullet_pool, player):   
    """第一关：测试延迟爆炸弹幕"""
    # 添加测试爆炸阵列弹幕
    stage_manager.add_coroutine(lambda: test_explosion_array_coroutine(bullet_pool, stage_manager))

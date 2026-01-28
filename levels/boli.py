import math
import random
from src.game.boss import Boss
from src.game.enemy import Enemy

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

# Boss弹幕模式
def boss_spiral_pattern(boss, bullet_pool, timer):
    """Boss螺旋弹幕模式"""
    # 每隔一定时间生成螺旋子弹
    if timer % 0.1 < 0.016:  # 每0.1秒生成一次
        angle = timer * 5  # 旋转角度
        speed = 0.3
        bullet_pool.spawn_bullet(
            boss.pos[0], boss.pos[1],
            angle, speed,
            sprite_id='star_small1'
        )
        # 生成第二层螺旋
        bullet_pool.spawn_bullet(
            boss.pos[0], boss.pos[1],
            angle + math.pi, speed * 0.7,
            sprite_id='grain_a2'
        )
    yield 1

def boss_circle_pattern(boss, bullet_pool, timer):
    """Boss圆形弹幕模式"""
    # 每隔一定时间生成圆形弹幕
    if timer % 0.5 < 0.016:  # 每0.5秒生成一次
        count = 12
        for i in range(count):
            angle = (2 * math.pi / count) * i + timer
            speed = 0.4
            bullet_pool.spawn_bullet(
                boss.pos[0], boss.pos[1],
                angle, speed,
                sprite_id='grain_a4'
            )
    yield 1

# 敌人攻击模式
def enemy_basic_pattern(enemy, bullet_pool, timer):
    """敌人基础攻击模式"""
    # 每隔一定时间生成子弹
    if timer % 1.0 < 0.016:  # 每1秒生成一次
        # 向玩家方向发射子弹
        angle = math.pi  # 简单示例，向下发射
        speed = 0.5
        bullet_pool.spawn_bullet(
            enemy.pos[0], enemy.pos[1],
            angle, speed,
            sprite_id='grain_a2'
        )
    yield 1

def spawn_enemies_coroutine(stage_manager, bullet_pool):
    """生成敌人的协程"""
    # 生成多个敌人
    for i in range(5):
        # 计算敌人的初始位置
        enemy_x = random.uniform(-0.8, 0.8)
        enemy_y = 1.2  # 从屏幕顶部进入
        
        # 创建敌人
        enemy = Enemy(
            enemy_id=f'enemy_{i}',
            pos=(enemy_x, enemy_y),
            sprite_id='grain_a4',
            max_hp=50
        )
        
        # 添加攻击模式
        enemy.add_attack_pattern('basic', enemy_basic_pattern)
        
        # 设置死亡回调
        def on_death_callback(enemy_instance):
            print(f"Enemy {enemy_instance.enemy_id} has been defeated!")
        
        enemy.set_on_death_callback(on_death_callback)
        
        # 设置被击中回调
        def on_hit_callback(enemy_instance, damage):
            print(f"Enemy {enemy_instance.enemy_id} hit! HP: {enemy_instance.current_hp}/{enemy_instance.max_hp}")
        
        enemy.set_on_hit_callback(on_hit_callback)
        
        # 添加敌人到关卡
        stage_manager.add_enemy(enemy)
        
        # 让敌人移动到指定位置
        target_y = random.uniform(0.2, 0.6)
        enemy.move_to((enemy_x, target_y), 2.0)  # 2秒内移动到目标位置
        
        # 等待一段时间再生成下一个敌人
        yield from stage_manager.wait(60)  # 等待1秒

 
def explosion_handler(bp, event):
    """爆炸处理函数"""
    # 爆炸效果：生成多个子弹
    for _ in range(100):  # 爆炸生成8颗子弹
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(0.5, 1.5)  # 增加速度，让子弹更明显
        # 添加很小的随机加速度，让爆炸效果更自然
        # 加速度方向与速度方向一致，大小随机
        acc_magnitude = random.uniform(0.05, 0.2)
        acc_x = math.cos(angle) * acc_magnitude
        acc_y = math.sin(angle) * acc_magnitude
        bp.spawn_bullet(event.x, event.y, angle, speed, acc=(acc_x, acc_y), sprite_id='star_small1')

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
            yield from stage_manager.wait(1)  # 每生成一颗子弹等待1帧
    
    # 这里不再需要手动触发爆炸，子弹会在离开屏幕时自动爆炸
    # 让子弹存在一段时间
    yield from stage_manager.wait(180)  # 等待3秒（180帧）

def repeat_explosion_coroutine(bullet_pool, stage_manager, repeat_count=3, interval_seconds=5):
    """
    重复执行爆炸弹幕阵列，中间有间隔
    :param bullet_pool: 子弹池
    :param stage_manager: 关卡管理器
    :param repeat_count: 重复次数
    :param interval_seconds: 每次间隔的秒数
    """
    # 转换间隔秒数为帧数（假设60帧/秒）
    interval_frames = int(interval_seconds * 60)
    
    # 重复执行
    for _ in range(repeat_count):
        # 执行爆炸弹幕阵列
        yield from test_explosion_array_coroutine(bullet_pool, stage_manager)
        # 等待指定的帧数
        yield from stage_manager.wait(interval_frames)

def rain_bullets_coroutine(bullet_pool, stage_manager, duration_seconds=30, spawn_interval_frames=2):
    """
    从天上往下面掉随机子弹的弹幕
    :param bullet_pool: 子弹池
    :param stage_manager: 关卡管理器
    :param duration_seconds: 持续时间（秒）
    :param spawn_interval_frames: 生成子弹的间隔帧数
    """
    # 转换持续时间为帧数（假设60帧/秒）
    duration_frames = int(duration_seconds * 60)
    frame_count = 0
    
    # 持续生成子弹
    while frame_count < duration_frames:
        # 每隔指定的帧数生成一颗子弹
        if frame_count % spawn_interval_frames == 0:
            # 随机生成子弹的x坐标（屏幕宽度范围内）
            random_x = random.uniform(-1.0, 1.0)
            # 子弹从屏幕顶部开始（y坐标大于1）
            start_y = 1.2
            # 随机生成子弹的角度（主要向下，有一些随机偏差）
            random_angle = random.uniform(math.pi * 1.3, math.pi * 1.7)  # 大约向下的角度
            # 随机生成子弹的速度
            random_speed = random.uniform(0.5, 1.5)
            # 生成子弹
            bullet_pool.spawn_bullet(
                random_x, start_y,
                random_angle, random_speed,
                sprite_id='grain_a2'
            )
        # 增加帧数计数
        frame_count += 1
        # 等待一帧
        yield from stage_manager.wait(1)

def level_1(stage_manager, bullet_pool, player):   
    """第一面：测试延迟爆炸弹幕"""
    # 首先生成敌人
    stage_manager.add_coroutine(lambda: spawn_enemies_coroutine(stage_manager, bullet_pool))
    
    # 等待敌人生成完毕
    yield from stage_manager.wait(300)  
    
    # 添加重复执行的爆炸阵列弹幕，重复1次
    stage_manager.add_coroutine(lambda: repeat_explosion_coroutine(bullet_pool, stage_manager, repeat_count=1, interval_seconds=5))
 
    # 添加从天上掉子弹的弹幕，持续10秒
    stage_manager.add_coroutine(lambda: rain_bullets_coroutine(bullet_pool, stage_manager, duration_seconds=10))
    
    # 等待前面的弹幕执行完毕
    yield from stage_manager.wait(600)  
    
    # 创建Boss
    boss = Boss(
        boss_id='test_boss',
        pos=(0.0, 0.5),  # Boss位置在屏幕上方
        sprite_id='boss',
        max_hp=500  # Boss生命值
    )
    
    # 添加Boss弹幕模式
    boss.add_pattern('spiral', boss_spiral_pattern)
    boss.add_pattern('circle', boss_circle_pattern)
    
    # 将Boss添加到关卡管理器
    stage_manager.add_boss(boss)
    
    # Boss战斗持续一段时间
    yield from stage_manager.wait(1800)  # 30秒 * 60帧/秒 = 1800帧

    
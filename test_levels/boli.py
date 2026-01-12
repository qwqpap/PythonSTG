from stage import spawn_ring, spawn_aiming, boss_pattern_1
import math

# 新的弹幕模式：从Boss位置开始每一秒发射五个角度均匀分布的子弹
def boss_pattern_coroutine(bp, player):
    """
    Boss弹幕模式（使用协程）
    :param bp: 子弹池
    :param player: 玩家对象
    """
    boss_pos = (0, 0.5)  # Boss位置
    base_angle = 0.0  # 基础角度
    x = 0  # 一次函数变量，每帧增加1
    bullet_count = 5  # 每次发射的子弹数量
    angle_interval = math.radians(360 / bullet_count)  # 角度间隔，转换为弧度
    fire_interval = 1  # 发射间隔（帧数，1秒=60帧）
    
    # 持续运行
    while True:
        # 发射5个均匀分布的子弹
        for i in range(bullet_count):
            angle = base_angle + i * angle_interval
            bp.spawn_bullet(boss_pos[0], boss_pos[1], angle, 1, sprite_id='grain_a4')
        
        # 等待60帧（1秒），同时每帧增加角度
        for _ in range(fire_interval):
            # 角度增加量是一次函数，与x成正比
            angle_increment_per_frame = math.radians(x)  # x每帧增加1，角度增加量线性增长
            base_angle += angle_increment_per_frame
            x += 0.1  # 每帧x增加1
            yield 1

# 新的弹幕模式：从Boss位置开始每一秒发射五个角度均匀分布的子弹
def level_1(stage_manager, bullet_pool, player):
    """
    第一关示例
    :param stage_manager: 关卡管理器
    :param bullet_pool: 子弹池
    :param player: 玩家对象
    """
    # 添加协程弹幕模式
    stage_manager.add_coroutine(lambda: boss_pattern_coroutine(bullet_pool, player))

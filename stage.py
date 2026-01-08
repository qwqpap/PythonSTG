class StageManager:
    def __init__(self, engine):
        """
        初始化关卡管理器
        :param engine: 游戏引擎实例，包含子弹池等核心组件
        """
        self.engine = engine
        self.frame_count = 0
        self.events = []  # 存储格式: [ [frame, function, args], ... ]

    def add_event(self, frame, func, *args):
        """
        添加一个事件到调度队列
        :param frame: 触发帧数
        :param func: 执行函数
        :param args: 函数参数
        """
        self.events.append([frame, func, args])
        # 按照帧数排序，确保事件按时间顺序执行
        self.events.sort(key=lambda x: x[0])

    def add_repeat_event(self, start_frame, interval, duration, func, *args):
        """
        添加一个重复事件
        :param start_frame: 开始帧数
        :param interval: 间隔帧数
        :param duration: 持续帧数
        :param func: 执行函数
        :param args: 函数参数
        """
        end_frame = start_frame + duration
        for frame in range(start_frame, end_frame, interval):
            self.add_event(frame, func, *args)

    def clear_events(self):
        """
        清空所有未执行的事件
        """
        self.events.clear()

    def update(self):
        """
        每帧更新，检查并执行待触发的事件
        """
        self.frame_count += 1
        # 检查有没有当前帧需要触发的任务
        while self.events and self.events[0][0] <= self.frame_count:
            frame, func, args = self.events.pop(0)
            func(*args)  # 执行用户定义的发射逻辑

    def get_frame_count(self):
        """
        获取当前帧数
        :return: 当前帧数
        """
        return self.frame_count

    def add_relative_event(self, relative_frames, func, *args):
        """
        添加一个相对当前帧的事件
        :param relative_frames: 相对于当前帧的帧数偏移
        :param func: 执行函数
        :param args: 函数参数
        """
        absolute_frame = self.frame_count + relative_frames
        self.add_event(absolute_frame, func, *args)

# 示例发射器函数
def spawn_ring(bullet_pool, center, count, speed, angle=0.0, sprite_id='star_small1'):
    """
    从中心点发射环形弹幕
    :param bullet_pool: 子弹池
    :param center: 中心点坐标 (x, y)
    :param count: 子弹数量
    :param speed: 子弹速度
    :param angle: 初始角度
    :param sprite_id: 精灵ID
    """
    bullet_pool.spawn_pattern(center[0], center[1], angle, speed, count=count, angle_spread=3.1415926 * 2, sprite_id=sprite_id)

def spawn_aiming(bullet_pool, center, player_pos, speed, sprite_id='star_small1'):
    """
    发射自机狙弹幕（追踪玩家）
    :param bullet_pool: 子弹池
    :param center: 中心点坐标 (x, y)
    :param player_pos: 玩家坐标 (x, y)
    :param speed: 子弹速度
    :param sprite_id: 精灵ID
    """
    import math
    dx = player_pos[0] - center[0]
    dy = player_pos[1] - center[1]
    angle = math.atan2(dy, dx)
    bullet_pool.spawn_bullet(center[0], center[1], angle, speed, sprite_id=sprite_id)

# 示例关卡定义
def level_1(stage_manager, bullet_pool, player):
    """
    第一关示例
    :param stage_manager: 关卡管理器
    :param bullet_pool: 子弹池
    :param player: 玩家对象
    """
    # 第 60 帧开始，每 30 帧发射一圈环形弹幕（循环执行，角度随帧数递增）
    def create_spawn_ring_task():
        base_angle = 0.0
        angle_increment = 0.1  # 每次递增的角度
        
        def spawn_ring_task():
            nonlocal base_angle
            spawn_ring(bullet_pool, (0, 0.5), 36, 0.15, angle=base_angle, sprite_id='arrow_big11')  # 增加速度并使用动态角度，使用star_small2子弹类型
            base_angle += angle_increment
        
        return spawn_ring_task
    
    spawn_ring_task = create_spawn_ring_task()
    stage_manager.add_repeat_event(60, 30, 800, spawn_ring_task)  # 从第60帧开始，每30帧执行一次，持续800帧
    
    # 第 120 帧到 600 帧，每 10 帧发一个自机狙
    def spawn_aiming_task():
        spawn_aiming(bullet_pool, (0, 0.5), player.pos, 0.5)  # 增加速度
    
    stage_manager.add_repeat_event(120, 10, 4800, spawn_aiming_task)
    
    # 第 700 帧开始，每 50 帧从四个角落发射扇形弹幕
    def spawn_fan():
        # 左上角
        bullet_pool.spawn_pattern(-0.8, 0.8, 0.0, 0.15, count=12, angle_spread=1.0, sprite_id='ball_small1')  # 使用ball_small1子弹类型
        # 右上角
        bullet_pool.spawn_pattern(0.8, 0.8, 3.1415926, 0.15, count=12, angle_spread=1.0, sprite_id='star_small2')  # 使用star_small2子弹类型
        # 左下角
        bullet_pool.spawn_pattern(-0.8, -0.8, 1.5707963, 0.15, count=12, angle_spread=1.0, sprite_id='ball_small1')  # 使用ball_small1子弹类型   
        # 右下角
        bullet_pool.spawn_pattern(0.8, -0.8, 4.712389, 0.15, count=12, angle_spread=1.0, sprite_id='star_small1')  # 增加速度
    
    stage_manager.add_repeat_event(700, 50, 4000, spawn_fan)  # 从第700帧开始，每50帧执行一次，持续400帧
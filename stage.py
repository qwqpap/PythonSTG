class StageManager:
    def __init__(self, engine):
        """
        初始化关卡管理器
        :param engine: 游戏引擎实例，包含子弹池等核心组件
        """
        self.engine = engine
        self.frame_count = 0
        self.events = []  # 存储格式: [ [frame, function, args], ... ]
        self.coroutines = []  # 存储协程: [ [coroutine, next_frame], ... ]

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
        每帧更新，检查并执行待触发的事件和协程
        """
        self.frame_count += 1
        # 检查有没有当前帧需要触发的任务
        while self.events and self.events[0][0] <= self.frame_count:
            frame, func, args = self.events.pop(0)
            func(*args)  # 执行用户定义的发射逻辑
        
        # 检查并执行协程
        completed_coroutines = []
        for i, (coroutine, next_frame) in enumerate(self.coroutines):
            if self.frame_count >= next_frame:
                try:
                    # 执行协程的下一步
                    wait_frames = next(coroutine)
                    # 更新协程的下一次执行帧数
                    self.coroutines[i][1] = self.frame_count + wait_frames
                except StopIteration:
                    # 协程执行完毕，标记为完成
                    completed_coroutines.append(i)
        
        # 移除已完成的协程（从后往前移除，避免索引偏移）
        for i in reversed(completed_coroutines):
            self.coroutines.pop(i)

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
    
    def add_coroutine(self, coroutine):
        """
        添加一个协程到管理器
        :param coroutine: 一个使用yield关键字的生成器函数
        """
        # 创建协程对象
        if callable(coroutine):
            coroutine = coroutine()
        # 存储协程和下一次执行的帧数
        self.coroutines.append([coroutine, self.frame_count])

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

def spawn_aiming(bullet_pool, center, player_pos, speed, sprite_id='grain_a5'):
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

# 示例协程函数
def boss_pattern_1(sm, bp, player):
    """
    示例Boss弹幕模式（使用协程）
    :param sm: 关卡管理器
    :param bp: 子弹池
    :param player: 玩家对象
    """
    for _ in range(5):
        spawn_ring(bp, (0, 0.5), 36, 0.1)
        yield 60  # 告诉管理器：等 60 帧再继续执行下一行
        spawn_aiming(bp, (0, 0.5), player.pos, 0.2)
        yield 30


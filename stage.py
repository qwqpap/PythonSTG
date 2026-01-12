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

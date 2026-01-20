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
        self.boss = None  # Boss实例
        self.player_bullets = None  # 玩家子弹池实例

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
        
        # 更新Boss状态
        if self.boss and self.boss.is_alive():
            # 假设dt=1/60秒（60fps）
            self.boss.update(1/60, self.engine.bullet_pool)
            # 检查玩家子弹与Boss的碰撞
            self._check_player_bullet_collisions()
    
    def _check_player_bullet_collisions(self):
        """
        检查玩家子弹与Boss的碰撞
        """
        if not self.player_bullets:
            return
        
        # 检查碰撞
        collisions = self.boss.check_player_bullet_collision(self.player_bullets.data)
        
        # 处理碰撞
        for idx in collisions:
            if self.player_bullets.data[idx]['alive'] == 1:
                # 应用伤害到Boss
                self.boss.apply_damage(10.0, source='player_bullet')
                # 销毁击中的子弹
                self.player_bullets.kill_bullet(idx)

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
    
    def set_boss(self, boss):
        """
        设置当前关卡的Boss
        :param boss: Boss实例
        """
        self.boss = boss
    
    def set_player_bullets(self, player_bullets):
        """
        设置玩家子弹池
        :param player_bullets: 玩家子弹池实例
        """
        self.player_bullets = player_bullets
    
    def draw(self, renderer):
        """
        绘制关卡元素
        :param renderer: 渲染器
        """
        if self.boss and self.boss.is_alive():
            self.boss.draw(renderer)

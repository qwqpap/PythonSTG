import numpy as np
from entity import Entity
from bullet import BulletPool
import types
import time

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

class BossPhase:
    """
    Boss阶段类，代表Boss的一个状态
    """
    def __init__(self, boss, phase_id, hp=None):
        """
        :param boss: 所属Boss实例
        :param phase_id: 阶段ID
        :param hp: 阶段HP（None表示共享Boss HP）
        """
        self.boss = boss
        self.phase_id = phase_id
        self.hp = hp
        self.max_hp = hp
        self.start_time = 0
        self.is_active = False
        
    def on_enter(self):
        """
        进入该阶段时调用
        """
        self.is_active = True
        self.start_time = time.time()
        if self.hp is not None:
            self.max_hp = self.hp
    
    def on_exit(self):
        """
        退出该阶段时调用
        """
        self.is_active = False
    
    def update(self, dt):
        """
        更新阶段状态
        :param dt: 时间步长
        """
        pass
    
    def get_pattern(self):
        """
        获取该阶段的弹幕模式生成器
        :return: 弹幕模式生成器
        """
        return self._pattern()
    
    def _pattern(self):
        """
        弹幕模式的具体实现，子类需要重写
        """
        yield 0

class Boss(Entity):
    """
    Boss实体类，实现六大模块
    """
    def __init__(self, pos=np.array([0.0, 0.0], dtype='f4')):
        super().__init__(pos)
        
        # 1. Boss实体属性
        self.hp = 1000.0
        self.max_hp = 1000.0
        self.phase = 0
        self.hit_radius = 0.05  # Boss碰撞体半径
        
        # 2. Phase系统
        self.phases = {}  # 阶段字典
        self.current_phase = None
        self.phase_transitioning = False
        
        # 3. 弹幕调度器
        self.patterns = []  # 活跃的弹幕生成器
        self.parallel_patterns = []  # 并行弹幕生成器
        self.frame_count = 0
        
        # 4. 伤害与判定系统
        self.invincible = False
        self.invincible_timer = 0.0
        self.damage_history = []
        
        # 5. 演出与行为层
        self.movement = None
        self.behavior_queue = []
        
        # 6. 生命周期管理
        self.spawned = False
        self.defeated = False
        self.spawn_time = 0
        self.defeat_time = 0
    
    def add_phase(self, phase_id, phase):
        """
        添加一个阶段
        :param phase_id: 阶段ID
        :param phase: BossPhase实例
        """
        self.phases[phase_id] = phase
        if phase_id == 0:
            self.current_phase = phase
            phase.on_enter()
    
    def switch_phase(self, phase_id):
        """
        切换到指定阶段
        :param phase_id: 阶段ID
        """
        if phase_id not in self.phases or self.phase == phase_id or self.phase_transitioning:
            return
        
        self.phase_transitioning = True
        
        # 退出当前阶段
        if self.current_phase:
            self.current_phase.on_exit()
        
        # 切换阶段
        self.phase = phase_id
        self.current_phase = self.phases[phase_id]
        self.current_phase.on_enter()
        
        # 重置弹幕调度器
        self.patterns.clear()
        self.parallel_patterns.clear()
        
        # 启动新阶段的弹幕模式
        self.start_pattern(self.current_phase.get_pattern())
        
        self.phase_transitioning = False
    
    def start_pattern(self, pattern_gen):
        """
        启动一个弹幕模式
        :param pattern_gen: 弹幕模式生成器
        """
        self.patterns.append(pattern_gen)
    
    def start_parallel_pattern(self, pattern_gen):
        """
        启动一个并行弹幕模式
        :param pattern_gen: 弹幕模式生成器
        """
        self.parallel_patterns.append(pattern_gen)
    
    def apply_damage(self, damage, source=None):
        """
        应用伤害
        :param damage: 伤害值
        :param source: 伤害来源
        :return: 是否真的受到伤害
        """
        if not self.alive or self.invincible or self.phase_transitioning:
            return False
        
        self.hp -= damage
        self.damage_history.append((self.frame_count, damage, source))
        
        # 检查是否需要切换阶段
        if self.hp <= 0:
            next_phase = self.phase + 1
            if next_phase in self.phases:
                # 进入下一阶段
                self.switch_phase(next_phase)
                # 恢复部分HP
                self.hp = self.max_hp * 0.8
            else:
                # Boss被击败
                self.defeat()
        
        return True
    
    def defeat(self):
        """
        Boss被击败
        """
        self.defeated = True
        self.defeat_time = time.time()
        self.alive = False
        self.invincible = True
    
    def move_to(self, target_pos, duration, easing=None):
        """
        移动到目标位置
        :param target_pos: 目标位置
        :param duration: 移动时间（秒）
        :param easing: 缓动函数
        :return: 移动生成器
        """
        start_pos = self.pos.copy()
        elapsed = 0.0
        
        def linear(t):
            return t
        
        easing_func = easing or linear
        
        while elapsed < duration:
            progress = easing_func(elapsed / duration)
            self.pos = start_pos + (target_pos - start_pos) * progress
            yield
            elapsed += 1/60  # 假设60fps
    
    def add_behavior(self, behavior_gen):
        """
        添加一个行为到队列
        :param behavior_gen: 行为生成器
        """
        self.behavior_queue.append(behavior_gen)
    
    def update(self, dt, bullet_pool):
        """
        更新Boss状态
        :param dt: 时间步长
        :param bullet_pool: 子弹池实例
        """
        if not self.alive:
            return
        
        self.frame_count += 1
        
        # 更新无敌时间
        if self.invincible:
            self.invincible_timer -= dt
            if self.invincible_timer <= 0:
                self.invincible = False
        
        # 更新阶段
        if self.current_phase:
            self.current_phase.update(dt)
        
        # 更新弹幕调度器
        self._update_patterns(bullet_pool)
        
        # 更新行为队列
        self._update_behavior(dt)
    
    def _update_patterns(self, bullet_pool):
        """
        更新弹幕模式
        :param bullet_pool: 子弹池实例
        """
        # 更新并行弹幕模式
        completed_parallel = []
        for i, pattern in enumerate(self.parallel_patterns):
            try:
                pattern.send(bullet_pool)
            except StopIteration:
                completed_parallel.append(i)
            except TypeError:
                # 首次调用生成器时使用next()
                next(pattern)
        
        # 移除完成的并行弹幕模式
        for i in reversed(completed_parallel):
            del self.parallel_patterns[i]
        
        # 更新串行弹幕模式
        if self.patterns:
            current_pattern = self.patterns[0]
            try:
                current_pattern.send(bullet_pool)
            except StopIteration:
                self.patterns.pop(0)
                # 启动下一个串行弹幕模式
                if not self.patterns and self.current_phase:
                    self.patterns.append(self.current_phase.get_pattern())
            except TypeError:
                # 首次调用生成器时使用next()
                next(current_pattern)
    
    def _update_behavior(self, dt):
        """
        更新行为队列
        :param dt: 时间步长
        """
        if self.behavior_queue:
            current_behavior = self.behavior_queue[0]
            try:
                next(current_behavior)
            except StopIteration:
                self.behavior_queue.pop(0)
    
    def draw(self, renderer):
        """
        渲染Boss
        :param renderer: 渲染器
        """
        if not self.alive:
            return
        
        # 默认绘制一个简单的Boss图形
        renderer.draw_circle(self.pos, self.hit_radius, (1.0, 0.0, 0.0))
    
    def spawn(self):
        """
        Boss登场
        """
        self.spawned = True
        self.spawn_time = time.time()
        self.alive = True
        
        # 启动第一个阶段的弹幕模式
        if self.current_phase:
            self.start_pattern(self.current_phase.get_pattern())
    
    def is_defeated(self):
        """
        检查Boss是否被击败
        :return: 是否被击败
        """
        return self.defeated
    
    def get_hp_percentage(self):
        """
        获取HP百分比
        :return: HP百分比
        """
        return self.hp / self.max_hp if self.max_hp > 0 else 0
    
    def set_invincible(self, duration):
        """
        设置无敌状态
        :param duration: 无敌时间（秒）
        """
        self.invincible = True
        self.invincible_timer = duration
    
    def check_player_bullet_collision(self, player_bullets):
        """
        检查玩家子弹与Boss的碰撞
        :param player_bullets: 玩家子弹数据
        :return: 碰撞的子弹索引列表
        """
        collisions = []
        if self.invincible or not self.alive:
            return collisions
        
        # 简化的碰撞检测，实际应该使用更高效的方法
        for idx in range(len(player_bullets)):
            if player_bullets[idx]['alive'] == 1:
                dx = player_bullets[idx]['pos'][0] - self.pos[0]
                dy = player_bullets[idx]['pos'][1] - self.pos[1]
                dist_sq = dx*dx + dy*dy
                combined_r = player_bullets[idx]['radius'] + self.hit_radius
                if dist_sq < combined_r * combined_r:
                    collisions.append(idx)
        
        return collisions
    
    def create_pattern_driver(self, func):
        """
        创建一个弹幕调度器
        :param func: 弹幕模式函数
        :return: 调度器生成器
        """
        def driver():
            gen = func(self)
            for _ in gen:
                yield
        return driver
    
    def create_parallel_driver(self, func):
        """
        创建一个并行弹幕调度器
        :param func: 弹幕模式函数
        :return: 并行调度器生成器
        """
        def parallel_driver():
            gen = func(self)
            for _ in gen:
                yield
        return parallel_driver
    
    # 便捷方法：创建常用的弹幕模式
    def circle_pattern(self, count=18, speed=0.01, angle_spread=np.pi*2):
        """
        圆形扩散弹幕模式
        :param count: 子弹数量
        :param speed: 速度
        :param angle_spread: 角度扩散范围
        :return: 生成器
        """
        def pattern(bullet_pool):
            angle_step = angle_spread / count
            for i in range(count):
                angle = i * angle_step
                bullet_pool.spawn_bullet(
                    self.pos[0], self.pos[1],
                    angle, speed,
                    color=(1.0, 0.0, 0.0),
                    sprite_id='bullet1'
                )
                yield
        return pattern
    
    def spiral_pattern(self, count=100, speed=0.005, rotation_speed=0.1):
        """
        螺旋弹幕模式
        :param count: 子弹数量
        :param speed: 速度
        :param rotation_speed: 旋转速度
        :return: 生成器
        """
        def pattern(bullet_pool):
            angle = 0.0
            for i in range(count):
                bullet_pool.spawn_bullet(
                    self.pos[0], self.pos[1],
                    angle, speed,
                    color=(0.0, 1.0, 0.0),
                    sprite_id='bullet2'
                )
                angle += rotation_speed
                yield
        return pattern
    
    def ring_pattern(self, ring_count=5, bullets_per_ring=20, speed=0.008):
        """
        环形弹幕模式
        :param ring_count: 环数
        :param bullets_per_ring: 每环子弹数
        :param speed: 速度
        :return: 生成器
        """
        def pattern(bullet_pool):
            for ring in range(ring_count):
                angle_step = 2 * np.pi / bullets_per_ring
                for i in range(bullets_per_ring):
                    angle = i * angle_step
                    current_speed = speed + ring * 0.002
                    bullet_pool.spawn_bullet(
                        self.pos[0], self.pos[1],
                        angle, current_speed,
                        color=(1.0, 1.0, 0.0),
                        sprite_id='bullet3'
                    )
                yield from self.wait_frames(30)
        return pattern
    
    def wait_frames(self, frames):
        """
        等待指定帧数
        :param frames: 帧数
        :return: 生成器
        """
        for _ in range(frames):
            yield

import numpy as np
from numba import njit
import math
import sys
from ..entity import Entity

# Boss状态常量
BOSS_STATE_IDLE = 0
BOSS_STATE_ATTACK = 1
BOSS_STATE_HURT = 2
BOSS_STATE_DEATH = 3
BOSS_STATE_MOVING = 4
BOSS_STATE_DIALOGUE = 5
BOSS_STATE_FINISHED = 6

class Boss(Entity):
    def __init__(self, boss_id, pos, sprite_id, max_hp=1000):
        """
        初始化Boss
        :param boss_id: Boss唯一标识符
        :param pos: 初始位置 (x, y)
        :param sprite_id: 精灵ID
        :param max_hp: 最大生命值
        """
        super().__init__(pos, sprite_id)
        self.boss_id = boss_id
        self.max_hp = max_hp
        self.current_hp = max_hp
        self.state = BOSS_STATE_IDLE
        self.state_timer = 0.0
        self.patterns = {}
        self.current_pattern = None
        self.pattern_timer = 0.0
        self.is_pattern_running = False
        self.hit_radius = 0.1  # Boss碰撞半径
        self.invincible = False  # 是否无敌
        self.invincible_timer = 0.0  # 无敌时间计时器
        
        # 移动相关属性
        self.target_pos = pos  # 目标位置
        self.move_speed = 0.0  # 移动速度
        self.move_duration = 0.0  # 移动持续时间
        self.start_pos = pos  # 移动起始位置
        
        # 对话相关属性
        self.dialogue_text = ""  # 当前对话文本
        self.dialogue_duration = 0.0  # 对话持续时间
        self.dialogue_callbacks = []  # 对话回调函数列表
        
        # 事件相关属性
        self.on_defeat_callback = None  # 被击败时的回调
        self.on_finished_callback = None  # Boss事件结束时的回调
    
    def add_pattern(self, pattern_id, pattern_func):
        """
        添加弹幕模式
        :param pattern_id: 模式唯一标识符
        :param pattern_func: 模式函数，应该是一个生成器函数
        """
        self.patterns[pattern_id] = pattern_func
    
    def switch_pattern(self, pattern_id):
        """
        切换到指定弹幕模式
        :param pattern_id: 要切换到的模式ID
        """
        if pattern_id in self.patterns:
            self.current_pattern = self.patterns[pattern_id]
            self.is_pattern_running = True
            self.pattern_timer = 0.0
    
    def update(self, dt, bullet_pool):
        """
        更新Boss状态和弹幕模式
        :param dt: 时间步长
        :param bullet_pool: 子弹池对象
        """
        # 更新状态计时器
        self.state_timer += dt
        
        # 更新无敌状态
        if self.invincible:
            self.invincible_timer -= dt
            if self.invincible_timer <= 0:
                self.invincible = False
        
        # 根据当前状态执行不同的行为
        if self.state == BOSS_STATE_IDLE:
            self._update_idle(dt, bullet_pool)
        elif self.state == BOSS_STATE_ATTACK:
            self._update_attack(dt, bullet_pool)
        elif self.state == BOSS_STATE_HURT:
            self._update_hurt(dt, bullet_pool)
        elif self.state == BOSS_STATE_DEATH:
            self._update_death(dt, bullet_pool)
        elif self.state == BOSS_STATE_MOVING:
            self._update_moving(dt, bullet_pool)
        elif self.state == BOSS_STATE_DIALOGUE:
            self._update_dialogue(dt, bullet_pool)
        elif self.state == BOSS_STATE_FINISHED:
            self._update_finished(dt, bullet_pool)
    
    def _update_idle(self, dt, bullet_pool):
        """
        更新待机状态
        """
        # 待机一段时间后切换到攻击状态
        if self.state_timer > 1.0:
            self.state = BOSS_STATE_ATTACK
            self.state_timer = 0.0
            # 随机选择一个弹幕模式
            if self.patterns:
                pattern_id = list(self.patterns.keys())[0]  # 简单示例，实际可以根据需要选择
                self.switch_pattern(pattern_id)
    
    def _update_attack(self, dt, bullet_pool):
        """
        更新攻击状态
        """
        # 更新弹幕模式
        if self.is_pattern_running and self.current_pattern:
            try:
                next(self.current_pattern(self, bullet_pool, self.pattern_timer))
                self.pattern_timer += dt
            except StopIteration:
                self.is_pattern_running = False
                self.pattern_timer = 0.0
        
        # 如果当前模式结束，切换到下一个模式或待机
        if not self.is_pattern_running:
            self.state = BOSS_STATE_IDLE
            self.state_timer = 0.0
    
    def _update_hurt(self, dt, bullet_pool):
        """
        更新受伤状态
        """
        # 受伤状态持续一段时间后切换回攻击状态
        if self.state_timer > 0.5:
            self.state = BOSS_STATE_ATTACK
            self.state_timer = 0.0
    
    def _update_death(self, dt, bullet_pool):
        """
        更新死亡状态
        """
        # 死亡状态处理
        if self.state_timer > 2.0:
            self.alive = False
    
    def take_damage(self, damage):
        """
        处理Boss受伤
        :param damage: 伤害值
        :return: 是否实际受到伤害
        """
        if not self.invincible:
            self.current_hp -= damage
            if self.current_hp <= 0:
                self.current_hp = 0
                self.state = BOSS_STATE_DEATH
                self.state_timer = 0.0
            else:
                self.state = BOSS_STATE_HURT
                self.state_timer = 0.0
                self.invincible = True
                self.invincible_timer = 0.3  # 0.3秒无敌时间
            return True
        return False
    
    def move_to(self, target_pos, duration, speed=None):
        """
        在指定时间内移动到目标位置
        :param target_pos: 目标位置 (x, y)
        :param duration: 移动持续时间（秒）
        :param speed: 可选，移动速度。如果提供，会忽略duration
        """
        self.state = BOSS_STATE_MOVING
        self.state_timer = 0.0
        self.target_pos = target_pos
        self.start_pos = self.pos.copy()
        
        if speed is not None:
            # 根据速度计算持续时间
            dx = target_pos[0] - self.pos[0]
            dy = target_pos[1] - self.pos[1]
            distance = math.sqrt(dx**2 + dy**2)
            self.move_duration = distance / speed
            self.move_speed = speed
        else:
            # 根据持续时间计算速度
            dx = target_pos[0] - self.pos[0]
            dy = target_pos[1] - self.pos[1]
            distance = math.sqrt(dx**2 + dy**2)
            self.move_duration = duration
            self.move_speed = distance / duration if duration > 0 else 0
    
    def _update_moving(self, dt, bullet_pool):
        """
        更新移动状态
        """
        if self.state_timer >= self.move_duration:
            # 移动完成
            self.pos = self.target_pos.copy()
            self.state = BOSS_STATE_IDLE
            self.state_timer = 0.0
        else:
            # 计算移动进度
            progress = self.state_timer / self.move_duration
            # 使用平滑的缓动函数
            t = progress * progress * (3 - 2 * progress)  # 缓动函数
            # 计算当前位置
            self.pos[0] = self.start_pos[0] + (self.target_pos[0] - self.start_pos[0]) * t
            self.pos[1] = self.start_pos[1] + (self.target_pos[1] - self.start_pos[1]) * t
    
    def show_dialogue(self, text, duration=3.0, callback=None):
        """
        显示对话文本
        :param text: 对话文本
        :param duration: 对话显示持续时间（秒）
        :param callback: 对话结束后的回调函数
        """
        self.state = BOSS_STATE_DIALOGUE
        self.state_timer = 0.0
        self.dialogue_text = text
        self.dialogue_duration = duration
        if callback:
            self.dialogue_callbacks = [callback]
        else:
            self.dialogue_callbacks = []
    
    def _update_dialogue(self, dt, bullet_pool):
        """
        更新对话状态
        """
        if self.state_timer >= self.dialogue_duration:
            # 对话结束
            self.state = BOSS_STATE_IDLE
            self.state_timer = 0.0
            # 执行对话回调
            for callback in self.dialogue_callbacks:
                callback(self)
            self.dialogue_callbacks = []
    
    def defeat(self):
        """
        击败Boss
        """
        self.state = BOSS_STATE_DEATH
        self.state_timer = 0.0
        self.current_hp = 0
        # 执行被击败回调
        if self.on_defeat_callback:
            self.on_defeat_callback(self)
    
    def finish_boss_event(self):
        """
        结束Boss事件
        """
        self.state = BOSS_STATE_FINISHED
        self.state_timer = 0.0
        # 执行结束回调
        if self.on_finished_callback:
            self.on_finished_callback(self)
    
    def _update_finished(self, dt, bullet_pool):
        """
        更新结束状态
        """
        # 结束状态可以在这里添加一些动画或效果
        # 简单实现：直接结束
        self.alive = False
    
    def set_on_defeat_callback(self, callback):
        """
        设置被击败时的回调函数
        :param callback: 回调函数，接收Boss实例作为参数
        """
        self.on_defeat_callback = callback
    
    def set_on_finished_callback(self, callback):
        """
        设置Boss事件结束时的回调函数
        :param callback: 回调函数，接收Boss实例作为参数
        """
        self.on_finished_callback = callback
    
    def get_hp_percentage(self):
        """
        获取当前生命值百分比
        :return: 生命值百分比 (0.0 - 1.0)
        """
        return self.current_hp / self.max_hp

# Boss管理器
class BossManager:
    def __init__(self):
        """
        初始化Boss管理器
        """
        self.bosses = []
        self.active_boss = None
    
    def add_boss(self, boss):
        """
        添加Boss到管理器
        :param boss: Boss对象
        """
        self.bosses.append(boss)
        if self.active_boss is None:
            self.active_boss = boss
    
    def update(self, dt, bullet_pool):
        """
        更新所有Boss
        :param dt: 时间步长
        :param bullet_pool: 子弹池对象
        """
        for boss in self.bosses:
            if boss.alive:
                boss.update(dt, bullet_pool)
            else:
                self.bosses.remove(boss)
                if self.active_boss == boss:
                    self.active_boss = self.bosses[0] if self.bosses else None
    

    def get_active_boss(self):
        """
        获取当前活跃的Boss
        :return: 当前活跃的Boss对象，或None
        """
        return self.active_boss
    


    def clear(self):
        """
        清除所有Boss
        """
        self.bosses.clear()
        self.active_boss = None
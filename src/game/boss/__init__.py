import numpy as np
from numba import njit
import math
import pygame
import sys
from ..entity import Entity

# Boss状态常量
BOSS_STATE_IDLE = 0
BOSS_STATE_ATTACK = 1
BOSS_STATE_HURT = 2
BOSS_STATE_DEATH = 3

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
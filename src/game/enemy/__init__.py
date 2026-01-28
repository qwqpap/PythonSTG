import numpy as np
from numba import njit
import math
import pygame
import sys
from ..entity import Entity

# Enemy状态常量
ENEMY_STATE_IDLE = 0
ENEMY_STATE_MOVING = 1
ENEMY_STATE_ATTACKING = 2
ENEMY_STATE_HURT = 3
ENEMY_STATE_DEATH = 4
ENEMY_STATE_FINISHED = 5

class Enemy(Entity):
    def __init__(self, enemy_id, pos, sprite_id, max_hp=100):
        """
        初始化敌人
        :param enemy_id: 敌人唯一标识符
        :param pos: 初始位置 (x, y)
        :param sprite_id: 精灵ID
        :param max_hp: 最大生命值
        """
        super().__init__(pos, sprite_id)
        self.enemy_id = enemy_id
        self.max_hp = max_hp
        self.current_hp = max_hp
        self.state = ENEMY_STATE_IDLE
        self.state_timer = 0.0
        self.hit_radius = 0.05  # 敌人碰撞半径
        self.invincible = False  # 是否无敌
        self.invincible_timer = 0.0  # 无敌时间计时器
        
        # 移动相关属性
        self.target_pos = pos  # 目标位置
        self.move_speed = 0.0  # 移动速度
        self.move_duration = 0.0  # 移动持续时间
        self.start_pos = pos  # 移动起始位置
        
        # 攻击相关属性
        self.attack_patterns = {}  # 攻击模式
        self.current_pattern = None  # 当前攻击模式
        self.is_pattern_running = False  # 攻击模式是否正在运行
        self.pattern_timer = 0.0  # 攻击模式计时器
        
        # 事件相关属性
        self.on_death_callback = None  # 死亡时的回调
        self.on_spawn_callback = None  # 生成时的回调
        self.on_hit_callback = None  # 被击中时的回调
    
    def add_attack_pattern(self, pattern_id, pattern_func):
        """
        添加攻击模式
        :param pattern_id: 模式唯一标识符
        :param pattern_func: 模式函数，应该是一个生成器函数
        """
        self.attack_patterns[pattern_id] = pattern_func
    
    def switch_attack_pattern(self, pattern_id):
        """
        切换到指定攻击模式
        :param pattern_id: 要切换到的模式ID
        """
        if pattern_id in self.attack_patterns:
            self.current_pattern = self.attack_patterns[pattern_id]
            self.is_pattern_running = True
            self.pattern_timer = 0.0
    
    def update(self, dt, bullet_pool):
        """
        更新敌人状态和攻击模式
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
        if self.state == ENEMY_STATE_IDLE:
            self._update_idle(dt, bullet_pool)
        elif self.state == ENEMY_STATE_MOVING:
            self._update_moving(dt, bullet_pool)
        elif self.state == ENEMY_STATE_ATTACKING:
            self._update_attacking(dt, bullet_pool)
        elif self.state == ENEMY_STATE_HURT:
            self._update_hurt(dt, bullet_pool)
        elif self.state == ENEMY_STATE_DEATH:
            self._update_death(dt, bullet_pool)
        elif self.state == ENEMY_STATE_FINISHED:
            self._update_finished(dt, bullet_pool)
    
    def _update_idle(self, dt, bullet_pool):
        """
        更新待机状态
        """
        # 待机一段时间后切换到攻击状态
        if self.state_timer > 1.0:
            self.state = ENEMY_STATE_ATTACKING
            self.state_timer = 0.0
            # 随机选择一个攻击模式
            if self.attack_patterns:
                pattern_id = list(self.attack_patterns.keys())[0]  # 简单示例
                self.switch_attack_pattern(pattern_id)
    
    def _update_moving(self, dt, bullet_pool):
        """
        更新移动状态
        """
        if self.state_timer >= self.move_duration:
            # 移动完成
            self.pos = self.target_pos.copy()
            self.state = ENEMY_STATE_IDLE
            self.state_timer = 0.0
        else:
            # 计算移动进度
            progress = self.state_timer / self.move_duration
            # 使用平滑的缓动函数
            t = progress * progress * (3 - 2 * progress)  # 缓动函数
            # 计算当前位置
            self.pos[0] = self.start_pos[0] + (self.target_pos[0] - self.start_pos[0]) * t
            self.pos[1] = self.start_pos[1] + (self.target_pos[1] - self.start_pos[1]) * t
    
    def _update_attacking(self, dt, bullet_pool):
        """
        更新攻击状态
        """
        # 更新攻击模式
        if self.is_pattern_running and self.current_pattern:
            try:
                next(self.current_pattern(self, bullet_pool, self.pattern_timer))
                self.pattern_timer += dt
            except StopIteration:
                self.is_pattern_running = False
                self.pattern_timer = 0.0
        
        # 如果当前模式结束，切换到待机状态
        if not self.is_pattern_running:
            self.state = ENEMY_STATE_IDLE
            self.state_timer = 0.0
    
    def _update_hurt(self, dt, bullet_pool):
        """
        更新受伤状态
        """
        # 受伤状态持续一段时间后切换回待机状态
        if self.state_timer > 0.3:
            self.state = ENEMY_STATE_IDLE
            self.state_timer = 0.0
    
    def _update_death(self, dt, bullet_pool):
        """
        更新死亡状态
        """
        # 死亡状态处理
        if self.state_timer > 1.0:
            self.alive = False
    
    def _update_finished(self, dt, bullet_pool):
        """
        更新结束状态
        """
        # 结束状态可以在这里添加一些动画或效果
        # 简单实现：直接结束
        self.alive = False
    
    def take_damage(self, damage):
        """
        处理敌人受伤
        :param damage: 伤害值
        :return: 是否实际受到伤害
        """
        if not self.invincible:
            self.current_hp -= damage
            if self.current_hp <= 0:
                self.current_hp = 0
                self.state = ENEMY_STATE_DEATH
                self.state_timer = 0.0
                # 执行死亡回调
                if self.on_death_callback:
                    self.on_death_callback(self)
            else:
                self.state = ENEMY_STATE_HURT
                self.state_timer = 0.0
                self.invincible = True
                self.invincible_timer = 0.2  # 0.2秒无敌时间
                # 执行被击中回调
                if self.on_hit_callback:
                    self.on_hit_callback(self, damage)
            return True
        return False
    
    def move_to(self, target_pos, duration, speed=None):
        """
        在指定时间内移动到目标位置
        :param target_pos: 目标位置 (x, y)
        :param duration: 移动持续时间（秒）
        :param speed: 可选，移动速度。如果提供，会忽略duration
        """
        self.state = ENEMY_STATE_MOVING
        self.state_timer = 0.0
        self.target_pos = np.array(target_pos, dtype='f4')
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
    
    def spawn(self):
        """
        生成敌人
        """
        self.alive = True
        self.state = ENEMY_STATE_IDLE
        self.state_timer = 0.0
        # 执行生成回调
        if self.on_spawn_callback:
            self.on_spawn_callback(self)
    
    def kill(self):
        """
        杀死敌人
        """
        self.state = ENEMY_STATE_DEATH
        self.state_timer = 0.0
        self.current_hp = 0
        # 执行死亡回调
        if self.on_death_callback:
            self.on_death_callback(self)
    
    def set_on_death_callback(self, callback):
        """
        设置死亡时的回调函数
        :param callback: 回调函数，接收Enemy实例作为参数
        """
        self.on_death_callback = callback
    
    def set_on_spawn_callback(self, callback):
        """
        设置生成时的回调函数
        :param callback: 回调函数，接收Enemy实例作为参数
        """
        self.on_spawn_callback = callback
    
    def set_on_hit_callback(self, callback):
        """
        设置被击中时的回调函数
        :param callback: 回调函数，接收Enemy实例和伤害值作为参数
        """
        self.on_hit_callback = callback
    
    def get_hp_percentage(self):
        """
        获取当前生命值百分比
        :return: 生命值百分比 (0.0 - 1.0)
        """
        return self.current_hp / self.max_hp

# 敌人管理器
class EnemyManager:
    def __init__(self):
        """
        初始化敌人管理器
        """
        self.enemies = []
    
    def add_enemy(self, enemy):
        """
        添加敌人到管理器
        :param enemy: Enemy对象
        """
        self.enemies.append(enemy)
        enemy.spawn()  # 生成敌人
    
    def update(self, dt, bullet_pool):
        """
        更新所有敌人
        :param dt: 时间步长
        :param bullet_pool: 子弹池对象
        """
        for enemy in self.enemies[:]:  # 使用切片创建副本，避免遍历过程中修改列表
            if enemy.alive:
                enemy.update(dt, bullet_pool)
            else:
                self.enemies.remove(enemy)
    
    def get_active_enemies(self):
        """
        获取所有活跃的敌人
        :return: 活跃敌人列表
        """
        return [enemy for enemy in self.enemies if enemy.alive]
    
    def clear(self):
        """
        清除所有敌人
        """
        self.enemies.clear()
    
    def spawn_enemy(self, enemy_id, pos, sprite_id, max_hp=100):
        """
        快速生成敌人
        :param enemy_id: 敌人唯一标识符
        :param pos: 初始位置 (x, y)
        :param sprite_id: 精灵ID
        :param max_hp: 最大生命值
        :return: 生成的Enemy对象
        """
        enemy = Enemy(enemy_id, pos, sprite_id, max_hp)
        self.add_enemy(enemy)
        return enemy
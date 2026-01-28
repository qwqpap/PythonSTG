"""
玩家基类 - 整合射击、动画、碰撞等所有系统
支持通过配置文件自定义
"""
import numpy as np
import pygame
from typing import Optional, Callable, Dict, Any

from ..entity import Entity
from .player_bullet import PlayerBulletPool
from .player_shot import PlayerShotSystem, create_shot_type_from_config, create_options_from_config
from .player_animation import PlayerAnimationStateMachine


class PlayerBase(Entity):
    """可配置的玩家基类"""
    
    def __init__(self, config: dict = None):
        """
        初始化玩家
        :param config: 玩家配置字典
        """
        super().__init__([0.0, -0.8], 'player')
        
        # 基础属性（可由配置覆盖）
        self.name = "Player"
        self.hit_radius = 0.01       # 判定点半径
        self.graze_radius = 0.05     # 擦弹半径
        self.speed_high = 0.02       # 高速移动速度
        self.speed_low = 0.008       # 低速移动速度
        
        # 资源属性
        self.power = 1.00
        self.max_power = 4.00
        self.score = 0
        self.lives = 3
        self.bombs = 3
        self.graze = 0
        
        # 状态
        self.is_focused = False      # 低速模式
        self.is_shooting = False     # 射击中
        self.invincible_timer = 0.0  # 无敌时间
        self.death_timer = 0.0       # 死亡动画计时
        self.is_dead = False
        self.is_respawning = False
        
        # 上一帧位置（用于动画判断）
        self.last_pos_x = 0.0
        
        # 子系统
        self.bullet_pool = PlayerBulletPool(max_bullets=2000)
        self.shot_system = PlayerShotSystem(self.bullet_pool)
        self.animation = PlayerAnimationStateMachine()
        
        # 输入映射（可自定义）
        self.key_up = [pygame.K_UP, pygame.K_w]
        self.key_down = [pygame.K_DOWN, pygame.K_s]
        self.key_left = [pygame.K_LEFT, pygame.K_a]
        self.key_right = [pygame.K_RIGHT, pygame.K_d]
        self.key_focus = [pygame.K_LSHIFT, pygame.K_RSHIFT]
        self.key_shoot = [pygame.K_z]
        self.key_bomb = [pygame.K_x]
        
        # 回调
        self.on_death: Optional[Callable[[], None]] = None
        self.on_bomb: Optional[Callable[[], None]] = None
        self.on_graze: Optional[Callable[[int], None]] = None  # 参数: 擦弹数
        self.on_get_item: Optional[Callable[[str, Any], None]] = None
        
        # 符卡系统
        self.spellcards: list = []
        self.current_spellcard_idx = 0
        
        # 加载配置
        if config:
            self.load_config(config)
    
    def load_config(self, config: dict):
        """从配置字典加载玩家设置"""
        # 基础信息
        self.name = config.get('name', self.name)
        
        # 属性
        stats = config.get('stats', {})
        self.speed_high = stats.get('speed_high', self.speed_high)
        self.speed_low = stats.get('speed_low', self.speed_low)
        self.hit_radius = stats.get('hit_radius', self.hit_radius)
        self.graze_radius = stats.get('graze_radius', self.graze_radius)
        
        # 初始资源
        initial = config.get('initial', {})
        self.lives = initial.get('lives', self.lives)
        self.bombs = initial.get('bombs', self.bombs)
        self.power = initial.get('power', self.power)
        
        # 动画
        if 'animations' in config:
            self.animation.load_from_dict(config)
        
        # 射击类型
        if 'shot_types' in config:
            shot_types = config['shot_types']
            
            if 'unfocused' in shot_types:
                unfocused = create_shot_type_from_config(shot_types['unfocused'])
                focused = create_shot_type_from_config(
                    shot_types.get('focused', shot_types['unfocused'])
                )
                self.shot_system.set_shot_types(unfocused, focused)
        
        # Option配置
        if 'options' in config:
            options = create_options_from_config(config['options'])
            self.shot_system.set_options(options)
        
        # 符卡
        self.spellcards = config.get('spellcards', [])
        
        # 输入映射
        if 'keybindings' in config:
            kb = config['keybindings']
            if 'up' in kb:
                self.key_up = [getattr(pygame, k) for k in kb['up']]
            if 'down' in kb:
                self.key_down = [getattr(pygame, k) for k in kb['down']]
            if 'left' in kb:
                self.key_left = [getattr(pygame, k) for k in kb['left']]
            if 'right' in kb:
                self.key_right = [getattr(pygame, k) for k in kb['right']]
            if 'focus' in kb:
                self.key_focus = [getattr(pygame, k) for k in kb['focus']]
            if 'shoot' in kb:
                self.key_shoot = [getattr(pygame, k) for k in kb['shoot']]
            if 'bomb' in kb:
                self.key_bomb = [getattr(pygame, k) for k in kb['bomb']]
    
    def update(self, dt: float, keys):
        """
        更新玩家状态
        :param dt: 时间步长
        :param keys: pygame键盘状态
        """
        # 处理无敌时间
        if self.invincible_timer > 0:
            self.invincible_timer -= dt
        
        # 处理死亡状态
        if self.is_dead:
            self.death_timer += dt
            self.animation.update(dt, 0)
            return
        
        # 保存上一帧位置
        self.last_pos_x = self.pos[0]
        
        # 处理输入
        self._handle_input(dt, keys)
        
        # 更新射击系统
        self.shot_system.update(
            dt, 
            self.pos[0], self.pos[1],
            self.is_shooting, 
            self.is_focused,
            self.power
        )
        
        # 更新子弹
        self.bullet_pool.update(dt)
        
        # 更新动画
        move_x = self.pos[0] - self.last_pos_x
        self.animation.update(dt, move_x)
    
    def _handle_input(self, dt: float, keys):
        """处理输入"""
        # Focus状态
        self.is_focused = any(keys[k] for k in self.key_focus if k < len(keys))
        
        # 射击状态
        self.is_shooting = any(keys[k] for k in self.key_shoot if k < len(keys))
        
        # Bomb
        if any(keys[k] for k in self.key_bomb if k < len(keys)):
            self._use_bomb()
        
        # 移动
        current_speed = self.speed_low if self.is_focused else self.speed_high
        move_multiplier = dt * 60  # 帧率无关
        
        if any(keys[k] for k in self.key_up if k < len(keys)):
            self.pos[1] += current_speed * move_multiplier
        if any(keys[k] for k in self.key_down if k < len(keys)):
            self.pos[1] -= current_speed * move_multiplier
        if any(keys[k] for k in self.key_left if k < len(keys)):
            self.pos[0] -= current_speed * move_multiplier
        if any(keys[k] for k in self.key_right if k < len(keys)):
            self.pos[0] += current_speed * move_multiplier
        
        # 边界限制
        aspect_ratio = 384.0 / 448.0
        self.pos[0] = np.clip(self.pos[0], -1.0, 1.0)
        self.pos[1] = np.clip(self.pos[1], -1.0 / aspect_ratio, 1.0 / aspect_ratio)
    
    def _use_bomb(self):
        """使用符卡"""
        if self.bombs > 0 and not self.is_dead:
            self.bombs -= 1
            self.invincible_timer = 5.0  # 符卡期间无敌
            
            if self.on_bomb:
                self.on_bomb()
            
            # 执行符卡脚本（如果有）
            if self.spellcards and self.current_spellcard_idx < len(self.spellcards):
                spellcard = self.spellcards[self.current_spellcard_idx]
                # 这里可以调用符卡脚本
    
    def take_damage(self) -> bool:
        """
        玩家受到伤害
        :return: 是否真的受到伤害
        """
        if self.invincible_timer > 0 or self.is_dead:
            return False
        
        self.lives -= 1
        
        if self.lives <= 0:
            self.is_dead = True
            self.animation.play_death_animation()
            if self.on_death:
                self.on_death()
        else:
            # 被弹复活
            self.invincible_timer = 3.0
            self.pos = np.array([0.0, -0.8], dtype='f4')
            self.power = max(1.0, self.power - 1.0)  # 掉power
            self.is_respawning = True
        
        return True
    
    def add_power(self, amount: float):
        """增加power"""
        self.power = min(self.max_power, self.power + amount)
    
    def add_score(self, amount: int):
        """增加分数"""
        self.score += amount
    
    def add_graze(self, amount: int = 1):
        """增加擦弹"""
        self.graze += amount
        if self.on_graze:
            self.on_graze(amount)
    
    def get_current_sprite(self) -> str:
        """获取当前显示的精灵ID"""
        sprite = self.animation.get_current_sprite()
        return sprite if sprite else self.sprite_id
    
    def is_invincible(self) -> bool:
        """是否处于无敌状态"""
        return self.invincible_timer > 0
    
    def get_render_alpha(self) -> float:
        """获取渲染透明度（无敌时闪烁）"""
        if self.invincible_timer > 0:
            # 闪烁效果
            return 0.5 + 0.5 * np.sin(self.invincible_timer * 20)
        return 1.0
    
    def get_hit_position(self) -> tuple:
        """获取判定点位置"""
        return (self.pos[0], self.pos[1])
    
    def get_option_positions(self) -> list:
        """获取Option位置列表"""
        return self.shot_system.option_positions
    
    def check_bullet_collisions(self, enemies) -> list:
        """
        检查玩家子弹与敌人的碰撞
        :param enemies: 敌人列表
        :return: 碰撞列表
        """
        return self.bullet_pool.check_collision_with_enemies(enemies)
    
    def reset(self):
        """重置玩家状态（新游戏）"""
        self.pos = np.array([0.0, -0.8], dtype='f4')
        self.power = 1.00
        self.score = 0
        self.lives = 3
        self.bombs = 3
        self.graze = 0
        self.is_dead = False
        self.is_respawning = False
        self.invincible_timer = 0.0
        self.bullet_pool.clear()

"""
玩家基类 - 整合射击、动画、碰撞等所有系统
支持通过配置文件和脚本自定义行为
"""
import numpy as np
import pygame
import os
from typing import Optional, Callable, Dict, Any, List, Tuple

from ..entity import Entity
from .player_bullet import PlayerBulletPool
from .player_shot import PlayerShotSystem, create_shot_type_from_config, create_options_from_config
from .player_animation import PlayerAnimationStateMachine
from .player_script import PlayerScript, load_player_script


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
        self._power = 1.00
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
        
        # 纹理/精灵资源
        self.texture_path = ""       # 纹理文件路径
        self.sprites = {}            # 精灵定义 {sprite_id: {rect: [x,y,w,h], ...}}
        
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
        
        # 回调（供外部系统使用）
        self.on_death: Optional[Callable[[], None]] = None
        self.on_bomb_callback: Optional[Callable[[], None]] = None
        self.on_graze: Optional[Callable[[int], None]] = None
        self.on_get_item: Optional[Callable[[str, Any], None]] = None
        
        # 符卡系统
        self.spellcards: dict = {}
        self.spell_cooldown = 0.0
        
        # ========== 脚本系统 ==========
        self.script: Optional[PlayerScript] = None  # 自机行为脚本
        self._config_base_path: str = ""            # 配置文件所在目录
        
        # 子机位置（由脚本管理或使用默认）
        self.option_positions: List[Tuple[float, float]] = []
        
        # 加载配置
        if config:
            self.load_config(config)
    
    @property
    def power(self) -> float:
        return self._power
    
    @power.setter
    def power(self, value: float):
        old_power = self._power
        self._power = min(self.max_power, max(0, value))
        if self.script and old_power != self._power:
            self.script.on_power_change(old_power, self._power)
    
    def load_config(self, config: dict):
        """从配置字典加载玩家设置"""
        # 保存配置路径（用于加载脚本）
        self._config_base_path = config.get('_base_path', '')
        
        # 基础信息
        self.name = config.get('name', self.name)
        
        # 纹理路径
        if 'texture' in config and self._config_base_path:
            self.texture_path = os.path.join(self._config_base_path, config['texture'])
        
        # 精灵定义
        if 'sprites' in config:
            self.sprites = config['sprites']
        
        # 属性
        stats = config.get('stats', {})
        self.speed_high = stats.get('speed_high', self.speed_high)
        self.speed_low = stats.get('speed_low', self.speed_low)
        
        # hitbox_radius 和 graze_radius 在配置中是像素值，需要转换为归一化坐标
        # 192 是半屏宽度的像素数
        pixel_to_norm = 1.0 / 192.0
        if 'hitbox_radius' in stats:
            self.hit_radius = stats['hitbox_radius'] * pixel_to_norm
        elif 'hit_radius' in stats:
            self.hit_radius = stats['hit_radius']  # 已经是归一化值
        
        if 'graze_radius' in stats:
            self.graze_radius = stats['graze_radius'] * pixel_to_norm
        
        # 初始资源
        initial = config.get('initial', {})
        self.lives = initial.get('lives', self.lives)
        self.bombs = initial.get('bombs', self.bombs)
        self._power = initial.get('power', self._power)  # 绕过 setter
        
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
        self.spellcards = config.get('spellcards', {})
        
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
        
        # ========== 加载脚本 ==========
        script_file = config.get('script', 'script.py')
        if self._config_base_path:
            script_path = os.path.join(self._config_base_path, script_file)
            self.script = load_player_script(script_path, self)
            if self.script:
                # 传递配置中的脚本参数
                if hasattr(self.script, 'config'):
                    self.script.config = config.get('script_config', {})
                self.script.on_init()
    
    def update(self, dt: float, keys):
        """
        更新玩家状态
        :param dt: 时间步长
        :param keys: pygame键盘状态
        """
        # 处理无敌时间
        if self.invincible_timer > 0:
            self.invincible_timer -= dt
        
        # 处理符卡冷却
        if self.spell_cooldown > 0:
            self.spell_cooldown -= dt
        
        # 处理死亡状态
        if self.is_dead:
            self.death_timer += dt
            self.animation.update(dt, 0)
            return
        
        # 保存上一帧位置
        self.last_pos_x = self.pos[0]
        
        # 处理输入
        self._handle_input(dt, keys)
        
        # ========== 调用脚本更新 ==========
        if self.script:
            self.script.on_update(dt)
        
        # ========== 获取脚本射击参数 ==========
        shot_params = {}
        if self.script:
            shot_params = self.script.get_shot_params() or {}
        
        # 更新射击系统
        self.shot_system.update(
            dt, 
            self.pos[0], self.pos[1],
            self.is_shooting, 
            self.is_focused,
            self.power,
            spread_range=shot_params.get('spread_range'),
            target_angle=shot_params.get('target_angle'),
            damage_bonus=shot_params.get('damage_bonus', 1.0)
        )
        
        # 更新子弹
        self.bullet_pool.update(dt)
        
        # 更新动画
        move_x = self.pos[0] - self.last_pos_x
        self.animation.update(dt, move_x)
    
    def _handle_input(self, dt: float, keys):
        """处理输入"""
        # Focus状态
        self.is_focused = any(keys[k] for k in self.key_focus)
        
        # 射击状态
        self.is_shooting = any(keys[k] for k in self.key_shoot)
        
        # Bomb
        if any(keys[k] for k in self.key_bomb):
            self._use_bomb()
        
        # 移动
        current_speed = self.speed_low if self.is_focused else self.speed_high
        move_multiplier = dt * 60  # 帧率无关
        
        if any(keys[k] for k in self.key_up):
            self.pos[1] += current_speed * move_multiplier
        if any(keys[k] for k in self.key_down):
            self.pos[1] -= current_speed * move_multiplier
        if any(keys[k] for k in self.key_left):
            self.pos[0] -= current_speed * move_multiplier
        if any(keys[k] for k in self.key_right):
            self.pos[0] += current_speed * move_multiplier
        
        # 边界限制
        aspect_ratio = 384.0 / 448.0
        self.pos[0] = np.clip(self.pos[0], -1.0, 1.0)
        self.pos[1] = np.clip(self.pos[1], -1.0 / aspect_ratio, 1.0 / aspect_ratio)
    
    def _use_bomb(self):
        """使用符卡"""
        if self.bombs > 0 and not self.is_dead and self.spell_cooldown <= 0:
            # 调用脚本处理符卡
            if self.script and self.script.on_bomb(self.is_focused):
                # 脚本处理了符卡
                self.bombs -= 1
                return
            
            # 默认符卡行为
            self.bombs -= 1
            
            # 获取当前符卡配置
            spellcard = self.spellcards.get('focused' if self.is_focused else 'unfocused', {})
            invincible_time = spellcard.get('invincible_time', 300) / 60.0
            cooldown = spellcard.get('duration', 300) / 60.0
            
            self.invincible_timer = invincible_time
            self.spell_cooldown = cooldown
            
            if self.on_bomb_callback:
                self.on_bomb_callback()
    
    def set_target(self, target_pos: Optional[Tuple[float, float]]):
        """设置追踪目标位置"""
        self.target_pos = target_pos
    
    def find_nearest_enemy(self, enemies: list):
        """
        寻找最近的敌人作为追踪目标
        :param enemies: 敌人列表，每个敌人需要有 pos 属性
        """
        if not enemies:
            self.target_pos = None
            return
        
        min_dist = float('inf')
        nearest = None
        
        for enemy in enemies:
            if hasattr(enemy, 'pos'):
                ex, ey = enemy.pos[0], enemy.pos[1]
            elif isinstance(enemy, (list, tuple)):
                ex, ey = enemy[0], enemy[1]
            elif isinstance(enemy, dict):
                ex, ey = enemy.get('x', 0), enemy.get('y', 0)
            else:
                continue
            
            dx = ex - self.pos[0]
            dy = ey - self.pos[1]
            dist = dx * dx + dy * dy
            
            if dist < min_dist:
                min_dist = dist
                nearest = (ex, ey)
        
        self.target_pos = nearest
    
    def get_option_render_data(self) -> List[Tuple[float, float, int]]:
        """
        获取子机渲染数据
        :return: [(x, y, frame_index), ...]
        """
        # 优先使用脚本提供的子机位置
        if self.script:
            positions = self.script.get_option_positions()
            if positions:
                frame = int((self.animation.frame_timer * 60 / 3) % 16) if hasattr(self.animation, 'frame_timer') else 0
                return [(pos[0], pos[1], frame) for pos in positions]
        
        # 使用射击系统的子机位置
        result = []
        frame = int((self.animation.frame_timer * 60 / 3) % 16) if hasattr(self.animation, 'frame_timer') else 0
        
        for pos in self.shot_system.option_positions:
            result.append((pos[0], pos[1], frame))
        
        return result
    
    def get_state_info(self) -> dict:
        """获取状态信息（用于调试和UI显示）"""
        info = {
            'name': self.name,
            'pos': (self.pos[0], self.pos[1]),
            'power': self.power,
            'lives': self.lives,
            'bombs': self.bombs,
            'score': self.score,
            'graze': self.graze,
            'is_focused': self.is_focused,
            'bullet_count': self.bullet_pool.active_count,
            'option_count': len(self.shot_system.option_positions),
        }
        
        # 如果脚本提供额外状态信息
        if self.script:
            shot_params = self.script.get_shot_params() or {}
            info['spread_range'] = shot_params.get('spread_range')
            info['target_angle'] = shot_params.get('target_angle', 90.0)
            info['damage_bonus'] = shot_params.get('damage_bonus', 1.0)
        
        return info
    
    def take_damage(self) -> bool:
        """
        玩家受到伤害
        :return: 是否真的受到伤害
        """
        if self.invincible_timer > 0 or self.is_dead:
            return False
        
        # 调用脚本处理被弹
        if self.script and self.script.on_hit():
            return True  # 脚本处理了被弹
        
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
        if self.script:
            self.script.on_graze(amount)
        if self.on_graze:
            self.on_graze(amount)
    
    def get_current_sprite(self) -> dict:
        """获取当前显示的精灵信息（包含rect等）"""
        sprite_id = self.animation.get_current_sprite()
        if not sprite_id:
            sprite_id = self.sprite_id
        
        # 从sprites字典获取精灵信息
        if sprite_id and sprite_id in self.sprites:
            return self.sprites[sprite_id]
        
        # 返回默认
        return None
    
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

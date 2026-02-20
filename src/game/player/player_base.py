"""
玩家基类 - 整合射击、动画、碰撞等所有系统
支持通过配置文件和脚本自定义行为
v3: 脚本优先控制发射，支持 bullet_anims / option_anims / skills
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
from .option_entity import OptionManager
from .skill_manager import SkillSlotManager


class PlayerBase(Entity):
    """可配置的玩家基类"""
    
    def __init__(self, config: dict = None):
        super().__init__([0.0, -0.8], 'player')
        
        self.name = "Player"
        self.hit_radius = 0.01
        self.graze_radius = 0.05
        self.speed_high = 0.02
        self.speed_low = 0.008
        
        self._power = 1.00
        self.max_power = 4.00
        self.score = 0
        self.lives = 3
        self.bombs = 3
        self.graze = 0

        self.render_size_px: Optional[float] = None
        self.render_downsample: bool = False

        self.hitbox_offset_x: float = 0.0
        self.hitbox_offset_y: float = 0.0
        
        self.is_focused = False
        self.is_shooting = False
        self.invincible_timer = 0.0
        self.death_timer = 0.0
        self.is_dead = False
        self.is_respawning = False
        
        self.texture_path = ""
        self.bullet_texture_path = ""
        self.sprites = {}
        self.bullet_sprites = {}
        
        self.last_pos_x = 0.0
        
        # 子系统
        self.bullet_pool = PlayerBulletPool(max_bullets=2000)
        self.shot_system = PlayerShotSystem(self.bullet_pool)
        self.animation = PlayerAnimationStateMachine()
        self.option_manager = OptionManager()
        self.skill_manager = SkillSlotManager()

        # v3 资源数据（供脚本和渲染使用）
        self.bullet_anims: Dict[str, dict] = {}
        self.option_anims: Dict[str, dict] = {}
        self._config_version: str = "2.0"
        
        self.key_up = [pygame.K_UP, pygame.K_w]
        self.key_down = [pygame.K_DOWN, pygame.K_s]
        self.key_left = [pygame.K_LEFT, pygame.K_a]
        self.key_right = [pygame.K_RIGHT, pygame.K_d]
        self.key_focus = [pygame.K_LSHIFT, pygame.K_RSHIFT]
        self.key_shoot = [pygame.K_z]
        self.key_bomb = [pygame.K_x]
        
        self.on_death: Optional[Callable[[], None]] = None
        self.on_bomb_callback: Optional[Callable[[], None]] = None
        self.on_graze: Optional[Callable[[int], None]] = None
        self.on_get_item: Optional[Callable[[str, Any], None]] = None
        
        self.spellcards: dict = {}
        self.spell_cooldown = 0.0
        
        self.script: Optional[PlayerScript] = None
        self._config_base_path: str = ""
        
        self.option_positions: List[Tuple[float, float]] = []
        
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
        """从配置字典加载玩家设置（支持 v2 和 v3）"""
        self._config_base_path = config.get('_base_path', '')
        self._config_version = config.get('version', '2.0')
        
        self.name = config.get('name', self.name)
        
        # 纹理路径
        if 'textures' in config and self._config_base_path:
            tex_map = config['textures']
            if 'player' in tex_map:
                self.texture_path = os.path.join(self._config_base_path, tex_map['player'])
            if 'bullet' in tex_map:
                self.bullet_texture_path = os.path.join(self._config_base_path, tex_map['bullet'])
        elif 'texture' in config and self._config_base_path:
            self.texture_path = os.path.join(self._config_base_path, config['texture'])

        if 'render_size_px' in config:
            try:
                value = float(config['render_size_px'])
                self.render_size_px = value if value > 0 else None
            except Exception:
                self.render_size_px = None
        if 'render_downsample' in config:
            self.render_downsample = bool(config.get('render_downsample', False))
        
        if 'sprites' in config:
            self.sprites = config['sprites']
            # 自动将 source="bullet" 的精灵也放入 bullet_sprites
            for sname, sdata in self.sprites.items():
                if isinstance(sdata, dict) and sdata.get('source') == 'bullet':
                    self.bullet_sprites[sname] = sdata
        if 'bullet_sprites' in config:
            self.bullet_sprites.update(config['bullet_sprites'])
        
        # 属性
        stats = config.get('stats', {})
        self.speed_high = stats.get('speed_high', self.speed_high)
        self.speed_low = stats.get('speed_low', self.speed_low)
        
        pixel_to_norm = 1.0 / 192.0
        if 'hitbox_radius' in stats:
            self.hit_radius = stats['hitbox_radius'] * pixel_to_norm
        elif 'hit_radius' in stats:
            self.hit_radius = stats['hit_radius']
        
        if 'graze_radius' in stats:
            self.graze_radius = stats['graze_radius'] * pixel_to_norm

        _sprite_w = 32.0
        if self.sprites:
            for _spr in self.sprites.values():
                _sprite_w = max(1.0, float(_spr.get('rect', [0,0,32,32])[2]))
                break
        _render_px = self.render_size_px if self.render_size_px else _sprite_w
        _offset_scale = float(_render_px) / _sprite_w * pixel_to_norm

        if 'hitbox_offset_x' in stats:
            try:
                self.hitbox_offset_x = float(stats['hitbox_offset_x']) * _offset_scale
            except Exception:
                self.hitbox_offset_x = 0.0
        if 'hitbox_offset_y' in stats:
            try:
                self.hitbox_offset_y = -float(stats['hitbox_offset_y']) * _offset_scale
            except Exception:
                self.hitbox_offset_y = 0.0
        
        initial = config.get('initial', {})
        self.lives = initial.get('lives', self.lives)
        self.bombs = initial.get('bombs', self.bombs)
        self._power = initial.get('power', self._power)
        
        if 'animations' in config:
            self.animation.load_from_dict(config)
        
        # v2 射击类型（仍支持作为 fallback）
        if 'shot_types' in config:
            shot_types = config['shot_types']
            if 'unfocused' in shot_types:
                unfocused = create_shot_type_from_config(shot_types['unfocused'])
                focused = create_shot_type_from_config(
                    shot_types.get('focused', shot_types['unfocused'])
                )
                self.shot_system.set_shot_types(unfocused, focused)
        
        if 'options' in config and config['options']:
            options = create_options_from_config(config['options'])
            self.shot_system.set_options(options)
        
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
        
        # ========== v3: 加载 bullet_anims ==========
        if 'bullet_anims' in config:
            self.bullet_anims = config['bullet_anims']
            self._register_bullet_anims()

        # ========== v3: 加载 option_anims ==========
        if 'option_anims' in config:
            self.option_anims = config['option_anims']

        # ========== v3: 加载 skills ==========
        if 'skills' in config:
            self.skill_manager.load_from_config(config['skills'])

        # ========== 加载脚本 ==========
        script_file = config.get('script', 'script.py')
        if self._config_base_path:
            script_path = os.path.join(self._config_base_path, script_file)
            self.script = load_player_script(script_path, self)
            if self.script:
                if hasattr(self.script, 'config'):
                    self.script.config = config.get('script_config', {})
                self.script.on_init()

    def _register_bullet_anims(self):
        """将 config 中的 bullet_anims 注册到 bullet_pool 的动画系统"""
        for anim_name, anim_cfg in self.bullet_anims.items():
            frames = anim_cfg.get('frames', [])
            if not frames:
                continue
            # 确保所有帧精灵都注册了
            for sid in frames:
                if sid not in self.bullet_pool.sprite_id_to_idx:
                    n = len(self.bullet_pool.sprite_id_to_idx)
                    self.bullet_pool.register_sprite(sid, n)
            self.bullet_pool.register_bullet_anim(
                anim_name, frames,
                frame_duration=anim_cfg.get('frame_duration', 4),
                loop=anim_cfg.get('loop', True),
            )

    def _has_v3_script_shooting(self) -> bool:
        """检查脚本是否实现了 v3 的 on_shoot"""
        if not self.script:
            return False
        return type(self.script).on_shoot is not PlayerScript.on_shoot

    def update(self, dt: float, keys):
        if self.invincible_timer > 0:
            self.invincible_timer -= dt
        
        if self.spell_cooldown > 0:
            self.spell_cooldown -= dt
        
        if self.is_dead:
            self.death_timer += dt
            self.animation.update(dt, 0)
            return
        
        self.last_pos_x = self.pos[0]
        
        self._handle_input(dt, keys)
        
        # 更新技能冷却
        self.skill_manager.update(dt)

        # 调用脚本每帧更新
        if self.script:
            self.script.on_update(dt)
        
        # ========== 射击：v3 脚本优先 ==========
        if self.is_shooting:
            if self._has_v3_script_shooting():
                self.script.on_shoot(self.is_focused)
            else:
                # v2 fallback: 使用 ShotSystem
                shot_params = {}
                if self.script:
                    shot_params = self.script.get_shot_params() or {}
                self.shot_system.update(
                    dt, self.pos[0], self.pos[1],
                    self.is_shooting, self.is_focused, self.power,
                    spread_range=shot_params.get('spread_range'),
                    target_angle=shot_params.get('target_angle'),
                    damage_bonus=shot_params.get('damage_bonus', 1.0)
                )
        else:
            # 不射击时仍需更新 shot_system（option 位置 lerp 等）
            if not self._has_v3_script_shooting():
                shot_params = {}
                if self.script:
                    shot_params = self.script.get_shot_params() or {}
                self.shot_system.update(
                    dt, self.pos[0], self.pos[1],
                    False, self.is_focused, self.power,
                    spread_range=shot_params.get('spread_range'),
                    target_angle=shot_params.get('target_angle'),
                    damage_bonus=shot_params.get('damage_bonus', 1.0)
                )

        # 更新僚机位置和动画（v3）
        self.option_manager.update(
            self.pos[0], self.pos[1], self.is_focused, dt,
            anim_data={
                name: {
                    'frame_count': len(cfg.get('frames', [])),
                    'frame_duration': cfg.get('frame_duration', 8) / 60.0,
                    'loop': cfg.get('loop', True),
                }
                for name, cfg in self.option_anims.items()
            } if self.option_anims else None
        )
        
        # 更新子弹
        self.bullet_pool.update(dt)
        
        # 更新动画
        move_x = self.pos[0] - self.last_pos_x
        self.animation.update(dt, move_x)
    
    def _handle_input(self, dt: float, keys):
        self.is_focused = any(keys[k] for k in self.key_focus)
        self.is_shooting = any(keys[k] for k in self.key_shoot)
        
        if any(keys[k] for k in self.key_bomb):
            self._use_bomb()
        
        current_speed = self.speed_low if self.is_focused else self.speed_high
        move_multiplier = dt * 60
        
        if any(keys[k] for k in self.key_up):
            self.pos[1] += current_speed * move_multiplier
        if any(keys[k] for k in self.key_down):
            self.pos[1] -= current_speed * move_multiplier
        if any(keys[k] for k in self.key_left):
            self.pos[0] -= current_speed * move_multiplier
        if any(keys[k] for k in self.key_right):
            self.pos[0] += current_speed * move_multiplier
        
        aspect_ratio = 384.0 / 448.0
        self.pos[0] = np.clip(self.pos[0], -1.0, 1.0)
        self.pos[1] = np.clip(self.pos[1], -1.0 / aspect_ratio, 1.0 / aspect_ratio)
    
    def _use_bomb(self):
        if self.bombs > 0 and not self.is_dead and self.spell_cooldown <= 0:
            # v3: 尝试技能系统
            if self.skill_manager.slots:
                if self.skill_manager.try_activate('bomb'):
                    if self.script and self.script.on_skill('bomb'):
                        self.bombs -= 1
                        return
            
            if self.script and self.script.on_bomb(self.is_focused):
                self.bombs -= 1
                return
            
            self.bombs -= 1
            spellcard = self.spellcards.get('focused' if self.is_focused else 'unfocused', {})
            invincible_time = spellcard.get('invincible_time', 300) / 60.0
            cooldown = spellcard.get('duration', 300) / 60.0
            self.invincible_timer = invincible_time
            self.spell_cooldown = cooldown
            if self.on_bomb_callback:
                self.on_bomb_callback()
    
    def set_target(self, target_pos: Optional[Tuple[float, float]]):
        self.target_pos = target_pos
    
    def find_nearest_enemy(self, enemies: list):
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
        """获取子机渲染数据（v3 优先使用 option_manager）"""
        # v3: 使用 option_manager
        if self.option_manager.options:
            return self.option_manager.get_render_data()

        # v2 fallback: 使用脚本位置
        if self.script:
            positions = self.script.get_option_positions()
            if positions:
                frame = int((self.animation.frame_timer * 60 / 3) % 16) if hasattr(self.animation, 'frame_timer') else 0
                return [(pos[0], pos[1], frame) for pos in positions]
        
        result = []
        frame = int((self.animation.frame_timer * 60 / 3) % 16) if hasattr(self.animation, 'frame_timer') else 0
        for pos in self.shot_system.option_positions:
            result.append((pos[0], pos[1], frame))
        return result
    
    def get_state_info(self) -> dict:
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
            'option_count': len(self.option_manager.options) or len(self.shot_system.option_positions),
        }
        if self.script:
            shot_params = self.script.get_shot_params() or {}
            info['spread_range'] = shot_params.get('spread_range')
            info['target_angle'] = shot_params.get('target_angle', 90.0)
            info['damage_bonus'] = shot_params.get('damage_bonus', 1.0)
        return info
    
    def take_damage(self) -> bool:
        if self.invincible_timer > 0 or self.is_dead:
            return False
        if self.script and self.script.on_hit():
            return True
        self.lives -= 1
        if self.lives <= 0:
            self.is_dead = True
            self.animation.play_death_animation()
            if self.on_death:
                self.on_death()
        else:
            self.invincible_timer = 3.0
            self.pos = np.array([0.0, -0.8], dtype='f4')
            self.power = max(1.0, self.power - 1.0)
            self.is_respawning = True
        return True
    
    def add_power(self, amount: float):
        self.power = min(self.max_power, self.power + amount)
    
    def add_score(self, amount: int):
        self.score += amount
    
    def add_graze(self, amount: int = 1):
        self.graze += amount
        if self.script:
            self.script.on_graze(amount)
        if self.on_graze:
            self.on_graze(amount)
    
    def get_current_sprite(self) -> dict:
        sprite_id = self.animation.get_current_sprite()
        if not sprite_id:
            sprite_id = self.sprite_id
        if sprite_id and sprite_id in self.sprites:
            return self.sprites[sprite_id]
        return None
    
    def is_invincible(self) -> bool:
        return self.invincible_timer > 0
    
    def get_render_alpha(self) -> float:
        if self.invincible_timer > 0:
            return 0.5 + 0.5 * np.sin(self.invincible_timer * 20)
        return 1.0
    
    def get_hit_position(self) -> tuple:
        return (self.pos[0] + self.hitbox_offset_x, self.pos[1] + self.hitbox_offset_y)
    
    def get_option_positions(self) -> list:
        if self.option_manager.options:
            return self.option_manager.get_positions()
        return self.shot_system.option_positions
    
    def check_bullet_collisions(self, enemies) -> list:
        return self.bullet_pool.check_collision_with_enemies(enemies)
    
    def reset(self):
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
        self.option_manager.clear()

"""
玩家射击系统
支持多种发射模式、射击间隔、power等级等
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from .player_bullet import PlayerBulletPool


@dataclass
class ShotPattern:
    """单个射击点的配置"""
    offset_x: float = 0.0          # 相对玩家的X偏移
    offset_y: float = 0.0          # 相对玩家的Y偏移
    angle: float = 90.0            # 发射角度（度数，90=向上）
    angle_offset: float = 0.0      # 角度偏移（用于扇形）
    speed: float = 0.8             # 子弹速度
    bullet_sprite: str = ''        # 子弹精灵ID
    damage: float = 10.0           # 伤害
    bullet_type: int = 0           # 子弹类型（0=普通，1=追踪）
    homing_strength: float = 0.0   # 追踪强度
    scale: float = 1.0             # 缩放
    color: tuple = None            # 颜色
    sound: str = ''                # 发射音效


@dataclass
class ShotType:
    """射击类型（低速/高速模式）"""
    name: str = ''
    fire_rate: float = 0.05        # 射击间隔（秒）
    patterns: List[ShotPattern] = field(default_factory=list)
    power_patterns: dict = field(default_factory=dict)  # power等级对应的额外pattern
    
    def get_patterns_for_power(self, power: float) -> List[ShotPattern]:
        """根据power等级获取发射pattern"""
        result = list(self.patterns)  # 基础pattern
        
        # 添加power等级对应的额外pattern
        for threshold, extra_patterns in sorted(self.power_patterns.items()):
            if power >= threshold:
                result.extend(extra_patterns)
        
        return result


@dataclass
class OptionConfig:
    """Option（子机）配置"""
    offset_x: float = 0.0
    offset_y: float = 0.0
    sprite: str = ''
    shot_patterns: List[ShotPattern] = field(default_factory=list)
    focused_offset_x: float = 0.0  # 低速模式时的位置
    focused_offset_y: float = 0.0


class PlayerShotSystem:
    """玩家射击系统"""
    
    def __init__(self, bullet_pool: PlayerBulletPool):
        """
        初始化射击系统
        :param bullet_pool: 玩家子弹池
        """
        self.bullet_pool = bullet_pool
        
        # 射击类型
        self.shot_unfocused: Optional[ShotType] = None  # 高速模式射击
        self.shot_focused: Optional[ShotType] = None    # 低速模式射击
        
        # Option系统
        self.options: List[OptionConfig] = []
        self.option_positions: List[tuple] = []  # 当前option位置
        
        # 射击状态
        self.fire_timer = 0.0
        self.is_shooting = False
        
        # 音效回调
        self.on_shot_sound: Optional[Callable[[str], None]] = None
    
    def set_shot_types(self, unfocused: ShotType, focused: ShotType):
        """设置射击类型"""
        self.shot_unfocused = unfocused
        self.shot_focused = focused
    
    def set_options(self, options: List[OptionConfig]):
        """设置Option配置"""
        self.options = options
        self.option_positions = [(opt.offset_x, opt.offset_y) for opt in options]
    
    def update(self, dt: float, player_x: float, player_y: float, 
               is_shooting: bool, is_focused: bool, power: float):
        """
        更新射击系统
        :param dt: 时间步长
        :param player_x: 玩家X坐标
        :param player_y: 玩家Y坐标
        :param is_shooting: 是否按住射击键
        :param is_focused: 是否低速模式
        :param power: 当前power值
        """
        self.is_shooting = is_shooting
        
        # 更新Option位置（低速模式收拢）
        self._update_option_positions(player_x, player_y, is_focused, dt)
        
        # 更新射击计时器
        if self.fire_timer > 0:
            self.fire_timer -= dt
        
        # 射击
        if is_shooting and self.fire_timer <= 0:
            shot_type = self.shot_focused if is_focused else self.shot_unfocused
            if shot_type:
                self._fire(player_x, player_y, shot_type, power)
                self.fire_timer = shot_type.fire_rate
    
    def _update_option_positions(self, player_x: float, player_y: float, 
                                  is_focused: bool, dt: float):
        """更新Option位置"""
        lerp_speed = 10.0  # 位置插值速度
        
        for i, opt in enumerate(self.options):
            if is_focused:
                target_x = player_x + opt.focused_offset_x
                target_y = player_y + opt.focused_offset_y
            else:
                target_x = player_x + opt.offset_x
                target_y = player_y + opt.offset_y
            
            # 平滑插值
            if i < len(self.option_positions):
                curr_x, curr_y = self.option_positions[i]
                new_x = curr_x + (target_x - curr_x) * min(1.0, lerp_speed * dt)
                new_y = curr_y + (target_y - curr_y) * min(1.0, lerp_speed * dt)
                self.option_positions[i] = (new_x, new_y)
    
    def _fire(self, player_x: float, player_y: float, 
              shot_type: ShotType, power: float):
        """发射子弹"""
        patterns = shot_type.get_patterns_for_power(power)
        sound_played = False
        
        # 玩家本体发射
        for pattern in patterns:
            self._spawn_bullet(
                player_x + pattern.offset_x,
                player_y + pattern.offset_y,
                pattern
            )
            
            # 播放音效（只播放一次）
            if not sound_played and pattern.sound and self.on_shot_sound:
                self.on_shot_sound(pattern.sound)
                sound_played = True
        
        # Option发射
        for i, opt in enumerate(self.options):
            if i >= len(self.option_positions):
                continue
            
            opt_x, opt_y = self.option_positions[i]
            
            for pattern in opt.shot_patterns:
                self._spawn_bullet(opt_x + pattern.offset_x, 
                                   opt_y + pattern.offset_y, 
                                   pattern)
    
    def _spawn_bullet(self, x: float, y: float, pattern: ShotPattern):
        """生成单颗子弹"""
        angle_rad = math.radians(pattern.angle + pattern.angle_offset)
        
        self.bullet_pool.spawn(
            x=x,
            y=y,
            angle=angle_rad,
            speed=pattern.speed,
            sprite_id=pattern.bullet_sprite,
            damage=pattern.damage,
            bullet_type=pattern.bullet_type,
            homing_strength=pattern.homing_strength,
            scale=pattern.scale,
            color=pattern.color
        )
    
    def get_option_render_data(self) -> List[tuple]:
        """
        获取Option渲染数据
        :return: [(x, y, sprite_id), ...]
        """
        result = []
        for i, opt in enumerate(self.options):
            if i < len(self.option_positions):
                x, y = self.option_positions[i]
                result.append((x, y, opt.sprite))
        return result


def create_shot_type_from_config(config: dict) -> ShotType:
    """从配置字典创建ShotType"""
    shot_type = ShotType(
        name=config.get('name', ''),
        fire_rate=config.get('fire_rate', 0.05)
    )
    
    # 解析基础pattern
    for p_config in config.get('patterns', []):
        pattern = ShotPattern(
            offset_x=p_config.get('offset', [0, 0])[0] if 'offset' in p_config else p_config.get('offset_x', 0),
            offset_y=p_config.get('offset', [0, 0])[1] if 'offset' in p_config else p_config.get('offset_y', 0),
            angle=p_config.get('angle', 90),
            angle_offset=p_config.get('angle_offset', 0),
            speed=p_config.get('speed', 0.8),
            bullet_sprite=p_config.get('bullet', ''),
            damage=p_config.get('damage', 10),
            bullet_type=1 if p_config.get('homing', False) else 0,
            homing_strength=p_config.get('homing_strength', 5.0) if p_config.get('homing', False) else 0,
            scale=p_config.get('scale', 1.0),
            sound=p_config.get('sound', '')
        )
        shot_type.patterns.append(pattern)
    
    # 解析power等级pattern
    for power_str, p_list in config.get('power_patterns', {}).items():
        power_threshold = float(power_str)
        extra_patterns = []
        
        for p_config in p_list:
            pattern = ShotPattern(
                offset_x=p_config.get('offset', [0, 0])[0] if 'offset' in p_config else p_config.get('offset_x', 0),
                offset_y=p_config.get('offset', [0, 0])[1] if 'offset' in p_config else p_config.get('offset_y', 0),
                angle=p_config.get('angle', 90),
                angle_offset=p_config.get('angle_offset', 0),
                speed=p_config.get('speed', 0.8),
                bullet_sprite=p_config.get('bullet', ''),
                damage=p_config.get('damage', 10),
                bullet_type=1 if p_config.get('homing', False) else 0,
                homing_strength=p_config.get('homing_strength', 5.0) if p_config.get('homing', False) else 0,
                scale=p_config.get('scale', 1.0),
                sound=p_config.get('sound', '')
            )
            extra_patterns.append(pattern)
        
        shot_type.power_patterns[power_threshold] = extra_patterns
    
    return shot_type


def create_options_from_config(config: list) -> List[OptionConfig]:
    """从配置创建Option列表"""
    options = []
    
    for opt_config in config:
        opt = OptionConfig(
            offset_x=opt_config.get('offset', [0, 0])[0],
            offset_y=opt_config.get('offset', [0, 0])[1],
            focused_offset_x=opt_config.get('focused_offset', [0, 0])[0],
            focused_offset_y=opt_config.get('focused_offset', [0, 0])[1],
            sprite=opt_config.get('sprite', '')
        )
        
        # 解析Option的射击pattern
        for p_config in opt_config.get('shot_patterns', []):
            pattern = ShotPattern(
                offset_x=p_config.get('offset', [0, 0])[0] if 'offset' in p_config else 0,
                offset_y=p_config.get('offset', [0, 0])[1] if 'offset' in p_config else 0,
                angle=p_config.get('angle', 90),
                speed=p_config.get('speed', 0.8),
                bullet_sprite=p_config.get('bullet', ''),
                damage=p_config.get('damage', 5),
                scale=p_config.get('scale', 0.8)
            )
            opt.shot_patterns.append(pattern)
        
        options.append(opt)
    
    return options

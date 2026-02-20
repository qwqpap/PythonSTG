"""
玩家动画状态机
处理 idle/move_left/move_right 等动画切换
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum, auto


class AnimationState(Enum):
    """动画状态枚举"""
    IDLE = auto()
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    MOVE_LEFT_FULL = auto()   # 完全左移（倾斜最大）
    MOVE_RIGHT_FULL = auto()  # 完全右移
    DEATH = auto()
    SPAWN = auto()


@dataclass
class Animation:
    """单个动画定义"""
    name: str
    frames: List[str]          # 精灵帧ID列表
    fps: float = 8.0           # 帧率
    loop: bool = True          # 是否循环
    next_state: str = None     # 播放完后切换到的状态（非循环动画用）
    
    def get_frame_duration(self) -> float:
        """获取每帧持续时间"""
        return 1.0 / self.fps if self.fps > 0 else 0.1


@dataclass
class AnimationConfig:
    """动画配置"""
    animations: Dict[str, Animation] = field(default_factory=dict)
    
    # 状态转换设置
    transition_speed: float = 8.0  # 状态转换插值速度
    
    # 左右移动检测阈值
    move_threshold: float = 0.001  # 速度超过此值视为移动
    full_tilt_frames: int = 8      # 多少帧后进入完全倾斜状态


class PlayerAnimationStateMachine:
    """玩家动画状态机"""
    
    def __init__(self):
        self.config: Optional[AnimationConfig] = None
        
        # 当前状态
        self.current_state: AnimationState = AnimationState.IDLE
        self.current_animation: Optional[Animation] = None
        
        # 动画播放状态
        self.frame_index: int = 0
        self.frame_timer: float = 0.0
        self.animation_finished: bool = False
        
        # 移动检测
        self.move_direction: int = 0  # -1=左, 0=静止, 1=右
        self.move_frames: int = 0     # 持续移动帧数
        
        # 状态名到枚举的映射
        self._state_map = {
            'idle': AnimationState.IDLE,
            'move_left': AnimationState.MOVE_LEFT,
            'move_right': AnimationState.MOVE_RIGHT,
            'move_left_full': AnimationState.MOVE_LEFT_FULL,
            'move_right_full': AnimationState.MOVE_RIGHT_FULL,
            'death': AnimationState.DEATH,
            'spawn': AnimationState.SPAWN,
        }
    
    def load_config(self, config: AnimationConfig):
        """加载动画配置"""
        self.config = config
        self._set_state(AnimationState.IDLE)
    
    def load_from_dict(self, anim_dict: dict):
        """从字典加载动画配置"""
        # 支持两种格式：
        # 1. 直接是animations配置: {"animations": {...}, "transition_speed": ...}
        # 2. 嵌套在animations键下: {"animations": {"animations": {...}, ...}}
        
        anim_config = anim_dict.get('animations', anim_dict)
        
        # 如果animations键的值还有animations子键，说明是嵌套格式
        if isinstance(anim_config, dict) and 'animations' in anim_config:
            inner_config = anim_config
            anim_data = inner_config.get('animations', {})
        else:
            inner_config = anim_dict
            anim_data = anim_config if isinstance(anim_config, dict) else {}
        
        config = AnimationConfig(
            transition_speed=inner_config.get('transition_speed', 8.0),
            move_threshold=inner_config.get('move_threshold', 0.001),
            full_tilt_frames=inner_config.get('full_tilt_frames', 8)
        )
        
        # 解析动画定义
        for name, data in anim_data.items():
            if not isinstance(data, dict):
                continue
            # 支持 fps 或 frame_duration（游戏帧/动画帧，60fps 下）
            fps_val = data.get('fps', 8.0)
            if 'frame_duration' in data:
                fd = data['frame_duration']
                fps_val = 60.0 / fd if fd > 0 else 8.0
            anim = Animation(
                name=name,
                frames=data.get('frames', []),
                fps=fps_val,
                loop=data.get('loop', True),
                next_state=data.get('next_state', None)
            )
            config.animations[name] = anim
        
        self.load_config(config)
    
    def update(self, dt: float, move_x: float):
        """
        更新动画状态
        :param dt: 时间步长
        :param move_x: X方向移动量（用于判断左右移动）
        """
        if not self.config:
            return
        
        # 检测移动方向
        threshold = self.config.move_threshold
        
        if move_x < -threshold:
            new_direction = -1
        elif move_x > threshold:
            new_direction = 1
        else:
            new_direction = 0
        
        # 更新移动帧计数
        if new_direction == self.move_direction and new_direction != 0:
            self.move_frames += 1
        else:
            self.move_frames = 0 if new_direction == 0 else 1
        
        self.move_direction = new_direction
        
        # 根据移动状态切换动画
        self._update_state_from_movement()
        
        # 更新动画帧
        self._update_animation(dt)
    
    def _update_state_from_movement(self):
        """根据移动状态更新动画状态"""
        if self.current_state in (AnimationState.DEATH, AnimationState.SPAWN):
            # 特殊状态不受移动影响
            return
        
        full_tilt_threshold = self.config.full_tilt_frames if self.config else 8
        
        if self.move_direction == -1:
            # 向左移动
            if self.move_frames >= full_tilt_threshold:
                target_state = AnimationState.MOVE_LEFT_FULL
            else:
                target_state = AnimationState.MOVE_LEFT
        elif self.move_direction == 1:
            # 向右移动
            if self.move_frames >= full_tilt_threshold:
                target_state = AnimationState.MOVE_RIGHT_FULL
            else:
                target_state = AnimationState.MOVE_RIGHT
        else:
            # 静止
            target_state = AnimationState.IDLE
        
        if target_state != self.current_state:
            self._set_state(target_state)
    
    def _set_state(self, state: AnimationState):
        """设置动画状态"""
        self.current_state = state
        
        # 获取对应的动画名称
        state_to_anim = {
            AnimationState.IDLE: 'idle',
            AnimationState.MOVE_LEFT: 'move_left',
            AnimationState.MOVE_RIGHT: 'move_right',
            AnimationState.MOVE_LEFT_FULL: 'move_left_full',
            AnimationState.MOVE_RIGHT_FULL: 'move_right_full',
            AnimationState.DEATH: 'death',
            AnimationState.SPAWN: 'spawn',
        }
        
        anim_name = state_to_anim.get(state, 'idle')
        
        # 如果没有对应的完全倾斜动画，使用普通倾斜
        if self.config and anim_name not in self.config.animations:
            if state == AnimationState.MOVE_LEFT_FULL:
                anim_name = 'move_left'
            elif state == AnimationState.MOVE_RIGHT_FULL:
                anim_name = 'move_right'
        
        if self.config and anim_name in self.config.animations:
            self.current_animation = self.config.animations[anim_name]
            self.frame_index = 0
            self.frame_timer = 0.0
            self.animation_finished = False
    
    def _update_animation(self, dt: float):
        """更新动画帧"""
        if not self.current_animation or not self.current_animation.frames:
            return
        
        self.frame_timer += dt
        frame_duration = self.current_animation.get_frame_duration()
        
        while self.frame_timer >= frame_duration:
            self.frame_timer -= frame_duration
            self.frame_index += 1
            
            # 处理动画结束
            if self.frame_index >= len(self.current_animation.frames):
                if self.current_animation.loop:
                    self.frame_index = 0
                else:
                    self.frame_index = len(self.current_animation.frames) - 1
                    self.animation_finished = True
                    
                    # 切换到下一个状态
                    if self.current_animation.next_state:
                        next_state = self._state_map.get(
                            self.current_animation.next_state, 
                            AnimationState.IDLE
                        )
                        self._set_state(next_state)
    
    def get_current_sprite(self) -> str:
        """获取当前应该显示的精灵ID"""
        if not self.current_animation or not self.current_animation.frames:
            return ''
        
        idx = min(self.frame_index, len(self.current_animation.frames) - 1)
        return self.current_animation.frames[idx]
    
    def play_death_animation(self):
        """播放死亡动画"""
        self._set_state(AnimationState.DEATH)
    
    def play_spawn_animation(self):
        """播放出生动画"""
        self._set_state(AnimationState.SPAWN)
    
    def is_animation_finished(self) -> bool:
        """当前动画是否播放完毕"""
        return self.animation_finished
    
    def get_state_name(self) -> str:
        """获取当前状态名称"""
        return self.current_state.name.lower()

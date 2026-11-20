"""
敌人贴图对象 - LuaSTG风格自动动画管理

当设置 sprite = "enemy1" 时，引擎自动：
1. 查找 enemy1_idle / enemy1_move_left / enemy1_move_right 子动画
2. 可选：enemy1_move_left_full / enemy1_move_right_full（两阶段：加速→全速）
3. 根据敌人X方向速度自动切换动画状态
4. 如果没有子动画，退回到单一循环动画

用法（引擎内部自动调用，关卡脚本无需关心）：
    render_obj = EnemyRenderObject("enemy1", asset_manager)
    # 每帧
    render_obj.update(vx=enemy.x - prev_x, dt=1/60)
    frame, texture_path = render_obj.get_current_frame()
"""

from typing import Optional, Tuple, TYPE_CHECKING
from ..animation import AnimationPlayback, SpriteVisual, resolve_animation

if TYPE_CHECKING:
    from src.resource.texture_asset import TextureAssetManager, SpriteFrame


class EnemyRenderObject:
    """敌人贴图对象 - 自动处理idle/move_left/move_right动画切换，支持两阶段(加速→全速)"""

    def __init__(self, sprite_name: str, asset_manager: 'TextureAssetManager'):
        self.sprite_name = sprite_name
        self.asset_manager = asset_manager

        # 尝试方向性模式：查找 {name}_idle, {name}_move_left, {name}_move_right
        self.idle_anim = asset_manager.get_animation(f"{sprite_name}_idle")
        self.left_anim = asset_manager.get_animation(f"{sprite_name}_move_left")
        self.right_anim = asset_manager.get_animation(f"{sprite_name}_move_right")
        self.directional = all([self.idle_anim, self.left_anim, self.right_anim])

        # 两阶段动画（可选）：move_left_full / move_right_full
        self.left_full_anim = asset_manager.get_animation(f"{sprite_name}_move_left_full")
        self.right_full_anim = asset_manager.get_animation(f"{sprite_name}_move_right_full")
        self.has_full_tilt = self.left_full_anim is not None and self.right_full_anim is not None

        # 退回到单一动画
        self.simple_anim = None
        if not self.directional:
            self.simple_anim = asset_manager.get_animation(sprite_name)

        # 动画状态
        self.state = 'idle'
        self.anim_time = 0.0
        self.move_threshold = 0.001
        self.move_frames = 0
        self._last_dir = 0  # -1=左, 0=静止, 1=右
        self.full_tilt_frames = 8
        self._manual = None
        self._resume_auto = True
        self.paused = False

    def play(self, name, *, loop=None, speed=1.0, resume_auto=True):
        candidate = AnimationPlayback(resolve_animation(self.asset_manager, name),
                                      loop=loop, speed=speed)
        self.stop()
        self._manual = candidate
        self._resume_auto = bool(resume_auto)
        return candidate

    def stop(self):
        if self._manual is not None:
            self._manual.stop()
        self._manual = None

    @property
    def is_valid(self) -> bool:
        """是否成功加载了动画"""
        return self.directional or self.simple_anim is not None

    def update(self, vx: float, dt: float, *, runtime_frame=None):
        """
        每帧更新：根据X速度自动选择动画状态
        支持两阶段：静止→加速(move_left/right)→全速(move_left_full/right_full)

        Args:
            vx: X方向速度（正=右移，负=左移）
            dt: 时间步长（秒）
        """
        if self.paused:
            return
        if (self._manual is not None and (runtime_frame is None
                or self._manual._born_frame != runtime_frame)):
            self._manual.advance(dt * 60.0)
        self.anim_time += dt

        if not self.directional:
            return

        if vx < -self.move_threshold:
            new_direction = -1
        elif vx > self.move_threshold:
            new_direction = 1
        else:
            new_direction = 0

        # 更新移动帧计数
        if new_direction != 0:
            self.move_frames = self.move_frames + 1 if new_direction == self._last_dir else 1
        else:
            self.move_frames = 0
        self._last_dir = new_direction

        # 确定目标状态
        if new_direction == -1:
            if self.has_full_tilt and self.move_frames >= self.full_tilt_frames:
                new_state = 'move_left_full'
            else:
                new_state = 'move_left'
        elif new_direction == 1:
            if self.has_full_tilt and self.move_frames >= self.full_tilt_frames:
                new_state = 'move_right_full'
            else:
                new_state = 'move_right'
        else:
            new_state = 'idle'

        if new_state != self.state:
            self.state = new_state
            self.anim_time = 0.0

    def get_current_frame(self) -> Tuple[Optional['SpriteFrame'], Optional[str]]:
        """
        获取当前帧数据

        Returns:
            (SpriteFrame, texture_path) 或 (None, None)
        """
        if (self._manual is not None and not self._manual.cancelled
                and (not self._manual.finished or not self._resume_auto)):
            return self._manual.get_render_frame()
        anim = self._get_current_animation()
        if anim is None:
            return None, None

        frame = anim.get_frame_at_time(self.anim_time)
        return frame, anim.texture_path

    def _get_current_animation(self):
        """获取当前应播放的动画"""
        if not self.directional:
            return self.simple_anim
        s = self.state
        if s == 'idle':
            return self.idle_anim
        if s == 'move_left':
            return self.left_anim
        if s == 'move_right':
            return self.right_anim
        if s == 'move_left_full':
            return self.left_full_anim if self.has_full_tilt else self.left_anim
        if s == 'move_right_full':
            return self.right_full_anim if self.has_full_tilt else self.right_anim
        return self.idle_anim


class ActorAnimationControls:
    """Shared public visual API for the existing EnemyScript and BossBase."""

    @property
    def visual(self):
        if not hasattr(self, '_visual'):
            self._visual = SpriteVisual()
        return self._visual

    def set_visual(self, **values):
        """Visual-only offset/rotation/scale/color/alpha/blend; never changes hitboxes."""
        return self.visual.set(**values)

    def _animation_object(self):
        if self._render_obj is None:
            if self.ctx is None:
                raise RuntimeError('animation control requires a bound stage context')
            name = getattr(self, 'sprite', getattr(self, 'texture', ''))
            self._render_obj = EnemyRenderObject(name, self.ctx.animations.assets)
        return self._render_obj

    def play_animation(self, name, *, loop=None, speed=1.0, resume_auto=True):
        playback = self._animation_object().play(name, loop=loop, speed=speed,
                                                resume_auto=resume_auto)
        if self.ctx is not None:
            playback._born_frame = self.ctx.runtime_frame
        return playback

    def stop_animation(self):
        if self._render_obj is not None:
            self._render_obj.stop()

    def pause_animation(self):
        self._animation_object().paused = True

    def resume_animation(self):
        self._animation_object().paused = False

    def attach_animation(self, name, **options):
        if self.ctx is None:
            raise RuntimeError('attached animation requires a bound stage context')
        return self.ctx.attach_animation(self, name, **options)

    def update_animation(self):
        vx = self.x - self._prev_x
        self._prev_x = self.x
        if self._render_obj is not None:
            if self.ctx is None:
                self._render_obj.update(vx, 1.0/60.0)
            elif not self.ctx._animation_effects_paused:
                self._render_obj.update(vx, self.ctx.get_simulation_rate('effects')/60.0,
                                        runtime_frame=self.ctx.runtime_frame)

    def _dispose_animations(self):
        self.stop_animation()
        if self.ctx is not None:
            self.ctx.animations.remove_owner(self)
            self.ctx.trails.remove_owner(self)

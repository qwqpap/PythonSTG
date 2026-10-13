"""
敌人行为脚本基类 - 用于定义可复用的敌人行为

敌人脚本定义了一个敌人的完整行为：进场、攻击、退场。
每个敌人脚本是一个独立的协程，可以在波次中被实例化。

使用方式（在 game_content/stages/stageN/enemies/ 中定义）：

    from src.game.stage.enemy_script import EnemyScript

    class RedFairy(EnemyScript):
        hp = 30
        sprite = "enemy_fairy_red"
        score = 100

        async def run(self):
            # 从上方飞入
            await self.move_to(self.x, 0.3, duration=60)

            # 开火
            for _ in range(3):
                self.fire_circle(count=8, speed=2.0, color="red")
                await self.wait(20)

            # 飞走
            await self.move_to(self.x, -0.2, duration=60)

在波次脚本中使用：

    from src.game.stage.wave_base import Wave

    class MyWave(Wave):
        async def run(self):
            # 生成3个红色妖精
            for i in range(3):
                self.spawn_enemy("enemies/red_fairy", x=-0.3 + i * 0.3, y=1.0)
                await self.wait(30)
"""

import math
import types
import inspect
import operator
import numpy as np
from abc import ABC, abstractmethod
from typing import Optional, Callable, List, Any, Tuple, TYPE_CHECKING

from .danmaku_audio import resolve_fire_sound
from .motion import ActorControls
from ..tasks import FrameTaskOwner, cancel_tasks, pump_tasks
from ..bullet.behavior import BulletGroup

if TYPE_CHECKING:
    from .spellcard import SpellCardContext
    from .enemy_render import EnemyRenderObject


class EnemyScript(ActorControls, FrameTaskOwner, ABC):
    """
    敌人行为脚本基类

    定义一个敌人从出现到消失的完整行为。
    提供与 SpellCard 相似的弹幕和移动 API。
    """

    # ========== 子类覆盖这些属性 ==========
    hp: int = 30                        # 生命值
    sprite: str = "enemy_fairy"         # 精灵图
    score: int = 100                    # 击破得分
    hitbox_radius: float = 0.02         # 碰撞半径
    drops: dict = {}                    # 击破掉落 {"power": N, "point": N, "faith": N}
    clear_bullets_on_death: bool = False # 死亡时是否清除自身发射的子弹

    def __init__(self):
        self.x: float = 0.0
        self.y: float = 0.0
        self.ctx: Optional['SpellCardContext'] = None
        self._active: bool = False
        self._coroutine = None
        self._bullet_groups: List[BulletGroup] = []
        self._time: int = 0
        self._prev_x: float = 0.0
        self._render_obj: Optional['EnemyRenderObject'] = None
        self._next_danmaku_se_frame: int = 0
        self._init_tasks()

        # 回调
        self.on_death: Optional[Callable] = None
        self.on_out_of_bounds: Optional[Callable] = None

    @property
    def time(self) -> int:
        """存活帧数"""
        return self._time

    @property
    def time_seconds(self) -> float:
        """存活时间（秒）"""
        return self._time / 60.0

    @property
    def is_active(self) -> bool:
        return self._active

    def bind(self, ctx: 'SpellCardContext', x: float = 0, y: float = 0):
        """绑定上下文和初始位置（由引擎/波次调用）"""
        self.ctx = ctx
        self.x = x
        self.y = y

    def start(self):
        """启动敌人（由引擎/波次调用）"""
        self._reset_tasks()
        self._active = True
        self._time = 0
        self._next_danmaku_se_frame = 0
        self._prev_x = self.x
        self._init_render_object()
        self._coroutine = self._run_wrapper()

    async def _run_wrapper(self):
        """协程包装器"""
        try:
            await self.on_spawn()
            await self.run()
        except EnemyDeath:
            pass
        finally:
            self._active = False
            cancel_tasks(self)

    def update(self) -> bool:
        """每帧更新（由引擎调用）"""
        if not self._active:
            return False

        self._time += 1
        try:
            pump_tasks(self)
            # 计算X速度并更新贴图对象动画
            vx = self.x - self._prev_x
            self._prev_x = self.x
            if self._render_obj:
                self._render_obj.update(vx, 1.0 / 60.0)
            if self._active and not self._step_main():
                self.dispose()
            pump_tasks(self)
        except BaseException:
            self.dispose()
            raise
        return self._active

    def damage(self, amount: int):
        """受到伤害"""
        if not self._active or not self.interactable:
            return
        if type(self).on_hit is not EnemyScript.on_hit:
            # Advance one actual hit event immediately; delayed actions continue
            # on this enemy's update loop, never on individual bullets.
            try:
                self.spawn_task(self.on_hit(amount), immediate=True)
            except BaseException:
                self.dispose()
                raise
        if not self._active or not self.interactable or not self.damageable:
            return
        self.hp -= amount
        if self.hp <= 0:
            self.hp = 0
            self._on_death()

    def kill(self):
        """立即击杀"""
        self.hp = 0
        self._on_death()

    def _on_death(self):
        """死亡处理"""
        if not self._active:
            return
        self.dispose()

        if self.clear_bullets_on_death:
            self.clear_bullets()
        else:
            self._bullet_groups.clear()

        # 掉道具
        if self.ctx and self.drops:
            self.ctx.spawn_drop(self.x, self.y, **self.drops)

        # 加基础分
        if self.ctx and self.score > 0:
            self.ctx.add_score(self.score)

        if self.on_death:
            result = self.on_death(self)
            if inspect.isawaitable(result):
                if self.ctx is None:
                    if hasattr(result, "close"):
                        result.close()
                    raise RuntimeError("asynchronous death reaction requires a stage context")
                self.ctx.spawn_task(result)

    def _close_hit_tasks(self):
        cancel_tasks(self)

    # ==================== 贴图对象 ====================

    def _init_render_object(self):
        """初始化贴图对象（从 sprite 名称自动创建）"""
        if not self.sprite or not self.ctx:
            return
        try:
            from .enemy_render import EnemyRenderObject
            from src.resource.texture_asset import get_texture_asset_manager
            asset_manager = get_texture_asset_manager()
            render_obj = EnemyRenderObject(self.sprite, asset_manager)
            if render_obj.is_valid:
                self._render_obj = render_obj
        except Exception:
            pass

    def get_render_frame(self) -> Tuple[Optional[Any], Optional[str]]:
        """
        获取当前渲染帧（由渲染器调用）

        Returns:
            (SpriteFrame, texture_path) 或 (None, None)
        """
        if self._render_obj:
            return self._render_obj.get_current_frame()
        return None, None

    def clear_bullets(self, to_items: bool = False):
        """手动清除该敌人创建的所有子弹"""
        if self.ctx and self._bullet_groups:
            group = self._combine_bullet_groups(self._bullet_groups)
            if to_items:
                self.ctx.bullets_to_items(group)
            else:
                self.ctx.remove_bullets(group)
        self._bullet_groups.clear()

    @staticmethod
    def _combine_bullet_groups(groups):
        if len(groups) == 1:
            return groups[0]
        combined = BulletGroup(
            np.concatenate([group.indices for group in groups]),
            np.concatenate([group.generations for group in groups]),
            groups[0].pool_token,
        )
        combined.indices.flags.writeable = False
        combined.generations.flags.writeable = False
        return combined

    def track_bullets(self, indices):
        """Record fixed generations for one authored/runtime emission burst."""
        group = self.ctx.capture_bullets(indices)
        if len(group):
            self._bullet_groups.append(group)

    def _fire_angles(self, angles, speed, *, play_sound, **options):
        """Ordinary bursts use one pool allocation and one generation snapshot."""
        x = options.pop("x", self.x)
        y = options.pop("y", self.y)
        x = self.x if x is None else x
        y = self.y if y is None else y
        if play_sound:
            self._play_danmaku_se(
                count=len(angles), speed=speed,
                bullet_type=options.get("bullet_type", "ball_m"),
            )
        if type(self).fire is not EnemyScript.fire or any(
            name in options for name in ("delay", "init", "on_death", "owner")
        ):
            # Preserve explicit legacy single-shot callbacks and overrides,
            # without retaining a group object for every bullet in the burst.
            first_group = len(self._bullet_groups)
            bullets = [self.fire(x=x, y=y, angle=float(angle), speed=speed,
                                 play_sound=False, **options) for angle in angles]
            groups = self._bullet_groups[first_group:]
            if groups:
                self._bullet_groups[first_group:] = [self._combine_bullet_groups(groups)]
            return bullets
        positions = np.empty((len(angles), 2), dtype=np.float32)
        positions[:, 0], positions[:, 1] = x, y
        indices = self.ctx.create_bullets_batch(
            positions=positions, angles=angles,
            speeds=np.full(len(angles), speed, dtype=np.float32), **options,
        )
        self.track_bullets(indices)
        return indices.tolist() + [-1] * (len(angles) - len(indices))

    # ==================== 弹幕 API ====================

    def fire(self, angle: float = -90, speed: float = 2.0,
             bullet_type: str = "ball_m", color: str = "red",
             x: float = None, y: float = None, play_sound: bool = False, **kwargs):
        """
        发射子弹（默认从自身位置发射）

        Args:
            angle: 角度（度）
            speed: 速度
            bullet_type: 弹幕类型
            color: 颜色
            x, y: 发射位置（默认为自身位置）
        """
        if x is None:
            x = self.x
        if y is None:
            y = self.y
        if play_sound:
            self._play_danmaku_se(count=1, speed=speed, bullet_type=bullet_type)
        bullet = self.ctx.create_bullet(
            x=x, y=y, angle=angle, speed=speed,
            bullet_type=bullet_type, color=color, **kwargs
        )
        self.track_bullets([bullet])
        return bullet

    def fire_circle(self, count: int = 8, speed: float = 2.0,
                    start_angle: float = 0, play_sound: bool = True, **kwargs):
        """发射圆形弹幕"""
        count = operator.index(count)
        angles = (
            start_angle + np.arange(count, dtype=np.float32) * (360.0 / count)
            if count > 0 else np.empty(0, dtype=np.float32)
        )
        return self._fire_angles(angles, speed, play_sound=play_sound, **kwargs)

    def fire_polar(self, orbit_radius: float, theta: float,
                   radial_speed: float = 0.0, angular_velocity: float = 0.0,
                   bullet_type: str = "ball_m", color: str = "red",
                   center=None, render_mode: str = "velocity",
                   angle_offset: float = 0.0, collision_radius: float = 0.0,
                   play_sound: bool = False, **kwargs):
        """
        发射极坐标运动子弹。

        默认围绕当前敌人位置运动；角度单位为“度”。
        """
        if center is None:
            center = self

        if play_sound:
            effective_speed = abs(radial_speed) + abs(angular_velocity) * max(0.2, orbit_radius)
            self._play_danmaku_se(
                count=1,
                speed=effective_speed,
                bullet_type=bullet_type,
            )

        bullet = self.ctx.create_polar_bullet(
            center=center,
            orbit_radius=orbit_radius,
            theta=theta,
            radial_speed=radial_speed,
            angular_velocity=angular_velocity,
            bullet_type=bullet_type,
            color=color,
            render_mode=render_mode,
            angle_offset=angle_offset,
            collision_radius=collision_radius,
            **kwargs
        )
        self.track_bullets([bullet])
        return bullet

    def fire_orbit(self, *args, **kwargs):
        """`fire_polar` 的语义化别名。"""
        return self.fire_polar(*args, **kwargs)

    def fire_arc(self, count: int = 5, speed: float = 2.0,
                 center_angle: float = -90, arc_angle: float = 60,
                 play_sound: bool = True, **kwargs):
        """发射扇形弹幕"""
        count = operator.index(count)
        angles = np.asarray([center_angle], dtype=np.float32) if count == 1 else np.linspace(
            center_angle - arc_angle / 2, center_angle + arc_angle / 2,
            max(0, count), dtype=np.float32,
        )
        return self._fire_angles(angles, speed, play_sound=play_sound, **kwargs)

    def fire_at_player(self, speed: float = 2.0, offset_angle: float = 0,
                       play_sound: bool = True, **kwargs):
        """发射自机狙"""
        player = self.ctx.get_player()
        if player:
            dx = player.x - self.x
            dy = player.y - self.y
            angle = math.degrees(math.atan2(dy, dx)) + offset_angle
        else:
            angle = -90 + offset_angle
        return self.fire(angle=angle, speed=speed, play_sound=play_sound, **kwargs)

    def angle_to_player(self) -> float:
        """计算到玩家的角度"""
        player = self.ctx.get_player()
        if player:
            dx = player.x - self.x
            dy = player.y - self.y
            return math.degrees(math.atan2(dy, dx))
        return -90

    # ==================== 移动 API ====================

    # ==================== 等待 API ====================

    @types.coroutine
    def wait(self, frames: int):
        """等待指定帧数"""
        for _ in range(frames):
            yield

    @types.coroutine
    def wait_seconds(self, seconds: float):
        """等待指定秒数"""
        yield from self.wait(int(seconds * 60))

    @types.coroutine
    def wait_until(self, condition: Callable[[], bool]):
        """Wait for HP/time/state conditions on this actor's ordinary frame task."""
        while not condition():
            yield

    # ==================== 音频 API ====================

    def play_se(self, name: str, volume: float = None, min_interval: float = 0.0) -> bool:
        """播放音效"""
        if self.ctx and hasattr(self.ctx, 'play_se'):
            return self.ctx.play_se(name, volume, min_interval=min_interval)
        return False

    def _play_danmaku_se(self, count: int = 1, speed: float = 2.0,
                         bullet_type: str = "ball_m") -> bool:
        if self.time < self._next_danmaku_se_frame:
            return False

        sound_name, volume, min_interval, cooldown_frames = resolve_fire_sound(
            count=count,
            speed=speed,
            bullet_type=bullet_type,
        )
        if self.ctx and hasattr(self.ctx, 'play_danmaku_se'):
            played = self.ctx.play_danmaku_se(sound_name, volume=volume, min_interval=min_interval)
        else:
            played = self.play_se(sound_name, volume=volume, min_interval=min_interval)
        if played:
            self._next_danmaku_se_frame = self.time + cooldown_frames
        return played

    async def on_spawn(self):
        """出生回调（可覆盖）"""
        pass

    @abstractmethod
    async def run(self):
        """
        主行为逻辑（必须实现）

        定义敌人从出现到消失的完整行为。
        当 run() 结束时，敌人自动消失。
        """
        pass

    async def on_hit(self, damage: int):
        """被击中回调（可覆盖）"""
        pass


class EnemyDeath(Exception):
    """用于在协程中提前结束敌人的异常"""
    pass

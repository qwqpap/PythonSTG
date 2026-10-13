"""
符卡基类 - 所有符卡脚本的基础

符卡是最小的可复用单元，可以：
1. 被 Boss 在关卡中调用
2. 被练习模式单独加载
3. 独立定义弹幕逻辑

注意：使用 yield 风格的生成器，而不是 async/await
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, List, Callable, Generator
from dataclasses import dataclass
import math
import types
import operator
import inspect
import numpy as np

from .danmaku_audio import resolve_fire_sound
from ..tasks import FrameTaskOwner, cancel_tasks, pump_tasks
from ..bullet.behavior import BulletGroup

if TYPE_CHECKING:
    from .boss_base import BossBase


@dataclass
class SpellCardInfo:
    """符卡元信息"""
    name: str                          # 符卡名称，如 "月符「Moonlight Ray」"
    hp: int = 1500                     # 血量
    time_limit: float = 60.0           # 时间限制（秒）
    bonus: int = 1000000               # 满血击破奖励
    is_survival: bool = False          # 是否是生存符（不攻击Boss）
    is_timeout: bool = False           # 是否是耐久符（等待时间结束）
    practice_unlock: bool = True       # 是否可在练习模式解锁


class SpellCard(FrameTaskOwner, ABC):
    """
    符卡基类

    使用协程风格编写弹幕逻辑，支持：
    - await self.wait(frames) - 等待指定帧数
    - await self.wait_seconds(seconds) - 等待指定秒数
    - self.fire(...) - 发射子弹
    - self.fire_pattern(...) - 发射预定义弹幕图案
    """

    # 子类应覆盖的元信息
    name: str = "Unnamed Spell"
    hp: int = 1500
    time_limit: float = 60.0
    bonus: int = 1000000
    is_survival: bool = False
    is_timeout: bool = False
    practice_unlock: bool = True
    clear_on_end: bool = True

    def __init__(self):
        self.boss: Optional['BossBase'] = None
        self.ctx: Optional['SpellCardContext'] = None
        self._time: int = 0                      # 当前帧数
        self._timer_frames: int = 0
        self.end_reason: str | None = None
        self.end_reaction = None
        self._coroutine = None                   # 主协程
        self._active: bool = False
        self._bullet_groups: List[BulletGroup] = []
        self._pending_waits: List[Callable] = [] # 等待中的协程
        self._next_danmaku_se_frame: int = 0
        self._init_tasks()

    @property
    def time(self) -> int:
        """当前帧数"""
        return self._time

    @property
    def time_seconds(self) -> float:
        """当前时间（秒）"""
        return self._time / 60.0

    @property
    def time_remaining(self) -> float:
        """剩余时间（秒）"""
        return max(0.0, self.time_limit - self.elapsed_seconds)

    @property
    def timer_frames(self) -> int:
        """Boss countdown elapsed time, separate from the controller clock."""
        return self._timer_frames

    @property
    def elapsed_seconds(self) -> float:
        return self._timer_frames / 60.0

    def set_timer(self, elapsed_frames: int = 0):
        """Reset/change countdown without rewinding tasks, waits or Trace."""
        self._timer_frames = operator.index(elapsed_frames)

    def bind(self, boss: 'BossBase', ctx: 'SpellCardContext'):
        """绑定到 Boss 和上下文"""
        self.boss = boss
        self.ctx = ctx

    def start(self):
        """启动符卡"""
        self._reset_tasks()
        self._active = True
        self._time = 0
        self._timer_frames = 0
        self.end_reason = None
        self.end_reaction = None
        self._next_danmaku_se_frame = 0
        self._coroutine = self._run_wrapper()

    async def _run_wrapper(self):
        """包装器 - 处理 setup 和主循环"""
        try:
            await self.setup()
            await self.run()
        except SpellCardEnd:
            pass
        finally:
            cancel_tasks(self)

    def update(self) -> bool:
        """
        每帧更新
        返回: True 表示符卡仍在进行，False 表示结束
        """
        if not self._active:
            return False

        self._time += 1
        if self.ctx is None or not self.ctx.is_time_stopped('boss_timer'):
            self._timer_frames += 1

        # 检查时间限制
        if self.elapsed_seconds >= self.time_limit:
            self.end("timeout")
            return False

        # 推进协程
        try:
            pump_tasks(self)
            if self._active and not self._step_main():
                self.end_reason = 'completed'
                self.dispose()
            pump_tasks(self)
        except BaseException:
            self.dispose()
            raise
        return self._active

    def end(self, reason: str = "defeated"):
        """结束符卡"""
        if not self._active:
            return
        self.end_reason = reason
        self.dispose()
        if reason == "timeout":
            self._on_timeout()
            hook = 'on_timeout'
        else:
            self._on_defeated()
            hook = 'on_defeated'
        if getattr(type(self), hook) is not getattr(SpellCard, hook):
            reaction = getattr(self, hook)()
            if inspect.isawaitable(reaction) or inspect.isgenerator(reaction):
                if self.ctx is None:
                    reaction.close()
                    raise RuntimeError('asynchronous spell end hook requires a stage context')
                self.end_reaction = self.ctx.spawn_task(reaction)

    def _on_timeout(self):
        """时间耗尽"""
        # 可以被子类覆盖
        if self.clear_on_end:
            self.clear_bullets()

    def _on_defeated(self):
        """被击败"""
        # 可以被子类覆盖
        if self.clear_on_end:
            self.clear_bullets()

    # ==================== 子类实现 ====================

    async def setup(self):
        """
        符卡开始前的准备（可选覆盖）
        例如：Boss 移动到特定位置
        """
        pass

    @abstractmethod
    async def run(self):
        """
        主弹幕逻辑（必须实现）
        使用 while True 循环发射弹幕
        使用 await self.wait(frames) 等待
        """
        pass

    async def on_hit(self, damage: int):
        """Sparse boss-hit reaction. Runs in this spell's existing task scope."""
        pass

    def on_timeout(self) -> Generator:
        """时间结束回调（可选覆盖）"""
        return
        yield

    def on_defeated(self) -> Generator:
        """被击败回调（可选覆盖）"""
        return
        yield

    # ==================== 弹幕 API ====================

    def fire(self,
             x: float = None, y: float = None,
             angle: float = 0, speed: float = 2.0,
             bullet_type: str = "ball_m", color: str = "red",
             accel: float = 0, angle_accel: float = 0,
             play_sound: bool = False,
             **kwargs):
        """
        发射单发子弹

        Args:
            x, y: 发射位置（默认为 Boss 位置）
            angle: 发射角度（度，0=向右，90=向上）
            speed: 速度
            bullet_type: 子弹类型
            color: 颜色
            accel: 加速度
            angle_accel: 角度加速度（用于曲线弹）
        """
        if x is None:
            x = self.boss.x if self.boss else 0
        if y is None:
            y = self.boss.y if self.boss else 0

        if play_sound:
            self._play_danmaku_se(count=1, speed=speed, bullet_type=bullet_type)

        bullet = self.ctx.create_bullet(
            x=x, y=y,
            angle=angle, speed=speed,
            bullet_type=bullet_type, color=color,
            accel=accel, angle_accel=angle_accel,
            owner=self,
            **kwargs
        )
        self.track_bullets([bullet])
        return bullet

    def fire_at_player(self,
                       x: float = None, y: float = None,
                       speed: float = 2.0,
                       offset_angle: float = 0,
                       play_sound: bool = True,
                       **kwargs):
        """发射自机狙"""
        if x is None:
            x = self.boss.x if self.boss else 0
        if y is None:
            y = self.boss.y if self.boss else 0

        player = self.ctx.get_player()
        if player:
            dx = player.x - x
            dy = player.y - y
            angle = math.degrees(math.atan2(dy, dx)) + offset_angle
        else:
            angle = -90 + offset_angle  # 默认向下

        return self.fire(x=x, y=y, angle=angle, speed=speed, play_sound=play_sound, **kwargs)

    def fire_circle(self,
                    x: float = None, y: float = None,
                    count: int = 36,
                    speed: float = 2.0,
                    start_angle: float = 0,
                    play_sound: bool = True,
                    **kwargs):
        """发射圆形弹幕"""
        count = operator.index(count)
        angles = (
            start_angle + np.arange(count, dtype=np.float32) * (360.0 / count)
            if count > 0 else np.empty(0, dtype=np.float32)
        )
        return self._fire_angles(angles, speed, x=x, y=y, play_sound=play_sound, **kwargs)

    def fire_polar(self,
                   orbit_radius: float,
                   theta: float,
                   radial_speed: float = 0.0,
                   angular_velocity: float = 0.0,
                   bullet_type: str = "ball_m",
                   color: str = "red",
                   center=None,
                   render_mode: str = "velocity",
                   angle_offset: float = 0.0,
                   collision_radius: float = 0.0,
                   play_sound: bool = False,
                   **kwargs):
        """
        发射极坐标运动子弹。

        默认围绕当前 Boss 运动；角度单位为“度”。
        """
        if center is None:
            center = self.boss

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
            owner=self,
            **kwargs
        )
        self.track_bullets([bullet])
        return bullet

    def fire_orbit(self, *args, **kwargs):
        """`fire_polar` 的语义化别名。"""
        return self.fire_polar(*args, **kwargs)

    def fire_arc(self,
                 x: float = None, y: float = None,
                 count: int = 5,
                 speed: float = 2.0,
                 center_angle: float = -90,
                 arc_angle: float = 60,
                 play_sound: bool = True,
                 **kwargs):
        """发射扇形弹幕"""
        count = operator.index(count)
        angles = np.asarray([center_angle], dtype=np.float32) if count == 1 else np.linspace(
            center_angle - arc_angle / 2, center_angle + arc_angle / 2,
            max(0, count), dtype=np.float32,
        )
        return self._fire_angles(angles, speed, x=x, y=y, play_sound=play_sound, **kwargs)

    def clear_bullets(self, to_items: bool = False):
        """清除此符卡创建的所有子弹"""
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

    def _fire_angles(self, angles, speed, *, x, y, play_sound, **options):
        x = (self.boss.x if self.boss else 0) if x is None else x
        y = (self.boss.y if self.boss else 0) if y is None else y
        if play_sound:
            self._play_danmaku_se(
                count=len(angles), speed=speed,
                bullet_type=options.get("bullet_type", "ball_m"),
            )
        if type(self).fire is not SpellCard.fire or any(
            name in options for name in ("delay", "init", "on_death", "owner")
        ):
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

    # ==================== 音频 API ====================

    def play_se(self, name: str, volume: float = None, min_interval: float = 0.0) -> bool:
        """
        播放音效

        Args:
            name: 音效名称（如 "kira", "lazer", "explode"）
            volume: 音量覆盖 (0.0~1.0)
        """
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

    # ==================== 等待 API ====================

    @types.coroutine
    def wait(self, frames: int) -> Generator:
        """等待指定帧数"""
        for _ in range(frames):
            yield

    @types.coroutine
    def wait_seconds(self, seconds: float) -> Generator:
        """等待指定秒数"""
        yield from self.wait(int(seconds * 60))

    @types.coroutine
    def wait_until(self, condition: Callable[[], bool]) -> Generator:
        """等待直到条件满足"""
        while not condition():
            yield

    # ==================== 辅助方法 ====================

    def angle_to_player(self, x: float = None, y: float = None) -> float:
        """计算到自机的角度"""
        if x is None:
            x = self.boss.x if self.boss else 0
        if y is None:
            y = self.boss.y if self.boss else 0

        player = self.ctx.get_player()
        if player:
            dx = player.x - x
            dy = player.y - y
            return math.degrees(math.atan2(dy, dx))
        return -90  # 默认向下

    def get_info(self) -> SpellCardInfo:
        """获取符卡信息"""
        return SpellCardInfo(
            name=self.name,
            hp=self.hp,
            time_limit=self.time_limit,
            bonus=self.bonus,
            is_survival=self.is_survival,
            is_timeout=self.is_timeout,
            practice_unlock=self.practice_unlock
        )


class SpellCardEnd(Exception):
    """用于提前结束符卡的异常"""
    pass


class NonSpell(SpellCard):
    """
    非符基类

    非符通常没有名字显示，奖励较少
    """
    bonus = 100000
    practice_unlock = False  # 非符通常不能单独练习


class SpellCardContext:
    """
    符卡执行上下文

    提供弹幕系统接口，由游戏引擎实现
    """

    def is_time_stopped(self, domain: str) -> bool:
        """Minimal legacy contexts have no system time-stop controller."""
        return False

    def create_bullet(self, **kwargs):
        """创建子弹"""
        raise NotImplementedError

    def remove_bullet(self, bullet):
        """移除子弹"""
        raise NotImplementedError

    def bullet_to_item(self, bullet):
        """将子弹转换为道具"""
        raise NotImplementedError

    def create_laser(self, **kwargs):
        """创建直线激光"""
        raise NotImplementedError

    def create_bent_laser(self, **kwargs):
        """创建曲线激光"""
        raise NotImplementedError

    def remove_laser(self, laser, off_time: int = 0):
        """移除激光"""
        raise NotImplementedError

    def clear_all_lasers(self):
        """清除所有激光"""
        raise NotImplementedError

    def get_player(self):
        """获取玩家"""
        raise NotImplementedError

    def get_enemies(self):
        """获取所有敌人"""
        raise NotImplementedError

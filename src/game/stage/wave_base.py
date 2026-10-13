"""
波次基类 - 用于定义道中敌人波次

波次脚本定义了一段时间内的子弹/敌人出现模式。
与 SpellCard 不同的是，波次不绑定 Boss，也没有 HP/时间限制。

支持两种编写风格：

1. 函数风格（简单情况）：
    def run(ctx):
        for i in range(8):
            ctx.create_bullet(x=i*0.2, y=0.9, angle=-90, speed=2.0,
                              bullet_type="rice", color="blue")
        for _ in range(60):
            yield

2. 类风格（复杂情况，推荐）：
    from src.game.stage.wave_base import Wave

    class MyWave(Wave):
        async def run(self):
            for i in range(8):
                self.fire(x=i*0.2, y=0.9, angle=-90, speed=2.0,
                          bullet_type="rice", color="blue")
            await self.wait(60)
"""

import math
import types
import operator
import numpy as np
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

from .danmaku_audio import resolve_fire_sound
from ..tasks import FrameTaskOwner, pump_tasks

if TYPE_CHECKING:
    from .spellcard import SpellCardContext


class Wave(FrameTaskOwner, ABC):
    """
    波次基类

    提供与 SpellCard 相似的弹幕 API，但不绑定 Boss。
    内容作者只需要实现 run() 方法。

    示例：
        class OpeningWave(Wave):
            async def run(self):
                for wave_num in range(3):
                    for i in range(8):
                        x = -0.7 + i * 0.2
                        self.fire(x=x, y=0.9, angle=-90, speed=1.8,
                                  bullet_type="rice", color="blue")
                    await self.wait(30)
    """

    def __init__(self):
        self.ctx: Optional['SpellCardContext'] = None
        self._time: int = 0
        self._next_danmaku_se_frame: int = 0
        self._coroutine = None
        self._active = False
        self._init_tasks()

    def bind(self, ctx: 'SpellCardContext'):
        """绑定上下文（由引擎调用）"""
        self.ctx = ctx

    @property
    def time(self) -> int:
        """当前帧数"""
        return self._time

    @property
    def time_seconds(self) -> float:
        """当前时间（秒）"""
        return self._time / 60.0

    def execute(self):
        """
        执行波次，返回一个生成器（由引擎调用）

        这个方法将 async def run() 转换为 yield 风格的生成器，
        让 StageScript 可以用 yield from 来驱动。
        """
        self._time = 0
        self._next_danmaku_se_frame = 0
        self._reset_tasks()
        self._active = True
        self._coroutine = self.run()
        try:
            while self._active:
                pump_tasks(self)
                if not self._active or not self._step_main():
                    break
                pump_tasks(self)
                self._time += 1
                yield
        finally:
            self.dispose()

    # ==================== 弹幕 API ====================

    def fire(self, x: float, y: float, angle: float = -90, speed: float = 2.0,
             bullet_type: str = "ball_m", color: str = "red",
             play_sound: bool = False, **kwargs):
        """
        发射子弹

        Args:
            x, y: 发射位置
            angle: 角度（度，0=右, 90=上, -90=下）
            speed: 速度
            bullet_type: 弹幕类型
            color: 颜色
        """
        if play_sound:
            self._play_danmaku_se(count=1, speed=speed, bullet_type=bullet_type)

        return self.ctx.create_bullet(
            x=x, y=y, angle=angle, speed=speed,
            bullet_type=bullet_type, color=color, **kwargs
        )

    def fire_circle(self, x: float, y: float, count: int = 16,
                    speed: float = 2.0, start_angle: float = 0,
                    play_sound: bool = True, **kwargs):
        """发射圆形弹幕"""
        count = operator.index(count)
        angles = (
            start_angle + np.arange(count, dtype=np.float32) * (360.0 / count)
            if count > 0 else np.empty(0, dtype=np.float32)
        )
        return self._fire_angles(angles, speed, x=x, y=y, play_sound=play_sound, **kwargs)

    def _fire_angles(self, angles, speed, *, x, y, play_sound, **options):
        if play_sound:
            self._play_danmaku_se(
                count=len(angles), speed=speed,
                bullet_type=options.get("bullet_type", "ball_m"),
            )
        if type(self).fire is not Wave.fire or any(
            name in options for name in ("delay", "init", "on_death", "owner")
        ):
            return [self.fire(x=x, y=y, angle=float(angle), speed=speed,
                              play_sound=False, **options) for angle in angles]
        positions = np.empty((len(angles), 2), dtype=np.float32)
        positions[:, 0], positions[:, 1] = x, y
        indices = self.ctx.create_bullets_batch(
            positions=positions, angles=angles,
            speeds=np.full(len(angles), speed, dtype=np.float32), **options,
        )
        return indices.tolist() + [-1] * (len(angles) - len(indices))

    def fire_arc(self, x: float, y: float, count: int = 5,
                 speed: float = 2.0, center_angle: float = -90,
                 arc_angle: float = 60, play_sound: bool = True, **kwargs):
        """发射扇形弹幕"""
        count = operator.index(count)
        angles = np.asarray([center_angle], dtype=np.float32) if count == 1 else np.linspace(
            center_angle - arc_angle / 2, center_angle + arc_angle / 2,
            max(0, count), dtype=np.float32,
        )
        return self._fire_angles(angles, speed, x=x, y=y, play_sound=play_sound, **kwargs)

    def fire_polar(self, center, orbit_radius: float, theta: float,
                   radial_speed: float = 0.0, angular_velocity: float = 0.0,
                   bullet_type: str = "ball_m", color: str = "red",
                   render_mode: str = "velocity", angle_offset: float = 0.0,
                   collision_radius: float = 0.0, play_sound: bool = False, **kwargs):
        """
        发射极坐标运动子弹。

        Args:
            center: (x, y) / 拥有 x,y 的对象 / callable
            orbit_radius: 初始半径
            theta: 初始角度（度）
        """
        if play_sound:
            effective_speed = abs(radial_speed) + abs(angular_velocity) * max(0.2, orbit_radius)
            self._play_danmaku_se(
                count=1,
                speed=effective_speed,
                bullet_type=bullet_type,
            )

        return self.ctx.create_polar_bullet(
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

    def fire_orbit(self, *args, **kwargs):
        """`fire_polar` 的语义化别名。"""
        return self.fire_polar(*args, **kwargs)

    def fire_at_player(self, x: float, y: float, speed: float = 2.0,
                       offset_angle: float = 0, play_sound: bool = True, **kwargs):
        """发射自机狙"""
        player = self.ctx.get_player()
        if player:
            dx = player.x - x
            dy = player.y - y
            angle = math.degrees(math.atan2(dy, dx)) + offset_angle
        else:
            angle = -90 + offset_angle
        return self.fire(x=x, y=y, angle=angle, speed=speed, play_sound=play_sound, **kwargs)

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

    # ==================== 敌人生成 API ====================

    def spawn_enemy_class(self, enemy_class: type, x: float = 0.0, y: float = 1.0):
        """
        生成敌人实例

        Args:
            enemy_class: 敌人类（必须是 EnemyScript 的子类）
            x: 初始X坐标
            y: 初始Y坐标

        Returns:
            敌人实例

        Example:
            from game_content.stages.stage1.enemies.fairy import Enemy1Custom

            enemy = self.spawn_enemy_class(Enemy1Custom, x=0.0, y=1.0)
        """
        if not self.ctx:
            print("[Wave] 警告: 无上下文，无法生成敌人")
            return None

        # 实例化敌人
        enemy = enemy_class()

        # 绑定上下文和位置
        enemy.bind(self.ctx, x, y)

        # 启动敌人
        enemy.start()

        # 添加到上下文管理（如果支持）
        if hasattr(self.ctx, 'add_enemy_script'):
            self.ctx.add_enemy_script(enemy)

        return enemy

    # ==================== 子类实现 ====================

    @abstractmethod
    async def run(self):
        """
        主波次逻辑（必须实现）

        使用 await self.wait(frames) 控制节奏
        使用 self.fire(...) 发射子弹
        """
        pass

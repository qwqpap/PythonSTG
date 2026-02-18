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
from abc import ABC, abstractmethod
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .spellcard import SpellCardContext


class Wave(ABC):
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
        coro = self.run()
        try:
            while True:
                coro.send(None)
                self._time += 1
                yield
        except StopIteration:
            pass
    
    # ==================== 弹幕 API ====================
    
    def fire(self, x: float, y: float, angle: float = -90, speed: float = 2.0,
             bullet_type: str = "ball_m", color: str = "red", **kwargs):
        """
        发射子弹
        
        Args:
            x, y: 发射位置
            angle: 角度（度，0=右, 90=上, -90=下）
            speed: 速度
            bullet_type: 弹幕类型
            color: 颜色
        """
        return self.ctx.create_bullet(
            x=x, y=y, angle=angle, speed=speed,
            bullet_type=bullet_type, color=color, **kwargs
        )
    
    def fire_circle(self, x: float, y: float, count: int = 16,
                    speed: float = 2.0, start_angle: float = 0, **kwargs):
        """发射圆形弹幕"""
        bullets = []
        for i in range(count):
            angle = start_angle + (360.0 / count) * i
            b = self.fire(x=x, y=y, angle=angle, speed=speed, **kwargs)
            bullets.append(b)
        return bullets
    
    def fire_arc(self, x: float, y: float, count: int = 5,
                 speed: float = 2.0, center_angle: float = -90,
                 arc_angle: float = 60, **kwargs):
        """发射扇形弹幕"""
        bullets = []
        if count == 1:
            return [self.fire(x=x, y=y, angle=center_angle, speed=speed, **kwargs)]
        start = center_angle - arc_angle / 2
        step = arc_angle / (count - 1)
        for i in range(count):
            angle = start + step * i
            b = self.fire(x=x, y=y, angle=angle, speed=speed, **kwargs)
            bullets.append(b)
        return bullets
    
    def fire_at_player(self, x: float, y: float, speed: float = 2.0,
                       offset_angle: float = 0, **kwargs):
        """发射自机狙"""
        player = self.ctx.get_player()
        if player:
            dx = player.x - x
            dy = player.y - y
            angle = math.degrees(math.atan2(dy, dx)) + offset_angle
        else:
            angle = -90 + offset_angle
        return self.fire(x=x, y=y, angle=angle, speed=speed, **kwargs)
    
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

    def play_se(self, name: str, volume: float = None) -> bool:
        """播放音效"""
        if self.ctx and hasattr(self.ctx, 'play_se'):
            return self.ctx.play_se(name, volume)
        return False

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

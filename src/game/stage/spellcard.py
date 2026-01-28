"""
符卡基类 - 所有符卡脚本的基础

符卡是最小的可复用单元，可以：
1. 被 Boss 在关卡中调用
2. 被练习模式单独加载
3. 独立定义弹幕逻辑

注意：使用 yield 风格的生成器，而不是 async/await
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, List, Callable, Any, Generator
from dataclasses import dataclass, field
import math

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


class SpellCard(ABC):
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
    
    def __init__(self):
        self.boss: Optional['BossBase'] = None
        self.ctx: Optional['SpellCardContext'] = None
        self._time: int = 0                      # 当前帧数
        self._coroutine = None                   # 主协程
        self._active: bool = False
        self._bullets: List[Any] = []            # 此符卡创建的子弹
        self._pending_waits: List[Callable] = [] # 等待中的协程
    
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
        return self.time_limit - self.time_seconds
    
    def bind(self, boss: 'BossBase', ctx: 'SpellCardContext'):
        """绑定到 Boss 和上下文"""
        self.boss = boss
        self.ctx = ctx
    
    def start(self):
        """启动符卡"""
        self._active = True
        self._time = 0
        self._coroutine = self._run_wrapper()
    
    async def _run_wrapper(self):
        """包装器 - 处理 setup 和主循环"""
        try:
            await self.setup()
            await self.run()
        except SpellCardEnd:
            pass
    
    def update(self) -> bool:
        """
        每帧更新
        返回: True 表示符卡仍在进行，False 表示结束
        """
        if not self._active:
            return False
        
        self._time += 1
        
        # 检查时间限制
        if self.time_seconds >= self.time_limit:
            self._on_timeout()
            return False
        
        # 推进协程
        if self._coroutine:
            try:
                self._coroutine.send(None)
            except StopIteration:
                self._active = False
                return False
        
        return True
    
    def end(self, reason: str = "defeated"):
        """结束符卡"""
        self._active = False
        if reason == "timeout":
            self._on_timeout()
        else:
            self._on_defeated()
    
    def _on_timeout(self):
        """时间耗尽"""
        # 可以被子类覆盖
        self.clear_bullets()
    
    def _on_defeated(self):
        """被击败"""
        # 可以被子类覆盖
        self.clear_bullets()
    
    # ==================== 子类实现 ====================
    
    def setup(self) -> Generator:
        """
        符卡开始前的准备（可选覆盖）
        例如：Boss 移动到特定位置
        使用 yield 暂停
        """
        return
        yield  # 使其成为生成器
    
    @abstractmethod
    def run(self) -> Generator:
        """
        主弹幕逻辑（必须实现）
        使用 while True 循环发射弹幕
        使用 yield from self.wait(frames) 等待
        """
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
        
        bullet = self.ctx.create_bullet(
            x=x, y=y,
            angle=angle, speed=speed,
            bullet_type=bullet_type, color=color,
            accel=accel, angle_accel=angle_accel,
            owner=self,
            **kwargs
        )
        self._bullets.append(bullet)
        return bullet
    
    def fire_at_player(self,
                       x: float = None, y: float = None,
                       speed: float = 2.0,
                       offset_angle: float = 0,
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
        
        return self.fire(x=x, y=y, angle=angle, speed=speed, **kwargs)
    
    def fire_circle(self,
                    x: float = None, y: float = None,
                    count: int = 36,
                    speed: float = 2.0,
                    start_angle: float = 0,
                    **kwargs):
        """发射圆形弹幕"""
        bullets = []
        for i in range(count):
            angle = start_angle + (360.0 / count) * i
            b = self.fire(x=x, y=y, angle=angle, speed=speed, **kwargs)
            bullets.append(b)
        return bullets
    
    def fire_arc(self,
                 x: float = None, y: float = None,
                 count: int = 5,
                 speed: float = 2.0,
                 center_angle: float = -90,
                 arc_angle: float = 60,
                 **kwargs):
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
    
    def clear_bullets(self, to_items: bool = False):
        """清除此符卡创建的所有子弹"""
        for bullet in self._bullets:
            if to_items:
                self.ctx.bullet_to_item(bullet)
            else:
                self.ctx.remove_bullet(bullet)
        self._bullets.clear()
    
    # ==================== 等待 API ====================
    
    def wait(self, frames: int) -> Generator:
        """等待指定帧数"""
        for _ in range(frames):
            yield
    
    def wait_seconds(self, seconds: float) -> Generator:
        """等待指定秒数"""
        yield from self.wait(int(seconds * 60))
    
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
    
    def create_bullet(self, **kwargs):
        """创建子弹"""
        raise NotImplementedError
    
    def remove_bullet(self, bullet):
        """移除子弹"""
        raise NotImplementedError
    
    def bullet_to_item(self, bullet):
        """将子弹转换为道具"""
        raise NotImplementedError
    
    def get_player(self):
        """获取玩家"""
        raise NotImplementedError
    
    def get_enemies(self):
        """获取所有敌人"""
        raise NotImplementedError

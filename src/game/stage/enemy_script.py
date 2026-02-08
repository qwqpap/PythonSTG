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
from abc import ABC, abstractmethod
from typing import Optional, Callable, List, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .spellcard import SpellCardContext


class EnemyScript(ABC):
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
    
    def __init__(self):
        self.x: float = 0.0
        self.y: float = 0.0
        self.ctx: Optional['SpellCardContext'] = None
        self._active: bool = False
        self._coroutine = None
        self._bullets: List[Any] = []
        self._time: int = 0
        
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
        self._active = True
        self._time = 0
        self._coroutine = self._run_wrapper()
    
    async def _run_wrapper(self):
        """协程包装器"""
        try:
            await self.on_spawn()
            await self.run()
        except EnemyDeath:
            pass
        except Exception as e:
            print(f"[EnemyScript] 错误: {e}")
        finally:
            self._active = False
    
    def update(self) -> bool:
        """每帧更新（由引擎调用）"""
        if not self._active:
            return False
        
        self._time += 1
        
        if self._coroutine:
            try:
                self._coroutine.send(None)
            except StopIteration:
                self._active = False
                return False
        
        return True
    
    def damage(self, amount: int):
        """受到伤害"""
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
        self._active = False
        # 清除该敌人创建的子弹
        for bullet_idx in self._bullets:
            if self.ctx:
                self.ctx.remove_bullet(bullet_idx)
        self._bullets.clear()
        
        if self.on_death:
            self.on_death(self)
    
    # ==================== 弹幕 API ====================
    
    def fire(self, angle: float = -90, speed: float = 2.0,
             bullet_type: str = "ball_m", color: str = "red",
             x: float = None, y: float = None, **kwargs):
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
        bullet = self.ctx.create_bullet(
            x=x, y=y, angle=angle, speed=speed,
            bullet_type=bullet_type, color=color, **kwargs
        )
        self._bullets.append(bullet)
        return bullet
    
    def fire_circle(self, count: int = 8, speed: float = 2.0,
                    start_angle: float = 0, **kwargs):
        """发射圆形弹幕"""
        bullets = []
        for i in range(count):
            angle = start_angle + (360.0 / count) * i
            b = self.fire(angle=angle, speed=speed, **kwargs)
            bullets.append(b)
        return bullets
    
    def fire_arc(self, count: int = 5, speed: float = 2.0,
                 center_angle: float = -90, arc_angle: float = 60, **kwargs):
        """发射扇形弹幕"""
        bullets = []
        if count == 1:
            return [self.fire(angle=center_angle, speed=speed, **kwargs)]
        start = center_angle - arc_angle / 2
        step = arc_angle / (count - 1)
        for i in range(count):
            angle = start + step * i
            b = self.fire(angle=angle, speed=speed, **kwargs)
            bullets.append(b)
        return bullets
    
    def fire_at_player(self, speed: float = 2.0, offset_angle: float = 0, **kwargs):
        """发射自机狙"""
        player = self.ctx.get_player()
        if player:
            dx = player.x - self.x
            dy = player.y - self.y
            angle = math.degrees(math.atan2(dy, dx)) + offset_angle
        else:
            angle = -90 + offset_angle
        return self.fire(angle=angle, speed=speed, **kwargs)
    
    def angle_to_player(self) -> float:
        """计算到玩家的角度"""
        player = self.ctx.get_player()
        if player:
            dx = player.x - self.x
            dy = player.y - self.y
            return math.degrees(math.atan2(dy, dx))
        return -90
    
    # ==================== 移动 API ====================
    
    @types.coroutine
    def move_to(self, x: float, y: float, duration: int = 60):
        """平滑移动到指定位置"""
        start_x, start_y = self.x, self.y
        for i in range(duration):
            t = (i + 1) / duration
            t = t * t * (3 - 2 * t)  # smoothstep
            self.x = start_x + (x - start_x) * t
            self.y = start_y + (y - start_y) * t
            yield
    
    @types.coroutine
    def move_linear(self, dx: float, dy: float, duration: int = 60):
        """匀速直线移动"""
        start_x, start_y = self.x, self.y
        for i in range(duration):
            t = (i + 1) / duration
            self.x = start_x + dx * t
            self.y = start_y + dy * t
            yield
    
    def set_position(self, x: float, y: float):
        """瞬移到指定位置"""
        self.x = x
        self.y = y
    
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

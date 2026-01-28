"""
掉落物系统 - 参考 LuaSTG THlib item 系统

物品类型:
- POWER: 小P点 (+1 power)
- POWER_LARGE: 大P点 (+100 power, 即 +1.00)
- POWER_FULL: 满P (+400)
- POINT: 得点 (分数根据收点倍率)
- FAITH: 信仰点 (+10000 固定)
- LIFE_CHIP: 残机碎片 (5个=1残)
- BOMB_CHIP: 炸弹碎片 (5个=1炸)
- EXTEND: 1UP
- BOMB: 炸弹

物品行为:
1. 生成时向上弹出，带随机角度
2. 逐渐减速后开始下落
3. 玩家靠近时吸附
4. 超过收点线时自动吸附
5. 与玩家碰撞时收集

坐标系: 归一化坐标 [-1, 1]
"""

import numpy as np
import math
import random
from numba import njit
from enum import IntEnum
from dataclasses import dataclass, field
from typing import List, Callable, Optional


class ItemType(IntEnum):
    """物品类型枚举"""
    POWER = 1        # 小P点
    POINT = 2        # 得点
    LIFE_CHIP = 3    # 残机碎片
    POWER_FULL = 4   # 满P
    FAITH = 5        # 信仰点
    POWER_LARGE = 6  # 大P点
    EXTEND = 7       # 1UP
    FAITH_MINOR = 8  # 小信仰点
    BOMB_CHIP = 9    # 炸弹碎片
    BOMB = 10        # 炸弹


# 物品在纹理中的索引 (item.png 是 64x160, 每个32x32, 2列5行共10种)
ITEM_TEXTURE_INDEX = {
    ItemType.POWER: 0,
    ItemType.POINT: 1,
    ItemType.LIFE_CHIP: 2,
    ItemType.POWER_FULL: 3,
    ItemType.FAITH: 4,
    ItemType.POWER_LARGE: 5,
    ItemType.EXTEND: 6,
    ItemType.FAITH_MINOR: 7,
    ItemType.BOMB_CHIP: 8,
    ItemType.BOMB: 9,
}


@dataclass
class ItemConfig:
    """物品系统配置"""
    # 收点线位置（归一化Y坐标，超过此线自动吸附）
    collect_line_y: float = 0.4
    # 吸附半径（玩家多近时开始吸附）
    attract_radius: float = 0.15
    # 吸附速度
    attract_speed: float = 0.025
    # 最大吸附速度
    max_attract_speed: float = 0.04
    # 下落速度
    fall_speed: float = 0.008
    # 最大下落速度
    max_fall_speed: float = 0.02
    # 初始弹出速度
    pop_speed: float = 0.02
    # 收集半径
    collect_radius: float = 0.03
    # 物品消失边界（Y坐标低于此值消失）
    despawn_y: float = -1.1
    # 残机碎片数量（收集满后+1残）
    life_chip_max: int = 5
    # 炸弹碎片数量
    bomb_chip_max: int = 5


@dataclass
class GameStats:
    """游戏统计数据（与 HUD 同步）"""
    score: int = 0
    hiscore: int = 0
    power: int = 100  # 100 = 1.00 power
    max_power: int = 400
    lives: int = 3
    bombs: int = 3
    graze: int = 0
    life_chips: int = 0
    bomb_chips: int = 0
    faith: int = 0
    point_rate: int = 10000  # 得点倍率
    
    # 收集统计
    items_collected: int = 0
    
    def get_power_float(self) -> float:
        """获取浮点格式的 Power (0.00 ~ 4.00)"""
        return self.power / 100.0
    
    def add_power(self, amount: int) -> int:
        """增加 Power，返回实际增加量（满后溢出转分数）"""
        if self.power >= self.max_power:
            # 满 Power 后转分数
            self.score += amount * 100
            return 0
        old = self.power
        self.power = min(self.max_power, self.power + amount)
        return self.power - old
    
    def update_point_rate(self):
        """更新得点倍率（基于 graze 和 faith）"""
        self.point_rate = 10000 + (self.graze // 10) * 10 + (self.faith // 10) * 10


class Item:
    """单个掉落物"""
    
    __slots__ = ['x', 'y', 'vx', 'vy', 'item_type', 'timer', 'alive', 
                 'attracting', 'collected', 'sprite_index']
    
    def __init__(self, x: float, y: float, item_type: ItemType, 
                 vx: float = 0, vy: float = 0):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.item_type = item_type
        self.timer = 0
        self.alive = True
        self.attracting = False
        self.collected = False
        self.sprite_index = ITEM_TEXTURE_INDEX.get(item_type, 0)


@njit(cache=True)
def _update_items_numba(
    x, y, vx, vy, timer, alive, attracting,
    player_x, player_y, dt_scale,
    collect_line_y, attract_radius,
    attract_speed, max_attract_speed,
    max_fall_speed, collect_radius,
    despawn_y
):
    collected = np.zeros(x.shape[0], dtype=np.uint8)
    for i in range(x.shape[0]):
        if alive[i] == 0:
            continue

        timer[i] += 1

        if timer[i] < 24:
            vy[i] -= 0.001 * dt_scale
        else:
            dx = player_x - x[i]
            dy = player_y - y[i]
            dist = math.sqrt(dx * dx + dy * dy)

            above_collect_line = player_y > collect_line_y
            in_attract_range = dist < attract_radius

            if above_collect_line or in_attract_range or attracting[i] == 1:
                attracting[i] = 1
                if dist > 0.001:
                    attract_v = attract_speed + timer[i] * 0.0002
                    if attract_v > max_attract_speed:
                        attract_v = max_attract_speed
                    vx[i] = (dx / dist) * attract_v
                    vy[i] = (dy / dist) * attract_v
            else:
                vx[i] *= 0.98
                fall_v = vy[i] - 0.0005 * dt_scale
                if fall_v < -max_fall_speed:
                    fall_v = -max_fall_speed
                vy[i] = fall_v

        x[i] += vx[i] * dt_scale
        y[i] += vy[i] * dt_scale

        dx = player_x - x[i]
        dy = player_y - y[i]
        if dx * dx + dy * dy < collect_radius * collect_radius:
            collected[i] = 1
            alive[i] = 0
            continue

        if y[i] < despawn_y:
            alive[i] = 0

    return collected


class ItemPool:
    """物品池 - 管理所有掉落物"""
    
    def __init__(self, max_items: int = 1000, config: ItemConfig = None, use_numba: bool = True):
        self.max_items = max_items
        self.config = config or ItemConfig()
        self.items: List[Item] = []
        self.stats = GameStats()
        self.use_numba = use_numba
        
        # 回调函数
        self.on_collect: Optional[Callable[[Item, GameStats], None]] = None
        self.on_power_up: Optional[Callable[[int, int], None]] = None  # old, new
        self.on_extend: Optional[Callable[[], None]] = None
        self.on_bomb_get: Optional[Callable[[], None]] = None
    
    def spawn(self, x: float, y: float, item_type: ItemType, 
              speed: float = None, angle: float = None) -> Optional[Item]:
        """
        生成一个掉落物
        
        Args:
            x, y: 生成位置（归一化坐标）
            item_type: 物品类型
            speed: 初始速度（默认使用配置）
            angle: 初始角度（度，90=向上，默认随机）
        
        Returns:
            Item 或 None（如果池已满）
        """
        if len(self.items) >= self.max_items:
            return None
        
        # 限制 X 在屏幕范围内
        x = max(-0.95, min(0.95, x))
        
        # 初始速度
        speed = speed if speed is not None else self.config.pop_speed
        angle_rad = math.radians(angle if angle is not None else random.uniform(70, 110))
        vx = speed * math.cos(angle_rad)
        vy = speed * math.sin(angle_rad)
        
        item = Item(x, y, item_type, vx, vy)
        self.items.append(item)
        return item
    
    def spawn_drop(self, x: float, y: float, 
                   power: int = 0, point: int = 0, faith: int = 0):
        """
        批量生成掉落物（敌人/Boss掉落）
        
        Args:
            x, y: 中心位置
            power: Power点数（1=小P, 100=大P, 400=满P）
            point: 得点数量
            faith: 信仰点数量
        """
        total = 0
        
        # 计算掉落数量
        if power >= 400:
            # 满P
            self._spawn_scattered(x, y, ItemType.POWER_FULL, 1)
            total += 1
        else:
            # 大P点
            large_count = power // 100
            if large_count > 0:
                self._spawn_scattered(x, y, ItemType.POWER_LARGE, large_count)
                total += large_count
            # 小P点
            small_count = power % 100
            if small_count > 0:
                self._spawn_scattered(x, y, ItemType.POWER, small_count)
                total += small_count
        
        # 得点
        if point > 0:
            self._spawn_scattered(x, y, ItemType.POINT, point)
            total += point
        
        # 信仰
        if faith > 0:
            self._spawn_scattered(x, y, ItemType.FAITH, faith)
            total += faith
    
    def _spawn_scattered(self, cx: float, cy: float, item_type: ItemType, count: int):
        """在指定位置散布生成物品"""
        if count <= 0:
            return
        
        # 散布半径随数量增加
        radius = math.sqrt(count) * 0.02
        
        for _ in range(count):
            # 随机偏移
            r = random.uniform(0, radius) * math.sqrt(random.random())
            a = random.uniform(0, 2 * math.pi)
            ox = r * math.cos(a)
            oy = r * math.sin(a)
            
            # 随机角度（向上偏）
            angle = random.uniform(60, 120)
            self.spawn(cx + ox, cy + oy, item_type, angle=angle)
    
    def update(self, player_x: float, player_y: float, dt: float = 1/60):
        """
        更新所有物品
        
        Args:
            player_x, player_y: 玩家位置（归一化坐标）
            dt: 时间步长
        """
        cfg = self.config
        dt_scale = dt * 60  # 归一化到60FPS
        
        if self.use_numba and self.items:
            n = len(self.items)
            x = np.empty(n, dtype=np.float32)
            y = np.empty(n, dtype=np.float32)
            vx = np.empty(n, dtype=np.float32)
            vy = np.empty(n, dtype=np.float32)
            timer = np.empty(n, dtype=np.int32)
            alive = np.empty(n, dtype=np.uint8)
            attracting = np.empty(n, dtype=np.uint8)

            for i, item in enumerate(self.items):
                x[i] = item.x
                y[i] = item.y
                vx[i] = item.vx
                vy[i] = item.vy
                timer[i] = item.timer
                alive[i] = 1 if item.alive else 0
                attracting[i] = 1 if item.attracting else 0

            collected = _update_items_numba(
                x, y, vx, vy, timer, alive, attracting,
                player_x, player_y, dt_scale,
                cfg.collect_line_y, cfg.attract_radius,
                cfg.attract_speed, cfg.max_attract_speed,
                cfg.max_fall_speed, cfg.collect_radius,
                cfg.despawn_y
            )

            items_to_remove = []
            for i, item in enumerate(self.items):
                item.x = float(x[i])
                item.y = float(y[i])
                item.vx = float(vx[i])
                item.vy = float(vy[i])
                item.timer = int(timer[i])
                item.alive = bool(alive[i])
                item.attracting = bool(attracting[i])

                if collected[i] == 1:
                    self._collect_item(item)
                    items_to_remove.append(item)
                elif not item.alive:
                    items_to_remove.append(item)

            for item in items_to_remove:
                if item in self.items:
                    self.items.remove(item)
            return

        items_to_remove = []
        
        for item in self.items:
            if not item.alive:
                items_to_remove.append(item)
                continue
            
            item.timer += 1
            
            # 物理更新
            if item.timer < 24:
                # 弹出阶段：逐渐减速
                item.vy -= 0.001 * dt_scale
            else:
                # 检查吸附条件
                dx = player_x - item.x
                dy = player_y - item.y
                dist = math.sqrt(dx * dx + dy * dy)
                
                # 是否在收点线上方
                above_collect_line = player_y > cfg.collect_line_y
                
                # 是否在吸附范围内
                in_attract_range = dist < cfg.attract_radius
                
                if above_collect_line or in_attract_range or item.attracting:
                    # 开始/继续吸附
                    item.attracting = True
                    if dist > 0.001:
                        attract_speed = min(cfg.attract_speed + item.timer * 0.0002, 
                                          cfg.max_attract_speed)
                        item.vx = (dx / dist) * attract_speed
                        item.vy = (dy / dist) * attract_speed
                else:
                    # 正常下落
                    item.vx *= 0.98  # 水平阻尼
                    item.vy = max(item.vy - 0.0005 * dt_scale, -cfg.max_fall_speed)
            
            # 移动
            item.x += item.vx * dt_scale
            item.y += item.vy * dt_scale
            
            # 收集检测
            dx = player_x - item.x
            dy = player_y - item.y
            if dx * dx + dy * dy < cfg.collect_radius * cfg.collect_radius:
                self._collect_item(item)
                items_to_remove.append(item)
                continue
            
            # 边界检测
            if item.y < cfg.despawn_y:
                item.alive = False
                items_to_remove.append(item)
        
        # 移除已收集/消失的物品
        for item in items_to_remove:
            if item in self.items:
                self.items.remove(item)
    
    def _collect_item(self, item: Item):
        """收集物品并应用效果"""
        item.collected = True
        item.alive = False
        self.stats.items_collected += 1
        
        t = item.item_type
        stats = self.stats
        
        if t == ItemType.POWER:
            old_power = stats.power
            stats.add_power(1)
            if stats.power // 100 > old_power // 100 and self.on_power_up:
                self.on_power_up(old_power, stats.power)
        
        elif t == ItemType.POWER_LARGE:
            old_power = stats.power
            stats.add_power(100)
            if stats.power // 100 > old_power // 100 and self.on_power_up:
                self.on_power_up(old_power, stats.power)
        
        elif t == ItemType.POWER_FULL:
            stats.add_power(400)
        
        elif t == ItemType.POINT:
            # 得点：收点线上方给满倍率，否则减半
            if item.attracting and item.y > self.config.collect_line_y * 0.5:
                stats.score += stats.point_rate
            else:
                stats.score += stats.point_rate // 2
        
        elif t == ItemType.FAITH:
            stats.faith += 100
            stats.score += 10000
        
        elif t == ItemType.FAITH_MINOR:
            stats.faith += 4
            stats.score += 500
        
        elif t == ItemType.LIFE_CHIP:
            stats.life_chips += 1
            if stats.life_chips >= self.config.life_chip_max:
                stats.life_chips = 0
                stats.lives += 1
                if self.on_extend:
                    self.on_extend()
        
        elif t == ItemType.BOMB_CHIP:
            stats.bomb_chips += 1
            if stats.bomb_chips >= self.config.bomb_chip_max:
                stats.bomb_chips = 0
                stats.bombs += 1
                if self.on_bomb_get:
                    self.on_bomb_get()
        
        elif t == ItemType.EXTEND:
            stats.lives += 1
            if self.on_extend:
                self.on_extend()
        
        elif t == ItemType.BOMB:
            stats.bombs += 1
            if self.on_bomb_get:
                self.on_bomb_get()
        
        # 更新得点倍率
        stats.update_point_rate()
        
        # 更新最高分
        if stats.score > stats.hiscore:
            stats.hiscore = stats.score
        
        # 回调
        if self.on_collect:
            self.on_collect(item, stats)
    
    def collect_all(self, player_x: float, player_y: float):
        """收集所有物品（清屏/Boss击破时）"""
        for item in self.items:
            if item.alive:
                item.attracting = True
    
    def get_active_items(self) -> List[Item]:
        """获取所有活动物品"""
        return [item for item in self.items if item.alive]
    
    def clear(self):
        """清空所有物品"""
        self.items.clear()
    
    @property
    def item_count(self) -> int:
        return len(self.items)


def create_item_sprite_config() -> dict:
    """
    生成物品精灵配置（用于 SpriteManager）
    
    item.png 是 64x160，每个物品 32x32，2列10行
    """
    sprites = {}
    item_names = [
        'item_power', 'item_point', 'item_life_chip', 'item_power_full',
        'item_faith', 'item_power_large', 'item_extend', 'item_faith_minor',
        'item_bomb_chip', 'item_bomb'
    ]
    
    for i, name in enumerate(item_names):
        col = i % 2
        row = i // 2
        sprites[name] = {
            'rect': [col * 32, row * 32, 32, 32],
            'center': [16, 16]
        }
    
    return {
        'texture': 'assets/images/item/item.png',
        'sprites': sprites
    }

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


# 物品在纹理中的索引 (item.png 2列5行共10种, 每个32x32)
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
    collect_line_y: float = 0.4
    attract_radius: float = 0.15
    attract_speed: float = 0.025
    max_attract_speed: float = 0.04
    fall_speed: float = 0.008
    max_fall_speed: float = 0.02
    pop_speed: float = 0.02
    collect_radius: float = 0.03
    despawn_y: float = -1.1
    life_chip_max: int = 5
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
    point_rate: int = 10000

    items_collected: int = 0

    def get_power_float(self) -> float:
        return self.power / 100.0

    def add_power(self, amount: int) -> int:
        if self.power >= self.max_power:
            self.score += amount * 100
            return 0
        old = self.power
        self.power = min(self.max_power, self.power + amount)
        return self.power - old

    def update_point_rate(self):
        self.point_rate = 10000 + (self.graze // 10) * 10 + (self.faith // 10) * 10


class Item:
    """单个掉落物 (lightweight view into SoA pool for _collect_item callbacks)"""

    __slots__ = ['x', 'y', 'vx', 'vy', 'item_type', 'timer', 'alive',
                 'attracting', 'collected', 'sprite_index']

    def __init__(self, x: float, y: float, item_type: int,
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
    """物品池 - SoA (Structure of Arrays) 布局，零拷贝 Numba 加速"""

    def __init__(self, max_items: int = 1000, config: ItemConfig = None, use_numba: bool = True):
        self.max_items = max_items
        self.config = config or ItemConfig()
        self.use_numba = use_numba
        self.stats = GameStats()

        # SoA preallocated arrays
        self.x = np.zeros(max_items, dtype=np.float32)
        self.y = np.zeros(max_items, dtype=np.float32)
        self.vx = np.zeros(max_items, dtype=np.float32)
        self.vy = np.zeros(max_items, dtype=np.float32)
        self.timer = np.zeros(max_items, dtype=np.int32)
        self.alive = np.zeros(max_items, dtype=np.uint8)
        self.attracting = np.zeros(max_items, dtype=np.uint8)
        self.item_type = np.zeros(max_items, dtype=np.int32)
        self.sprite_index = np.zeros(max_items, dtype=np.int32)

        self._count = 0  # high-water mark for active region

        # 回调函数
        self.on_collect: Optional[Callable] = None
        self.on_power_up: Optional[Callable[[int, int], None]] = None
        self.on_extend: Optional[Callable[[], None]] = None
        self.on_bomb_get: Optional[Callable[[], None]] = None

        if use_numba:
            self._warmup_numba()

    def _warmup_numba(self):
        """触发 Numba JIT 编译（或加载缓存），避免首次掉落卡顿。"""
        n = 1
        _update_items_numba(
            np.zeros(n, dtype=np.float32), np.zeros(n, dtype=np.float32),
            np.zeros(n, dtype=np.float32), np.zeros(n, dtype=np.float32),
            np.zeros(n, dtype=np.int32), np.zeros(n, dtype=np.uint8),
            np.zeros(n, dtype=np.uint8),
            0.0, 0.0, 1.0,
            0.4, 0.15, 0.025, 0.04, 0.02, 0.03, -1.1
        )

    def _alloc_slot(self) -> int:
        """Find a single free slot. Returns index or -1 if pool is full."""
        if self._count > 0:
            dead = np.where(self.alive[:self._count] == 0)[0]
            if len(dead) > 0:
                return int(dead[0])
        if self._count < self.max_items:
            idx = self._count
            self._count += 1
            return idx
        return -1

    def _alloc_batch(self, count: int) -> np.ndarray:
        """Find multiple free slots at once (vectorized)."""
        slots = []
        if self._count > 0:
            dead = np.where(self.alive[:self._count] == 0)[0]
            reuse = dead[:count]
            slots.append(reuse)
            count -= len(reuse)
        if count > 0:
            available = min(count, self.max_items - self._count)
            if available > 0:
                new_slots = np.arange(self._count, self._count + available)
                slots.append(new_slots)
                self._count += available
        if len(slots) == 0:
            return np.array([], dtype=np.intp)
        return np.concatenate(slots).astype(np.intp)

    def spawn(self, x: float, y: float, item_type: ItemType,
              speed: float = None, angle: float = None) -> Optional[int]:
        """
        生成一个掉落物，返回 slot index 或 None（池满时）。
        """
        idx = self._alloc_slot()
        if idx < 0:
            return None

        x = max(-0.95, min(0.95, x))

        speed = speed if speed is not None else self.config.pop_speed
        angle_rad = math.radians(angle if angle is not None else random.uniform(70, 110))
        vx = speed * math.cos(angle_rad)
        vy = speed * math.sin(angle_rad)

        self.x[idx] = x
        self.y[idx] = y
        self.vx[idx] = vx
        self.vy[idx] = vy
        self.timer[idx] = 0
        self.alive[idx] = 1
        self.attracting[idx] = 0
        self.item_type[idx] = int(item_type)
        self.sprite_index[idx] = ITEM_TEXTURE_INDEX.get(item_type, 0)
        return idx

    def spawn_drop(self, x: float, y: float,
                   power: int = 0, point: int = 0, faith: int = 0):
        """批量生成掉落物（敌人/Boss掉落）"""
        if power >= 400:
            self._spawn_scattered(x, y, ItemType.POWER_FULL, 1)
        else:
            large_count = power // 100
            if large_count > 0:
                self._spawn_scattered(x, y, ItemType.POWER_LARGE, large_count)
            small_count = power % 100
            if small_count > 0:
                self._spawn_scattered(x, y, ItemType.POWER, small_count)

        if point > 0:
            self._spawn_scattered(x, y, ItemType.POINT, point)
        if faith > 0:
            self._spawn_scattered(x, y, ItemType.FAITH, faith)

    def _spawn_scattered(self, cx: float, cy: float, item_type: ItemType, count: int):
        if count <= 0:
            return

        slots = self._alloc_batch(count)
        n = len(slots)
        if n == 0:
            return

        scatter_radius = math.sqrt(count) * 0.02
        r = np.random.uniform(0, scatter_radius, n) * np.sqrt(np.random.random(n))
        a = np.random.uniform(0, 2 * math.pi, n)
        ox = r * np.cos(a)
        oy = r * np.sin(a)

        angles_rad = np.radians(np.random.uniform(60, 120, n))
        speed = self.config.pop_speed

        self.x[slots] = np.clip(cx + ox, -0.95, 0.95).astype(np.float32)
        self.y[slots] = np.float32(cy) + oy.astype(np.float32)
        self.vx[slots] = (speed * np.cos(angles_rad)).astype(np.float32)
        self.vy[slots] = (speed * np.sin(angles_rad)).astype(np.float32)
        self.timer[slots] = 0
        self.alive[slots] = 1
        self.attracting[slots] = 0
        self.item_type[slots] = int(item_type)
        self.sprite_index[slots] = ITEM_TEXTURE_INDEX.get(item_type, 0)

    def update(self, player_x, player_y, dt: float = 1/60):
        """更新所有物品（直接操作 SoA 数组，零拷贝）"""
        if self._count == 0:
            return

        cfg = self.config
        # Normalize scalar types to Python float so Numba always sees the same
        # signature (player.pos elements are numpy.float32 which would trigger
        # recompilation if the warmup used Python float).
        px = float(player_x)
        py = float(player_y)
        dt_scale = float(dt * 60)
        n = self._count

        if self.use_numba:
            collected = _update_items_numba(
                self.x[:n], self.y[:n], self.vx[:n], self.vy[:n],
                self.timer[:n], self.alive[:n], self.attracting[:n],
                px, py, dt_scale,
                cfg.collect_line_y, cfg.attract_radius,
                cfg.attract_speed, cfg.max_attract_speed,
                cfg.max_fall_speed, cfg.collect_radius,
                cfg.despawn_y
            )

            for i in range(n):
                if collected[i] == 1:
                    self._collect_item_at(i)
        else:
            self._update_python(player_x, player_y, dt_scale)

        self._compact()

    def _update_python(self, player_x: float, player_y: float, dt_scale: float):
        """Python fallback update (no Numba)"""
        cfg = self.config
        for i in range(self._count):
            if self.alive[i] == 0:
                continue

            self.timer[i] += 1

            if self.timer[i] < 24:
                self.vy[i] -= 0.001 * dt_scale
            else:
                dx = player_x - self.x[i]
                dy = player_y - self.y[i]
                dist = math.sqrt(dx * dx + dy * dy)

                above_collect_line = player_y > cfg.collect_line_y
                in_attract_range = dist < cfg.attract_radius

                if above_collect_line or in_attract_range or self.attracting[i]:
                    self.attracting[i] = 1
                    if dist > 0.001:
                        attract_speed = min(cfg.attract_speed + self.timer[i] * 0.0002,
                                            cfg.max_attract_speed)
                        self.vx[i] = (dx / dist) * attract_speed
                        self.vy[i] = (dy / dist) * attract_speed
                else:
                    self.vx[i] *= 0.98
                    self.vy[i] = max(self.vy[i] - 0.0005 * dt_scale, -cfg.max_fall_speed)

            self.x[i] += self.vx[i] * dt_scale
            self.y[i] += self.vy[i] * dt_scale

            dx = player_x - self.x[i]
            dy = player_y - self.y[i]
            if dx * dx + dy * dy < cfg.collect_radius * cfg.collect_radius:
                self._collect_item_at(i)
                self.alive[i] = 0
                continue

            if self.y[i] < cfg.despawn_y:
                self.alive[i] = 0

    def _compact(self):
        """Shrink _count by trimming dead slots at the tail."""
        while self._count > 0 and self.alive[self._count - 1] == 0:
            self._count -= 1

    def _collect_item_at(self, idx: int):
        """收集物品并应用效果"""
        self.stats.items_collected += 1
        t = int(self.item_type[idx])
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
            if self.attracting[idx] and self.y[idx] > self.config.collect_line_y * 0.5:
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

        stats.update_point_rate()
        if stats.score > stats.hiscore:
            stats.hiscore = stats.score

        if self.on_collect:
            item = Item(
                float(self.x[idx]), float(self.y[idx]),
                t, float(self.vx[idx]), float(self.vy[idx])
            )
            item.timer = int(self.timer[idx])
            item.attracting = bool(self.attracting[idx])
            item.collected = True
            item.alive = False
            self.on_collect(item, stats)

    def collect_all(self, player_x: float, player_y: float):
        """收集所有物品（清屏/Boss击破时）"""
        for i in range(self._count):
            if self.alive[i]:
                self.attracting[i] = 1

    def get_active_items(self) -> List[Item]:
        """获取所有活动物品（兼容旧接口）"""
        result = []
        for i in range(self._count):
            if self.alive[i]:
                item = Item(
                    float(self.x[i]), float(self.y[i]),
                    int(self.item_type[i]),
                    float(self.vx[i]), float(self.vy[i])
                )
                item.timer = int(self.timer[i])
                item.alive = True
                item.attracting = bool(self.attracting[i])
                item.sprite_index = int(self.sprite_index[i])
                result.append(item)
        return result

    def get_render_data(self):
        """
        Return SoA slices for the renderer (zero-copy).
        Returns (x, y, timer, sprite_index, alive, count).
        """
        n = self._count
        return (self.x[:n], self.y[:n], self.timer[:n],
                self.sprite_index[:n], self.alive[:n], n)

    def clear(self):
        """清空所有物品"""
        self.alive[:self._count] = 0
        self._count = 0

    @property
    def item_count(self) -> int:
        if self._count == 0:
            return 0
        return int(np.sum(self.alive[:self._count]))


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

"""
碰撞管理器 - 统一管理所有碰撞检测

将分散在各处的碰撞检测逻辑集中管理：
- 玩家 vs 敌弹
- 玩家 vs 激光
- 玩家子弹 vs 敌人/Boss
- 玩家 vs 道具（擦弹、收集）

使用 Numba JIT 加速关键路径
"""

import numpy as np
from numba import njit
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import math
from .collision_shapes import shapes_overlap, hitbox_values, BOX

# Both pool formats use bit 2 for non-colliding emitter controllers. Keep
# this numerical kernel independent of the pool module (core imports first).
_FLAG_IS_EMITTER = 1 << 2


@dataclass
class CollisionResult:
    """碰撞结果"""
    occurred: bool = False
    index: int = -1  # 碰撞对象的索引
    position: Tuple[float, float] = (0, 0)
    damage: float = 0.0
    extra_data: Dict[str, Any] = None


@dataclass
class BulletCollisionResult:
    """子弹碰撞结果（批量）"""
    bullet_idx: int
    target_idx: int
    damage: float
    position: Tuple[float, float]
    source: str = 'shot'
    attack_generation: int = -1
    region: int = 0


# ============= Numba JIT 加速函数 =============

@njit(cache=True)
def _check_player_vs_bullets(
    player_x: float,
    player_y: float,
    player_radius: float,
    bullet_pos: np.ndarray,  # shape: (N, 2)
    bullet_radius: np.ndarray,  # shape: (N,)
    bullet_alive: np.ndarray,  # shape: (N,)
    bullet_flags: np.ndarray,
    collision_eligible: np.ndarray,
) -> int:
    """
    检查玩家与子弹的碰撞（Numba加速）

    Returns:
        碰撞的子弹索引，-1表示无碰撞
    """
    n = bullet_pos.shape[0]
    for i in range(n):
        if bullet_alive[i] == 0 or not collision_eligible[i] or bullet_flags[i] & _FLAG_IS_EMITTER:
            continue

        dx = bullet_pos[i, 0] - player_x
        dy = bullet_pos[i, 1] - player_y
        dist_sq = dx * dx + dy * dy

        combined_r = player_radius + bullet_radius[i]
        if dist_sq < combined_r * combined_r:
            return i

    return -1


@njit(cache=True)
def _check_player_vs_shapes(px, py, kind, radius, hx, hy, angle, data, eligible):
    for i in range(len(data)):
        b = data[i]
        if not b['alive'] or not eligible[i] or b['flags'] & _FLAG_IS_EMITTER:
            continue
        if shapes_overlap(px, py, kind, radius, hx, hy, angle,
                          b['pos'][0], b['pos'][1], b['collision_shape'], b['radius'],
                          b['hitbox_size'][0]*.5, b['hitbox_size'][1]*.5, b['hitbox_angle']):
            return i
    return -1


@njit(cache=True)
def _graze_shapes(px, py, graze_radius, data, eligible, grazed):
    count = 0
    for i in range(len(data)):
        b = data[i]
        if not b['alive'] or not eligible[i] or grazed[i] or b['flags'] & _FLAG_IS_EMITTER:
            continue
        # Preserve legacy circular graze (center-distance only). Boxes use
        # their actual region, otherwise long thin bullets cannot be grazed.
        if b['collision_shape'] == BOX:
            hit = shapes_overlap(px, py, 0, graze_radius, 0., 0., 0.,
                                 b['pos'][0], b['pos'][1], BOX, 0.,
                                 b['hitbox_size'][0]*.5, b['hitbox_size'][1]*.5, b['hitbox_angle'])
        else:
            hit = (b['pos'][0]-px)**2+(b['pos'][1]-py)**2 < graze_radius**2
        if hit:
            grazed[i] = 1
            count += 1
    return count


@njit(cache=True)
def _check_player_vs_bullets_graze(
    player_x: float,
    player_y: float,
    graze_radius: float,
    bullet_pos: np.ndarray,
    bullet_alive: np.ndarray,
    bullet_grazed: np.ndarray,  # 已擦弹标记
    bullet_flags: np.ndarray,
    collision_eligible: np.ndarray,
) -> int:
    """
    检查擦弹（Numba加速）

    Returns:
        擦弹数量
    """
    n = bullet_pos.shape[0]
    graze_count = 0

    for i in range(n):
        if bullet_alive[i] == 0 or not collision_eligible[i] or bullet_grazed[i] == 1 or bullet_flags[i] & _FLAG_IS_EMITTER:
            continue

        dx = bullet_pos[i, 0] - player_x
        dy = bullet_pos[i, 1] - player_y
        dist_sq = dx * dx + dy * dy

        if dist_sq < graze_radius * graze_radius:
            bullet_grazed[i] = 1
            graze_count += 1

    return graze_count


@njit(cache=True)
def _check_player_bullets_vs_enemies(
    bullet_pos: np.ndarray,      # shape: (N, 2)
    bullet_alive: np.ndarray,    # shape: (N,)
    bullet_damage: np.ndarray,   # shape: (N,)
    bullet_penetrate: np.ndarray,  # shape: (N,)
    enemy_pos: np.ndarray,       # shape: (M, 2)
    enemy_alive: np.ndarray,     # shape: (M,)
    enemy_radius: np.ndarray,    # shape: (M,)
    hit_radius: float = 0.05,
) -> np.ndarray:
    """
    检查玩家子弹与敌人的碰撞（Numba加速）

    Returns:
        碰撞结果数组，shape: (K, 4) - [bullet_idx, enemy_idx, damage, penetrate_remaining]
    """
    # 预分配结果数组（最多处理1000次碰撞）
    max_collisions = 1000
    results = np.zeros((max_collisions, 4), dtype=np.float32)
    collision_count = 0

    n_bullets = bullet_pos.shape[0]
    n_enemies = enemy_pos.shape[0]

    for b_idx in range(n_bullets):
        if bullet_alive[b_idx] == 0:
            continue

        bx, by = bullet_pos[b_idx, 0], bullet_pos[b_idx, 1]

        for e_idx in range(n_enemies):
            if enemy_alive[e_idx] == 0:
                continue

            ex, ey = enemy_pos[e_idx, 0], enemy_pos[e_idx, 1]

            dx = bx - ex
            dy = by - ey
            dist_sq = dx * dx + dy * dy

            combined_r = hit_radius + enemy_radius[e_idx]
            if dist_sq < combined_r * combined_r:
                if collision_count < max_collisions:
                    results[collision_count, 0] = b_idx
                    results[collision_count, 1] = e_idx
                    results[collision_count, 2] = bullet_damage[b_idx]
                    results[collision_count, 3] = bullet_penetrate[b_idx]
                    collision_count += 1

                # 处理穿透逻辑
                if bullet_penetrate[b_idx] <= 0:
                    bullet_alive[b_idx] = 0
                    break
                else:
                    bullet_penetrate[b_idx] -= 1

    return results[:collision_count]


@njit(cache=True)
def _check_laser_collision(
    player_x: float,
    player_y: float,
    player_radius: float,
    laser_x: float,
    laser_y: float,
    laser_angle: float,
    l1: float, l2: float, l3: float,
    laser_width: float,
) -> bool:
    """
    检查直线激光碰撞（三段式）
    """
    cos_a = math.cos(laser_angle)
    sin_a = math.sin(laser_angle)

    dx = player_x - laser_x
    dy = player_y - laser_y

    # 旋转到激光局部坐标系
    local_x = dx * cos_a + dy * sin_a
    local_y = -dx * sin_a + dy * cos_a
    local_y = abs(local_y)

    if local_x < 0:
        return False

    half_width = laser_width * 0.5 + player_radius
    total_length = l1 + l2 + l3

    if local_x > total_length:
        return False

    # 头部（锥形）
    if local_x < l1:
        if l1 > 0:
            segment_width = (local_x / l1) * half_width
        else:
            segment_width = half_width
        return local_y < segment_width

    # 身体（矩形）
    if local_x < l1 + l2:
        return local_y < half_width

    # 尾部（锥形）
    remaining = total_length - local_x
    if l3 > 0:
        segment_width = (remaining / l3) * half_width
    else:
        segment_width = half_width
    return local_y < segment_width


@njit(cache=True)
def _check_bent_laser_collision(
    player_x: float,
    player_y: float,
    player_radius: float,
    path_x: np.ndarray,
    path_y: np.ndarray,
    laser_width: float,
    path_len: int,
) -> bool:
    """
    检查曲线激光碰撞
    """
    collision_dist_sq = (laser_width * 0.5 + player_radius) ** 2

    for i in range(path_len - 1):
        x1, y1 = path_x[i], path_y[i]
        x2, y2 = path_x[i + 1], path_y[i + 1]

        dx = x2 - x1
        dy = y2 - y1
        length_sq = dx * dx + dy * dy

        if length_sq < 1e-6:
            dist_sq = (player_x - x1) ** 2 + (player_y - y1) ** 2
        else:
            t = max(0.0, min(1.0, ((player_x - x1) * dx + (player_y - y1) * dy) / length_sq))
            nearest_x = x1 + t * dx
            nearest_y = y1 + t * dy
            dist_sq = (player_x - nearest_x) ** 2 + (player_y - nearest_y) ** 2

        if dist_sq < collision_dist_sq:
            return True

    return False


# ============= 碰撞管理器类 =============

class CollisionManager:
    """
    统一碰撞管理器

    使用方式:
        collision_mgr = CollisionManager()

        # 检查玩家碰撞
        result = collision_mgr.check_player_vs_bullets(player, bullet_pool)
        if result.occurred:
            player.take_damage()

        # 检查玩家子弹碰撞
        hits = collision_mgr.check_player_bullets_vs_enemies(
            player.bullet_pool, enemies
        )
    """

    def __init__(self):
        """初始化碰撞管理器"""
        # 擦弹标记数组（需要与子弹池同步）
        self._graze_flags: Optional[np.ndarray] = None
        self._graze_flags_size = 0
        self._graze_generations = None
        self._graze_pool = None

    def warmup(self, bullet_pool):
        from time import perf_counter
        from .collision_shapes import capsule_box, polygon_box_overlap
        start = perf_counter()
        data = bullet_pool.data[:0]
        eligible = np.empty(0, np.bool_)
        _check_player_vs_shapes(0., 0., 0, .01, 0., 0., 0., data, eligible)
        _graze_shapes(0., 0., .05, data, eligible, np.empty(0, np.int32))
        shapes_overlap(0., 0., 0, .01, 0., 0., 0., 1., 1., 1, 0., .1, .1, 0.)
        capsule_box(0., 0., 1., 1., .01, 0., 0., .02, .02, 0.)
        polygon_box_overlap(np.zeros((3, 2), np.float64), 0., 0., .02, .02, 0.)
        return {'geometry_ms': (perf_counter()-start)*1000}

    def _ensure_graze_array(self, size: int):
        """确保擦弹标记数组大小足够"""
        if self._graze_flags is None or self._graze_flags_size < size:
            self._graze_flags = np.zeros(size, dtype=np.int32)
            self._graze_generations = np.zeros(size, dtype=np.uint64)
            self._graze_flags_size = size

    def reset_graze_flags(self):
        """重置擦弹标记（新的一帧开始时调用）"""
        if self._graze_flags is not None:
            self._graze_flags.fill(0)

    def check_player_vs_bullets(
        self,
        player_x: float,
        player_y: float,
        player_radius: float,
        bullet_pool,
        *, player_hitbox=None,
    ) -> CollisionResult:
        """
        检查玩家与敌弹碰撞

        Args:
            player_x, player_y: 玩家位置
            player_radius: 玩家判定半径
            bullet_pool: 子弹池对象（BulletPool）

        Returns:
            CollisionResult
        """
        data = bullet_pool.data

        # 提取需要的数组
        positions = data['pos']
        alive = data['alive']
        radius = data['radius']

        # 调用JIT函数
        if 'collision_shape' in data.dtype.names:
            kind, pr, half, angle = hitbox_values(player_hitbox, player_radius)
            hit_idx = _check_player_vs_shapes(
                float(player_x), float(player_y), kind, pr, half[0], half[1], angle, data,
                getattr(bullet_pool, 'collision_eligible', alive))
        else:
            hit_idx = _check_player_vs_bullets(
                player_x, player_y, player_radius,
                positions, radius, alive, data['flags'], getattr(bullet_pool, 'collision_eligible', alive))

        if hit_idx >= 0:
            return CollisionResult(
                occurred=True,
                index=hit_idx,
                position=(positions[hit_idx, 0], positions[hit_idx, 1]),
            )

        return CollisionResult(occurred=False)

    def check_player_graze(
        self,
        player_x: float,
        player_y: float,
        graze_radius: float,
        bullet_pool,
    ) -> int:
        """
        检查擦弹

        Args:
            player_x, player_y: 玩家位置
            graze_radius: 擦弹判定半径
            bullet_pool: 子弹池对象

        Returns:
            本帧擦弹数量
        """
        data = bullet_pool.data
        n = len(data)

        # 确保擦弹标记数组存在
        self._ensure_graze_array(n)

        # 清除已死亡子弹的擦弹标记（处理槽位复用：新子弹不会继承旧子弹的擦弹状态）
        if self._graze_pool is not bullet_pool:
            self.reset_graze_flags()
            self._graze_pool = bullet_pool
        generations = getattr(bullet_pool, 'generations', None)
        if generations is not None:
            self._graze_flags[:n][self._graze_generations[:n] != generations] = 0
            np.copyto(self._graze_generations[:n], generations)
        np.multiply(self._graze_flags[:n], data['alive'], out=self._graze_flags[:n])

        if 'collision_shape' in data.dtype.names:
            return _graze_shapes(float(player_x), float(player_y), float(graze_radius), data,
                                 getattr(bullet_pool, 'collision_eligible', data['alive']), self._graze_flags)
        graze_count = _check_player_vs_bullets_graze(
            player_x, player_y, graze_radius,
            data['pos'], data['alive'], self._graze_flags, data['flags'],
            getattr(bullet_pool, 'collision_eligible', data['alive'])
        )

        return graze_count

    def check_player_bullets_vs_enemies(
        self,
        bullet_pool,
        enemy_manager,
        hit_radius: float = 0.05,
    ) -> List[BulletCollisionResult]:
        """
        检查玩家子弹与敌人碰撞

        Args:
            bullet_pool: 玩家子弹池
            enemy_manager: 敌人管理器
            hit_radius: 基础命中半径

        Returns:
            碰撞结果列表
        """
        if enemy_manager is None:
            return []

        # 获取活跃敌人数据
        enemies = enemy_manager.get_active_enemies()
        if not enemies:
            return []
        if hasattr(bullet_pool, 'collide_targets'):
            return self.check_player_bullets_vs_targets(bullet_pool, enemies, hit_radius)[0]

        # 构建敌人数组
        n_enemies = len(enemies)
        enemy_pos = np.zeros((n_enemies, 2), dtype=np.float32)
        enemy_alive = np.ones(n_enemies, dtype=np.int32)
        enemy_radius = np.zeros(n_enemies, dtype=np.float32)

        for i, enemy in enumerate(enemies):
            enemy_pos[i, 0] = enemy.pos[0]
            enemy_pos[i, 1] = enemy.pos[1]
            enemy_radius[i] = getattr(enemy, 'hit_radius', 0.05)

        # 获取子弹数据
        bullet_data = bullet_pool.data

        # 调用JIT函数
        raw_results = _check_player_bullets_vs_enemies(
            bullet_data['pos'],
            bullet_data['alive'],
            bullet_data['damage'],
            bullet_data['penetrate'],
            enemy_pos,
            enemy_alive,
            enemy_radius,
            hit_radius,
        )

        # 转换结果
        results = []
        for row in raw_results:
            results.append(BulletCollisionResult(
                bullet_idx=int(row[0]),
                target_idx=int(row[1]),
                damage=row[2],
                position=(
                    bullet_data['pos'][int(row[0]), 0],
                    bullet_data['pos'][int(row[0]), 1]
                ),
            ))

        return results

    def check_player_bullets_vs_targets(
        self,
        bullet_pool,
        targets: list,
        hit_radius: float = 0.05,
    ) -> 'tuple[list[BulletCollisionResult], list]':
        """
        检查玩家子弹与目标列表碰撞（无需 adapter/wrapper）

        targets 中的元素需提供 x, y 属性和 hitbox_radius 或 hit_radius 属性。

        Returns:
            (碰撞结果列表, 活跃目标列表)
        """
        active = [t for t in targets
                  if getattr(t, '_active', getattr(t, 'alive', True))
                  and getattr(t, 'collidable', True)
                  and getattr(t, 'interactable', True)]
        if hasattr(bullet_pool, 'collide_targets'):
            return bullet_pool.collide_targets(active, tracked_targets=targets, hit_radius=hit_radius), active
        if not active:
            return [], active

        n = len(active)
        enemy_pos = np.zeros((n, 2), dtype=np.float32)
        enemy_alive = np.ones(n, dtype=np.int32)
        enemy_radius = np.zeros(n, dtype=np.float32)

        for i, t in enumerate(active):
            enemy_pos[i, 0] = getattr(t, 'x', 0.0)
            enemy_pos[i, 1] = getattr(t, 'y', 0.0)
            enemy_radius[i] = getattr(
                t, 'hitbox_radius', getattr(t, 'hit_radius', 0.05))

        bullet_data = bullet_pool.data
        raw_results = _check_player_bullets_vs_enemies(
            bullet_data['pos'],
            bullet_data['alive'],
            bullet_data['damage'],
            bullet_data['penetrate'],
            enemy_pos,
            enemy_alive,
            enemy_radius,
            hit_radius,
        )

        results = []
        for row in raw_results:
            results.append(BulletCollisionResult(
                bullet_idx=int(row[0]),
                target_idx=int(row[1]),
                damage=row[2],
                position=(
                    bullet_data['pos'][int(row[0]), 0],
                    bullet_data['pos'][int(row[0]), 1]
                ),
            ))

        return results, active

    def check_player_vs_contacts(self, player, targets):
        """Opt-in actor-body/trail contact. Uses the same hit decision chain."""
        px, py = player.get_hit_position()
        pk, pr, ph, pa = hitbox_values(getattr(player, 'hitbox', None), player.hit_radius)
        for i, target in enumerate(targets):
            if (not getattr(target, '_active', getattr(target, 'alive', True))
                    or not getattr(target, 'contact_enabled', False)
                    or not getattr(target, 'interactable', True)):
                continue
            tk, tr, th, ta = hitbox_values(getattr(target, 'contact_hitbox', None),
                                          getattr(target, 'hitbox_radius', getattr(target, 'hit_radius', .05)))
            pos = getattr(target, 'pos', None)
            x, y = pos if pos is not None else (target.x, target.y)
            for dx, dy in getattr(target, 'contact_offsets', ((0.0, 0.0),)):
                if shapes_overlap(px, py, pk, pr, ph[0], ph[1], pa,
                                  x+dx, y+dy, tk, tr, th[0], th[1], ta):
                    return CollisionResult(True, i, (x+dx, y+dy))
        return CollisionResult()

    def check_player_vs_lasers(
        self,
        player_x: float,
        player_y: float,
        player_radius: float,
        laser_pool,
        *, player_hitbox=None,
    ) -> CollisionResult:
        """
        检查玩家与激光碰撞

        Args:
            player_x, player_y: 玩家位置
            player_radius: 玩家判定半径
            laser_pool: 激光池对象

        Returns:
            CollisionResult
        """
        if laser_pool is None:
            return CollisionResult(occurred=False)

        lasers, bent_lasers = laser_pool.get_all_lasers()
        kind, radius, half, angle = hitbox_values(player_hitbox, player_radius)

        # 检查直线激光
        for i, laser in enumerate(lasers):
            if not getattr(laser, 'alive', False):
                continue

            if (laser.check_box_collision(player_x, player_y, half, angle) if kind == BOX
                    else laser.check_collision(player_x, player_y, radius)):
                return CollisionResult(
                    occurred=True,
                    index=i,
                    position=(laser.x, laser.y),
                )

        # 检查曲线激光
        for i, bent_laser in enumerate(bent_lasers):
            if not getattr(bent_laser, 'alive', False):
                continue

            if (bent_laser.check_box_collision(player_x, player_y, half, angle) if kind == BOX
                    else bent_laser.check_collision(player_x, player_y, radius)):
                return CollisionResult(
                    occurred=True,
                    index=len(lasers) + i,  # 曲线激光索引偏移
                    position=(bent_laser.head_x, bent_laser.head_y),
                )

        return CollisionResult(occurred=False)

    def check_player_vs_items(
        self,
        player_x: float,
        player_y: float,
        collect_radius: float,
        item_pool,
    ) -> List[int]:
        """
        检查玩家与道具碰撞

        Args:
            player_x, player_y: 玩家位置
            collect_radius: 收集半径
            item_pool: 道具池

        Returns:
            被收集的道具索引列表
        """
        if item_pool is None:
            return []

        collected = []
        items = item_pool.get_active_items()

        collect_r_sq = collect_radius * collect_radius

        for i, item in enumerate(items):
            if not item.alive:
                continue

            dx = item.pos[0] - player_x
            dy = item.pos[1] - player_y
            dist_sq = dx * dx + dy * dy

            if dist_sq < collect_r_sq:
                collected.append(i)

        return collected


# ============= 全局碰撞管理器实例 =============

_collision_manager: Optional[CollisionManager] = None


def get_collision_manager() -> CollisionManager:
    """获取全局碰撞管理器实例"""
    global _collision_manager
    if _collision_manager is None:
        _collision_manager = CollisionManager()
    return _collision_manager

"""
玩家子弹池系统
独立于敌弹系统，用于管理玩家发射的子弹
支持子弹动画（v3 配置）
"""
import numpy as np
from numba import njit
import math
from typing import Dict, List, Optional
from dataclasses import dataclass
from ...core.collision_shapes import Hitbox, hitbox_values, shapes_overlap
from ..damage import damage_source_code, damage_source_name


@dataclass(frozen=True)
class ImpactArea:
    """Numeric post-impact phase: duration/interval in simulation frames.

    Growth interpolates full dimensions (box) or radius (circle). No per-shot
    callback/task runs. The projectile's direct hit is followed by this area.
    """
    hitbox: Hitbox
    damage: float = 10.0
    frames: int = 30
    hit_interval: float = 6.0
    end_hitbox: Hitbox | None = None
    sprite_id: str = ''
    anim_id: int = -1


class PlayerAttack:
    """Generation-safe control of a sparse anchored/continuous attack."""

    def __init__(self, pool, index):
        self.pool, self.index = pool, index
        self.generation = int(pool.generations[index]) if index >= 0 else -1

    @property
    def active(self):
        return (self.index >= 0 and self.pool.generations[self.index] == self.generation
                and bool(self.pool.data['alive'][self.index]))

    def cancel(self):
        if self.active:
            self.pool.kill(self.index)

    def set_damage(self, damage):
        if self.active:
            self.pool.data['damage'][self.index] = damage


class BulletAnimRegistry:
    """子弹动画注册表：管理 bullet_anim_id -> 帧序列的映射"""

    def __init__(self, max_anims: int = 64):
        self.max_anims = max_anims
        self.anim_names: Dict[str, int] = {}
        # 每个动画最多 32 帧
        self.frame_table = np.zeros((max_anims, 32), dtype=np.int32)
        self.frame_count = np.zeros(max_anims, dtype=np.int32)
        self.frame_duration = np.ones(max_anims, dtype=np.float32) * (4.0 / 60.0)
        self.loop_flags = np.ones(max_anims, dtype=np.int32)
        self._next_id = 0

    def register(self, name: str, sprite_ids: List[int],
                 frame_duration: int = 4, loop: bool = True) -> int:
        if name in self.anim_names:
            return self.anim_names[name]
        if self._next_id >= self.max_anims:
            return -1

        anim_id = self._next_id
        self._next_id += 1
        self.anim_names[name] = anim_id
        n = min(len(sprite_ids), 32)
        for i in range(n):
            self.frame_table[anim_id, i] = sprite_ids[i]
        self.frame_count[anim_id] = n
        self.frame_duration[anim_id] = frame_duration / 60.0
        self.loop_flags[anim_id] = 1 if loop else 0
        return anim_id

    def get_id(self, name: str) -> int:
        return self.anim_names.get(name, -1)


class PlayerBulletPool:
    """玩家子弹池"""

    def __init__(self, max_bullets=2000, target_capacity=128):
        self.max_bullets = max_bullets

        self.TYPE_NORMAL = 0
        self.TYPE_HOMING = 1
        self.TYPE_LASER = 2
        self.TYPE_MISSILE = 3

        self.dtype = np.dtype([
            ('pos', 'f4', 2),
            ('vel', 'f4', 2),
            ('angle', 'f4'),
            ('speed', 'f4'),
            ('alive', 'i4'),
            ('bullet_type', 'i4'),
            ('damage', 'f4'),
            ('damage_source', 'u1'),
            ('sprite_idx', 'i4'),
            ('lifetime', 'f4'),
            ('max_lifetime', 'f4'),
            ('homing_strength', 'f4'),
            ('target_idx', 'i4'),
            ('scale', 'f4'),
            ('alpha', 'f4'),
            ('color', 'f4', 4),
            ('penetrate', 'i4'),
            ('anim_id', 'i4'),       # 动画 ID（-1 = 无动画，使用静态 sprite_idx）
            ('anim_timer', 'f4'),    # 动画计时器
            ('shape', 'u1'),
            ('radius', 'f4'),  # negative = use the legacy collision call's radius
            ('half_size', 'f4', 2),
            ('shape_angle', 'f4'),
            ('hit_interval', 'f4'),
            ('render_size', 'f4', 2),  # normalized full size; zero = sprite pixels
            ('phase', 'u1'),
            ('phase_age', 'f8'),
            ('impact_enabled', 'u1'),
            ('impact_shape', 'u1'),
            ('impact_radius', 'f4', 2),
            ('impact_half_size', 'f4', 4),
            ('impact_angle', 'f4'),
            ('impact_angle_end', 'f4'),
            ('impact_damage', 'f4'),
            ('impact_duration', 'f8'),
            ('impact_interval', 'f4'),
            ('impact_sprite', 'i4'),
            ('impact_anim', 'i4'),
        ])

        self.data = np.zeros(max_bullets, dtype=self.dtype)
        self.data['scale'] = 1.0
        self.data['alpha'] = 1.0
        self.data['color'] = [1.0, 1.0, 1.0, 1.0]
        self.data['anim_id'] = -1
        self.generations = np.zeros(max_bullets, np.uint64)
        self.clock_frames = 0.0
        self._alive_before = np.zeros(max_bullets, np.bool_)
        self._anchors = {}
        self._anchor_positions = np.zeros((max_bullets, 2), np.float32)
        self._anchor_flags = np.zeros(max_bullets, np.uint8)
        self._target_objects = [None] * target_capacity
        self._target_slots = {}
        self._hit_deadlines = np.full((max_bullets, target_capacity), -np.inf, np.float64)
        self._collision_output = np.empty((max_bullets, 5), np.float64)
        self._collision_generations = np.empty(max_bullets, np.uint64)

        self.free_indices = list(range(max_bullets - 1, -1, -1))
        self.active_count = 0

        self.sprite_id_to_idx = {}
        self.sprite_idx_to_id = {}

        self.anim_registry = BulletAnimRegistry()

    def register_sprite(self, sprite_id: str, idx: int):
        """注册精灵ID映射"""
        self.sprite_id_to_idx[sprite_id] = idx
        self.sprite_idx_to_id[idx] = sprite_id

    def warmup(self):
        from time import perf_counter
        timings = {}
        empty = self.data[:0]
        start = perf_counter()
        _update_player_bullets(empty, 1.0/60.0, self._empty_enemy_data, self.TYPE_HOMING,
                               self.anim_registry.frame_table, self.anim_registry.frame_count,
                               self.anim_registry.frame_duration, self.anim_registry.loop_flags,
                               self._anchor_flags, self._anchor_positions)
        timings['update_ms'] = (perf_counter()-start)*1000
        start = perf_counter()
        _collide_player_attacks(empty, np.empty((0, 15), np.float64), np.empty(0, np.int32),
                               0.0, self._hit_deadlines, self._collision_output, .02,
                               self.generations, self._collision_generations)
        timings['collision_ms'] = (perf_counter()-start)*1000
        return timings

    def register_bullet_anim(self, name: str, frame_sprite_ids: List[str],
                             frame_duration: int = 4, loop: bool = True) -> int:
        """注册子弹动画，返回 anim_id"""
        idx_list = []
        for sid in frame_sprite_ids:
            if sid not in self.sprite_id_to_idx:
                n = len(self.sprite_id_to_idx)
                self.register_sprite(sid, n)
            idx_list.append(self.sprite_id_to_idx[sid])
        return self.anim_registry.register(name, idx_list, frame_duration, loop)

    def spawn(self, x: float, y: float, angle: float, speed: float,
              sprite_id: str = '', damage: float = 10.0,
              bullet_type: int = 0, homing_strength: float = 0.0,
              max_lifetime: float = 0.0, penetrate: int = 0,
              color: tuple = None, scale: float = 1.0,
              anim_id: int = -1, *, hitbox=None, hit_interval=0.0,
              render_size=(0.0, 0.0), anchor=None, anchor_offset=(0.0, 0.0),
              impact: ImpactArea | None = None, damage_source='shot') -> int:
        """
        生成一颗玩家子弹
        :param anim_id: 动画ID（-1=静态，使用sprite_id）
        :return: 子弹索引，-1表示池已满
        """
        if not self.free_indices:
            return -1
        source_code = damage_source_code(damage_source)
        if hit_interval < 0:
            raise ValueError('hit interval must be non-negative frames')
        shape, radius, half_size, shape_angle = hitbox_values(hitbox, -1.0)
        if impact is not None:
            if impact.frames <= 0 or impact.hit_interval <= 0:
                raise ValueError('impact duration and hit interval must be positive')
            end = impact.end_hitbox or impact.hitbox
            if end.kind != impact.hitbox.kind:
                raise ValueError('impact growth must retain its shape')

        idx = self.free_indices.pop()
        self.active_count += 1

        vx = speed * math.cos(angle)
        vy = speed * math.sin(angle)

        self.data[idx]['pos'] = [x, y]
        self.data[idx]['vel'] = [vx, vy]
        self.data[idx]['angle'] = angle
        self.data[idx]['speed'] = speed
        self.data[idx]['alive'] = 1
        self.data[idx]['bullet_type'] = bullet_type
        self.data[idx]['damage'] = damage
        self.data[idx]['damage_source'] = source_code
        self.data[idx]['lifetime'] = 0.0
        self.data[idx]['max_lifetime'] = max_lifetime
        self.data[idx]['homing_strength'] = homing_strength
        self.data[idx]['target_idx'] = -1
        self.data[idx]['scale'] = scale
        self.data[idx]['alpha'] = 1.0
        self.data[idx]['penetrate'] = penetrate
        self.data[idx]['anim_id'] = anim_id
        self.data[idx]['anim_timer'] = 0.0
        self.data[idx]['shape'] = shape
        self.data[idx]['radius'] = radius
        self.data[idx]['half_size'] = half_size
        self.data[idx]['shape_angle'] = shape_angle
        self.data[idx]['hit_interval'] = hit_interval
        self.data[idx]['render_size'] = render_size
        self.data[idx]['phase'] = 0
        self.data[idx]['phase_age'] = 0.0
        self.data[idx]['impact_enabled'] = impact is not None
        self.generations[idx] += 1
        self._hit_deadlines[idx].fill(-np.inf)
        self._anchor_flags[idx] = 0
        if anchor is not None:
            self._anchors[idx] = (anchor, tuple(anchor_offset))
            self._anchor_flags[idx] = 1
        if impact is not None:
            a = hitbox_values(impact.hitbox)
            b = hitbox_values(end)
            self.data[idx]['impact_shape'] = a[0]
            self.data[idx]['impact_radius'] = a[1], b[1]
            self.data[idx]['impact_half_size'] = (*a[2], *b[2])
            self.data[idx]['impact_angle'] = a[3]
            self.data[idx]['impact_angle_end'] = b[3]
            self.data[idx]['impact_damage'] = impact.damage
            self.data[idx]['impact_duration'] = impact.frames / 60.0
            self.data[idx]['impact_interval'] = impact.hit_interval
            self.data[idx]['impact_anim'] = impact.anim_id
            self.data[idx]['impact_sprite'] = self.sprite_id_to_idx.get(impact.sprite_id, 0)

        if anim_id >= 0 and anim_id < self.anim_registry.frame_count.shape[0]:
            fc = self.anim_registry.frame_count[anim_id]
            if fc > 0:
                self.data[idx]['sprite_idx'] = self.anim_registry.frame_table[anim_id, 0]
            else:
                self.data[idx]['sprite_idx'] = self.sprite_id_to_idx.get(sprite_id, 0)
        else:
            self.data[idx]['sprite_idx'] = self.sprite_id_to_idx.get(sprite_id, 0)

        if color:
            self.data[idx]['color'] = color
        else:
            self.data[idx]['color'] = [1.0, 1.0, 1.0, 1.0]

        return idx

    def kill(self, idx: int):
        """销毁子弹"""
        if self.data[idx]['alive']:
            self.data[idx]['alive'] = 0
            self.data[idx]['anim_id'] = -1
            self.free_indices.append(idx)
            self.active_count -= 1
            self._anchors.pop(idx, None)
            self._anchor_flags[idx] = 0

    def attack_handle(self, index):
        return PlayerAttack(self, index)

    def cancel_anchored(self, owner):
        for index, (anchor, _) in tuple(self._anchors.items()):
            if anchor is owner:
                self.kill(index)

    _enemy_dtype = np.dtype([
        ('pos', 'f4', 2),
        ('alive', 'i4'),
    ])

    # 空的敌人数组（避免向 njit 传 None，防止类型推断问题）
    _empty_enemy_data = np.zeros(0, dtype=_enemy_dtype)

    def build_enemy_data(self, enemy_list):
        """从敌人对象列表构建 njit 可用的 numpy 结构数组"""
        if not enemy_list:
            return self._empty_enemy_data
        n = len(enemy_list)
        arr = np.zeros(n, dtype=self._enemy_dtype)
        count = 0
        for i, e in enumerate(enemy_list):
            alive = getattr(e, '_active', getattr(e, 'alive', True))
            if not alive or not getattr(e, 'interactable', True) or not getattr(e, 'collidable', True):
                continue
            # EnemyScript 用 .x/.y，Boss/Entity 用 .pos
            pos = getattr(e, 'pos', None)
            if pos is not None:
                arr[i]['pos'][0] = float(pos[0])
                arr[i]['pos'][1] = float(pos[1])
                arr[i]['alive'] = 1
                count += 1
            elif hasattr(e, 'x') and hasattr(e, 'y'):
                arr[i]['pos'][0] = float(e.x)
                arr[i]['pos'][1] = float(e.y)
                arr[i]['alive'] = 1
                count += 1
        return arr

    def update(self, dt: float, enemies=None):
        self.clock_frames += dt * 60.0
        np.copyto(self._alive_before, self.data['alive'], casting='unsafe')
        # Only sparse anchored attacks inspect owners. All movement, aging,
        # geometry, phase growth and collision loops below are numeric kernels.
        for idx, (owner, offset) in self._anchors.items():
            if not self.data['alive'][idx]:
                continue
            if (not getattr(owner, '_active', getattr(owner, 'active', getattr(owner, 'alive', True)))
                    or getattr(owner, 'is_dead', False)):
                self._anchor_flags[idx] = 2
                continue
            pos = getattr(owner, 'pos', None)
            if pos is not None:
                x, y = pos[0], pos[1]
            else:
                x = getattr(owner, 'current_x', getattr(owner, 'x', 0.0))
                y = getattr(owner, 'current_y', getattr(owner, 'y', 0.0))
            self._anchor_positions[idx] = x + offset[0], y + offset[1]
        if enemies is not None and not isinstance(enemies, np.ndarray):
            # enemies 是 Python 对象列表，转成 numpy 数组
            enemies_data = self.build_enemy_data(enemies)
        elif enemies is not None:
            enemies_data = enemies
        else:
            enemies_data = self._empty_enemy_data

        _update_player_bullets(
            self.data, dt,
            enemies_data,
            self.TYPE_HOMING,
            self.anim_registry.frame_table,
            self.anim_registry.frame_count,
            self.anim_registry.frame_duration,
            self.anim_registry.loop_flags,
            self._anchor_flags, self._anchor_positions,
        )

        died = np.flatnonzero(self._alive_before & (self.data['alive'] == 0))
        if len(died):
            self.free_indices.extend(died.tolist())
            self.active_count -= len(died)
            for idx in died:
                self._anchors.pop(int(idx), None)
            self._anchor_flags[died] = 0

    def target_slots(self, targets):
        wanted = {id(target) for target in targets}
        for key, slot in tuple(self._target_slots.items()):
            if key not in wanted:
                self._target_objects[slot] = None
                del self._target_slots[key]
        for target in targets:
            key = id(target)
            if key not in self._target_slots:
                try:
                    slot = self._target_objects.index(None)
                except ValueError:
                    old = len(self._target_objects)
                    self._target_objects.extend([None] * max(1, old))
                    self._hit_deadlines = np.pad(self._hit_deadlines, ((0, 0), (0, max(1, old))),
                                                 constant_values=-np.inf)
                    slot = old
                self._target_objects[slot] = target  # prevents Python id reuse
                self._target_slots[key] = slot
                self._hit_deadlines[:, slot] = -np.inf
        return np.asarray([self._target_slots[id(t)] for t in targets], np.int32)

    def collide_targets(self, active, *, tracked_targets=None, hit_radius=0.02):
        from ...core.collision import BulletCollisionResult
        self.target_slots(active if tracked_targets is None else tracked_targets)
        if not active:
            return []
        slots = np.asarray([self._target_slots[id(t)] for t in active], np.int32)
        target_data = np.zeros((len(active), 15), np.float64)
        target_data[:, 7] = -1
        for i, target in enumerate(active):
            pos = getattr(target, 'pos', None)
            x, y = pos if pos is not None else (target.x, target.y)
            radius = getattr(target, 'hitbox_radius', getattr(target, 'hit_radius', .05))
            kind, radius, half, angle = hitbox_values(getattr(target, 'hitbox', None), radius)
            target_data[i, :7] = x, y, kind, radius, half[0], half[1], angle
            bound = radius if kind == 0 else math.hypot(*half)
            secondary = getattr(target, 'secondary_hitbox', None)
            if secondary is not None:
                kind2, radius2, half2, angle2 = hitbox_values(secondary)
                target_data[i, 7:14] = kind2, radius2, half2[0], half2[1], angle2, x, y
                bound = max(bound, radius2 if kind2 == 0 else math.hypot(*half2))
            target_data[i, 14] = bound
        capacity = self.max_bullets * len(active)
        if len(self._collision_output) < capacity:
            self._collision_output = np.empty((capacity, 5), np.float64)
            self._collision_generations = np.empty(capacity, np.uint64)
        np.copyto(self._alive_before, self.data['alive'], casting='unsafe')
        count = _collide_player_attacks(self.data, target_data, slots, self.clock_frames,
                                       self._hit_deadlines, self._collision_output, hit_radius,
                                       self.generations, self._collision_generations)
        died = np.flatnonzero(self._alive_before & (self.data['alive'] == 0))
        self.free_indices.extend(died.tolist())
        self.active_count -= len(died)
        for idx in died:
            self._anchors.pop(int(idx), None)
        self._anchor_flags[died] = 0
        return [BulletCollisionResult(int(b), int(t), damage,
                                      tuple(self.data['pos'][int(b)]),
                                      source=damage_source_name(int(source)),
                                      attack_generation=int(self._collision_generations[row]),
                                      region=int(region))
                for row, (b, t, damage, source, region) in enumerate(self._collision_output[:count])]

    def check_collision_with_enemies(self, enemies) -> list:
        from ...core.collision import get_collision_manager
        hits, active = get_collision_manager().check_player_bullets_vs_targets(self, enemies or [])
        return [(hit.bullet_idx, enemies.index(active[hit.target_idx]), hit.damage) for hit in hits]

    def get_active_data(self):
        """获取活跃子弹的数据（用于渲染）"""
        mask = self.data['alive'] == 1
        return self.data[mask]

    def clear(self):
        """清空所有子弹"""
        self.data['alive'] = 0
        self.data['anim_id'] = -1
        self.free_indices = list(range(self.max_bullets - 1, -1, -1))
        self.active_count = 0
        self._anchors.clear()
        self._anchor_flags.fill(0)
        self._target_slots.clear()
        self._target_objects[:] = [None] * len(self._target_objects)
        self._hit_deadlines.fill(-np.inf)

    # 兼容旧代码
    def clear_all(self):
        self.clear()


@njit(cache=True)
def _update_player_bullets(data, dt, enemy_data, TYPE_HOMING,
                           anim_frame_table, anim_frame_count,
                           anim_frame_duration, anim_loop_flags, anchor_flags, anchor_positions):
    for idx in range(data.shape[0]):
        if data[idx]['alive'] == 0:
            continue

        data[idx]['lifetime'] += dt
        if data[idx]['phase'] == 1:
            data[idx]['phase_age'] += dt
            t = min(1.0, data[idx]['phase_age'] / data[idx]['impact_duration'])
            data[idx]['shape_angle'] = (data[idx]['impact_angle']
                + (data[idx]['impact_angle_end']-data[idx]['impact_angle']) * t)
            data[idx]['angle'] = data[idx]['shape_angle']
            r = data[idx]['impact_radius']
            data[idx]['radius'] = r[0] + (r[1] - r[0]) * t
            h = data[idx]['impact_half_size']
            for axis in range(2):
                data[idx]['half_size'][axis] = h[axis] + (h[axis+2] - h[axis]) * t
                data[idx]['render_size'][axis] = (data[idx]['radius'] * 2.0
                                                 if data[idx]['shape'] == 0
                                                 else data[idx]['half_size'][axis] * 2.0)
            if data[idx]['phase_age'] + 1e-8 >= data[idx]['impact_duration']:
                data[idx]['alive'] = 0
                continue

        # ---- 动画帧更新 ----
        aid = data[idx]['anim_id']
        if aid >= 0 and aid < anim_frame_count.shape[0]:
            fc = anim_frame_count[aid]
            if fc > 0:
                data[idx]['anim_timer'] += dt
                fd = anim_frame_duration[aid]
                if fd > 0:
                    frame_idx = int(data[idx]['anim_timer'] / fd)
                    if anim_loop_flags[aid] == 1:
                        frame_idx = frame_idx % fc
                    else:
                        if frame_idx >= fc:
                            frame_idx = fc - 1
                    data[idx]['sprite_idx'] = anim_frame_table[aid, frame_idx]

        bullet_type = data[idx]['bullet_type']

        # ---- 追踪弹逻辑 ----
        if bullet_type == TYPE_HOMING and enemy_data is not None:
            homing_strength = data[idx]['homing_strength']
            if homing_strength > 0:
                min_dist_sq = 1e10
                target_x, target_y = 0.0, 0.0
                found_target = False

                bx, by = data[idx]['pos']

                for e_idx in range(enemy_data.shape[0]):
                    if enemy_data[e_idx]['alive'] == 0:
                        continue

                    ex = enemy_data[e_idx]['pos'][0]
                    ey = enemy_data[e_idx]['pos'][1]
                    dist_sq = (ex - bx) ** 2 + (ey - by) ** 2

                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq
                        target_x, target_y = ex, ey
                        found_target = True

                if found_target:
                    target_angle = math.atan2(target_y - by, target_x - bx)
                    current_angle = data[idx]['angle']

                    angle_diff = target_angle - current_angle
                    while angle_diff > math.pi:
                        angle_diff -= 2 * math.pi
                    while angle_diff < -math.pi:
                        angle_diff += 2 * math.pi

                    max_turn = homing_strength * dt
                    if angle_diff > max_turn:
                        angle_diff = max_turn
                    elif angle_diff < -max_turn:
                        angle_diff = -max_turn

                    new_angle = current_angle + angle_diff
                    data[idx]['angle'] = new_angle
                    speed = data[idx]['speed']
                    data[idx]['vel'][0] = speed * math.cos(new_angle)
                    data[idx]['vel'][1] = speed * math.sin(new_angle)

        # ---- 更新位置 ----
        data[idx]['pos'][0] += data[idx]['vel'][0] * dt
        data[idx]['pos'][1] += data[idx]['vel'][1] * dt
        if data[idx]['phase'] == 0 and anchor_flags[idx] != 0:
            if anchor_flags[idx] == 2:
                data[idx]['alive'] = 0
                continue
            data[idx]['pos'] = anchor_positions[idx]
        x, y = data[idx]['pos']
        # Cull by extents: a beam centered above the screen may still cross it.
        extent = max(data[idx]['half_size'][0], data[idx]['half_size'][1],
                     max(0.0, data[idx]['radius']))
        if (x < -1.5-extent or x > 1.5+extent or y < -1.5-extent or y > 1.5+extent
                or (data[idx]['max_lifetime'] > 0
                    and data[idx]['lifetime'] > data[idx]['max_lifetime'])):
            data[idx]['alive'] = 0


@njit(cache=True)
def _collide_player_attacks(data, targets, slots, now, deadlines, output, default_radius,
                            generations, output_generations):
    count = 0
    for i in range(len(data)):
        if not data[i]['alive']:
            continue
        row = data[i]
        radius = default_radius if row['radius'] < 0 else row['radius']
        attack_bound = (radius if row['shape'] == 0 else
                        math.hypot(row['half_size'][0], row['half_size'][1]))
        for j in range(len(targets)):
            t = targets[j]
            dx, dy = row['pos'][0] - t[0], row['pos'][1] - t[1]
            bound = attack_bound + t[14]
            if dx * dx + dy * dy > bound * bound:
                continue
            slot = slots[j]
            interval = row['hit_interval']
            if interval > 0 and now + 1e-8 < deadlines[i, slot]:
                continue
            primary = shapes_overlap(row['pos'][0], row['pos'][1], row['shape'], radius,
                                  row['half_size'][0], row['half_size'][1], row['shape_angle'],
                                  t[0], t[1], int(t[2]), t[3], t[4], t[5], t[6])
            region = 0
            if not primary:
                if t[7] < 0 or not shapes_overlap(
                        row['pos'][0], row['pos'][1], row['shape'], radius,
                        row['half_size'][0], row['half_size'][1], row['shape_angle'],
                        t[12], t[13], int(t[7]), t[8], t[9], t[10], t[11]):
                    continue
                region = 1
            output[count, 0], output[count, 1], output[count, 2] = i, j, row['damage']
            output[count, 3] = row['damage_source']
            output[count, 4] = region
            output_generations[count] = generations[i]
            count += 1
            if row['impact_enabled'] and row['phase'] == 0:
                row['phase'] = 1
                row['phase_age'] = 0.0
                row['vel'][0] = 0.0
                row['vel'][1] = 0.0
                row['speed'] = 0.0
                row['bullet_type'] = 0
                row['damage'] = row['impact_damage']
                row['shape'] = row['impact_shape']
                row['radius'] = row['impact_radius'][0]
                row['half_size'][0] = row['impact_half_size'][0]
                row['half_size'][1] = row['impact_half_size'][1]
                row['shape_angle'] = row['impact_angle']
                row['angle'] = row['impact_angle']
                row['hit_interval'] = row['impact_interval']
                row['sprite_idx'] = row['impact_sprite']
                row['anim_id'] = row['impact_anim']
                row['anim_timer'] = 0.0
                row['max_lifetime'] = 0.0
                for axis in range(2):
                    row['render_size'][axis] = (row['radius'] * 2.0 if row['shape'] == 0
                                               else row['half_size'][axis] * 2.0)
                for k in range(deadlines.shape[1]):
                    deadlines[i, k] = -np.inf
                deadlines[i, slot] = now + row['hit_interval']
                break
            if interval > 0:
                deadlines[i, slot] = now + interval
            elif row['penetrate'] > 0:
                row['penetrate'] -= 1
            else:
                row['alive'] = 0
                break
    return count

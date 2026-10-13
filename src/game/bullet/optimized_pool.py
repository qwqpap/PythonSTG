"""
优化版子弹池 - 使用整数精灵索引和向量化渲染数据准备

主要优化:
1. sprite_id 使用 uint16 整数索引（从32字节减少到2字节）
2. 预计算并缓存渲染数据（UV、尺寸）
3. 使用向量化操作准备批量渲染数据
4. 支持按纹理/大小分组的高效渲染

v2 扩展字段:
- render_angle / angular_vel: 渲染朝向与运动方向解耦，支持自转
- friction: 摩擦 / 阻尼系数
- tag: 分组标签（用于按组消弹等）
- time_scale: 每子弹时间缩放（时停 / 慢动作）
- flags: 位标志（反弹、发射器、render_angle 锁定等）
- curve_type / curve_param: 内置数学曲线（sin/cos/linear 速度/角度调制）
"""

import numpy as np
from numba import njit
import math
from typing import Dict, List, Tuple, Optional, Callable, Any
from dataclasses import dataclass

# 使用绝对导入
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from src.core.sprite_registry import SpriteRegistry, get_sprite_registry
from src.core.config import get_config
from src.game.bullet.tags import BOMB_PROTECTED_TAGS
from src.game.bullet.behavior import (
    BulletGroup, STAGE_DTYPE, advance_stages, compile_stages, region_mask,
)
from src.game.bullet.batch import (
    BulletSnapshot, normalize_scalar, normalize_vector,
    distance_acceleration, neighbor_activation,
)
from src.game.bullet.motion import post_bounds
from src.game.bullet.termination import TerminationQueue


# ============= Flags 位常量 =============

FLAG_BOUNCE_X            = 0x0001  # 碰到左右边界反弹
FLAG_BOUNCE_Y            = 0x0002  # 碰到上下边界反弹
FLAG_IS_EMITTER          = 0x0004  # 发射器节点（不渲染、不碰撞）
FLAG_RENDER_ANGLE_LOCKED = 0x0008  # render_angle 锁定跟随运动角（默认开启）
FLAG_IS_POLAR            = 0x0010  # 极坐标子弹（JIT 内核跳过，由 _update_polar_motions 驱动）

# ============= Curve 类型常量 =============

CURVE_NONE         = 0
CURVE_SIN_SPEED    = 1  # speed = base + amp * sin(freq * t + phase)
CURVE_SIN_ANGLE    = 2  # angle += amp * sin(freq * t + phase) * dt
CURVE_COS_SPEED    = 3  # speed = base + amp * cos(freq * t + phase)
CURVE_LINEAR_SPEED = 4  # speed = base + amp * t
CURVE_DELAYED_TURN = 5  # after delay seconds, add a constant angular velocity


@dataclass
class SpawnRequest:
    """生成请求"""
    x: float
    y: float
    angle: float
    speed: float
    sprite_idx: int = 0
    delay: int = 0
    acc: Tuple[float, float] = (0.0, 0.0)
    # Straight-projectile acceleration state.  ``speed`` is the pool's
    # normalized per-frame scalar; ``speed_accel`` changes that scalar per
    # second.  Angular values are radians/second² and radians/second.
    speed_accel: float = 0.0
    motion_angular_accel: float = 0.0
    max_lifetime: float = 0.0
    radius: float = 0.0
    init: Optional[Callable] = None
    on_death: Optional[Callable] = None
    # v2 扩展
    friction: float = 0.0
    tag: int = 0
    time_scale: float = 1.0
    flags: int = FLAG_RENDER_ANGLE_LOCKED  # 默认锁定
    angular_vel: float = 0.0
    render_angle: float = 0.0
    render_scale: float = 1.0
    curve_type: int = 0
    curve_param: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass
class DeathEvent:
    """死亡事件"""
    idx: int
    x: float
    y: float
    handler: Optional[Callable] = None


@dataclass(frozen=True)
class LifecycleBatch:
    """One data-oriented lifecycle fact for an arbitrary number of bullets."""

    event_type: str
    source: str
    owner: str | None
    reason: str | None
    count: int
    representative_ids: tuple[str, ...] = ()
    representative_positions: tuple[tuple[float, float], ...] = ()
    payload: dict[str, Any] | None = None


@dataclass
class PolarMotion:
    """极坐标运动：bullet position = center + polar(radius, theta)."""
    center: Any
    radius: float
    theta: float
    radial_speed: float = 0.0
    angular_velocity: float = 0.0
    render_mode: str = 'velocity'
    angle_offset: float = 0.0


class OptimizedBulletPool:
    """
    优化版子弹池 (v2)

    v2 新增能力:
    - render_angle 与运动角解耦、自转 (angular_vel)
    - 摩擦力 / 阻尼 (friction)
    - 分组标签 (tag) + clear_by_tag / set_time_scale_by_tag
    - 时间缩放 (time_scale) — 每子弹独立
    - 边界反弹 (flags & BOUNCE_X/Y)
    - 发射器节点 (flags & IS_EMITTER) — 不渲染不碰撞但可挂回调
    - 内置数学曲线 (curve_type + curve_param)
    """

    def __init__(self, max_bullets: int = 50000, sprite_registry: SpriteRegistry = None):
        self.max_bullets = max_bullets
        self.sprite_registry = sprite_registry or get_sprite_registry()

        # v2 数据结构
        self.dtype = np.dtype([
            ('pos', 'f4', 2),           # 位置 (x, y)
            ('vel', 'f4', 2),           # 速度 (vx, vy)
            ('acc', 'f4', 2),           # 加速度 (ax, ay)
            ('angle', 'f4'),            # 运动方向角（弧度，由 vel 重算）
            ('render_angle', 'f4'),     # 渲染朝向角（可自转）
            ('angular_vel', 'f4'),      # render_angle 的角速度（弧度/秒）
            ('render_scale', 'f4'),     # per-bullet render size multiplier
            ('speed', 'f4'),            # 标量速度
            ('speed_accel', 'f4'),      # 标量速度加速度（每秒，pool speed 单位）
            ('motion_angular_vel', 'f4'),    # 运动角速度（弧度/秒）
            ('motion_angular_accel', 'f4'), # 运动角加速度（弧度/秒²）
            ('alive', 'i4'),            # 存活标记
            ('sprite_idx', 'u2'),       # 精灵索引
            ('flags', 'u2'),            # 位标志 (bounce, emitter, render_angle_locked, ...)
            ('radius', 'f4'),           # 碰撞半径
            ('lifetime', 'f4'),         # 已存活秒数
            ('max_lifetime', 'f4'),     # ≤0 无限存活
            ('friction', 'f4'),         # 摩擦/阻尼系数
            ('tag', 'i4'),              # 分组标签
            ('time_scale', 'f4'),       # 时间缩放 (1.0=正常)
            ('curve_type', 'u1'),       # 内置曲线类型
            ('curve_param', 'f4', 4),   # 曲线参数 [amp, freq, phase, base]
        ])

        self.data = np.zeros(max_bullets, dtype=self.dtype)
        # 默认值
        self.data['time_scale'] = 1.0
        self.data['flags'] = FLAG_RENDER_ANGLE_LOCKED
        self.data['render_scale'] = 1.0

        # Stack pop should allocate low-to-high indices for deterministic
        # authored batch order; releases still append for O(1) reuse.
        self.free_indices = list(range(max_bullets - 1, -1, -1))

        # Python 层回调
        self.death_handlers: Dict[int, Callable] = {}
        self.polar_motions: Dict[int, PolarMotion] = {}
        self.emitter_callbacks: Dict[int, Callable] = {}

        self.spawn_queue: List[SpawnRequest] = []
        self.death_queue: List[DeathEvent] = []
        # Formal runtime lifecycle facts are one record per (reason, owner,
        # frame/update), never one Python object per bullet.  Legacy
        # ``death_handlers`` remain available only for the explicitly opted-in
        # compatibility API.
        self.lifecycle_batches: List[LifecycleBatch] = []
        self._termination_reasons: Dict[int, str] = {}
        self._termination_batch_reactions: Dict[int, Dict[str, Any]] = {}
        self._termination_batch_queue: List[tuple[np.ndarray, np.ndarray, Dict[str, Any]]] = []
        self.last_alive = np.zeros(max_bullets, dtype='i4')
        self.batch_spawn_calls = 0
        # Monotonic runtime counter used by the editor's fixed-rate aggregate
        # Trace. It is one integer update per spawn/batch, never a callback or
        # Python object per bullet.
        self.spawned_total = 0
        self.generations = np.zeros(max_bullets, dtype=np.uint32)
        self.collision_eligible = np.zeros(max_bullets, dtype=np.bool_)
        self._group_token = object()
        self._in_update = False
        self._clock = 0.0
        self.scope_generation = 0
        self._player_target = (0.0, 0.0)
        self._cooldowns: dict[Any, np.ndarray] = {}
        # Behavior state is allocated only when the project actually uses it.
        self._behavior_stage = None
        self._behavior_end = None
        self._behavior_elapsed = None
        self._behavior_entered = None
        self._bounce_remaining_x = None
        self._bounce_remaining_y = None
        self._wrap_remaining_x = None
        self._wrap_remaining_y = None
        self._wrap_live_count = 0
        self.terminations = TerminationQueue()
        self._behavior_count = 0
        self._behavior_table = np.empty(0, dtype=STAGE_DTYPE)
        self._behavior_programs = {}
        self._behavior_gc_at = 128

        # ===== 渲染优化相关 =====
        self._render_positions = np.zeros((max_bullets, 2), dtype='f4')
        self._render_angles = np.zeros(max_bullets, dtype='f4')
        self._render_uvs = np.zeros((max_bullets, 4), dtype='f4')
        self._render_scales = np.zeros((max_bullets, 2), dtype='f4')
        self._render_tex_indices = np.zeros(max_bullets, dtype='u2')
        self._render_categories = np.zeros(max_bullets, dtype='u1')
        self._render_bucket_counts = np.zeros(0, dtype=np.int32)
        self._render_bucket_write_offsets = np.zeros(0, dtype=np.int32)
        self._render_batch_starts = np.zeros(0, dtype=np.int32)
        self._render_batch_counts = np.zeros(0, dtype=np.int32)
        self._render_batch_tex = np.zeros(0, dtype=np.int32)
        self._render_batch_cat = np.zeros(0, dtype=np.int32)

        config = get_config()
        self._scale_factor = config.pixel_to_ndc_scale

        self._sprite_id_to_idx: Dict[str, int] = {}

    def _ensure_render_bucket_buffers(self, key_count: int):
        if self._render_bucket_counts.size >= key_count:
            return
        self._render_bucket_counts = np.zeros(key_count, dtype=np.int32)
        self._render_bucket_write_offsets = np.zeros(key_count, dtype=np.int32)
        self._render_batch_starts = np.zeros(key_count, dtype=np.int32)
        self._render_batch_counts = np.zeros(key_count, dtype=np.int32)
        self._render_batch_tex = np.zeros(key_count, dtype=np.int32)
        self._render_batch_cat = np.zeros(key_count, dtype=np.int32)

    # ===== 精灵注册 =====

    def register_sprite(self, sprite_id: str) -> int:
        if sprite_id in self._sprite_id_to_idx:
            return self._sprite_id_to_idx[sprite_id]
        idx = self.sprite_registry.get_index(sprite_id)
        self._sprite_id_to_idx[sprite_id] = idx
        return idx

    # ===== 生成 =====

    def spawn_bullet(
        self,
        x: float,
        y: float,
        angle: float,
        speed: float,
        sprite_id: str = '',
        sprite_idx: int = -1,
        delay: int = 0,
        acc: Tuple[float, float] = None,
        speed_accel: float = 0.0,
        motion_angular_accel: float = 0.0,
        max_lifetime: float = 0.0,
        radius: float = 0.0,
        init: Callable = None,
        on_death: Callable = None,
        # v2 扩展参数
        friction: float = 0.0,
        tag: int = 0,
        time_scale: float = 1.0,
        flags: int = FLAG_RENDER_ANGLE_LOCKED,
        angular_vel: float = 0.0,
        render_angle: float = None,
        render_scale: float = 1.0,
        curve_type: int = 0,
        curve_param: Tuple[float, float, float, float] = None,
        **kwargs
    ) -> int:
        """
        生成子弹

        v2 新增 Args:
            friction: 摩擦/阻尼系数
            tag: 分组标签
            time_scale: 时间缩放
            flags: 位标志 (FLAG_BOUNCE_X, FLAG_BOUNCE_Y, FLAG_IS_EMITTER, FLAG_RENDER_ANGLE_LOCKED)
            angular_vel: render_angle 角速度（弧度/秒）
            render_angle: 初始渲染朝向（None = 跟随 angle）
            curve_type: 内置曲线类型
            curve_param: 曲线参数 (amp, freq, phase, base)
        """
        if kwargs:
            raise TypeError('unknown spawn_bullet parameters: ' + ', '.join(sorted(kwargs)))
        acc = (0.0, 0.0) if acc is None else acc
        curve_param = curve_param or (0.0, 0.0, 0.0, 0.0)
        if render_angle is None:
            render_angle = angle

        if sprite_idx < 0:
            sprite_idx = self.register_sprite(sprite_id) if sprite_id else 0

        if delay > 0:
            self.spawn_queue.append(SpawnRequest(
                x=x, y=y, angle=angle, speed=speed,
                sprite_idx=sprite_idx, delay=delay, acc=acc,
                speed_accel=speed_accel,
                motion_angular_accel=motion_angular_accel,
                max_lifetime=max_lifetime, radius=radius,
                init=init, on_death=on_death,
                friction=friction, tag=tag, time_scale=time_scale,
                flags=flags, angular_vel=angular_vel, render_angle=render_angle,
                render_scale=render_scale,
                curve_type=curve_type, curve_param=curve_param,
            ))
            return -1

        if not self.free_indices:
            return -1

        idx = self.free_indices.pop()
        self._write_bullet(idx, x, y, angle, speed, acc, speed_accel,
                           motion_angular_accel, sprite_idx, radius,
                           max_lifetime, friction, tag, time_scale, flags,
                           angular_vel, render_angle, render_scale,
                           curve_type, curve_param)

        if on_death:
            self.death_handlers[idx] = on_death
        elif idx in self.death_handlers:
            del self.death_handlers[idx]

        if init:
            init(self, idx)

        return idx

    def _write_bullet(self, idx, x, y, angle, speed, acc, speed_accel,
                      motion_angular_accel, sprite_idx, radius,
                      max_lifetime, friction, tag, time_scale, flags,
                      angular_vel, render_angle, render_scale, curve_type, curve_param):
        """写入子弹数据到指定 slot"""
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed

        d = self.data
        d['pos'][idx] = (x, y)
        d['vel'][idx] = (vx, vy)
        d['acc'][idx] = acc
        d['angle'][idx] = angle
        d['render_angle'][idx] = render_angle
        d['angular_vel'][idx] = angular_vel
        d['render_scale'][idx] = render_scale
        d['speed'][idx] = speed
        d['speed_accel'][idx] = speed_accel
        d['motion_angular_vel'][idx] = 0.0
        d['motion_angular_accel'][idx] = motion_angular_accel
        d['sprite_idx'][idx] = sprite_idx
        d['radius'][idx] = radius
        d['lifetime'][idx] = 0.0
        d['max_lifetime'][idx] = max_lifetime
        d['friction'][idx] = friction
        d['tag'][idx] = tag
        d['time_scale'][idx] = time_scale
        d['flags'][idx] = flags
        d['curve_type'][idx] = curve_type
        d['curve_param'][idx] = curve_param
        d['alive'][idx] = 1
        self._reset_spawn_state(np.asarray([idx], dtype=np.intp))
        self.spawned_total += 1

    def spawn_pattern(
        self,
        x: float,
        y: float,
        angle: float,
        speed: float,
        count: int = 18,
        angle_spread: float = math.pi * 2,
        sprite_id: str = '',
        sprite_idx: int = -1,
        max_lifetime: float = 0.0,
        radius: float = 0.0,
        acc: Tuple[float, float] = None,
        on_death: Callable = None,
        # v2
        friction: float = 0.0,
        tag: int = 0,
        time_scale: float = 1.0,
        flags: int = FLAG_RENDER_ANGLE_LOCKED,
    ):
        """批量生成圆形扩散子弹（向量化优化）"""
        if count <= 0:
            return

        acc = acc or (0.0, 0.0)
        if sprite_idx < 0:
            sprite_idx = self.register_sprite(sprite_id) if sprite_id else 0

        angle_step = angle_spread / count
        angles = np.array([angle + i * angle_step for i in range(count)], dtype='f4')
        vxs = np.cos(angles) * speed
        vys = np.sin(angles) * speed

        available = min(count, len(self.free_indices))
        if available == 0:
            return

        use_indices = self._allocate_indices(available)
        n = len(use_indices)

        d = self.data
        d['pos'][use_indices, 0] = x
        d['pos'][use_indices, 1] = y
        d['vel'][use_indices, 0] = vxs[:n]
        d['vel'][use_indices, 1] = vys[:n]
        d['acc'][use_indices, 0] = acc[0]
        d['acc'][use_indices, 1] = acc[1]
        d['angle'][use_indices] = angles[:n]
        d['render_angle'][use_indices] = angles[:n]
        d['angular_vel'][use_indices] = 0.0
        d['render_scale'][use_indices] = 1.0
        d['speed'][use_indices] = speed
        d['speed_accel'][use_indices] = 0.0
        d['motion_angular_vel'][use_indices] = 0.0
        d['motion_angular_accel'][use_indices] = 0.0
        d['sprite_idx'][use_indices] = sprite_idx
        d['radius'][use_indices] = radius
        d['lifetime'][use_indices] = 0.0
        d['max_lifetime'][use_indices] = max_lifetime
        d['friction'][use_indices] = friction
        d['tag'][use_indices] = tag
        d['time_scale'][use_indices] = time_scale
        d['flags'][use_indices] = flags
        d['curve_type'][use_indices] = CURVE_NONE
        d['curve_param'][use_indices] = (0.0, 0.0, 0.0, 0.0)
        d['alive'][use_indices] = 1
        self._reset_spawn_state(use_indices)
        self.spawned_total += n

        if on_death:
            for idx in use_indices:
                self.death_handlers[idx] = on_death
        return use_indices

    # ===== 发射器 (Emitter) =====

    def spawn_bullets_batch(
        self,
        positions,
        angles,
        speeds,
        *,
        sprite_id: str = '',
        sprite_idx: int = -1,
        acc: Tuple[float, float] = (0.0, 0.0),
        speed_accel: float = 0.0,
        motion_angular_accel: float = 0.0,
        max_lifetime: float = 0.0,
        radius: float = 0.0,
        friction: float = 0.0,
        tag: int = 0,
        time_scale: float = 1.0,
        flags: int = FLAG_RENDER_ANGLE_LOCKED,
        angular_vel: float = 0.0,
        render_angles=None,
        render_scale: float = 1.0,
        curve_type: int = CURVE_NONE,
        curve_param: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    ) -> np.ndarray:
        """Spawn heterogeneous bullets with one vectorized pool write.

        Angles are radians and speeds are normalized units per frame, matching
        :meth:`spawn_bullet`. Capacity exhaustion is explicit: the returned
        array contains only the slots that were actually allocated.
        """
        position_array = np.asarray(positions, dtype=np.float32)
        if position_array.size == 0:
            position_array = position_array.reshape((0, 2))
        if position_array.ndim != 2 or position_array.shape[1] != 2:
            raise ValueError("positions must have shape (count, 2)")
        count = len(position_array)
        angle_array = normalize_scalar(angles, count, 'angles')
        speed_array = normalize_scalar(speeds, count, 'speeds')
        if not (
            np.all(np.isfinite(position_array))
            and np.all(np.isfinite(angle_array))
            and np.all(np.isfinite(speed_array))
        ):
            raise ValueError("batch positions, angles, and speeds must be finite")
        if np.any(speed_array < 0):
            raise ValueError("batch speeds must be non-negative")

        if render_angles is None:
            render_angle_array = angle_array
        else:
            render_angle_array = normalize_scalar(render_angles, count, 'render_angles')

        available = min(count, len(self.free_indices))
        if available == 0:
            return np.empty(0, dtype=np.intp)
        if np.ndim(sprite_idx) == 0 and sprite_idx < 0:
            sprite_idx = self.register_sprite(sprite_id) if sprite_id else 0

        parameters = {
            'acc': self._batch_parameter(acc, count, 'acc', vector=True),
            'speed_accel': self._batch_parameter(speed_accel, count, 'speed_accel'),
            'motion_angular_accel': self._batch_parameter(motion_angular_accel, count, 'motion_angular_accel'),
            'sprite_idx': self._batch_parameter(sprite_idx, count, 'sprite_idx', dtype=np.uint16),
            'radius': self._batch_parameter(radius, count, 'radius'),
            'max_lifetime': self._batch_parameter(max_lifetime, count, 'max_lifetime'),
            'friction': self._batch_parameter(friction, count, 'friction'),
            'tag': self._batch_parameter(tag, count, 'tag', dtype=np.int32),
            'time_scale': self._batch_parameter(time_scale, count, 'time_scale'),
            'flags': self._batch_parameter(flags, count, 'flags', dtype=np.uint16),
            'angular_vel': self._batch_parameter(angular_vel, count, 'angular_vel'),
            'render_scale': self._batch_parameter(render_scale, count, 'render_scale'),
            'curve_type': self._batch_parameter(curve_type, count, 'curve_type', dtype=np.uint8),
        }
        curve_array = np.asarray(curve_param, dtype=np.float32)
        if curve_array.shape not in {(4,), (count, 4)} or not np.all(np.isfinite(curve_array)):
            raise ValueError('curve_param requires shape (4,) or (count, 4)')

        use_indices = self._allocate_indices(available)
        # Preserve authored batch order in the observable pool layout.  The
        # free-list is a stack for O(1) reuse, but callers must not see a
        # burst's data reversed merely because slots were allocated backward.
        use_indices.sort()
        batch_positions = position_array[:available]
        batch_angles = angle_array[:available]
        batch_speeds = speed_array[:available]
        d = self.data
        d['pos'][use_indices] = batch_positions
        d['vel'][use_indices, 0] = np.cos(batch_angles) * batch_speeds
        d['vel'][use_indices, 1] = np.sin(batch_angles) * batch_speeds
        d['angle'][use_indices] = batch_angles
        d['render_angle'][use_indices] = render_angle_array[:available]
        d['speed'][use_indices] = batch_speeds
        d['motion_angular_vel'][use_indices] = 0.0
        d['lifetime'][use_indices] = 0.0
        d['curve_param'][use_indices] = curve_array[:available] if curve_array.ndim == 2 else curve_array
        for name, parameter in parameters.items():
            d[name][use_indices] = parameter[:available] if np.ndim(parameter) > (1 if name == 'acc' else 0) else parameter
        d['alive'][use_indices] = 1
        self._reset_spawn_state(use_indices)
        self.batch_spawn_calls += 1
        self.spawned_total += available

        # Formal pattern batches never install per-bullet callbacks. Clear any
        # stale sparse state defensively if a legacy path reused these slots.
        self._clear_sparse_state(use_indices)
        return use_indices

    def _clear_sparse_state(self, indices):
        for mapping in (self.death_handlers, self._termination_reasons,
                        self.polar_motions, self.emitter_callbacks):
            if mapping:
                keys = np.asarray(tuple(mapping), dtype=np.intp)
                for idx in keys[np.isin(keys, indices)].tolist():
                    mapping.pop(idx, None)

    def _allocate_indices(self, count):
        """Bulk-pop the free stack without a Python call for every bullet."""
        indices = np.asarray(self.free_indices[-count:][::-1], dtype=np.intp)
        del self.free_indices[-count:]
        return indices

    def _release_behavior_state(self, indices):
        if self._behavior_stage is not None:
            self._behavior_count -= int(np.count_nonzero(self._behavior_stage[indices] >= 0))
            self._behavior_stage[indices] = -1
            self._bounce_remaining_x[indices] = -1
            self._bounce_remaining_y[indices] = -1
        if self._wrap_remaining_x is not None:
            self._wrap_remaining_x[indices] = -1
            self._wrap_remaining_y[indices] = -1

    def _reset_spawn_state(self, indices):
        self._release_behavior_state(indices)
        self.generations[indices] += np.uint32(1)
        # Gameplay controllers run after pool.update and before collision.
        # All births wait for their first pool update, including those births.
        self.collision_eligible[indices] = False
        for deadlines in self._cooldowns.values():
            deadlines[indices] = 0.0

    def capture_group(self, indices) -> BulletGroup:
        """Capture fixed slot generations; replacing a dead slot cannot join it."""
        values = self._resolve_indices(indices)
        values = values.copy()
        generations = self.generations[values].copy()
        values.flags.writeable = False
        generations.flags.writeable = False
        return BulletGroup(values, generations, self._group_token)

    def _resolve_indices(self, group=None, *, tag=None, region=None):
        if isinstance(group, BulletGroup):
            if group.pool_token is not self._group_token:
                raise ValueError('bullet group belongs to another pool')
            values = group.indices
            values = values[self.generations[values] == group.generations]
            values = values[self.data['alive'][values] != 0]
        elif group is not None:
            values = np.asarray(group, dtype=np.intp).reshape(-1)
            values = np.unique(values[(values >= 0) & (values < self.max_bullets)])
            values = values[self.data['alive'][values] != 0]
        else:
            mask = self.data['alive'] != 0
            if tag is not None:
                mask &= self.data['tag'] == int(tag)
            if region is not None:
                mask &= region_mask(self.data, region)
            return np.flatnonzero(mask)
        if tag is not None:
            values = values[self.data['tag'][values] == int(tag)]
        if region is not None:
            mask = region_mask(self.data, region)
            values = values[mask[values]]
        return values

    def resolve_indices(self, group=None, *, tag=None, region=None) -> np.ndarray:
        """Return living slot indices after validating fixed group generations."""
        return self._resolve_indices(group, tag=tag, region=region)

    def select_bullets(self, *, tag=None, region=None) -> BulletGroup:
        """Snapshot living bullets now; tags by contrast are queried each call."""
        indices = self._resolve_indices(tag=tag, region=region)
        indices = indices[(self.data['flags'][indices] & FLAG_IS_EMITTER) == 0]
        return self.capture_group(indices)

    def count_bullets(self, group=None, *, tag=None, region=None) -> int:
        return len(self._resolve_indices(group, tag=tag, region=region))

    @staticmethod
    def _batch_parameter(value, count, name, *, source_count=None, survivor_mask=None,
                         vector=False, dtype=np.float32):
        array = np.asarray(value)
        if (vector and array.shape == (2,)) or (not vector and array.ndim == 0):
            if not np.all(np.isfinite(array)):
                raise ValueError(name + ' must be finite')
            if np.issubdtype(np.dtype(dtype), np.integer):
                limits = np.iinfo(dtype)
                if np.any(array != np.floor(array)) or np.any(array < limits.min) or np.any(array > limits.max):
                    raise ValueError(name + ' must fit its integer representation')
            return array.astype(dtype) if vector else np.dtype(dtype).type(value)
        if vector:
            return normalize_vector(value, count, name, source_count=source_count,
                                    survivor_mask=survivor_mask)
        return normalize_scalar(value, count, name, source_count=source_count,
                                survivor_mask=survivor_mask, dtype=dtype)

    def _batch_selection(self, group=None, *, tag=None, region=None):
        if isinstance(group, BulletGroup):
            if group.pool_token is not self._group_token:
                raise ValueError('bullet group belongs to another pool')
            original = group.indices
            keep = (self.generations[original] == group.generations) & (self.data['alive'][original] != 0)
            if tag is not None:
                keep &= self.data['tag'][original] == int(tag)
            if region is not None:
                keep &= region_mask(self.data, region)[original]
        else:
            original = self._resolve_indices(group, tag=tag, region=region)
            keep = np.ones(len(original), dtype=np.bool_)
        return original, keep

    def read_bullets(self, group=None, *, tag=None, region=None, fields=None):
        names = tuple(fields or ('pos', 'vel', 'angle', 'speed', 'acc', 'speed_accel',
                                 'sprite_idx', 'tag', 'time_scale', 'lifetime'))
        allowed = {'pos', 'vel', 'angle', 'speed', 'acc', 'speed_accel',
                   'sprite_idx', 'tag', 'time_scale', 'lifetime'}
        if set(names) - allowed:
            raise ValueError('unsupported snapshot fields: ' + ', '.join(sorted(set(names) - allowed)))
        indices = self._resolve_indices(group, tag=tag, region=region)
        captured = self.capture_group(indices)
        return BulletSnapshot(captured, {name: self.data[name][captured.indices] for name in names})

    def transform_bullets(
        self, group=None, *, tag=None, region=None, speed=None, angle=None,
        aim=None, speed_accel=None, time_scale=None, sprite_id=None,
        render_scale=None, cooldown=0.0, cooldown_key=None, positions=None,
        velocities=None, vector_accel=None, sprite_indices=None, motion_angular_accel=None,
    ) -> int:
        """Apply one batch operation. Angles are radians; cooldown is seconds.

        Each cooldown key represents one independent region/rule.  It never
        installs per-bullet callbacks or publishes per-bullet events.
        """
        original, keep = self._batch_selection(group, tag=tag, region=region)
        if sprite_id is not None and sprite_indices is not None:
            raise ValueError('sprite_id and sprite_indices cannot both be set')
        if velocities is not None and (speed is not None or angle is not None or aim is not None):
            raise ValueError('velocities cannot be combined with speed, angle or aim')
        if not math.isfinite(cooldown) or cooldown < 0:
            raise ValueError('bullet cooldown must be non-negative seconds')
        if cooldown > 0 and cooldown_key is None:
            raise ValueError('bullet cooldown requires an independent cooldown_key')
        target = None
        if aim is not None:
            if isinstance(aim, str) and aim == 'player':
                target = self._player_target
            elif isinstance(aim, (tuple, list)) and len(aim) == 2:
                target = tuple(float(value) for value in aim)
                if not all(math.isfinite(value) for value in target):
                    raise ValueError('bullet aim target must be finite')
            else:
                raise ValueError("aim must be 'player' or (x, y)")
        sprite_idx = self.register_sprite(sprite_id) if sprite_id is not None else None
        if cooldown > 0:
            if cooldown_key not in self._cooldowns:
                self._cooldowns[cooldown_key] = np.zeros(self.max_bullets, dtype=np.float64)
            deadlines = self._cooldowns[cooldown_key]
            keep &= deadlines[original] <= self._clock + 1e-9
        indices = original[keep]
        updates = {'speed': speed, 'angle': angle, 'speed_accel': speed_accel,
                   'time_scale': time_scale, 'render_scale': render_scale,
                   'pos': positions, 'vel': velocities, 'acc': vector_accel,
                   'sprite_idx': sprite_indices, 'motion_angular_accel': motion_angular_accel}
        updates = {
            name: self._batch_parameter(value, len(indices), name, source_count=len(original),
                                       survivor_mask=keep, vector=name in {'pos', 'vel', 'acc'},
                                       dtype=np.uint16 if name == 'sprite_idx' else np.float32)
            for name, value in updates.items() if value is not None
        }
        for name in ('speed', 'time_scale', 'render_scale'):
            if name in updates and np.any(updates[name] < 0):
                raise ValueError('invalid bullet transform ' + name)
        if cooldown > 0:
            deadlines[indices] = self._clock + cooldown
        for name, value in updates.items():
            self.data[name][indices] = value
        if velocities is not None:
            velocity = self.data['vel'][indices]
            self.data['speed'][indices] = np.hypot(velocity[:, 0], velocity[:, 1])
            moving = indices[self.data['speed'][indices] > 0]
            self.data['angle'][moving] = np.arctan2(self.data['vel'][moving, 1], self.data['vel'][moving, 0])
        if target is not None:
            positions = self.data['pos'][indices]
            self.data['angle'][indices] = np.arctan2(target[1] - positions[:, 1],
                                                   target[0] - positions[:, 0])
        if sprite_idx is not None:
            self.data['sprite_idx'][indices] = sprite_idx
        if speed is not None or angle is not None or target is not None:
            angles = self.data['angle'][indices]
            speeds = self.data['speed'][indices]
            self.data['vel'][indices, 0] = np.cos(angles) * speeds
            self.data['vel'][indices, 1] = np.sin(angles) * speeds
        locked = indices[(self.data['flags'][indices] & FLAG_RENDER_ANGLE_LOCKED) != 0]
        self.data['render_angle'][locked] = self.data['angle'][locked]
        return len(indices)

    def remove_bullets(self, group=None, *, tag=None, reason='phase_cleared') -> int:
        """Terminate and recycle a batch immediately, with an explicit reason."""
        indices = self._resolve_indices(group, tag=tag)
        mask = np.zeros(self.max_bullets, dtype=np.bool_)
        mask[indices] = True
        self._clear_mask_now(mask, reason=str(reason))
        return len(indices)

    def set_player_target(self, x: float, y: float) -> None:
        self._player_target = (float(x), float(y))

    def warmup(self) -> dict[str, float]:
        """Prepare JIT signatures on empty arrays before the gameplay loop.

        Returns first-call milliseconds (compilation OR cache loading).  No
        bullets, generations, counters or configured stages are modified.
        """
        from time import perf_counter

        data = self.data[:0]
        stages = np.empty(0, dtype=np.int32)
        elapsed = np.empty(0, dtype=np.float64)
        entered = np.empty(0, dtype=np.bool_)
        bounces = np.empty(0, dtype=np.int16)
        table = np.empty(0, dtype=STAGE_DTYPE)
        times = {}
        start = perf_counter()
        _update_bullets_optimized(data, 1.0 / 60.0, None, None)
        times['motion_default_ms'] = (perf_counter() - start) * 1000.0
        start = perf_counter()
        _update_bullets_optimized(data, 1.0 / 60.0, bounces, bounces)
        times['motion_behavior_ms'] = (perf_counter() - start) * 1000.0
        start = perf_counter()
        advance_stages(data, table, stages, stages, elapsed, entered,
                       bounces, bounces, 1.0 / 60.0, 0.0, 0.0, None, None)
        times['stage_ms'] = (perf_counter() - start) * 1000.0
        start = perf_counter()
        advance_stages(data, table, stages, stages, elapsed, entered,
                       bounces, bounces, 1.0 / 60.0, 0.0, 0.0, bounces, bounces)
        _update_bullets_optimized(data, 1.0 / 60.0, bounces, bounces, False)
        post_bounds(data, bounces, bounces)
        times['wrap_ms'] = (perf_counter() - start) * 1000.0
        start = perf_counter()
        region_mask(data, {'kind': 'circle', 'radius': 1.0})
        times['region_ms'] = (perf_counter() - start) * 1000.0
        points = np.empty((0, 2), dtype=np.float32)
        center = np.zeros(2, dtype=np.float32)
        eligible = np.empty(0, dtype=np.bool_)
        start = perf_counter()
        distance_acceleration(points, center, 1.0, 0.0, 0.01)
        distance_acceleration(points, center, 1.0, 0.0, 0.01, 0.1)
        times['distance_ms'] = (perf_counter() - start) * 1000.0
        start = perf_counter()
        neighbor_activation(points, points, center, 0.1, 2.2, eligible)
        neighbor_activation(points, points, center, 0.1, 2.2, eligible, 0.01)
        times['neighbor_ms'] = (perf_counter() - start) * 1000.0
        start = perf_counter()
        self.prepare_render_data_sorted()
        times['render_prepare_ms'] = (perf_counter() - start) * 1000.0
        return times

    def set_bullet_behavior(self, group=None, *, tag=None, stages) -> int:
        """Replace movement with a shared stage table; no Python bullet tasks."""
        rows = compile_stages(stages, self.register_sprite)
        indices = self._resolve_indices(group, tag=tag)
        if not len(indices):
            return 0
        if self._wrap_remaining_x is None and (np.any(rows['wrap_x'] > 0) or np.any(rows['wrap_y'] > 0)):
            self._wrap_remaining_x = np.full(self.max_bullets, -1, dtype=np.int16)
            self._wrap_remaining_y = np.full(self.max_bullets, -1, dtype=np.int16)
        if self._behavior_stage is None:
            self._behavior_stage = np.full(self.max_bullets, -1, dtype=np.int32)
            self._behavior_end = np.zeros(self.max_bullets, dtype=np.int32)
            self._behavior_elapsed = np.zeros(self.max_bullets, dtype=np.float64)
            self._behavior_entered = np.zeros(self.max_bullets, dtype=np.bool_)
            self._bounce_remaining_x = np.full(self.max_bullets, -1, dtype=np.int16)
            self._bounce_remaining_y = np.full(self.max_bullets, -1, dtype=np.int16)
        self._release_behavior_state(indices)
        if not self._behavior_count:
            self._behavior_table = np.empty(0, dtype=STAGE_DTYPE)
            self._behavior_programs.clear()
            self._behavior_gc_at = 128
        elif len(self._behavior_programs) >= self._behavior_gc_at:
            self._compact_behavior_programs()
        key = rows.tobytes()
        if key not in self._behavior_programs:
            start = len(self._behavior_table)
            self._behavior_table = np.concatenate((self._behavior_table, rows))
            self._behavior_programs[key] = (start, start + len(rows))
        start, end = self._behavior_programs[key]
        self._behavior_stage[indices] = start
        self._behavior_end[indices] = end
        self._behavior_elapsed[indices] = 0.0
        self._behavior_entered[indices] = False
        self._behavior_count += len(indices)
        # A replacement does not accidentally retain curves/old acceleration.
        self.data['curve_type'][indices] = CURVE_NONE
        self.data['acc'][indices] = 0.0
        self.data['friction'][indices] = 0.0
        self.data['speed_accel'][indices] = 0.0
        self.data['motion_angular_vel'][indices] = 0.0
        self.data['motion_angular_accel'][indices] = 0.0
        polar = indices[(self.data['flags'][indices] & FLAG_IS_POLAR) != 0]
        for index in polar.tolist():
            self.polar_motions.pop(index, None)
        self.data['flags'][indices] &= np.uint16(65535 ^ FLAG_IS_POLAR)
        return len(indices)

    def _compact_behavior_programs(self):
        """Drop unused shared definitions during assignment, never each tick."""
        active = self._behavior_stage >= 0
        active_ends = set(np.unique(self._behavior_end[active]).tolist())
        old_ends = self._behavior_end.copy()
        rows = []
        programs = {}
        position = 0
        for key, (start, end) in self._behavior_programs.items():
            if end not in active_ends:
                continue
            rows.append(self._behavior_table[start:end])
            selected = active & (old_ends == end)
            self._behavior_stage[selected] += position - start
            self._behavior_end[selected] = position + end - start
            programs[key] = (position, position + end - start)
            position += end - start
        self._behavior_table = np.concatenate(rows) if rows else np.empty(0, dtype=STAGE_DTYPE)
        self._behavior_programs = programs
        self._behavior_gc_at = max(128, len(programs) * 2)

    def spawn_emitter(self, x: float, y: float, angle: float, speed: float,
                      callback: Callable, **kwargs) -> int:
        """
        生成发射器节点（不渲染、不碰撞，有运动轨迹和每帧回调）

        callback 签名: callback(pool, idx, x, y, lifetime)
        """
        kwargs['flags'] = kwargs.get('flags', FLAG_RENDER_ANGLE_LOCKED) | FLAG_IS_EMITTER
        idx = self.spawn_bullet(x, y, angle, speed, **kwargs)
        if idx >= 0:
            self.emitter_callbacks[idx] = callback
        return idx

    def _update_emitters(self):
        """驱动所有发射器回调"""
        to_remove = []
        for idx, cb in self.emitter_callbacks.items():
            if self.data['alive'][idx] == 0:
                to_remove.append(idx)
                continue
            x = float(self.data['pos'][idx][0])
            y = float(self.data['pos'][idx][1])
            lt = float(self.data['lifetime'][idx])
            cb(self, idx, x, y, lt)
        for idx in to_remove:
            del self.emitter_callbacks[idx]

    # ===== Tag 系统 =====

    def _clear_mask_now(
        self,
        mask,
        *,
        reason: str = "phase_cleared",
        record: bool = True,
    ) -> np.ndarray:
        """Clear alive bullets matching mask and return their positions."""
        indices = np.where(mask)[0].astype(np.intp)
        if indices.size == 0:
            return np.zeros((0, 2), dtype=np.float32)

        positions = self.data['pos'][indices].copy()
        if record:
            self._record_lifecycle(indices, reason=reason)
            self._queue_termination_batch_reaction(indices, reason)
        self.data['alive'][indices] = 0
        self.collision_eligible[indices] = False
        self._release_behavior_state(indices)
        self.data['time_scale'][indices] = 1.0
        self.last_alive[indices] = 0

        # ``free_indices`` is a stack whose pop order is the observable pool
        # order for deterministic replays.  Append released slots in reverse
        # index order so a cleared contiguous burst is allocated low-to-high
        # again on the next replay instead of appearing reversed in a mask.
        self.free_indices.extend(indices[::-1].tolist())
        self._clear_sparse_state(indices)

        return positions

    def clear_by_tag(self, tag: int, *, reason: str = "phase_cleared") -> int:
        """按标签消除所有子弹"""
        mask = (self.data['alive'] == 1) & (self.data['tag'] == tag)
        count = int(np.count_nonzero(mask))
        self._clear_mask_now(mask, reason=reason)
        return count

    def translate_by_tag(self, tag: int, dx: float, dy: float) -> int:
        """Translate alive bullets owned by ``tag`` with one vectorized write."""
        if not math.isfinite(dx) or not math.isfinite(dy):
            raise ValueError("translation must be finite")
        mask = (self.data['alive'] == 1) & (self.data['tag'] == tag)
        count = int(np.count_nonzero(mask))
        if count:
            self.data['pos'][mask, 0] += dx
            self.data['pos'][mask, 1] += dy
        return count

    def cancel_for_bomb(self, protected_tags=None) -> np.ndarray:
        """Cancel all bomb-clearable bullets and return canceled positions."""
        tags = BOMB_PROTECTED_TAGS if protected_tags is None else protected_tags
        alive = self.data['alive'] == 1
        emitters = (self.data['flags'] & FLAG_IS_EMITTER) != 0
        protected = np.isin(self.data['tag'], tags)
        return self._clear_mask_now(
            alive & ~emitters & ~protected,
            reason="bomb_cancelled",
        )

    def set_time_scale_by_tag(self, tag: int, time_scale: float):
        """按标签设置时间缩放"""
        mask = (self.data['alive'] == 1) & (self.data['tag'] == tag)
        self.data['time_scale'][mask] = time_scale

    def set_global_time_scale(self, time_scale: float):
        """设置全部子弹的时间缩放"""
        mask = self.data['alive'] == 1
        self.data['time_scale'][mask] = time_scale

    # ===== 销毁 =====

    def kill_bullet(
        self,
        idx: int,
        handler: Callable = None,
        *,
        reason: str = "hit_destroyed",
    ):
        """杀死子弹"""
        if 0 <= idx < self.max_bullets and self.data['alive'][idx]:
            # Explicit hit/cancel operations happen before the next pool
            # update, so record the fact now.  The update collector will see
            # ``alive == 0`` in its baseline and therefore cannot duplicate
            # this batch.
            self._record_lifecycle(np.asarray([idx], dtype=np.intp), reason=str(reason))
            self._queue_termination_batch_reaction(np.asarray([idx], dtype=np.intp), str(reason))
            self.data['alive'][idx] = 0
            self.collision_eligible[idx] = False
            self._release_behavior_state(np.asarray([idx], dtype=np.intp))
            self.last_alive[idx] = 0
            self.polar_motions.pop(int(idx), None)
            self.emitter_callbacks.pop(idx, None)

            original_handler = self.death_handlers.pop(idx, None)
            if handler is None:
                handler = original_handler

            x, y = self.data['pos'][idx]
            if handler is not None:
                self.death_queue.append(DeathEvent(idx, x, y, handler))
            self.free_indices.append(int(idx))

    # ===== 主更新 =====

    def update(self, dt: float):
        """更新所有子弹"""
        self._clock += dt
        self.last_alive[:] = self.data['alive']
        self.collision_eligible[:] = self.last_alive != 0
        self._in_update = True
        try:
            if self._behavior_count:
                self._behavior_count, wrapping = advance_stages(
                    self.data, self._behavior_table, self._behavior_stage,
                    self._behavior_end, self._behavior_elapsed, self._behavior_entered,
                    self._bounce_remaining_x, self._bounce_remaining_y, dt,
                    self._player_target[0], self._player_target[1],
                    self._wrap_remaining_x, self._wrap_remaining_y,
                )
                self._wrap_live_count = max(self._wrap_live_count, wrapping)
            if self._wrap_live_count:
                _update_bullets_optimized(self.data, dt, self._bounce_remaining_x,
                                          self._bounce_remaining_y, False)
                self._wrap_live_count = post_bounds(self.data, self._wrap_remaining_x,
                                                    self._wrap_remaining_y)
            else:
                _update_bullets_optimized(self.data, dt, self._bounce_remaining_x,
                                          self._bounce_remaining_y)
            self._update_polar_motions(dt)
            self._update_emitters()
            self._collect_deaths()
            self._process_termination_batch_reactions()
            self._process_death_queue()
            self._process_spawn_queue()
        finally:
            self._in_update = False

    def _collect_deaths(self):
        died_mask = (self.last_alive == 1) & (self.data['alive'] == 0)
        died_indices = np.where(died_mask)[0]

        if died_indices.size:
            self._record_classified_deaths(died_indices)
            self.collision_eligible[died_indices] = False
            self._release_behavior_state(died_indices)
        else:
            return

        self.free_indices.extend(died_indices.tolist())
        # Formal batches need no Python work per dead bullet.  Only explicitly
        # opted-in legacy sparse handlers/motions are cleaned individually.
        for idx in tuple(self.death_handlers):
            if self.data['alive'][idx] == 0:
                handler = self.death_handlers.pop(idx)
                x, y = self.data['pos'][idx]
                self.death_queue.append(DeathEvent(idx, x, y, handler))
        for mapping in (self.polar_motions, self.emitter_callbacks, self._termination_reasons):
            for idx in tuple(mapping):
                if self.data['alive'][idx] == 0:
                    mapping.pop(idx, None)

    def _process_death_queue(self):
        for event in self.death_queue:
            if event.handler:
                event.handler(self, event)
        self.death_queue.clear()

    def _record_lifecycle(
        self,
        indices,
        *,
        reason: str | None,
        event_type: str = "bullet.terminated",
    ) -> None:
        """Append one bounded batch fact for ``indices``.

        The pool stores only a small representative sample.  Consumers that
        need every position must use a vectorized action over the owner/tag,
        not a Python callback per element.
        """

        values = np.asarray(indices, dtype=np.intp)
        if values.size == 0:
            return
        tags = self.data['tag'][values]
        # A single clear operation may contain multiple owners.  Split by the
        # typed tag while keeping each group as one batch record.
        for tag in np.unique(tags):
            group = values[tags == tag]
            sample = group[:8]
            positions = tuple(
                (float(self.data['pos'][int(index), 0]), float(self.data['pos'][int(index), 1]))
                for index in sample
            )
            owner = None if int(tag) == 0 else str(int(tag))
            self.lifecycle_batches.append(
                LifecycleBatch(
                    event_type=event_type,
                    source="bullet_pool",
                    owner=owner,
                    reason=reason,
                    count=int(group.size),
                    representative_ids=tuple(str(int(index)) for index in sample),
                    representative_positions=positions,
                    payload={"tag": int(tag)},
                )
            )

    def register_termination_batch_reaction(self, tag: int, spec: Dict[str, Any]) -> None:
        """Register one vectorized owner reaction, never one callback per bullet."""
        data = dict(spec)
        if data.get("action") != "split":
            raise ValueError("only the built-in split batch action is supported")
        count = data.get("count", 0)
        speed = data.get("speed", 0.0)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 256:
            raise ValueError("split count must be an integer in 1..256")
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or speed < 0:
            raise ValueError("split speed must be non-negative")
        allowed = {'action', 'count', 'speed', 'reason', 'reasons', 'child_tag',
                   'sprite_id', 'max_lifetime', 'angle_offset', 'inherit_angle'}
        if set(data) - allowed:
            raise TypeError('unknown termination reaction fields: ' + ', '.join(sorted(set(data) - allowed)))
        reasons = data.get('reasons', [data.get('reason', 'expired')])
        if isinstance(reasons, str) or not reasons or any(not isinstance(item, str) for item in reasons):
            raise ValueError('termination reasons must be a nonempty list of strings')
        data['reasons'] = tuple(reasons)
        data['child_tag'] = int(data.get('child_tag', 0))
        data['sprite_idx'] = self.register_sprite(data['sprite_id']) if data.get('sprite_id') else 0
        if not math.isfinite(float(speed)):
            raise ValueError('split speed must be finite')
        if not math.isfinite(float(data.get('angle_offset', 0.0))):
            raise ValueError('split angle_offset must be finite')
        self._termination_batch_reactions[int(tag)] = data

    def unregister_termination_batch_reaction(self, tag: int) -> None:
        self._termination_batch_reactions.pop(int(tag), None)

    def _queue_termination_batch_reaction(self, indices, reason: str) -> None:
        self.terminations.capture(self.data, indices, reason)
        if not self._termination_batch_reactions:
            return
        values = np.asarray(indices, dtype=np.intp)
        for tag in np.unique(self.data['tag'][values]):
            spec = self._termination_batch_reactions.get(int(tag))
            if spec is None or str(reason) not in spec['reasons']:
                continue
            group = values[self.data['tag'][values] == tag]
            self._termination_batch_queue.append(
                (self.data['pos'][group].copy(), self.data['angle'][group].copy(), dict(spec))
            )

    def _process_termination_batch_reactions(self) -> None:
        queue = self._termination_batch_queue
        self._termination_batch_queue = []
        for sources, source_angles, spec in queue:
            split_count = int(spec["count"])
            if sources.size == 0:
                continue
            # Limit temporary arrays to actual remaining pool capacity; a
            # large split cannot allocate N*256 unused positions.
            available = min(len(sources) * split_count, len(self.free_indices))
            if not available:
                continue
            child_index = np.arange(available, dtype=np.intp)
            source_index = child_index // split_count
            positions = sources[source_index]
            angles = np.tile(
                np.arange(split_count, dtype=np.float32)
                * (2.0 * math.pi / split_count),
                (available + split_count - 1) // split_count,
            )[:available] + float(spec.get('angle_offset', 0.0))
            if spec.get('inherit_angle', False):
                angles += source_angles[source_index]
            speeds = np.full(
                len(positions), float(spec["speed"]), dtype=np.float32
            )
            self.spawn_bullets_batch(
                positions,
                angles,
                speeds,
                tag=spec['child_tag'],
                sprite_idx=spec['sprite_idx'],
                max_lifetime=float(spec.get("max_lifetime", 0.0)),
            )

    def _record_classified_deaths(self, indices) -> None:
        values = np.asarray(indices, dtype=np.intp)
        if values.size == 0:
            return
        data = self.data
        expired = (
            (data['max_lifetime'][values] > 0.0)
            & (data['lifetime'][values] >= data['max_lifetime'][values])
        )
        outside = (
            (data['pos'][values, 0] < -1.5)
            | (data['pos'][values, 0] > 1.5)
            | (data['pos'][values, 1] < -1.5)
            | (data['pos'][values, 1] > 1.5)
        )
        explicit = (np.isin(values, tuple(self._termination_reasons))
                    if self._termination_reasons else np.zeros(values.size, dtype=bool))
        handled = np.zeros(values.size, dtype=bool)
        for reason, mask in (
            ("expired", expired),
            ("out_of_bounds", outside & ~expired),
        ):
            selected = values[mask & ~explicit]
            if selected.size:
                self._record_lifecycle(selected, reason=reason)
                self._queue_termination_batch_reaction(selected, reason)
                handled |= mask & ~explicit
        explicit_values = values[explicit]
        if explicit_values.size:
            for reason in sorted({self._termination_reasons[int(index)] for index in explicit_values}):
                selected = np.asarray(
                    [index for index in explicit_values if self._termination_reasons[int(index)] == reason],
                    dtype=np.intp,
                )
                self._record_lifecycle(selected, reason=reason)
                self._queue_termination_batch_reaction(selected, reason)
                handled |= np.isin(values, selected)
        remaining = values[~handled]
        if remaining.size:
            self._record_lifecycle(remaining, reason="hit_destroyed")
            self._queue_termination_batch_reaction(remaining, 'hit_destroyed')

    def drain_lifecycle_batches(self) -> tuple[LifecycleBatch, ...]:
        """Return and clear formal batch facts collected since the last drain."""

        values = tuple(self.lifecycle_batches)
        self.lifecycle_batches.clear()
        return values

    def _process_spawn_queue(self):
        pending = self.spawn_queue
        self.spawn_queue = []
        for req in pending:
            req.delay -= 1
            if req.delay <= 0:
                self._spawn_from_request(req)
            else:
                self.spawn_queue.append(req)

    def _spawn_from_request(self, req: SpawnRequest):
        if not self.free_indices:
            return

        idx = self.free_indices.pop()
        self._write_bullet(idx, req.x, req.y, req.angle, req.speed, req.acc,
                           req.speed_accel, req.motion_angular_accel,
                           req.sprite_idx, req.radius, req.max_lifetime,
                           req.friction, req.tag, req.time_scale, req.flags,
                           req.angular_vel, req.render_angle, req.render_scale,
                           req.curve_type, req.curve_param)

        if req.on_death:
            self.death_handlers[idx] = req.on_death
        if req.init:
            req.init(self, idx)

    # ===== 渲染数据准备（向量化优化） =====

    def prepare_render_data(self) -> Dict[int, Dict]:
        """准备渲染数据（向量化操作），过滤掉 emitter"""
        # 活跃且非 emitter
        active_mask = (self.data['alive'] == 1) & ((self.data['flags'] & FLAG_IS_EMITTER) == 0)
        active_count = np.sum(active_mask)

        if active_count == 0:
            return {}

        active_data = self.data[active_mask]

        positions = active_data['pos']
        angles = active_data['render_angle']  # v2: 使用 render_angle
        sprite_indices = active_data['sprite_idx']

        uv_array = self.sprite_registry._uv_array
        size_array = self.sprite_registry._size_array
        category_array = self.sprite_registry._category_array
        tex_idx_array = self.sprite_registry._texture_idx_array

        uvs = uv_array[sprite_indices]
        scales = size_array[sprite_indices] * active_data['render_scale'][:, None] * self._scale_factor
        categories = category_array[sprite_indices]
        tex_indices = tex_idx_array[sprite_indices]

        result = {}
        unique_tex = np.unique(tex_indices)

        for tex_idx in unique_tex:
            mask = tex_indices == tex_idx
            count = np.sum(mask)
            result[tex_idx] = {
                'positions': positions[mask],
                'angles': angles[mask],
                'uvs': uvs[mask],
                'scales': scales[mask],
                'categories': categories[mask],
                'count': count,
            }

        return result

    def prepare_render_data_sorted(self) -> List[Dict]:
        """准备按大小/纹理分组的渲染数据。

        旧实现先按纹理分组，再对每个纹理按 category 二次 boolean mask。
        弹量上来后，这会制造很多临时数组。这里用 Numba 做计数分桶，把渲染数据
        写入预分配的连续数组，再用切片描述 batch。
        """
        uv_array = self.sprite_registry._uv_array
        size_array = self.sprite_registry._size_array
        category_array = self.sprite_registry._category_array
        tex_idx_array = self.sprite_registry._texture_idx_array

        texture_count = max(1, len(self.sprite_registry._texture_paths))
        key_count = texture_count * 6
        self._ensure_render_bucket_buffers(key_count)

        batch_count, total_count = _prepare_render_data_sorted_numba(
            self.data,
            uv_array,
            size_array,
            category_array,
            tex_idx_array,
            float(self._scale_factor),
            int(texture_count),
            int(FLAG_IS_EMITTER),
            self._render_positions,
            self._render_angles,
            self._render_uvs,
            self._render_scales,
            self._render_bucket_counts,
            self._render_bucket_write_offsets,
            self._render_batch_starts,
            self._render_batch_counts,
            self._render_batch_tex,
            self._render_batch_cat,
        )
        if total_count == 0:
            return []

        result = []
        for i in range(int(batch_count)):
            start = int(self._render_batch_starts[i])
            count = int(self._render_batch_counts[i])
            end = start + count
            tex_idx = int(self._render_batch_tex[i])
            category = int(self._render_batch_cat[i])
            result.append({
                'texture_idx': tex_idx,
                'texture_path': self.sprite_registry.get_texture_path(tex_idx),
                'positions': self._render_positions[start:end],
                'angles': self._render_angles[start:end],
                'uvs': self._render_uvs[start:end],
                'scales': self._render_scales[start:end],
                'count': count,
                'category': category,
            })

        return result

    # ===== 兼容旧接口 =====

    def get_active_bullets(self):
        """兼容旧版接口：获取活跃子弹数据（过滤 emitter）"""
        active_mask = (self.data['alive'] == 1) & ((self.data['flags'] & FLAG_IS_EMITTER) == 0)
        active_data = self.data[active_mask]

        if len(active_data) == 0:
            return np.array([]), np.array([]), np.array([]), np.array([])

        positions = active_data['pos']
        colors = np.zeros((len(active_data), 3), dtype='f4')
        angles = active_data['render_angle']  # v2: render_angle

        sprite_ids = np.array([
            self.sprite_registry.get_id(idx)
            for idx in active_data['sprite_idx']
        ])

        return positions, colors, angles, sprite_ids

    def clear_all(self):
        """清空所有子弹"""
        self.scope_generation += 1
        alive = np.where(self.data['alive'] == 1)[0].astype(np.intp)
        if alive.size:
            self._record_lifecycle(alive, reason="phase_cleared")
        self.data['alive'] = 0
        # ``clear_all`` is an explicit terminal operation.  Keep the
        # vectorized death collector from re-emitting the same bullets on the
        # next update (the tag-clear path already does this per index).
        self.last_alive[:] = 0
        self.collision_eligible[:] = False
        if self._behavior_stage is not None:
            self._behavior_stage[:] = -1
            self._bounce_remaining_x[:] = -1
            self._bounce_remaining_y[:] = -1
        self._behavior_count = 0
        self._behavior_table = np.empty(0, dtype=STAGE_DTYPE)
        self._behavior_programs.clear()
        self._behavior_gc_at = 128
        self._cooldowns.clear()
        self._wrap_live_count = 0
        if self._wrap_remaining_x is not None:
            self._wrap_remaining_x[:] = -1
            self._wrap_remaining_y[:] = -1
        self.terminations.clear()
        self.spawn_queue.clear()
        self.death_queue.clear()
        self.free_indices = list(range(self.max_bullets - 1, -1, -1))
        self.death_handlers.clear()
        self._termination_reasons.clear()
        self._termination_batch_queue.clear()
        self._termination_batch_reactions.clear()
        self.polar_motions.clear()
        self.emitter_callbacks.clear()
        # 还原默认值
        self.data['time_scale'] = 1.0
        self.data['flags'] = FLAG_RENDER_ANGLE_LOCKED
        self.data['render_scale'] = 1.0

    # ===== 极坐标运动 API =====

    def _resolve_motion_center(self, center):
        if callable(center):
            center = center()
        if hasattr(center, 'x') and hasattr(center, 'y'):
            return float(center.x), float(center.y)
        if hasattr(center, 'pos'):
            return float(center.pos[0]), float(center.pos[1])
        if isinstance(center, (tuple, list)) and len(center) >= 2:
            return float(center[0]), float(center[1])
        raise ValueError(f"Unsupported polar center: {center!r}")

    def _apply_polar_motion(self, idx: int, motion: PolarMotion,
                            dt: float = None, old_pos: Tuple[float, float] = None):
        cx, cy = self._resolve_motion_center(motion.center)
        x = cx + math.cos(motion.theta) * motion.radius
        y = cy + math.sin(motion.theta) * motion.radius
        self.data['pos'][idx] = (x, y)

        if dt is not None and dt > 1e-8 and old_pos is not None:
            vx = (x - old_pos[0]) / dt
            vy = (y - old_pos[1]) / dt
        else:
            vx = math.cos(motion.theta) * motion.radial_speed - math.sin(motion.theta) * motion.radius * motion.angular_velocity
            vy = math.sin(motion.theta) * motion.radial_speed + math.cos(motion.theta) * motion.radius * motion.angular_velocity

        speed = math.sqrt(vx * vx + vy * vy)
        self.data['speed'][idx] = speed

        if motion.render_mode == 'radial':
            angle = math.atan2(y - cy, x - cx) + motion.angle_offset
        elif motion.render_mode == 'inward':
            angle = math.atan2(cy - y, cx - x) + motion.angle_offset
        elif motion.render_mode == 'fixed':
            angle = motion.angle_offset
        else:
            angle = math.atan2(vy, vx) if speed > 1e-8 else self.data['angle'][idx]

        self.data['angle'][idx] = angle
        self.data['render_angle'][idx] = angle
        self.data['vel'][idx] = (0.0, 0.0)

    def attach_polar_motion(self, idx: int, center, orbit_radius: float, theta: float,
                            radial_speed: float = 0.0, angular_velocity: float = 0.0,
                            render_mode: str = 'velocity', angle_offset: float = 0.0):
        motion = PolarMotion(
            center=center, radius=orbit_radius, theta=theta,
            radial_speed=radial_speed, angular_velocity=angular_velocity,
            render_mode=render_mode, angle_offset=angle_offset,
        )
        self.polar_motions[int(idx)] = motion
        self.data['acc'][idx] = (0.0, 0.0)
        self.data['flags'][idx] |= 0x0010  # FLAG_IS_POLAR
        self._apply_polar_motion(int(idx), motion)

    def spawn_polar_bullet(self, center, orbit_radius: float, theta: float,
                           radial_speed: float = 0.0, angular_velocity: float = 0.0,
                           sprite_id: str = '', delay: int = 0, init: Callable = None,
                           on_death: Callable = None, max_lifetime: float = 0.0,
                           hit_radius: float = 0.0, render_mode: str = 'velocity',
                           angle_offset: float = 0.0, **kwargs) -> int:
        cx, cy = self._resolve_motion_center(center)
        x = cx + math.cos(theta) * orbit_radius
        y = cy + math.sin(theta) * orbit_radius

        def _init(pool, idx):
            pool.attach_polar_motion(
                idx, center=center, orbit_radius=orbit_radius, theta=theta,
                radial_speed=radial_speed, angular_velocity=angular_velocity,
                render_mode=render_mode, angle_offset=angle_offset
            )
            if init:
                init(pool, idx)

        return self.spawn_bullet(
            x=x, y=y, angle=theta, speed=0.0,
            sprite_id=sprite_id, delay=delay,
            init=_init, on_death=on_death,
            max_lifetime=max_lifetime, radius=hit_radius,
            acc=(0.0, 0.0), **kwargs,
        )

    def _update_polar_motions(self, dt: float):
        if not self.polar_motions:
            return

        to_remove = []
        for idx, motion in list(self.polar_motions.items()):
            if idx < 0 or idx >= self.max_bullets or self.data['alive'][idx] == 0:
                to_remove.append(idx)
                continue

            local_dt = dt * float(self.data['time_scale'][idx])
            old_pos = (float(self.data['pos'][idx][0]), float(self.data['pos'][idx][1]))
            motion.theta += motion.angular_velocity * local_dt
            motion.radius += motion.radial_speed * local_dt
            self._apply_polar_motion(idx, motion, dt=local_dt, old_pos=old_pos)

            x, y = self.data['pos'][idx]
            if x < -1.5 or x > 1.5 or y < -1.5 or y > 1.5:
                self.data['alive'][idx] = 0
                to_remove.append(idx)

        for idx in to_remove:
            self.polar_motions.pop(int(idx), None)


# ============= Numba JIT 优化函数 =============

@njit(cache=True)
def _prepare_render_data_sorted_numba(
    data,
    uv_array,
    size_array,
    category_array,
    tex_idx_array,
    scale_factor,
    texture_count,
    emitter_flag,
    positions_out,
    angles_out,
    uvs_out,
    scales_out,
    bucket_counts,
    bucket_write_offsets,
    batch_starts,
    batch_counts,
    batch_tex,
    batch_cat,
):
    key_count = texture_count * 6
    for i in range(key_count):
        bucket_counts[i] = 0

    for i in range(data.shape[0]):
        if data[i]['alive'] == 0:
            continue
        if (data[i]['flags'] & emitter_flag) != 0:
            continue
        sprite_idx = int(data[i]['sprite_idx'])
        cat = int(category_array[sprite_idx])
        tex = int(tex_idx_array[sprite_idx])
        key = cat * texture_count + tex
        if 0 <= key < key_count:
            bucket_counts[key] += 1

    write_pos = 0
    batch_count = 0
    for cat in range(6):
        for tex in range(texture_count):
            key = cat * texture_count + tex
            count = bucket_counts[key]
            bucket_write_offsets[key] = write_pos
            if count > 0:
                batch_starts[batch_count] = write_pos
                batch_counts[batch_count] = count
                batch_tex[batch_count] = tex
                batch_cat[batch_count] = cat
                batch_count += 1
                write_pos += count

    for i in range(data.shape[0]):
        if data[i]['alive'] == 0:
            continue
        if (data[i]['flags'] & emitter_flag) != 0:
            continue
        sprite_idx = int(data[i]['sprite_idx'])
        cat = int(category_array[sprite_idx])
        tex = int(tex_idx_array[sprite_idx])
        key = cat * texture_count + tex
        if key < 0 or key >= key_count:
            continue
        dst = bucket_write_offsets[key]
        positions_out[dst, 0] = data[i]['pos'][0]
        positions_out[dst, 1] = data[i]['pos'][1]
        angles_out[dst] = data[i]['render_angle']
        uvs_out[dst, 0] = uv_array[sprite_idx, 0]
        uvs_out[dst, 1] = uv_array[sprite_idx, 1]
        uvs_out[dst, 2] = uv_array[sprite_idx, 2]
        uvs_out[dst, 3] = uv_array[sprite_idx, 3]
        render_scale = data[i]['render_scale']
        scales_out[dst, 0] = size_array[sprite_idx, 0] * render_scale * scale_factor
        scales_out[dst, 1] = size_array[sprite_idx, 1] * render_scale * scale_factor
        bucket_write_offsets[key] = dst + 1

    return batch_count, write_pos


@njit(cache=True)
def _update_bullets_optimized(data, dt, bounce_remaining_x=None, bounce_remaining_y=None,
                              cull_outside=True):
    """
    v2 子弹更新内核（Numba JIT）

    新增处理：time_scale, friction, render_angle/angular_vel,
    bounce, curve, emitter 边界豁免
    """
    n = len(data)
    for i in range(n):
        if data[i]['alive'] == 0:
            continue

        # 每子弹独立时间缩放
        ts = data[i]['time_scale']
        local_dt = dt * ts

        # 极坐标子弹由 _update_polar_motions 驱动，跳过 JIT 内核中的位置更新
        flags = data[i]['flags']
        if flags & 16:  # FLAG_IS_POLAR
            data[i]['lifetime'] += local_dt
            if data[i]['max_lifetime'] > 0.0 and data[i]['lifetime'] >= data[i]['max_lifetime']:
                data[i]['alive'] = 0
            continue

        data[i]['lifetime'] += local_dt

        # 生命周期检查
        max_life = data[i]['max_lifetime']
        if max_life > 0.0 and data[i]['lifetime'] >= max_life:
            data[i]['alive'] = 0
            continue

        # ---- 内置数学曲线 ----
        ct = data[i]['curve_type']
        if ct > 0:
            amp = data[i]['curve_param'][0]
            freq = data[i]['curve_param'][1]
            phase = data[i]['curve_param'][2]
            base = data[i]['curve_param'][3]
            t = data[i]['lifetime']
            if ct == 1:    # SIN_SPEED
                data[i]['speed'] = base + amp * math.sin(freq * t + phase)
            elif ct == 2:  # SIN_ANGLE
                data[i]['angle'] += amp * math.sin(freq * t + phase) * local_dt
            elif ct == 3:  # COS_SPEED
                data[i]['speed'] = base + amp * math.cos(freq * t + phase)
            elif ct == 4:  # LINEAR_SPEED
                data[i]['speed'] = base + amp * t
            elif ct == 5:  # DELAYED_TURN: amp=angular velocity, freq=delay
                if t >= freq:
                    data[i]['angle'] += amp * local_dt

        # ---- 摩擦力 / 阻尼 ----
        friction = data[i]['friction']
        if friction > 0.0:
            factor = 1.0 - friction * local_dt
            if factor < 0.0:
                factor = 0.0
            data[i]['speed'] *= factor

        # ---- 作者可见的直线运动加速度 ----
        # ``speed`` keeps the pool's historic normalized-per-frame scale;
        # ``speed_accel`` is its per-second derivative.  The context converts
        # author speed units before writing either field, so one scalar rule
        # applies identically to single and vectorized batch spawns.
        data[i]['speed'] += data[i]['speed_accel'] * local_dt
        data[i]['motion_angular_vel'] += (
            data[i]['motion_angular_accel'] * local_dt
        )
        data[i]['angle'] += data[i]['motion_angular_vel'] * local_dt

        # ---- 从 angle + speed 重建 vel（曲线/摩擦后） ----
        speed = data[i]['speed']
        angle = data[i]['angle']
        data[i]['vel'][0] = speed * math.cos(angle)
        data[i]['vel'][1] = speed * math.sin(angle)

        # ---- 加速度 ----
        data[i]['vel'][0] += data[i]['acc'][0] * local_dt
        data[i]['vel'][1] += data[i]['acc'][1] * local_dt

        # ---- 位置 ----
        data[i]['pos'][0] += data[i]['vel'][0] * local_dt
        data[i]['pos'][1] += data[i]['vel'][1] * local_dt

        # ---- 重算 speed / angle ----
        vx = data[i]['vel'][0]
        vy = data[i]['vel'][1]
        data[i]['speed'] = math.sqrt(vx * vx + vy * vy)
        if vx != 0.0 or vy != 0.0:
            data[i]['angle'] = math.atan2(vy, vx)

        # ---- 渲染角 ----
        flags = data[i]['flags']
        if flags & 8:  # RENDER_ANGLE_LOCKED
            data[i]['render_angle'] = data[i]['angle']
        else:
            data[i]['render_angle'] += data[i]['angular_vel'] * local_dt

        # ---- 边界处理 ----
        x = data[i]['pos'][0]
        y = data[i]['pos'][1]

        if flags & 1:  # BOUNCE_X
            bounced = False
            if x < -1.0:
                data[i]['vel'][0] = -data[i]['vel'][0]
                data[i]['pos'][0] = -1.0
                data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])
                bounced = True
            elif x > 1.0:
                data[i]['vel'][0] = -data[i]['vel'][0]
                data[i]['pos'][0] = 1.0
                data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])
                bounced = True
            if bounced and bounce_remaining_x is not None and bounce_remaining_x[i] > 0:
                bounce_remaining_x[i] -= 1
                if bounce_remaining_x[i] == 0:
                    data[i]['flags'] &= 65534

        if flags & 2:  # BOUNCE_Y
            bounced = False
            if y < -1.14:  # 真实屏幕底部 ≈ -1.167 (y_scale=384/448)
                data[i]['vel'][1] = -data[i]['vel'][1]
                data[i]['pos'][1] = -1.14
                data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])
                bounced = True
            elif y > 1.0:
                data[i]['vel'][1] = -data[i]['vel'][1]
                data[i]['pos'][1] = 1.0
                data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])
                bounced = True
            if bounced and bounce_remaining_y is not None and bounce_remaining_y[i] > 0:
                bounce_remaining_y[i] -= 1
                if bounce_remaining_y[i] == 0:
                    data[i]['flags'] &= 65533

        # 非反弹子弹的屏幕外消亡
        if cull_outside and not (data[i]['flags'] & 3):
            x = data[i]['pos'][0]
            y = data[i]['pos'][1]
            if x < -1.5 or x > 1.5 or y < -1.5 or y > 1.5:
                data[i]['alive'] = 0

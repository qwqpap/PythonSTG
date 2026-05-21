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

        self.free_indices = list(range(max_bullets))

        # Python 层回调
        self.death_handlers: Dict[int, Callable] = {}
        self.polar_motions: Dict[int, PolarMotion] = {}
        self.emitter_callbacks: Dict[int, Callable] = {}

        self.spawn_queue: List[SpawnRequest] = []
        self.death_queue: List[DeathEvent] = []
        self.last_alive = np.zeros(max_bullets, dtype='i4')

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
        **kwargs  # 忽略未知参数
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
        acc = acc or (0.0, 0.0)
        curve_param = curve_param or (0.0, 0.0, 0.0, 0.0)
        if render_angle is None:
            render_angle = angle

        if sprite_idx < 0:
            sprite_idx = self.register_sprite(sprite_id) if sprite_id else 0

        if delay > 0:
            self.spawn_queue.append(SpawnRequest(
                x=x, y=y, angle=angle, speed=speed,
                sprite_idx=sprite_idx, delay=delay, acc=acc,
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
        self._write_bullet(idx, x, y, angle, speed, acc, sprite_idx, radius,
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

    def _write_bullet(self, idx, x, y, angle, speed, acc, sprite_idx, radius,
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

        use_indices = []
        for _ in range(available):
            use_indices.append(self.free_indices.pop())
        use_indices = np.array(use_indices, dtype='i4')
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

        if on_death:
            for idx in use_indices:
                self.death_handlers[idx] = on_death

    # ===== 发射器 (Emitter) =====

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

    def _clear_mask_now(self, mask) -> np.ndarray:
        """Clear alive bullets matching mask and return their positions."""
        indices = np.where(mask)[0].astype(np.intp)
        if indices.size == 0:
            return np.zeros((0, 2), dtype=np.float32)

        positions = self.data['pos'][indices].copy()
        self.data['alive'][indices] = 0
        self.data['time_scale'][indices] = 1.0
        self.last_alive[indices] = 0

        for idx in indices.tolist():
            idx = int(idx)
            self.death_handlers.pop(idx, None)
            self.polar_motions.pop(idx, None)
            self.emitter_callbacks.pop(idx, None)
            self.free_indices.append(idx)

        return positions

    def clear_by_tag(self, tag: int):
        """按标签消除所有子弹"""
        mask = (self.data['alive'] == 1) & (self.data['tag'] == tag)
        self._clear_mask_now(mask)

    def cancel_for_bomb(self, protected_tags=None) -> np.ndarray:
        """Cancel all bomb-clearable bullets and return canceled positions."""
        tags = BOMB_PROTECTED_TAGS if protected_tags is None else protected_tags
        alive = self.data['alive'] == 1
        emitters = (self.data['flags'] & FLAG_IS_EMITTER) != 0
        protected = np.isin(self.data['tag'], tags)
        return self._clear_mask_now(alive & ~emitters & ~protected)

    def set_time_scale_by_tag(self, tag: int, time_scale: float):
        """按标签设置时间缩放"""
        mask = (self.data['alive'] == 1) & (self.data['tag'] == tag)
        self.data['time_scale'][mask] = time_scale

    def set_global_time_scale(self, time_scale: float):
        """设置全部子弹的时间缩放"""
        mask = self.data['alive'] == 1
        self.data['time_scale'][mask] = time_scale

    # ===== 销毁 =====

    def kill_bullet(self, idx: int, handler: Callable = None):
        """杀死子弹"""
        if 0 <= idx < self.max_bullets and self.data['alive'][idx]:
            self.data['alive'][idx] = 0
            self.polar_motions.pop(int(idx), None)
            self.emitter_callbacks.pop(idx, None)

            if handler is None:
                handler = self.death_handlers.pop(idx, None)

            x, y = self.data['pos'][idx]
            self.death_queue.append(DeathEvent(idx, x, y, handler))

    # ===== 主更新 =====

    def update(self, dt: float):
        """更新所有子弹"""
        self.last_alive[:] = self.data['alive']

        _update_bullets_optimized(self.data, dt)

        self._update_polar_motions(dt)
        self._update_emitters()

        self._collect_deaths()
        self._process_death_queue()
        self._process_spawn_queue()

    def _collect_deaths(self):
        died_mask = (self.last_alive == 1) & (self.data['alive'] == 0)
        died_indices = np.where(died_mask)[0]

        for idx in died_indices:
            x, y = self.data['pos'][idx]
            handler = self.death_handlers.pop(idx, None)
            self.polar_motions.pop(int(idx), None)
            self.emitter_callbacks.pop(idx, None)
            self.death_queue.append(DeathEvent(idx, x, y, handler))
            self.free_indices.append(idx)

    def _process_death_queue(self):
        for event in self.death_queue:
            if event.handler:
                event.handler(self, event)
        self.death_queue.clear()

    def _process_spawn_queue(self):
        new_queue = []
        for req in self.spawn_queue:
            if req.delay <= 0:
                self._spawn_from_request(req)
            else:
                req.delay -= 1
                new_queue.append(req)
        self.spawn_queue = new_queue

    def _spawn_from_request(self, req: SpawnRequest):
        if not self.free_indices:
            return

        idx = self.free_indices.pop()
        self._write_bullet(idx, req.x, req.y, req.angle, req.speed, req.acc,
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
        self.data['alive'] = 0
        self.spawn_queue.clear()
        self.death_queue.clear()
        self.free_indices = list(range(self.max_bullets))
        self.death_handlers.clear()
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
def _update_bullets_optimized(data, dt):
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

        # ---- 摩擦力 / 阻尼 ----
        friction = data[i]['friction']
        if friction > 0.0:
            factor = 1.0 - friction * local_dt
            if factor < 0.0:
                factor = 0.0
            data[i]['speed'] *= factor

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
            if x < -1.0:
                data[i]['vel'][0] = -data[i]['vel'][0]
                data[i]['pos'][0] = -1.0
                data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])
            elif x > 1.0:
                data[i]['vel'][0] = -data[i]['vel'][0]
                data[i]['pos'][0] = 1.0
                data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])

        if flags & 2:  # BOUNCE_Y
            if y < -1.14:  # 真实屏幕底部 ≈ -1.167 (y_scale=384/448)
                data[i]['vel'][1] = -data[i]['vel'][1]
                data[i]['pos'][1] = -1.14
                data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])
            elif y > 1.0:
                data[i]['vel'][1] = -data[i]['vel'][1]
                data[i]['pos'][1] = 1.0
                data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])

        # 非反弹子弹的屏幕外消亡
        if not (flags & 3):
            x = data[i]['pos'][0]
            y = data[i]['pos'][1]
            if x < -1.5 or x > 1.5 or y < -1.5 or y > 1.5:
                data[i]['alive'] = 0

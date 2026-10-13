import numpy as np
from numba import njit
import math

# 导入优化版本（新代码应使用这个）
from .optimized_pool import OptimizedBulletPool
from .behavior import BulletGroup
from .batch import BulletSnapshot
# 导入 flags / curve 常量（统一使用）
from .optimized_pool import (
    FLAG_BOUNCE_X, FLAG_BOUNCE_Y, FLAG_IS_EMITTER, FLAG_RENDER_ANGLE_LOCKED, FLAG_IS_POLAR,
    CURVE_NONE, CURVE_SIN_SPEED, CURVE_SIN_ANGLE, CURVE_COS_SPEED, CURVE_LINEAR_SPEED,
    CURVE_DELAYED_TURN,
)
from .tags import BOMB_PROTECTED_TAGS

__all__ = [
    'OptimizedBulletPool', 'BulletGroup', 'BulletSnapshot', 'BulletPool', 'SpawnRequest',
    'DeathEvent', 'PolarMotion', 'BOMB_PROTECTED_TAGS',
    'FLAG_BOUNCE_X', 'FLAG_BOUNCE_Y', 'FLAG_IS_EMITTER',
    'FLAG_RENDER_ANGLE_LOCKED', 'FLAG_IS_POLAR', 'CURVE_NONE',
    'CURVE_SIN_SPEED', 'CURVE_SIN_ANGLE', 'CURVE_COS_SPEED', 'CURVE_LINEAR_SPEED',
    'CURVE_DELAYED_TURN',
]

class SpawnRequest:
    """生成请求"""
    def __init__(self, x, y, angle, speed, color=None, sprite_id='', init=None,
                 delay=0, acc=None, on_death=None, max_lifetime=0.0,
                 radius=0.0, friction=0.0, tag=0, time_scale=1.0,
                 flags=FLAG_RENDER_ANGLE_LOCKED, angular_vel=0.0,
                 render_angle=None, curve_type=0, curve_param=None):
        self.x = x
        self.y = y
        self.angle = angle
        self.speed = speed
        self.color = color
        self.sprite_id = sprite_id
        self.init = init
        self.delay = delay
        self.acc = acc or (0.0, 0.0)
        self.on_death = on_death
        self.max_lifetime = max_lifetime
        self.radius = radius
        # v2
        self.friction = friction
        self.tag = tag
        self.time_scale = time_scale
        self.flags = flags
        self.angular_vel = angular_vel
        self.render_angle = render_angle if render_angle is not None else angle
        self.curve_type = curve_type
        self.curve_param = curve_param or (0.0, 0.0, 0.0, 0.0)

class DeathEvent:
    """死亡事件"""
    def __init__(self, idx, x, y, handler=None):
        self.idx = idx
        self.x = x
        self.y = y
        self.handler = handler


class PolarMotion:
    """极坐标运动描述：bullet position = center + polar(radius, theta)."""
    def __init__(self, center, orbit_radius, theta, radial_speed=0.0,
                 angular_velocity=0.0, render_mode='velocity', angle_offset=0.0):
        self.center = center
        self.radius = orbit_radius
        self.theta = theta
        self.radial_speed = radial_speed
        self.angular_velocity = angular_velocity
        self.render_mode = render_mode
        self.angle_offset = angle_offset

class BulletPool:
    def __init__(self, max_bullets=50000):
        self.max_bullets = max_bullets

        self.DEATH_NONE = 0
        self.DEATH_EXPLODE = 1

        # v2 数据结构（与 OptimizedBulletPool 对齐）
        self.dtype = np.dtype([
            ('pos', 'f4', 2),
            ('vel', 'f4', 2),
            ('acc', 'f4', 2),
            ('angle', 'f4'),
            ('render_angle', 'f4'),
            ('angular_vel', 'f4'),
            ('speed', 'f4'),
            ('alive', 'i4'),
            ('sprite_id', 'U32'),
            ('radius', 'f4'),
            ('lifetime', 'f4'),
            ('max_lifetime', 'f4'),
            ('friction', 'f4'),
            ('tag', 'i4'),
            ('time_scale', 'f4'),
            ('flags', 'u2'),
            ('curve_type', 'u1'),
            ('curve_param', 'f4', 4),
        ])

        self.death_handlers = {}
        self.data = np.zeros(max_bullets, dtype=self.dtype)
        self.data['time_scale'] = 1.0
        self.data['flags'] = FLAG_RENDER_ANGLE_LOCKED

        self.spawn_queue = []
        self.death_queue = []
        self.last_alive = np.zeros(max_bullets, dtype='i4')
        self.free_indices = list(range(max_bullets))

        # 极坐标运动 / Emitter
        self.polar_motions = {}
        self.emitter_callbacks = {}

    def spawn_bullet(self, x, y, angle, speed, color=None, sprite_id='', init=None,
                     delay=0, on_death=None, max_lifetime=0.0, radius=0.0, acc=None,
                     friction=0.0, tag=0, time_scale=1.0, flags=FLAG_RENDER_ANGLE_LOCKED,
                     angular_vel=0.0, render_angle=None, curve_type=0, curve_param=None,
                     **kwargs):
        acc = acc or (0.0, 0.0)
        curve_param = curve_param or (0.0, 0.0, 0.0, 0.0)
        if render_angle is None:
            render_angle = angle

        if delay > 0:
            self.spawn_queue.append(SpawnRequest(
                x, y, angle, speed, color, sprite_id, init, delay,
                acc, on_death, max_lifetime, radius,
                friction, tag, time_scale, flags, angular_vel,
                render_angle, curve_type, curve_param,
            ))
            return -1

        if len(self.free_indices) > 0:
            idx = self.free_indices.pop()

            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed

            d = self.data
            d['pos'][idx] = (x, y)
            d['vel'][idx] = (vx, vy)
            d['acc'][idx] = acc
            d['angle'][idx] = angle
            d['render_angle'][idx] = render_angle
            d['angular_vel'][idx] = angular_vel
            d['speed'][idx] = speed
            d['sprite_id'][idx] = sprite_id
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

            if on_death:
                self.death_handlers[idx] = on_death
            else:
                self.death_handlers.pop(idx, None)

            if init:
                init(self, idx)

            return idx
        return -1

    def spawn_pattern(self, x, y, angle, speed, count=18, angle_spread=math.pi*2,
                      sprite_id='', on_death=None, max_lifetime=0.0, radius=0.0, acc=None,
                      friction=0.0, tag=0, time_scale=1.0, flags=FLAG_RENDER_ANGLE_LOCKED):
        if count <= 0:
            return

        acc = acc or (0.0, 0.0)
        angle_step = angle_spread / count
        angles = np.array([angle + i * angle_step for i in range(count)], dtype='f4')
        vxs = np.cos(angles) * speed
        vys = np.sin(angles) * speed

        free_indices = np.flatnonzero(self.data['alive'] == 0)
        if len(free_indices) == 0:
            return

        use_indices = free_indices[:min(count, len(free_indices))]
        n = len(use_indices)

        for idx in use_indices:
            if idx in self.free_indices:
                self.free_indices.remove(idx)

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
        d['speed'][use_indices] = speed
        d['sprite_id'][use_indices] = sprite_id
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

    # ===== Emitter =====

    def spawn_emitter(self, x, y, angle, speed, callback, **kwargs):
        kwargs['flags'] = kwargs.get('flags', FLAG_RENDER_ANGLE_LOCKED) | FLAG_IS_EMITTER
        idx = self.spawn_bullet(x, y, angle, speed, **kwargs)
        if idx >= 0:
            self.emitter_callbacks[idx] = callback
        return idx

    def _update_emitters(self):
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

    def _clear_mask_now(self, mask):
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

    def clear_by_tag(self, tag):
        mask = (self.data['alive'] == 1) & (self.data['tag'] == tag)
        self._clear_mask_now(mask)

    def cancel_for_bomb(self, protected_tags=None):
        tags = BOMB_PROTECTED_TAGS if protected_tags is None else protected_tags
        alive = self.data['alive'] == 1
        emitters = (self.data['flags'] & FLAG_IS_EMITTER) != 0
        protected = np.isin(self.data['tag'], tags)
        return self._clear_mask_now(alive & ~emitters & ~protected)

    def set_time_scale_by_tag(self, tag, time_scale):
        mask = (self.data['alive'] == 1) & (self.data['tag'] == tag)
        self.data['time_scale'][mask] = time_scale

    def set_global_time_scale(self, time_scale):
        mask = self.data['alive'] == 1
        self.data['time_scale'][mask] = time_scale

    # ===== 销毁 =====

    def kill_bullet(self, idx, handler=None):
        if 0 <= idx < self.max_bullets and self.data['alive'][idx]:
            self.data['alive'][idx] = 0
            self.polar_motions.pop(int(idx), None)
            self.emitter_callbacks.pop(idx, None)

            if handler is None:
                handler = self.death_handlers.get(idx)
                if idx in self.death_handlers:
                    del self.death_handlers[idx]

            x, y = self.data['pos'][idx]
            self.death_queue.append(DeathEvent(idx, x, y, handler))

    def update(self, dt):
        self.last_alive[:] = self.data['alive']
        _update_bullets(self.data, dt)
        self._update_polar_motions(dt)
        self._update_emitters()
        self._collect_deaths()
        self._process_death_queue()
        self._process_spawn_queue()

    def _collect_deaths(self):
        died_indices = np.where((self.last_alive == 1) & (self.data['alive'] == 0))[0]

        for idx in died_indices:
            x, y = self.data['pos'][idx]
            handler = self.death_handlers.get(idx)
            if idx in self.death_handlers:
                del self.death_handlers[idx]
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

    def _spawn_from_request(self, req):
        if len(self.free_indices) > 0:
            idx = self.free_indices.pop()

            vx = math.cos(req.angle) * req.speed
            vy = math.sin(req.angle) * req.speed

            d = self.data
            d['pos'][idx] = (req.x, req.y)
            d['vel'][idx] = (vx, vy)
            d['acc'][idx] = req.acc
            d['angle'][idx] = req.angle
            d['render_angle'][idx] = req.render_angle
            d['angular_vel'][idx] = req.angular_vel
            d['speed'][idx] = req.speed
            d['sprite_id'][idx] = req.sprite_id
            d['radius'][idx] = getattr(req, 'radius', 0.01)
            d['lifetime'][idx] = 0.0
            d['max_lifetime'][idx] = req.max_lifetime
            d['friction'][idx] = req.friction
            d['tag'][idx] = req.tag
            d['time_scale'][idx] = req.time_scale
            d['flags'][idx] = req.flags
            d['curve_type'][idx] = req.curve_type
            d['curve_param'][idx] = req.curve_param
            d['alive'][idx] = 1

            if req.on_death:
                self.death_handlers[idx] = req.on_death
            else:
                self.death_handlers.pop(idx, None)

            if req.init:
                req.init(self, idx)

    def get_active_bullets(self):
        active_mask = (self.data['alive'] == 1) & ((self.data['flags'] & FLAG_IS_EMITTER) == 0)
        active_data = self.data[active_mask]

        if len(active_data) > 0:
            positions = active_data['pos']
            colors = np.zeros((len(active_data), 3), dtype='f4')
            angles = active_data['render_angle']
            sprite_ids = active_data['sprite_id']
            return positions, colors, angles, sprite_ids
        return np.array([]), np.array([]), np.array([]), np.array([])

    def clear_all(self):
        self.data['alive'] = 0
        self.spawn_queue.clear()
        self.death_queue.clear()
        self.polar_motions.clear()
        self.emitter_callbacks.clear()
        self.data['time_scale'] = 1.0
        self.data['flags'] = FLAG_RENDER_ANGLE_LOCKED

    def pre_update(self, dt):
        pass

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

    def _apply_polar_motion(self, idx, motion, dt=None, old_pos=None):
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

    def attach_polar_motion(self, idx, center, orbit_radius, theta,
                            radial_speed=0.0, angular_velocity=0.0,
                            render_mode='velocity', angle_offset=0.0):
        motion = PolarMotion(
            center=center, orbit_radius=orbit_radius, theta=theta,
            radial_speed=radial_speed, angular_velocity=angular_velocity,
            render_mode=render_mode, angle_offset=angle_offset,
        )
        self.polar_motions[int(idx)] = motion
        self.data['acc'][idx] = (0.0, 0.0)
        self.data['flags'][idx] |= FLAG_IS_POLAR
        self._apply_polar_motion(int(idx), motion)

    def spawn_polar_bullet(self, center, orbit_radius, theta,
                           radial_speed=0.0, angular_velocity=0.0,
                           color=None, sprite_id='', init=None, delay=0,
                           on_death=None, max_lifetime=0.0,
                           hit_radius=0.0, render_mode='velocity',
                           angle_offset=0.0, **kwargs):
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
            color=color, sprite_id=sprite_id,
            init=_init, delay=delay,
            on_death=on_death, max_lifetime=max_lifetime,
            radius=hit_radius, acc=(0.0, 0.0), **kwargs,
        )

    def _update_polar_motions(self, dt):
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


@njit(cache=True)
def _update_bullets(data, dt):
    """v2 子弹更新函数（与 OptimizedBulletPool 逻辑对齐）"""
    for i in range(len(data)):
        if data[i]['alive']:
            ts = data[i]['time_scale']
            local_dt = dt * ts

            data[i]['lifetime'] += local_dt

            if data[i]['max_lifetime'] > 0.0 and data[i]['lifetime'] >= data[i]['max_lifetime']:
                data[i]['alive'] = 0
                continue

            if data[i]['flags'] & 16:  # FLAG_IS_POLAR: 跳过，由 _update_polar_motions 驱动
                continue

            # 内置曲线
            ct = data[i]['curve_type']
            if ct > 0:
                amp = data[i]['curve_param'][0]
                freq = data[i]['curve_param'][1]
                phase = data[i]['curve_param'][2]
                base = data[i]['curve_param'][3]
                t = data[i]['lifetime']
                if ct == 1:
                    data[i]['speed'] = base + amp * math.sin(freq * t + phase)
                elif ct == 2:
                    data[i]['angle'] += amp * math.sin(freq * t + phase) * local_dt
                elif ct == 3:
                    data[i]['speed'] = base + amp * math.cos(freq * t + phase)
                elif ct == 4:
                    data[i]['speed'] = base + amp * t

            # 摩擦力
            friction = data[i]['friction']
            if friction > 0.0:
                factor = 1.0 - friction * local_dt
                if factor < 0.0:
                    factor = 0.0
                data[i]['speed'] *= factor

            # 从 angle+speed 重建 vel
            speed = data[i]['speed']
            angle = data[i]['angle']
            data[i]['vel'][0] = speed * math.cos(angle)
            data[i]['vel'][1] = speed * math.sin(angle)

            # 加速度
            data[i]['vel'][0] += data[i]['acc'][0] * local_dt
            data[i]['vel'][1] += data[i]['acc'][1] * local_dt

            # 位置
            data[i]['pos'][0] += data[i]['vel'][0] * local_dt
            data[i]['pos'][1] += data[i]['vel'][1] * local_dt

            # 重算
            vx, vy = data[i]['vel'][0], data[i]['vel'][1]
            data[i]['speed'] = math.sqrt(vx*vx + vy*vy)
            data[i]['angle'] = math.atan2(vy, vx)

            # 渲染角
            flags = data[i]['flags']
            if flags & 8:
                data[i]['render_angle'] = data[i]['angle']
            else:
                data[i]['render_angle'] += data[i]['angular_vel'] * local_dt

            # 边界
            x, y = data[i]['pos'][0], data[i]['pos'][1]
            if flags & 1:
                if x < -1.0:
                    data[i]['vel'][0] = -data[i]['vel'][0]
                    data[i]['pos'][0] = -1.0
                    data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])
                elif x > 1.0:
                    data[i]['vel'][0] = -data[i]['vel'][0]
                    data[i]['pos'][0] = 1.0
                    data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])
            if flags & 2:
                if y < -1.0:
                    data[i]['vel'][1] = -data[i]['vel'][1]
                    data[i]['pos'][1] = -1.0
                    data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])
                elif y > 1.0:
                    data[i]['vel'][1] = -data[i]['vel'][1]
                    data[i]['pos'][1] = 1.0
                    data[i]['angle'] = math.atan2(data[i]['vel'][1], data[i]['vel'][0])

            if not (flags & 3):
                x, y = data[i]['pos'][0], data[i]['pos'][1]
                if x < -1.5 or x > 1.5 or y < -1.5 or y > 1.5:
                    data[i]['alive'] = 0

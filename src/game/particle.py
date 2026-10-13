"""Non-colliding, fixed-step particles: shared visuals and packed numeric state.

Content uses StageContext.emit_particles. There are no particle objects, Tasks,
callbacks or references to the renderer. Simulation is one step at 60 Hz.
"""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping
import math
import time

import numpy as np
from numba import njit

from ..core.sprite_registry import get_sprite_registry


@dataclass(frozen=True)
class ParticleEffect:
    """Reusable sprite animation. All durations are simulation frames.

    Scale/alpha interpolate from their start to end values over the lifetime.
    Sprite animation holds its last frame unless loop is True. Rotation speed
    is degrees/second. Sprite names are exact catalog IDs, not bullet aliases.
    """

    sprites: tuple[str, ...]
    lifetime: int = 30
    frame_ticks: int = 1
    loop: bool = False
    scale: float | tuple[float, float] = 1.0
    scale_end: float | tuple[float, float] | None = None
    alpha: float = 1.0
    alpha_end: float = 0.0
    angular_speed: float = 0.0
    blend: str = 'alpha'
    layer: str = 'front'

    def __post_init__(self):
        object.__setattr__(self, 'sprites', (self.sprites,) if isinstance(self.sprites, str)
                           else tuple(self.sprites))
        if not self.sprites or self.lifetime < 1 or self.frame_ticks < 1:
            raise ValueError('particle sprites and positive lifetime/frame_ticks are required')
        if self.blend not in ('alpha', 'add') or self.layer not in ('back', 'front'):
            raise ValueError('particle blend must be alpha/add and layer back/front')
        for name in ('scale', 'scale_end'):
            value = getattr(self, name)
            if value is not None and not np.isscalar(value):
                object.__setattr__(self, name, tuple(value))


@dataclass(frozen=True, eq=False)
class ParticleGroup:
    """One emission's generation-safe selection, including capacity loss."""

    indices: np.ndarray = field(repr=False)
    generations: np.ndarray = field(repr=False)
    requested: int
    _pool_identity: object = field(repr=False)
    _scope: int = field(repr=False)

    @property
    def count(self):
        """Number emitted, not the number still alive."""
        return len(self.indices)

    @property
    def dropped(self):
        return self.requested - self.count


@dataclass(frozen=True, eq=False)
class ParticleSnapshot:
    """Detached read-only arrays aligned with a captured living group."""

    group: ParticleGroup
    fields: Mapping[str, np.ndarray]

    def __post_init__(self):
        values = {}
        for name, value in self.fields.items():
            array = np.array(value, copy=True, order='C')
            array.setflags(write=False)
            values[name] = array
        object.__setattr__(self, 'fields', MappingProxyType(values))

    def __getitem__(self, name):
        return self.fields[name]


@njit(cache=True)
def _step(active, count, free, free_count, alive, age, lifetime, origin,
          position, velocity, acceleration, direction, radius, radial_step, radial):
    retained = 0
    for j in range(count):
        i = active[j]
        age[i] += 1
        if not alive[i] or age[i] >= lifetime[i]:
            alive[i] = False
            free[free_count] = i
            free_count += 1
            continue
        # Explicit Euler: integrate position BEFORE changing velocity.
        for axis in range(2):
            origin[i, axis] += velocity[i, axis]
            velocity[i, axis] += acceleration[i, axis]
        if radial[i]:
            radius[i] += radial_step[i]
            for axis in range(2):
                position[i, axis] = origin[i, axis] + direction[i, axis] * radius[i]
        else:
            position[i, 0] = origin[i, 0]
            position[i, 1] = origin[i, 1]
        active[retained] = i
        retained += 1
    return retained, free_count


@njit(cache=True)
def _compact(active, count, free, free_count, alive):
    retained = 0
    for j in range(count):
        i = active[j]
        if alive[i]:
            active[retained] = i
            retained += 1
        else:
            free[free_count] = i
            free_count += 1
    return retained, free_count


@njit(cache=True)
def _pack(active, count, age, start, layer, position, rotation, color, scale,
          visual, visual_keys, output, keys):
    back_count = 0
    for j in range(count):
        if layer[active[j]] == 0:
            back_count += 1
    back, front = 0, back_count
    for j in range(count):
        i = active[j]
        frame = start[i] + age[i]
        if layer[i] == 0:
            dst = back
            back += 1
        else:
            dst = front
            front += 1
        output[dst, 0] = position[i, 0]
        output[dst, 1] = position[i, 1]
        output[dst, 2] = rotation[i] + visual[frame, 7]
        for k in range(6):
            output[dst, 3 + k] = visual[frame, k]
        output[dst, 7] *= scale[i, 0]
        output[dst, 8] *= scale[i, 1]
        for k in range(3):
            output[dst, 9 + k] = color[i, k]
        output[dst, 12] = color[i, 3] * visual[frame, 6]
        keys[dst] = visual_keys[frame]
    return back_count


class ParticlePool:
    """Independent finite pool. Full pools drop new particles, never bullets.

    Active indices are compacted in birth order, so alpha blending does not
    change when a slot is reused. Work scales with live count, not capacity.
    Shared visual tables are compiled once per immutable ParticleEffect.
    """

    def __init__(self, max_particles=8192, sprite_registry=None):
        self.max_particles = int(max_particles)
        self.sprite_registry = sprite_registry if sprite_registry is not None else get_sprite_registry()
        n = self.max_particles
        self.position = np.zeros((n, 2), np.float32)
        self._origin = np.zeros((n, 2), np.float32)
        self._velocity = np.zeros((n, 2), np.float32)
        self._acceleration = np.zeros((n, 2), np.float32)
        self._direction = np.zeros((n, 2), np.float32)
        self._radius = np.zeros(n, np.float32)
        self._radial_step = np.zeros(n, np.float32)
        self._radial = np.zeros(n, np.bool_)
        self._rotation = np.zeros(n, np.float32)
        self._color = np.ones((n, 4), np.float32)
        self._scale = np.ones((n, 2), np.float32)
        self.age = np.zeros(n, np.int32)
        self._lifetime = np.zeros(n, np.int32)
        self._start = np.zeros(n, np.int32)
        self._layer = np.zeros(n, np.uint8)
        self.alive = np.zeros(n, np.bool_)
        self._generation = np.zeros(n, np.uint64)
        self._active = np.empty(n, np.int32)
        self._free = np.arange(n, dtype=np.int32)
        self._count = 0
        self._free_count = n
        self._identity = object()
        self._scope = 0
        self._effects = {}
        self._visual = np.empty((0, 8), np.float32)
        self._visual_keys = np.empty(0, np.int32)
        self._output = np.empty((n, 13), np.float32)
        self._keys = np.empty(n, np.int32)
        self._render_dirty = True
        self._back_count = 0

    @property
    def count(self):
        return self._count

    @staticmethod
    def _values(value, shape, name):
        try:
            values = np.broadcast_to(np.asarray(value, dtype=np.float32), shape)
        except ValueError as exc:
            raise ValueError(f'{name} must broadcast to {shape}') from exc
        if not np.isfinite(values).all():
            raise ValueError(f'{name} must be finite')
        return values

    def _compile_effect(self, effect):
        cached = self._effects.get(effect)
        if cached is not None:
            return cached
        if len(self._effects) >= 256 or len(self._visual) + effect.lifetime > 65536:
            raise RuntimeError('particle visual capacity exceeded; reuse effects or clear the stage')
        frames = []
        for name in effect.sprites:
            if name not in self.sprite_registry:
                raise ValueError(f'unknown particle sprite: {name}')
            idx = self.sprite_registry.get_index(name)
            info = self.sprite_registry.get_info(idx)
            if info is None or not info.texture_path:
                raise ValueError(f'particle sprite has no texture: {name}')
            frames.append(idx)
        ticks = np.arange(effect.lifetime, dtype=np.int32)
        animation = ticks // effect.frame_ticks
        animation = animation % len(frames) if effect.loop else np.minimum(animation, len(frames) - 1)
        sprites = np.asarray(frames, dtype=np.int32)[animation]
        progress = ticks.astype(np.float32) / max(1, effect.lifetime - 1)
        first = self._values(effect.scale, (2,), 'scale')
        last = self._values(effect.scale if effect.scale_end is None else effect.scale_end, (2,), 'scale_end')
        table = np.empty((effect.lifetime, 8), np.float32)
        table[:, :4] = self.sprite_registry.get_uv_array()[sprites]
        table[:, 4:6] = self.sprite_registry.get_size_array()[sprites] * (
            first + (last - first) * progress[:, None])
        table[:, 6] = effect.alpha + (effect.alpha_end - effect.alpha) * progress
        table[:, 7] = ticks * (math.radians(effect.angular_speed) / 60.0)
        if not np.isfinite(table).all():
            raise ValueError('particle visual parameters must be finite')
        textures = np.asarray([self.sprite_registry.get_texture_index(int(i)) for i in frames], np.int32)
        keys = textures[animation] * 2 + int(effect.blend == 'add')
        cached = (len(self._visual), int(effect.layer == 'front'))
        self._visual = np.concatenate((self._visual, table))
        self._visual_keys = np.concatenate((self._visual_keys, keys))
        self._effects[effect] = cached
        return cached

    def emit(self, effect, x, y, *, count=1, velocity=(0.0, 0.0),
             acceleration=(0.0, 0.0), rotation=0.0, color=(1.0, 1.0, 1.0, 1.0),
             motion='linear', radius=0.0, radial_speed=0.0, direction=0.0):
        """Batch emission in author units (units/s, units/s², degrees).

        x/y and scalar fields broadcast to count; velocity/acceleration/color
        accept a constant vector or count-by-dimension array. Radial motion
        uses x/y as centers and direction as degrees, without clamping radius.
        """
        count = int(count)
        if count < 0 or motion not in ('linear', 'radial'):
            raise ValueError('particle count must be nonnegative; motion linear/radial')
        xs = self._values(x, (count,), 'x')
        ys = self._values(y, (count,), 'y')
        vel = self._values(velocity, (count, 2), 'velocity') / 60.0
        acc = self._values(acceleration, (count, 2), 'acceleration') / 3600.0
        rot = np.deg2rad(self._values(rotation, (count,), 'rotation'))
        colors = self._values(color, (count, 4), 'color')
        radii = self._values(radius, (count,), 'radius')
        dr = self._values(radial_speed, (count,), 'radial_speed') / 60.0
        headings = np.deg2rad(self._values(direction, (count,), 'direction'))
        start, layer = self._compile_effect(effect)
        n = min(count, self._free_count)
        indices = self._free[self._free_count - n:self._free_count].copy()
        self._free_count -= n
        self._active[self._count:self._count + n] = indices
        self._count += n
        self._origin[indices, 0], self._origin[indices, 1] = xs[:n], ys[:n]
        self.position[indices] = self._origin[indices]
        self._velocity[indices], self._acceleration[indices] = vel[:n], acc[:n]
        self._rotation[indices], self._color[indices] = rot[:n], colors[:n]
        self._scale[indices] = 1.0
        self._radius[indices], self._radial_step[indices] = radii[:n], dr[:n]
        self._radial[indices] = motion == 'radial'
        self._direction[indices, 0], self._direction[indices, 1] = np.cos(headings[:n]), np.sin(headings[:n])
        if motion == 'radial':
            self.position[indices] += self._direction[indices] * radii[:n, None]
        self._start[indices], self._layer[indices] = start, layer
        self.age[indices], self._lifetime[indices] = 0, effect.lifetime
        self.alive[indices] = True
        self._generation[indices] += 1
        generations = self._generation[indices].copy()
        indices.setflags(write=False)
        generations.setflags(write=False)
        self._render_dirty = True
        return ParticleGroup(indices, generations, count, self._identity, self._scope)

    def _resolve(self, group):
        if group._pool_identity is not self._identity or group._scope != self._scope:
            return np.empty(0, np.int32)
        indices = group.indices
        return indices[self.alive[indices] & (self._generation[indices] == group.generations)]

    def count_group(self, group):
        return len(self._resolve(group))

    def read(self, group=None):
        """Whole-group snapshots, never writable pool slots or Python objects."""
        indices = self._active[:self._count].copy() if group is None else self._resolve(group)
        generations = self._generation[indices].copy()
        indices.setflags(write=False)
        generations.setflags(write=False)
        selection = ParticleGroup(indices, generations, len(indices), self._identity, self._scope)
        return ParticleSnapshot(selection, {
            'position': self.position[indices], 'age': self.age[indices],
            'velocity': self._velocity[indices] * 60.0,
            'acceleration': self._acceleration[indices] * 3600.0,
            'rotation': np.rad2deg(self._rotation[indices]),
            'color': self._color[indices], 'scale': self._scale[indices],
        })

    def transform(self, group, *, position=None, velocity=None, acceleration=None,
                  rotation=None, color=None, scale=None):
        """Apply vectorized formulas with original-row alignment after waits.

        Only still-living generations are changed. Scale is a multiplier on
        the shared effect's animated scale. Age/lifetime remain pool-owned.
        """
        if group._pool_identity is not self._identity or group._scope != self._scope:
            return 0
        indices = group.indices
        living = self.alive[indices] & (self._generation[indices] == group.generations)
        selected = indices[living]
        if not len(selected):
            return 0
        changes = {}
        for name, value, dimension in (
            ('position', position, 2), ('velocity', velocity, 2),
            ('acceleration', acceleration, 2), ('rotation', rotation, 0),
            ('color', color, 4), ('scale', scale, 2),
        ):
            if value is not None:
                shape = (len(indices), dimension) if dimension else (len(indices),)
                changes[name] = self._values(value, shape, name)[living]
        for name, values in changes.items():
            if name == 'position':
                self.position[selected] = values
                self._origin[selected] = values - (
                    self._direction[selected] * self._radius[selected, None]
                    * self._radial[selected, None])
            elif name == 'velocity':
                self._velocity[selected] = values / 60.0
            elif name == 'acceleration':
                self._acceleration[selected] = values / 3600.0
            elif name == 'rotation':
                self._rotation[selected] = np.deg2rad(values)
            elif name == 'color':
                self._color[selected] = values
            else:
                self._scale[selected] = values
        self._render_dirty = True
        return len(selected)

    def clear(self, group=None):
        if group is None:
            removed = self._count
            self.alive.fill(False)
            self._free[:] = np.arange(self.max_particles, dtype=np.int32)
            self._count, self._free_count = 0, self.max_particles
            self._scope += 1
            self._effects.clear()
            self._visual = np.empty((0, 8), np.float32)
            self._visual_keys = np.empty(0, np.int32)
        else:
            indices = self._resolve(group)
            removed = len(indices)
            if not removed:
                return 0
            self.alive[indices] = False
            self._count, self._free_count = _compact(
                self._active, self._count, self._free, self._free_count, self.alive)
        self._render_dirty = True
        return removed

    def _step(self):
        self._count, self._free_count = _step(
            self._active, self._count, self._free, self._free_count, self.alive,
            self.age, self._lifetime, self._origin, self.position, self._velocity,
            self._acceleration, self._direction, self._radius, self._radial_step, self._radial)

    def update(self):
        if self._count:
            self._step()
            self._render_dirty = True

    def _pack(self):
        self._back_count = _pack(
            self._active, self._count, self.age, self._start, self._layer,
            self.position, self._rotation, self._color, self._scale, self._visual,
            self._visual_keys, self._output, self._keys)

    def prepare_render_data(self, layer):
        """Reusable float32 views, stable birth order within each layer."""
        if layer not in ('back', 'front'):
            raise ValueError('particle layer must be back/front')
        if self._render_dirty:
            self._pack()
            self._render_dirty = False
        start, end = (0, self._back_count) if layer == 'back' else (self._back_count, self._count)
        return self._output[start:end], self._keys[start:end]

    def warmup(self):
        """Compile the actual update/pack signatures without modifying gameplay."""
        scratch = ParticlePool(1, self.sprite_registry)
        timings = {}
        for name, operation in (
            ('update', scratch._step), ('pack', scratch._pack),
            ('compact', lambda: _compact(scratch._active, scratch._count, scratch._free,
                                        scratch._free_count, scratch.alive)),
        ):
            start = time.perf_counter()
            operation()
            timings[name] = round((time.perf_counter() - start) * 1000, 3)
        return timings

"""Snapshots, parameter alignment and whole-batch numerical computations.

This module has no pool writes, task scheduler or per-bullet Python callback.
Positions, velocities and accelerations use the caller's coordinate and unit
system; angles use radians.  Author-facing unit conversion belongs to Context.
"""

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping

import numpy as np
from numba import njit

from src.game.bullet.behavior import BulletGroup, compile_stages


VECTOR_FIELDS = frozenset({'pos', 'vel', 'acc', 'hitbox_size'})
SCALAR_FIELDS = frozenset({
    'angle', 'speed', 'speed_accel', 'sprite_idx', 'tag', 'time_scale', 'lifetime',
    'collision_shape', 'radius', 'hitbox_angle',
    'render_angle', 'render_angle_offset', 'render_flip_y',
})
SNAPSHOT_FIELDS = VECTOR_FIELDS | SCALAR_FIELDS

_SCALAR_LIMITS = {}


def scalar_parameter(value, name, dtype=np.float32):
    """Convert one numeric scalar without NumPy array reductions/broadcasts."""
    target = np.dtype(dtype)
    limits = _SCALAR_LIMITS.get(target)
    if limits is None:
        if target.kind not in {'f', 'i', 'u'}:
            raise TypeError('bullet scalar dtype must be numeric')
        info = np.finfo(target) if target.kind == 'f' else np.iinfo(target)
        limits = (info.min, info.max)
        _SCALAR_LIMITS[target] = limits
    number = value.item() if isinstance(value, (np.ndarray, np.generic)) else value
    if not math.isfinite(number):
        raise ValueError(f'bullet {name} must be finite and representable as {target}')
    if target.kind in {'i', 'u'}:
        if number != math.floor(number) or number < limits[0] or number > limits[1]:
            raise ValueError(f'bullet {name} requires integers representable as {target}')
    elif number < limits[0] or number > limits[1]:
        # Preserve representable rounding near a dtype limit, but reject an
        # actual overflow before it can be written to a live pool slot.
        with np.errstate(over='ignore', invalid='ignore'):
            converted = target.type(number)
        if not math.isfinite(converted):
            raise ValueError(f'bullet {name} must be finite and representable as {target}')
        return converted
    return target.type(number)


@dataclass(frozen=True, eq=False)
class BulletSnapshot:
    """Detached, read-only field copies aligned with one fixed living group.

    ``group`` is captured when the pool reads the snapshot, not the original
    possibly partly expired selection.  Writing a computed result back through
    that group still checks slot generations.  Internal pool allocation and
    liveness arrays are never included in ``fields``.
    """

    group: BulletGroup
    fields: Mapping[str, np.ndarray]

    def __post_init__(self):
        if not isinstance(self.group, BulletGroup):
            raise TypeError('bullet snapshot requires a fixed BulletGroup')
        unknown = set(self.fields) - SNAPSHOT_FIELDS
        if unknown:
            raise ValueError('unknown bullet snapshot fields: ' + ', '.join(sorted(unknown)))
        copies = {}
        count = len(self.group)
        for name, value in self.fields.items():
            array = np.array(value, copy=True, order='C')
            expected = (count, 2) if name in VECTOR_FIELDS else (count,)
            if array.shape != expected:
                raise ValueError(f'bullet snapshot {name} requires shape {expected}')
            array.flags.writeable = False
            copies[name] = array
        object.__setattr__(self, 'fields', MappingProxyType(copies))

    def __len__(self):
        return len(self.group)

    def __getitem__(self, name):
        return self.fields[name]

    def select(self, mask):
        """Keep matching snapshot rows without losing their slot generations."""
        mask = np.asarray(mask)
        if mask.dtype != np.bool_ or mask.shape != (len(self),):
            raise ValueError('snapshot selection requires a length-N boolean mask')
        indices = self.group.indices[mask]
        generations = self.group.generations[mask]
        indices.flags.writeable = False
        generations.flags.writeable = False
        group = BulletGroup(indices, generations, self.group.pool_token)
        return BulletSnapshot(group, {name: values[mask] for name, values in self.fields.items()})


def _alignment(count, source_count, survivor_mask):
    """Validate explicit original-selection alignment, never truncate arrays."""
    if not isinstance(count, (int, np.integer)) or count < 0:
        raise ValueError('bullet batch count must be a non-negative integer')
    source_count = count if source_count is None else source_count
    if not isinstance(source_count, (int, np.integer)) or source_count < 0:
        raise ValueError('bullet source count must be a non-negative integer')
    if survivor_mask is None:
        if source_count != count:
            raise ValueError('changed bullet selection requires a survivor mask')
        return source_count, None
    mask = np.asarray(survivor_mask)
    if mask.dtype != np.bool_ or mask.shape != (source_count,):
        raise ValueError('bullet survivor mask must be a boolean array for the original selection')
    if np.count_nonzero(mask) != count:
        raise ValueError('bullet survivor mask does not match the living selection')
    return source_count, mask


def normalize_scalar(value, count, name, *, source_count=None,
                     survivor_mask=None, dtype=np.float32):
    """Broadcast a scalar or align an original-selection length-N array.

    When a group lost bullets, array values must still have the original group's
    length.  The explicit survivor mask selects the corresponding values; an
    array of merely the surviving length is rejected, not silently reindexed.
    Integer dtypes reject fractional values and out-of-range values.
    """
    expected, mask = _alignment(count, source_count, survivor_mask)
    raw = np.asarray(value)
    if raw.ndim != 0 and raw.shape != (expected,):
        raise ValueError(f'bullet {name} requires a scalar or shape ({expected},)')
    target = np.dtype(dtype)
    if target.kind not in {'f', 'i', 'u'}:
        raise TypeError('bullet scalar dtype must be numeric')
    if raw.ndim == 0 and raw.dtype.kind in {'b', 'i', 'u', 'f'}:
        return np.full(count, scalar_parameter(raw, name, target), dtype=target)
    if target.kind in {'i', 'u'}:
        numeric = np.asarray(value, dtype=np.float64)
        limits = np.iinfo(target)
        if (not np.all(np.isfinite(numeric)) or np.any(numeric != np.floor(numeric))
                or np.any(numeric < limits.min) or np.any(numeric > limits.max)):
            raise ValueError(f'bullet {name} requires integers representable as {target}')
    with np.errstate(over='ignore', invalid='ignore'):
        array = np.asarray(value, dtype=target)
    if not np.all(np.isfinite(array)):
        raise ValueError(f'bullet {name} must be finite')
    if array.ndim == 0:
        return np.full(count, array.item(), dtype=target)
    if mask is not None:
        array = array[mask]
    return np.ascontiguousarray(array)


def normalize_vector(value, count, name, *, source_count=None, survivor_mask=None):
    """Broadcast (x, y), or align an original-selection array of shape (N, 2)."""
    expected, mask = _alignment(count, source_count, survivor_mask)
    with np.errstate(over='ignore', invalid='ignore'):
        array = np.asarray(value, dtype=np.float32)
    if array.shape != (2,) and array.shape != (expected, 2):
        raise ValueError(f'bullet {name} requires shape (2,) or ({expected}, 2)')
    if not np.all(np.isfinite(array)):
        raise ValueError(f'bullet {name} must be finite')
    if array.shape == (2,):
        return np.broadcast_to(array, (count, 2)).copy()
    if mask is not None:
        array = array[mask]
    return np.ascontiguousarray(array)


def compile_batch_stages(stages, register_sprite, count, *, source_count=None,
                         survivor_mask=None):
    """Pack shared commands and optional original-row-aligned parameters.

    Only an explicitly supplied length-N parameter allocates per-row stages.
    The ordinary scalar program remains a small shared table. Parameter rows
    are bullet-major so the existing stage cursor can read them without Python
    callbacks, array lookups by tag, or a task for each projectile.
    """
    numeric = {'duration', 'speed', 'angle', 'angle_offset', 'velocity_scale_end',
               'accel', 'turn_rate', 'max_turn_rate', 'vector_accel'}
    shared = []
    overrides = []
    for stage_index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            raise TypeError('each bullet stage must be a dictionary')
        values = dict(stage)
        for name in numeric & values.keys():
            value = values[name]
            if name == 'duration' and value is None:
                continue
            array = np.asarray(value)
            vector = name == 'vector_accel'
            if (vector and array.shape == (2,)) or (not vector and array.ndim == 0):
                continue
            if vector:
                normalized = normalize_vector(
                    value, count, name, source_count=source_count,
                    survivor_mask=survivor_mask,
                )
                values[name] = (0.0, 0.0)
            else:
                normalized = normalize_scalar(
                    value, count, name, source_count=source_count,
                    survivor_mask=survivor_mask,
                    dtype=np.float64 if name == 'duration' else np.float32,
                )
                if name in {'duration', 'speed', 'max_turn_rate'} and np.any(normalized < 0):
                    raise ValueError('bullet stage ' + name + ' must be non-negative')
                if name == 'turn_rate' and values.get('homing') is not None and np.any(normalized != 0):
                    raise ValueError('bullet stage homing cannot be combined with turn_rate')
                values[name] = 0.0
            overrides.append((stage_index, name, normalized))
        shared.append(values)
    rows = compile_stages(shared, register_sprite)
    if not overrides:
        return rows, None
    parameters = np.broadcast_to(rows, (count, len(rows))).copy()
    for stage_index, name, values in overrides:
        parameters[name][:, stage_index] = values
    return rows, parameters.reshape(-1)


@njit(cache=True)
def distance_acceleration(positions, center, angle_scale, angle_offset,
                          magnitude, minimum_distance_squared=0.1):
    """Compute a distance-dependent acceleration direction for each bullet.

    TH06 Stage6Func9 uses ``angle_scale=pi/256`` and one shared random offset.
    Its squared distances <= 0.1 are treated as zero.  This helper preserves
    that detail and does not replace the bullet's existing velocity.
    """
    if positions.shape[1] != 2 or len(center) != 2:
        raise ValueError('distance acceleration requires 2D positions and a 2D center')
    if (not math.isfinite(angle_scale) or not math.isfinite(angle_offset)
            or not math.isfinite(magnitude) or not math.isfinite(minimum_distance_squared)
            or minimum_distance_squared < 0):
        raise ValueError('distance acceleration parameters must be finite')
    result = np.empty((len(positions), 2), dtype=np.float32)
    for index in range(len(positions)):
        dx = positions[index, 0] - center[0]
        dy = positions[index, 1] - center[1]
        squared = dx * dx + dy * dy
        distance = math.sqrt(squared) if squared > minimum_distance_squared else 0.0
        angle = distance * angle_scale + angle_offset
        result[index, 0] = math.cos(angle) * magnitude
        result[index, 1] = math.sin(angle) * magnitude
    return result


@njit(cache=True)
def neighbor_activation(source_positions, target_positions, center, radius,
                        angle_factor, eligible_mask, magnitude=0.01):
    """Activate eligible targets using the first qualifying source in order.

    Returns ``matched, angles, acceleration, source_indices`` aligned with all
    targets.  Unmatched entries have zero angle/acceleration and source -1.
    Source ordering is semantic: TH06 StageXFunc15 activates a resting small
    bullet only once, from the first nearby large bullet in pool-slot order.
    The strict radius test and unwrapped angle difference match the original.

    The loop uses O(N + M) result/work storage, never an M-by-N distance matrix.
    Callers choose a spatial index separately if measured source counts need it.
    """
    if source_positions.shape[1] != 2 or target_positions.shape[1] != 2 or len(center) != 2:
        raise ValueError('neighbor activation requires 2D positions and a 2D center')
    count = len(target_positions)
    if len(eligible_mask) != count:
        raise ValueError('neighbor activation eligibility must align with targets')
    if (not math.isfinite(radius) or radius < 0 or not math.isfinite(angle_factor)
            or not math.isfinite(magnitude)):
        raise ValueError('neighbor activation parameters must be finite and radius non-negative')
    matched = np.zeros(count, dtype=np.bool_)
    angles = np.zeros(count, dtype=np.float32)
    acceleration = np.zeros((count, 2), dtype=np.float32)
    source_indices = np.full(count, -1, dtype=np.intp)
    source_angles = np.empty(len(source_positions), dtype=np.float64)
    for source in range(len(source_positions)):
        source_angles[source] = math.atan2(source_positions[source, 1] - center[1],
                                          source_positions[source, 0] - center[0])
    radius_squared = radius * radius
    for target in range(count):
        if not eligible_mask[target]:
            continue
        for source in range(len(source_positions)):
            dx = target_positions[target, 0] - source_positions[source, 0]
            dy = target_positions[target, 1] - source_positions[source, 1]
            if dx * dx + dy * dy < radius_squared:
                target_angle = math.atan2(target_positions[target, 1] - center[1],
                                          target_positions[target, 0] - center[0])
                angle = ((target_angle - source_angles[source]) * angle_factor
                         + source_angles[source])
                matched[target] = True
                angles[target] = angle
                acceleration[target, 0] = math.cos(angle) * magnitude
                acceleration[target, 1] = math.sin(angle) * magnitude
                source_indices[target] = source
                break
    return matched, angles, acceleration, source_indices

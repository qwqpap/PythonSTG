"""Compact shared bullet stages, executed inside the existing array pool.

Pool units are radians, seconds and the pool's normalized speed units.  The
author-facing StageContext performs its usual coordinate/unit conversion.
This module contains no objects/tasks/callbacks per bullet.
"""

from dataclasses import dataclass
import math

import numpy as np
from numba import njit


@dataclass(frozen=True, eq=False)
class BulletGroup:
    """A fixed spawn selection; slot reuse never adds replacement bullets."""

    indices: np.ndarray
    generations: np.ndarray
    pool_token: object

    def __len__(self):
        return len(self.indices)


STAGE_DTYPE = np.dtype([
    ('duration', 'f8'),
    ('speed', 'f4'),
    ('angle', 'f4'),
    ('aim', 'i1'),
    ('target', 'f4', 2),
    ('accel', 'f4'),
    ('vector_accel', 'f4', 2),
    ('turn_rate', 'f4'),
    ('homing', 'i1'),
    ('homing_target', 'f4', 2),
    ('max_turn_rate', 'f4'),
    ('bounce_x', 'i2'),
    ('bounce_y', 'i2'),
    ('wrap_x', 'i2'),
    ('wrap_y', 'i2'),
    ('sprite_idx', 'i4'),
])


def compile_stages(stages, register_sprite):
    """Validate and pack a finite stage sequence once, not once per bullet."""
    stages = tuple(stages)
    if not 1 <= len(stages) <= 64:
        raise ValueError('bullet behavior requires 1..64 stages')
    rows = np.zeros(len(stages), dtype=STAGE_DTYPE)
    for name in ('speed', 'angle'):
        rows[name] = np.nan
    for name in ('bounce_x', 'bounce_y', 'wrap_x', 'wrap_y'):
        rows[name] = -1
    rows['sprite_idx'] = -1
    allowed = set(STAGE_DTYPE.names) - {'target', 'homing_target', 'sprite_idx'} | {'sprite_id'}
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            raise TypeError('each bullet stage must be a dictionary')
        unknown = set(stage) - allowed
        if unknown:
            raise TypeError('unknown bullet stage fields: ' + ', '.join(sorted(unknown)))
        duration = stage.get('duration')
        if duration is None:
            if index != len(stages) - 1:
                raise ValueError('only the last bullet stage may omit duration')
            rows['duration'][index] = -1.0
        else:
            duration = float(duration)
            if not math.isfinite(duration) or duration < 0:
                raise ValueError('bullet stage duration must be finite and non-negative')
            rows['duration'][index] = duration
        for name in ('speed', 'angle', 'accel', 'turn_rate', 'max_turn_rate'):
            if name in stage:
                value = float(stage[name])
                if not math.isfinite(value) or (name in {'speed', 'max_turn_rate'} and value < 0):
                    raise ValueError('invalid bullet stage ' + name)
                rows[name][index] = value
        if 'vector_accel' in stage:
            acceleration = np.asarray(stage['vector_accel'], dtype=np.float32)
            if acceleration.shape != (2,) or not np.all(np.isfinite(acceleration)):
                raise ValueError('bullet stage vector_accel must be a finite (x, y) pair')
            rows['vector_accel'][index] = acceleration
        aim = stage.get('aim')
        if aim is not None:
            if isinstance(aim, str) and aim == 'player':
                rows['aim'][index] = 1
            elif isinstance(aim, (tuple, list)) and len(aim) == 2:
                target = np.asarray(aim, dtype=np.float32)
                if not np.all(np.isfinite(target)):
                    raise ValueError('bullet stage aim position must be finite')
                rows['aim'][index] = 2
                rows['target'][index] = target
            else:
                raise ValueError("bullet stage aim must be 'player' or (x, y)")
        homing = stage.get('homing')
        if homing is not None:
            if 'max_turn_rate' not in stage:
                raise ValueError('bullet stage homing requires max_turn_rate')
            if rows['turn_rate'][index] != 0:
                raise ValueError('bullet stage homing cannot be combined with turn_rate')
            if isinstance(homing, str) and homing == 'player':
                rows['homing'][index] = 1
            elif isinstance(homing, (tuple, list)) and len(homing) == 2:
                target = np.asarray(homing, dtype=np.float32)
                if not np.all(np.isfinite(target)):
                    raise ValueError('bullet stage homing position must be finite')
                rows['homing'][index] = 2
                rows['homing_target'][index] = target
            else:
                raise ValueError("bullet stage homing must be 'player' or (x, y)")
        elif 'max_turn_rate' in stage:
            raise ValueError('bullet stage max_turn_rate requires homing')
        for name in ('bounce_x', 'bounce_y', 'wrap_x', 'wrap_y'):
            if name in stage:
                value = stage[name]
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 32767:
                    raise ValueError(name + ' must be an integer in 0..32767')
                rows[name][index] = value
        for axis in ('x', 'y'):
            if rows['bounce_' + axis][index] > 0 and rows['wrap_' + axis][index] > 0:
                raise ValueError('bullet stage bounce_' + axis + ' and wrap_' + axis + ' are mutually exclusive')
        if 'sprite_id' in stage:
            rows['sprite_idx'][index] = register_sprite(stage['sprite_id'])
    return rows


@njit(cache=True)
def advance_stages(data, table, stages, ends, elapsed, entered,
                   bounce_x, bounce_y, dt, player_x, player_y,
                   wrap_remaining_x=None, wrap_remaining_y=None):
    """Apply entry commands before this frame's existing movement kernel."""
    active = 0
    wrapping = 0
    for i in range(len(data)):
        stage = stages[i]
        if stage < 0 or data[i]['alive'] == 0:
            continue
        end = ends[i]
        # At most 64 entries can be processed.  Zero-duration stages cannot
        # create a busy loop, and timers belong to individual bullet slots.
        while stage < end:
            row = table[stage]
            if not entered[i]:
                if not math.isnan(row['speed']):
                    data[i]['speed'] = row['speed']
                if not math.isnan(row['angle']):
                    data[i]['angle'] = row['angle']
                if row['aim'] == 1:
                    data[i]['angle'] = math.atan2(player_y - data[i]['pos'][1],
                                                 player_x - data[i]['pos'][0])
                elif row['aim'] == 2:
                    data[i]['angle'] = math.atan2(row['target'][1] - data[i]['pos'][1],
                                                 row['target'][0] - data[i]['pos'][0])
                if not math.isnan(row['accel']):
                    data[i]['speed_accel'] = row['accel']
                data[i]['acc'][0] = row['vector_accel'][0]
                data[i]['acc'][1] = row['vector_accel'][1]
                if not math.isnan(row['turn_rate']):
                    data[i]['motion_angular_vel'] = row['turn_rate']
                if row['bounce_x'] >= 0:
                    bounce_x[i] = row['bounce_x']
                    if bounce_x[i] > 0:
                        data[i]['flags'] |= 1
                    else:
                        data[i]['flags'] &= 65534
                if row['bounce_y'] >= 0:
                    bounce_y[i] = row['bounce_y']
                    if bounce_y[i] > 0:
                        data[i]['flags'] |= 2
                    else:
                        data[i]['flags'] &= 65533
                if wrap_remaining_x is not None:
                    if row['bounce_x'] > 0:
                        wrap_remaining_x[i] = 0
                    if row['wrap_x'] >= 0:
                        wrap_remaining_x[i] = row['wrap_x']
                        if row['wrap_x'] > 0:
                            bounce_x[i] = 0
                            data[i]['flags'] &= 65534
                if wrap_remaining_y is not None:
                    if row['bounce_y'] > 0:
                        wrap_remaining_y[i] = 0
                    if row['wrap_y'] >= 0:
                        wrap_remaining_y[i] = row['wrap_y']
                        if row['wrap_y'] > 0:
                            bounce_y[i] = 0
                            data[i]['flags'] &= 65533
                if row['sprite_idx'] >= 0:
                    data[i]['sprite_idx'] = row['sprite_idx']
                entered[i] = True
            duration = row['duration']
            if duration < 0 or elapsed[i] + 1e-9 < duration:
                break
            elapsed[i] -= duration
            stage += 1
            entered[i] = False
        if wrap_remaining_x is not None and wrap_remaining_x[i] > 0:
            wrapping += 1
        elif wrap_remaining_y is not None and wrap_remaining_y[i] > 0:
            wrapping += 1
        if stage == end:
            stages[i] = -1
            continue
        # The existing stage index is also the homing state: leaving a stage
        # immediately stops tracking, without another per-bullet side array.
        row = table[stage]
        local_dt = dt * data[i]['time_scale']
        if row['homing'] != 0 and local_dt > 0:
            tx, ty = player_x, player_y
            if row['homing'] == 2:
                tx, ty = row['homing_target'][0], row['homing_target'][1]
            dx, dy = tx - data[i]['pos'][0], ty - data[i]['pos'][1]
            if dx != 0 or dy != 0:
                target_angle = math.atan2(dy, dx)
                difference = (target_angle - data[i]['angle'] + math.pi) % (2.0 * math.pi) - math.pi
                limit = row['max_turn_rate'] * local_dt
                data[i]['angle'] += max(-limit, min(limit, difference))
        stages[i] = stage
        elapsed[i] += local_dt
        active += 1
    return active, wrapping


@njit(cache=True)
def select_region(data, kind, cx, cy, extent_x, extent_y, angle):
    """Return a full mask for a circle or rotated rectangle, excluding emitters."""
    result = np.zeros(len(data), dtype=np.bool_)
    ca = math.cos(angle)
    sa = math.sin(angle)
    for i in range(len(data)):
        if data[i]['alive'] == 0 or data[i]['flags'] & 4:
            continue
        dx = data[i]['pos'][0] - cx
        dy = data[i]['pos'][1] - cy
        if kind == 0:
            result[i] = dx * dx + dy * dy <= extent_x * extent_x
        else:
            x = dx * ca + dy * sa
            y = -dx * sa + dy * ca
            result[i] = abs(x) <= extent_x * 0.5 and abs(y) <= extent_y * 0.5
    return result


def region_mask(data, region):
    """Region schema: {kind: circle/rect, x, y, radius OR width,height,angle}."""
    if not isinstance(region, dict):
        raise TypeError('bullet region must be a dictionary')
    kind = region.get('kind', 'circle')
    keys = {'kind', 'x', 'y', 'radius'} if kind == 'circle' else {'kind', 'x', 'y', 'width', 'height', 'angle'}
    if kind not in {'circle', 'rect'} or set(region) - keys:
        raise ValueError('unsupported bullet region fields')
    x, y = float(region.get('x', 0.0)), float(region.get('y', 0.0))
    if kind == 'circle':
        a, b, angle = float(region['radius']), 0.0, 0.0
    else:
        a, b = float(region['width']), float(region['height'])
        angle = float(region.get('angle', 0.0))
    if not all(math.isfinite(v) for v in (x, y, a, b, angle)) or a < 0 or b < 0:
        raise ValueError('invalid bullet region geometry')
    return select_region(data, 0 if kind == 'circle' else 1, x, y, a, b, angle)

"""Shared frame-based movement and interaction controls for scripted actors.

Only the few actor coroutines use this module. Bullet motion remains batched
in the NumPy/Numba pool; there is no per-bullet task here.
"""

import math
import operator
import types


EASINGS = {
    'linear': lambda t: t,
    'smoothstep': lambda t: t * t * (3.0 - 2.0 * t),
    'ease_in': lambda t: t * t,
    'ease_out': lambda t: 1.0 - (1.0 - t) ** 2,
    'ease_in_fast': lambda t: t ** 4,
    'ease_out_fast': lambda t: 1.0 - (1.0 - t) ** 4,
}


class ActorControls:
    """Public controls shared by EnemyScript, BossBase and spell preview."""

    collidable = True
    damageable = True
    interactable = True
    visible = True
    movement_bounds = None

    def set_interaction(self, *, collidable=None, damageable=None,
                        interactable=None, visible=None):
        """Keep hit reactions, HP loss, targetability and drawing independent.

        A fake boss uses damageable=False but remains collidable. A bat hidden
        during Bomb uses interactable=False; it is neither hit nor homed onto.
        invisible alone does not confer invulnerability.
        """
        for name, value in (('collidable', collidable), ('damageable', damageable),
                            ('interactable', interactable), ('visible', visible)):
            if value is not None:
                setattr(self, name, bool(value))

    def set_movement_bounds(self, left, right, bottom, top):
        if left > right or bottom > top:
            raise ValueError('movement bounds must be ordered')
        self.movement_bounds = (float(left), float(right), float(bottom), float(top))
        self.set_position(self.x, self.y)

    def clear_movement_bounds(self):
        self.movement_bounds = None

    def set_position(self, x, y):
        bounds = self.movement_bounds
        if bounds is not None:
            left, right, bottom, top = bounds
            x, y = min(right, max(left, x)), min(top, max(bottom, y))
        self.x, self.y = float(x), float(y)

    @types.coroutine
    def move_to(self, x, y, duration=60, *, easing='smoothstep'):
        """Move over exactly duration yields. Zero duration is a teleport."""
        curve = EASINGS[easing]
        duration = operator.index(duration)
        if duration < 0:
            raise ValueError('movement duration must be non-negative')
        if duration == 0:
            self.set_position(x, y)
            return
        start_x, start_y = self.x, self.y
        for frame in range(duration):
            t = curve((frame + 1) / duration)
            self.set_position(start_x + (x - start_x) * t,
                              start_y + (y - start_y) * t)
            yield

    @types.coroutine
    def move_linear(self, dx, dy, duration=60):
        yield from self.move_to(self.x + dx, self.y + dy, duration, easing='linear')

    @types.coroutine
    def move_velocity(self, angle, speed, frames=None, *, accel=0.0, turn_rate=0.0):
        """Polar motion: degrees, normalized units/second, seconds-based rates.

        Run as an ordinary actor task to shoot concurrently. Cancellation leaves
        the current position intact; it never schedules another motion task.
        """
        remaining = None if frames is None else operator.index(frames)
        if remaining is not None and remaining < 0:
            raise ValueError('movement frames must be non-negative')
        while remaining is None or remaining > 0:
            angle += turn_rate / 60.0
            speed += accel / 60.0
            theta = math.radians(angle)
            self.set_position(self.x + math.cos(theta) * speed / 60.0,
                              self.y + math.sin(theta) * speed / 60.0)
            if remaining is not None:
                remaining -= 1
            yield


__all__ = ['ActorControls', 'EASINGS']

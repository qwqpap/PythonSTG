"""TH07 stage 5 road, hand-translated from ecldata5 Sub4--36.

The births are plain content data, decoded from the original Timeline0/1.
No source instruction stream runs in PythonSTG. Each ghost owns one ordinary
enemy coroutine; all bullets use the existing numerical pool.
"""

from __future__ import annotations

import math

from src.core.collision_shapes import Hitbox
from src.game.stage.wave_base import Wave

from .common import TH07Enemy, px, py


ROAD_END_FRAME = 4820
AFTER_MIDBOSS_START = 4823
AFTER_MIDBOSS_END = 6113
# frame, source Sub, X, Y, HP, item, score, movement mirror.
ROAD_SPAWNS = (
    (500, 10, 64, 128, 80, 0, 1500, False),
    (510, 10, 80, 112, 80, 0, 1500, False),
    (520, 10, 96, 104, 80, 1, 1500, False),
    (900, 12, 320, 112, 80, 0, 1500, False),
    (910, 12, 304, 96, 80, 0, 1500, False),
    (920, 12, 288, 80, 80, 1, 1500, False),
    (930, 12, 256, 64, 80, 1, 1500, False),
    (1030, 10, 32, 128, 80, 2, 1500, False),
    (1040, 10, 48, 112, 80, 0, 1500, False),
    (1050, 10, 64, 104, 80, 0, 1500, False),
    (1060, 10, 80, 96, 80, 1, 1500, False),
    (1070, 10, 96, 88, 80, 1, 1500, False),
    (1270, 16, 320, 96, 80, 1, 1500, False),
    (1370, 14, 64, 128, 80, 1, 1500, False),
    (1470, 14, 96, 64, 80, 1, 1500, False),
    (1570, 12, 320, 112, 80, 1, 1500, False),
    (1580, 12, 304, 96, 80, 1, 1500, False),
    (1590, 12, 288, 80, 80, 1, 1500, False),
    (1600, 12, 256, 64, 80, 1, 1500, False),
    (1800, 20, 320, 96, 80, 1, 1500, False),
    (1810, 10, 64, 112, 80, 0, 1500, False),
    (1840, 18, 64, 128, 80, 1, 1500, False),
    (1850, 12, 304, 96, 80, 0, 1500, False),
    (1880, 20, 288, 64, 80, 1, 1500, False),
    (1890, 10, 96, 80, 80, 0, 1500, False),
    (1920, 18, 64, 128, 80, 1, 1500, False),
    (1930, 12, 256, 64, 80, 0, 1500, False),
    (1990, 12, 320, 96, 80, 1, 1500, False),
    (2000, 10, 64, 112, 80, 0, 1500, False),
    (2030, 10, 64, 128, 80, 1, 1500, False),
    (2040, 12, 304, 96, 80, 0, 1500, False),
    (2070, 12, 288, 64, 80, 1, 1500, False),
    (2080, 10, 96, 80, 80, 0, 1500, False),
    (2110, 10, 64, 128, 80, 1, 1500, False),
    (2120, 12, 256, 64, 80, 0, 1500, False),
    (2180, 20, 320, 96, 80, 1, 1500, False),
    (2190, 10, 64, 112, 80, 0, 1500, False),
    (2220, 18, 64, 128, 80, 1, 1500, False),
    (2230, 12, 304, 96, 80, 0, 1500, False),
    (2260, 16, 288, 64, 80, 1, 1500, False),
    (2270, 10, 96, 80, 80, 0, 1500, False),
    (2300, 14, 64, 128, 80, 1, 1500, False),
    (2310, 12, 256, 64, 80, 0, 1500, False),
    (2610, 22, 320, -16, 160, 1, 2000, True),
    (2710, 22, 64, -16, 160, 1, 2000, False),
    (2810, 22, 320, -16, 160, 0, 2000, True),
    (2910, 22, 64, -16, 160, 0, 2000, False),
    (3010, 22, 320, -16, 160, 0, 2000, True),
    (3110, 22, 64, -16, 160, 0, 2000, False),
    (3210, 22, 288, -16, 160, 1, 2000, True),
    (3210, 22, 96, -16, 160, 1, 2000, False),
    (3510, 24, 192, -16, 160, 2, 2000, False),
    (3610, 22, 288, -16, 160, 1, 2000, True),
    (3610, 22, 96, -16, 160, 1, 2000, False),
    (3810, 12, 320, 96, 80, 1, 1500, False),
    (3820, 10, 64, 112, 80, 0, 1500, False),
    (3850, 10, 64, 128, 80, 1, 1500, False),
    (3860, 12, 304, 96, 80, 0, 1500, False),
    (3890, 12, 288, 64, 80, 1, 1500, False),
    (3900, 10, 96, 80, 80, 0, 1500, False),
    (3930, 10, 64, 128, 80, 1, 1500, False),
    (3940, 12, 256, 64, 80, 0, 1500, False),
    (3970, 10, 64, 128, 80, 1, 1500, False),
    (3980, 12, 256, 64, 80, 0, 1500, False),
    (4010, 10, 64, 128, 80, 1, 1500, False),
    (4020, 12, 256, 64, 80, 0, 1500, False),
    (4320, 23, 192, -16, 160, 1, 2000, False),
    (4420, 24, 256, -16, 160, 2, 2000, False),
    (4420, 24, 128, -16, 160, 2, 2000, False),
)
AFTER_MIDBOSS_SPAWNS = (
    (4943, 25, 64, 32, 160, 1, 2000, False),
    (4973, 27, 96, 64, 160, 0, 2000, False),
    (5003, 25, 128, 96, 160, 1, 2000, False),
    (5033, 27, 160, 128, 160, 0, 2000, False),
    (5063, 25, 192, 160, 160, 1, 2000, False),
    (5093, 27, 224, 192, 160, 0, 2000, False),
    (5123, 25, 256, 224, 160, 1, 2000, False),
    (5153, 29, 288, 256, 160, 0, 2000, False),
    (5393, 31, 320, 112, 110, 0, 2000, False),
    (5413, 33, 302.865540, 157.922012, 110, 1, 2000, False),
    (5433, 31, 271.195953, 191.195953, 110, 0, 2000, False),
    (5453, 33, 231.799072, 208.083466, 110, 1, 2000, False),
    (5473, 31, 192, 208, 110, 0, 2000, False),
    (5493, 33, 158.323853, 193.301392, 110, 1, 2000, False),
    (5513, 31, 135.431458, 168.568542, 110, 0, 2000, False),
    (5533, 33, 125.480675, 139.553207, 110, 1, 2000, False),
    (5553, 31, 128, 112, 110, 0, 2000, False),
    (5573, 33, 140.262741, 90.569725, 110, 1, 2000, False),
    (5593, 31, 158.058868, 78.058876, 110, 0, 2000, False),
    (5613, 33, 176.692657, 75.0448151, 110, 1, 2000, False),
    (5633, 31, 192, 80, 110, 0, 2000, False),
    (5653, 33, 201.184402, 89.826889, 110, 1, 2000, False),
    (5673, 31, 203.313705, 100.686295, 110, 0, 2000, False),
    (5693, 33, 199.391037, 108.938530, 110, 2, 2000, False),
    (5713, 35, 192, 112, 200, 0, 2000, False),
)
TIMELINE1_SPAWNS = (
    (2701, 12, 320, 112, 80, 0, 1500, False),
    (2711, 12, 304, 96, 80, 0, 1500, False),
    (2911, 10, 64, 112, 80, 0, 1500, False),
    (2921, 10, 80, 96, 80, 0, 1500, False),
    (3121, 12, 320, 112, 80, 0, 1500, False),
    (3131, 12, 304, 96, 80, 0, 1500, False),
    (3331, 10, 64, 112, 80, 0, 1500, False),
    (3341, 10, 80, 96, 80, 0, 1500, False),
    (3541, 12, 320, 112, 80, 0, 1500, False),
    (3551, 12, 304, 96, 80, 0, 1500, False),
)


def drop_power_or_points(actor, count):
    stats = actor.ctx.item_stats
    if stats is not None and stats.power >= stats.max_power:
        actor.drop(1, count)
    elif count:
        actor.drop(2)
        actor.drop(0, count - 1)


def signed(rng, value):
    return value if rng.integers(0, 2) else -value


def hermite_controls(start, end, tangent_start, tangent_end):
    return ((start[0] + tangent_start[0] / 3, start[1] + tangent_start[1] / 3),
            (end[0] - tangent_end[0] / 3, end[1] - tangent_end[1] / 3))


class _TrailGhost(TH07Enemy):
    """Literal ANM30/31 visual state on one ordinary enemy lifecycle.

    The source's ins_138(25, 48, 16, 1) hides the sprite head and draws one
    continuous textured ribbon over 48 position samples. The animation has
    one sprite: its motion, scale, tint and interrupt-driven alpha make it
    animate; cycling a few cut frames cannot reproduce that effect.
    """

    def _start_ghost_visual(self, script):
        self.animate(script)
        self._ghost_started = self.time
        self._ghost_fade_started = None
        self._ghost_tint = (1., 140 / 255, 1.) if script == 31 else (1., 1., 1.)
        self._ghost_alpha = 140 / 255 if script == 31 else 1.
        self.set_visual(scale=(1., 2.), color=(*self._ghost_tint, 0.), blend='add')
        self._ghost_trail = self.ctx.attach_trail(
            self, 'th07_stg5enm_e0_s42', history_frames=48, node_step=1,
            width=32 / 192, blend='add', hide_owner=True)

    def _fade_ghost_visual(self):
        # ANM30/31 wait at their frame-30 STOP until interrupt 1. Resuming
        # starts a new 40-frame interpolation; it is not absolute frame 30.
        self._ghost_fade_started = self.time

    def _stop_ghost_visual(self, *, restore=False):
        trail = getattr(self, '_ghost_trail', None)
        if trail is not None:
            trail.cancel()
            self._ghost_trail = None
        if restore:
            # Entrance and shooting share an actor in this hand translation.
            # The new normal sprite must not inherit the ribbon's material.
            self.set_visual(rotation=0., scale=(1., 1.),
                            color=(1., 1., 1., 1.), blend='alpha')

    def update(self):
        previous = self.x, self.y
        active = super().update()
        if active and getattr(self, '_ghost_trail', None) is not None:
            age = self.time - self._ghost_started
            alpha = self._ghost_alpha * min(1., max(0., age / 30))
            if self._ghost_fade_started is not None:
                alpha *= max(0., 1. - (self.time - self._ghost_fade_started) / 40)
            dx, dy = self.x - previous[0], self.y - previous[1]
            if dx or dy:
                self.set_visual(rotation=math.degrees(math.atan2(dy, dx)))
            self.set_visual(alpha=alpha)
        return active

    def dispose(self):
        self._stop_ghost_visual()
        super().dispose()


class RoadDeathGhost(_TrailGhost):
    hp = 10
    score = 0
    sprite = ''

    async def run(self):
        self.set_interaction(interactable=False, damageable=False)
        self.set_contact_hitbox(enabled=False)
        self._start_ghost_visual(31)
        start = self.source_position
        target = start[0] + 4, start[1] - 156
        controls = hermite_controls(start, target, (signed(self.rng, 144), 59),
                                    (signed(self.rng, 144), signed(self.rng, 32)))
        self.spawn_task(self.move_curve_source(target, *controls, 120), immediate=True)
        await self.wait(80)
        self._fade_ghost_visual()
        await self.wait(40)


class RoadGhost(_TrailGhost):
    """Source entrance Sub9 followed by its literal shooting subroutine."""

    sprite = ''

    def __init__(self, *, sub=10, hp=80, item=0, score=1500, mirror=False):
        super().__init__()
        self.source_sub, self.hp, self.source_item = sub, hp, item
        self.score, self.mirror = score, mirror
        self.protected_until = float('inf')
        self._shooting = False
        self.on_death = self._after_death

    def damage(self, amount, **kwargs):
        if self.time >= self.protected_until:
            super().damage(amount, **kwargs)

    def update(self):
        active = super().update()
        if active and self._shooting:
            frame, _ = self.get_render_frame()
            if frame is None:
                raise RuntimeError('TH07 road ghost needs its original sprite for OOB culling')
            x, y = self.source_position
            if (x + frame.width / 2 < 0 or x - frame.width / 2 > 384
                    or y + frame.height / 2 < 0 or y - frame.height / 2 > 448):
                self.dispose()
                active = False
        return active

    def _after_death(self, _enemy):
        if self.source_item >= 0:
            self.drop(self.source_item)
        if self.source_sub in (14, 16, 18, 20, 29, 35, 22, 23, 24):
            drop_power_or_points(self, 4)
            self.drop(1, 3 if self.source_sub in (22, 23, 24) else 1)
        self.spawn_source(RoadDeathGhost, *self.source_position)

    async def run(self):
        self.set_contact_hitbox(enabled=False)
        self.set_interaction(interactable=False, damageable=False)
        if self.source_sub not in (22, 23, 24):
            target = self.source_position
            start = target[0] - 3, target[1] + 147
            controls = hermite_controls(start, target, (signed(self.rng, 144), 1),
                                        (signed(self.rng, 144), signed(self.rng, 32)))
            self.set_position(px(start[0]), py(start[1]))
            self._start_ghost_visual(30)
            self.spawn_task(self.move_curve_source(target, *controls, 80), immediate=True)
            await self.wait(80)
            self._stop_ghost_visual(restore=True)
        self.animate(26 if self.source_sub in (22, 23, 24) else 27)
        if self.source_sub in (22, 23, 24):
            self.attach_animation('th07_stg5enm_script_32')
        self.set_hitbox(Hitbox.box(24 / 192, 24 / 192))
        self.set_interaction(interactable=True, damageable=True)
        self._shooting = True
        self.protected_until = self.time + {
            10: 10, 12: 10, 18: 30, 20: 30, 22: 30, 23: self.rank((30, 40, 40, 40)),
            24: 30, 25: 20, 27: 20, 29: 10, 31: 4, 33: 4, 35: 10,
        }.get(self.source_sub, 0)
        self.sound(1)
        if self.source_sub in (10, 12):
            await self._curving_stream()
        elif self.source_sub in (14, 16, 18, 20):
            await self._speed_stack()
        elif self.source_sub in (22, 23, 24):
            await self._fairy_fan()
        else:
            await self._orbit_offsets()
        await self.wait(3000)

    async def _curving_stream(self):
        left = self.source_sub == 10
        self.spawn_task(self.move_polar_source(0 if left else math.pi, 0,
                                               accel=0.02), immediate=True)
        angle = math.pi if left else 0
        commands = ((0, 1, 0, -1, -1, -1., -1.),)
        for _ in range(22):
            angle += (-1 if left else 1) * math.pi / 64
            self.emit(6, 2, self.rank((1, 5, 7, 11)), 1,
                      self.rank((1.7, 1.7, 1.9, 2.2 if left else 2.0)),
                      self.rank((1., 1., 1., 1.3)), angle, math.pi / 2, 515,
                      aim_mode=3, commands=commands)
            await self.wait(10)

    async def _speed_stack(self):
        right = self.source_sub in (14, 18)
        self.spawn_task(self.move_polar_source(0 if right else math.pi, 0,
                                               accel=0.02), immediate=True)
        narrow = self.source_sub in (18, 20)
        for index in range(self.rank((4, 8, 10, 12) if narrow else (4, 8, 12, 16))):
            self.emit(1, 6, 5, 1, 0.8 + index * (0.375 if narrow else 0.475),
                      1., self.aim_source(), math.pi / (7 if narrow else (4.5 if right else 5)),
                      514)
            await self.wait(4)

    async def _fairy_fan(self):
        self.spawn_task(self.move_source(self.sx, self.sy + 120, 60, easing=4), immediate=True)
        await self.wait(60)
        if self.source_sub == 22:
            angle = self.aim_source()
            if self.diff:
                self.emit(3, 2, 3, 3, 2.4, 1., angle, 0., 514)
            for sign in (-1, 1):
                commands = ((0, 32, 0, 60, -1, 0., -sign * math.pi / 720),)
                self.emit(3, 2, 3, 3, self.rank((2., 2.4, 2.8, 3.)), 1.,
                          angle + sign * math.pi / 4, sign * math.pi / 8, 546,
                          commands=commands)
        else:
            if self.diff:
                self.emit(6, 2, self.rank((3, 3, 5, 5)), 5,
                          self.rank((2.4, 2.4, 2.4, 3.)), 1., math.pi / 2, math.pi / 8, 514)
            for color, layers, speed, side in ((2, 5, 2.8, math.pi / 4),
                                                (14, 4, 2.4, math.pi / 2)):
                if color == 14:
                    self.emit(6, color, 3, layers, speed, 1., math.pi / 2, math.pi / 4, 514)
                for sign in (-1, 1):
                    commands = ((0, 32, 0, 60, -1, 0., -sign * (math.pi / 240 if color == 2
                                                                             else math.pi / 120)),)
                    self.emit(6, color, 3, layers, speed, 1., math.pi / 2 + sign * side,
                              math.pi / (8 if color == 2 else 4), 546, commands=commands)
        await self.wait(60)
        angle = (math.pi if self.mirror else 0) if self.source_sub == 22 else math.pi / 2
        self.spawn_task(self.move_polar_source(angle, 2.), immediate=True)

    async def _orbit_offsets(self):
        sub = self.source_sub
        double = sub in (29, 35)
        radius = 64 if sub == 35 else 32
        angles = [-math.pi / 2, -math.pi / 2] if double else [math.pi / 2]
        commands = ((0, 1, 0, -1, -1, -1., -1.),)
        for _ in range(16 if double else 32):
            for side in range(2 if double else 1):
                sign = -1 if side == 0 and sub not in (27, 33) else 1
                angles[side] += sign * math.pi / 16
                x, y = self.source_position
                origin = x + math.sin(angles[side]) * radius, y + math.cos(angles[side]) * radius
                if sub in (31, 33, 35):
                    color = (2 if side == 0 else 6) if sub == 35 else (2 if sub == 31 else 6)
                    # Sub36's second burst really reuses the first angle.
                    self.emit(3 if sub == 35 else 6, color,
                              4 if sub == 35 else self.diff + 1, 1,
                              1. if sub == 35 else 1.2, 1., angles[0] if sub == 35 else angles[side],
                              math.pi / 4, 517, position=origin, commands=commands)
                else:
                    self.emit(1, 8 if sub == 29 else (2 if sub == 25 else 6),
                              self.rank((1, 1, 2, 3)), self.rank((1, 3, 3, 4)),
                              self.rank((1.2, 1.6, 2., 2.)) if sub == 29 else self.rank((2.8, 3.2, 3.5, 4.2)),
                              1., 0., math.pi / 40, 515, aim_mode=0, position=origin, commands=commands)
                await self.wait(1 if sub in (31, 33, 35) else (2 if sub == 29 else 4))
        await self.wait(120 if sub == 35 else (60 if sub in (31, 33) else 0))
        self.spawn_task(self.move_polar_source(-math.pi / 2, 0., accel=0.02), immediate=True)


def spawn_road(ctx, record):
    frame, sub, x, y, hp, item, score, mirror = record
    enemy = RoadGhost(sub=sub, hp=hp, item=item, score=score, mirror=mirror)
    enemy.bind(ctx, px(x), py(y))
    enemy.start()
    ctx.add_enemy_script(enemy)
    return enemy


class RoadWave(Wave):
    async def run(self):
        previous = 0
        for record in ROAD_SPAWNS:
            await self.wait(record[0] - previous)
            spawn_road(self.ctx, record)
            previous = record[0]
        await self.wait(ROAD_END_FRAME - previous)


class AfterMidbossWave(Wave):
    async def run(self):
        previous = AFTER_MIDBOSS_START
        for record in AFTER_MIDBOSS_SPAWNS:
            await self.wait(record[0] - previous)
            spawn_road(self.ctx, record)
            previous = record[0]
        await self.wait(AFTER_MIDBOSS_END - previous)


class Timeline1Enemies(TH07Enemy):
    hp = 1
    score = 0
    sprite = ''

    async def run(self):
        self.set_interaction(interactable=False, damageable=False, visible=False)
        self.set_contact_hitbox(enabled=False)
        previous = 0
        for record in TIMELINE1_SPAWNS:
            await self.wait(record[0] - previous)
            if not getattr(self.state, 'boss_present', False):
                spawn_road(self.ctx, record)
            previous = record[0]


__all__ = ['ROAD_END_FRAME', 'AFTER_MIDBOSS_START', 'AFTER_MIDBOSS_END',
           'ROAD_SPAWNS', 'AFTER_MIDBOSS_SPAWNS', 'TIMELINE1_SPAWNS',
           'RoadWave', 'AfterMidbossWave', 'Timeline1Enemies', 'RoadGhost',
           'RoadDeathGhost', 'drop_power_or_points', 'hermite_controls']

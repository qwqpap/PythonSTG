"""TH07 stage 6 road, translated to ordinary Wave / EnemyScript content.

Source: ecldata6.ecl Sub1, Sub4--16 and Timeline0/1, TH07 1.00b.
The source coordinates are pixels, Y down; common.py performs the conversion.
The 47 births below are data, not executable ECL. Source animation interrupts
and trails remain explicitly identified resource work, not claimed by the
cut-frame animation adapter.
"""

from __future__ import annotations

import math

from src.core.collision_shapes import Hitbox
from src.game.stage.wave_base import Wave

from .common import TH07Enemy, px, py


ROAD_END_FRAME = 1914
# (timeline frame, source sub, x, y, z, life, itemDrop, score).
# Raw source offsets 0xe050--0xe62f; named dump lines 2953--3045.
ROAD_SPAWNS = (
    (720, 11, 320, 112, 0, 80, 2, 1500),
    (730, 11, 304, 96, 0, 80, 0, 1500),
    (740, 11, 288, 80, 0, 80, 1, 1500),
    (750, 11, 256, 64, 0, 80, 1, 1500),
    (950, 9, 64, 112, 0, 80, 2, 1500),
    (960, 9, 80, 96, 0, 80, 0, 1500),
    (970, 9, 96, 80, 0, 80, 1, 1500),
    (980, 9, 128, 64, 0, 80, 1, 1500),
    (1180, 11, 224, 112, 0, 80, 2, 1500),
    (1190, 9, 64, 112, 0, 80, 2, 1500),
    (1200, 11, 288, 96, 0, 80, 0, 1500),
    (1210, 9, 128, 96, 0, 80, 0, 1500),
    (1220, 11, 320, 80, 0, 80, 1, 1500),
    (1230, 9, 96, 80, 0, 80, 1, 1500),
    (1240, 11, 256, 64, 0, 80, 1, 1500),
    (1250, 9, 160, 64, 0, 80, 1, 1500),
    (1310, 11, 224, 112, 0, 80, 1, 1500),
    (1320, 9, 64, 112, 0, 80, 1, 1500),
    (1330, 11, 288, 96, 0, 80, 1, 1500),
    (1340, 9, 128, 96, 0, 80, 1, 1500),
    (1350, 11, 320, 80, 0, 80, 1, 1500),
    (1360, 9, 96, 80, 0, 80, 1, 1500),
    (1370, 11, 256, 64, 0, 80, 2, 1500),
    (1380, 9, 160, 64, 0, 80, 2, 1500),
    (1440, 11, 224, 112, 0, 80, 1, 1500),
    (1450, 9, 32, 112, 0, 80, 1, 1500),
    (1460, 11, 288, 96, 0, 80, 1, 1500),
    (1470, 9, 128, 64, 0, 80, 1, 1500),
    (1480, 11, 352, 80, 0, 80, 1, 1500),
    (1490, 9, 64, 80, 0, 80, 1, 1500),
    (1500, 11, 256, 64, 0, 80, 2, 1500),
    (1510, 9, 160, 64, 0, 80, 2, 1500),
    (1530, 15, 224, 112, 0, 80, 1, 1500),
    (1536, 13, 64, 112, 0, 80, 1, 1500),
    (1542, 15, 288, 96, 0, 80, 1, 1500),
    (1548, 13, 128, 96, 0, 80, 1, 1500),
    (1554, 15, 320, 80, 0, 80, 1, 1500),
    (1560, 13, 96, 80, 0, 80, 1, 1500),
    (1566, 15, 256, 64, 0, 80, 2, 1500),
    (1572, 13, 160, 64, 0, 80, 2, 1500),
    (1578, 13, 64, 112, 0, 80, 1, 1500),
    (1584, 15, 288, 96, 0, 80, 1, 1500),
    (1590, 13, 128, 96, 0, 80, 1, 1500),
    (1596, 15, 320, 80, 0, 80, 1, 1500),
    (1602, 13, 96, 80, 0, 80, 1, 1500),
    (1608, 15, 256, 64, 0, 80, 2, 1500),
    (1614, 13, 160, 64, 0, 80, 2, 1500),
)


def drop_power_or_points(actor, count):
    """Source opcode119: one big P + small P, or all points at full power."""
    stats = actor.ctx.item_stats
    if stats is not None and stats.power >= stats.max_power:
        actor.drop(1, count)
    elif count:
        actor.drop(2)
        actor.drop(0, count - 1)


def _signed(rng, value):
    # Opcode11 consumes a U16 even when value is zero.
    return value if rng.integers(0, 2) else -value


def hermite_controls(start, end, tangent_start, tangent_end):
    """Exact Hermite-to-Bezier conversion; mode7 arguments are tangents."""
    return (
        (start[0] + tangent_start[0] / 3, start[1] + tangent_start[1] / 3),
        (end[0] - tangent_end[0] / 3, end[1] - tangent_end[1] / 3),
    )


class RoadDeathGhost(TH07Enemy):
    """Sub6/7 -> Sub4: the defeated ghost's 120-frame exit animation."""

    hp = 10
    score = 0
    sprite = ""

    async def run(self):
        self.set_interaction(interactable=False, damageable=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(31)
        start = self.source_position
        end = (start[0] - 8, start[1] - 150)
        controls = hermite_controls(
            start, end, (_signed(self.rng, 144), 35),
            (_signed(self.rng, 144), _signed(self.rng, 32)),
        )
        self.spawn_task(self.move_curve_source(end, *controls, 120), immediate=True)
        await self.wait(80)
        # Opcode128 is an ANM interrupt, not a new gameplay phase. The current
        # local rect export does not reproduce the source ANM interrupt body.
        self.source_animation_interrupt = 1
        await self.wait(40)


class RoadGhost(TH07Enemy):
    """Sub9/11/13/15 appearance followed by Sub10/12/14/16 shooting."""

    sprite = ""

    def __init__(self, *, sub=9, hp=80, item=0, score=1500):
        super().__init__()
        self.source_sub = sub
        self.hp = hp
        self.source_item = item
        self.score = score
        self.protected_until = float("inf")
        self._shooting = False
        self.on_death = self._after_death

    def update(self):
        active = super().update()
        if active and self._shooting:
            frame, _ = self.get_render_frame()
            if frame is None:
                raise RuntimeError('the source road ghost needs its original sprite for OOB culling')
            x, y = self.source_position
            if (x + frame.width / 2 < 0 or x - frame.width / 2 > 384
                    or y + frame.height / 2 < 0 or y - frame.height / 2 > 448):
                # Natural OOB is despawn, not defeat: no items/callback/score.
                self.dispose()
                active = False
        return active

    def damage(self, amount, *, source='shot', attack_index=-1, attack_generation=-1, region=0):
        if self.time < self.protected_until:
            return
        super().damage(
            amount, source=source, attack_index=attack_index,
            attack_generation=attack_generation,
            region=region,
        )

    def _after_death(self, enemy):
        self.drop(self.source_item)
        if self.source_sub in (13, 15):
            # Sub7: opcode119(4), opcode154(3). The latter is POINT items,
            # despite the supplied dump calling it "spawnParticleTrail".
            drop_power_or_points(self, 4)
            self.drop(1, 3)
        x, y = self.source_position
        self.spawn_source(RoadDeathGhost, x, y)

    async def run(self):
        self.set_interaction(interactable=False, damageable=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(30)
        target = self.source_position
        start = (target[0] + 14, target[1] + 161)
        controls = hermite_controls(
            start, target, (_signed(self.rng, 144), 16),
            (_signed(self.rng, 144), _signed(self.rng, 32)),
        )
        self.set_position(px(start[0]), py(start[1]))
        self.spawn_task(self.move_curve_source(target, *controls, 80), immediate=True)
        await self.wait(80)
        self.animate(27)
        self.set_hitbox(Hitbox.box(24 / 192, 24 / 192))
        self.set_interaction(interactable=True, damageable=True)
        self._shooting = True
        self.protected_until = self.time + 10
        direction = 0 if self.source_sub in (9, 13) else math.pi
        self.spawn_task(
            self.move_polar_source(direction, 0, accel=0.02), immediate=True,
        )
        self.commands = [(0, 1, 0, -1, -1, -1.0, -1.0)]
        color = 6 if self.source_sub in (9, 13) else 2
        for _ in range(28):
            speed = self.rng.random() * self.rank((1, 1, 2, 3)) + 0.5
            angle = self.rng.random() * math.tau - math.pi
            self.emit(
                6, color, self.rank((1, 3, 5, 5)), self.rank((1, 1, 1, 2)),
                speed, 0.5, angle, math.pi / 2, 515,
                commands=self.commands, aim_mode=3,
            )
            await self.wait(5)


class BackgroundMotes(TH07Enemy):
    """Timeline1 frame1 -> Sub1; sparse owner, particles stay in ParticlePool."""

    hp = 80
    score = 0
    sprite = ""

    async def _wait_weather(self, frames):
        remaining = float(frames)
        while remaining > 1e-8:
            await self.wait_control(1)
            remaining -= self.ctx.get_simulation_rate('background')

    async def run(self):
        self.set_interaction(interactable=False, damageable=False, visible=False)
        self.set_contact_hitbox(enabled=False)
        self.effect(31, 64)
        for count in (100, 1170):
            for _ in range(count):
                self.effect(31, 2)
                await self._wait_weather(4)
        while True:
            self.effect(31, 4)
            await self._wait_weather(4)


class RoadWave(Wave):
    """All 47 Timeline0 births, then its 300-frame gap before message2."""

    async def run(self):
        previous = 0
        for frame, sub, x, y, z, hp, item, score in ROAD_SPAWNS:
            await self.wait(frame - previous)
            enemy = RoadGhost(sub=sub, hp=hp, item=item, score=score)
            enemy.bind(self.ctx, px(x), py(y))
            enemy.start()
            self.ctx.add_enemy_script(enemy)
            previous = frame
        await self.wait(ROAD_END_FRAME - previous)


__all__ = [
    "ROAD_END_FRAME", "ROAD_SPAWNS", "RoadWave", "RoadGhost",
    "RoadDeathGhost", "BackgroundMotes", "drop_power_or_points",
    "hermite_controls",
]

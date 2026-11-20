"""Yuyuko's ten real stage-6 phases, translated from TH07 1.00b Sub28--73.

This file contains ordinary SpellCard/EnemyScript content, not an ECL VM.
The raw numeric dump is authoritative where the supplied named dump aliases
opcode114 (deadline) and opcode142 (damage protection) to the same name.
Projectile movement commands remain finite definitions for the shared pool.
Remaining original actor ANM transforms/trails are separately reported work.
"""

from __future__ import annotations

import math

import numpy as np

from src.core.collision_shapes import Hitbox
from src.game.stage.boss_base import BossPhase, BossPhaseType
from src.game.tasks import simulation_rate

from .common import TH07Enemy, TH07Spell, bullet_speed, damage_rule, px, py, source_laser
from .resources import source_sprite
from .road import drop_power_or_points, hermite_controls
from .youmu import (
    _clear_source_bullets, _clear_source_enemies, _set_source_bounds,
    normalize_angle, source_exit_angle,
)


YUYUKO_SOURCE_SUBS = (29, 43, 34, 50, 36, 52, 38, 55, 58, 62)
YUYUKO_SPELL_NAMES = (
    ('亡郷「亡我郷 -さまよえる魂-」', '亡郷「亡我郷 -宿罪-」',
     '亡郷「亡我郷 -道無き道-」', '亡郷「亡我郷 -自尽-」'),
    ('亡舞「生者必滅の理 -眩惑-」', '亡舞「生者必滅の理 -死蝶-」',
     '亡舞「生者必滅の理 -毒蛾-」', '亡舞「生者必滅の理 -魔境-」'),
    ('華霊「ゴーストバタフライ」', '華霊「スワローテイルバタフライ」',
     '華霊「ディープルーティドバタフライ」', '華霊「バタフライディルージョン」'),
    ('幽曲「リポジトリ・オブ・ヒロカワ -偽霊-」', '幽曲「リポジトリ・オブ・ヒロカワ -亡霊-」',
     '幽曲「リポジトリ・オブ・ヒロカワ -幻霊-」', '幽曲「リポジトリ・オブ・ヒロカワ -神霊-」'),
    ('桜符「完全なる墨染の桜 -封印-」', '桜符「完全なる墨染の桜 -亡我-」',
     '桜符「完全なる墨染の桜 -春眠-」', '桜符「完全なる墨染の桜 -開花-」'),
    ('「反魂蝶 -一分咲-」', '「反魂蝶 -参分咲-」', '「反魂蝶 -伍分咲-」', '「反魂蝶 -八分咲-」'),
)


def _cmd(kind, duration, first=-1.0, second=-1.0, *, index=0, continued=0, loops=-1):
    return (index, kind, continued, duration, loops, first, second)


def _settle(boss, result):
    if result.reason == 'timeout' and not result.is_survival:
        # Enemy::HandleTimerCallback uses RemoveAllBullets(10): no item
        # reward on a failed timeout. The source despawn ANM is separate work.
        boss.ctx.clear_all_bullets()
        boss.ctx.clear_all_lasers()
        _clear_source_enemies(boss.ctx)
    elif result.reason == 'defeated':
        # EndSpellcard / nonspell death converts the live field, not just the
        # new phase's own emit groups. Settlement score formulas remain partial.
        _clear_source_bullets(boss.ctx)
        _clear_source_enemies(boss.ctx)
    if (result.phase_type is BossPhaseType.SPELLCARD
            and (result.reason == 'defeated' or result.is_survival and result.reason == 'timeout')
            and result.no_miss and result.no_bomb and result.capture_failure_reason is None):
        boss.ctx.add_score(result.bonus - result.bonus % 10)
        boss.ctx._th07_stage6_state.captured += 1


def _next_nonspell(boss, result):
    # Life callback/timeout enters its matching card. A lethal overkill follows
    # raw107 and skips that card, rather than resurrecting the zero-HP phase.
    return boss.current_phase_index + (2 if result.reason == 'defeated' else 1)


def _bonus(boss, spell):
    if spell.is_survival:
        return 3_000_000
    duration = spell.time_limit
    drain = int(5_000_000 / (duration + 10))
    score = max(0, int(5_000_000 - spell.elapsed_seconds * drain))
    return score - score % 10


class _YuyukoScript(TH07Spell):
    clear_on_end = False

    def _bounds(self, bounds):
        self._source_bounds = bounds
        _set_source_bounds(self.boss, bounds)

    def _move(self, x, y, frames=60, easing=4):
        previous = getattr(self, '_motion', None)
        if previous is not None and not previous.done:
            previous.cancel()
        self._motion = self.spawn_task(self.move_source(x, y, frames, easing=easing), immediate=True)
        return self._motion

    def _random_move(self, frames=60, speed=1.5, easing=4):
        angle = source_exit_angle(self, self._source_bounds)
        self.source_move_angle = normalize_angle(angle)
        x, y = self.source_position
        self._move(x + math.cos(angle) * frames * speed,
                   y + math.sin(angle) * frames * speed, frames, easing)

    def _periodic(self, interval, callback):
        previous = getattr(self, '_periodic_handle', None)
        if previous is not None:
            previous.cancel()

        async def run():
            while True:
                await self.wait(interval)
                callback()
        self._periodic_handle = self.spawn_task(run())
        return self._periodic_handle

    def _normal_start(self, protect=300, bounds=(32, 48, 352, 128)):
        self.boss.set_interaction(damageable=True, interactable=True)
        self.boss.set_hitbox(Hitbox.box(48 / 192, 64 / 192))
        self.boss.set_contact_hitbox(Hitbox.box(32 / 192, (64 / 1.5) / 192))
        self.protected_until = self.time + protect
        self._bounds(bounds)
        self.animate(147)

    async def _prepare(self, position=(192, 112), *, protect=240, bounds=(64, 48, 320, 128)):
        _clear_source_enemies(self.ctx)
        _clear_source_bullets(self.ctx)
        self.boss.set_interaction(damageable=False, interactable=True)
        self.boss.clear_movement_bounds()
        self._move(*position, 120)
        # All difficulty branches reset local ECL time before the same 120
        # frames. The named dump's cumulative //240, //360 are not extra waits.
        await self.wait(120)
        self.boss.set_interaction(damageable=True)
        self.protected_until = self.time + protect
        self._bounds(bounds)
        self.animate(147)

    async def _particle_rows(self, rows, count):
        for _ in range(rows):
            self.effect(33, count, -8355585)
            await self.wait(4)

    def _between_cards(self, background):
        _clear_source_bullets(self.ctx)
        _clear_source_enemies(self.ctx)
        self.background(background)
        drop_power_or_points(self, 8)
        self.drop(1, 6)


class _YuyukoEntrance(TH07Spell):
    async def run(self):
        self.boss.set_interaction(damageable=False)
        self.boss.set_contact_hitbox(enabled=False)
        self.boss.set_hitbox(Hitbox.box(48 / 192, 64 / 192))
        self.boss.clear_movement_bounds()
        self.boss.set_position(px(192), py(-32))
        self.animate(147)
        await self.move_source(192, 112, 150, easing=4)
        while True:
            await self.wait(10000)


async def enter_yuyuko(boss, ctx):
    """Sub28 entrance; the stage/message controller owns its cancellation."""
    entrance = _YuyukoEntrance()
    entrance.bind(boss, ctx)
    try:
        await entrance.run()
    finally:
        entrance.dispose()


class YuyukoNonspell1(_YuyukoScript):
    """Sub29 and its time-consuming synchronous Sub30--33 calls."""

    async def run(self):
        self._normal_start(240)
        self.cycles = 0
        for _ in range(6):
            self.effect(6)
            await self.wait(10)
        while True:
            await self._petals(30)
            await self.wait(100)
            self._random_move()
            await self._petals(31)
            await self.wait(100)
            self._random_move()
            await self._particle_rows(8, 12)
            for sub in (33, 32, 33, 32):
                await self._petals(sub)
            await self.wait(100)
            self._random_move()
            self.cycles += 1
            await self.wait(100)

    async def _petals(self, sub):
        # [10024] is angle TO PLAYER, not the actor's movement direction.
        a = self.aim_source() - math.pi / 2
        b = self.aim_source() + math.pi / 2
        ways = 8 if sub == 32 else self.rank((4, 8, 12, 16) if sub < 32 else (6, 8, 12, 16))
        bases = {30: (1.6, 1.8, 1.8, 2.1), 31: (2, 2.4, 2.8, 3),
                 32: (2, 2.4, 2.8, 3), 33: (1.6, 1.8, 2.1, 2.4)}
        speed = self.rank(bases[sub]) + self.cycles * .2
        count = 15 if sub < 32 else 30
        for _ in range(count):
            a, b = normalize_angle(a), normalize_angle(b)
            radius = {30: 32, 31: 32, 32: 64, 33: 24}[sub]
            offset = (math.cos(a) * radius, math.sin(a) * radius)
            main_angle = b if sub < 32 else (a - math.pi / 2 if sub == 32 else b + math.pi / 2)
            self.emit(2, 8 if sub in (30, 32) else 13, ways, 1, speed, 1,
                      normalize_angle(main_angle),
                      self.rank((math.pi/12, math.pi/15, math.pi/16, math.pi/17)) if sub < 32 else math.pi/16,
                      517, aim_mode=1, offset=offset, rank_boost=(0, 0, 0, 0, 0, 0))
            await self.wait(2)
            radius = {30: 64, 31: 16, 32: 16, 33: 96}[sub]
            theta = b if sub == 30 else a
            offset = (math.cos(theta) * radius, math.sin(theta) * radius)
            if sub < 32:
                extra_speed, extra_angle, extra_ways, mode = speed - .5, b if sub == 30 else a, 6, 3
            else:
                extra_speed = speed - (.3 if sub == 32 else .1)
                extra_angle, extra_ways, mode = (b + math.pi/2 if sub == 32 else a - math.pi/2), 5, 1
            self.emit(7, 6 if sub in (30, 32) else 4, extra_ways, 1,
                      extra_speed, 1, normalize_angle(extra_angle), math.pi/10, 5,
                      aim_mode=mode, offset=offset, rank_boost=(0, 0, 0, 0, 0, 0))
            a += math.pi/15
            b -= math.pi/15
            if self.source_distance() < 64:
                self.emit(3 if sub == 32 else 2, 2, 16 if sub in (30, 32) else 7,
                          1, 4, 1, self.rng.uniform(-math.pi, math.pi), math.pi/80, 0,
                          aim_mode=3 if sub in (30, 32) else 0,
                          rank_boost=(0, 0, 0, 0, 0, 0))
            await self.wait(2)


class YuyukoNonspell2(_YuyukoScript):
    """Sub34/35: periodic opposing curves plus increasingly frequent bubbles."""

    async def run(self):
        self._between_cards(2)
        self._normal_start()
        self._move(192, 112)
        await self._particle_rows(30, 12)
        await self._particle_rows(30, 12)
        await self.wait(30)
        self.animate(147)
        await self.wait(15)
        self.ctx.flash_screen(frames=60)
        await self.wait(60)
        self.boss.set_secondary_hitbox(Hitbox.box(356 / 192, 32 / 192))
        await self.wait(60)
        self._periodic(self.rank((13, 11, 11, 11)), self._curves)
        delay = 120
        while True:
            await self.wait(delay)
            self.emit(10, 1, self.rank((3, 9, 11, 13)), 1,
                      self.rank((2.4, 2.8, 3, 3.2)), 1, 0,
                      self.rank((math.pi/8, math.pi/15, math.pi/16, math.pi/17)), 4,
                      aim_mode=0, rank_boost=(0, 0, 0, 0, 0, 0))
            delay = max(60, delay - 5)

    def _curves(self):
        offset = (self.rng.uniform(-176, 176), self.rng.uniform(-24, 24))
        self.emit(3, 4, 3, 1, 1, 1, 0, math.pi/6, 516, aim_mode=0, offset=offset,
                  rank_boost=(0, 0, 0, 0, 0, 0))
        for turn in (math.pi/120, -math.pi/120):
            commands = (_cmd(32, 80, 0, 0), _cmd(32, 60, .01, turn, index=1))
            self.emit(3, 1, 3, 1, 1, 1, 0, math.pi/6, 36, aim_mode=0,
                      commands=commands, offset=offset, rank_boost=(0, 0, 0, 0, 0, 0))


class YuyukoNonspell3(_YuyukoScript):
    """Sub36/37: eight independent emission offsets and their saved turn rates."""

    async def run(self):
        self._between_cards(3)
        self._normal_start()
        self._move(192, 112)
        await self.wait(60)
        self.turns = np.zeros(8, np.float64)
        self.callback_count = 0
        self._periodic(11, self._side_emitters)
        delay = 200
        while True:
            await self.wait(delay)
            self.emit(10, 1, self.rank((5, 9, 11, 11)), 1,
                      self.rank((.8, .8, 1, 1.2)), 1, 0,
                      self.rank((math.pi/8, math.pi/12, math.pi/14, math.pi/16)), 2,
                      aim_mode=0, rank_boost=(0, 0, 0, 0, 0, 0))
            delay = max(80, delay - 5)

    def _side_emitters(self):
        n = self.callback_count
        offsets = ((128, -16), (96, 0), (64, 16), (-128, -16),
                   (-96, 0), (-64, 16), (160, 0), (-160, 0))
        gates = (0, 2, 4, 6, 1, 7, 3, 5)
        angles = (math.pi/4, 3*math.pi/8, math.pi/2, 3*math.pi/4,
                  5*math.pi/8, math.pi/2, math.pi/2, math.pi/2)
        for i, (offset, gate, angle) in enumerate(zip(offsets, gates, angles)):
            if (n + gate) % 8 < 4:
                self.emit(9, 4, self.rank((3, 3, 5, 7)) if i in (0, 3) else 3,
                          1, self.rank((1.8, 2, 2.2, 2.5)), 1, angle, math.pi/6,
                          546, aim_mode=3, offset=offset,
                          commands=(_cmd(32, 80, 0, float(self.turns[i])),),
                          rank_boost=(0, 0, 0, 0, 0, 0))
        delta = .0004908739
        if 20 <= n < 40:
            self.turns += np.asarray((1, 1, 1, -1, -1, -1, 1, -1)) * delta
        elif 60 <= n < 100:
            self.turns[[0, 2]] -= delta
            self.turns[[3, 5]] += delta
        elif 100 <= n < 120:
            self.turns += np.asarray((1, -1, 1, -1, 1, -1, 0, 0)) * delta
        elif n >= 120:
            n = 0
        self.callback_count = n + 1


class YuyukoNonspell4(_YuyukoScript):
    """Sub38--42: four replacement periodic callbacks, not four concurrent ones."""

    async def run(self):
        self.boss.set_secondary_hitbox(None)
        self._between_cards(4)
        self._normal_start()
        self._move(192, 112)
        await self.wait(180)
        while True:
            for pattern in range(4):
                self._periodic(8, lambda pattern=pattern: self._aimed_pairs(pattern))
                await self.wait(20)
                self._random_move()
                if self.diff:
                    self.emit(8, 5, 32, self.rank((1, 1, 2, 3)),
                              self.rank((0, 1.6, 2.2, 2.8)), 1,
                              self.rng.uniform(-math.pi, math.pi),
                              math.pi/6 if self.diff == 1 else 0, 512, aim_mode=3,
                              rank_boost=(0, 0, 0, 0, 0, 0))
                await self.wait(80 if pattern == 3 else 60)

    def _aimed_pairs(self, pattern):
        if pattern in (0, 2):
            self._pair(6, 0, 0, math.pi/4 if pattern == 0 else math.pi/2, 658)
        if pattern:
            tilt, color = ((math.pi/8, 8) if pattern == 1 else
                           (math.pi/6, 10) if pattern == 2 else (math.pi/4, 8))
            for sign, flags in ((1, 658), (-1, 146)):
                # Sub41/42 keep the initial +/-pi/8 aim even when their later
                # re-aim offset is pi/6 or pi/4.
                self._pair(color, sign * tilt, -sign * math.pi/8, math.pi/4, flags)
            if pattern == 3:
                self._pair(8, 0, 0, math.pi/4, 658)
                self._pair(10, math.pi/6, -3*math.pi/8, math.pi/4, 658)
                self._pair(10, -math.pi/6, 3*math.pi/8, math.pi/4, 146)

    def _pair(self, color, turn, initial, spread, flags):
        commands = (_cmd(128, 60, turn, .1, loops=1),
                    _cmd(16, 80, .038, -999, index=1))
        self.emit(6, color, 2, 1, self.rank((3.5, 3.8, 3.8, 4.1)), 1,
                  initial, spread, flags, aim_mode=0, commands=commands,
                  rank_boost=(0, 0, 0, 0, 0, 0))


class LostHometown(_YuyukoScript):
    """Sub43--49: callback arrows remain active during the synchronous lasers."""

    async def run(self):
        await self._prepare((192, 64), protect=300)
        self._move(192, 70)
        cycles = 0
        while True:
            self.callback_angle = -math.pi/2
            self._periodic(9, lambda: self._arrows(False))
            await self.wait(30)
            await self._laser_fan(False, cycles)
            cycles += 1
            self.callback_angle = -math.pi/2
            self._periodic(9, lambda: self._arrows(True))
            await self.wait(30)
            await self._laser_fan(True, cycles)
            cycles += 1

    def _arrows(self, mirrored):
        def burst(angle, reverse, extra=False):
            speed = self.rng.uniform(3.7 if extra else self.rank((3.7, 3.7, 4, 4.2)),
                                     4 if extra else self.rank((4, 4, 4.3, 4.5)))
            turn = math.pi/60 if reverse else -math.pi/60
            commands = (_cmd(8192, 120),
                        _cmd(32, 30, -1/30, turn, index=1, continued=1),
                        _cmd(32, 20, -.05, -turn, index=2),
                        _cmd(32, 20, 0, turn*1.5, index=3))
            self.emit(6, 8, 1 if extra else self.rank((5, 5, 1, 3)), 1, speed, 1,
                      angle, math.pi/6, 8736, aim_mode=1, commands=commands,
                      rank_boost=(0, 0, 0, 0, 0, 0))
            self.emit(6, 10 if reverse else 13, self.rank((4, 4, 2, 2)),
                      1, speed, 1, angle, math.pi/6, 8736, aim_mode=1,
                      commands=commands, rank_boost=(0, 0, 0, 0, 0, 0))
        burst(normalize_angle(self.callback_angle), mirrored)
        if self.diff >= 2:
            burst(normalize_angle(math.pi - self.callback_angle), not mirrored, True)
        step = self.rng.uniform(math.pi/80, math.pi/40)
        self.callback_angle += step if mirrored else -step

    async def _laser_fan(self, mirrored, cycle):
        start = 0 if mirrored else -math.pi
        color = 4 if mirrored else 2
        lasers = [source_laser(
            self, start, start=24, end=540, length=540, width=32,
            warning=120, active=270+i*10, fade=30, hitbox_delay=100,
            hitbox_fade_frames=20, color=color,
        ) for i in range(5)]
        base = cycle * (.06544985 if not mirrored else -.06544985)
        base += (self.rank((math.pi/4, math.pi/2, math.pi/2, math.pi/2)) if not mirrored
                 else self.rank((-5*math.pi/4, -3*math.pi/2, -3*math.pi/2, -3*math.pi/2)))
        targets = np.asarray([base + (1 if mirrored else -1)*i*math.pi/16 for i in range(5)])
        await self.wait(120)
        for frame in range(300):
            k = 1 - (1 - frame / 300)**3  # raw27 mode5, not generic smoothstep.
            for laser, target in zip(lasers, targets):
                laser.angle = -math.degrees(start + (target - start) * k)
            await self.wait(1)


class MortalLaw(_YuyukoScript):
    """Sub50/51, including saved periodic counters and the late bubble gate."""

    async def run(self):
        await self._prepare()
        self._move(192, 112)
        self.rotation = 0.0
        self.calls = self.rotation_calls = self.bubble_calls = 0
        self._periodic(3, self._wheel)
        while True:
            await self.wait(300)

    def _wheel(self):
        self.calls += 1
        branch = self.calls % 4
        if branch == 0:
            self.emit(8, 4, 4, 1, 1.4, 1, self.rotation, math.pi/6, 512,
                      aim_mode=3, rank_boost=(0, 0, 0, 0, 0, 0))
        elif branch == 1:
            self.bubble_calls += 1
            if self.bubble_calls >= 16 and self.bubble_calls % 8 < self.rank((2, 5, 6, 7)):
                self.emit(10, 1, 1, 1, self.rank((3.4, 3.4, 3.7, 3.7)), 1,
                          self.rotation, math.pi/6, 644,
                          aim_mode=1 if self.diff < 2 else 3,
                          commands=(_cmd(128, 100, 0, self.rank((2, 2.4, 2.8, 3)), loops=1),),
                          rank_boost=(0, 0, 0, 0, 0, 0))
        else:
            self.emit(8, 3 if branch == 2 else 2, 2, 1, 3.2 if branch == 2 else 3,
                      1, self.rotation, math.pi/6, 576, aim_mode=3,
                      commands=(_cmd(64, 100, math.pi/2 if branch == 2 else -math.pi/2,
                                     1.1, loops=1),), rank_boost=(0, 0, 0, 0, 0, 0))
        self.rotation_calls += 1
        self.rotation = normalize_angle(self.rotation + (.04759989 if self.rotation_calls % 600 < 300 else -.04759989))


class ButterflyPhantom(TH07Enemy):
    """ExIns17 -> Sub53: a real sparse projectile enemy, not a bullet Task."""

    hp = 1
    score = 10
    sprite = ''

    def __init__(self, *, heading=0.0, fan_angle=0.0):
        super().__init__()
        self.heading = heading
        self.fan_angle = fan_angle

    async def run(self):
        self.set_interaction(damageable=False, interactable=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(12)
        factor = self.rank((1, 1, 1.4, 1.8))
        player = self.ctx.get_player()
        target = (player.x * 192 + 192, 224 - player.y * 192)
        start = self.source_position
        direction = (math.cos(self.heading), math.sin(self.heading))
        controls = hermite_controls(start, target,
                                    (direction[0]*400*factor, direction[1]*400*factor),
                                    (direction[0]*100*factor, direction[1]*100*factor))
        self.spawn_task(self.move_curve_source(target, *controls, 120), immediate=True)
        await self.wait(120)
        for color, ways, speed, turn, mode, spread in (
            (4, 1, .8, math.pi/40, 3, math.pi/6),
            (3, 1, 1.46, -math.pi/40, 3, math.pi/6),
            (2, 2, 2.4, math.pi/35, 1, math.pi/16),
            (1, 2, 3.2, -math.pi/35, 1, math.pi/16),
        ):
            self.emit(8, color, ways, 1, speed, 1, self.fan_angle, spread, 12836,
                      aim_mode=mode, commands=(_cmd(32, 80, 0, turn),
                                              _cmd(8192, 300, index=1, continued=1)),
                      rank_boost=(0, 0, 0, 0, 0, 0))


class GhostButterfly(_YuyukoScript):
    """Sub52/54 and all three butterfly ExIns, using complete snapshots."""

    async def run(self):
        await self._prepare()
        self._move(192, 112)
        self.reverse_speed = .6
        await self.wait(60)
        periodic = None
        while True:
            self.emit(8, 4, 8, 1, .5, 1, 0, math.pi/6, 12804, aim_mode=3,
                      commands=(_cmd(8192, 300, continued=1),),
                      rank_boost=(0, 0, 0, 0, 0, 0))
            for _ in range(8):
                self._reverse_fans()
                await self.wait(10)
            self._spawn_phantoms()
            # Normal EnemyScript births begin on the next update, independent
            # of pool-slot order. Align the first polling sample with that
            # actual birth; otherwise the 120-frame poll ends one update before
            # Sub53 emits and spuriously adds another eight mother bullets.
            await self.wait_control(1)
            ring_angle = self.rng.uniform(-math.pi, math.pi)
            interval = 60
            def periodic_ring():
                nonlocal ring_angle
                self.emit(7, 3, self.rank((12, 18, 18, 18)), self.rank((1, 2, 2, 3)),
                          self.rank((1.5, 2, 2.5, 2.5)), .8, ring_angle, math.pi/16, 512,
                          aim_mode=3, rank_boost=(0, 0, 0, 0, 0, 0))
                ring_angle += math.pi/120
            periodic = self._periodic(interval, periodic_ring)
            self.reverse_speed = .75
            while True:
                for _ in range(12):
                    self._blue_count()
                    await self.wait(10)
                self.reverse_speed = min(2, self.reverse_speed + .25)
                for _ in range(8):
                    if self._blue_count() == 0:
                        break
                    await self.wait(10)
                else:
                    self._spawn_phantoms()
                    await self.wait_control(1)
                    interval = max(40, interval - 4)
                    periodic.cancel()
                    periodic = self._periodic(interval, periodic_ring)
                    continue
                break

    def _butterflies(self):
        snapshot = self.ctx.read_bullets(fields=('pos', 'angle', 'sprite_idx'))
        registry = self.ctx.bullet_pool.sprite_registry
        colors = np.asarray([registry.get_index(source_sprite(8, i)) for i in range(8)])
        return snapshot.select(np.isin(snapshot['sprite_idx'], colors))

    def _blue_count(self):
        snapshot = self._butterflies()
        blue = self.ctx.bullet_pool.sprite_registry.get_index(source_sprite(8, 4))
        return int(np.count_nonzero(snapshot['sprite_idx'] == blue))

    def _reverse_fans(self):
        # ExIns16 never kills or marks its mothers. Each invocation creates
        # another five-shot fan behind every currently alive butterfly.
        snapshot = self._butterflies()
        if not len(snapshot):
            return
        angles = np.repeat(snapshot['angle'] - 180, 5)
        angles += np.tile(np.asarray((0, 1, -1, 2, -2))*22.5, len(snapshot))
        positions = np.repeat(snapshot['pos'], 5, axis=0)
        radians = np.deg2rad(angles)
        positions[:, 0] -= np.cos(radians)*self.reverse_speed*4/192
        positions[:, 1] -= np.sin(radians)*self.reverse_speed*4/192
        indices = self.ctx.create_bullets_batch(
            positions=positions, angles=angles, speeds=float(bullet_speed(self.reverse_speed)),
            sprite_id=source_sprite(0, 6),
        )
        group = self.ctx.capture_bullets(indices)
        warmup = self.state.assets.manifest['bullet_spawns']['0']['fast']['end_frame']
        self.ctx.configure_bullet_birth(group, warmup_frames=warmup, motion_factor=.5)
        self.state.emitted += len(indices)
        self.state.dropped_bullets += len(positions)-len(indices)

    def _spawn_phantoms(self):
        snapshot = self._butterflies()
        blue = self.ctx.bullet_pool.sprite_registry.get_index(source_sprite(8, 4))
        mothers = snapshot.select(snapshot['sprite_idx'] == blue)
        self.ctx.flash_screen((207/255, 207/255, 1, 128/255), 12)
        # Original loops in pool-slot order. This is a bounded real-enemy birth
        # operation; each resulting actor is allowed its ordinary actor Task.
        for i, (position, angle) in enumerate(zip(mothers['pos'], mothers['angle'])):
            self.spawn_source(ButterflyPhantom, position[0]*192+192, 224-position[1]*192,
                              heading=-math.radians(float(angle)), fan_angle=-math.pi+i*math.pi/4)
        self.ctx.clear_bullet_group(snapshot.group, reason='converted')


class Hirokawa(_YuyukoScript):
    """Sub55--57: eight speed layers at saved absolute emission positions."""

    async def run(self):
        await self._prepare()
        self._move(192, 112)
        await self.wait(60)
        while True:
            self.sound(5)
            self._spiral(14, 4, math.pi/120)
            await self.wait(1)
            self._spiral(14, 4, -math.pi/120)
            await self.wait(8)
            ways = 14 if self.diff == 0 else 10
            self._spiral(ways, 6, math.pi/120, position=(80, 128))
            await self.wait(1)
            self._spiral(ways, 6, -math.pi/120, position=(304, 128))
            await self.wait(1)
            if self.diff >= 2:
                self._spiral(6 if self.diff == 2 else 10, 5, -math.pi/120,
                             position=(136, 144))
            await self.wait(1)
            if self.diff >= 2:
                self._spiral(6 if self.diff == 2 else 10, 5, math.pi/120,
                             position=(248, 144))
            await self.wait(60)
            self._random_move()
            await self.wait(60)
            self._returning_fan(10, 3, math.pi/120)
            await self.wait(10)
            self._random_move()
            await self.wait(60)
            self._returning_fan(12, 3, -math.pi/120)
            await self.wait(5)
            self._random_move()
            await self.wait(60)
            self._returning_fan(self.rank((10, 14, 16, 18)),
                                self.rank((3, 2, 3, 2)), math.pi/120)
            self._random_move()
            await self.wait(60)
            self._returning_fan(16, 3, -math.pi/120)
            self._move(192, 112, 80)
            await self.wait(80)

    def _spiral(self, ways, color, turn, *, position=None):
        accel = self.rank((.035, .042, .045, .047))
        decrement = self.rank((.007, .008, .008428572, .008714286))
        for _ in range(8):
            self.emit(8, color, ways, 1, .5, 1, 0, math.pi/4, 8752,
                      aim_mode=3, position=position,
                      commands=(_cmd(32, 120, .01, turn),
                                _cmd(8192, 200, index=1, continued=1),
                                _cmd(16, 80, accel, -999, index=2)),
                      rank_boost=(0, 0, 0, 0, 0, 0))
            accel -= decrement

    def _returning_fan(self, ways, color, turn):
        self.sound(5)
        accel = self.rank((.035, .045, .047, .049))
        decrement = self.rank((.0074285716, .008857143, .009142857, .009428571))
        angle = normalize_angle(self.aim_source() + math.pi)
        for _ in range(8):
            self.emit(8, color, ways, 1, .5, 1, angle,
                      self.rank((math.pi/10, math.pi/12, .24166097, .22439948)),
                      8880, aim_mode=1,
                      commands=(_cmd(32, 120, .013, turn),
                                _cmd(8192, 200, index=1, continued=1),
                                _cmd(128, 1, 0, -999, index=2, loops=1),
                                _cmd(16, 80, accel, -999, index=3)),
                      rank_boost=(0, 0, 0, 0, 0, 0))
            accel -= decrement


class PerfectCherryBlossom(_YuyukoScript):
    """Sub58--61, including the delayed declaration and changing callback rate."""

    async def run(self):
        _clear_source_bullets(self.ctx)
        _clear_source_enemies(self.ctx)
        drop_power_or_points(self, 10)
        self.drop(1, 10)
        self.protected_until = self.time + 120
        await self.wait(120)
        self.time_limit = 99
        self.set_timer(0)
        self.boss.declare_spell()
        await self._prepare((192, 96), protect=360, bounds=(64, 48, 320, 96))
        self._move(192, 96)
        await self.wait(60)
        self._bubble_ring(self.rank((24, 32, 38, 42)))
        await self.wait(60)
        self._source_attachment = self.boss.attach_animation('th07_stg6enm_script_153')
        self.boss.set_secondary_hitbox(Hitbox.box(356 / 192, 32 / 192))
        self.cycles = 0
        interval = 10
        await self.wait(100)
        try:
            while True:
                for index in range(3):
                    self._cherry_fan(2, normalize_angle(1.3962634 + index*math.tau/3), math.pi/120)
                await self.wait(60)
                self._random_move()
                await self.wait(140)
                for index in range(3):
                    self._cherry_fan(4, normalize_angle(-1.3962634 + index*math.tau/3), -math.pi/120)
                if self.diff >= 2 and self.cycles % 2 == 1:
                    self._bubble_ring(20)
                if interval >= 5:
                    interval -= 1
                    self._periodic(interval, self._falling_petals)
                self.cycles += 1
                await self.wait(120)
        finally:
            self._source_attachment.stop()

    def _cherry_fan(self, color, angle, turn):
        self.sound(7)
        accel = .03 if self.diff == 3 else .016
        for _ in range(4 if self.diff == 3 else 3):
            relative = angle
            for speed in (8, 6.5, 5, 3.5, 2, .5):
                self.emit(8, color, 2, 1, speed, .5, 0, math.pi/2, 8304,
                          aim_mode=0,
                          commands=(_cmd(64, 80, relative, .2, loops=1),
                                    _cmd(8192, 400, index=1, continued=1),
                                    _cmd(32, 120, .006, turn, index=2),
                                    _cmd(16, 60, accel, -999, index=3)),
                          rank_boost=(0, 0, 0, 0, 0, 0))
                relative = normalize_angle(relative + turn*8)
            accel -= .01 if self.diff == 3 else .008

    def _bubble_ring(self, ways):
        self.sound(7)
        accel = .04
        for _ in range(5):
            self.emit(10, 1, ways, 1, .5, 1, 0, math.pi/4, 8240, aim_mode=3,
                      commands=(_cmd(32, 80, .02, 0),
                                _cmd(8192, 200, index=1, continued=1),
                                _cmd(16, 80, accel, -999, index=2)),
                      rank_boost=(0, 0, 0, 0, 0, 0))
            accel -= .012

    def _falling_petals(self):
        # raw7 consumes GetRandomU32 even though this unused local never
        # changes the subsequent fixed style/color pair.
        self.rng.integers32(1, 5)
        accel, turn = 0, 0
        if self.cycles >= 6:
            accel = self.rng.uniform(0, .02)
            turn = self.rng.uniform(-math.pi/1000, math.pi/1000)
        elif self.cycles >= 3:
            turn = self.rng.uniform(-math.pi/1200, math.pi/1200)
        position = (self.rng.uniform(0, 384), self.rng.uniform(64, 224))
        speed = self.rng.uniform(.4, 1.1)
        self.emit(2, 4, 2, 1, speed, 1, math.pi/2, 0, 36, aim_mode=3,
                  position=position, commands=(_cmd(32, 50, accel, turn),),
                  rank_boost=(0, 0, 0, 0, 0, 0))


class ResurrectionEcho(TH07Enemy):
    """Sub63: independent 600-frame original animation actor."""

    hp = 1
    score = 10
    sprite = ''

    async def run(self):
        self.set_interaction(damageable=False, interactable=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(155)
        await self.wait(600)


class ResurrectionLasers(TH07Enemy):
    """Sub67/68: only the sparse owner rotates; lasers outlive its 60 frames."""

    hp = 10
    score = 10
    sprite = ''

    def __init__(self, *, count=3, mirrored=False):
        super().__init__()
        self.count = count
        self.mirrored = mirrored

    async def run(self):
        self.set_interaction(damageable=False, interactable=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(155)
        sign = -1 if self.mirrored else 1
        theta = math.pi/2 + sign * math.pi/(2*self.count)
        bases = [normalize_angle(theta + i*math.tau/self.count + sign*math.pi/3)
                 for i in range(self.count)]
        lasers = [source_laser(
            self, angle, start=64, end=448, length=448, width=16,
            warning=120, active=120, fade=60, hitbox_delay=90,
            hitbox_fade_frames=30, color=8 if self.mirrored else 4,
        ) for angle in bases]
        self.sound(16 if self.mirrored else 13)
        elapsed = 0.0
        while elapsed < 60:
            # Raw27 and raw54 both use the source out-quad mode4.
            t = elapsed/60
            offset = -sign * math.pi/3 * (1-(1-t)**2)
            for laser, base in zip(lasers, bases):
                laser.angle = -math.degrees(base + offset)
            elapsed = min(60, elapsed + simulation_rate(self))
            await self.wait(1)


class ResurrectionItems(TH07Enemy):
    """Sub70/71: expanding orbit, then the exact last-frame linear velocity."""

    hp = 1
    score = 10
    sprite = ''

    def __init__(self, *, heading=0.0, angular_speed=0.0, item=8, short=False):
        super().__init__()
        self.heading = heading
        self.angular_speed = angular_speed
        self.item = item
        self.short = short

    async def _orbit(self):
        center = np.asarray(self.source_position, np.float64)
        angle, radius, elapsed = self.heading, 0.0, 0.0
        velocity = np.zeros(2)
        while elapsed < 120:
            step = min(120-elapsed, simulation_rate(self))
            angle = normalize_angle(angle + self.angular_speed*step)
            radius += step
            point = center + radius * np.asarray((math.cos(angle), math.sin(angle)))
            velocity = point - np.asarray(self.source_position)
            self.set_position(px(point[0]), py(point[1]))
            elapsed += step
            await self.wait(1)
        while True:
            step = simulation_rate(self)
            self.set_position(self.x + velocity[0]*step/192,
                              self.y - velocity[1]*step/192)
            await self.wait(1)

    async def run(self):
        self.set_interaction(damageable=False, interactable=False)
        self.set_contact_hitbox(enabled=False)
        self.animate(12)
        self.sound(5)
        self.spawn_task(self._orbit(), immediate=True)
        await self.wait(30)
        for _ in range(10 if self.short else 30):
            self.drop(self.item)
            await self.wait(10 if self.short else 5)


_SOUL_COLORS = (-1, -1, -32640, -32640, -8323200, -8323200,
                -8355585, -8355585, -128, -128)


async def _soul_particles(owner):
    # Effect32's full ANM transform/rotation is intentionally still partial in
    # common.effect; preserve original count/color/time instead of fake trails.
    for _ in range(6):
        for color in _SOUL_COLORS:
            await owner.wait(1)
            owner.effect(32, 1, color)
        owner.sound(7)
    owner.sound(18)
    owner.effect(32, 64, -8355585)


class ResurrectionButterfly(_YuyukoScript):
    """Sub62--72: delayed 67-second survival card, not a fake HP phase."""

    is_survival = True
    is_timeout = True

    async def run(self):
        self.background(5)
        # Sub72 is a synchronous 60-frame call; the +480 prelude begins AFTER
        # it returns. Only then does raw111 reset the real countdown.
        _clear_source_bullets(self.ctx)
        _clear_source_enemies(self.ctx)
        self.boss.set_interaction(damageable=False, interactable=False)
        self.boss.set_contact_hitbox(enabled=False)
        self.boss.clear_movement_bounds()
        heading = self.rng.uniform(-math.pi, math.pi)
        x, y = self.source_position
        self._move(x + math.cos(heading)*9, y + math.sin(heading)*9)
        await _soul_particles(self)
        self.protected_until = self.time + 240
        self.animate(154)
        self.state.trace('bgm.fade', seconds=3)
        if self.state.audio_enabled:
            self.ctx.stop_bgm(fade_ms=3000)
        await self.wait(120)
        self.spawn_source(ResurrectionEcho, *self.source_position)
        await self.wait(360)
        self.state.bgm(2)
        self.time_limit = 67
        self.set_timer(0)
        _clear_source_bullets(self.ctx)
        _clear_source_enemies(self.ctx)
        self.boss.declare_spell()
        self._move(192, 96, 120)
        self.protected_until = self.time + 360
        await self.wait(120)
        self._move(192, 112)
        await self.wait(60)
        self._bounds((128, 96, 256, 128))
        self.animate(154)
        ways, item_count, speed = (20 if self.diff == 0 else 28), 6, .5
        while True:
            angle = self.rng.uniform(-math.pi, math.pi)
            self.spawn_source(ResurrectionLasers, *self.source_position, count=item_count//2)
            self.spawn_source(ResurrectionLasers, *self.source_position,
                              count=item_count//2, mirrored=True)
            for wave in range(6):
                self._layers(ways, 3 if wave % 2 == 0 else 2, angle, 0, speed,
                             layers=3 if wave % 2 == 0 else 2)
                if wave < 5:
                    await self.wait(10)
                    angle = normalize_angle(angle + math.pi/ways)
            await self.wait(120)
            for index, count in enumerate((32, 32, 38, 40)):
                self.spawn_source(
                    ResurrectionItems, *self.source_position,
                    heading=0 if index == 1 else math.pi,
                    angular_speed=-math.pi/50 if index == 1 else math.pi/50,
                    item=8 if index < 2 else index-2, short=index >= 2,
                )
                # raw count1 grows on H and shrinks by five on L; L adds a
                # second speed layer (.3), it does NOT swap count1/count2.
                count += 3 if self.diff == 2 else -5 if self.diff == 3 else 0
                self._layers(count, 1, self.rng.uniform(-math.pi, math.pi),
                             (1 if index % 2 == 0 else -1) * math.pi/(600 if index < 2 else 300),
                             .8, speed_layers=2 if self.diff == 3 else 1)
                if index < 3:
                    await self.wait(30)
            self._random_move(speed=.2, easing=0)
            await self.wait(60)
            if self.diff >= 2:
                self._layers(24, 0, math.pi/2, 0, speed, style=10, aim_mode=5)
            speed += .08
            ways += 3
            item_count += 2
            await self.wait(95)

    def _layers(self, ways, color, angle, turn, speed, *, layers=3,
                style=8, aim_mode=3, speed_layers=1):
        accel = .06
        for _ in range(layers):
            self.emit(style, color, ways, speed_layers, speed,
                      .3 if speed_layers == 2 else 1, angle,
                      0 if speed_layers == 2 else math.pi/4, 8752, aim_mode=aim_mode,
                      commands=(_cmd(32, 120, .01, turn),
                                _cmd(8192, 200, index=1, continued=1),
                                _cmd(16, 80, accel, -999, index=2)),
                      rank_boost=(0, 0, 0, 0, 0, 0))
            accel -= .065 if layers == 2 else .0325


class _YuyukoFinish(TH07Spell):
    async def run(self):
        self.boss.set_interaction(damageable=False, interactable=False)
        self.boss.set_contact_hitbox(enabled=False)
        with self.ctx.slow_motion(.5):
            await _soul_particles(self)
        with self.ctx.slow_motion(.25):
            _clear_source_bullets(self.ctx)
            _clear_source_enemies(self.ctx)
            await self.wait(60)
        self.boss.set_interaction(visible=False)
        self.state.trace('boss.exit', source_sub=73)


async def finish_yuyuko(boss, ctx):
    """Sub73's actual exit; omit only the invisible +4000 deletion idle."""
    finish = _YuyukoFinish()
    finish.bind(boss, ctx)
    try:
        await finish.run()
    finally:
        finish.dispose()


def build_yuyuko_phases(difficulty):
    """Ten source phases; final two declarations reset their own countdowns."""
    if difficulty not in range(4):
        raise ValueError('TH07 difficulty must be 0, 1, 2, or 3')
    phases = []
    for index, (normal, card, hp, threshold) in enumerate((
        (YuyukoNonspell1, LostHometown, 21000, 2100),
        (YuyukoNonspell2, MortalLaw, 32000, 3000),
        (YuyukoNonspell3, GhostButterfly, 32000, 3000),
        (YuyukoNonspell4, Hirokawa, 22000, 2200),
    )):
        phases.append(BossPhase(
            BossPhaseType.NONSPELL, hp=hp, time_limit=60,
            script_class=normal, hp_threshold=threshold,
            transition_rule=_next_nonspell, finish_rule=_settle,
            damage_rule=damage_rule,
        ))
        phases.append(BossPhase(
            BossPhaseType.SPELLCARD, hp=threshold, time_limit=65,
            script_class=card, name=YUYUKO_SPELL_NAMES[index][difficulty],
            bonus=5_000_000, carry_hp=True, declaration_blocks_spell=False,
            finish_rule=_settle, bonus_rule=_bonus, damage_rule=damage_rule,
        ))
    for index, (card, limit, hp) in enumerate((
        (PerfectCherryBlossom, 101, 6000), (ResurrectionButterfly, 76, 1),
    ), 4):
        phases.append(BossPhase(
            BossPhaseType.SPELLCARD, hp=hp, time_limit=limit,
            script_class=card, name=YUYUKO_SPELL_NAMES[index][difficulty],
            bonus=3_000_000 if index == 5 else 5_000_000,
            declaration_blocks_spell=False, auto_declaration=False,
            finish_rule=_settle, bonus_rule=_bonus, damage_rule=damage_rule,
        ))
    return phases


__all__ = [
    'YUYUKO_SOURCE_SUBS', 'YUYUKO_SPELL_NAMES', 'YuyukoNonspell1',
    'YuyukoNonspell2', 'YuyukoNonspell3', 'YuyukoNonspell4', 'LostHometown',
    'MortalLaw', 'GhostButterfly', 'Hirokawa', 'PerfectCherryBlossom',
    'ResurrectionButterfly', 'ButterflyPhantom', 'ResurrectionEcho',
    'ResurrectionLasers', 'ResurrectionItems', 'build_yuyuko_phases',
    'enter_yuyuko', 'finish_yuyuko',
]

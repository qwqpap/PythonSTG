"""Source-unit helpers for the hand-translated TH07 stage 6 content.

This is ordinary game content, not an ECL interpreter. Only finite burst
definitions are translated to the existing shared bullet stages. Actors use
the engine's existing coroutine scheduler; bullets never own Python tasks.
"""

from __future__ import annotations

from collections import deque
import math

import numpy as np
from numba import njit

from src.core.collision_shapes import Hitbox
from src.game.item import ItemType
from src.game.particle import ParticleEffect
from src.game.stage.boss_base import BossBase, BossPhaseType
from src.game.stage.enemy_script import EnemyScript
from src.game.stage.motion import EASINGS
from src.game.stage.spellcard import SpellCard
from src.game.tasks import simulation_rate, wait_frames

from .resources import install_resources, play_source_bgm, play_source_se, source_sprite


DIFFICULTIES = ('easy', 'normal', 'hard', 'lunatic')
SOURCE_EASINGS = {
    0: lambda t: t,
    1: lambda t: t * t,
    2: lambda t: t ** 3,
    3: lambda t: t ** 4,
    4: lambda t: 1 - (1 - t) ** 2,
    5: lambda t: 1 - (1 - t) ** 3,
    6: lambda t: 1 - (1 - t) ** 4,
}


def px(value):
    return (value - 192.0) / 192.0


def py(value):
    return (224.0 - value) / 192.0


def bullet_speed(value):
    """Pixels/frame -> existing Context author speed units (not pool units)."""
    return np.asarray(value) * (3600.0 / 192.0)


@njit(cache=True)
def _random_values(seed, count):
    values = np.empty(count, np.float32)
    for index in range(count):
        tmp = ((seed ^ 0x9630) - 0x6553) & 0xffff
        seed = (((tmp & 0xc000) >> 14) + tmp * 4) & 0xffff
        high = seed
        tmp = ((seed ^ 0x9630) - 0x6553) & 0xffff
        seed = (((tmp & 0xc000) >> 14) + tmp * 4) & 0xffff
        values[index] = np.float32((high << 16) | seed) / np.float32(4294967296.0)
    return seed, values


class SourceRng:
    """TH07 Global.cpp Rng, including f32 rounding and consumption count."""

    @staticmethod
    def warmup():
        """Prepare the batch kernel without consuming any content RNG state."""
        _random_values(0, 0)

    def __init__(self, seed=0):
        self.seed = int(seed) & 0xffff
        self.generation = 0

    def u16(self):
        tmp = ((self.seed ^ 0x9630) - 0x6553) & 0xffff
        self.seed = (((tmp & 0xc000) >> 14) + tmp * 4) & 0xffff
        self.generation += 1
        return self.seed

    def u32(self):
        return (self.u16() << 16) | self.u16()

    def integers32(self, low, high=None):
        if high is None:
            low, high = 0, low
        width = int(high) - int(low)
        return int(low) + (self.u32() % width if width else 0)

    def random(self, size=None):
        count = 1 if size is None else int(np.prod(size))
        self.seed, values = _random_values(self.seed, count)
        self.generation += count * 2
        return float(values[0]) if size is None else values.reshape(size)

    def uniform(self, low=0.0, high=1.0, size=None):
        return np.float32(low) + self.random(size) * np.float32(high - low)

    def integers(self, low, high=None, size=None):
        if high is None:
            low, high = 0, low
        width = int(high) - int(low)
        if width < 0:
            raise ValueError('source integer range must be nonnegative')
        def next_value():
            return int(low) + (self.u16() % width if width else 0)
        if size is None:
            return next_value()
        return np.fromiter((next_value() for _ in range(int(np.prod(size)))),
                           np.int32).reshape(size)


class PortState:
    """Stage-owned content state; bounded observations, no renderer dependency."""

    def __init__(self, ctx, *, asset_root=None, audio=True, resources=None):
        self.ctx = ctx
        self.rng = SourceRng(ctx.seed)
        self.assets = resources if resources is not None else install_resources(ctx, asset_root)
        self.diff = DIFFICULTIES.index(ctx.difficulty)
        self.audio_enabled = bool(audio and ctx.audio is not None)
        self.events = deque(maxlen=4096)
        self.is_spell = False
        self.background_label = 0
        self.background_controller = None
        self.emitted = 0
        self.dropped_bullets = 0
        self._next_tag = 6000
        self._command_cache = {}
        self._effects = {}
        self.cherry = 0
        self.cherry_plus = 0
        self.captured = 0
        ctx.set_item_collection_rule(self.collect_item)

    def trace(self, event, **data):
        self.events.append({'frame': self.ctx.runtime_frame, 'event': event, **data})

    def background(self, label):
        self.background_label = label
        self.trace('background.label', label=label)
        if self.background_controller is not None:
            self.background_controller.label(label)
        self.ctx.emit_event('th07.background.label', {'label': label})

    def play_se(self, index):
        if self.audio_enabled:
            return play_source_se(self.ctx, index)
        return False

    def bgm(self, index):
        self.trace('bgm', index=index)
        from .titles import music_title
        self.ctx.spawn_task(music_title(self.ctx, index))
        if self.audio_enabled:
            return play_source_bgm(self.ctx, index)
        return False

    def new_tag(self):
        self._next_tag += 1
        return self._next_tag

    def drop(self, item, x, y, count=1):
        types = {0: ItemType.POWER, 1: ItemType.POINT, 2: ItemType.POWER_LARGE,
                 3: ItemType.BOMB, 4: ItemType.POWER_FULL, 5: ItemType.EXTEND,
                 6: ItemType.POINT, 7: ItemType.FAITH, 8: ItemType.FAITH_MINOR,
                 9: ItemType.FAITH}
        for _ in range(int(count)):
            self.ctx.spawn_item(px(x), py(y), types[item], tag=60000 + item)

    def collect_item(self, stats, item):
        source_type = item.tag - 60000
        if source_type not in (6, 7, 8, 9):
            return False  # Existing generic item policy, not fake Cherry gain.
        if source_type == 8:
            self.cherry_plus += 30
            self.cherry += 70
        elif source_type == 7:
            self.cherry_plus += 1000 + self.captured * 100
        elif source_type == 9:
            stats.add_score(stats.graze // 40 * 10 + 300)
            self.cherry_plus += 100
        else:
            stats.add_score(100)
            self.cherry_plus += 20
        self.trace('item.source_collected', source_type=source_type,
                   cherry=self.cherry, cherry_plus=self.cherry_plus)
        # Full CherryMax/Border policies and source item sprites are still
        # separate content work; these counters are not a claimed full port.
        return True


def get_state(ctx):
    state = getattr(ctx, '_th07_stage6_state', None)
    if state is None:
        state = PortState(ctx)
        ctx._th07_stage6_state = state
    return state


# 引擎自机弹单发伤害（10）约为原作 TH07 单发伤害（约 40）的四分之一。
# 下面的规则按 TH07 EnemyManager 的伤害单位书写，所以进入 cap70 与各阶段
# 减伤之前，先把引擎伤害换算成原作单位；血量与节奏仍保持原作数值。
ENGINE_TO_SOURCE_DAMAGE = 4.0


def to_source_damage(amount):
    """把引擎伤害换算成 TH07 EnemyManager 的伤害单位。"""
    return float(amount) * ENGINE_TO_SOURCE_DAMAGE


def damage_rule(boss, hit):
    """EnemyManager.cpp: source phase reduction AFTER per-target cap70."""
    damage = min(70, int(to_source_damage(hit.amount)))
    phase = boss.phases[boss.current_phase_index]
    if phase.phase_type == BossPhaseType.SPELLCARD:
        if hit.source == 'shot':
            damage = damage // 7 if damage > 7 else int(damage != 0)
        elif not boss._spell_no_bomb:
            damage = int(damage / 2.5) if damage > 2 else int(damage != 0)
        else:
            damage = 0
    spell = boss.current_spellcard
    if spell.time < getattr(spell, 'protected_until', 0):
        damage //= 9
    return damage


class TH07Boss(BossBase):
    """Opt-in original frame-total damage policy, on the normal Boss runtime."""

    def _start_phase(self, index):
        if index < len(self.phases):
            state = get_state(self.ctx)
            state.is_spell = self.phases[index].phase_type == BossPhaseType.SPELLCARD
            if state.background_controller is not None:
                state.background_controller.set_spell(
                    False, kind='youmu' if self.id == 'th07_youmu' else 'yuyuko')
            state.trace('phase.start', boss=self.id, index=index,
                        name=self.phases[index].name)
        super()._start_phase(index)

    def declare_spell(self, name=None):
        declaration = super().declare_spell(name)
        controller = get_state(self.ctx).background_controller
        if declaration is not None and controller is not None:
            controller.set_spell(True, kind='youmu' if self.id == 'th07_youmu' else 'yuyuko')
        return declaration

    def damage_batch(self, hits):
        if not hits:
            return
        # Original Player::CalcDamage reports one collisionOut flag for the
        # complete target query; a Bomb region takes precedence over shots.
        primary = [hit for hit in hits if hit.region == 0]
        secondary = [hit for hit in hits if hit.region == 1 and hit.source == 'shot']
        source = 'bomb' if any(hit.source == 'bomb' for hit in primary) else 'shot'
        amount = int(sum(hit.amount for hit in primary) + sum(hit.amount for hit in secondary) / 2.5)
        self.damage(amount, source=source)


def _command_stages(commands, flags):
    """Compile the finite movement combinations used by stage 6.

    Grace is an immediate property, not a wait. An active movement command
    takes its D update frames, one clearing frame, then the next command may
    start. Parallel movement commands are rejected, never silently serialized.
    """
    stages = []
    grace = 0
    boost = False
    for _, kind, continued, duration, loops, first, second in sorted(commands):
        if kind == 0:
            break
        if not flags & kind:
            continue
        if kind == 8192:
            if stages and not continued:
                raise NotImplementedError('delayed source cull grace needs an explicit stage property')
            grace = duration
            continue
        if continued and stages:
            raise NotImplementedError('simultaneous source movement commands are not stage-serializable')
        if kind == 1:
            if stages:
                raise NotImplementedError('a delayed source velocity boost needs a stage-local boost')
            boost = True
            stages.append({'frames': 18})
        elif kind in (16, 32):
            row = {'frames': duration}
            if kind == 16:
                if second <= -990:
                    row['accel'] = float(first) * 216000.0 / 192.0
                else:
                    row['vector_accel'] = (math.cos(second) * first * 216000.0 / 192.0,
                                           -math.sin(second) * first * 216000.0 / 192.0)
            else:
                row['accel'] = float(first) * 216000.0 / 192.0
                row['turn_rate'] = -math.degrees(second) * 60.0
            stages.extend((row, {'frames': 1}))
        elif kind in (64, 128, 256):
            if loops != 1:
                raise NotImplementedError('repeated source slowdown needs reset-timer stages')
            stages.append({'frames': duration, 'velocity_scale_end': 0.0})
            row = {'frames': 1}
            if second > -999:
                row['speed'] = float(bullet_speed(second))
            if kind == 64:
                row['angle_offset'] = -math.degrees(first)
            elif kind == 128:
                row.update(aim='player', angle_offset=-math.degrees(first))
            else:
                row['angle'] = -math.degrees(first)
            stages.append(row)
        else:
            raise NotImplementedError(f'untranslated TH07 movement command {kind}')
    if stages:
        stages.append({})
    return tuple(stages), grace, boost


class SourceActor:
    @property
    def actor(self):
        return self.boss if isinstance(self, SpellCard) else self

    @property
    def state(self):
        return get_state(self.ctx)

    @property
    def diff(self):
        return self.state.diff

    @property
    def rng(self):
        return self.state.rng

    def rank(self, values):
        return values[self.diff]

    @property
    def source_position(self):
        return self.actor.x * 192.0 + 192.0, 224.0 - self.actor.y * 192.0

    @property
    def sx(self):
        return self.source_position[0]

    @property
    def sy(self):
        return self.source_position[1]

    @property
    def source_angle(self):
        return getattr(self.actor, '_source_angle', 0.0)

    def aim_source(self, position=None):
        player = self.ctx.get_player()
        x, y = self.source_position if position is None else position
        return math.atan2(224.0 - player.y * 192.0 - y,
                          player.x * 192.0 + 192.0 - x)

    def source_distance(self):
        player = self.ctx.get_player()
        return math.hypot(player.x * 192 + 192 - self.sx,
                          224 - player.y * 192 - self.sy)

    def emit(self, style, color, ways, layers, speed1, speed2, angle, spread, flags,
             *, aim_mode=1, position=None, offset=(0, 0), commands=(),
             rank_boost=None, tag=0):
        modes = {'fan': 1, 'fan_aimed': 0, 'ring': 3, 'ring_aimed': 2,
                 'shifted': 5, 'shifted_aimed': 4, 'angle_random': 6,
                 'speed_random': 7, 'random': 8}
        mode = modes[aim_mode] if isinstance(aim_mode, str) else aim_mode
        if mode not in range(9):
            raise ValueError(f'unsupported source aim mode {mode}')
        if not self.state.is_spell:
            low, high = (-0.5, 0.5) if rank_boost is None else rank_boost[:2]
            speed_delta = self.ctx.run_state.rank_value(low, high)
            if speed1 != 0:
                speed1 = max(0.3, speed1 + speed_delta)
            speed2 = max(0.3, speed2 + speed_delta / 2)
        ways, layers = max(1, int(ways)), max(1, int(layers))
        layer = np.repeat(np.arange(layers, dtype=np.float32), ways)
        index = np.tile(np.arange(ways, dtype=np.int32), layers)
        count = len(index)
        speeds = np.full(count, speed1, np.float32)
        if layers > 1:
            speeds -= np.float32(speed1 - speed2) * layer / np.float32(layers)
        origin = self.source_position if position is None else position
        origin = origin[0] + offset[0], origin[1] + offset[1]
        if mode in (0, 1):
            offsets = (index + 1) // 2 if ways & 1 else index // 2 + 0.5
            angles = np.where(index & 1, -1, 1) * offsets * spread + angle
        else:
            angles = index * (math.tau / ways) + angle
            if mode in (4, 5):
                angles += math.pi / ways
            else:
                angles += layer * spread
        if mode in (0, 2, 4):
            angles += self.aim_source(origin)
        if mode == 6:
            angles = self.rng.random(count) * np.float32(angle - spread) + spread
        elif mode == 7:
            speeds = self.rng.random(count) * np.float32(speed1 - speed2) + speed2
        elif mode == 8:
            randoms = self.rng.random((count, 2))
            angles = randoms[:, 0] * np.float32(angle - spread) + spread
            speeds = randoms[:, 1] * np.float32(speed1 - speed2) + speed2
        positions = np.empty((count, 2), np.float32)
        positions[:, 0], positions[:, 1] = px(origin[0]), py(origin[1])
        warmup, factor = 0, 1.0
        for bit, key, divisor in ((2, 'fast', 2.0), (4, 'normal', 2.5), (8, 'slow', 3.0)):
            if flags & bit:
                warmup = self.state.assets.manifest['bullet_spawns'][str(style)][key]['end_frame']
                factor = 1.0 / divisor
                positions[:, 0] -= np.cos(angles) * speeds * (4.0 / 192.0)
                positions[:, 1] += np.sin(angles) * speeds * (4.0 / 192.0)
                break
        key = tuple(tuple(command) for command in commands), int(flags)
        if key not in self.state._command_cache:
            if len(self.state._command_cache) >= 256:
                self.state._command_cache.pop(next(iter(self.state._command_cache)))
            self.state._command_cache[key] = _command_stages(commands, flags)
        stages, grace, boost = self.state._command_cache[key]
        indices = self.ctx.create_bullets_batch(
            positions=positions, angles=-np.rad2deg(angles), speeds=bullet_speed(speeds),
            sprite_id=source_sprite(style, color), tag=tag,
            # Source autoRotate draws angle + pi/2. The source Y axis is
            # reflected here, so the corresponding visual offset is -90°.
            render_angle_offset=-90.0 if style in (2, 4, 5, 6, 8, 9) else 0.0,
            # The existing bullet UV convention reflects uploaded atlas rows.
            # Correct only these source images; never mutate the shared registry.
            render_flip_y=True,
            hitbox=Hitbox.box((4, 6, 4, 6, 4, 4, 4, 10, 5, 8, 24)[style] / 192.0,
                              (4, 6, 4, 6, 4, 4, 4, 10, 5, 8, 24)[style] / 192.0))
        group = self.ctx.bullet_pool.capture_group(indices)
        self.ctx.configure_bullet_birth(
            group, warmup_frames=warmup, motion_factor=factor,
            velocity_boost=5.0 * 60.0 / 192.0 if boost else 0.0,
            boost_frames=16 if boost else 0,
            offscreen_grace_frames=warmup + grace)
        if stages:
            self.ctx.set_bullet_behavior(group, stages=stages)
        self.state.emitted += len(indices)
        self.state.dropped_bullets += count - len(indices)
        return group

    async def move_source(self, x, y, frames, easing='linear'):
        curve = SOURCE_EASINGS[easing] if isinstance(easing, int) else EASINGS[easing]
        start_x, start_y = self.source_position
        if start_x != x or start_y != y:
            self.actor._source_angle = math.atan2(y - start_y, x - start_x)
        elapsed = 0.0
        if frames <= 0:
            self.actor.set_position(px(x), py(y))
        while elapsed < frames:
            elapsed = min(frames, elapsed + simulation_rate(self))
            t = curve(elapsed / frames)
            self.actor.set_position(px(start_x + (x - start_x) * t),
                                    py(start_y + (y - start_y) * t))
            await wait_frames(1, clock='control')

    async def move_polar_source(self, angle, speed, frames=None, *, accel=0, turn_rate=0):
        elapsed = 0.0
        while frames is None or elapsed < frames:
            step = simulation_rate(self)
            if frames is not None:
                step = min(step, frames - elapsed)
            angle += turn_rate * step
            speed += accel * step
            self.actor._source_angle = angle
            self.actor.set_position(self.actor.x + math.cos(angle) * speed * step / 192.0,
                                    self.actor.y - math.sin(angle) * speed * step / 192.0)
            elapsed += step
            await wait_frames(1, clock='control')

    move_velocity_source = move_polar_source

    async def move_curve_source(self, end, control1, control2, frames):
        start = np.asarray(self.source_position)
        c1, c2, target = map(np.asarray, (control1, control2, end))
        elapsed = 0.0
        while elapsed < frames:
            elapsed = min(frames, elapsed + simulation_rate(self))
            t = elapsed / frames
            point = (1-t)**3 * start + 3*(1-t)**2*t*c1 + 3*(1-t)*t*t*c2 + t**3*target
            self.actor.set_position(px(point[0]), py(point[1]))
            await wait_frames(1, clock='control')

    def spawn_source(self, enemy, x, y, **kwargs):
        actor = enemy(**kwargs) if isinstance(enemy, type) else enemy
        actor.bind(self.ctx, px(x), py(y))
        actor.start()
        self.ctx.add_enemy_script(actor)
        return actor

    def sound(self, index):
        return self.state.play_se(index)

    def background(self, label):
        return self.state.background(label)

    def drop(self, item, count=1):
        return self.state.drop(item, *self.source_position, count=count)

    def animate(self, script):
        name = f'th07_stg6enm_script_{int(script)}'
        if self.ctx.animations.assets.get_animation(name) is None:
            raise ValueError(f'missing source enemy animation {script}: {name}')
        return self.actor.play_animation(name, resume_auto=False)

    def effect(self, kind, count=1, color=0xffffffff, *, position=None):
        if kind == 31:
            if self.state.background_controller is None:
                raise RuntimeError('TH07 weather requires the stage-owned background controller')
            return self.state.background_controller.emit_weather(count)
        # Visual reconstruction is explicitly partial: use original cut frames
        # in the real ParticlePool, without claiming ANM transforms/interrupts.
        if kind not in self.state._effects:
            source_scripts = {0: 28, 3: 31, 4: 36, 5: 37, 6: 38, 7: 39,
                              8: 40, 9: 41, 10: 42, 11: 43, 12: 44, 13: 45,
                              14: 45, 15: 45, 17: 32, 18: 33, 22: 49,
                              29: 35, 32: 50, 33: 34}
            if kind in source_scripts:
                name = f'th07_etama_script_{source_scripts[kind] + 143}'
                animation = self.state.assets.manifest['animations'].get(name)
                if animation is None:
                    raise ValueError(f'missing effect cut frames: {kind}')
                sprites = tuple(frame['sprite'] for frame in animation['cut_frames'])
            else:
                raise NotImplementedError(f'untranslated source effect {kind}')
            self.state._effects[kind] = ParticleEffect(sprites, lifetime=32, layer='back')
            self.state.trace('visual.partial', kind=kind,
                             missing='ANM transforms and source effect motion')
        rgba = (((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255,
                (color & 255) / 255, ((color >> 24) & 255) / 255)
        x, y = self.source_position if position is None else position
        return self.ctx.emit_particles(self.state._effects[kind], px(x), py(y),
                                       count=count, color=rgba)


class TH07Enemy(SourceActor, EnemyScript):
    pass


class TH07Spell(SourceActor, SpellCard):
    def bind(self, boss, ctx):
        super().bind(boss, ctx)
        self.protected_until = 0


def source_laser(actor, angle, *, position=None, start=0, end=500, length=500,
                 width=16, warning=0, active=60, fade=0, hitbox_delay=None,
                 hitbox_fade_frames=0, transition_hitbox='midpoint', color=1,
                 speed=0):
    x, y = actor.source_position if position is None else position
    laser = actor.ctx.create_laser(px(x), py(y), -math.degrees(angle),
                                   0, length / 192.0, 0, width / 192.0,
                                   color=color, on_time=1)
    laser.configure_motion(speed=speed * 60 / 192, start_offset=start / 192,
                           end_offset=end / 192, length=length / 192)
    laser.configure_lifecycle(warning_frames=warning, active_frames=active,
                              fade_frames=fade, hitbox_delay=hitbox_delay,
                              hitbox_fade_frames=hitbox_fade_frames,
                              transition_hitbox=transition_hitbox)
    return laser

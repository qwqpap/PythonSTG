"""Five-stage content bindings; shared numerical helpers remain ordinary Python.

The stages have independent state/resource ownership. Only the source-unit and
burst helpers are reused from the existing port; no ECL VM or second runtime.
"""

from src.game.stage.boss_base import BossBase, BossPhaseType
from src.game.stage.enemy_script import EnemyScript
from src.game.stage.spellcard import SpellCard

from game_content.ports.th07_stage6.common import (
    DIFFICULTIES, SOURCE_EASINGS, SourceRng, PortState as _SharedState,
    SourceActor as _SharedActor, TH07Boss as _SharedBoss,
    bullet_speed, damage_rule, px, py, source_laser, to_source_damage,
)
from .resources import install_resources, play_source_bgm, play_source_se, source_sprite


class PortState(_SharedState):
    def __init__(self, ctx, *, asset_root=None, audio=True):
        super().__init__(ctx, audio=audio, resources=install_resources(ctx, asset_root))
        self.boss_present = False

    def play_se(self, index):
        return play_source_se(self.ctx, index) if self.audio_enabled else False

    def bgm(self, index):
        from .titles import music_title
        self.trace('bgm', index=index)
        self.ctx.spawn_task(music_title(self.ctx, index))
        return play_source_bgm(self.ctx, index) if self.audio_enabled else False


def get_state(ctx):
    state = getattr(ctx, '_th07_stage5_state', None)
    if state is None:
        state = PortState(ctx)
        ctx._th07_stage5_state = state
    return state


class SourceActor(_SharedActor):
    @property
    def state(self):
        return get_state(self.ctx)

    def animate(self, script):
        return self.actor.play_animation(f'th07_stg5enm_script_{int(script)}', resume_auto=False)

    def effect(self, kind, count=1, color=0xffffffff, *, position=None):
        if kind in (30, 31):
            if self.state.background_controller is None:
                raise RuntimeError('TH07 weather requires a stage background controller')
            return self.state.background_controller.emit_weather(count, kind=kind)
        return super().effect(kind, count, color, position=position)


class TH07Enemy(SourceActor, EnemyScript):
    pass


class TH07Spell(SourceActor, SpellCard):
    def bind(self, boss, ctx):
        super().bind(boss, ctx)
        self.protected_until = 0


class TH07Boss(BossBase):
    damage_batch = _SharedBoss.damage_batch

    def _start_phase(self, index):
        if index < len(self.phases):
            state = get_state(self.ctx)
            state.is_spell = self.phases[index].phase_type == BossPhaseType.SPELLCARD
            if state.background_controller is not None:
                state.background_controller.set_spell(False, kind='youmu')
            state.trace('phase.start', boss=self.id, index=index, name=self.phases[index].name)
        super()._start_phase(index)

    def declare_spell(self, name=None):
        declaration = super().declare_spell(name)
        controller = get_state(self.ctx).background_controller
        if declaration is not None and controller is not None:
            controller.set_spell(True, kind='youmu')
        return declaration


__all__ = ['DIFFICULTIES', 'SOURCE_EASINGS', 'SourceRng', 'PortState', 'SourceActor',
           'TH07Enemy', 'TH07Spell', 'TH07Boss', 'get_state', 'damage_rule',
           'bullet_speed', 'px', 'py', 'source_laser', 'source_sprite', 'to_source_damage']

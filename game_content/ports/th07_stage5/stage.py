"""TH07 stage 5 on the existing stage, wave, actor and Boss lifecycle."""

from src.game.stage.stage_base import StageScript, BossDef

from .background import TH07Stage5Background
from .common import DIFFICULTIES, TH07Boss, get_state
from .road import RoadWave, AfterMidbossWave, Timeline1Enemies
from .titles import stage_titles
from .youmu import (build_midboss_phases, build_youmu_phases,
                    enter_midboss, enter_youmu, finish_youmu, _split_random)


class TH07Stage5(StageScript):
    id = 'th07_stage5'
    name = 'TH07 第五面 · 白玉楼階段の幻闘'
    title = 'Perfect Cherry Blossom'
    subtitle = '普通 API 移植 · 原 MSG 对话与部分角色动画未还原'
    requires_background = True
    disable_default_background = True
    seed_override = None
    start_section = 'road'
    initial_phase = None

    def bind(self, ctx):
        super().bind(ctx)
        # Pay cold Numba compilation at stage preparation, not the first ghost.
        ctx.trails.warmup()
        if ctx.difficulty not in DIFFICULTIES:
            raise ValueError('difficulty must be easy/normal/hard/lunatic')
        if self.seed_override is not None:
            ctx.seed = int(self.seed_override)
        self.port = get_state(ctx)
        self.port.rng.warmup()
        # Compile the split-bullet RNG without consuming the live source seed.
        _split_random(0, 0, False, False)
        self.presentation = TH07Stage5Background(self.port)
        self.port.background_controller = self.presentation
        if self.start_section == 'youmu':
            self.presentation.start_at_boss()
        elif self.start_section == 'midboss':
            self.presentation.start_at_midboss()
        self.phase_history = []
        self.midboss = BossDef('th07_stage5_midboss', '魂魄妖夢', 'th07_youmu',
                               build_midboss_phases(self.port.diff), boss_class=TH07Boss)
        self.youmu = BossDef('th07_stage5_youmu', '魂魄妖夢', 'th07_youmu',
                             build_youmu_phases(self.port.diff), boss_class=TH07Boss)

    def presentation_resources(self):
        bosses = (self.midboss, self.youmu)
        return {
            'spell_names': tuple(phase.name for boss in bosses for phase in boss.phases
                                 if phase.name),
            'texts': tuple({'text': boss.name, 'size': 22, 'stroke_width': 1}
                           for boss in bosses),
            'particle_effects': (self.presentation._weather_effect,),
            'bgm_names': tuple(track['name'] for track in self.port.assets.manifest['bgm'].values()),
            'trail_vertices': 16 * 47 * 6,
        }

    async def _boss(self, definition, entrance, *, ending=None):
        boss = TH07Boss.create(definition, self.ctx)
        boss.setup_render_obj(self.ctx.animations.assets)
        self._current_boss = boss
        self.port.boss_present = True
        boss._active = True
        boss.set_interaction(damageable=False, interactable=False)
        self.ctx.show_title(definition.name, x=192, y=32, size=22,
                            duration_frames=150, key='th07.boss.intro')
        intro = self.spawn_task(entrance(boss, self.ctx), immediate=True)
        try:
            await self.wait(60)
            intro.cancel()
            is_practice = (self.initial_phase is not None and
                           definition.id.endswith(self.start_section))
            if is_practice:
                boss.start_phase_practice(self.initial_phase)
            else:
                boss.start()
            previous = None
            while boss._active:
                if boss.current_phase_index != previous:
                    previous = boss.current_phase_index
                    self.phase_history.append((definition.id, previous, self.ctx.runtime_frame))
                boss.update()
                await self.wait_control(1)
            spell = boss.phases[boss.current_phase_index].spellcard
            reaction = spell.end_reaction if spell is not None else None
            if reaction is not None and not reaction.done:
                boss._active = True
                while not reaction.done:
                    boss.update_animation()
                    await self.wait_control(1)
                reaction.result()
            if ending is not None:
                boss._active = True
                await ending(boss, self.ctx)
        finally:
            intro.cancel()
            boss.dispose()
            self._current_boss = None
            self.port.boss_present = False
            self.port.is_spell = False
            self.presentation.set_spell(False)

    async def run(self):
        if self.start_section not in ('road', 'midboss', 'youmu'):
            raise ValueError('start_section must be road/midboss/youmu')
        background = self.spawn_task(self.presentation.run(), immediate=True)
        try:
            self.port.trace('stage.start', difficulty=self.ctx.difficulty,
                            start=self.start_section, seed=self.ctx.seed)
            if self.start_section == 'road':
                self.spawn_task(stage_titles(self.ctx), immediate=True)
                self.port.bgm(0)
                extra = Timeline1Enemies()
                extra.bind(self.ctx, 0, 0)
                extra.start()
                self.ctx.add_enemy_script(extra)
                await self.run_wave(RoadWave)
            if self.start_section != 'youmu':
                await self._boss(self.midboss, enter_midboss)
                # Original Timeline0 resumes at4823 after its Boss waits.
                await self.run_wave(AfterMidbossWave)
            self.port.trace('message.skipped', index=0,
                            reason='original MSG dialogue not yet translated')
            self.port.bgm(1)
            await self._boss(self.youmu, enter_youmu, ending=finish_youmu)
            self.port.trace('message.skipped', index=1,
                            reason='original MSG dialogue not yet translated')
            self.port.trace('stage.complete', emitted=self.port.emitted,
                            dropped=self.port.dropped_bullets)
        finally:
            background.cancel()
            self.presentation.close()


__all__ = ['TH07Stage5']

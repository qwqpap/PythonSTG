"""The full stage-6 controller on the existing StageManager runtime.

Original MSG dialogue is explicitly incomplete.
Default preview skips MSG text, not the actual Boss entrance movement. Source
Timeline local timestamps resume only after their dialogue/Boss wait returns.
"""

from __future__ import annotations

import inspect

from src.game.stage.stage_base import StageScript, BossDef

from .common import DIFFICULTIES, TH07Boss, get_state, px, py
from .road import BackgroundMotes, RoadWave
from .youmu import build_youmu_phases, enter_youmu
from .yuyuko import build_yuyuko_phases, enter_yuyuko, finish_yuyuko
from .background import TH07Stage6Background
from .titles import stage_titles


class TH07Stage6(StageScript):
    id = 'th07_stage6'
    name = 'TH07 第六面 · 彼の世に嬢の亡骸'
    title = 'Perfect Cherry Blossom'
    subtitle = '手写 API 移植 · 原对话与部分动画未还原'
    disable_default_background = True
    requires_background = True
    seed_override = None
    start_section = 'road'
    initial_phase = None
    skip_dialogue = True
    dialogue_hook = None

    def bind(self, ctx):
        super().bind(ctx)
        if ctx.difficulty not in DIFFICULTIES:
            raise ValueError('TH07 difficulty must be easy/normal/hard/lunatic')
        if self.seed_override is not None:
            ctx.seed = int(self.seed_override)
        self.port = get_state(ctx)
        self.port.rng.warmup()
        self.presentation = TH07Stage6Background(self.port)
        self.port.background_controller = self.presentation
        self.phase_history = []
        self.source_timeline = 0
        self.youmu = BossDef('th07_youmu', '魂魄妖夢', 'th07_youmu',
                             build_youmu_phases(self.port.diff), boss_class=TH07Boss)
        self.yuyuko = BossDef('th07_yuyuko', '西行寺幽々子', 'th07_yuyuko',
                              build_yuyuko_phases(self.port.diff), boss_class=TH07Boss)

    def presentation_resources(self):
        bosses = (self.youmu, self.yuyuko)
        return {
            'spell_names': tuple(phase.name for boss in bosses for phase in boss.phases
                                 if phase.name),
            'texts': tuple({'text': boss.name, 'size': 22, 'stroke_width': 1}
                           for boss in bosses),
            'particle_effects': (self.presentation._weather_effect,),
            'bgm_names': tuple(track['name'] for track in self.port.assets.manifest['bgm'].values()),
        }

    async def _message(self, index, entrance_frames=0):
        self.port.trace('message.start', index=index, skipped=self.skip_dialogue,
                        source_frame=self.source_timeline)
        start = self.time
        if self.skip_dialogue:
            print(f'[TH07 六面] 原 MSG {index} 尚未移植，明确跳过台词。')
        else:
            hook = type(self).dialogue_hook
            if hook is None:
                raise RuntimeError('原 MSG 尚未移植：提供 dialogue_hook 或显式 skip_dialogue=True。')
            result = hook(self, index)
            if not inspect.isawaitable(result):
                raise TypeError('dialogue_hook(stage, index) must return an awaitable')
            await result
        remaining = entrance_frames - (self.time - start)
        if remaining > 0:
            await self.wait(remaining)
        self.port.trace('message.end', index=index, source_frame=self.source_timeline)

    async def _run_source_boss(self, definition, entrance, message, entrance_frames,
                               *, ending=None):
        """Customize the normal Boss lifecycle with content-owned entry/exit.

        Boss.update still owns all phases. The stage only waits and retains
        the visible actor during the source entrance/end reaction interval.
        """
        boss = TH07Boss.create(definition, self.ctx)
        boss.setup_render_obj(self.ctx.animations.assets)
        self._current_boss = boss
        boss._active = True
        self.ctx.show_title(definition.name, x=192, y=32, size=22,
                            subtitle_size=14, duration_frames=150,
                            fade_in_frames=24, fade_out_frames=30,
                            key='th07.boss.intro')
        boss.set_interaction(damageable=False, interactable=False)
        intro = self.spawn_task(entrance(boss, self.ctx), immediate=True)
        try:
            await self._message(message, entrance_frames)
            intro.cancel()
            if (self.initial_phase is not None
                    and definition.id == f'th07_{self.start_section}'):
                boss.start_phase_practice(self.initial_phase)
            else:
                boss.start()
            previous = None
            while boss._active:
                index = boss.current_phase_index
                if index != previous:
                    self.phase_history.append((definition.id, index, self.ctx.runtime_frame))
                    previous = index
                boss.update()
                await self.wait_control(1)
            final_phase = boss.phases[boss.current_phase_index]
            spell = final_phase.spellcard
            reaction = spell.end_reaction if spell is not None else None
            if reaction is not None and not reaction.done:
                boss._active = True  # Visible retreat, no further Boss updates.
                boss.play_animation(definition.texture, resume_auto=False)
                while not reaction.done:
                    boss.update_animation()
                    await self.wait_control(1)
                reaction.result()
            if ending is not None:
                boss._active = True
                boss.play_animation('th07_stg6enm_script_154', resume_auto=False)
                await ending(boss, self.ctx)
        finally:
            intro.cancel()
            boss.dispose()
            self._current_boss = None
            self.port.is_spell = False
            self.presentation.set_spell(False)

    async def run(self):
        background_task = self.spawn_task(self.presentation.run(), immediate=True)
        if self.start_section == 'road':
            self.spawn_task(stage_titles(self.ctx), immediate=True)
        try:
            await self._run_stage_content()
        finally:
            background_task.cancel()
            self.presentation.close()

    async def _run_stage_content(self):
        if self.start_section not in ('road', 'youmu', 'yuyuko'):
            raise ValueError('start_section must be road/youmu/yuyuko')
        self.port.trace('stage.start', difficulty=self.ctx.difficulty,
                        start=self.start_section, seed=self.ctx.seed)
        self.port.bgm(0)
        motes = BackgroundMotes()
        motes.bind(self.ctx, px(80), py(-32))
        motes.start()
        self.ctx.add_enemy_script(motes)
        if self.start_section == 'road':
            await self.run_wave(RoadWave)
        self.source_timeline = 1914
        if self.start_section != 'yuyuko':
            await self._run_source_boss(self.youmu, enter_youmu, 2, 60)
            self.source_timeline = 1918
            self.port.background(1)
            await self.wait(600)
        self.source_timeline = 2518
        self.port.bgm(1)
        await self._run_source_boss(self.yuyuko, enter_yuyuko, 0, 150,
                                    ending=finish_yuyuko)
        self.source_timeline = 2522
        await self.wait(120)
        self.source_timeline = 2642
        await self._message(1)
        self.port.trace('stage.complete', source_frame=self.source_timeline,
                        emitted=self.port.emitted, dropped=self.port.dropped_bullets)


__all__ = ['TH07Stage6']

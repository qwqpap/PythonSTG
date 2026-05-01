"""
Stage 2 - 燃料与汗水的疾走 ～ 延伸至地平线外的昌平线
Terminal Station ~ The Subway to the Edge of the World.

流程编排：本文件只负责"什么时候做什么"，
Boss 数据见 bosses/__init__.py，对话见 dialogue/__init__.py。
"""

import os

from src.game.stage.stage_base import StageScript

from game_content.stages.stage2.waves.stage_2_wave_1 import Stage2Wave1
from game_content.stages.stage2.waves.stage_2_wave_2 import Stage2Wave2
from game_content.stages.stage2.waves.stage_2_wave_3 import Stage2Wave3

from game_content.stages.stage2.bosses import LUNA_BOSS
from game_content.stages.stage2.dialogue import (
    pre_boss_dialogue,
    post_boss_dialogue,
)


class Stage2(StageScript):
    """Stage 2 - 昌平线"""

    id = "stage2"
    name = "Stage 2"
    title = "燃料与汗水的疾走 ～ 延伸至地平线外的昌平线"
    subtitle = "Terminal Station ~ The Subway to the Edge of the World."
    bgm = "03.wav"
    boss_bgm = "04.wav"
    background = "bamboo"
    DEBUG_BOOKMARK = False

    # ===== Boss 定义（数据集中在 bosses/__init__.py） =====

    boss = LUNA_BOSS

    # ===== 关卡流程 =====

    async def run(self):
        # 关卡道中开始
        await self.wait(60)

        await self.run_wave(Stage2Wave1)
        await self.wait(45)
        await self.run_wave(Stage2Wave2)
        await self.wait(30)
        await self.run_wave(Stage2Wave3)

        await self.wait(20)

        # Boss 出现：从路途道中切到更强烈的红色中国风舞台。
        await self.set_background("luastg_gzz_stage04bg")
        await self.wait(180)
        if self.ctx and self.ctx.background_renderer:
            self.ctx.background_renderer.load_texture(
                os.path.join("game_content", "stages", "stage2", "back", "cpline.png")
            )

        # Boss 战前剧情
        await self.play_dialogue(pre_boss_dialogue, initial_delay_frames=180)

        # 等待 3 秒（180 帧），让道中残余子弹飞离屏幕后再进入 Boss 战
        await self.wait(180)

        # 开始激烈弹幕对战
        await self.run_boss(self.boss)

        # Boss 战后剧情
        await self.play_dialogue(post_boss_dialogue)

        # 挂载下一关
        from game_content.stages.stage3.stage_script import Stage3
        self._next_stage_class = Stage3

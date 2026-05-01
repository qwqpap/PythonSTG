"""
Stage 3 - 成府路的周口店荒野~地壳应力焦虑
Geological Report of Senior Celestial and Junior Fairy

流程编排：本文件只负责"什么时候做什么"，
Boss 数据见 bosses/__init__.py，对话见 dialogue/__init__.py，
全游戏 Staff Roll 名单见 game_content/credits.py。
"""

from src.game.stage.stage_base import StageScript

from game_content.stages.stage3.waves.stage_3_wave_1 import Stage3Wave1
from game_content.stages.stage3.waves.stage_3_wave_2 import Stage3Wave2
from game_content.stages.stage3.waves.stage_3_wave_3 import Stage3Wave3

from game_content.stages.stage3.bosses import STAR_BOSS
from game_content.stages.stage3.dialogue import (
    pre_boss_dialogue,
    post_boss_dialogue,
    group_ending_dialogue,
    ending_dialogue,
)
from game_content.credits import STAFF_ROLL


class Stage3(StageScript):
    """Stage 3 - 地壳地质报告"""

    id = "stage3"
    name = "Stage 3"
    title = "成府路的周口店荒野~地壳应力焦虑"
    subtitle = "Geological Report of Senior Celestial and Junior Fairy"
    bgm = "05.wav"
    boss_bgm = "06.wav"
    background = "luastg_stage3bg"
    DEBUG_BOOKMARK = False

    boss = STAR_BOSS

    async def run(self):
        await self.wait(60)

        # 高压高速波次 1：晶体与应力的狂轰乱炸
        await self.run_wave(Stage3Wave1)
        await self.wait(100)

        # 波次 2：横向震波扫荡与中心精英压制
        await self.run_wave(Stage3Wave2)
        await self.wait(100)

        # 波次 3：地幔岩浆爆发与晶体集群
        await self.run_wave(Stage3Wave3)

        await self.wait(80)

        # Boss 出现：切到星星们的背景，和道中地质/地毯感背景拉开。
        await self.set_background("luastg_temple2")
        await self.wait(180)

        # Boss 战前对话
        await self.play_dialogue(pre_boss_dialogue, initial_delay_frames=180)

        # 等待 3 秒（180 帧），让道中残余子弹飞离屏幕后再进入 Boss 战
        await self.wait(180)

        # Boss 战
        await self.run_boss(self.boss)

        # ===== Boss 战后对话（一对一） =====
        await self.play_dialogue(post_boss_dialogue)

        await self.wait(60)

        # ===== 群像收尾对话（三组人汇合） =====
        await self.play_dialogue(group_ending_dialogue)

        # ===== Ending（结局） =====
        # 文本由作者填写在 game_content/stages/stage3/dialogue/__init__.py
        if ending_dialogue:
            await self.wait(60)
            # 切到一个安静背景，避免最终对话还顶着 boss 战背景
            await self.set_background("luastg_temple2")
            await self.play_dialogue(ending_dialogue)

        # ===== Staff Roll =====
        # 名单内容见 game_content/credits.py
        await self.wait(90)
        # 停 BGM，给 staff roll 一个安静的开场
        if self.ctx and hasattr(self.ctx, "stop_bgm"):
            self.ctx.stop_bgm()
        await self.run_staff_roll(STAFF_ROLL, scroll_speed_px=1.2)

        # run() 自然结束 → StageManager 不再有 _next_stage_class →
        # is_finished=True → main.py 检测到后回主菜单。

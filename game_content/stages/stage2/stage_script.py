"""
Stage 2 - 燃料与汗水的疾走 ～ 延伸至地平线外的昌平线
Terminal Station ~ The Subway to the Edge of the World.
"""

import os

from src.game.stage.stage_base import StageScript, BossDef
from src.game.stage.boss_base import spellcard

from game_content.stages.stage2.waves.stage_2_wave_1 import Stage2Wave1
from game_content.stages.stage2.waves.stage_2_wave_2 import Stage2Wave2
from game_content.stages.stage2.waves.stage_2_wave_3 import Stage2Wave3
from game_content.stages.stage2.spellcards.luna_spell_1 import LunaSpell1
from game_content.stages.stage2.spellcards.luna_spell_2 import LunaSpell2
from game_content.stages.stage2.spellcards.luna_spell_3 import LunaSpell3
from game_content.stages.stage2.spellcards.luna_spell_4 import LunaSpell4
from game_content.stages.stage2.spellcards.luna_spell_5 import LunaSpell5


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

    # ===== Boss 定义 =====

    boss = BossDef(
        id="luna_boss",
        name="Luna Child",
        texture="luna",
        phases=[
            spellcard(LunaSpell1, "跑符「111真的吗？不跑校园跑要挂科？」", hp=5200, time=60),
            spellcard(LunaSpell2, "线符「昌平列车」",                       hp=5600, time=60),
            spellcard(LunaSpell3, "网符「交织的死亡菱形」",                   hp=5400, time=60),
            spellcard(LunaSpell4, "月符「月光回廊」",                        hp=6200, time=65),
            spellcard(LunaSpell5, "幻符「月归昌平」",                        hp=7000, time=70),
        ]
    )

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
        await self.play_dialogue([
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "我没招了，这油大怎么这么远？", "portrait": "Happy"},
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "我勺子好像过不了地铁安检。算了，乘乘bus好了，幻想乡没有bus，正好体验一下。", "portrait": "Happy"},
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "刚刚在bus上遇到一个长得像琪露诺的生物，一直拉着我说要带我吃什么毒液鸭肠……我虽然什么都吃，但也……算了，办正事要紧。", "portrait": "Happy"},
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "（油门口）\n可算到了。什么玩意一下子闪过去了？", "portrait": "Happy"},
            {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "厚积薄发、开物成务！", "portrait": "Happy"},
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "你先别跑了，我问你个事。", "portrait": "Happy"},
            {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "哇，喜羊羊。", "portrait": "Happy"},
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "我不在红魔馆打工。不是，你在跑什么？", "portrait": "Happy"},
            {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "我一百公里校园跑再不跑体育就要挂科了。拜拜！", "portrait": "Happy"},
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "你给我回来！", "portrait": "Anger"},
        ], initial_delay_frames=180)

        # 等待 3 秒（180 帧），让道中残余子弹飞离屏幕后再进入 Boss 战
        await self.wait(180)

        # 开始激烈弹幕对战
        await self.run_boss(self.boss)

        # Boss 战后剧情
        await self.play_dialogue([
            {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "别打了别打了，再打我晚自习就要迟到了。", "portrait": "Happy"},
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "你怎么这么菜啊，电脑拿来，我给你搞个自动签到+虚拟机刷校园跑一条龙。", "portrait": "Happy"},
            {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "不行啊，大一不让带电脑，这几天我只能玩LW和千夜帖。", "portrait": "Happy"},
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "？", "portrait": "Anger"},
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "那跟我回去，全套官作你玩个爽。", "portrait": "Happy"},
            {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "111真的吗，但我明天早操……", "portrait": "Happy"},
            {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "别惦记，赶紧跟我回去。", "portrait": "Happy"},
        ])

        # 挂载下一关
        from game_content.stages.stage3.stage_script import Stage3
        self._next_stage_class = Stage3

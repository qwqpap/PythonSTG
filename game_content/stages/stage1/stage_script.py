"""
Stage 1 - 从旧地狱街道到地灵殿
"""

from src.game.stage.stage_base import StageScript, BossDef
from src.game.stage.boss_base import nonspell, spellcard

from game_content.stages.stage1.waves.fairy_wave import FairyWave

from game_content.stages.stage1.spellcards.nonspell_1 import NonSpell1
from game_content.stages.stage1.spellcards.spell_1 import MoonlightRay
from game_content.stages.stage1.spellcards.spell_2 import NightBird


class Stage1(StageScript):
    """Stage 1 - 从旧地狱街道到地灵殿"""

    id = "stage1"
    name = "Stage 1"
    title = "从旧地狱街道到地灵殿"
    subtitle = "From Old Hell to the Moriya Shrine"
    bgm = "stage1.ogg"
    boss_bgm = "boss1.ogg"
    background = "stage1_bg"

    # ===== Boss 定义 =====

    midboss = BossDef(
        id="rumia_midboss",
        name="ルーミア",
        texture="enemy_rumia",
        phases=[
            nonspell(NonSpell1, hp=600, time=20, bonus=50000),
        ]
    )

    boss = BossDef(
        id="rumia_boss",
        name="ルーミア",
        texture="enemy_rumia",
        phases=[
            nonspell(NonSpell1, hp=800, time=30, bonus=100000),
            spellcard(MoonlightRay, "月符「Moonlight Ray」", hp=1200, time=60),
            spellcard(NightBird, "夜符「Night Bird」", hp=1500, time=60, bonus=1500000),
        ]
    )

    # ===== 关卡流程 =====

    async def run(self):
        # 开场对话
        """
        await self.play_dialogue([
            ("Hinanawi_Tenshi", "left", "你素？"),
            ("Reiuji_Utsuho", "right", "是我，露米娅的人类老公！"),
            ("Reiuji_Utsuho", "right", "不"),
            ("Hinanawi_Tenshi", "left", "本吧主来了！"),
            ("Reiuji_Utsuho", "right", "清真食堂开始了。"),
        ])
        """

        await self.wait(60)

        # 道中波次：左右各 5 个妖精飞入，边飞边射自机狙
        await self.run_wave(FairyWave)

        await self.wait(60)

        # 道中 Boss - 露米娅（1 段非符）
        await self.run_boss(self.midboss, is_midboss=True)

        # Boss 战前对话
        await self.play_dialogue([
            ("Hinanawi_Tenshi", "left", "你就是露米娅吗？"),
            ("Reiuji_Utsuho", "right", "没错！我是灵乌路空！"),
            ("Hinanawi_Tenshi", "left", "我听说你很擅长使用符卡？"),
            ("Reiuji_Utsuho", "right", "哼哼，那当然！"),
        ])

        # 关底 Boss - 露米娅
        await self.run_boss(self.boss)

        # Boss 战后对话
        await self.play_dialogue([
            ("Reiuji_Utsuho", "right", "好...好强...！"),
            ("Hinanawi_Tenshi", "left", "这就是天界的实力！"),
        ])

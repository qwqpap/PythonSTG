"""
Stage 3 Boss 配置

把 Boss 数据集中在这里，stage_script.py 只负责流程编排。
新增/调整 Boss 阶段、HP、时限时，只改这一个文件。
"""

from src.game.stage.stage_base import BossDef
from src.game.stage.boss_base import spellcard

from game_content.stages.stage3.spellcards.star_spell_1 import StarSpell1
from game_content.stages.stage3.spellcards.star_spell_2 import StarSpell2
from game_content.stages.stage3.spellcards.star_spell_3 import StarSpell3
from game_content.stages.stage3.spellcards.star_spell_4 import StarSpell4


STAR_BOSS = BossDef(
    id="star_boss",
    name="Star Sapphire",
    texture="star",
    phases=[
        spellcard(StarSpell1, "门符「23:00 准时关闭的东北门」",       hp=6000, time=60),
        spellcard(StarSpell2, "幻符「十二人间里的癔症狂想曲」",       hp=6800, time=65),
        spellcard(StarSpell3, "华丽星地「周口店：星辰坠落的沉积层」", hp=7600, time=70),
        spellcard(StarSpell4, "地质纪元「永不退色的群星频率」",       hp=8400, time=75),
    ],
)


__all__ = ["STAR_BOSS"]

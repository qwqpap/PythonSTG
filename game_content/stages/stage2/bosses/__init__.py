"""
Stage 2 Boss 配置

把 Boss 数据集中在这里，stage_script.py 只负责流程编排。
新增/调整 Boss 阶段、HP、时限时，只改这一个文件。
"""

from src.game.stage.stage_base import BossDef
from src.game.stage.boss_base import spellcard

from game_content.stages.stage2.spellcards.luna_spell_1 import LunaSpell1
from game_content.stages.stage2.spellcards.luna_spell_2 import LunaSpell2
from game_content.stages.stage2.spellcards.luna_spell_3 import LunaSpell3
from game_content.stages.stage2.spellcards.luna_spell_4 import LunaSpell4
from game_content.stages.stage2.spellcards.luna_spell_5 import LunaSpell5


LUNA_BOSS = BossDef(
    id="luna_boss",
    name="Luna Child",
    texture="luna",
    phases=[
        spellcard(LunaSpell1, "跑符「111真的吗？不跑校园跑要挂科？」", hp=5200, time=60),
        spellcard(LunaSpell2, "线符「昌平列车」",                     hp=5600, time=60),
        spellcard(LunaSpell3, "网符「交织的死亡菱形」",                 hp=5400, time=60),
        spellcard(LunaSpell4, "月符「月光回廊」",                      hp=6200, time=65),
        spellcard(LunaSpell5, "幻符「月归昌平」",                      hp=7000, time=70),
    ],
)


__all__ = ["LUNA_BOSS"]

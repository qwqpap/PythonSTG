"""
Stage 1 Boss 战前对话

天子 vs 灵乌路空
"""

from src.game.stage.dialog_data import DialogSequence, DialogSentence

# Boss战前对话
pre_boss_dialogue = DialogSequence(
    sentences=[
        DialogSentence(
            text="你就是掌握核融合力量的地狱鸦吗？",
            character="Hinanawi_Tenshi",
            portrait="normal",
            position="left",
            balloon_style=1
        ),
        DialogSentence(
            text="没错！我是灵乌路空！",
            character="Reiuji_Utsuho",
            portrait="normal",
            position="right",
            balloon_style=2
        ),
        DialogSentence(
            text="你这个天界的任性小姐，来地底做什么？",
            character="Reiuji_Utsuho",
            portrait="normal",
            position="right",
            balloon_style=3
        ),
        DialogSentence(
            text="当然是来修行的！正好拿你练练手！",
            character="Hinanawi_Tenshi",
            portrait="normal",
            position="left",
            balloon_style=2
        ),
        DialogSentence(
            text="哼哼，那就让你见识一下核融合的威力！",
            character="Reiuji_Utsuho",
            portrait="normal",
            position="right",
            balloon_style=4
        ),
    ],
    can_skip=True,
    auto_advance=True
)

# Boss战后对话（占位）
post_boss_dialogue = DialogSequence(
    sentences=[
        DialogSentence(
            text="好...好强...！",
            character="Reiuji_Utsuho",
            portrait="normal",
            position="right",
            balloon_style=1
        ),
        DialogSentence(
            text="这就是天界的实力！",
            character="Hinanawi_Tenshi",
            portrait="normal",
            position="left",
            balloon_style=3
        ),
    ],
    can_skip=True
)

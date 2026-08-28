from src.authoring.dsl import FireArc, NonSpell, Repeat, Wait


nonspell = NonSpell(
    id="demo_nonspell",
    name="通常攻击 · 薄明",
    hp=240,
    time_limit=1.0,
    body=[
        Repeat(
            4,
            body=[
                FireArc(
                    count=9,
                    speed=1.7,
                    center_angle=-90.0,
                    arc_angle=100.0,
                    uid="nonspell_arc",
                ),
                Wait(12, uid="nonspell_wait"),
            ],
            uid="nonspell_repeat",
        )
    ],
)

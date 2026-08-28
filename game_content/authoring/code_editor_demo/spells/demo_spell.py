from src.authoring.dsl import (
    FireAtPlayer,
    FireCircle,
    Parallel,
    RawPython,
    Repeat,
    Spell,
    Wait,
)


spell = Spell(
    id="demo_spell",
    name="夜符『代码星环』",
    hp=360,
    time_limit=1.5,
    body=[
        Parallel(
            branches=[
                [
                    Repeat(
                        3,
                        body=[
                            FireCircle(
                                count=16,
                                speed=1.6,
                                uid="spell_circle",
                            ),
                            Wait(12, uid="spell_circle_wait"),
                        ],
                        uid="spell_circle_repeat",
                    )
                ],
                [
                    Repeat(
                        2,
                        body=[
                            FireAtPlayer(
                                speed=2.4,
                                offset_angle=10.0,
                                uid="spell_aimed",
                            ),
                            Wait(20, uid="spell_aimed_wait"),
                        ],
                        uid="spell_aimed_repeat",
                    )
                ],
            ],
            uid="spell_parallel",
        ),
        RawPython(
            "phase_marker = getattr(self, 'time', 0)",
            uid="spell_raw_python",
        ),
    ],
)

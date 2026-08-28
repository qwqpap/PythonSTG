from src.authoring.dsl import FireAtPlayer, Kill, MoveLinear, MoveTo, Repeat, Wait, Enemy


enemy = Enemy(
    id="aimed_fairy",
    name="自机狙妖精",
    hp=45,
    sprite="enemy_fairy",
    body=[
        MoveTo(0.0, 0.55, duration=45, uid="aimed_enter"),
        Repeat(
            3,
            body=[
                FireAtPlayer(
                    speed=2.2,
                    bullet_type="rice",
                    color="blue",
                    uid="aimed_fire",
                ),
                Wait(20, uid="aimed_fire_wait"),
            ],
            uid="aimed_repeat",
        ),
        MoveLinear(0.0, 0.7, duration=30, uid="aimed_leave"),
        Kill(uid="aimed_kill"),
    ],
)

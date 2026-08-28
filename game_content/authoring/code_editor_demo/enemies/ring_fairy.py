from src.authoring.dsl import Kill, MoveTo, Wait, Enemy, ring_burst


enemy = Enemy(
    id="ring_fairy",
    name="环射妖精",
    hp=60,
    sprite="enemy_fairy",
    body=[
        MoveTo(0.0, 0.62, duration=60, uid="ring_enter"),
        ring_burst(
            count=3,
            interval=14,
            bullet_count=18,
            speed=1.8,
            uid="ring_template_call",
        ),
        Wait(30, uid="ring_tail_wait"),
        Kill(uid="ring_kill"),
    ],
)

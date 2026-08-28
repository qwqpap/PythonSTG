from src.authoring.dsl import Ref, SpawnEnemy, Wait, Wave


wave = Wave(
    id="opening_wave",
    name="开场妖精",
    body=[
        SpawnEnemy(
            Ref("aimed_fairy"),
            x=-0.45,
            y=0.9,
            uid="opening_spawn_aimed",
        ),
        Wait(90, uid="opening_wait_middle"),
        SpawnEnemy(
            Ref("ring_fairy"),
            x=0.45,
            y=0.9,
            uid="opening_spawn_ring",
        ),
        Wait(150, uid="opening_wait_end"),
    ],
)

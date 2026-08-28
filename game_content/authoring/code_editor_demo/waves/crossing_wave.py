from src.authoring.dsl import Ref, SpawnEnemy, SpawnTask, Wait, Wave


wave = Wave(
    id="crossing_wave",
    name="交叉火力",
    body=[
        SpawnTask(
            Ref("support_burst"),
            arguments={"bursts": 3, "interval": 12},
            uid="crossing_support_task",
        ),
        SpawnEnemy(
            Ref("ring_fairy"),
            x=-0.3,
            y=0.85,
            uid="crossing_spawn_left",
        ),
        SpawnEnemy(
            Ref("aimed_fairy"),
            x=0.3,
            y=0.85,
            uid="crossing_spawn_right",
        ),
        Wait(180, uid="crossing_wait_end"),
    ],
)

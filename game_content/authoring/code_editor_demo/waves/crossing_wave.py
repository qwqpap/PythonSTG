from src.authoring.dsl import Ref, SpawnEnemy, SpawnTask, Wait, Wave

from src.authoring.dsl import Set

wave = Wave(
    id='crossing_wave',
    name='交叉火力',
    body=[
        SpawnTask(
            task=Ref('support_burst'),
            arguments={'bursts': 3, 'interval': 12},
            uid='crossing_support_task',
        ),
        SpawnEnemy(enemy_class=Ref('ring_fairy'), x=-0.3, y=0.85, uid='crossing_spawn_left'),
        SpawnEnemy(enemy_class=Ref('aimed_fairy'), x=0.3, y=0.85, uid='crossing_spawn_right'),
        Wait(frames=180, uid='crossing_wait_end'),
        Set(name='i', value=0, uid='set_d6a731efa04b4681b8cbe2797a39878d'),
    ],
)

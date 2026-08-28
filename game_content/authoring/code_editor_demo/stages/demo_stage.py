from src.authoring.dsl import (
    At,
    Parallel,
    PlayBGM,
    PlayDialogue,
    PlaySE,
    Ref,
    RunBoss,
    RunWave,
    SetBackground,
    Stage,
    Wait,
)


stage = Stage(
    id="demo_stage",
    name="雾之湖代码演示",
    title="Code Driven Stage",
    subtitle="静态投影与运行 Trace",
    bgm="res://assets/audio/music/00.wav",
    background="res://game_content/authoring/code_editor_demo/assets/background/demo.json",
    body=[
        SetBackground(
            "res://game_content/authoring/code_editor_demo/assets/background/demo.json",
            uid="stage_background",
        ),
        PlayBGM(
            "res://assets/audio/music/00.wav",
            uid="stage_bgm",
        ),
        Wait(30, uid="stage_intro_wait"),
        At(
            35,
            body=[
                PlaySE(
                    "res://assets/audio/se/se_alert.wav",
                    uid="stage_at_se",
                )
            ],
            uid="stage_at_cue",
        ),
        Parallel(
            branches=[
                [Wait(20, uid="stage_parallel_short_wait")],
                [Wait(40, uid="stage_parallel_camera_wait")],
            ],
            uid="stage_parallel_intro",
        ),
        RunWave(Ref("opening_wave"), uid="stage_opening_wave"),
        Wait(30, uid="stage_between_waves"),
        RunWave(Ref("crossing_wave"), uid="stage_crossing_wave"),
        Wait(60, uid="stage_before_boss"),
        RunBoss(Ref("demo_boss"), uid="stage_boss"),
        PlayDialogue(
            "res://game_content/authoring/code_editor_demo/assets/dialogue/intro.json",
            initial_delay_frames=10,
            uid="stage_dialogue",
        ),
    ],
)

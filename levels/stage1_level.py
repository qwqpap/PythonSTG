"""
Stage 1 测试关卡

使用程序化关卡脚本 StageScript。
这个文件属于"引擎胶水层"，连接 main.py 的引擎对象和 game_content 的内容。
"""
from typing import Generator

from src.game.stage.context import StageContext
from game_content.stages.stage1.stage_script import Stage1
from src.game.audio import StageAudioBank


def stage1_level(stage_manager, bullet_pool, player,
                 audio_manager=None, **kwargs) -> Generator:
    """加载并运行 Stage 1"""
    print("=== Stage 1 测试关卡开始 ===")

    # 加载关卡私有音频（如果有）
    if audio_manager:
        stage_bank = StageAudioBank.from_directory(
            "stage1", "game_content/stages/stage1"
        )
        audio_manager.set_stage_bank(stage_bank)

    # 创建上下文：将引擎对象包装成内容脚本可用的统一接口
    ctx = StageContext(
        bullet_pool=bullet_pool,
        player=player,
        enemy_manager=stage_manager.enemy_manager,
        audio_manager=audio_manager
    )

    # 将ctx保存到stage_manager，供渲染器访问
    stage_manager.current_context = ctx

    # 使用程序化关卡脚本
    stage = Stage1()
    stage.bind(ctx)
    stage.start()

    # 保存 stage 对象到 stage_manager，供对话渲染使用
    stage_manager.current_stage = stage

    while stage._active:
        stage.update()
        yield

    print("=== Stage 1 测试关卡结束 ===")

    # 清理 stage 引用
    stage_manager.current_stage = None

    # 清理上下文引用
    stage_manager.current_context = None

    # 清理关卡私有音频
    if audio_manager:
        audio_manager.stop_bgm(fade_ms=500)
        audio_manager.set_stage_bank(None)

    bullet_pool.clear_all()
    for _ in range(120):
        yield

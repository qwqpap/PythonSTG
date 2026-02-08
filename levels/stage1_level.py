"""
Stage 1 测试关卡

使用新的 StageContext 桥接引擎层和内容层。
这个文件属于"引擎胶水层"，连接 main.py 的引擎对象和 game_content 的内容。
"""
from typing import Generator

from src.game.stage.context import StageContext
from src.game.stage.stage_base import StageBase
from src.game.audio import StageAudioBank


def stage1_level(stage_manager, bullet_pool, player,
                 audio_manager=None) -> Generator:
    """加载 stage1/stage.json 并运行"""
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

    # 加载关卡配置并启动
    stage = StageBase.from_config("game_content/stages/stage1/stage.json", ctx)
    stage.start()

    while stage._active:
        stage.update()
        yield

    print("=== Stage 1 测试关卡结束 ===")

    # 清理关卡私有音频
    if audio_manager:
        audio_manager.stop_bgm(fade_ms=500)
        audio_manager.set_stage_bank(None)

    bullet_pool.clear_all()
    for _ in range(120):
        yield

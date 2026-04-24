"""
Stage Test - 背景测试关卡

无 Boss、无波次、无符卡，仅用于测试背景/HUD/弹幕系统。
按 ESC 可返回主菜单。
"""

from src.game.stage.stage_base import StageScript


class StageTest(StageScript):
    """测试关卡 —— 只有背景，无敌人无 Boss"""

    id = "stage_test"
    name = "测试关卡"
    title = "测试模式"
    subtitle = "Test Stage"
    bgm = "00.wav"           # 使用标题 BGM，可按需修改
    background = "galaxy"   # 使用银河背景

    async def run(self):
        # 持续等待，直到玩家按 ESC 退出（由主循环处理）
        # 每 6000 帧（约 100 秒）循环一次，实际上无限运行
        while True:
            await self.wait(6000)

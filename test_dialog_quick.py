"""
对话系统快速测试

测试 DialogPhase 是否能正常工作
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.game.stage.dialog_spellcard import DialogPhase
from game_content.stages.stage1.dialogue.boss_dialogue import pre_boss_dialogue


class MockBoss:
    """模拟 Boss"""
    def __init__(self):
        self.x = 0
        self.y = 0.5

    async def move_to(self, x, y, duration):
        """模拟移动"""
        self.x = x
        self.y = y
        for _ in range(duration):
            await asyncio.sleep(0)


class MockContext:
    """模拟上下文"""
    def create_bullet(self, **kwargs):
        pass

    def remove_bullet(self, bullet):
        pass

    def get_player(self):
        return None

    def play_se(self, name, volume=None):
        return False


async def test_dialog_phase():
    """测试对话阶段"""
    print("="*60)
    print("对话系统快速测试")
    print("="*60)
    print()

    # 创建对话阶段
    dialog_phase = DialogPhase()
    dialog_phase.dialogue_sequence = pre_boss_dialogue

    # 绑定 Boss 和上下文
    mock_boss = MockBoss()
    mock_ctx = MockContext()
    dialog_phase.bind(mock_boss, mock_ctx)

    # 启动对话
    dialog_phase.start()

    print("对话阶段已启动，开始更新...\n")

    # 模拟游戏循环
    frame = 0
    while dialog_phase.update():
        frame += 1
        if frame % 60 == 0:
            print(f"[帧 {frame}] 对话进行中...")
        await asyncio.sleep(1/60)  # 模拟 60 FPS

    print(f"\n对话结束，总共 {frame} 帧 ({frame/60:.1f}秒)")
    print("="*60)


if __name__ == "__main__":
    try:
        asyncio.run(test_dialog_phase())
    except KeyboardInterrupt:
        print("\n测试中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

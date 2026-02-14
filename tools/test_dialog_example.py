"""
对话系统测试工具

演示对话系统的基本使用。

Usage:
    python test_dialog_example.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.game.stage.dialog_data import DialogSequence, DialogSentence, create_sentence
from src.game.stage.dialog_manager import DialogManager


def example_1_basic():
    """示例1：基本对话"""
    print("=" * 60)
    print("示例1：基本对话")
    print("=" * 60)

    sequence = DialogSequence(
        sentences=[
            DialogSentence(
                text="你好！我是天子！",
                character="Hinanawi_Tenshi",
                position="left",
                balloon_style=1
            ),
            DialogSentence(
                text="哼，我是空！",
                character="Reiuji_Utsuho",
                position="right",
                balloon_style=2
            ),
        ]
    )

    manager = DialogManager(sequence)
    manager.start()

    print(f"对话句子数: {len(sequence)}")
    print(f"可跳过: {sequence.can_skip}")
    print()

    # 模拟更新
    frame = 0
    while manager.update():
        frame += 1
        if manager.current_sentence:
            if frame % 60 == 0:  # 每60帧打印一次
                print(f"[帧{frame}] 当前: {manager.current_sentence.text}")

    print(f"\n对话结束，总帧数: {frame}")


def example_2_with_callbacks():
    """示例2：使用回调"""
    print("\n" + "=" * 60)
    print("示例2：对话回调")
    print("=" * 60)

    sequence = DialogSequence(
        sentences=[
            create_sentence("开始战斗！", character="Tenshi", position="left"),
            create_sentence("来吧！", character="Utsuho", position="right"),
        ]
    )

    manager = DialogManager(sequence)

    # 设置回调
    def on_sentence_start(sentence: DialogSentence):
        print(f"→ {sentence.character} ({sentence.position}): {sentence.text}")

    def on_sentence_end(sentence: DialogSentence):
        print(f"  [句子结束，持续{sentence.get_duration()}帧]")

    def on_complete():
        print("✓ 对话完成！")

    manager.on_sentence_start = on_sentence_start
    manager.on_sentence_end = on_sentence_end
    manager.on_complete = on_complete

    manager.start()

    # 模拟更新
    frame = 0
    while manager.update():
        frame += 1


def example_3_skip():
    """示例3：跳过对话"""
    print("\n" + "=" * 60)
    print("示例3：跳过对话")
    print("=" * 60)

    sequence = DialogSequence(
        sentences=[
            create_sentence("这是很长的对话...", character="Tenshi"),
            create_sentence("再来一句...", character="Utsuho"),
            create_sentence("还有一句...", character="Tenshi"),
        ],
        can_skip=True
    )

    manager = DialogManager(sequence)
    manager.start()

    print("正在播放对话...")
    # 模拟30帧后跳过
    for frame in range(30):
        if not manager.update():
            break

    print(f"第30帧，执行跳过...")
    manager.skip()

    print(f"对话状态: {'活跃' if manager.is_active else '已结束'}")


def example_4_real_dialogue():
    """示例4：实际对话（从配置加载）"""
    print("\n" + "=" * 60)
    print("示例4：Stage 1 Boss 对话")
    print("=" * 60)

    try:
        from game_content.stages.stage1.dialogue.boss_dialogue import pre_boss_dialogue

        print(f"加载对话: {len(pre_boss_dialogue)} 句")
        print()

        for i, sentence in enumerate(pre_boss_dialogue):
            print(f"[{i+1}] {sentence.character} ({sentence.position}):")
            print(f"    {sentence.text}")
            print(f"    样式: {sentence.balloon_style}, 持续: {sentence.get_duration()}帧")
            print()

    except ImportError as e:
        print(f"无法加载对话配置: {e}")


def main():
    """主函数"""
    print("\n对话系统测试工具\n")

    example_1_basic()
    example_2_with_callbacks()
    example_3_skip()
    example_4_real_dialogue()

    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()

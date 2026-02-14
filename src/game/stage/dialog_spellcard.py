"""
对话符卡 - 用于在 Boss 战序列中插入对话

DialogPhase 是一个特殊的符卡，用于播放对话序列。
可以像普通符卡一样插入到 Boss 的 phases 列表中。

Usage:
    from src.game.stage.boss_base import dialog
    from game_content.stages.stage1.dialogue.boss_dialogue import pre_boss_dialogue

    boss = BossDef(
        id="utsuho",
        name="灵乌路 空",
        phases=[
            dialog(pre_boss_dialogue),  # 对话阶段
            nonspell(NonSpell1, hp=800, time=30),
            spellcard(Spell1, "核符「Nuclear Fusion」", hp=1500, time=60),
        ]
    )
"""

from typing import Optional
from .spellcard import SpellCard
from .dialog_data import DialogSequence, DialogSentence
from .dialog_manager import DialogManager

# 延迟导入 pygame，避免在无渲染环境中报错
try:
    from .simple_dialog_renderer import SimpleDialogTextRenderer
    _has_renderer = True
except ImportError:
    _has_renderer = False
    SimpleDialogTextRenderer = None


class DialogPhase(SpellCard):
    """
    对话符卡

    在 Boss 战中播放对话序列，支持：
    - 跳过对话（长按射击键60帧）
    - 自动前进
    - Boss 和角色立绘显示
    """

    # 类属性（由 dialog() 函数动态设置）
    dialogue_sequence: Optional[DialogSequence] = None

    # 符卡元信息
    name = ""  # 对话阶段无名称
    hp = 999999999  # 对话阶段不耗血
    time_limit = 9999.0  # 足够长的时间
    bonus = 0
    is_survival = True  # 对话阶段不攻击 Boss
    practice_unlock = False

    def __init__(self):
        super().__init__()
        self._dialog_manager: Optional[DialogManager] = None
        self._text_renderer = None  # 文本渲染器
        self._completed = False

    async def setup(self):
        """初始化对话管理器"""
        print("[DialogPhase] 正在初始化对话...")

        if self.dialogue_sequence is None:
            raise ValueError("DialogPhase requires dialogue_sequence to be set")

        # 创建简化文本渲染器
        if _has_renderer:
            self._text_renderer = SimpleDialogTextRenderer()

        # 创建对话管理器
        self._dialog_manager = DialogManager(self.dialogue_sequence)

        # 设置回调
        def on_sentence_start(sentence: DialogSentence):
            print(f"\n[对话开始] {sentence.character} ({sentence.position}):")
            print(f"  \"{sentence.text}\"")
            print(f"  气泡样式: {sentence.balloon_style}, 持续: {sentence.get_duration()}帧")

            # 更新渲染器
            if self._text_renderer:
                self._text_renderer.set_sentence(sentence)

        def on_sentence_end(sentence: DialogSentence):
            print(f"[对话结束] {sentence.character}")

        def on_complete():
            print("\n[对话阶段完成] 全部对话播放完毕\n")
            self._completed = True
            if self._text_renderer:
                self._text_renderer.clear()

        self._dialog_manager.on_sentence_start = on_sentence_start
        self._dialog_manager.on_sentence_end = on_sentence_end
        self._dialog_manager.on_complete = on_complete

        # 启动对话
        self._dialog_manager.start()
        print(f"[DialogPhase] 对话管理器已启动，共{len(self.dialogue_sequence)}句对话")

    async def run(self):
        """主循环：更新对话直到结束"""
        print("[DialogPhase] 开始播放对话...")

        while not self._completed:
            # 更新对话管理器
            if self._dialog_manager:
                # 处理输入（这里简化处理，实际应从输入系统获取）
                # shoot_pressed = self.ctx.is_key_pressed("shoot")
                # self._dialog_manager.handle_input(shoot_pressed)

                # 更新
                if not self._dialog_manager.update():
                    self._completed = True
                    break

            # 更新文本渲染器（打字机效果）
            if self._text_renderer:
                self._text_renderer.update()

            await self.wait(1)  # 每帧暂停

        # 对话结束，符卡结束
        print("[DialogPhase] 对话播放完成，退出对话阶段")

    def get_text_renderer(self):
        """获取文本渲染器供外部调用"""
        return self._text_renderer

    async def on_defeated(self):
        """对话阶段不能被击败"""
        pass

    async def on_timeout(self):
        """对话阶段不会超时"""
        pass

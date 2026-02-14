"""
对话管理器

管理对话序列的播放、更新和状态控制。
参照 LuaSTG boss_dialog.lua 实现。
"""

import types
from typing import Optional, Callable
from .dialog_data import DialogSequence, DialogSentence


class DialogManager:
    """
    对话管理器

    控制对话序列的播放流程，管理当前对话状态。
    可作为协程使用，与 SpellCard 系统集成。

    Usage:
        dialog_mgr = DialogManager(dialog_sequence)
        dialog_mgr.start()

        # 每帧更新
        if dialog_mgr.update():
            # 对话进行中
            pass
        else:
            # 对话结束
            pass
    """

    def __init__(self, sequence: DialogSequence):
        self.sequence = sequence
        self._current_index: int = 0
        self._active: bool = False
        self._coroutine = None

        # 当前句子状态
        self._sentence_timer: int = 0      # 当前句子计时器
        self._current_sentence: Optional[DialogSentence] = None

        # 输入状态
        self._skip_timer: int = 0          # 跳过计时器（长按跳过）
        self._advance_pressed: bool = False

        # 回调
        self.on_complete: Optional[Callable] = None  # 对话结束回调
        self.on_sentence_start: Optional[Callable[[DialogSentence], None]] = None  # 句子开始回调
        self.on_sentence_end: Optional[Callable[[DialogSentence], None]] = None    # 句子结束回调

    @property
    def is_active(self) -> bool:
        """对话是否正在进行"""
        return self._active

    @property
    def current_sentence(self) -> Optional[DialogSentence]:
        """当前显示的对话句子"""
        return self._current_sentence

    @property
    def current_index(self) -> int:
        """当前对话句子索引"""
        return self._current_index

    @property
    def progress(self) -> float:
        """对话进度（0.0-1.0）"""
        if len(self.sequence) == 0:
            return 1.0
        return self._current_index / len(self.sequence)

    def start(self):
        """启动对话"""
        self._active = True
        self._current_index = 0
        self._sentence_timer = 0
        self._skip_timer = 0
        self._coroutine = self._run_dialog()

    def update(self) -> bool:
        """
        每帧更新

        Returns:
            True: 对话进行中
            False: 对话已结束
        """
        if not self._active:
            return False

        self._sentence_timer += 1

        # 驱动协程
        if self._coroutine:
            try:
                next(self._coroutine)
            except StopIteration:
                self._active = False
                if self.on_complete:
                    self.on_complete()
                return False

        return True

    def handle_input(self, shoot_pressed: bool = False):
        """
        处理输入

        Args:
            shoot_pressed: 射击键是否按下（用于跳过）
        """
        if not self._active:
            return

        # 跳过对话（长按60帧）
        if shoot_pressed and self.sequence.can_skip:
            self._skip_timer += 1
            if self._skip_timer > 60:
                self.skip()
        else:
            self._skip_timer = 0

        # 快进到下一句（短按）
        if shoot_pressed and not self._advance_pressed:
            self._advance_pressed = True
            self.advance()
        elif not shoot_pressed:
            self._advance_pressed = False

    def advance(self):
        """前进到下一句对话"""
        if not self._active:
            return

        # 结束当前句子
        if self._current_sentence:
            if self.on_sentence_end:
                self.on_sentence_end(self._current_sentence)

        # 移动到下一句
        self._current_index += 1
        if self._current_index >= len(self.sequence):
            self._active = False
            if self.on_complete:
                self.on_complete()
            return

        # 开始新句子
        self._sentence_timer = 0
        self._load_sentence(self._current_index)

    def skip(self):
        """跳过整个对话"""
        if not self._active or not self.sequence.can_skip:
            return

        self._active = False
        if self.on_complete:
            self.on_complete()

    def _load_sentence(self, index: int):
        """加载指定句子"""
        if index >= len(self.sequence):
            return

        self._current_sentence = self.sequence[index]
        self._sentence_timer = 0

        if self.on_sentence_start:
            self.on_sentence_start(self._current_sentence)

    def _run_dialog(self):
        """对话协程"""
        for i, sentence in enumerate(self.sequence):
            self._current_index = i
            self._load_sentence(i)

            # 等待句子持续时间
            duration = sentence.get_duration()
            for _ in range(duration):
                yield

            # 句子结束
            if self.on_sentence_end:
                self.on_sentence_end(sentence)

            # 如果不自动前进，等待用户输入
            if not self.sequence.auto_advance:
                while self._active:
                    yield

        # 对话结束
        self._active = False


# ==================== 协程工具 ====================

@types.coroutine
def play_dialog(sequence: DialogSequence):
    """
    播放对话（协程）

    可在 SpellCard 或 Wave 中使用：

    Example:
        async def run(self):
            await play_dialog(EXAMPLE_PRE_BOSS_DIALOG)
            # 对话结束后继续
    """
    manager = DialogManager(sequence)
    manager.start()

    while manager.update():
        yield

    return manager

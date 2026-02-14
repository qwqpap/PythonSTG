"""
对话数据结构定义

定义对话句子、对话阶段等数据结构。
参照 LuaSTG 的对话系统实现。
"""

from typing import List, Optional, Literal
from dataclasses import dataclass, field


@dataclass
class DialogSentence:
    """
    单句对话数据

    参照 LuaSTG boss.dialog:sentence() 参数
    """
    text: str                                    # 对话文本
    character: Optional[str] = None              # 角色ID（如 "Tenshi", "Utsuho"）
    portrait: Optional[str] = "normal"           # 立绘key（如 "normal", "angry"）
    position: Literal["left", "right"] = "left"  # 立绘位置
    balloon_style: int = 1                       # 气泡样式（1-8）
    duration: Optional[int] = None               # 显示时长（帧），None=自动计算

    # 高级参数
    portrait_scale: float = 1.0                  # 立绘缩放
    portrait_x: Optional[float] = None           # 立绘X坐标（None=使用默认）
    portrait_y: Optional[float] = None           # 立绘Y坐标（None=使用默认）
    balloon_x: Optional[float] = None            # 气泡X坐标（None=使用默认）
    balloon_y: Optional[float] = None            # 气泡Y坐标（None=使用默认）

    character_num: int = 1                       # 角色编号（支持多角色同时在场）
    keep_balloons: int = 1                       # 保留气泡条数
    stay_active: bool = False                    # 完成后是否保持激活

    def get_duration(self) -> int:
        """
        获取对话显示时长（帧数）

        如果未指定，按 LuaSTG 公式计算：60 + len(text) * 5
        """
        if self.duration is not None:
            return self.duration
        return 60 + len(self.text) * 5

    def get_position_code(self) -> int:
        """
        获取位置代码（LuaSTG格式）

        Returns:
            1: right (右)
            -1: left (左)
        """
        return 1 if self.position == "right" else -1


@dataclass
class DialogSequence:
    """
    对话序列（一段完整的对话）

    包含多个对话句子，可以作为关卡对话、Boss战前对话等。
    """
    sentences: List[DialogSentence] = field(default_factory=list)
    can_skip: bool = True                        # 是否可跳过
    auto_advance: bool = True                    # 是否自动前进到下一句
    skip_key: str = "z"                          # 跳过按键（默认射击键）

    def __len__(self) -> int:
        return len(self.sentences)

    def __getitem__(self, index: int) -> DialogSentence:
        return self.sentences[index]

    def __iter__(self):
        return iter(self.sentences)


# ==================== 便捷构造函数 ====================

def create_sentence(
    text: str,
    character: Optional[str] = None,
    portrait: str = "normal",
    position: Literal["left", "right"] = "left",
    balloon_style: int = 1,
    **kwargs
) -> DialogSentence:
    """
    便捷创建对话句子

    Examples:
        >>> s = create_sentence("你好！", character="Tenshi", position="left")
        >>> s = create_sentence("哼哼", character="Utsuho", position="right", balloon_style=3)
    """
    return DialogSentence(
        text=text,
        character=character,
        portrait=portrait,
        position=position,
        balloon_style=balloon_style,
        **kwargs
    )


def create_sequence(sentences: List[DialogSentence], can_skip: bool = True) -> DialogSequence:
    """
    便捷创建对话序列

    Examples:
        >>> seq = create_sequence([
        ...     create_sentence("天子！", character="Utsuho", position="right"),
        ...     create_sentence("什么事？", character="Tenshi", position="left"),
        ... ])
    """
    return DialogSequence(sentences=sentences, can_skip=can_skip)


# ==================== 示例数据 ====================

# 示例：Boss战前对话
EXAMPLE_PRE_BOSS_DIALOG = DialogSequence(
    sentences=[
        DialogSentence(
            text="你就是地狱鸦 灵乌路空吗？",
            character="Tenshi",
            position="left",
            balloon_style=1
        ),
        DialogSentence(
            text="没错！我掌控着核融合的力量！",
            character="Utsuho",
            position="right",
            balloon_style=2
        ),
        DialogSentence(
            text="那就让我看看你的实力吧！",
            character="Tenshi",
            position="left",
            balloon_style=3
        ),
    ],
    can_skip=True
)

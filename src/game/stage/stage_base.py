"""
Stage 脚本基类 - 程序化关卡定义

提供 StageScript 基类和 BossDef 数据类。
内容作者通过继承 StageScript 并实现 async def run() 来定义关卡流程。
"""

from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from abc import abstractmethod
import types

if TYPE_CHECKING:
    from .boss_base import BossBase
    from .spellcard import SpellCardContext


@dataclass
class BossDef:
    """Boss 定义数据对象（用于程序化关卡脚本）"""
    id: str
    name: str
    texture: str
    phases: list       # List[BossPhase] - 使用 list 避免导入循环
    animations: dict = field(default_factory=dict)


class StageScript:
    """
    程序化关卡脚本基类

    使用 async def run() 定义关卡流程。
    提供统一的外部接口（start, update, _active）。

    示例：
        class Stage1(StageScript):
            id = "stage1"
            name = "Stage 1"
            bgm = "stage1.ogg"
            boss_bgm = "boss1.ogg"

            boss = BossDef("rumia", "ルーミア", "enemy_rumia", [
                nonspell(NonSpell1, hp=800, time=30),
                spellcard(MoonlightRay, "月符「Moonlight Ray」", hp=1200, time=60),
            ])

            async def run(self):
                await self.run_wave(OpeningWave)
                await self.wait(120)
                await self.run_boss(self.boss)
    """

    # ===== 子类覆盖这些类属性 =====
    id: str = ""
    name: str = ""
    title: str = ""
    subtitle: str = ""
    bgm: str = ""
    boss_bgm: str = ""
    background: str = ""

    def __init__(self):
        self.ctx: Optional['SpellCardContext'] = None
        self._active: bool = False
        self._coroutine = None
        self._current_boss: Optional['BossBase'] = None
        self._current_dialog_renderer = None  # 当前对话渲染器
        self._time: int = 0

    @property
    def time(self) -> int:
        """当前帧数"""
        return self._time

    def bind(self, ctx: 'SpellCardContext'):
        """绑定上下文"""
        self.ctx = ctx

    def start(self):
        """开始关卡"""
        self._active = True
        self._time = 0
        self._coroutine = self._run_wrapper()

    async def _run_wrapper(self):
        """包装 run() —— 播放 BGM 后执行主流程"""
        if self.bgm:
            self._play_bgm(self.bgm)
        try:
            await self.run()
        except Exception as e:
            import traceback
            print(f"[StageScript] 关卡脚本异常: {e}")
            traceback.print_exc()
        self._on_stage_complete()

    def update(self):
        """每帧更新"""
        if not self._active:
            return

        self._time += 1

        # 更新所有敌人脚本
        if self.ctx and hasattr(self.ctx, 'update_enemy_scripts'):
            self.ctx.update_enemy_scripts()

        if self._coroutine:
            try:
                self._coroutine.send(None)
            except StopIteration:
                self._active = False

    # ==================== 子类实现 ====================

    @abstractmethod
    async def run(self):
        """
        主关卡流程（子类必须实现）

        使用 await self.run_wave(WaveClass) 运行波次
        使用 await self.run_boss(boss_def) 运行 Boss 战
        使用 await self.wait(frames) 等待
        """
        pass

    # ==================== 流程控制 API ====================

    @types.coroutine
    def run_wave(self, wave_class):
        """
        运行一个道中波次

        Args:
            wave_class: Wave 子类（类本身，不是实例）
        """
        wave = wave_class()
        wave.bind(self.ctx)
        yield from wave.execute()

    @types.coroutine
    def run_boss(self, boss_def, is_midboss=False):
        """
        运行 Boss 战

        Args:
            boss_def: BossDef 数据对象
            is_midboss: 是否为道中 Boss
        """
        from .boss_base import BossBase

        # 切换到 Boss BGM（仅关底 Boss）
        if not is_midboss and self.boss_bgm:
            self._play_bgm(self.boss_bgm)

        # 从 BossDef 创建 Boss 实例
        boss = BossBase.create(boss_def, self.ctx)
        self._current_boss = boss
        boss.start()

        # 等待 Boss 战结束
        while boss._active:
            boss.update()
            yield

        self._current_boss = None

        # 恢复道中 BGM（如果是道中 Boss）
        if is_midboss and self.bgm:
            self._play_bgm(self.bgm)

    @types.coroutine
    def play_dialogue(self, dialogue_list):
        """
        播放对话序列

        Args:
            dialogue_list: 对话列表，支持两种格式：
                简单格式: [("角色名", "位置", "文本"), ...]
                详细格式: [{"character": "...", "position": "...", "text": "...", "balloon_style": 1}, ...]

        Example:
            await self.play_dialogue([
                ("Hinanawi_Tenshi", "left", "你好！"),
                ("Reiuji_Utsuho", "right", "哼！"),
            ])
        """
        from .dialog_data import DialogSequence, DialogSentence

        # 转换为 DialogSentence 列表
        sentences = []
        for item in dialogue_list:
            if isinstance(item, tuple):
                # 简单格式: (character, position, text)
                character, position, text = item
                sentences.append(DialogSentence(
                    text=text,
                    character=character,
                    position=position,
                    balloon_style=1  # 默认样式
                ))
            elif isinstance(item, dict):
                # 详细格式
                sentences.append(DialogSentence(**item))
            else:
                raise ValueError(f"Invalid dialogue format: {type(item)}")

        # 创建对话序列
        sequence = DialogSequence(sentences=sentences, can_skip=True)

        # 创建对话管理器
        from .dialog_manager import DialogManager
        manager = DialogManager(sequence)

        # 创建简化渲染器
        text_renderer = None
        try:
            from .simple_dialog_renderer import SimpleDialogTextRenderer
            text_renderer = SimpleDialogTextRenderer()
            # 存储到实例变量以便外部渲染
            self._current_dialog_renderer = text_renderer
            print(f"[对话] 渲染器已创建: {text_renderer}")
        except ImportError as e:
            print(f"[对话] 警告：无法导入渲染器: {e}")
        except Exception as e:
            print(f"[对话] 警告：创建渲染器失败: {e}")

        # 设置回调
        def on_sentence_start(sentence):
            print(f"\n[对话] {sentence.character} ({sentence.position}): {sentence.text}")
            if text_renderer:
                text_renderer.set_sentence(sentence)

        def on_complete():
            print("[对话] 对话结束\n")
            if text_renderer:
                text_renderer.clear()
            self._current_dialog_renderer = None

        manager.on_sentence_start = on_sentence_start
        manager.on_complete = on_complete

        # 启动对话
        manager.start()

        # 等待对话完成
        while manager.update():
            if text_renderer:
                text_renderer.update()
            yield

    @types.coroutine
    def run_dialogue(self, dialogue_data):
        """
        运行对话（兼容旧 API）

        Args:
            dialogue_data: 对话数据
        """
        # 兼容：如果是 DialogSequence 对象，使用旧方式
        from .dialog_data import DialogSequence
        if isinstance(dialogue_data, DialogSequence):
            dialogue_list = [(s.character, s.position, s.text) for s in dialogue_data.sentences]
            yield from self.play_dialogue(dialogue_list)
        else:
            yield from self.play_dialogue(dialogue_data)

    # ==================== 等待 API ====================

    @types.coroutine
    def wait(self, frames: int):
        """等待指定帧数"""
        for _ in range(frames):
            yield

    @types.coroutine
    def wait_seconds(self, seconds: float):
        """等待指定秒数"""
        yield from self.wait(int(seconds * 60))

    # ==================== 音频 API ====================

    @types.coroutine
    def play_bgm(self, name: str):
        """切换 BGM（可在 run() 中随时调用）"""
        self._play_bgm(name)
        return
        yield  # 使其成为协程，支持 await

    def _play_bgm(self, bgm_name: str):
        """播放 BGM - 通过 ctx.audio 系统"""
        if self.ctx and hasattr(self.ctx, 'play_bgm'):
            name = bgm_name
            if '.' in name:
                name = name.rsplit('.', 1)[0]
            if self.ctx.play_bgm(name):
                return
        print(f"[StageScript] 播放 BGM: {bgm_name}")

    # ==================== 生命周期 ====================

    def _on_stage_complete(self):
        """关卡完成"""
        self._active = False
        print(f"[StageScript] 关卡完成: {self.name}")

    def get_dialog_renderer(self):
        """获取当前对话渲染器（供外部渲染使用）"""
        return self._current_dialog_renderer


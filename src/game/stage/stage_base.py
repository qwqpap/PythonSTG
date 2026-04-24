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


class _ImageOverlayRenderer:
    """用于关卡脚本中按帧播放静态图片序列。"""

    def __init__(self):
        self.current_sentence = None
        self.scene_image_path: Optional[str] = None
        self.scene_image_alpha: float = 1.0
        self.active_speaker_position = None
        self.portrait_slots = {"left": None, "right": None}
        self._active = True

    def set_image(self, image_path: str):
        self.scene_image_path = image_path
        self.current_sentence = None

    def clear(self):
        self._active = False
        self.scene_image_path = None
        self.current_sentence = None

    def is_active(self) -> bool:
        return self._active


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

        # ===== Debug 跳转 =====
        # 格式: {"type": "boss"/"midboss", "phase": 0} 或 None
        self._debug_skip_target: Optional[dict] = None

        # ===== 关卡链式跳转 =====
        # 在 run() 末尾赋值，StageManager 会在清场后自动加载
        self._next_stage_class = None

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
        """包装 run() —— 应用背景、播放 BGM 后执行主流程"""
        # 应用关卡声明的背景（失败时保留 main.py 的默认背景）
        if self.background and self.ctx:
            self.ctx.set_background(self.background)
        # Debug 跳转模式下不播放道中 BGM（目标 Boss 会自行播放 Boss BGM）
        if self.bgm and not self._debug_skip_target:
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
        # Debug: 跳转目标检测
        if self._debug_skip_target:
            target = self._debug_skip_target
            if target.get("type") == "wave" and target.get("wave_class") is wave_class:
                # 到达目标 wave，退出跳过模式，继续执行
                self._debug_skip_target = None
                print(f"[Debug] 跳转到 wave: {wave_class.__name__}")
            else:
                return  # 不是目标，跳过

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

        effective_type = "midboss" if is_midboss else "boss"
        start_phase = 0

        # Debug: 检查是否为跳转目标
        if self._debug_skip_target:
            target = self._debug_skip_target
            if target["type"] == effective_type:
                # 到达目标 Boss！退出跳过模式
                start_phase = target.get("phase", 0)
                self._debug_skip_target = None
                print(f"[Debug] 跳转到 {effective_type}, phase={start_phase}")
            else:
                # 不是目标，跳过此 Boss
                return

        # 切换到 Boss BGM（仅关底 Boss）
        if not is_midboss and self.boss_bgm:
            self._play_bgm(self.boss_bgm)

        # 从 BossDef 创建 Boss 实例
        boss = BossBase.create(boss_def, self.ctx)
        try:
            from src.resource.texture_asset import get_texture_asset_manager
            boss.setup_render_obj(get_texture_asset_manager())
        except Exception as e:
            import traceback
            print(f"[StageScript] Boss setup_render_obj 失败 (texture={boss_def.texture!r}): {e}")
            traceback.print_exc()
        self._current_boss = boss

        # Debug: 从指定阶段开始
        if start_phase > 0:
            boss.start_phase_practice(start_phase)
        else:
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
    def play_dialogue(self, dialogue_list, initial_delay_frames: int = 0):
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
        # Debug: 跳过对话（不是跳转目标类型）
        if self._debug_skip_target:
            return
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
        initial_delay_frames = max(0, int(initial_delay_frames))
        for _ in range(initial_delay_frames):
            yield

        # 等待对话完成
        while manager.update():
            if text_renderer:
                text_renderer.update()
            yield

    @types.coroutine
    def play_image_sequence(
        self,
        image_paths,
        frame_duration: int = 45,
    ):
        """
        依次播放图片序列（占用对话层渲染通道）。

        Args:
            image_paths: 图片路径列表（按传入顺序播放）
            frame_duration: 每张图显示帧数
        """
        if self._debug_skip_target:
            return
        if not image_paths:
            return

        renderer = _ImageOverlayRenderer()
        self._current_dialog_renderer = renderer
        duration = max(1, int(frame_duration))

        try:
            for image_path in image_paths:
                renderer.set_image(image_path)

                for _ in range(duration):
                    yield
        finally:
            renderer.clear()
            self._current_dialog_renderer = None

    # ==================== 等待 API ====================

    @types.coroutine
    def wait(self, frames: int):
        """等待指定帧数"""
        if self._debug_skip_target:
            return
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

    @types.coroutine
    def set_background(self, name: str):
        """切换背景场景（可在 run() 中随时调用，如 Boss 战前换图）"""
        if self.ctx:
            self.ctx.set_background(name)
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


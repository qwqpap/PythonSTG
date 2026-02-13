"""
Stage 基类 - 管理完整关卡流程
"""

from typing import List, Optional, Dict, Any, Generator, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
from abc import abstractmethod
import json
import os
import types

if TYPE_CHECKING:
    from .boss_base import BossBase
    from .spellcard import SpellCardContext


class SectionType(Enum):
    WAVE = "wave"           # 道中敌人波次
    MIDBOSS = "midboss"     # 道中 Boss
    BOSS = "boss"           # 关底 Boss
    DIALOGUE = "dialogue"   # 对话
    WAIT = "wait"           # 等待


@dataclass
class StageSection:
    """关卡段落"""
    section_type: SectionType
    script: Optional[str] = None      # 脚本路径
    boss: Optional[str] = None        # Boss 配置路径
    duration: int = 0                 # 等待时长（帧）
    data: Dict[str, Any] = None       # 额外数据


@dataclass
class BossDef:
    """Boss 定义数据对象（用于程序化关卡脚本）"""
    id: str
    name: str
    texture: str
    phases: list       # List[BossPhase] - 使用 list 避免导入循环
    animations: dict = field(default_factory=dict)


class StageBase:
    """
    Stage 基类
    
    管理：
    - 道中敌人波次
    - 中Boss
    - 关底 Boss
    - 对话
    """
    
    def __init__(self):
        self.id: str = ""
        self.name: str = ""
        self.title: str = ""           # 关卡标题
        self.subtitle: str = ""        # 关卡副标题
        
        self.bgm: str = ""             # 道中 BGM
        self.boss_bgm: str = ""        # Boss 战 BGM
        self.background: str = ""      # 背景
        
        self.sections: List[StageSection] = []
        self.current_section_index: int = 0
        
        self.ctx: Optional['SpellCardContext'] = None
        self._active: bool = False
        self._coroutine: Optional[Generator] = None
        self._current_boss: Optional['BossBase'] = None
        
        # 关卡时间
        self._time: int = 0
    
    @property
    def time(self) -> int:
        return self._time
    
    @classmethod
    def from_config(cls, config_path: str, ctx: 'SpellCardContext') -> 'StageBase':
        """从配置文件创建 Stage"""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        stage = cls()
        stage.ctx = ctx
        stage.id = config.get('id', '')
        stage.name = config.get('name', '')
        stage.title = config.get('title', '')
        stage.subtitle = config.get('subtitle', '')
        stage.bgm = config.get('bgm', '')
        stage.boss_bgm = config.get('boss_bgm', '')
        stage.background = config.get('background', '')
        
        base_dir = os.path.dirname(config_path)
        
        # 加载段落
        for section_cfg in config.get('sections', []):
            section = StageSection(
                section_type=SectionType(section_cfg['type']),
                script=section_cfg.get('script'),
                boss=section_cfg.get('boss'),
                duration=section_cfg.get('duration', 0),
                data=section_cfg.get('data', {})
            )
            
            # 补全路径
            if section.script:
                section.script = os.path.join(base_dir, section.script + '.py')
            if section.boss:
                section.boss = os.path.join(base_dir, section.boss + '.json')
            
            stage.sections.append(section)
        
        return stage
    
    def start(self):
        """开始关卡"""
        self._active = True
        self._time = 0
        self.current_section_index = 0
        self._coroutine = self._run()
    
    def _run(self) -> Generator:
        """关卡主流程"""
        # 播放道中 BGM
        if self.bgm:
            self._play_bgm(self.bgm)
        
        # 执行每个段落
        for i, section in enumerate(self.sections):
            self.current_section_index = i
            
            if section.section_type == SectionType.WAVE:
                yield from self._run_wave(section)
            
            elif section.section_type == SectionType.MIDBOSS:
                yield from self._run_boss(section, is_midboss=True)
            
            elif section.section_type == SectionType.BOSS:
                yield from self._run_boss(section, is_midboss=False)
            
            elif section.section_type == SectionType.DIALOGUE:
                yield from self._run_dialogue(section)
            
            elif section.section_type == SectionType.WAIT:
                yield from self._wait(section.duration)
        
        # 关卡完成
        self._on_stage_complete()
    
    def _run_wave(self, section: StageSection) -> Generator:
        """执行道中波次"""
        if not section.script or not os.path.exists(section.script):
            return
        
        # 加载波次脚本
        import importlib.util
        spec = importlib.util.spec_from_file_location("wave_module", section.script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 支持三种波次编写方式：
        
        # 1. 函数风格：def run(ctx): ... yield
        if hasattr(module, 'run'):
            wave_gen = module.run(self.ctx)
            if wave_gen:
                yield from wave_gen
        
        # 2. 注册风格：wave = MyWaveClass（推荐）
        elif hasattr(module, 'wave'):
            wave_cls = module.wave
            wave_instance = wave_cls()
            wave_instance.bind(self.ctx)
            yield from wave_instance.execute()
        
        # 3. 自动查找 Wave 子类
        else:
            from .wave_base import Wave as WaveBase
            for name in dir(module):
                obj = getattr(module, name)
                if (isinstance(obj, type) and issubclass(obj, WaveBase) 
                        and obj is not WaveBase):
                    wave_instance = obj()
                    wave_instance.bind(self.ctx)
                    yield from wave_instance.execute()
                    break
    
    def _run_boss(self, section: StageSection, is_midboss: bool) -> Generator:
        """执行 Boss 战"""
        if not section.boss:
            return
        
        from .boss_base import BossBase
        
        # 切换 BGM
        if not is_midboss and self.boss_bgm:
            self._play_bgm(self.boss_bgm)
        
        # 加载并启动 Boss
        boss = BossBase.from_config(section.boss, self.ctx)
        self._current_boss = boss
        boss.start()
        
        # 等待 Boss 战结束
        while boss._active:
            boss.update()
            yield
        
        self._current_boss = None
        
        # 恢复道中 BGM（如果是中 Boss）
        if is_midboss and self.bgm:
            self._play_bgm(self.bgm)
    
    def _run_dialogue(self, section: StageSection) -> Generator:
        """执行对话"""
        # TODO: 对话系统
        yield
    
    def _wait(self, frames: int) -> Generator:
        """等待指定帧数"""
        for _ in range(frames):
            yield
    
    def update(self):
        """每帧更新"""
        if not self._active:
            return

        self._time += 1

        # 更新所有敌人脚本
        if self.ctx and hasattr(self.ctx, 'update_enemy_scripts'):
            self.ctx.update_enemy_scripts()

        # 推进主协程
        if self._coroutine:
            try:
                next(self._coroutine)
            except StopIteration:
                self._active = False
    
    def _play_bgm(self, bgm_name: str):
        """播放 BGM - 通过 ctx.audio 系统"""
        if self.ctx and hasattr(self.ctx, 'play_bgm'):
            # 去掉扩展名作为 BGM 名称查找
            name = bgm_name
            if '.' in name:
                name = name.rsplit('.', 1)[0]
            if self.ctx.play_bgm(name):
                return
        print(f"[Stage] 播放 BGM: {bgm_name}")
    
    def _on_stage_complete(self):
        """关卡完成（可覆盖）"""
        self._active = False
        print(f"[Stage] 关卡完成: {self.name}")
    
    # ==================== 练习模式 ====================
    
    def get_boss_sections(self) -> List[tuple]:
        """获取所有 Boss 段落（用于练习模式）"""
        result = []
        for i, section in enumerate(self.sections):
            if section.section_type in (SectionType.MIDBOSS, SectionType.BOSS):
                result.append((i, section))
        return result
    
    def start_from_section(self, section_index: int):
        """从指定段落开始（练习模式）"""
        self._active = True
        self._time = 0
        self.sections = self.sections[section_index:]
        self.current_section_index = 0
        self._coroutine = self._run()


class StageScript:
    """
    程序化关卡脚本基类

    使用 async def run() 定义关卡流程，替代 JSON 驱动的 StageBase。
    提供与 StageBase 相同的外部接口（start, update, _active）。

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
    def run_dialogue(self, dialogue_data):
        """
        运行对话（TODO: 对话系统实现后补充）

        Args:
            dialogue_data: 对话数据
        """
        # TODO: 对话系统
        yield

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

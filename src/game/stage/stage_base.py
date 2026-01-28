"""
Stage 基类 - 管理完整关卡流程
"""

from typing import List, Optional, Dict, Any, Generator, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
import json
import os

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
        
        # 执行 run 函数或类
        if hasattr(module, 'run'):
            wave_gen = module.run(self.ctx)
            if wave_gen:
                yield from wave_gen
        elif hasattr(module, 'Wave'):
            wave = module.Wave(self.ctx)
            yield from wave.run()
    
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
        
        # 推进主协程
        if self._coroutine:
            try:
                next(self._coroutine)
            except StopIteration:
                self._active = False
    
    def _play_bgm(self, bgm_path: str):
        """播放 BGM（可覆盖）"""
        print(f"[Stage] 播放 BGM: {bgm_path}")
    
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

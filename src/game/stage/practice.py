"""
练习模式管理器

支持：
1. 符卡单独练习
2. 关卡练习（从指定位置开始）
3. Boss 连续练习
"""

from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from .spellcard import SpellCard, SpellCardContext
from .boss_base import BossBase, BossPhase


@dataclass
class PracticeEntry:
    """练习模式条目"""
    stage_id: str              # 关卡 ID
    stage_name: str            # 关卡名称
    boss_id: str               # Boss ID
    boss_name: str             # Boss 名称
    phase_index: int           # 阶段索引
    spell_name: str            # 符卡名称（非符为空）
    is_nonspell: bool          # 是否为非符
    boss_def: Optional[Any] = None  # BossDef 对象

    @property
    def display_name(self) -> str:
        """显示名称"""
        if self.is_nonspell:
            return f"{self.boss_name} - 通常攻撃 {self.phase_index + 1}"
        return f"{self.boss_name} - {self.spell_name}"


class PracticeManager:
    """
    练习模式管理器

    用法：
        manager = PracticeManager()
        manager.load([Stage1, Stage2, Stage3])

        # 获取所有可练习符卡
        entries = manager.get_all_entries()

        # 按关卡分组
        by_stage = manager.get_entries_by_stage()

        # 开始练习
        manager.start_practice(entry, ctx)
    """

    def __init__(self):
        self._entries: List[PracticeEntry] = []
        self._loaded = False

    def load(self, stage_classes: list):
        """
        从 StageScript 子类列表加载练习条目。

        扫描每个 StageScript 子类的类属性，查找 BossDef 实例，
        从中提取可练习的符卡条目。

        Args:
            stage_classes: StageScript 子类的列表

        用法：
            from game_content.stages.stage1.stage_script import Stage1
            manager.load([Stage1])
        """
        from .stage_base import BossDef
        from .boss_base import BossPhaseType

        self._entries.clear()

        for stage_cls in stage_classes:
            stage_id = getattr(stage_cls, 'id', '')
            stage_name = getattr(stage_cls, 'name', stage_id)

            # 扫描类属性，查找所有 BossDef 实例
            for attr_name in dir(stage_cls):
                if attr_name.startswith('_'):
                    continue
                attr = getattr(stage_cls, attr_name, None)
                if not isinstance(attr, BossDef):
                    continue

                boss_def = attr
                for i, phase in enumerate(boss_def.phases):
                    if not phase.practice_unlock:
                        continue

                    entry = PracticeEntry(
                        stage_id=stage_id,
                        stage_name=stage_name,
                        boss_id=boss_def.id,
                        boss_name=boss_def.name,
                        phase_index=i,
                        spell_name=phase.name or '',
                        is_nonspell=(phase.phase_type == BossPhaseType.NONSPELL),
                        boss_def=boss_def
                    )
                    self._entries.append(entry)

        self._loaded = True
        print(f"[Practice] 加载了 {len(self._entries)} 个可练习符卡")

    def get_all_entries(self) -> List[PracticeEntry]:
        """获取所有练习条目"""
        return self._entries.copy()

    def get_entries_by_stage(self) -> Dict[str, List[PracticeEntry]]:
        """按关卡分组"""
        result: Dict[str, List[PracticeEntry]] = {}
        for entry in self._entries:
            if entry.stage_id not in result:
                result[entry.stage_id] = []
            result[entry.stage_id].append(entry)
        return result

    def get_entries_by_boss(self) -> Dict[str, List[PracticeEntry]]:
        """按 Boss 分组"""
        result: Dict[str, List[PracticeEntry]] = {}
        for entry in self._entries:
            key = f"{entry.stage_id}_{entry.boss_id}"
            if key not in result:
                result[key] = []
            result[key].append(entry)
        return result

    def start_practice(self, entry: PracticeEntry, ctx: SpellCardContext) -> BossBase:
        """
        开始符卡练习

        Returns:
            Boss 实例（已启动到指定阶段）
        """
        boss = BossBase.create(entry.boss_def, ctx)
        boss.start_phase_practice(entry.phase_index)
        return boss

    def start_boss_practice(self, stage_id: str, boss_id: str, ctx: SpellCardContext) -> BossBase:
        """
        开始 Boss 连续练习（所有符卡）
        """
        entries = [e for e in self._entries
                   if e.stage_id == stage_id and e.boss_id == boss_id]

        if not entries:
            raise ValueError(f"未找到 Boss: {stage_id}/{boss_id}")

        first = entries[0]
        boss = BossBase.create(first.boss_def, ctx)
        boss.start()  # 从头开始
        return boss


class SpellCardPractice:
    """
    单符卡练习封装

    用法：
        practice = SpellCardPractice.from_path("game_content/stages/stage1/spellcards/spell_1.py")
        practice.start(ctx)

        # 游戏循环中
        if practice.update():
            # 练习中
            pass
        else:
            # 结束
            result = practice.get_result()
    """

    def __init__(self, spellcard: SpellCard, boss: Optional[BossBase] = None):
        self.spellcard = spellcard
        self.boss = boss or self._create_dummy_boss()
        self._result: Optional['PracticeResult'] = None
        self._started = False

    @classmethod
    def from_path(cls, script_path: str) -> 'SpellCardPractice':
        """从脚本路径创建"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("spellcard_module", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 查找符卡类
        spellcard = None
        if hasattr(module, 'spellcard'):
            spellcard = module.spellcard()
        else:
            from .spellcard import SpellCard
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and issubclass(obj, SpellCard) and obj != SpellCard:
                    spellcard = obj()
                    break

        if not spellcard:
            raise ValueError(f"未找到符卡类: {script_path}")

        return cls(spellcard)

    def _create_dummy_boss(self) -> BossBase:
        """创建练习用的假 Boss"""
        boss = BossBase()
        boss.x = 0.0
        boss.y = 0.5
        boss.hp = self.spellcard.hp
        boss.max_hp = self.spellcard.hp
        return boss

    def start(self, ctx: SpellCardContext):
        """开始练习"""
        self.boss.ctx = ctx
        self.spellcard.bind(self.boss, ctx)
        self.spellcard.start()
        self._started = True
        self._start_time = 0

    def update(self) -> bool:
        """更新，返回是否仍在进行"""
        if not self._started:
            return False

        # 更新 Boss 位置等
        # ...

        # 更新符卡
        return self.spellcard.update()

    def get_result(self) -> 'PracticeResult':
        """获取练习结果"""
        if self._result:
            return self._result

        self._result = PracticeResult(
            success=self.boss.hp <= 0,  # 击破
            time_used=self.spellcard.time_seconds,
            time_limit=self.spellcard.time_limit,
            hp_remaining=self.boss.hp,
            hp_total=self.boss.max_hp
        )
        return self._result


@dataclass
class PracticeResult:
    """练习结果"""
    success: bool          # 是否击破
    time_used: float       # 使用时间
    time_limit: float      # 时间限制
    hp_remaining: int      # 剩余血量
    hp_total: int          # 总血量

    @property
    def is_timeout(self) -> bool:
        """是否超时"""
        return self.time_used >= self.time_limit

    @property
    def hp_percent(self) -> float:
        """剩余血量百分比"""
        if self.hp_total <= 0:
            return 0.0
        return self.hp_remaining / self.hp_total

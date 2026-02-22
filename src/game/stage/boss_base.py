"""
Boss 基类
"""

from typing import List, Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
import json
import os
import types

if TYPE_CHECKING:
    from .spellcard import SpellCard, SpellCardContext


class BossPhaseType(Enum):
    NONSPELL = "nonspell"
    SPELLCARD = "spellcard"


@dataclass
class BossPhase:
    """Boss 的一个阶段（符卡或非符）"""
    phase_type: BossPhaseType
    hp: int
    time_limit: float
    script_path: str = ""                    # 脚本路径（JSON 模式）
    script_class: Optional[type] = None      # 脚本类（程序化模式）
    name: Optional[str] = None               # 符卡名称（非符为 None）
    bonus: int = 0
    practice_unlock: bool = False

    # 运行时
    spellcard: Optional['SpellCard'] = None


class BossBase:
    """
    Boss 基类
    
    管理符卡序列，处理符卡切换
    """
    
    def __init__(self):
        self.id: str = ""
        self.name: str = ""
        self.x: float = 0.0
        self.y: float = 0.5
        self.hp: int = 0
        self.max_hp: int = 0
        
        self.phases: List[BossPhase] = []
        self.current_phase_index: int = 0
        self.current_spellcard: Optional['SpellCard'] = None
        
        self.ctx: Optional['SpellCardContext'] = None
        self._active: bool = False
        self.hit_radius: float = 0.08  # 碰撞半径（Boss 通常比小怪大）
        
        # 动画/渲染相关
        self.texture: str = ""
        self.animations: Dict[str, Any] = {}
        
        # ===== 积分系统 =====
        self._spell_bonus: int = 0         # 当前符卡 bonus（逐帧衰减）
        self._spell_no_miss: bool = True   # 当前符卡期间玩家未被击中
        self._spell_no_bomb: bool = True   # 当前符卡期间玩家未使用 bomb
    
    @classmethod
    def from_config(cls, config_path: str, ctx: 'SpellCardContext') -> 'BossBase':
        """从配置文件创建 Boss"""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        boss = cls()
        boss.ctx = ctx
        boss.id = config.get('id', '')
        boss.name = config.get('name', '')
        boss.texture = config.get('texture', '')
        boss.animations = config.get('animations', {})
        
        # 加载阶段
        base_dir = os.path.dirname(config_path)
        spellcard_dir = os.path.join(base_dir, 'spellcards')
        # 兼容旧结构：若 bosses/spellcards 不存在，则回退到 stage 根目录下的 spellcards
        if not os.path.isdir(spellcard_dir):
            spellcard_dir = os.path.normpath(os.path.join(base_dir, '..', 'spellcards'))
        
        for phase_cfg in config.get('phases', []):
            phase = BossPhase(
                phase_type=BossPhaseType(phase_cfg['type']),
                hp=phase_cfg.get('hp', 1000),
                time_limit=phase_cfg.get('time', 60),
                script_path=os.path.join(spellcard_dir, phase_cfg['script'] + '.py'),
                name=phase_cfg.get('name'),
                bonus=phase_cfg.get('bonus', 0),
                practice_unlock=phase_cfg.get('practice_unlock', False)
            )
            boss.phases.append(phase)
        
        return boss

    @classmethod
    def create(cls, boss_def, ctx: 'SpellCardContext') -> 'BossBase':
        """从 BossDef 数据对象创建 Boss（程序化模式）"""
        from dataclasses import replace

        boss = cls()
        boss.ctx = ctx
        boss.id = boss_def.id
        boss.name = boss_def.name
        boss.texture = boss_def.texture
        boss.animations = boss_def.animations.copy()

        # 复制 phases，避免修改定义中的运行时状态
        boss.phases = [replace(p, spellcard=None) for p in boss_def.phases]

        return boss

    def start(self):
        """开始 Boss 战"""
        self._active = True
        self.current_phase_index = 0
        self._start_phase(0)
    
    def _start_phase(self, index: int):
        """开始指定阶段"""
        if index >= len(self.phases):
            self._on_all_phases_complete()
            return
        
        phase = self.phases[index]
        self.current_phase_index = index
        self.hp = phase.hp
        self.max_hp = phase.hp
        
        # 重置符卡积分追踪
        self._spell_bonus = phase.bonus
        self._spell_no_miss = True
        self._spell_no_bomb = True
        
        # 加载并启动符卡：优先使用 script_class，回退到 script_path
        if phase.script_class:
            spellcard = phase.script_class()
        else:
            spellcard = self._load_spellcard(phase.script_path)
        if spellcard:
            # 用配置覆盖符卡默认值
            if phase.name:
                spellcard.name = phase.name
            spellcard.hp = phase.hp
            spellcard.time_limit = phase.time_limit
            spellcard.bonus = phase.bonus
            
            spellcard.bind(self, self.ctx)
            spellcard.start()
            self.current_spellcard = spellcard
            phase.spellcard = spellcard
            
            # 符卡开始事件
            if phase.phase_type == BossPhaseType.SPELLCARD:
                self._on_spellcard_start(phase)
    
    def _load_spellcard(self, script_path: str) -> Optional['SpellCard']:
        """动态加载符卡脚本"""
        import importlib.util
        
        if not os.path.exists(script_path):
            print(f"[Boss] 符卡脚本不存在: {script_path}")
            return None
        
        spec = importlib.util.spec_from_file_location("spellcard_module", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 查找 spellcard 变量或 SpellCard 子类
        if hasattr(module, 'spellcard'):
            return module.spellcard()
        
        # 查找第一个 SpellCard 子类
        from .spellcard import SpellCard
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, SpellCard) and obj != SpellCard:
                return obj()
        
        print(f"[Boss] 未找到符卡类: {script_path}")
        return None
    
    def update(self):
        """每帧更新"""
        if not self._active:
            return
        
        if self.current_spellcard:
            # 逐帧衰减符卡 bonus（从 max 线性衰减到 base = max/2）
            phase = self.phases[self.current_phase_index]
            if phase.bonus > 0 and self.current_spellcard._active:
                elapsed = self.current_spellcard.time_seconds
                total = phase.time_limit
                if total > 0:
                    base_bonus = phase.bonus // 2
                    ratio = min(1.0, elapsed / total)
                    self._spell_bonus = int(phase.bonus - (phase.bonus - base_bonus) * ratio)
                    self._spell_bonus = max(base_bonus, self._spell_bonus)
            
            if not self.current_spellcard.update():
                # 当前符卡结束，进入下一阶段
                self._on_phase_end()
                self._start_phase(self.current_phase_index + 1)
    
    def damage(self, amount: int):
        """受到伤害"""
        if not self._active or not self.current_spellcard:
            return
        
        self.hp -= amount
        if self.hp <= 0:
            self.hp = 0
            self.current_spellcard.end("defeated")
    
    def _on_phase_end(self):
        """阶段结束 - 结算积分、掉落道具、子弹转化"""
        phase = self.phases[self.current_phase_index]
        
        # 1. 结算符卡 bonus
        defeated = (self.hp <= 0)
        if defeated and self._spell_no_miss and self._spell_no_bomb and phase.bonus > 0:
            # 取整到 10 的倍数
            awarded = self._spell_bonus - (self._spell_bonus % 10)
            if self.ctx and awarded > 0:
                self.ctx.add_score(awarded)
            print(f"Spell Bonus! +{awarded:,}")
        elif phase.bonus > 0:
            print(f"Spell Failed (miss={not self._spell_no_miss}, bomb={not self._spell_no_bomb})")
        
        # 2. 子弹转化为道具
        if self.current_spellcard:
            self.current_spellcard.clear_bullets(to_items=True)
        
        # 3. Boss 阶段掉落道具
        if self.ctx:
            drops = {}
            if self._spell_no_miss:
                drops['life_chip'] = 1
            if self._spell_no_bomb:
                drops['bomb_chip'] = 1
            # 每个阶段额外掉一些点和 P
            drops['point'] = 5
            drops['power'] = 10
            self.ctx.spawn_drop(self.x, self.y, **drops)
        
        if phase.phase_type == BossPhaseType.SPELLCARD:
            self._on_spellcard_end(phase)
    
    def _on_spellcard_start(self, phase: BossPhase):
        """符卡开始（可覆盖）"""
        print(f"符卡开始: {phase.name}")
    
    def _on_spellcard_end(self, phase: BossPhase):
        """符卡结束（可覆盖）"""
        print(f"符卡结束: {phase.name}")
    
    def _on_all_phases_complete(self):
        """所有阶段完成 - 收集所有道具"""
        self._active = False
        # Boss 击破时，吸收场上所有道具
        if self.ctx and hasattr(self.ctx, '_item_pool') and self.ctx._item_pool:
            px = self.ctx.get_player().x if self.ctx.get_player() else 0
            py = self.ctx.get_player().y if self.ctx.get_player() else 0
            self.ctx._item_pool.collect_all(px, py)
        print(f"Boss {self.name} 击破!")
    
    # ==================== 积分系统通知 ====================
    
    def on_player_miss(self):
        """玩家被击中时由引擎调用"""
        self._spell_no_miss = False
    
    def on_player_bomb(self):
        """玩家使用 bomb 时由引擎调用"""
        self._spell_no_bomb = False
    
    @property
    def alive(self) -> bool:
        """是否存活（兼容 HUD 系统）"""
        return self._active
    
    @property
    def current_spell(self):
        """当前符卡（兼容 HUD 系统）"""
        return self.current_spellcard
    
    @property
    def current_hp(self) -> int:
        """当前 HP（兼容 HUD）"""
        return self.hp
    
    @property
    def spell_bonus_display(self) -> int:
        """当前可获得的符卡 bonus（HUD 显示用，逐帧衰减值）"""
        if self._spell_no_miss and self._spell_no_bomb:
            return self._spell_bonus
        return 0
    
    # ==================== 移动 API ====================
    
    @types.coroutine
    def move_to(self, x: float, y: float, duration: int = 60):
        """移动到指定位置"""
        start_x, start_y = self.x, self.y
        for i in range(duration):
            t = (i + 1) / duration
            # 缓动函数
            t = t * t * (3 - 2 * t)  # smoothstep
            self.x = start_x + (x - start_x) * t
            self.y = start_y + (y - start_y) * t
            yield
    
    def move_to_instant(self, x: float, y: float):
        """瞬移到指定位置"""
        self.x = x
        self.y = y
    
    # ==================== 练习模式支持 ====================
    
    def get_practiceable_spellcards(self) -> List[BossPhase]:
        """获取可练习的符卡列表"""
        return [p for p in self.phases if p.practice_unlock]
    
    def start_phase_practice(self, phase_index: int):
        """练习模式：直接开始指定阶段"""
        self._active = True
        self._start_phase(phase_index)


# ==================== 阶段定义辅助函数 ====================

def nonspell(script_class: type, hp: int, time: float, bonus: int = 100000) -> BossPhase:
    """创建非符阶段定义"""
    return BossPhase(
        phase_type=BossPhaseType.NONSPELL,
        hp=hp,
        time_limit=time,
        script_class=script_class,
        bonus=bonus,
        practice_unlock=False
    )


def spellcard(script_class: type, name: str, hp: int, time: float,
              bonus: int = 1000000, practice: bool = True) -> BossPhase:
    """创建符卡阶段定义"""
    return BossPhase(
        phase_type=BossPhaseType.SPELLCARD,
        hp=hp,
        time_limit=time,
        script_class=script_class,
        name=name,
        bonus=bonus,
        practice_unlock=practice
    )


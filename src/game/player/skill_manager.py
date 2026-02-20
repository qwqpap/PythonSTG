"""
技能槽位管理器
管理主动技能（bomb、skill）和被动技能的冷却与触发
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SkillSlot:
    """技能槽位"""
    slot: str = "bomb"          # "bomb", "skill_1", "skill_2", "passive"
    name: str = ""
    cooldown: float = 300.0     # 冷却时间（帧）
    current_cd: float = 0.0     # 当前冷却剩余（帧）
    icon: str = ""              # 图标精灵 ID
    description: str = ""
    is_passive: bool = False    # 被动技能无需手动触发

    @property
    def is_ready(self) -> bool:
        return not self.is_passive and self.current_cd <= 0

    @property
    def cd_progress(self) -> float:
        """冷却进度 0.0（冷却中）~ 1.0（就绪）"""
        if self.cooldown <= 0:
            return 1.0
        return max(0.0, 1.0 - self.current_cd / self.cooldown)


class SkillSlotManager:
    """技能槽位管理器"""

    def __init__(self):
        self.slots: Dict[str, SkillSlot] = {}

    def load_from_config(self, skills_config: list):
        """从 config.json 的 skills 列表加载"""
        self.slots.clear()
        for cfg in skills_config:
            slot_key = cfg.get('slot', 'bomb')
            is_passive = slot_key == 'passive' or cfg.get('is_passive', False)
            slot = SkillSlot(
                slot=slot_key,
                name=cfg.get('name', ''),
                cooldown=cfg.get('cooldown', 300.0),
                icon=cfg.get('icon', ''),
                description=cfg.get('description', ''),
                is_passive=is_passive,
            )
            self.slots[slot_key] = slot

    def update(self, dt: float):
        """每帧更新冷却"""
        frames = dt * 60.0
        for slot in self.slots.values():
            if slot.current_cd > 0:
                slot.current_cd = max(0.0, slot.current_cd - frames)

    def try_activate(self, slot_key: str) -> bool:
        """
        尝试激活技能，成功返回 True 并开始冷却
        """
        slot = self.slots.get(slot_key)
        if slot is None or slot.is_passive:
            return False
        if slot.current_cd > 0:
            return False
        slot.current_cd = slot.cooldown
        return True

    def get_slot(self, slot_key: str) -> Optional[SkillSlot]:
        return self.slots.get(slot_key)

    def get_active_skills(self) -> List[SkillSlot]:
        return [s for s in self.slots.values() if not s.is_passive]

    def get_passive_skills(self) -> List[SkillSlot]:
        return [s for s in self.slots.values() if s.is_passive]

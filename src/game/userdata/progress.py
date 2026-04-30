"""
玩家进度持久化：关卡解锁、最佳成绩、清关记录。

文件：userdata/progress.json
单例访问：from src.game.userdata import get_progress
"""

import os
from typing import Any, Dict, List, Optional

from ._io import load_json, save_json, USERDATA_DIR


PROGRESS_PATH = os.path.join(USERDATA_DIR, "progress.json")
PROGRESS_VERSION = 1


def _default_progress() -> Dict[str, Any]:
    return {
        "version": PROGRESS_VERSION,
        # 已解锁的关卡 ID 列表（默认 stage1 已解锁）
        "stages_unlocked": ["stage1"],
        # best_scores[stage_id][character] = score
        "best_scores": {},
        # clears[stage_id][character] = {"count": N, "no_miss": bool, "no_bomb": bool}
        "clears": {},
    }


def _merge_defaults(loaded: Dict[str, Any]) -> Dict[str, Any]:
    result = _default_progress()
    if "stages_unlocked" in loaded and isinstance(loaded["stages_unlocked"], list):
        # 去重并合并默认解锁
        merged = list(dict.fromkeys(result["stages_unlocked"] + loaded["stages_unlocked"]))
        result["stages_unlocked"] = merged
    if "best_scores" in loaded and isinstance(loaded["best_scores"], dict):
        result["best_scores"] = loaded["best_scores"]
    if "clears" in loaded and isinstance(loaded["clears"], dict):
        result["clears"] = loaded["clears"]
    result["version"] = PROGRESS_VERSION
    return result


class Progress:
    """玩家进度。"""

    def __init__(self, path: str = PROGRESS_PATH):
        self.path = path
        self._data = _merge_defaults(load_json(self.path, _default_progress()))

    # ---------- 持久化 ----------

    def save(self) -> bool:
        return save_json(self.path, self._data)

    # ---------- 关卡解锁 ----------

    def is_unlocked(self, stage_id: str) -> bool:
        return stage_id in self._data["stages_unlocked"]

    def unlock(self, stage_id: str) -> bool:
        """返回 True 表示新解锁，False 表示已解锁。"""
        if stage_id in self._data["stages_unlocked"]:
            return False
        self._data["stages_unlocked"].append(stage_id)
        return True

    def get_unlocked_stages(self) -> List[str]:
        return list(self._data["stages_unlocked"])

    # ---------- 成绩 ----------

    def get_best_score(self, stage_id: str, character: str = "default") -> int:
        return int(self._data["best_scores"].get(stage_id, {}).get(character, 0))

    def submit_score(self, stage_id: str, character: str, score: int) -> bool:
        """更新最佳成绩。返回 True 表示刷新记录。"""
        scores = self._data["best_scores"].setdefault(stage_id, {})
        old = int(scores.get(character, 0))
        if score > old:
            scores[character] = int(score)
            return True
        return False

    # ---------- 清关记录 ----------

    def record_clear(
        self,
        stage_id: str,
        character: str,
        *,
        no_miss: bool = False,
        no_bomb: bool = False,
    ):
        """记录一次清关。命中 no_miss / no_bomb 标志一旦达成即永久保留。"""
        char_data = self._data["clears"].setdefault(stage_id, {}).setdefault(
            character, {"count": 0, "no_miss": False, "no_bomb": False},
        )
        char_data["count"] = int(char_data.get("count", 0)) + 1
        if no_miss:
            char_data["no_miss"] = True
        if no_bomb:
            char_data["no_bomb"] = True

    def get_clear_record(self, stage_id: str, character: str) -> Dict[str, Any]:
        return dict(
            self._data["clears"].get(stage_id, {}).get(
                character, {"count": 0, "no_miss": False, "no_bomb": False},
            )
        )

    # ---------- 调试 ----------

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)


# ---------- 单例访问 ----------

_singleton: Optional[Progress] = None


def get_progress() -> Progress:
    global _singleton
    if _singleton is None:
        _singleton = Progress()
    return _singleton

"""
全局设置持久化：音量、键位、显示选项、上次自机。

文件：userdata/settings.json
单例访问：from src.game.userdata import get_settings
"""

import os
from typing import Any, Dict, Optional

from ._io import load_json, save_json, USERDATA_DIR


SETTINGS_PATH = os.path.join(USERDATA_DIR, "settings.json")
SETTINGS_VERSION = 1


def _default_settings() -> Dict[str, Any]:
    return {
        "version": SETTINGS_VERSION,
        "audio": {
            "se_volume": 0.7,
            "bgm_volume": 0.6,
        },
        "video": {
            "fullscreen": False,
        },
        "gameplay": {
            "last_character": "tao",  # tao / orin / tenshi
        },
        "keybindings": {
            # 玩家配置中通过 key_name_to_code 解析；此处使用 pygame 风格名
            "shoot":  "K_z",
            "bomb":   "K_x",
            "switch": "K_c",
            "focus":  "K_LSHIFT",
            "up":     "K_UP",
            "down":   "K_DOWN",
            "left":   "K_LEFT",
            "right":  "K_RIGHT",
            "pause":  "K_ESCAPE",
        },
    }


def _merge_defaults(loaded: Dict[str, Any]) -> Dict[str, Any]:
    """递归填充缺失字段，保证旧版本存档兼容。"""
    result = _default_settings()
    for top_key, default_value in result.items():
        if top_key not in loaded:
            continue
        value = loaded[top_key]
        if isinstance(default_value, dict) and isinstance(value, dict):
            merged = dict(default_value)
            merged.update({k: v for k, v in value.items() if k in default_value})
            result[top_key] = merged
        else:
            result[top_key] = value
    result["version"] = SETTINGS_VERSION
    return result


class Settings:
    """游戏全局设置，模块级单例（通过 get_settings() 访问）。"""

    def __init__(self, path: str = SETTINGS_PATH):
        self.path = path
        self._data = _merge_defaults(load_json(self.path, _default_settings()))

    # ---------- 持久化 ----------

    def save(self) -> bool:
        return save_json(self.path, self._data)

    def reload(self):
        self._data = _merge_defaults(load_json(self.path, _default_settings()))

    # ---------- 通用访问 ----------

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any):
        if section not in self._data or not isinstance(self._data[section], dict):
            self._data[section] = {}
        self._data[section][key] = value

    def as_dict(self) -> Dict[str, Any]:
        # 浅拷贝足够外部只读；嵌套 dict 共享引用以便对调试者直观
        return dict(self._data)

    # ---------- 便捷快捷方式 ----------

    @property
    def se_volume(self) -> float:
        return float(self.get("audio", "se_volume", 0.7))

    @se_volume.setter
    def se_volume(self, value: float):
        self.set("audio", "se_volume", max(0.0, min(1.0, float(value))))

    @property
    def bgm_volume(self) -> float:
        return float(self.get("audio", "bgm_volume", 0.6))

    @bgm_volume.setter
    def bgm_volume(self, value: float):
        self.set("audio", "bgm_volume", max(0.0, min(1.0, float(value))))

    @property
    def fullscreen(self) -> bool:
        return bool(self.get("video", "fullscreen", False))

    @fullscreen.setter
    def fullscreen(self, value: bool):
        self.set("video", "fullscreen", bool(value))

    @property
    def last_character(self) -> str:
        return str(self.get("gameplay", "last_character", "tao"))

    @last_character.setter
    def last_character(self, value: str):
        self.set("gameplay", "last_character", str(value))

    def get_keybinding(self, action: str, default: str = "") -> str:
        return str(self.get("keybindings", action, default))

    def set_keybinding(self, action: str, key_name: str):
        self.set("keybindings", action, key_name)

    # ---------- 应用到引擎 ----------

    def apply_audio(self, audio_manager) -> None:
        """将音量设置同步到 AudioManager。"""
        try:
            audio_manager.set_se_volume(self.se_volume)
            audio_manager.set_bgm_volume(self.bgm_volume)
        except Exception as e:
            print(f"[Settings] 应用音频设置失败: {e}")


# ---------- 单例访问 ----------

_singleton: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局 Settings 单例（首次调用时自动加载）。"""
    global _singleton
    if _singleton is None:
        _singleton = Settings()
    return _singleton

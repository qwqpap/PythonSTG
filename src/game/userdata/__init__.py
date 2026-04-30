"""
用户数据持久化模块

提供三类用户数据：
- Settings: 音量、键位、显示选项、上次自机（settings.json）
- Progress: 关卡解锁、最佳成绩（progress.json）
- Replay: 输入序列重放（replays/<timestamp>.json）

所有文件存放在 userdata/ 目录下。读写均失败安全：损坏的文件回退默认值，
保存失败仅打印警告，不中断游戏。
"""

from .settings import Settings, get_settings
from .progress import Progress, get_progress
from .replay import (
    Replay,
    ReplayRecorder,
    ReplayPlayback,
    INPUT_KEYS,
    list_replays,
    load_replay,
)

__all__ = [
    "Settings",
    "get_settings",
    "Progress",
    "get_progress",
    "Replay",
    "ReplayRecorder",
    "ReplayPlayback",
    "INPUT_KEYS",
    "list_replays",
    "load_replay",
]

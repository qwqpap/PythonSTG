"""
Replay（重放）系统：录制和回放玩家输入。

设计原则
--------
1. 确定性：依赖固定 60fps 时间步 + 单一 RNG 种子。
2. 紧凑：每帧仅记录玩家相关按键的位掩码（1 字节/帧）。
3. 自洽：文件中保存 stage_id、character、rng_seed、起始版本号。

回放工作原理
-----------
- 录制时：StageManager 启动时调用 random.seed(seed) / np.random.seed(seed)，
  每帧调用 ReplayRecorder.capture(keys)。
- 回放时：使用同样的 seed 重新进入关卡，主循环用 ReplayPlayback.next_keys()
  替代真实键盘状态。
- dt 强制为 1/60 秒（在主循环中处理）。

文件位置：userdata/replays/<timestamp>_<stage>_<char>.json
"""

import base64
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import glfw

from ._io import load_json, save_json, ensure_userdata_dir, USERDATA_DIR


REPLAY_DIR = os.path.join(USERDATA_DIR, "replays")
REPLAY_VERSION = 1
REPLAY_ENGINE_TAG = "pystg-0.1"


# 编码顺序固定，扩展时只能在末尾追加，不能重排（否则旧 replay 解码错位）
INPUT_KEYS: List[int] = [
    glfw.KEY_UP,             # bit 0
    glfw.KEY_DOWN,           # bit 1
    glfw.KEY_LEFT,           # bit 2
    glfw.KEY_RIGHT,          # bit 3
    glfw.KEY_LEFT_SHIFT,     # bit 4 (focus)
    glfw.KEY_RIGHT_SHIFT,    # bit 5 (focus alt)
    glfw.KEY_Z,              # bit 6 (shoot)
    glfw.KEY_X,              # bit 7 (bomb)
]
# 注意：KEY_C（切换自机）刻意不录入，回放期间禁用切换以防破坏确定性


def encode_keys(keys) -> int:
    """把 KeyboardState 编码为单字节位掩码。"""
    bits = 0
    for i, code in enumerate(INPUT_KEYS):
        if keys[code]:
            bits |= (1 << i)
    return bits & 0xFF


def decode_keys(byte: int) -> Dict[int, bool]:
    """位掩码 → {key_code: pressed} 字典。"""
    result: Dict[int, bool] = {}
    for i, code in enumerate(INPUT_KEYS):
        result[code] = bool(byte & (1 << i))
    return result


# =========================================================================
# Replay 数据模型
# =========================================================================


class Replay:
    """已加载的 replay 数据。"""

    def __init__(self, data: Dict[str, Any]):
        self.version: int = int(data.get("version", REPLAY_VERSION))
        self.engine: str = str(data.get("engine", ""))
        self.created_at: str = str(data.get("created_at", ""))
        self.stage: str = str(data.get("stage", ""))
        self.character: str = str(data.get("character", "tao"))
        self.rng_seed: int = int(data.get("rng_seed", 0))
        self.frame_count: int = int(data.get("frame_count", 0))
        self.result: Dict[str, Any] = dict(data.get("result", {}))
        # inputs: base64 编码的字节流，每字节 = 1 帧的位掩码
        self._inputs: bytes = self._decode_inputs(data.get("inputs", ""))

    @staticmethod
    def _decode_inputs(value: Any) -> bytes:
        if isinstance(value, str) and value:
            try:
                return base64.b64decode(value)
            except Exception as e:
                print(f"[Replay] 输入流解码失败: {e}")
        return b""

    def get_frame_keys(self, frame_index: int) -> Dict[int, bool]:
        if 0 <= frame_index < len(self._inputs):
            return decode_keys(self._inputs[frame_index])
        # 越界则视为全部松开
        return decode_keys(0)

    def __repr__(self) -> str:
        return (
            f"<Replay stage={self.stage} char={self.character} "
            f"frames={self.frame_count} seed={self.rng_seed}>"
        )


def list_replays() -> List[Dict[str, Any]]:
    """扫描 replay 目录，返回 [{path, stage, character, frame_count, created_at}, ...]。"""
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(REPLAY_DIR):
        return out
    for filename in sorted(os.listdir(REPLAY_DIR), reverse=True):
        if not filename.endswith(".json"):
            continue
        full = os.path.join(REPLAY_DIR, filename)
        try:
            with open(full, "r", encoding="utf-8") as f:
                head = json.load(f)
            out.append({
                "path": full,
                "filename": filename,
                "stage": head.get("stage", ""),
                "character": head.get("character", ""),
                "frame_count": int(head.get("frame_count", 0)),
                "created_at": head.get("created_at", ""),
                "result": head.get("result", {}),
            })
        except Exception as e:
            print(f"[Replay] 跳过损坏文件 {filename}: {e}")
    return out


def load_replay(path: str) -> Optional[Replay]:
    data = load_json(path, default={})
    if not data:
        return None
    return Replay(data)


# =========================================================================
# 录制
# =========================================================================


class ReplayRecorder:
    """
    每帧调用 capture(keys) 记录玩家输入。
    游戏结束后调用 save() 写入磁盘。
    """

    def __init__(self, stage_id: str, character: str, rng_seed: int):
        self.stage_id = stage_id
        self.character = character
        self.rng_seed = int(rng_seed)
        self._buffer = bytearray()

    def capture(self, keys) -> None:
        self._buffer.append(encode_keys(keys))

    @property
    def frame_count(self) -> int:
        return len(self._buffer)

    def to_dict(self, result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "version": REPLAY_VERSION,
            "engine": REPLAY_ENGINE_TAG,
            "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "stage": self.stage_id,
            "character": self.character,
            "rng_seed": self.rng_seed,
            "frame_count": self.frame_count,
            "result": dict(result or {}),
            "inputs": base64.b64encode(bytes(self._buffer)).decode("ascii"),
        }

    def save(self, result: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """保存到 userdata/replays/<timestamp>_<stage>_<char>.json，返回路径。"""
        if self.frame_count == 0:
            return None
        ensure_userdata_dir("replays")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        # 文件名清洗：避免空白和分隔符
        safe_stage = "".join(c for c in (self.stage_id or "stage") if c.isalnum() or c in "_-")
        safe_char = "".join(c for c in (self.character or "char") if c.isalnum() or c in "_-")
        filename = f"{stamp}_{safe_stage}_{safe_char}.json"
        path = os.path.join(REPLAY_DIR, filename)
        if save_json(path, self.to_dict(result)):
            return path
        return None


# =========================================================================
# 回放
# =========================================================================


class ReplayPlayback:
    """
    回放控制器：每帧调用 next_keys() 取出本帧应注入的 KeyboardState-like 对象。
    """

    class _FakeKeyboardState:
        """提供 keys[code] 接口的轻量 dict 包装。"""
        __slots__ = ("_states",)

        def __init__(self, states: Dict[int, bool]):
            self._states = states

        def __getitem__(self, key):
            return self._states.get(key, False)

    def __init__(self, replay: Replay):
        self.replay = replay
        self._frame = 0

    @property
    def stage_id(self) -> str:
        return self.replay.stage

    @property
    def character(self) -> str:
        return self.replay.character

    @property
    def rng_seed(self) -> int:
        return self.replay.rng_seed

    @property
    def frame_index(self) -> int:
        return self._frame

    @property
    def is_finished(self) -> bool:
        return self._frame >= self.replay.frame_count

    def next_keys(self) -> "ReplayPlayback._FakeKeyboardState":
        states = self.replay.get_frame_keys(self._frame)
        self._frame += 1
        return ReplayPlayback._FakeKeyboardState(states)

    def reset(self):
        self._frame = 0

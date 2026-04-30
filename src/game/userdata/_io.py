"""共享 JSON 读写工具：原子写入、损坏回退、目录自动创建。"""

import json
import os
import tempfile
from typing import Any, Dict, Optional


USERDATA_DIR = "userdata"


def ensure_userdata_dir(subpath: str = "") -> str:
    """确保 userdata/<subpath> 存在，返回该绝对路径（相对工作目录）。"""
    path = os.path.join(USERDATA_DIR, subpath) if subpath else USERDATA_DIR
    os.makedirs(path, exist_ok=True)
    return path


def load_json(path: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """读 JSON。文件缺失或损坏返回 default 副本。"""
    if default is None:
        default = {}
    if not os.path.exists(path):
        return dict(default)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(default)
        return data
    except Exception as e:
        print(f"[userdata] 读取 {path} 失败，回退默认: {e}")
        return dict(default)


def save_json(path: str, data: Dict[str, Any]) -> bool:
    """原子写入 JSON。先写临时文件再 rename，避免半写损坏。"""
    try:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        # tempfile + rename 保证原子性
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", dir=directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            # 写入失败清理临时文件
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
        return True
    except Exception as e:
        print(f"[userdata] 保存 {path} 失败: {e}")
        return False

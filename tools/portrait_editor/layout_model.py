"""立绘编辑器数据模型 - layout 加载/保存 + 角色扫描"""

import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from src.core.atomic_io import atomic_write_json

LAYOUT_PATH = os.path.join(PROJECT_ROOT, "assets", "ui", "dialog_portrait_layout.json")
CHAR_DIR = os.path.join(PROJECT_ROOT, "assets", "images", "character")

GAME_VIEW_W = 768   # game_view_width = base_width * game_scale = 384 * 2
GAME_VIEW_H = 896   # game_view_height = base_height * game_scale = 448 * 2


def default_layout():
    return {
        "slots": {
            "left": {"anchor_px": [220, GAME_VIEW_H - 40]},
            "right": {"anchor_px": [GAME_VIEW_W - 220, GAME_VIEW_H - 40]},
        },
        "focus": {
            "speaker_lift_px": 20,
            "inactive_lift_px": 0,
            "active_alpha": 1.0,
            "inactive_alpha": 0.62,
            "active_saturation": 1.0,
            "inactive_saturation": 0.35,
        },
        "render_order": ["left", "right"],
    }


def load_layout():
    if not os.path.exists(LAYOUT_PATH):
        return default_layout()
    try:
        with open(LAYOUT_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        cfg = default_layout()
        if "slots" in loaded:
            cfg["slots"].update(loaded["slots"])
        if "focus" in loaded:
            cfg["focus"].update(loaded["focus"])
        if "render_order" in loaded:
            cfg["render_order"] = loaded["render_order"]
        return cfg
    except Exception:
        return default_layout()


def save_layout(cfg):
    atomic_write_json(LAYOUT_PATH, cfg)


def load_characters():
    """扫描所有有 character.json 的角色目录，返回角色字典"""
    characters = {}
    if not os.path.isdir(CHAR_DIR):
        return characters
    for char_name in sorted(os.listdir(CHAR_DIR)):
        char_path = os.path.join(CHAR_DIR, char_name)
        cfg_path = os.path.join(char_path, "character.json")
        if not os.path.isdir(char_path) or not os.path.exists(cfg_path):
            continue
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            characters[char_name] = cfg
        except Exception:
            continue
    return characters

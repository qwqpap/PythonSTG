"""
主菜单布局配置

提供默认布局、加载、保存 main_menu_layout.json。
"""

import json
import os
from typing import Dict, Any


def default_layout() -> Dict[str, Any]:
    """返回默认主菜单布局，与 MainMenuRenderer 原硬编码值一致。"""
    return {
        "title": {
            "text": "弹幕游戏",
            "font_size": 56,
            "color": [220, 220, 255],
            "y_ratio": 0.25,
        },
        "options": [
            {"text": "开始游戏"},
            {"text": "退出"},
        ],
        "option_spacing": 48,
        "option_colors": {
            "normal": [160, 160, 180],
            "selected": [255, 255, 200],
        },
        "hint": {
            "text": "方向键 ↑↓ 选择  Z 确认  ESC 退出",
            "font_size": 18,
            "color": [100, 100, 120],
            "y_offset": -50,
        },
        "bg_gradient": {
            "top": [12, 8, 28],
            "bottom": [20, 20, 44],
        },
    }


def load_layout(path: str) -> Dict[str, Any]:
    """
    从 JSON 文件加载主菜单布局。
    若文件不存在或解析失败，返回 default_layout()。
    """
    if not path or not os.path.exists(path):
        return default_layout()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _merge_with_default(data)
    except Exception:
        return default_layout()


def save_layout(path: str, layout: Dict[str, Any]) -> bool:
    """保存布局到 JSON 文件。"""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(layout, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _merge_with_default(data: Dict[str, Any]) -> Dict[str, Any]:
    """将加载的数据与默认值合并，填充缺失字段。"""
    default = default_layout()
    result = default.copy()
    for key in default:
        if key in data:
            if isinstance(default[key], dict) and isinstance(data[key], dict):
                result[key] = {**default[key], **data[key]}
            elif key == "options" and isinstance(data[key], list):
                result[key] = data[key]
            else:
                result[key] = data[key]
    return result

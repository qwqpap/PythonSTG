"""
BackgroundScene - 可复用的背景场景

在关卡脚本中快速加载和切换背景:

    from src.game.background_render.scene import BackgroundScene

    # 列出所有可用场景
    print(BackgroundScene.list_all())
    # -> ['bamboo', 'gensokyosora', 'lake', 'temple']

    # 加载场景
    scene = BackgroundScene.load("bamboo")
    print(scene)
    # -> BackgroundScene('bamboo', layers=2, textures=['bamboo_far', 'ground'])

    # 应用到 DataDrivenBackground 或 BackgroundRenderer
    bg = scene.apply(background_renderer)

    # 查看场景属性
    print(scene.description)         # "竹林背景 - 多层竹林深度效果"
    print(scene.layer_count)         # 2
    print(scene.texture_names)       # ['bamboo_far', 'ground']
    print(scene.camera_config)       # {'eye': [0, -1.4, 2.5], ...}
"""

import os
import json
from typing import List, Optional, Dict, Any
from pathlib import Path

# 背景资源根目录
_BG_DIR = Path(__file__).parent.parent.parent.parent / "assets" / "images" / "background"


class BackgroundScene:
    """
    可复用的背景场景封装

    封装一个完整的背景配置 (JSON)，提供便捷的加载和应用接口。
    每个场景对应 assets/images/background/{name}.json。
    """

    def __init__(self, name: str, config: dict, config_path: str = ""):
        self.name = name
        self.config = config
        self.config_path = config_path

    # ==================== 工厂方法 ====================

    @classmethod
    def load(cls, name: str, base_dir: Optional[str] = None) -> 'BackgroundScene':
        """
        按名称加载背景场景

        Args:
            name: 场景名称 (对应 assets/images/background/{name}.json)
            base_dir: 可选的自定义基础目录

        Returns:
            BackgroundScene 实例

        Raises:
            FileNotFoundError: 场景文件不存在
            json.JSONDecodeError: JSON 解析失败
        """
        bg_dir = Path(base_dir) if base_dir else _BG_DIR
        json_path = bg_dir / f"{name}.json"

        if not json_path.exists():
            raise FileNotFoundError(f"背景场景不存在: {json_path}")

        with open(json_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        return cls(name, config, str(json_path))

    @classmethod
    def list_all(cls, base_dir: Optional[str] = None) -> List[str]:
        """
        列出所有可用的背景场景名称

        Returns:
            场景名称列表 (按字母排序)
        """
        bg_dir = Path(base_dir) if base_dir else _BG_DIR
        if not bg_dir.exists():
            return []
        return sorted([f.stem for f in bg_dir.glob("*.json")])

    @classmethod
    def load_all(cls, base_dir: Optional[str] = None) -> Dict[str, 'BackgroundScene']:
        """
        加载所有可用场景

        Returns:
            {name: BackgroundScene} 字典
        """
        result = {}
        for name in cls.list_all(base_dir):
            try:
                result[name] = cls.load(name, base_dir)
            except Exception:
                pass
        return result

    # ==================== 应用到渲染器 ====================

    def apply(self, target) -> Any:
        """
        将场景应用到背景渲染系统

        Args:
            target: DataDrivenBackground 实例或 BackgroundRenderer 实例

        Returns:
            应用后的 DataDrivenBackground 实例

        用法:
            # 方式1: 直接传 DataDrivenBackground
            scene.apply(data_driven_bg)

            # 方式2: 传 BackgroundRenderer, 自动创建 DataDrivenBackground
            bg = scene.apply(background_renderer)
        """
        from .data_driven_background import DataDrivenBackground

        if isinstance(target, DataDrivenBackground):
            target.load_by_name(self.name)
            return target
        else:
            # 假定是 BackgroundRenderer
            bg = DataDrivenBackground(target)
            bg.load_by_name(self.name)
            return bg

    # ==================== 属性访问 ====================

    @property
    def description(self) -> str:
        """场景描述"""
        return self.config.get("description", "")

    @property
    def layer_count(self) -> int:
        """图层数量"""
        return len(self.config.get("layers", []))

    @property
    def texture_names(self) -> List[str]:
        """纹理名称列表"""
        return list(self.config.get("textures", {}).keys())

    @property
    def camera_config(self) -> dict:
        """摄像机配置"""
        return self.config.get("camera", {})

    @property
    def fog_config(self) -> dict:
        """雾效配置"""
        return self.config.get("fog", {})

    @property
    def scroll_config(self) -> dict:
        """滚动配置"""
        return self.config.get("scroll", {})

    def get_layer(self, name: str) -> Optional[dict]:
        """获取指定名称的图层配置"""
        for layer in self.config.get("layers", []):
            if layer.get("name") == name:
                return layer
        return None

    def get_layers(self) -> List[dict]:
        """获取所有图层配置"""
        return self.config.get("layers", [])

    # ==================== 序列化 ====================

    def to_json(self, path: Optional[str] = None) -> str:
        """
        导出为 JSON 字符串 (或保存到文件)

        Args:
            path: 可选的文件保存路径

        Returns:
            JSON 字符串
        """
        text = json.dumps(self.config, indent=2, ensure_ascii=False)
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
        return text

    def __repr__(self):
        return (f"BackgroundScene('{self.name}', "
                f"layers={self.layer_count}, "
                f"textures={self.texture_names})")

"""
背景配置系统

支持通过 JSON 配置文件定义静态背景图层。
对于需要动态逻辑的背景，请使用 procedural_background.py 中的程序化背景类。
"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


@dataclass
class BackgroundTextureConfig:
    """背景纹理配置"""
    name: str                    # 纹理名称/ID
    path: str                    # 相对路径
    rect: Optional[Tuple[int, int, int, int]] = None  # 可选的裁剪区域
    blend_mode: str = "normal"   # 混合模式
    alpha: float = 1.0           # 透明度


@dataclass
class Camera3DConfig:
    """3D摄像机配置"""
    eye: Tuple[float, float, float] = (0.0, 0.0, -1.0)
    at: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    up: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    fovy: float = 0.6
    z_near: float = 0.01
    z_far: float = 10.0


@dataclass
class FogConfig:
    """雾效配置"""
    enabled: bool = True
    start: float = 3.0
    end: float = 6.0
    color: Tuple[int, int, int, int] = (0, 0, 0, 255)  # RGBA


@dataclass
class LayerConfig:
    """图层配置"""
    texture: str                 # 纹理名称引用
    z_order: int = 0
    scroll_speed: Tuple[float, float] = (0.0, 0.0)
    parallax_factor: float = 1.0
    alpha: float = 1.0
    blend_mode: str = "normal"
    tile_repeat: Tuple[int, int] = (1, 1)
    
    # 3D渲染参数
    use_3d: bool = False
    vertices_3d: Optional[List[List[float]]] = None


@dataclass 
class BackgroundConfig:
    """完整背景配置"""
    name: str
    description: str = ""
    
    # 纹理列表
    textures: List[BackgroundTextureConfig] = field(default_factory=list)
    
    # 摄像机配置
    camera: Camera3DConfig = field(default_factory=Camera3DConfig)
    
    # 雾效配置
    fog: FogConfig = field(default_factory=FogConfig)
    
    # 图层配置
    layers: List[LayerConfig] = field(default_factory=list)
    
    # 动画参数
    scroll_speed: float = 0.01
    
    def to_dict(self) -> dict:
        """转换为字典（用于JSON序列化）"""
        return {
            "name": self.name,
            "description": self.description,
            "textures": [asdict(t) for t in self.textures],
            "camera": asdict(self.camera),
            "fog": asdict(self.fog),
            "layers": [asdict(l) for l in self.layers],
            "scroll_speed": self.scroll_speed
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'BackgroundConfig':
        """从字典创建"""
        config = cls(name=data.get("name", "unknown"))
        config.description = data.get("description", "")
        config.scroll_speed = data.get("scroll_speed", 0.01)
        
        # 解析纹理
        for tex_data in data.get("textures", []):
            config.textures.append(BackgroundTextureConfig(
                name=tex_data["name"],
                path=tex_data["path"],
                rect=tuple(tex_data["rect"]) if tex_data.get("rect") else None,
                blend_mode=tex_data.get("blend_mode", "normal"),
                alpha=tex_data.get("alpha", 1.0)
            ))
        
        # 解析摄像机
        cam_data = data.get("camera", {})
        config.camera = Camera3DConfig(
            eye=tuple(cam_data.get("eye", [0, 0, -1])),
            at=tuple(cam_data.get("at", [0, 0, 0])),
            up=tuple(cam_data.get("up", [0, 1, 0])),
            fovy=cam_data.get("fovy", 0.6),
            z_near=cam_data.get("z_near", 0.01),
            z_far=cam_data.get("z_far", 10.0)
        )
        
        # 解析雾效
        fog_data = data.get("fog", {})
        config.fog = FogConfig(
            enabled=fog_data.get("enabled", True),
            start=fog_data.get("start", 3.0),
            end=fog_data.get("end", 6.0),
            color=tuple(fog_data.get("color", [0, 0, 0, 255]))
        )
        
        # 解析图层
        for layer_data in data.get("layers", []):
            vertices = layer_data.get("vertices_3d")
            config.layers.append(LayerConfig(
                texture=layer_data["texture"],
                z_order=layer_data.get("z_order", 0),
                scroll_speed=tuple(layer_data.get("scroll_speed", [0, 0])),
                parallax_factor=layer_data.get("parallax_factor", 1.0),
                alpha=layer_data.get("alpha", 1.0),
                blend_mode=layer_data.get("blend_mode", "normal"),
                tile_repeat=tuple(layer_data.get("tile_repeat", [1, 1])),
                use_3d=layer_data.get("use_3d", False),
                vertices_3d=[list(v) for v in vertices] if vertices else None
            ))
        
        return config


def load_background_config(json_path: str) -> Optional[BackgroundConfig]:
    """
    从JSON文件加载背景配置
    
    Args:
        json_path: JSON配置文件路径
        
    Returns:
        BackgroundConfig 或 None
    """
    if not os.path.exists(json_path):
        print(f"配置文件不存在: {json_path}")
        return None
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return BackgroundConfig.from_dict(data)
    except Exception as e:
        print(f"加载配置失败 {json_path}: {e}")
        return None


def save_background_config(config: BackgroundConfig, json_path: str) -> bool:
    """
    保存背景配置到JSON文件
    
    Args:
        config: 背景配置
        json_path: 输出文件路径
        
    Returns:
        是否保存成功
    """
    try:
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"保存配置失败 {json_path}: {e}")
        return False

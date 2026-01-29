"""
数据驱动的背景系统

从 JSON 配置文件加载背景定义，支持：
- 多层纹理平铺
- 3D 摄像机和雾效
- 可配置的滚动速度和混合模式
- 实时参数调整
"""

import json
import os
from typing import Dict, List, Tuple, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

if TYPE_CHECKING:
    from .background_renderer import BackgroundRenderer


class BlendMode(Enum):
    """混合模式"""
    NORMAL = "normal"
    ADD = "add"
    MULTIPLY = "multiply"


@dataclass
class TextureInfo:
    """纹理信息"""
    name: str
    path: str
    full_path: str = ""
    description: str = ""


@dataclass
class CameraConfig:
    """摄像机配置"""
    eye: Tuple[float, float, float] = (0, 0, 1)
    at: Tuple[float, float, float] = (0, 0, 0)
    up: Tuple[float, float, float] = (0, 1, 0)
    fovy: float = 0.8
    z_near: float = 0.1
    z_far: float = 10.0


@dataclass
class FogConfig:
    """雾效配置"""
    enabled: bool = False
    color: Tuple[int, int, int, int] = (0, 0, 0, 255)
    start: float = 0.0
    end: float = 10.0


@dataclass
class TileConfig:
    """平铺配置"""
    x_range: Tuple[int, int] = (-1, 1)
    y_range: Tuple[int, int] = (-4, 7)
    size: float = 1.0


@dataclass
class LayerVariant:
    """图层变体（同一纹理的不同位置/速度）"""
    offset: Tuple[float, float] = (0, 0)
    scroll_multiplier: float = 1.0


@dataclass
class LayerConfig:
    """图层配置"""
    name: str
    texture: str
    z_order: int = 0
    z_depth: float = 0.0
    blend_mode: BlendMode = BlendMode.NORMAL
    alpha: float = 1.0
    scroll_multiplier: float = 1.0
    tile: TileConfig = field(default_factory=TileConfig)
    variants: List[LayerVariant] = field(default_factory=list)
    enabled: bool = True


@dataclass
class ScrollConfig:
    """滚动配置"""
    base_speed: float = 0.001
    direction: Tuple[float, float] = (0, 1)


@dataclass
class BackgroundData:
    """完整的背景数据"""
    name: str
    description: str = ""
    textures: Dict[str, TextureInfo] = field(default_factory=dict)
    camera: CameraConfig = field(default_factory=CameraConfig)
    fog: FogConfig = field(default_factory=FogConfig)
    scroll: ScrollConfig = field(default_factory=ScrollConfig)
    layers: List[LayerConfig] = field(default_factory=list)
    
    # 运行时状态
    time: float = 0.0
    scroll_offset: float = 0.0


class DataDrivenBackground:
    """
    数据驱动的背景
    
    从 JSON 配置加载，动态渲染
    """
    
    ASSET_BASE = "assets/images/background"
    
    def __init__(self, renderer: 'BackgroundRenderer'):
        self.renderer = renderer
        self.data: Optional[BackgroundData] = None
        self.config_path: str = ""
        
        # 渲染四边形缓存
        self.quads: List[Dict] = []
    
    def load_from_json(self, json_path: str) -> bool:
        """
        从 JSON 文件加载背景配置
        
        Args:
            json_path: JSON 配置文件路径
            
        Returns:
            是否加载成功
        """
        if not os.path.exists(json_path):
            print(f"[Background] 配置文件不存在: {json_path}")
            return False
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            self.config_path = json_path
            self.data = self._parse_config(config, os.path.dirname(json_path))
            
            # 加载所有纹理
            for tex in self.data.textures.values():
                if not self.renderer.load_texture(tex.full_path):
                    print(f"[Background] 警告: 纹理加载失败 {tex.full_path}")
            
            print(f"[Background] 已加载背景: {self.data.name} ({len(self.data.layers)} 图层)")
            return True
            
        except Exception as e:
            print(f"[Background] 加载失败 {json_path}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def load_by_name(self, name: str) -> bool:
        """
        按名称加载背景
        
        Args:
            name: 背景名称（对应 assets/images/background/{name}.json）
        """
        json_path = os.path.join(self.ASSET_BASE, f"{name}.json")
        return self.load_from_json(json_path)
    
    def _parse_config(self, config: dict, base_dir: str) -> BackgroundData:
        """解析 JSON 配置"""
        data = BackgroundData(
            name=config.get("name", "unknown"),
            description=config.get("description", "")
        )
        
        # 解析纹理
        for tex_name, tex_info in config.get("textures", {}).items():
            path = tex_info.get("path", "")
            full_path = os.path.join(base_dir, path)
            data.textures[tex_name] = TextureInfo(
                name=tex_name,
                path=path,
                full_path=full_path,
                description=tex_info.get("description", "")
            )
        
        # 解析摄像机
        cam = config.get("camera", {})
        data.camera = CameraConfig(
            eye=tuple(cam.get("eye", [0, 0, 1])),
            at=tuple(cam.get("at", [0, 0, 0])),
            up=tuple(cam.get("up", [0, 1, 0])),
            fovy=cam.get("fovy", 0.8),
            z_near=cam.get("z_near", 0.1),
            z_far=cam.get("z_far", 10.0)
        )
        
        # 解析雾效
        fog = config.get("fog", {})
        data.fog = FogConfig(
            enabled=fog.get("enabled", False),
            color=tuple(fog.get("color", [0, 0, 0, 255])),
            start=fog.get("start", 0.0),
            end=fog.get("end", 10.0)
        )
        
        # 解析滚动
        scroll = config.get("scroll", {})
        data.scroll = ScrollConfig(
            base_speed=scroll.get("base_speed", 0.001),
            direction=tuple(scroll.get("direction", [0, 1]))
        )
        
        # 解析图层
        for layer_cfg in config.get("layers", []):
            tile_cfg = layer_cfg.get("tile", {})
            tile = TileConfig(
                x_range=tuple(tile_cfg.get("x_range", [-1, 1])),
                y_range=tuple(tile_cfg.get("y_range", [-4, 7])),
                size=tile_cfg.get("size", 1.0)
            )
            
            # 解析变体
            variants = []
            for var_cfg in layer_cfg.get("variants", []):
                variants.append(LayerVariant(
                    offset=tuple(var_cfg.get("offset", [0, 0])),
                    scroll_multiplier=var_cfg.get("scroll_multiplier", 1.0)
                ))
            
            # 解析混合模式
            blend_str = layer_cfg.get("blend_mode", "normal").lower()
            blend_mode = BlendMode.NORMAL
            if blend_str == "add":
                blend_mode = BlendMode.ADD
            elif blend_str == "multiply":
                blend_mode = BlendMode.MULTIPLY
            
            layer = LayerConfig(
                name=layer_cfg.get("name", ""),
                texture=layer_cfg.get("texture", ""),
                z_order=layer_cfg.get("z_order", 0),
                z_depth=layer_cfg.get("z_depth", 0.0),
                blend_mode=blend_mode,
                alpha=layer_cfg.get("alpha", 1.0),
                scroll_multiplier=layer_cfg.get("scroll_multiplier", 1.0),
                tile=tile,
                variants=variants,
                enabled=layer_cfg.get("enabled", True)
            )
            data.layers.append(layer)
        
        # 按 z_order 排序
        data.layers.sort(key=lambda x: x.z_order)
        
        return data
    
    def update(self, dt: float):
        """更新背景状态"""
        if not self.data:
            return
        
        self.data.time += dt
        self.data.scroll_offset += self.data.scroll.base_speed * dt
    
    def render(self):
        """渲染背景"""
        if not self.data:
            return
        
        self.quads.clear()
        
        # 应用摄像机设置
        self._apply_camera()
        
        # 渲染每个图层
        for layer in self.data.layers:
            if not layer.enabled:
                continue
            
            tex_info = self.data.textures.get(layer.texture)
            if not tex_info:
                continue
            
            # 计算滚动偏移
            scroll_y = self.data.scroll_offset * layer.scroll_multiplier
            
            # 渲染主要 tiles
            self._render_layer_tiles(layer, tex_info, scroll_y, (0, 0))
            
            # 渲染变体
            for variant in layer.variants:
                var_scroll = self.data.scroll_offset * variant.scroll_multiplier
                self._render_layer_tiles(layer, tex_info, var_scroll, variant.offset)
    
    def _apply_camera(self):
        """应用摄像机和雾效设置"""
        cam = self.data.camera
        self.renderer.set_camera(
            eye=cam.eye,
            at=cam.at,
            up=cam.up,
            fovy=cam.fovy
        )
        self.renderer.camera.z_near = cam.z_near
        self.renderer.camera.z_far = cam.z_far
        
        fog = self.data.fog
        fog_color = (
            fog.color[0] / 255.0,
            fog.color[1] / 255.0,
            fog.color[2] / 255.0,
            fog.color[3] / 255.0 if len(fog.color) > 3 else 1.0
        )
        self.renderer.set_fog(fog_color, fog.start, fog.end, fog.enabled)
    
    def _render_layer_tiles(self, layer: LayerConfig, tex_info: TextureInfo, 
                           scroll_y: float, offset: Tuple[float, float]):
        """渲染图层的所有 tiles"""
        tile = layer.tile
        y_scroll = scroll_y % tile.size
        
        x_start, x_end = tile.x_range
        y_start, y_end = tile.y_range
        
        for i in range(x_start, x_end):
            for j in range(y_start, y_end):
                x0 = i * tile.size + offset[0]
                x1 = (i + 1) * tile.size + offset[0]
                y0 = (j - y_scroll) * tile.size + offset[1]
                y1 = (j + 1 - y_scroll) * tile.size + offset[1]
                z = layer.z_depth
                
                self.quads.append({
                    'texture': tex_info.full_path,
                    'v0': (x0, y0, z),
                    'v1': (x0, y1, z),
                    'v2': (x1, y1, z),
                    'v3': (x1, y0, z),
                    'alpha': layer.alpha,
                    'blend_mode': layer.blend_mode
                })
    
    def get_render_quads(self) -> List[Dict]:
        """获取渲染四边形列表"""
        return self.quads
    
    # ========== 实时编辑接口 ==========
    
    def set_camera_param(self, param: str, value: Any):
        """设置摄像机参数"""
        if not self.data:
            return
        setattr(self.data.camera, param, value)
    
    def set_fog_param(self, param: str, value: Any):
        """设置雾效参数"""
        if not self.data:
            return
        setattr(self.data.fog, param, value)
    
    def set_scroll_param(self, param: str, value: Any):
        """设置滚动参数"""
        if not self.data:
            return
        setattr(self.data.scroll, param, value)
    
    def set_layer_param(self, layer_name: str, param: str, value: Any):
        """设置图层参数"""
        if not self.data:
            return
        for layer in self.data.layers:
            if layer.name == layer_name:
                if param == "blend_mode":
                    value = BlendMode(value)
                setattr(layer, param, value)
                break
    
    def save_config(self, json_path: str = None) -> bool:
        """保存配置到 JSON 文件"""
        if not self.data:
            return False
        
        path = json_path or self.config_path
        if not path:
            return False
        
        try:
            config = self._to_dict()
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"[Background] 已保存配置: {path}")
            return True
        except Exception as e:
            print(f"[Background] 保存失败: {e}")
            return False
    
    def _to_dict(self) -> dict:
        """转换为字典"""
        if not self.data:
            return {}
        
        return {
            "name": self.data.name,
            "description": self.data.description,
            "textures": {
                name: {
                    "path": tex.path,
                    "description": tex.description
                }
                for name, tex in self.data.textures.items()
            },
            "camera": {
                "eye": list(self.data.camera.eye),
                "at": list(self.data.camera.at),
                "up": list(self.data.camera.up),
                "fovy": self.data.camera.fovy,
                "z_near": self.data.camera.z_near,
                "z_far": self.data.camera.z_far
            },
            "fog": {
                "enabled": self.data.fog.enabled,
                "color": list(self.data.fog.color),
                "start": self.data.fog.start,
                "end": self.data.fog.end
            },
            "scroll": {
                "base_speed": self.data.scroll.base_speed,
                "direction": list(self.data.scroll.direction)
            },
            "layers": [
                {
                    "name": layer.name,
                    "texture": layer.texture,
                    "z_order": layer.z_order,
                    "z_depth": layer.z_depth,
                    "blend_mode": layer.blend_mode.value,
                    "alpha": layer.alpha,
                    "scroll_multiplier": layer.scroll_multiplier,
                    "tile": {
                        "x_range": list(layer.tile.x_range),
                        "y_range": list(layer.tile.y_range),
                        "size": layer.tile.size
                    },
                    "variants": [
                        {
                            "offset": list(var.offset),
                            "scroll_multiplier": var.scroll_multiplier
                        }
                        for var in layer.variants
                    ],
                    "enabled": layer.enabled
                }
                for layer in self.data.layers
            ]
        }
    
    def reload(self) -> bool:
        """重新加载配置"""
        if self.config_path:
            return self.load_from_json(self.config_path)
        return False


def list_available_backgrounds() -> List[str]:
    """列出所有可用的背景配置"""
    bg_dir = DataDrivenBackground.ASSET_BASE
    if not os.path.exists(bg_dir):
        return []
    
    backgrounds = []
    for f in os.listdir(bg_dir):
        if f.endswith('.json'):
            backgrounds.append(f[:-5])  # 移除 .json 后缀
    return backgrounds

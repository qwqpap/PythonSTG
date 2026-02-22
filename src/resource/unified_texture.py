"""
统一纹理资产系统 (Unified Texture Asset System)

提供所有类型资产（子弹、激光、敌人、道具、玩家、背景、UI）的统一抽象。

核心概念:
- TextureRegion: 纹理区域（最基本的单元）
- SpriteAsset: 静态精灵（单个区域）
- AnimationAsset: 动画精灵（多帧）
- CompositeAsset: 复合资产（激光的head/body/tail，玩家的本体+僚机+子弹）
- AssetGroup: 资产组（同一纹理上的多个相关资产，如16色子弹）

使用方式:
    manager = UnifiedTextureManager("assets")
    manager.load_config("images/bullet/bullet1.json")
    
    # 获取精灵UV（所有类型统一接口）
    uv = manager.get_uv("ball_red")
    
    # 获取激光部件
    laser = manager.get_composite("laser_red")
    head_uv = laser.get_part_uv("head")
    
    # 获取动画
    anim = manager.get_animation("sakuya_idle")
    frame_uv = anim.get_frame_uv(frame_index)
"""

from __future__ import annotations
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, TYPE_CHECKING
from ..core.image_loader import load_image_surface, SoftwareSurface
import numpy as np

if TYPE_CHECKING:
    import moderngl


class AssetType(Enum):
    """资产类型"""
    SPRITE = auto()      # 静态精灵
    ANIMATION = auto()   # 动画
    LASER = auto()       # 激光（三段式）
    BENT_LASER = auto()  # 曲线激光
    PLAYER = auto()      # 玩家（含僚机、子弹）
    ENEMY = auto()       # 敌人
    BOSS = auto()        # Boss
    ITEM = auto()        # 道具
    BACKGROUND = auto()  # 背景
    UI = auto()          # UI元素


@dataclass
class TextureRegion:
    """
    纹理区域 - 最基本的纹理单元
    
    定义纹理图集中的一个矩形区域及其属性
    """
    x: int
    y: int
    width: int
    height: int
    center_x: float = None  # None表示使用默认中心
    center_y: float = None
    
    def __post_init__(self):
        if self.center_x is None:
            self.center_x = self.width / 2
        if self.center_y is None:
            self.center_y = self.height / 2
    
    @property
    def rect(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)
    
    @property
    def center(self) -> Tuple[float, float]:
        return (self.center_x, self.center_y)
    
    def get_uv(self, tex_width: int, tex_height: int, flip_y: bool = False) -> Tuple[float, float, float, float]:
        """
        获取归一化UV坐标
        
        Returns:
            (u0, v0, u1, v1) - 左上角和右下角的UV坐标
        """
        u0 = self.x / tex_width
        u1 = (self.x + self.width) / tex_width
        
        if flip_y:
            v0 = 1.0 - self.y / tex_height
            v1 = 1.0 - (self.y + self.height) / tex_height
        else:
            v0 = self.y / tex_height
            v1 = (self.y + self.height) / tex_height
        
        return (u0, v0, u1, v1)
    
    def get_uv_offset_scale(self, tex_width: int, tex_height: int, flip_y: bool = False) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        获取UV偏移和缩放（用于实例化渲染）
        
        Returns:
            ((u_offset, v_offset), (u_scale, v_scale))
        """
        u_offset = self.x / tex_width
        u_scale = self.width / tex_width
        
        if flip_y:
            v_offset = 1.0 - (self.y + self.height) / tex_height
        else:
            v_offset = self.y / tex_height
        v_scale = self.height / tex_height
        
        return ((u_offset, v_offset), (u_scale, v_scale))
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TextureRegion':
        """从字典创建"""
        if 'rect' in data:
            rect = data['rect']
            x, y, w, h = rect[0], rect[1], rect[2], rect[3]
        else:
            x = data.get('x', 0)
            y = data.get('y', 0)
            w = data.get('width', data.get('w', 32))
            h = data.get('height', data.get('h', 32))
        
        center = data.get('center', None)
        cx, cy = None, None
        if center:
            cx, cy = center[0], center[1]
        
        return cls(x, y, w, h, cx, cy)


@dataclass
class BaseAsset(ABC):
    """资产基类"""
    name: str
    asset_type: AssetType
    texture_path: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 可选属性
    radius: float = 0.0  # 碰撞半径
    rotate: bool = False  # 是否跟随方向旋转
    scale: float = 1.0    # 缩放
    
    @abstractmethod
    def get_primary_region(self) -> TextureRegion:
        """获取主要纹理区域"""
        pass
    
    @abstractmethod
    def get_uv(self, tex_width: int, tex_height: int, **kwargs) -> Tuple[float, float, float, float]:
        """获取UV坐标"""
        pass


@dataclass
class SpriteAsset(BaseAsset):
    """静态精灵资产"""
    region: TextureRegion = None
    
    def __post_init__(self):
        if self.asset_type is None:
            self.asset_type = AssetType.SPRITE
    
    def get_primary_region(self) -> TextureRegion:
        return self.region
    
    def get_uv(self, tex_width: int, tex_height: int, flip_y: bool = False) -> Tuple[float, float, float, float]:
        return self.region.get_uv(tex_width, tex_height, flip_y)
    
    def get_uv_offset_scale(self, tex_width: int, tex_height: int, flip_y: bool = False) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        return self.region.get_uv_offset_scale(tex_width, tex_height, flip_y)


@dataclass
class AnimationAsset(BaseAsset):
    """动画资产"""
    frames: List[TextureRegion] = field(default_factory=list)
    frame_duration: int = 5  # 每帧持续的游戏帧数
    loop: bool = True
    
    def __post_init__(self):
        if self.asset_type is None:
            self.asset_type = AssetType.ANIMATION
    
    @property
    def frame_count(self) -> int:
        return len(self.frames)
    
    @property
    def total_frames(self) -> int:
        """动画总帧数（游戏帧）"""
        return self.frame_count * self.frame_duration
    
    def get_frame_index(self, game_frame: int) -> int:
        """根据游戏帧获取动画帧索引"""
        if self.frame_count == 0:
            return 0
        
        if self.loop:
            return (game_frame // self.frame_duration) % self.frame_count
        else:
            return min(game_frame // self.frame_duration, self.frame_count - 1)
    
    def get_frame_region(self, game_frame: int) -> TextureRegion:
        """获取当前帧的纹理区域"""
        idx = self.get_frame_index(game_frame)
        return self.frames[idx] if self.frames else None
    
    def get_primary_region(self) -> TextureRegion:
        return self.frames[0] if self.frames else None
    
    def get_uv(self, tex_width: int, tex_height: int, game_frame: int = 0, flip_y: bool = False) -> Tuple[float, float, float, float]:
        region = self.get_frame_region(game_frame)
        if region:
            return region.get_uv(tex_width, tex_height, flip_y)
        return (0, 0, 1, 1)
    
    def get_frame_uv(self, frame_index: int, tex_width: int, tex_height: int, flip_y: bool = False) -> Tuple[float, float, float, float]:
        """直接按帧索引获取UV"""
        if 0 <= frame_index < len(self.frames):
            return self.frames[frame_index].get_uv(tex_width, tex_height, flip_y)
        return (0, 0, 1, 1)


@dataclass
class LaserAsset(BaseAsset):
    """
    激光资产（三段式：head/body/tail）
    """
    head: TextureRegion = None
    body: TextureRegion = None
    tail: TextureRegion = None
    
    def __post_init__(self):
        self.asset_type = AssetType.LASER
    
    def get_primary_region(self) -> TextureRegion:
        return self.body
    
    def get_uv(self, tex_width: int, tex_height: int, part: str = 'body', flip_y: bool = False) -> Tuple[float, float, float, float]:
        region = getattr(self, part, self.body)
        if region:
            return region.get_uv(tex_width, tex_height, flip_y)
        return (0, 0, 1, 1)
    
    def get_part_uv(self, part: str, tex_width: int, tex_height: int, flip_y: bool = False) -> Tuple[float, float, float, float]:
        """获取指定部件的UV"""
        return self.get_uv(tex_width, tex_height, part, flip_y)
    
    def get_all_uvs(self, tex_width: int, tex_height: int, flip_y: bool = False) -> Dict[str, Tuple[float, float, float, float]]:
        """获取所有部件的UV"""
        return {
            'head': self.head.get_uv(tex_width, tex_height, flip_y) if self.head else None,
            'body': self.body.get_uv(tex_width, tex_height, flip_y) if self.body else None,
            'tail': self.tail.get_uv(tex_width, tex_height, flip_y) if self.tail else None,
        }


@dataclass
class BentLaserAsset(BaseAsset):
    """曲线激光资产（单段重复）"""
    segment: TextureRegion = None
    
    def __post_init__(self):
        self.asset_type = AssetType.BENT_LASER
    
    def get_primary_region(self) -> TextureRegion:
        return self.segment
    
    def get_uv(self, tex_width: int, tex_height: int, flip_y: bool = False) -> Tuple[float, float, float, float]:
        if self.segment:
            return self.segment.get_uv(tex_width, tex_height, flip_y)
        return (0, 0, 1, 1)


@dataclass
class ColorVariantGroup:
    """
    颜色变体组
    管理一组具有相同形状但不同颜色的资产（如16色子弹/激光）
    """
    name: str
    base_asset_type: AssetType
    variants: Dict[str, Union[SpriteAsset, LaserAsset, BentLaserAsset]] = field(default_factory=dict)
    color_order: List[str] = field(default_factory=list)  # 颜色顺序
    
    # 标准16色顺序
    STANDARD_COLORS = [
        'red', 'orange', 'yellow', 'green', 'cyan', 'blue', 'purple', 'pink',
        'darkred', 'brown', 'lime', 'aqua', 'navy', 'violet', 'gray', 'white'
    ]
    
    def get_variant(self, color: Union[str, int]) -> Optional[BaseAsset]:
        """
        获取指定颜色的变体
        
        Args:
            color: 颜色名称或索引
        """
        if isinstance(color, int):
            if 0 <= color < len(self.color_order):
                color = self.color_order[color]
            else:
                return None
        return self.variants.get(color)
    
    def get_uv_by_color(self, color: Union[str, int], tex_width: int, tex_height: int, **kwargs) -> Optional[Tuple[float, float, float, float]]:
        """获取指定颜色的UV"""
        asset = self.get_variant(color)
        if asset:
            return asset.get_uv(tex_width, tex_height, **kwargs)
        return None


@dataclass
class PlayerAsset(BaseAsset):
    """
    玩家资产
    包含本体动画、僚机动画、子弹精灵等
    """
    # 本体动画
    animations: Dict[str, AnimationAsset] = field(default_factory=dict)
    
    # 僚机
    option_animation: Optional[AnimationAsset] = None
    
    # 子弹精灵
    bullets: Dict[str, SpriteAsset] = field(default_factory=dict)
    
    # 属性
    stats: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        self.asset_type = AssetType.PLAYER
    
    def get_primary_region(self) -> TextureRegion:
        idle = self.animations.get('idle')
        if idle and idle.frames:
            return idle.frames[0]
        return None
    
    def get_uv(self, tex_width: int, tex_height: int, animation: str = 'idle', game_frame: int = 0, flip_y: bool = False) -> Tuple[float, float, float, float]:
        anim = self.animations.get(animation)
        if anim:
            return anim.get_uv(tex_width, tex_height, game_frame, flip_y)
        return (0, 0, 1, 1)
    
    def get_bullet_uv(self, bullet_name: str, tex_width: int, tex_height: int, flip_y: bool = False) -> Optional[Tuple[float, float, float, float]]:
        bullet = self.bullets.get(bullet_name)
        if bullet:
            return bullet.get_uv(tex_width, tex_height, flip_y)
        return None
    
    def get_option_uv(self, game_frame: int, tex_width: int, tex_height: int, flip_y: bool = False) -> Optional[Tuple[float, float, float, float]]:
        if self.option_animation:
            return self.option_animation.get_uv(tex_width, tex_height, game_frame, flip_y)
        return None


@dataclass
class TextureSheet:
    """
    纹理表
    管理单个纹理文件及其上的所有资产
    """
    path: str
    width: int = 0
    height: int = 0
    
    # 资产索引
    sprites: Dict[str, SpriteAsset] = field(default_factory=dict)
    animations: Dict[str, AnimationAsset] = field(default_factory=dict)
    lasers: Dict[str, LaserAsset] = field(default_factory=dict)
    bent_lasers: Dict[str, BentLaserAsset] = field(default_factory=dict)
    color_groups: Dict[str, ColorVariantGroup] = field(default_factory=dict)
    
    _surface: Optional[SoftwareSurface] = field(default=None, repr=False)
    
    def load(self, base_path: str = "") -> bool:
        """加载纹理"""
        full_path = os.path.join(base_path, self.path) if base_path else self.path
        
        if not os.path.exists(full_path):
            print(f"纹理文件不存在: {full_path}")
            return False
        
        try:
            self._surface = load_image_surface(full_path)
            self.width, self.height = self._surface.get_size()
            return True
        except Exception as e:
            print(f"加载纹理失败 {full_path}: {e}")
            return False
    
    @property
    def surface(self) -> Optional[SoftwareSurface]:
        return self._surface
    
    def get_uv(self, asset_name: str, **kwargs) -> Optional[Tuple[float, float, float, float]]:
        """统一的UV获取接口"""
        # 按优先级查找
        if asset_name in self.sprites:
            return self.sprites[asset_name].get_uv(self.width, self.height, **kwargs)
        if asset_name in self.animations:
            return self.animations[asset_name].get_uv(self.width, self.height, **kwargs)
        if asset_name in self.lasers:
            return self.lasers[asset_name].get_uv(self.width, self.height, **kwargs)
        if asset_name in self.bent_lasers:
            return self.bent_lasers[asset_name].get_uv(self.width, self.height, **kwargs)
        
        # 检查颜色组
        for group in self.color_groups.values():
            if asset_name in group.variants:
                return group.variants[asset_name].get_uv(self.width, self.height, **kwargs)
        
        return None


class UnifiedTextureManager:
    """
    统一纹理资产管理器
    
    提供所有类型资产的统一加载和访问接口
    """
    
    def __init__(self, asset_root: str = "assets"):
        self.asset_root = Path(asset_root)
        
        # 纹理表缓存
        self.sheets: Dict[str, TextureSheet] = {}
        
        # 全局资产索引（按名称快速查找）
        self.all_sprites: Dict[str, SpriteAsset] = {}
        self.all_animations: Dict[str, AnimationAsset] = {}
        self.all_lasers: Dict[str, LaserAsset] = {}
        self.all_bent_lasers: Dict[str, BentLaserAsset] = {}
        self.all_color_groups: Dict[str, ColorVariantGroup] = {}
        self.all_players: Dict[str, PlayerAsset] = {}
        
        # 资产名称到纹理表的映射
        self._asset_to_sheet: Dict[str, str] = {}
        
        # UV缓存（预计算）
        self._uv_cache: Dict[str, Tuple[float, float, float, float]] = {}
        self._uv_offset_scale_cache: Dict[str, Tuple[Tuple[float, float], Tuple[float, float]]] = {}

    def _resolve_texture_path(self, config_dir: Path, texture_file: Optional[str]) -> str:
        """解析纹理路径，兼容 assets/ 前缀与绝对路径"""
        if not texture_file:
            return ""

        tex_path = Path(texture_file)
        if tex_path.is_absolute():
            return str(tex_path)

        normalized = texture_file.replace('\\', '/')
        if normalized.startswith('assets/'):
            relative = normalized[len('assets/'):]
            return str(self.asset_root / relative)

        return str(config_dir / texture_file)
    
    def load_config(self, config_path: str, sheet_name: Optional[str] = None) -> Optional[TextureSheet]:
        """
        加载配置文件
        
        自动识别配置类型（子弹/激光/玩家等）并正确解析
        
        Args:
            config_path: 配置文件路径（相对于asset_root）
            sheet_name: 纹理表名称（默认使用文件名）
        """
        full_path = self.asset_root / config_path
        if not full_path.exists():
            print(f"配置文件不存在: {full_path}")
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"读取配置失败 {config_path}: {e}")
            return None
        
        if sheet_name is None:
            sheet_name = full_path.stem
        
        # 检测配置类型
        config_type = self._detect_config_type(config, config_path)
        
        # 根据类型调用对应的解析器
        if config_type == 'laser':
            return self._parse_laser_config(config, full_path.parent, sheet_name)
        elif config_type == 'player':
            return self._parse_player_config(config, full_path.parent, sheet_name)
        elif config_type == 'bullet':
            return self._parse_bullet_config(config, full_path.parent, sheet_name)
        elif config_type == 'item':
            return self._parse_item_config(config, full_path.parent, sheet_name)
        elif config_type == 'background':
            return self._parse_background_config(config, full_path.parent, sheet_name)
        else:
            # 通用精灵配置
            return self._parse_generic_config(config, full_path.parent, sheet_name)
    
    def _detect_config_type(self, config: dict, path: str) -> str:
        """检测配置类型"""
        path_lower = path.lower()
        
        # 根据配置内容判断
        if 'laser_textures' in config or 'bent_laser' in config:
            return 'laser'
        if 'stats' in config and ('animations' in config or 'sprites' in config):
            if 'speed_high' in config.get('stats', {}) or 'hitbox_radius' in config.get('stats', {}):
                return 'player'
        
        # 根据路径判断
        if 'laser' in path_lower:
            return 'laser'
        if 'player' in path_lower:
            return 'player'
        if 'bullet' in path_lower:
            return 'bullet'
        if 'item' in path_lower:
            return 'item'
        if 'background' in path_lower:
            return 'background'
        
        return 'generic'
    
    def _parse_bullet_config(self, config: dict, config_dir: Path, sheet_name: str) -> TextureSheet:
        """解析子弹配置"""
        # 确定纹理路径
        texture_file = config.get('texture') or config.get('__image_filename', f'{sheet_name}.png')
        texture_path = self._resolve_texture_path(config_dir, texture_file)
        
        sheet = TextureSheet(path=texture_path)
        sheet.load()
        
        # 解析精灵
        sprites_data = config.get('sprites', {})
        
        # 检测是否有颜色变体（根据命名模式）
        color_groups: Dict[str, Dict[str, SpriteAsset]] = {}
        
        for name, data in sprites_data.items():
            if name.startswith('__'):
                continue
            if not isinstance(data, dict):
                continue
            
            region = TextureRegion.from_dict(data)
            sprite = SpriteAsset(
                name=name,
                asset_type=AssetType.SPRITE,
                texture_path=texture_path,
                region=region,
                radius=data.get('radius', 0.0),
                rotate=data.get('rotate', data.get('is_rotating', False)),
                scale=data.get('scale', 1.0)
            )
            
            sheet.sprites[name] = sprite
            self.all_sprites[name] = sprite
            self._asset_to_sheet[name] = sheet_name
            
            # 检测颜色分组
            for color in ColorVariantGroup.STANDARD_COLORS:
                if f'_{color}' in name or name.endswith(color):
                    base_name = name.replace(f'_{color}', '').replace(color, '').rstrip('_')
                    if base_name not in color_groups:
                        color_groups[base_name] = {}
                    color_groups[base_name][color] = sprite
                    break
        
        # 创建颜色组
        for base_name, variants in color_groups.items():
            if len(variants) > 1:
                group = ColorVariantGroup(
                    name=base_name,
                    base_asset_type=AssetType.SPRITE,
                    variants=variants,
                    color_order=[c for c in ColorVariantGroup.STANDARD_COLORS if c in variants]
                )
                sheet.color_groups[base_name] = group
                self.all_color_groups[base_name] = group
        
        # 解析动画
        animations_data = config.get('animations', {})
        for name, data in animations_data.items():
            anim = self._parse_animation(name, data, texture_path, sheet.sprites)
            if anim:
                sheet.animations[name] = anim
                self.all_animations[name] = anim
                self._asset_to_sheet[name] = sheet_name
        
        self.sheets[sheet_name] = sheet
        print(f"已加载子弹配置 '{sheet_name}': {len(sheet.sprites)} 精灵, {len(sheet.color_groups)} 颜色组")
        return sheet
    
    def _parse_laser_config(self, config: dict, config_dir: Path, sheet_name: str) -> Optional[TextureSheet]:
        """解析激光配置"""
        laser_textures = config.get('laser_textures', {})
        bent_laser = config.get('bent_laser', {})
        
        for laser_name, laser_data in laser_textures.items():
            texture_file = laser_data.get('file', f'{laser_name}.png')
            texture_path = self._resolve_texture_path(config_dir, texture_file)
            
            sheet = TextureSheet(path=texture_path)
            sheet.load()
            
            # 解析三段式激光
            head_w = laser_data.get('head_width', 64)
            body_w = laser_data.get('body_width', 128)
            tail_w = laser_data.get('tail_width', 64)
            row_h = laser_data.get('row_height', 16)
            num_colors = laser_data.get('colors', 16)
            
            # 为每种颜色创建激光资产
            color_variants = {}
            for i, color in enumerate(ColorVariantGroup.STANDARD_COLORS[:num_colors]):
                y = i * row_h
                
                head = TextureRegion(0, y, head_w, row_h)
                body = TextureRegion(head_w, y, body_w, row_h)
                tail = TextureRegion(head_w + body_w, y, tail_w, row_h)
                
                laser_asset = LaserAsset(
                    name=f'{laser_name}_{color}',
                    asset_type=AssetType.LASER,
                    texture_path=texture_path,
                    head=head,
                    body=body,
                    tail=tail
                )
                
                full_name = f'{laser_name}_{color}'
                sheet.lasers[full_name] = laser_asset
                self.all_lasers[full_name] = laser_asset
                self._asset_to_sheet[full_name] = laser_name
                color_variants[color] = laser_asset
            
            # 创建颜色组
            group = ColorVariantGroup(
                name=laser_name,
                base_asset_type=AssetType.LASER,
                variants=color_variants,
                color_order=ColorVariantGroup.STANDARD_COLORS[:num_colors]
            )
            sheet.color_groups[laser_name] = group
            self.all_color_groups[laser_name] = group
            
            self.sheets[laser_name] = sheet
            print(f"已加载激光配置 '{laser_name}': {num_colors} 种颜色")
        
        # 解析曲线激光
        if bent_laser:
            texture_file = bent_laser.get('file', 'laser_bent.png')
            texture_path = self._resolve_texture_path(config_dir, texture_file)
            
            sheet = TextureSheet(path=texture_path)
            sheet.load()
            
            seg_w = bent_laser.get('segment_width', 16)
            row_h = bent_laser.get('row_height', 16)
            num_colors = bent_laser.get('colors', 16)
            
            color_variants = {}
            for i, color in enumerate(ColorVariantGroup.STANDARD_COLORS[:num_colors]):
                segment = TextureRegion(0, i * row_h, seg_w, row_h)
                
                bent = BentLaserAsset(
                    name=f'bent_{color}',
                    asset_type=AssetType.BENT_LASER,
                    texture_path=texture_path,
                    segment=segment
                )
                
                sheet.bent_lasers[f'bent_{color}'] = bent
                self.all_bent_lasers[f'bent_{color}'] = bent
                color_variants[color] = bent
            
            group = ColorVariantGroup(
                name='bent_laser',
                base_asset_type=AssetType.BENT_LASER,
                variants=color_variants,
                color_order=ColorVariantGroup.STANDARD_COLORS[:num_colors]
            )
            sheet.color_groups['bent_laser'] = group
            self.all_color_groups['bent_laser'] = group
            
            self.sheets['bent_laser'] = sheet
            print(f"已加载曲线激光配置: {num_colors} 种颜色")
        
        return self.sheets.get(sheet_name)
    
    def _parse_player_config(self, config: dict, config_dir: Path, sheet_name: str) -> TextureSheet:
        """解析玩家配置"""
        texture_file = config.get('texture', f'{sheet_name}.png')
        texture_path = self._resolve_texture_path(config_dir, texture_file)
        
        sheet = TextureSheet(path=texture_path)
        sheet.load()
        
        # 解析精灵
        sprites_data = config.get('sprites', {})
        sprite_map: Dict[str, SpriteAsset] = {}
        
        for name, data in sprites_data.items():
            region = TextureRegion.from_dict(data)
            sprite = SpriteAsset(
                name=name,
                asset_type=AssetType.SPRITE,
                texture_path=texture_path,
                region=region
            )
            sprite_map[name] = sprite
            sheet.sprites[name] = sprite
            self.all_sprites[name] = sprite
        
        # 解析动画
        animations_data = config.get('animations', {})
        anim_map: Dict[str, AnimationAsset] = {}
        
        for name, data in animations_data.items():
            anim = self._parse_animation(name, data, texture_path, sprite_map)
            if anim:
                anim_map[name] = anim
                sheet.animations[name] = anim
                self.all_animations[name] = anim
        
        # 识别子弹精灵
        bullet_sprites = {}
        for name, sprite in sprite_map.items():
            if 'knife' in name.lower() or 'bullet' in name.lower() or 'shot' in name.lower():
                bullet_sprites[name] = sprite
        
        # 创建玩家资产
        player = PlayerAsset(
            name=sheet_name,
            asset_type=AssetType.PLAYER,
            texture_path=texture_path,
            animations=anim_map,
            option_animation=anim_map.get('option'),
            bullets=bullet_sprites,
            stats=config.get('stats', {}),
            metadata=config.get('initial', {})
        )
        
        self.all_players[sheet_name] = player
        self.sheets[sheet_name] = sheet
        print(f"已加载玩家配置 '{sheet_name}': {len(anim_map)} 动画, {len(bullet_sprites)} 子弹")
        return sheet
    
    def _parse_item_config(self, config: dict, config_dir: Path, sheet_name: str) -> TextureSheet:
        """解析道具配置"""
        texture_file = config.get('texture') or config.get('__image_filename', f'{sheet_name}.png')
        texture_path = self._resolve_texture_path(config_dir, texture_file)
        
        sheet = TextureSheet(path=texture_path)
        sheet.load()
        
        sprites_data = config.get('sprites', {})
        for name, data in sprites_data.items():
            if name.startswith('__') or not isinstance(data, dict):
                continue
            
            region = TextureRegion.from_dict(data)
            sprite = SpriteAsset(
                name=name,
                asset_type=AssetType.ITEM,
                texture_path=texture_path,
                region=region,
                metadata={'collect_radius': data.get('collect_radius', 16)}
            )
            
            sheet.sprites[name] = sprite
            self.all_sprites[name] = sprite
            self._asset_to_sheet[name] = sheet_name
        
        self.sheets[sheet_name] = sheet
        print(f"已加载道具配置 '{sheet_name}': {len(sheet.sprites)} 精灵")
        return sheet
    
    def _parse_background_config(self, config: dict, config_dir: Path, sheet_name: str) -> TextureSheet:
        """解析背景配置"""
        # 背景配置比较特殊，通常是多层结构
        layers = config.get('layers', [])
        
        sheet = TextureSheet(path=self._resolve_texture_path(config_dir, f'{sheet_name}.png'))
        sheet.load()
        
        # 每层作为一个精灵
        for i, layer in enumerate(layers):
            texture_file = layer.get('texture', '')
            if texture_file:
                sprite = SpriteAsset(
                    name=f'{sheet_name}_layer_{i}',
                    asset_type=AssetType.BACKGROUND,
                    texture_path=self._resolve_texture_path(config_dir, texture_file),
                    region=TextureRegion(0, 0, sheet.width, sheet.height),
                    metadata=layer
                )
                sheet.sprites[sprite.name] = sprite
                self.all_sprites[sprite.name] = sprite
        
        self.sheets[sheet_name] = sheet
        return sheet
    
    def _parse_generic_config(self, config: dict, config_dir: Path, sheet_name: str) -> TextureSheet:
        """解析通用配置"""
        texture_file = config.get('texture') or config.get('__image_filename', f'{sheet_name}.png')
        texture_path = self._resolve_texture_path(config_dir, texture_file)
        
        sheet = TextureSheet(path=texture_path)
        sheet.load()
        
        # 解析精灵
        sprites_data = config.get('sprites', {})
        sprite_map = {}
        
        for name, data in sprites_data.items():
            if name.startswith('__') or not isinstance(data, dict):
                continue
            
            region = TextureRegion.from_dict(data)
            sprite = SpriteAsset(
                name=name,
                asset_type=AssetType.SPRITE,
                texture_path=texture_path,
                region=region,
                radius=data.get('radius', 0.0),
                rotate=data.get('rotate', False)
            )
            
            sprite_map[name] = sprite
            sheet.sprites[name] = sprite
            self.all_sprites[name] = sprite
            self._asset_to_sheet[name] = sheet_name
        
        # 解析动画
        animations_data = config.get('animations', {})
        for name, data in animations_data.items():
            anim = self._parse_animation(name, data, texture_path, sprite_map)
            if anim:
                sheet.animations[name] = anim
                self.all_animations[name] = anim
                self._asset_to_sheet[name] = sheet_name
        
        self.sheets[sheet_name] = sheet
        print(f"已加载配置 '{sheet_name}': {len(sheet.sprites)} 精灵, {len(sheet.animations)} 动画")
        return sheet
    
    def _parse_animation(self, name: str, data: dict, texture_path: str, sprite_map: Dict[str, SpriteAsset]) -> Optional[AnimationAsset]:
        """解析动画"""
        frames = []
        
        if 'frames' in data:
            frame_refs = data['frames']
            
            # 检查是精灵名称列表还是区域列表
            if frame_refs and isinstance(frame_refs[0], str):
                # 精灵名称引用
                for sprite_name in frame_refs:
                    sprite = sprite_map.get(sprite_name)
                    if sprite:
                        frames.append(sprite.region)
            elif frame_refs and isinstance(frame_refs[0], dict):
                # 直接区域定义
                for frame_data in frame_refs:
                    frames.append(TextureRegion.from_dict(frame_data))
        
        elif 'strip' in data:
            # 条带模式
            strip = data['strip']
            x = strip.get('x', 0)
            y = strip.get('y', 0)
            w = strip.get('width', 32)
            h = strip.get('height', 32)
            count = strip.get('count', 1)
            direction = strip.get('direction', 'horizontal')
            spacing = strip.get('spacing', 0)
            
            for i in range(count):
                if direction == 'horizontal':
                    fx = x + i * (w + spacing)
                    fy = y
                else:
                    fx = x
                    fy = y + i * (h + spacing)
                frames.append(TextureRegion(fx, fy, w, h))
        
        if not frames:
            return None
        
        return AnimationAsset(
            name=name,
            asset_type=AssetType.ANIMATION,
            texture_path=texture_path,
            frames=frames,
            frame_duration=data.get('frame_duration', 5),
            loop=data.get('loop', True)
        )
    
    # ==================== 统一访问接口 ====================
    
    def get_sprite(self, name: str) -> Optional[SpriteAsset]:
        """获取精灵"""
        return self.all_sprites.get(name)
    
    def get_animation(self, name: str) -> Optional[AnimationAsset]:
        """获取动画"""
        return self.all_animations.get(name)
    
    def get_laser(self, name: str) -> Optional[LaserAsset]:
        """获取激光"""
        return self.all_lasers.get(name)
    
    def get_bent_laser(self, name: str) -> Optional[BentLaserAsset]:
        """获取曲线激光"""
        return self.all_bent_lasers.get(name)
    
    def get_color_group(self, name: str) -> Optional[ColorVariantGroup]:
        """获取颜色组"""
        return self.all_color_groups.get(name)
    
    def get_player(self, name: str) -> Optional[PlayerAsset]:
        """获取玩家资产"""
        return self.all_players.get(name)
    
    def get_sheet(self, name: str) -> Optional[TextureSheet]:
        """获取纹理表"""
        return self.sheets.get(name)
    
    def get_uv(self, asset_name: str, **kwargs) -> Optional[Tuple[float, float, float, float]]:
        """
        统一的UV获取接口
        
        Args:
            asset_name: 资产名称
            **kwargs: 额外参数（如 game_frame, part 等）
        """
        # 检查缓存（仅对无额外参数的调用）
        if not kwargs and asset_name in self._uv_cache:
            return self._uv_cache[asset_name]
        
        # 查找资产
        sheet_name = self._asset_to_sheet.get(asset_name)
        if sheet_name:
            sheet = self.sheets.get(sheet_name)
            if sheet:
                uv = sheet.get_uv(asset_name, **kwargs)
                if not kwargs and uv:
                    self._uv_cache[asset_name] = uv
                return uv
        
        # 全局搜索
        for sheet in self.sheets.values():
            uv = sheet.get_uv(asset_name, **kwargs)
            if uv:
                return uv
        
        return None
    
    def get_uv_offset_scale(self, asset_name: str, flip_y: bool = False) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """
        获取UV偏移和缩放（用于实例化渲染）
        """
        cache_key = f"{asset_name}_{flip_y}"
        if cache_key in self._uv_offset_scale_cache:
            return self._uv_offset_scale_cache[cache_key]
        
        sprite = self.all_sprites.get(asset_name)
        if sprite:
            sheet_name = self._asset_to_sheet.get(asset_name)
            sheet = self.sheets.get(sheet_name)
            if sheet:
                result = sprite.get_uv_offset_scale(sheet.width, sheet.height, flip_y)
                self._uv_offset_scale_cache[cache_key] = result
                return result
        
        return None
    
    def get_texture_surface(self, asset_name: str) -> Optional[SoftwareSurface]:
        """获取资产所属的纹理Surface"""
        sheet_name = self._asset_to_sheet.get(asset_name)
        if sheet_name:
            sheet = self.sheets.get(sheet_name)
            if sheet:
                return sheet.surface
        return None
    
    def build_sprite_uv_array(self, sprite_names: List[str], flip_y: bool = False) -> np.ndarray:
        """
        为一组精灵构建UV数组（用于批量渲染）
        
        Returns:
            numpy数组，shape=(n, 4)，每行是(u0, v0, u1, v1)
        """
        uvs = []
        for name in sprite_names:
            uv = self.get_uv(name, flip_y=flip_y)
            if uv:
                uvs.append(uv)
            else:
                uvs.append((0, 0, 1, 1))
        return np.array(uvs, dtype=np.float32)
    
    def build_sprite_uv_offset_scale_arrays(self, sprite_names: List[str], flip_y: bool = False) -> Tuple[np.ndarray, np.ndarray]:
        """
        为一组精灵构建UV偏移和缩放数组
        
        Returns:
            (offsets, scales) - 每个都是numpy数组，shape=(n, 2)
        """
        offsets = []
        scales = []
        for name in sprite_names:
            result = self.get_uv_offset_scale(name, flip_y)
            if result:
                offsets.append(result[0])
                scales.append(result[1])
            else:
                offsets.append((0, 0))
                scales.append((1, 1))
        return np.array(offsets, dtype=np.float32), np.array(scales, dtype=np.float32)


# 全局实例
_manager: Optional[UnifiedTextureManager] = None


def init_unified_texture_manager(asset_root: str = "assets") -> UnifiedTextureManager:
    """初始化全局纹理管理器"""
    global _manager
    _manager = UnifiedTextureManager(asset_root)
    return _manager


def get_unified_texture_manager() -> Optional[UnifiedTextureManager]:
    """获取全局纹理管理器"""
    return _manager

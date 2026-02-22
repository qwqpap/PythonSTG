"""
统一纹理资产管理系统
支持纹理图集、精灵和动画精灵

该模块提供统一的纹理资产管理，包括：
- TextureAtlas: 纹理图集，管理一张纹理及其上的精灵/动画
- Sprite: 静态精灵资产
- AnimatedSprite: 动画精灵资产
- TextureAssetManager: 统一资产管理器

使用方式:
    from src.resource.texture_asset import get_texture_asset_manager, init_texture_asset_manager
    
    # 初始化
    manager = init_texture_asset_manager("assets")
    
    # 加载配置
    manager.load_atlas_config("images/bullet/bullet1.json")
    
    # 获取精灵
    sprite = manager.get_sprite("star_small1")
    uv = manager.get_sprite_uv_for_gl("star_small1")  # 用于OpenGL渲染
"""
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from pathlib import Path
from ..core.image_loader import load_image_surface, SoftwareSurface

# 可选的 ModernGL 支持
try:
    import moderngl
    HAS_MODERNGL = True
except ImportError:
    HAS_MODERNGL = False
    moderngl = None

if TYPE_CHECKING:
    import moderngl


@dataclass
class SpriteFrame:
    """精灵帧数据"""
    rect: Tuple[int, int, int, int]  # (x, y, width, height)
    center: Tuple[float, float] = (0.0, 0.0)  # 中心点偏移
    
    @property
    def x(self) -> int:
        return self.rect[0]
    
    @property
    def y(self) -> int:
        return self.rect[1]
    
    @property
    def width(self) -> int:
        return self.rect[2]
    
    @property
    def height(self) -> int:
        return self.rect[3]


@dataclass
class Sprite:
    """静态精灵资产"""
    name: str
    texture_path: str  # 所属纹理路径
    rect: Tuple[int, int, int, int]  # (x, y, width, height)
    center: Tuple[float, float] = (0.0, 0.0)  # 中心点
    radius: float = 0.0  # 碰撞半径
    rotate: bool = False  # 是否跟随方向旋转
    scale: Tuple[float, float] = (1.0, 1.0)  # 缩放
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    
    @property
    def x(self) -> int:
        return self.rect[0]
    
    @property
    def y(self) -> int:
        return self.rect[1]
    
    @property
    def width(self) -> int:
        return self.rect[2]
    
    @property
    def height(self) -> int:
        return self.rect[3]
    
    def get_uv(self, texture_size: Tuple[int, int]) -> Tuple[float, float, float, float]:
        """
        获取UV坐标 (归一化到0-1)
        
        Args:
            texture_size: 纹理尺寸 (width, height)
            
        Returns:
            (u_left, v_top, u_right, v_bottom)
        """
        tex_w, tex_h = texture_size
        u_left = self.x / tex_w
        v_top = self.y / tex_h
        u_right = (self.x + self.width) / tex_w
        v_bottom = (self.y + self.height) / tex_h
        return (u_left, v_top, u_right, v_bottom)


@dataclass
class AnimatedSprite:
    """
    动画精灵资产
    支持从图集中连续帧或指定帧列表创建动画
    """
    name: str
    texture_path: str  # 所属纹理路径
    frames: List[SpriteFrame]  # 帧列表
    center: Tuple[float, float] = (0.0, 0.0)  # 动画中心点
    radius: float = 0.0  # 碰撞半径
    rotate: bool = False  # 是否跟随方向旋转
    frame_duration: float = 0.1  # 每帧持续时间（秒）
    loop: bool = True  # 是否循环播放
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def frame_count(self) -> int:
        return len(self.frames)
    
    @property
    def total_duration(self) -> float:
        return self.frame_count * self.frame_duration
    
    def get_frame_at_time(self, time: float) -> SpriteFrame:
        """
        根据时间获取当前帧
        
        Args:
            time: 动画播放时间（秒）
            
        Returns:
            当前帧数据
        """
        if not self.frames:
            raise ValueError(f"Animation '{self.name}' has no frames")
        
        if self.loop:
            frame_index = int(time / self.frame_duration) % self.frame_count
        else:
            frame_index = min(int(time / self.frame_duration), self.frame_count - 1)
        
        return self.frames[frame_index]
    
    def get_frame_index_at_time(self, time: float) -> int:
        """根据时间获取当前帧索引"""
        if not self.frames:
            return 0
        
        if self.loop:
            return int(time / self.frame_duration) % self.frame_count
        else:
            return min(int(time / self.frame_duration), self.frame_count - 1)
    
    def get_frame_uv_at_time(self, time: float, texture_size: Tuple[int, int]) -> Tuple[float, float, float, float]:
        """
        根据时间获取当前帧的UV坐标
        
        Args:
            time: 动画播放时间
            texture_size: 纹理尺寸
            
        Returns:
            (u_left, v_top, u_right, v_bottom)
        """
        frame = self.get_frame_at_time(time)
        tex_w, tex_h = texture_size
        u_left = frame.x / tex_w
        v_top = frame.y / tex_h
        u_right = (frame.x + frame.width) / tex_w
        v_bottom = (frame.y + frame.height) / tex_h
        return (u_left, v_top, u_right, v_bottom)


@dataclass
class TextureAtlas:
    """
    纹理图集
    管理一张纹理图片及其上的所有精灵和动画
    """
    name: str
    texture_path: str
    sprites: Dict[str, Sprite] = field(default_factory=dict)
    animations: Dict[str, AnimatedSprite] = field(default_factory=dict)
    _surface: Optional[SoftwareSurface] = field(default=None, repr=False)
    _texture_size: Optional[Tuple[int, int]] = field(default=None, repr=False)
    
    def load_texture(self, base_path: str = "") -> bool:
        """
        加载纹理图片
        
        Args:
            base_path: 基础路径
            
        Returns:
            是否加载成功
        """
        full_path = os.path.join(base_path, self.texture_path) if base_path else self.texture_path
        full_path = os.path.normpath(full_path)
        
        if not os.path.exists(full_path):
            print(f"纹理文件不存在: {full_path}")
            return False
        
        try:
            self._surface = load_image_surface(full_path)
            self._texture_size = self._surface.get_size()
            print(f"已加载纹理图集: {self.name} ({self._texture_size[0]}x{self._texture_size[1]})")
            return True
        except Exception as e:
            print(f"加载纹理失败 {full_path}: {e}")
            return False
    
    @property
    def surface(self) -> Optional[SoftwareSurface]:
        return self._surface
    
    @property
    def texture_size(self) -> Optional[Tuple[int, int]]:
        return self._texture_size
    
    def get_sprite(self, name: str) -> Optional[Sprite]:
        return self.sprites.get(name)
    
    def get_animation(self, name: str) -> Optional[AnimatedSprite]:
        return self.animations.get(name)
    
    def get_sprite_surface(self, name: str) -> Optional[SoftwareSurface]:
        """获取精灵的子Surface"""
        sprite = self.get_sprite(name)
        if sprite and self._surface:
            try:
                return self._surface.subsurface(sprite.rect).copy()
            except ValueError as e:
                print(f"获取精灵Surface失败 {name}: {e}")
        return None
    
    def get_animation_frame_surface(self, name: str, frame_index: int) -> Optional[SoftwareSurface]:
        """获取动画某帧的子Surface"""
        anim = self.get_animation(name)
        if anim and self._surface and 0 <= frame_index < len(anim.frames):
            frame = anim.frames[frame_index]
            try:
                return self._surface.subsurface(frame.rect).copy()
            except ValueError as e:
                print(f"获取动画帧Surface失败 {name}[{frame_index}]: {e}")
        return None


class TextureAssetManager:
    """
    统一纹理资产管理器
    负责加载、缓存和管理所有纹理资产
    """
    
    def __init__(self, asset_root: str = "assets"):
        """
        初始化资产管理器
        
        Args:
            asset_root: 资产根目录
        """
        self.asset_root = Path(asset_root)
        
        # 资产缓存
        self.atlases: Dict[str, TextureAtlas] = {}  # 纹理图集
        self.sprites: Dict[str, Sprite] = {}  # 所有精灵（扁平化索引）
        self.animations: Dict[str, AnimatedSprite] = {}  # 所有动画（扁平化索引）
        
        # 纹理缓存（按路径）
        self.texture_cache: Dict[str, SoftwareSurface] = {}
        
        # 精灵Surface缓存
        self.sprite_surface_cache: Dict[str, SoftwareSurface] = {}
    
    def load_atlas_config(self, config_path: str, atlas_name: Optional[str] = None) -> Optional[TextureAtlas]:
        """
        从JSON配置文件加载纹理图集
        
        Args:
            config_path: 配置文件路径（相对于asset_root）
            atlas_name: 图集名称（默认使用配置文件名）
            
        Returns:
            加载的纹理图集，失败返回None
        """
        full_path = self.asset_root / config_path
        if not full_path.exists():
            print(f"配置文件不存在: {full_path}")
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"读取配置文件失败 {full_path}: {e}")
            return None
        
        # 确定图集名称
        if atlas_name is None:
            atlas_name = full_path.stem
        
        # 确定纹理路径
        texture_filename = config.get('texture') or config.get('__image_filename', '')
        if not texture_filename:
            print(f"配置文件缺少纹理路径: {config_path}")
            return None
        
        # 构建完整纹理路径（支持多种路径格式）
        config_dir = full_path.parent
        texture_path = None
        
        # 尝试不同的路径组合
        possible_paths = [
            config_dir / texture_filename,                          # 相对于配置文件目录
            self.asset_root / texture_filename,                     # 相对于asset_root
            Path(texture_filename),                                 # 绝对路径
            config_dir / os.path.basename(texture_filename),        # 仅文件名
            config_dir / 'bullet' / os.path.basename(texture_filename),  # bullet子目录
            config_dir.parent / os.path.basename(texture_filename), # 上级目录
        ]
        
        for path in possible_paths:
            if path.exists():
                texture_path = str(path)
                break
        
        if texture_path is None:
            texture_path = str(config_dir / texture_filename)
        
        # 创建图集
        atlas = TextureAtlas(name=atlas_name, texture_path=texture_path)
        
        # 解析精灵
        sprites_data = config.get('sprites', {})
        for sprite_name, sprite_data in sprites_data.items():
            sprite = self._parse_sprite(sprite_name, sprite_data, texture_path)
            atlas.sprites[sprite_name] = sprite
            # 添加到全局索引（使用 atlas_name.sprite_name 格式）
            full_name = f"{atlas_name}.{sprite_name}"
            self.sprites[full_name] = sprite
            # 也支持直接用精灵名访问（如果没有冲突）
            if sprite_name not in self.sprites:
                self.sprites[sprite_name] = sprite
        
        # 解析动画
        animations_data = config.get('animations', {})
        for anim_name, anim_data in animations_data.items():
            animation = self._parse_animation(anim_name, anim_data, texture_path)
            atlas.animations[anim_name] = animation
            # 添加到全局索引
            full_name = f"{atlas_name}.{anim_name}"
            self.animations[full_name] = animation
            if anim_name not in self.animations:
                self.animations[anim_name] = animation
        
        # 加载纹理
        atlas.load_texture()
        if atlas.surface:
            self.texture_cache[texture_path] = atlas.surface
        
        # 缓存图集
        self.atlases[atlas_name] = atlas
        
        print(f"已加载图集 '{atlas_name}': {len(atlas.sprites)} 精灵, {len(atlas.animations)} 动画")
        return atlas
    
    def _parse_sprite(self, name: str, data: dict, texture_path: str) -> Sprite:
        """解析精灵数据"""
        rect = tuple(data.get('rect', [0, 0, 32, 32]))
        center = tuple(data.get('center', [rect[2] / 2, rect[3] / 2]))
        
        return Sprite(
            name=name,
            texture_path=texture_path,
            rect=rect,
            center=center,
            radius=data.get('radius', 0.0),
            rotate=data.get('rotate', data.get('is_rotating', False)),
            scale=tuple(data.get('scale', [1.0, 1.0])),
            metadata=data.get('metadata', {})
        )
    
    def _parse_animation(self, name: str, data: dict, texture_path: str) -> AnimatedSprite:
        """解析动画数据"""
        frames = []
        default_center = tuple(data.get('center', [0, 0]))
        
        # 支持两种帧定义方式
        if 'frames' in data:
            # 方式1: 显式帧列表
            for frame_data in data['frames']:
                if isinstance(frame_data, str):
                    # 精灵名引用 — 从已加载的精灵中查找 rect/center
                    sprite = self.sprites.get(frame_data)
                    if sprite:
                        frames.append(SpriteFrame(rect=sprite.rect, center=sprite.center))
                    else:
                        print(f"[AnimParse] 未找到精灵引用: {frame_data}")
                        frames.append(SpriteFrame(rect=(0, 0, 32, 32), center=default_center))
                else:
                    rect = tuple(frame_data.get('rect', [0, 0, 32, 32]))
                    center = tuple(frame_data.get('center', default_center))
                    frames.append(SpriteFrame(rect=rect, center=center))
        
        elif 'strip' in data:
            # 方式2: 连续帧带（自动计算）
            strip = data['strip']
            start_x = strip.get('x', 0)
            start_y = strip.get('y', 0)
            frame_width = strip.get('width', 32)
            frame_height = strip.get('height', 32)
            frame_count = strip.get('count', 1)
            direction = strip.get('direction', 'horizontal')  # horizontal 或 vertical
            spacing = strip.get('spacing', 0)  # 帧间距
            
            for i in range(frame_count):
                if direction == 'horizontal':
                    x = start_x + i * (frame_width + spacing)
                    y = start_y
                else:
                    x = start_x
                    y = start_y + i * (frame_height + spacing)
                
                frames.append(SpriteFrame(
                    rect=(x, y, frame_width, frame_height),
                    center=default_center
                ))
        
        return AnimatedSprite(
            name=name,
            texture_path=texture_path,
            frames=frames,
            center=default_center,
            radius=data.get('radius', 0.0),
            rotate=data.get('rotate', False),
            frame_duration=data.get('frame_duration', 0.1),
            loop=data.get('loop', True),
            metadata=data.get('metadata', {})
        )
    
    def load_legacy_config(self, config_path: str) -> Optional[TextureAtlas]:
        """
        加载旧格式的精灵配置（兼容现有配置）
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            转换后的纹理图集
        """
        full_path = self.asset_root / config_path
        if not full_path.exists():
            print(f"配置文件不存在: {full_path}")
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"读取配置文件失败: {e}")
            return None
        
        atlas_name = full_path.stem
        texture_filename = config.get('__image_filename', '')
        config_dir = full_path.parent
        texture_path = str(config_dir / texture_filename) if texture_filename else ""
        
        atlas = TextureAtlas(name=atlas_name, texture_path=texture_path)
        
        # 解析旧格式精灵
        sprites_data = config.get('sprites', config)
        for sprite_name, sprite_data in sprites_data.items():
            if sprite_name.startswith('__'):
                continue
            if not isinstance(sprite_data, dict):
                continue
            
            # 处理旧格式的 image_path
            sprite_texture = sprite_data.get('texture_path') or sprite_data.get('image_path') or texture_path
            
            sprite = Sprite(
                name=sprite_name,
                texture_path=sprite_texture,
                rect=tuple(sprite_data.get('rect', [0, 0, 32, 32])),
                center=tuple(sprite_data.get('center', [16, 16])),
                radius=sprite_data.get('radius', 0.0),
                rotate=sprite_data.get('rotate', sprite_data.get('is_rotating', False)),
                scale=tuple(sprite_data.get('scale', [1.0, 1.0]))
            )
            
            atlas.sprites[sprite_name] = sprite
            full_name = f"{atlas_name}.{sprite_name}"
            self.sprites[full_name] = sprite
            if sprite_name not in self.sprites:
                self.sprites[sprite_name] = sprite
        
        # 加载纹理
        if texture_path:
            atlas.load_texture()
            if atlas.surface:
                self.texture_cache[texture_path] = atlas.surface
        
        self.atlases[atlas_name] = atlas
        print(f"已加载旧格式图集 '{atlas_name}': {len(atlas.sprites)} 精灵")
        return atlas
    
    def get_sprite(self, name: str) -> Optional[Sprite]:
        """获取精灵"""
        return self.sprites.get(name)
    
    def get_animation(self, name: str) -> Optional[AnimatedSprite]:
        """获取动画"""
        return self.animations.get(name)
    
    def get_atlas(self, name: str) -> Optional[TextureAtlas]:
        """获取纹理图集"""
        return self.atlases.get(name)
    
    def get_texture(self, path: str) -> Optional[SoftwareSurface]:
        """获取纹理Surface"""
        return self.texture_cache.get(path)
    
    def get_sprite_surface(self, name: str) -> Optional[SoftwareSurface]:
        """
        获取精灵的Surface（带缓存）
        
        Args:
            name: 精灵名称
            
        Returns:
            精灵Surface
        """
        if name in self.sprite_surface_cache:
            return self.sprite_surface_cache[name]
        
        sprite = self.get_sprite(name)
        if not sprite:
            return None
        
        texture = self.texture_cache.get(sprite.texture_path)
        if not texture:
            return None
        
        try:
            surface = texture.subsurface(sprite.rect).copy()
            self.sprite_surface_cache[name] = surface
            return surface
        except ValueError as e:
            print(f"获取精灵Surface失败 {name}: {e}")
            return None
    
    def get_sprite_uv(self, name: str) -> Optional[Tuple[float, float, float, float]]:
        """
        获取精灵的UV坐标（标准顺序：左上右下）
        
        Args:
            name: 精灵名称
            
        Returns:
            (u_left, v_top, u_right, v_bottom) 或 None
        """
        sprite = self.get_sprite(name)
        if not sprite:
            return None
        
        texture = self.texture_cache.get(sprite.texture_path)
        if not texture:
            return None
        
        return sprite.get_uv(texture.get_size())
    
    def get_sprite_uv_for_gl(self, name: str, flip_y: bool = True) -> Optional[Tuple[float, float, float, float]]:
        """
        获取精灵的UV坐标（用于OpenGL渲染）
        
        OpenGL纹理坐标Y轴从下往上，而图片坐标Y轴从上往下
        
        Args:
            name: 精灵名称
            flip_y: 是否翻转Y轴（默认True，用于tobytes翻转的纹理）
            
        Returns:
            (u_left, v_top, u_right, v_bottom) 用于GL渲染
        """
        sprite = self.get_sprite(name)
        if not sprite:
            return None
        
        texture = self.texture_cache.get(sprite.texture_path)
        if not texture:
            return None
        
        tex_w, tex_h = texture.get_size()
        
        u_left = sprite.x / tex_w
        u_right = (sprite.x + sprite.width) / tex_w
        
        if flip_y:
            # 纹理通过 tobytes(..., True) 加载时已翻转Y轴
            v_top = (tex_h - (sprite.y + sprite.height)) / tex_h
            v_bottom = (tex_h - sprite.y) / tex_h
        else:
            v_top = sprite.y / tex_h
            v_bottom = (sprite.y + sprite.height) / tex_h
        
        return (u_left, v_top, u_right, v_bottom)
    
    def get_animation_frame_uv(self, name: str, time: float) -> Optional[Tuple[float, float, float, float]]:
        """
        获取动画当前帧的UV坐标
        
        Args:
            name: 动画名称
            time: 当前时间
            
        Returns:
            (u_left, v_top, u_right, v_bottom) 或 None
        """
        anim = self.get_animation(name)
        if not anim:
            return None
        
        texture = self.texture_cache.get(anim.texture_path)
        if not texture:
            return None
        
        return anim.get_frame_uv_at_time(time, texture.get_size())
    
    def get_animation_frame_uv_for_gl(self, name: str, time: float, flip_y: bool = True) -> Optional[Tuple[float, float, float, float]]:
        """
        获取动画当前帧的UV坐标（用于OpenGL）
        
        Args:
            name: 动画名称
            time: 当前时间
            flip_y: 是否翻转Y轴
            
        Returns:
            (u_left, v_top, u_right, v_bottom) 用于GL渲染
        """
        anim = self.get_animation(name)
        if not anim:
            return None
        
        texture = self.texture_cache.get(anim.texture_path)
        if not texture:
            return None
        
        frame = anim.get_frame_at_time(time)
        tex_w, tex_h = texture.get_size()
        
        u_left = frame.x / tex_w
        u_right = (frame.x + frame.width) / tex_w
        
        if flip_y:
            v_top = (tex_h - (frame.y + frame.height)) / tex_h
            v_bottom = (tex_h - frame.y) / tex_h
        else:
            v_top = frame.y / tex_h
            v_bottom = (frame.y + frame.height) / tex_h
        
        return (u_left, v_top, u_right, v_bottom)
    
    # ==================== 兼容旧 SpriteManager 的接口 ====================
    
    def load_sprite_config_folder(self, folder_path: str) -> bool:
        """
        加载指定文件夹中的所有精灵配置文件（兼容旧接口）
        
        Args:
            folder_path: 包含JSON配置文件的文件夹路径
            
        Returns:
            是否加载成功
        """
        folder = Path(folder_path)
        if not folder.is_absolute():
            folder = Path.cwd() / folder_path
        
        if not folder.exists():
            print(f"文件夹不存在: {folder}")
            return False
        
        print(f"加载精灵配置文件夹: {folder}")
        
        success = True
        config_count = 0
        
        for config_file in folder.rglob("*.json"):
            # 计算相对于asset_root的路径
            try:
                rel_path = config_file.relative_to(self.asset_root)
            except ValueError:
                rel_path = config_file
            
            # 尝试加载为新格式，失败则尝试旧格式
            atlas = self.load_atlas_config(str(rel_path))
            if atlas is None:
                atlas = self.load_legacy_config(str(rel_path))
            
            if atlas:
                config_count += 1
            else:
                print(f"加载配置文件失败: {config_file}")
                success = False
        
        print(f"成功加载 {config_count} 个配置文件，共 {len(self.sprites)} 个精灵")
        return success
    
    def get_all_sprite_ids(self) -> List[str]:
        """获取所有精灵ID（兼容旧接口）"""
        return list(self.sprites.keys())
    
    def get_all_texture_paths(self) -> List[str]:
        """获取所有纹理路径（兼容旧接口）"""
        return list(self.texture_cache.keys())
    
    def get_sprite_texture_path(self, sprite_id: str) -> Optional[str]:
        """获取精灵使用的纹理路径（兼容旧接口）"""
        sprite = self.get_sprite(sprite_id)
        return sprite.texture_path if sprite else None
    
    def get_sprite_image(self, sprite_id: str) -> Optional[SoftwareSurface]:
        """获取精灵所属的纹理图片（兼容旧接口）"""
        sprite = self.get_sprite(sprite_id)
        if sprite:
            return self.texture_cache.get(sprite.texture_path)
        return None
    
    def get_sprite_data(self, sprite_id: str) -> Optional[Dict[str, Any]]:
        """
        获取精灵数据（兼容旧接口）
        
        返回格式与旧 SpriteManager 相同
        """
        sprite = self.get_sprite(sprite_id)
        if not sprite:
            return None
        
        return {
            'rect': list(sprite.rect),
            'center': list(sprite.center),
            'radius': sprite.radius,
            'is_rotating': sprite.rotate,
            'image_path': sprite.texture_path
        }
    
    # ==================== ModernGL 纹理支持 ====================
    
    def create_gl_texture(self, ctx: 'moderngl.Context', texture_path: str, 
                          flip_y: bool = True) -> Optional['moderngl.Texture']:
        """
        从缓存的SoftwareSurface创建ModernGL纹理
        
        Args:
            ctx: ModernGL上下文
            texture_path: 纹理路径
            flip_y: 是否翻转Y轴（OpenGL需要）
            
        Returns:
            ModernGL纹理对象
        """
        if not HAS_MODERNGL:
            print("ModernGL不可用")
            return None
        
        surface = self.texture_cache.get(texture_path)
        if not surface:
            return None
        
        # 获取图片数据
        data = surface.to_bytes("RGBA", flip_y)
        size = surface.get_size()
        
        # 创建ModernGL纹理
        texture = ctx.texture(size, 4, data)
        texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        
        return texture
    
    def create_all_gl_textures(self, ctx: 'moderngl.Context', 
                               flip_y: bool = True) -> Dict[str, 'moderngl.Texture']:
        """
        创建所有已加载纹理的ModernGL版本
        
        Args:
            ctx: ModernGL上下文
            flip_y: 是否翻转Y轴
            
        Returns:
            {texture_path: moderngl.Texture} 字典
        """
        gl_textures = {}
        for path in self.texture_cache.keys():
            texture = self.create_gl_texture(ctx, path, flip_y)
            if texture:
                gl_textures[path] = texture
        return gl_textures
    
    def compute_all_sprite_uvs(self, flip_y: bool = True) -> Dict[str, Tuple[float, float, float, float]]:
        """
        预计算所有精灵的UV坐标
        
        Args:
            flip_y: 是否翻转Y轴（用于OpenGL）
            
        Returns:
            {sprite_id: (u_left, v_top, u_right, v_bottom)} 字典
        """
        uv_map = {}
        for name in self.sprites.keys():
            uv = self.get_sprite_uv_for_gl(name, flip_y) if flip_y else self.get_sprite_uv(name)
            if uv:
                uv_map[name] = uv
        return uv_map
    
    # ==================== 列表和统计方法 ====================
    
    def list_all_sprites(self) -> List[str]:
        """列出所有精灵名称"""
        return list(self.sprites.keys())
    
    def list_all_animations(self) -> List[str]:
        """列出所有动画名称"""
        return list(self.animations.keys())
    
    def list_all_atlases(self) -> List[str]:
        """列出所有图集名称"""
        return list(self.atlases.keys())
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return {
            'atlases': len(self.atlases),
            'sprites': len(self.sprites),
            'animations': len(self.animations),
            'cached_textures': len(self.texture_cache),
            'cached_surfaces': len(self.sprite_surface_cache)
        }
    
    def clear_cache(self):
        """清空Surface缓存"""
        self.sprite_surface_cache.clear()
    
    def clear_all(self):
        """清空所有数据"""
        self.atlases.clear()
        self.sprites.clear()
        self.animations.clear()
        self.texture_cache.clear()
        self.sprite_surface_cache.clear()
    
    def unload_atlas(self, name: str):
        """卸载图集"""
        if name in self.atlases:
            atlas = self.atlases[name]
            
            # 移除精灵索引
            for sprite_name in atlas.sprites.keys():
                full_name = f"{name}.{sprite_name}"
                self.sprites.pop(full_name, None)
                if self.sprites.get(sprite_name) == atlas.sprites[sprite_name]:
                    self.sprites.pop(sprite_name, None)
                self.sprite_surface_cache.pop(sprite_name, None)
                self.sprite_surface_cache.pop(full_name, None)
            
            # 移除动画索引
            for anim_name in atlas.animations.keys():
                full_name = f"{name}.{anim_name}"
                self.animations.pop(full_name, None)
                if self.animations.get(anim_name) == atlas.animations[anim_name]:
                    self.animations.pop(anim_name, None)
            
            # 移除纹理缓存
            self.texture_cache.pop(atlas.texture_path, None)
            
            # 移除图集
            del self.atlases[name]
            print(f"已卸载图集: {name}")


# ==================== 全局实例管理 ====================

_global_texture_asset_manager: Optional[TextureAssetManager] = None


def get_texture_asset_manager() -> TextureAssetManager:
    """获取全局纹理资产管理器实例"""
    global _global_texture_asset_manager
    if _global_texture_asset_manager is None:
        _global_texture_asset_manager = TextureAssetManager()
    return _global_texture_asset_manager


def init_texture_asset_manager(asset_root: str = "assets") -> TextureAssetManager:
    """初始化全局纹理资产管理器"""
    global _global_texture_asset_manager
    _global_texture_asset_manager = TextureAssetManager(asset_root)
    return _global_texture_asset_manager

"""
精灵注册表 - 管理精灵ID到整数索引的映射

解决问题:
1. 子弹池中存储字符串sprite_id效率低（32字符 * 50000 = 6.4MB）
2. 每帧查找sprite数据需要字典查询

优化方案:
- 精灵ID在注册时转换为整数索引
- 子弹数据只存储2字节整数索引
- 预计算并缓存UV/尺寸数据到连续数组
"""

import numpy as np
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass


@dataclass
class SpriteInfo:
    """精灵信息"""
    sprite_id: str
    index: int
    texture_path: str
    rect: Tuple[int, int, int, int]  # x, y, width, height
    uv: Tuple[float, float, float, float]  # u_left, v_top, u_right, v_bottom
    center: Tuple[float, float] = (0.0, 0.0)
    radius: float = 0.0
    size_category: int = 3  # BulletSizeCategory.MEDIUM


class SpriteRegistry:
    """
    精灵注册表
    
    提供精灵ID到整数索引的高效映射，以及预计算的渲染数据
    
    使用方式:
        registry = SpriteRegistry()
        
        # 注册精灵
        idx = registry.register('star_small1', 'bullet1.png', (0, 0, 16, 16), (256, 256))
        
        # 获取索引
        idx = registry.get_index('star_small1')
        
        # 获取批量渲染数据
        uvs = registry.get_uv_array()
        sizes = registry.get_size_array()
    """
    
    # 特殊索引
    INVALID_INDEX = 65535
    DEFAULT_INDEX = 0
    
    def __init__(self, max_sprites: int = 4096):
        """
        初始化注册表
        
        Args:
            max_sprites: 最大精灵数量
        """
        self.max_sprites = max_sprites
        
        # ID到索引的映射
        self._id_to_index: Dict[str, int] = {}
        self._index_to_id: Dict[int, str] = {}
        
        # 精灵信息列表
        self._sprites: List[Optional[SpriteInfo]] = [None] * max_sprites
        
        # 预计算的渲染数据数组
        # UV: [u_left, v_top, u_right, v_bottom]
        self._uv_array = np.zeros((max_sprites, 4), dtype=np.float32)
        # 尺寸: [width, height] (像素)
        self._size_array = np.zeros((max_sprites, 2), dtype=np.float32)
        # 大小分类
        self._category_array = np.zeros(max_sprites, dtype=np.uint8)
        # 碰撞半径
        self._radius_array = np.zeros(max_sprites, dtype=np.float32)
        # 纹理索引
        self._texture_idx_array = np.zeros(max_sprites, dtype=np.uint16)
        
        # 纹理路径到索引的映射
        self._texture_paths: List[str] = []
        self._texture_to_idx: Dict[str, int] = {}
        
        # 当前已注册的精灵数量
        self._count = 0
        
        # 注册默认精灵（索引0）
        self._register_default()
    
    def _register_default(self):
        """注册默认精灵（用于缺失精灵的回退）"""
        self._id_to_index['__default__'] = 0
        self._index_to_id[0] = '__default__'
        self._uv_array[0] = [0.0, 0.0, 1.0, 1.0]
        self._size_array[0] = [16.0, 16.0]
        self._category_array[0] = 3  # MEDIUM
        self._count = 1
    
    def register(
        self,
        sprite_id: str,
        texture_path: str,
        rect: Tuple[int, int, int, int],
        texture_size: Tuple[int, int],
        center: Tuple[float, float] = (0.0, 0.0),
        radius: float = 0.0,
        size_category: int = 3,
    ) -> int:
        """
        注册精灵
        
        Args:
            sprite_id: 精灵唯一ID
            texture_path: 纹理文件路径
            rect: 精灵在纹理中的矩形 (x, y, width, height)
            texture_size: 纹理尺寸 (width, height)
            center: 中心点偏移
            radius: 碰撞半径
            size_category: 大小分类 (BulletSizeCategory)
            
        Returns:
            分配的整数索引
        """
        # 检查是否已注册
        if sprite_id in self._id_to_index:
            return self._id_to_index[sprite_id]
        
        # 检查容量
        if self._count >= self.max_sprites:
            print(f"Warning: SpriteRegistry full, cannot register '{sprite_id}'")
            return self.DEFAULT_INDEX
        
        # 分配索引
        idx = self._count
        self._count += 1
        
        # 计算UV坐标
        tex_w, tex_h = texture_size
        x, y, w, h = rect
        u_left = x / tex_w
        v_top = y / tex_h
        u_right = (x + w) / tex_w
        v_bottom = (y + h) / tex_h
        
        # 注册纹理
        if texture_path not in self._texture_to_idx:
            tex_idx = len(self._texture_paths)
            self._texture_paths.append(texture_path)
            self._texture_to_idx[texture_path] = tex_idx
        else:
            tex_idx = self._texture_to_idx[texture_path]
        
        # 存储映射
        self._id_to_index[sprite_id] = idx
        self._index_to_id[idx] = sprite_id
        
        # 存储精灵信息
        self._sprites[idx] = SpriteInfo(
            sprite_id=sprite_id,
            index=idx,
            texture_path=texture_path,
            rect=rect,
            uv=(u_left, v_top, u_right, v_bottom),
            center=center,
            radius=radius,
            size_category=size_category,
        )
        
        # 更新预计算数组
        self._uv_array[idx] = [u_left, v_top, u_right, v_bottom]
        self._size_array[idx] = [w, h]
        self._category_array[idx] = size_category
        self._radius_array[idx] = radius
        self._texture_idx_array[idx] = tex_idx
        
        return idx
    
    def register_from_sprite_manager(self, sprite_manager, texture_sizes: Dict[str, Tuple[int, int]]):
        """
        从现有的SpriteManager批量注册精灵
        
        Args:
            sprite_manager: SpriteManager实例
            texture_sizes: 纹理尺寸字典 {texture_path: (width, height)}
        """
        for sprite_id in sprite_manager.get_all_sprite_ids():
            sprite_data = sprite_manager.get_sprite(sprite_id)
            if sprite_data is None:
                continue
            
            texture_path = sprite_manager.get_sprite_texture_path(sprite_id)
            if not texture_path or texture_path not in texture_sizes:
                continue
            
            rect = sprite_data.get('rect', (0, 0, 16, 16))
            tex_size = texture_sizes[texture_path]
            radius = sprite_data.get('radius', 0.0)
            
            # 从精灵尺寸推断大小分类
            max_dim = max(rect[2], rect[3])
            if max_dim >= 64:
                category = 1  # HUGE
            elif max_dim >= 32:
                category = 2  # LARGE
            elif max_dim >= 16:
                category = 3  # MEDIUM
            elif max_dim >= 8:
                category = 4  # SMALL
            else:
                category = 5  # TINY
            
            self.register(
                sprite_id=sprite_id,
                texture_path=texture_path,
                rect=rect,
                texture_size=tex_size,
                radius=radius,
                size_category=category,
            )
    
    def get_index(self, sprite_id: str) -> int:
        """
        获取精灵的整数索引
        
        Args:
            sprite_id: 精灵ID
            
        Returns:
            整数索引，未找到返回DEFAULT_INDEX
        """
        return self._id_to_index.get(sprite_id, self.DEFAULT_INDEX)
    
    def get_id(self, index: int) -> str:
        """
        获取索引对应的精灵ID
        
        Args:
            index: 整数索引
            
        Returns:
            精灵ID，未找到返回'__default__'
        """
        return self._index_to_id.get(index, '__default__')
    
    def get_info(self, index: int) -> Optional[SpriteInfo]:
        """获取精灵信息"""
        if 0 <= index < self._count:
            return self._sprites[index]
        return None
    
    def get_uv(self, index: int) -> np.ndarray:
        """获取单个精灵的UV"""
        return self._uv_array[index]
    
    def get_size(self, index: int) -> np.ndarray:
        """获取单个精灵的尺寸"""
        return self._size_array[index]
    
    def get_uv_array(self) -> np.ndarray:
        """获取UV数组（用于批量渲染）"""
        return self._uv_array[:self._count]
    
    def get_size_array(self) -> np.ndarray:
        """获取尺寸数组（用于批量渲染）"""
        return self._size_array[:self._count]
    
    def get_category_array(self) -> np.ndarray:
        """获取大小分类数组（用于渲染排序）"""
        return self._category_array[:self._count]
    
    def get_texture_index(self, index: int) -> int:
        """获取精灵对应的纹理索引"""
        return self._texture_idx_array[index]
    
    def get_texture_path(self, texture_idx: int) -> str:
        """获取纹理索引对应的路径"""
        if 0 <= texture_idx < len(self._texture_paths):
            return self._texture_paths[texture_idx]
        return ""
    
    def get_all_texture_paths(self) -> List[str]:
        """获取所有纹理路径"""
        return self._texture_paths.copy()
    
    @property
    def count(self) -> int:
        """已注册的精灵数量"""
        return self._count
    
    def __contains__(self, sprite_id: str) -> bool:
        return sprite_id in self._id_to_index
    
    def __len__(self) -> int:
        return self._count


# ============= 全局实例 =============

_sprite_registry: Optional[SpriteRegistry] = None


def get_sprite_registry() -> SpriteRegistry:
    """获取全局精灵注册表"""
    global _sprite_registry
    if _sprite_registry is None:
        _sprite_registry = SpriteRegistry()
    return _sprite_registry


def init_sprite_registry(max_sprites: int = 4096) -> SpriteRegistry:
    """初始化全局精灵注册表"""
    global _sprite_registry
    _sprite_registry = SpriteRegistry(max_sprites)
    return _sprite_registry

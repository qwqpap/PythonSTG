"""
精灵管理器 - 兼容层

这个模块现在作为兼容层，内部使用新的 TextureAssetManager
保持旧的接口以兼容现有代码
"""
import json
import os
import pygame
from typing import Dict, List, Optional, Any
from ..texture_asset import TextureAssetManager, get_texture_asset_manager, init_texture_asset_manager


class SpriteManager:
    """
    精灵管理器（兼容层）
    
    内部使用 TextureAssetManager，但保持旧的接口
    """
    
    def __init__(self):
        """初始化精灵管理器"""
        # 使用全局的 TextureAssetManager
        self._asset_manager: Optional[TextureAssetManager] = None
        
        # 保持旧接口的数据结构
        self.sprites: Dict[str, dict] = {}
        self.image_cache: Dict[str, pygame.Surface] = {}
        self.subsurface_cache: Dict[str, pygame.Surface] = {}
        self.config_files: List[str] = []
        self.sprite_texture_map: Dict[str, str] = {}
        self.texture_paths: set = set()
    
    @property
    def asset_manager(self) -> TextureAssetManager:
        """获取或创建资产管理器"""
        if self._asset_manager is None:
            self._asset_manager = get_texture_asset_manager()
        return self._asset_manager
    
    def _sync_from_asset_manager(self):
        """从资产管理器同步数据到兼容层"""
        am = self.asset_manager
        
        # 同步精灵数据
        for name, sprite in am.sprites.items():
            self.sprites[name] = {
                'rect': list(sprite.rect),
                'center': list(sprite.center),
                'radius': sprite.radius,
                'is_rotating': sprite.rotate,
                'image_path': sprite.texture_path
            }
            self.sprite_texture_map[name] = sprite.texture_path
            self.texture_paths.add(sprite.texture_path)
        
        # 同步纹理缓存
        self.image_cache = am.texture_cache
    
    def load_sprite_config(self, config_path: str) -> bool:
        """
        加载精灵配置文件
        
        Args:
            config_path: JSON配置文件路径
            
        Returns:
            是否加载成功
        """
        try:
            # 规范化路径
            config_path = os.path.normpath(config_path)
            
            # 如果是相对路径且不存在，尝试相对于当前工作目录
            if not os.path.isabs(config_path) and not os.path.exists(config_path):
                alt_path = os.path.join(os.getcwd(), config_path)
                alt_path = os.path.normpath(alt_path)
                if os.path.exists(alt_path):
                    config_path = alt_path
            
            if not os.path.exists(config_path):
                print(f"配置文件不存在: {config_path}")
                return False
            
            # 保存配置路径
            if config_path not in self.config_files:
                self.config_files.append(config_path)
            
            # 计算相对于assets的路径
            am = self.asset_manager
            try:
                rel_path = os.path.relpath(config_path, am.asset_root)
            except ValueError:
                rel_path = config_path
            
            # 尝试使用新格式加载
            atlas = am.load_atlas_config(rel_path)
            if atlas is None:
                # 尝试旧格式
                atlas = am.load_legacy_config(rel_path)
            
            if atlas:
                self._sync_from_asset_manager()
                return True
            
            return False
            
        except Exception as e:
            print(f"加载精灵配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_sprite(self, sprite_id: str) -> Optional[dict]:
        """
        获取精灵数据
        
        Args:
            sprite_id: 精灵ID
            
        Returns:
            精灵数据字典
        """
        # 优先从兼容层获取
        if sprite_id in self.sprites:
            return self.sprites[sprite_id]
        
        # 从资产管理器获取
        data = self.asset_manager.get_sprite_data(sprite_id)
        if data:
            self.sprites[sprite_id] = data
        return data
    
    def get_sprite_image(self, sprite_id: str) -> Optional[pygame.Surface]:
        """
        获取精灵对应的纹理图片
        
        Args:
            sprite_id: 精灵ID
            
        Returns:
            pygame.Surface对象
        """
        return self.asset_manager.get_sprite_image(sprite_id)

    def get_sprite_surface(self, sprite_id: str) -> Optional[pygame.Surface]:
        """
        返回裁剪后的子精灵 Surface
        
        Args:
            sprite_id: 精灵ID
            
        Returns:
            pygame.Surface
        """
        # 缓存优先
        if sprite_id in self.subsurface_cache:
            return self.subsurface_cache[sprite_id]
        
        surface = self.asset_manager.get_sprite_surface(sprite_id)
        if surface:
            self.subsurface_cache[sprite_id] = surface
        return surface
    
    def get_all_sprite_ids(self) -> List[str]:
        """获取所有精灵ID"""
        return self.asset_manager.get_all_sprite_ids()
    
    def load_sprite_config_folder(self, folder_path: str) -> bool:
        """
        加载指定文件夹中的所有精灵配置文件
        
        Args:
            folder_path: 包含JSON配置文件的文件夹路径
            
        Returns:
            是否加载成功
        """
        success = self.asset_manager.load_sprite_config_folder(folder_path)
        if success:
            self._sync_from_asset_manager()
        return success
    
    def get_sprite_texture_path(self, sprite_id: str) -> Optional[str]:
        """获取精灵使用的纹理路径"""
        return self.asset_manager.get_sprite_texture_path(sprite_id)
    
    def get_all_texture_paths(self) -> List[str]:
        """获取所有加载的纹理路径"""
        return self.asset_manager.get_all_texture_paths()
    
    def clear(self):
        """清除所有精灵数据和缓存"""
        self.sprites.clear()
        self.image_cache.clear()
        self.subsurface_cache.clear()
        self.sprite_texture_map.clear()
        self.texture_paths.clear()
        self.config_files.clear()
        self.asset_manager.clear_all()
    
    def save_sprite_config(self, config_path: str) -> bool:
        """保存精灵配置到指定文件"""
        try:
            # 按图片路径分组精灵数据
            sprites_by_image = {}
            for sprite_id, sprite_data in self.sprites.items():
                image_path = sprite_data.get('image_path', '')
                if image_path not in sprites_by_image:
                    sprites_by_image[image_path] = {}
                sprites_by_image[image_path][sprite_id] = {
                    'rect': sprite_data['rect'],
                    'center': sprite_data['center'],
                    'radius': sprite_data['radius'],
                    'rotate': sprite_data.get('is_rotating', False)
                }
            
            # 为每个图片路径创建一个配置文件
            for image_path, sprites_data in sprites_by_image.items():
                config_dir = os.path.dirname(config_path)
                relative_image_path = os.path.relpath(image_path, config_dir) if image_path else ""
                
                config_data = {
                    'version': '2.0',
                    'texture': relative_image_path,
                    'sprites': sprites_data,
                    'animations': {}
                }
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            print(f"精灵配置已保存到: {config_path}")
            return True
        except Exception as e:
            print(f"保存精灵配置失败: {e}")
            return False
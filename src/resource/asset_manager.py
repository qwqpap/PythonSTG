"""
资产管理器 - 统一管理游戏资源（纹理、精灵、音频等）
参考 LuaSTG 的资源管理方式
"""
import os
import json
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from ..core.image_loader import load_image_surface, SoftwareSurface
from ..core.audio_backend import get_audio_backend


class AssetManager:
    """
    游戏资产管理器
    负责加载和管理所有游戏资源（图片、音频、配置等）
    """
    
    def __init__(self, asset_root: str = "assets"):
        """
        初始化资产管理器
        
        Args:
            asset_root: 资产根目录
        """
        self.asset_root = Path(asset_root)
        
        # 资源缓存
        self.textures: Dict[str, SoftwareSurface] = {}  # 纹理缓存
        self.sprites: Dict[str, dict] = {}  # 精灵配置缓存
        self.sounds: Dict[str, object] = {}  # 音效缓存
        self.music: Dict[str, str] = {}  # 音乐文件路径
        self.configs: Dict[str, dict] = {}  # 配置文件缓存
        
        # 资源组（用于批量加载/卸载）
        self.resource_groups: Dict[str, List[str]] = {}
        
    def load_texture(self, name: str, path: str, convert_alpha: bool = True) -> SoftwareSurface:
        """
        加载纹理
        
        Args:
            name: 纹理名称（用于引用）
            path: 纹理文件路径（相对于资产根目录）
            convert_alpha: 是否转换为带alpha通道的格式
            
        Returns:
            加载的纹理Surface
        """
        if name in self.textures:
            return self.textures[name]
        
        full_path = self.asset_root / path
        if not full_path.exists():
            print(f"Warning: Texture not found: {full_path}")
            surface = SoftwareSurface(32, 32)
            surface.fill((255, 0, 255))
            self.textures[name] = surface
            return surface
        
        surface = load_image_surface(str(full_path))
        
        self.textures[name] = surface
        print(f"Loaded texture: {name} from {path}")
        return surface
    
    def get_texture(self, name: str) -> Optional[SoftwareSurface]:
        """获取已加载的纹理"""
        return self.textures.get(name)
    
    def load_sprite_config(self, name: str, config_path: str) -> dict:
        """
        加载精灵配置文件（JSON格式）
        
        Args:
            name: 配置名称
            config_path: 配置文件路径（相对于资产根目录）
            
        Returns:
            精灵配置字典
        """
        if name in self.sprites:
            return self.sprites[name]
        
        full_path = self.asset_root / config_path
        if not full_path.exists():
            print(f"Warning: Sprite config not found: {full_path}")
            return {}
        
        with open(full_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        self.sprites[name] = config
        print(f"Loaded sprite config: {name} from {config_path}")
        return config
    
    def get_sprite_config(self, name: str) -> Optional[dict]:
        """获取精灵配置"""
        return self.sprites.get(name)
    
    def load_sound(self, name: str, path: str) -> Optional[object]:
        """
        加载音效
        
        Args:
            name: 音效名称
            path: 音效文件路径（相对于资产根目录）
            
        Returns:
            加载的音效对象
        """
        if name in self.sounds:
            return self.sounds[name]
        
        full_path = self.asset_root / path
        if not full_path.exists():
            print(f"Warning: Sound not found: {full_path}")
            return None
        
        try:
            sound = get_audio_backend().load_sound(str(full_path))
            self.sounds[name] = sound
            print(f"Loaded sound: {name} from {path}")
            return sound
        except Exception as e:
            print(f"Error loading sound {name}: {e}")
            return None
    
    def get_sound(self, name: str) -> Optional[object]:
        """获取音效"""
        return self.sounds.get(name)
    
    def play_sound(self, name: str, volume: float = 1.0) -> bool:
        """
        播放音效
        
        Args:
            name: 音效名称
            volume: 音量（0.0-1.0）
            
        Returns:
            是否播放成功
        """
        sound = self.get_sound(name)
        if sound:
            sound.set_volume(volume)
            sound.play()
            return True
        return False
    
    def register_music(self, name: str, path: str):
        """
        注册音乐文件（不立即加载）
        
        Args:
            name: 音乐名称
            path: 音乐文件路径（相对于资产根目录）
        """
        full_path = self.asset_root / path
        if full_path.exists():
            self.music[name] = str(full_path)
            print(f"Registered music: {name} from {path}")
        else:
            print(f"Warning: Music not found: {full_path}")
    
    def play_music(self, name: str, loops: int = -1, volume: float = 1.0) -> bool:
        """
        播放背景音乐
        
        Args:
            name: 音乐名称
            loops: 循环次数（-1为无限循环）
            volume: 音量（0.0-1.0）
            
        Returns:
            是否播放成功
        """
        if name not in self.music:
            print(f"Warning: Music not registered: {name}")
            return False
        
        try:
            get_audio_backend().load_and_play_bgm(self.music[name], loops=loops, volume=volume)
            return True
        except Exception as e:
            print(f"Error playing music {name}: {e}")
            return False
    
    def stop_music(self):
        """停止背景音乐"""
        get_audio_backend().stop_bgm()
    
    def load_config(self, name: str, path: str) -> dict:
        """
        加载配置文件（JSON格式）
        
        Args:
            name: 配置名称
            path: 配置文件路径（相对于资产根目录）
            
        Returns:
            配置字典
        """
        if name in self.configs:
            return self.configs[name]
        
        full_path = self.asset_root / path
        if not full_path.exists():
            print(f"Warning: Config not found: {full_path}")
            return {}
        
        with open(full_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        self.configs[name] = config
        print(f"Loaded config: {name} from {path}")
        return config
    
    def get_config(self, name: str) -> Optional[dict]:
        """获取配置"""
        return self.configs.get(name)
    
    def create_resource_group(self, group_name: str):
        """创建资源组"""
        if group_name not in self.resource_groups:
            self.resource_groups[group_name] = []
    
    def add_to_group(self, group_name: str, resource_name: str):
        """将资源添加到组"""
        if group_name not in self.resource_groups:
            self.create_resource_group(group_name)
        self.resource_groups[group_name].append(resource_name)
    
    def load_group(self, group_name: str):
        """加载资源组（需要预先定义）"""
        if group_name not in self.resource_groups:
            print(f"Warning: Resource group not found: {group_name}")
            return
        
        print(f"Loading resource group: {group_name}")
        # 这里可以根据需要扩展批量加载逻辑
    
    def unload_texture(self, name: str):
        """卸载纹理"""
        if name in self.textures:
            del self.textures[name]
            print(f"Unloaded texture: {name}")
    
    def unload_sound(self, name: str):
        """卸载音效"""
        if name in self.sounds:
            del self.sounds[name]
            print(f"Unloaded sound: {name}")
    
    def clear_all(self):
        """清空所有资源"""
        self.textures.clear()
        self.sprites.clear()
        self.sounds.clear()
        self.music.clear()
        self.configs.clear()
        self.resource_groups.clear()
        print("Cleared all assets")
    
    def get_texture_size(self, name: str) -> Optional[Tuple[int, int]]:
        """获取纹理尺寸"""
        texture = self.get_texture(name)
        if texture:
            return texture.get_size()
        return None
    
    def list_assets(self):
        """列出所有已加载的资源"""
        print("\n=== Asset Manager Status ===")
        print(f"Textures: {len(self.textures)}")
        for name in self.textures.keys():
            print(f"  - {name}")
        print(f"Sprites: {len(self.sprites)}")
        for name in self.sprites.keys():
            print(f"  - {name}")
        print(f"Sounds: {len(self.sounds)}")
        for name in self.sounds.keys():
            print(f"  - {name}")
        print(f"Music: {len(self.music)}")
        for name in self.music.keys():
            print(f"  - {name}")
        print(f"Configs: {len(self.configs)}")
        for name in self.configs.keys():
            print(f"  - {name}")
        print("============================\n")


# 全局资产管理器实例（可选）
_global_asset_manager: Optional[AssetManager] = None


def get_asset_manager() -> AssetManager:
    """获取全局资产管理器实例"""
    global _global_asset_manager
    if _global_asset_manager is None:
        _global_asset_manager = AssetManager()
    return _global_asset_manager


def init_asset_manager(asset_root: str = "assets") -> AssetManager:
    """初始化全局资产管理器"""
    global _global_asset_manager
    _global_asset_manager = AssetManager(asset_root)
    return _global_asset_manager

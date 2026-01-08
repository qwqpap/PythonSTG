import json
import os
import pygame

class SpriteManager:
    def __init__(self):
        """
        初始化精灵管理器
        """
        self.sprites = {}
        self.image_cache = {}
        self.config_files = []
        self.sprite_texture_map = {}  # 记录每个精灵使用的纹理路径
        
    def load_sprite_config(self, config_path):
        """
        加载精灵配置文件
        :param config_path: JSON配置文件路径
        :return: 是否加载成功
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 保存配置路径
            if config_path not in self.config_files:
                self.config_files.append(config_path)
            config_dir = os.path.dirname(config_path)
            
            # 获取图片文件名
            image_filename = config_data.get('__image_filename', '')
            image_path = os.path.join(config_dir, image_filename)
            
            # 加载图片
            if os.path.exists(image_path) and image_path not in self.image_cache:
                self.image_cache[image_path] = pygame.image.load(image_path)
            
            # 解析精灵数据
            if 'sprites' in config_data:
                # 新格式：精灵数据在sprites字段下
                for sprite_id, sprite_data in config_data['sprites'].items():
                    # 保存精灵数据
                    self.sprites[sprite_id] = {
                        'rect': sprite_data.get('rect', [0, 0, 0, 0]),
                        'center': sprite_data.get('center', [0, 0]),
                        'radius': sprite_data.get('radius', 0.0),
                        'is_rotating': sprite_data.get('is_rotating', sprite_data.get('rotate', False)),
                        'image_path': image_path
                    }
                    # 记录精灵使用的纹理路径
                    self.sprite_texture_map[sprite_id] = image_path
            else:
                # 旧格式：精灵数据直接在根级别
                for sprite_id, sprite_data in config_data.items():
                    if sprite_id != '__image_filename':
                        # 保存精灵数据
                        self.sprites[sprite_id] = {
                            'rect': sprite_data.get('rect', [0, 0, 0, 0]),
                            'center': sprite_data.get('center', [0, 0]),
                            'radius': sprite_data.get('radius', 0.0),
                            'is_rotating': sprite_data.get('is_rotating', sprite_data.get('rotate', False)),
                            'image_path': image_path
                        }
                        # 记录精灵使用的纹理路径
                        self.sprite_texture_map[sprite_id] = image_path
            
            return True
        except Exception as e:
            print(f"加载精灵配置失败: {e}")
            return False
    
    def get_sprite(self, sprite_id):
        """
        获取精灵数据
        :param sprite_id: 精灵ID
        :return: 精灵数据字典，如果不存在则返回None
        """
        return self.sprites.get(sprite_id)
    
    def get_sprite_image(self, sprite_id):
        """
        获取精灵对应的图片
        :param sprite_id: 精灵ID
        :return: pygame.Surface对象，如果不存在则返回None
        """
        sprite_data = self.get_sprite(sprite_id)
        if sprite_data and sprite_data['image_path'] in self.image_cache:
            return self.image_cache[sprite_data['image_path']]
        return None
    
    def get_all_sprite_ids(self):
        """
        获取所有精灵ID
        :return: 精灵ID列表
        """
        return list(self.sprites.keys())
    
    def load_sprite_config_folder(self, folder_path):
        """
        加载指定文件夹中的所有精灵配置文件
        :param folder_path: 包含JSON配置文件的文件夹路径
        :return: 是否所有文件都加载成功
        """
        if not os.path.exists(folder_path):
            print(f"文件夹不存在: {folder_path}")
            return False
        
        success = True
        
        # 遍历文件夹中的所有文件
        for filename in os.listdir(folder_path):
            if filename.endswith('.json'):
                config_path = os.path.join(folder_path, filename)
                if not self.load_sprite_config(config_path):
                    print(f"加载配置文件失败: {config_path}")
                    success = False
        
        return success
    
    def get_sprite_texture_path(self, sprite_id):
        """
        获取指定精灵使用的纹理路径
        :param sprite_id: 精灵ID
        :return: 纹理路径，如果精灵不存在则返回None
        """
        return self.sprite_texture_map.get(sprite_id)
    
    def get_all_texture_paths(self):
        """
        获取所有加载的纹理路径
        :return: 纹理路径集合
        """
        return set(self.image_cache.keys())
    
    def clear(self):
        """
        清除所有精灵数据和缓存
        """
        self.sprites.clear()
        self.image_cache.clear()
        self.config_path = None
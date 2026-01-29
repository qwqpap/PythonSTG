"""
物品渲染器 - 使用 ModernGL 渲染掉落物
"""

import moderngl
import numpy as np
import pygame
import os
import json
from typing import List, Dict, Optional, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..resource.texture_asset import TextureAssetManager


class ItemRenderer:
    """物品渲染器"""
    
    # ItemType mapping to sprite names in config
    ITEM_TYPE_NAMES = {
        1: "item_power",       # POWER
        2: "item_point",       # POINT
        3: "item_life_chip",   # LIFE_CHIP
        4: "item_power_full",  # POWER_FULL
        5: "item_faith",       # FAITH
        6: "item_power_large", # POWER_LARGE
        7: "item_extend",      # EXTEND
        8: "item_faith_minor", # FAITH_MINOR
        9: "item_bomb_chip",   # BOMB_CHIP
        10: "item_bomb"        # BOMB
    }
    
    def __init__(self, ctx: moderngl.Context, base_size=(384, 448)):
        """
        初始化物品渲染器
        
        Args:
            ctx: ModernGL 上下文
            base_size: 游戏基础尺寸
        """
        self.ctx = ctx
        self.base_size = base_size
        
        # 纹理
        self.texture: Optional[moderngl.Texture] = None
        self.texture_size = (64, 160)
        
        # 精灵 UV 缓存
        self.sprite_uvs: Dict[int, tuple] = {}
        
        # 初始化着色器
        self._init_shader()
    
    def _init_shader(self):
        """初始化着色器"""
        vertex_shader = """
        #version 330
        
        in vec2 in_vert;
        in vec2 in_uv_base;
        in vec2 in_offset;
        in float in_scale;
        in vec4 in_uv_rect;
        
        out vec2 v_uv;
        
        void main() {
            vec2 scaled = in_vert * in_scale;
            vec2 position = scaled + in_offset;
            // 宽高比校正
            position.y *= 384.0 / 448.0;
            gl_Position = vec4(position, 0.0, 1.0);
            // UV 映射
            v_uv = in_uv_base * vec2(in_uv_rect.z - in_uv_rect.x, in_uv_rect.w - in_uv_rect.y) + in_uv_rect.xy;
        }
        """
        
        fragment_shader = """
        #version 330
        
        uniform sampler2D u_texture;
        
        in vec2 v_uv;
        out vec4 f_color;
        
        void main() {
            vec4 tex_color = texture(u_texture, v_uv);
            f_color = tex_color;
        }
        """
        
        self.program = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        self.program['u_texture'].value = 0
        
        # 单位四边形顶点（32x32 物品）
        scale_factor = 2.0 / self.base_size[1]
        size = 32 * scale_factor
        half = size / 2
        
        vertices = np.array([
            -half,  half, 0.0, 0.0,
            -half, -half, 0.0, 1.0,
             half,  half, 1.0, 0.0,
             half,  half, 1.0, 0.0,
            -half, -half, 0.0, 1.0,
             half, -half, 1.0, 1.0,
        ], dtype='f4')
        
        self.vbo = self.ctx.buffer(vertices.tobytes())
        
        # 实例化缓冲区
        self.instance_vbo = self.ctx.buffer(reserve=1000 * 2 * 4)   # offset
        self.scale_vbo = self.ctx.buffer(reserve=1000 * 1 * 4)      # scale
        self.uv_vbo = self.ctx.buffer(reserve=1000 * 4 * 4)         # uv_rect
        
        self.vao = self.ctx.vertex_array(
            self.program,
            [
                (self.vbo, '2f 2f', 'in_vert', 'in_uv_base'),
                (self.instance_vbo, '2f/i', 'in_offset'),
                (self.scale_vbo, '1f/i', 'in_scale'),
                (self.uv_vbo, '4f/i', 'in_uv_rect'),
            ]
        )
    
    def load_texture(self, texture_path: str = "assets/images/item/item.png", 
                     asset_manager: Optional['TextureAssetManager'] = None,
                     config_path: Optional[str] = None):
        """
        加载物品纹理
        
        Args:
            texture_path: 纹理文件路径
            asset_manager: 可选的纹理资产管理器（如果提供，将使用其缓存）
            config_path: 自定义配置文件路径 (Optional)
        """
        # 尝试自动查找配置文件
        config_data = None
        
        # 1. 尝试使用传入的 config_path
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                print(f"已加载物品配置: {config_path}")
            except Exception as e:
                print(f"无法读取配置 {config_path}: {e}")

        # 2. 如果没有传入，尝试在纹理目录找 item.json
        if config_data is None:
            dir_path = os.path.dirname(texture_path)
            auto_config_path = os.path.join(dir_path, "item.json")
            if os.path.exists(auto_config_path):
                try:
                    with open(auto_config_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    print(f"自动加载物品配置: {auto_config_path}")
                except Exception as e:
                    print(f"无法读取自动配置 {auto_config_path}: {e}")

        # 尝试从资产管理器获取
        if asset_manager:
            surface = asset_manager.get_texture(texture_path)

            if surface is None:
                # 尝试加载
                from ..resource.texture_asset import get_texture_asset_manager
                manager = get_texture_asset_manager()
                # 检查纹理缓存
                for path, tex in manager.texture_cache.items():
                    if texture_path in path or path.endswith(os.path.basename(texture_path)):
                        surface = tex
                        break
        
        if not os.path.exists(texture_path):
            print(f"物品纹理不存在: {texture_path}")
            return False
        
        try:
            img = pygame.image.load(texture_path).convert_alpha()
            self.texture_size = img.get_size()
            self.texture = self.ctx.texture(
                self.texture_size, 4,
                pygame.image.tobytes(img, "RGBA", True)
            )
            self.texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
            
            # 计算UV
            if config_data and "sprites" in config_data:
                self._compute_uvs_from_config(config_data["sprites"])
            else:
                self._precompute_uvs()
            
            print(f"已加载物品纹理: {texture_path}")
            return True
        except Exception as e:
            print(f"加载物品纹理失败: {e}")
            return False
    
    def _compute_uvs_from_config(self, sprites_config: Dict[str, Any]):
        """从配置计算 UV"""
        tex_w, tex_h = self.texture_size
        
        # 反向映射: 名字 -> ID
        name_to_id = {v: k for k, v in self.ITEM_TYPE_NAMES.items()}
        
        for name, data in sprites_config.items():
            if name in name_to_id:
                item_id = name_to_id[name]
                rect = data.get("rect", [0, 0, 32, 32])
                x, y, w, h = rect
                
                # tobytes(flip=True) 已翻转纹理，ModernGL 中 (0,0) 左下
                # 如果 texture 加载时用了 vertical flip, 则 v_top 对应 y=0 的行
                # 但是 Pygame tobytes(flip=True) 意味着 y=0 变成了底部
                # 通常 UV: (0,0) is bottom-left
                # Rect (x, y, w, h) 通常 y 是从顶部开始 (top-left system)
                # 所以 y_in_gl = height - y - h
                
                u_left = x / tex_w
                u_right = (x + w) / tex_w
                

                
                v_top = y / tex_h 
                v_bottom = (y + h) / tex_h

                self.sprite_uvs[item_id] = (u_left, v_bottom, u_right, v_top)
                
    def _precompute_uvs(self):
        """预计算所有物品类型的 UV 坐标"""
        tex_w, tex_h = self.texture_size
        
        # item.png: 64x160, 每个 32x32, 2列5行
        item_size = 32
        cols = 2
        
        for i in range(10):
            col = i % cols
            row = i // cols
            
            x = col * item_size
            y = row * item_size
            
            # tobytes(flip=True) 已翻转纹理，UV 使用原始坐标
            u_left = x / tex_w
            u_right = (x + item_size) / tex_w
            v_top = y / tex_h
            v_bottom = (y + item_size) / tex_h
            
            self.sprite_uvs[i] = (u_left, v_bottom, u_right, v_top)
    
    def render_items(self, items: list):
        """
        渲染所有物品
        
        Args:
            items: Item 对象列表
        """
        if not self.texture or not items:
            return
        
        count = len(items)
        if count == 0:
            return
        
        # 准备实例数据
        offsets = np.zeros((count, 2), dtype='f4')
        scales = np.ones(count, dtype='f4')
        uv_rects = np.zeros((count, 4), dtype='f4')
        
        for i, item in enumerate(items):
            offsets[i] = [item.x, item.y]
            
            # 弹出动画缩放
            if item.timer < 24:
                scales[i] = (item.timer + 25) / 48
            else:
                scales[i] = 1.0
            
            # UV
            sprite_idx = item.sprite_index
            if sprite_idx in self.sprite_uvs:
                uv_rects[i] = self.sprite_uvs[sprite_idx]
            else:
                uv_rects[i] = [0, 0, 1, 1]
        
        # 上传数据
        self.instance_vbo.write(offsets.tobytes())
        self.scale_vbo.write(scales.tobytes())
        self.uv_vbo.write(uv_rects.tobytes())
        
        # 渲染
        self.texture.use(0)
        self.vao.render(moderngl.TRIANGLES, instances=count)
    
    def cleanup(self):
        """清理资源"""
        pass

"""
优化版子弹渲染器 - 配合 OptimizedBulletPool 使用

主要优化:
1. 使用预计算的渲染数据（避免每帧Python循环查询UV/尺寸）
2. 批量上传GPU数据
3. 按纹理/大小分组批量渲染
"""

import moderngl
import numpy as np
from typing import Dict, List, Tuple, Optional

# 使用绝对导入以确保兼容性
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.config import get_config
from src.core.sprite_registry import get_sprite_registry


class OptimizedBulletRenderer:
    """
    优化版子弹渲染器
    
    配合 OptimizedBulletPool.prepare_render_data() 使用
    """
    
    def __init__(self, ctx: moderngl.Context, textures: Dict[str, moderngl.Texture]):
        """
        初始化渲染器
        
        Args:
            ctx: ModernGL上下文
            textures: 纹理字典 {texture_path: texture}
        """
        self.ctx = ctx
        self.textures = textures
        self.config = get_config()
        self.sprite_registry = get_sprite_registry()
        
        # 初始化shader和缓冲区
        self._init_shader()
        self._init_buffers()
    
    def _init_shader(self):
        """初始化着色器"""
        vertex_shader = """
        #version 330
        
        // 顶点属性
        in vec2 in_vert;
        in vec2 in_uv_base;
        
        // 实例属性
        in vec2 in_offset;      // 位置
        in float in_angle;      // 角度
        in vec4 in_uv_rect;     // UV矩形 [u_left, v_top, u_right, v_bottom]
        in vec2 in_scale;       // 尺寸
        
        out vec2 v_uv;
        
        uniform float u_y_scale;  // Y轴缩放因子
        
        void main() {
            // 缩放
            vec2 scaled = in_vert * in_scale;
            
            // 旋转
            float s = sin(in_angle);
            float c = cos(in_angle);
            vec2 rotated = vec2(
                scaled.x * c - scaled.y * s,
                scaled.x * s + scaled.y * c
            );
            
            // 平移
            vec2 position = rotated + in_offset;
            
            // 宽高比校正
            position.y *= u_y_scale;
            
            gl_Position = vec4(position, 0.0, 1.0);
            
            // 计算UV
            v_uv = in_uv_base * vec2(
                in_uv_rect.z - in_uv_rect.x,
                in_uv_rect.w - in_uv_rect.y
            ) + in_uv_rect.xy;
        }
        """
        
        fragment_shader = """
        #version 330
        
        uniform sampler2D u_texture;
        
        in vec2 v_uv;
        out vec4 f_color;
        
        void main() {
            f_color = texture(u_texture, v_uv);
        }
        """
        
        self.program = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        
        # 设置uniform
        self.program['u_texture'].value = 0
        self.program['u_y_scale'].value = self.config.y_scale_factor
    
    def _init_buffers(self):
        """初始化缓冲区"""
        max_bullets = self.config.render.max_bullets
        
        # 顶点数据（单位正方形）
        vertices = np.array([
            -0.5,  0.5, 0.0, 0.0,  # 左上
            -0.5, -0.5, 0.0, 1.0,  # 左下
             0.5,  0.5, 1.0, 0.0,  # 右上
             0.5,  0.5, 1.0, 0.0,  # 右上
            -0.5, -0.5, 0.0, 1.0,  # 左下
             0.5, -0.5, 1.0, 1.0,  # 右下
        ], dtype='f4')
        
        self.vertex_vbo = self.ctx.buffer(vertices.tobytes())
        
        # 实例数据缓冲区（预分配）
        self.position_vbo = self.ctx.buffer(reserve=max_bullets * 2 * 4)
        self.angle_vbo = self.ctx.buffer(reserve=max_bullets * 1 * 4)
        self.uv_vbo = self.ctx.buffer(reserve=max_bullets * 4 * 4)
        self.scale_vbo = self.ctx.buffer(reserve=max_bullets * 2 * 4)
        
        # 创建VAO
        self.vao = self.ctx.vertex_array(
            self.program,
            [
                (self.vertex_vbo, '2f 2f', 'in_vert', 'in_uv_base'),
                (self.position_vbo, '2f/i', 'in_offset'),
                (self.angle_vbo, '1f/i', 'in_angle'),
                (self.uv_vbo, '4f/i', 'in_uv_rect'),
                (self.scale_vbo, '2f/i', 'in_scale'),
            ]
        )
    
    def render_from_pool(self, bullet_pool):
        """
        从OptimizedBulletPool渲染子弹
        
        Args:
            bullet_pool: OptimizedBulletPool实例
        """
        # 获取预处理的渲染数据
        render_batches = bullet_pool.prepare_render_data_sorted()
        
        if not render_batches:
            return
        
        # 按批次渲染
        for batch in render_batches:
            self._render_batch(batch)
    
    def render_from_data(self, render_data: Dict[int, Dict]):
        """
        从渲染数据字典渲染
        
        Args:
            render_data: bullet_pool.prepare_render_data() 的返回值
        """
        if not render_data:
            return
        
        for tex_idx, data in render_data.items():
            texture_path = self.sprite_registry.get_texture_path(tex_idx)
            if texture_path in self.textures:
                self._render_batch_data(
                    self.textures[texture_path],
                    data['positions'],
                    data['angles'],
                    data['uvs'],
                    data['scales'],
                    data['count']
                )
    
    def _render_batch(self, batch: Dict):
        """渲染单个批次"""
        texture_path = batch.get('texture_path', '')
        if texture_path not in self.textures:
            return
        
        texture = self.textures[texture_path]
        self._render_batch_data(
            texture,
            batch['positions'],
            batch['angles'],
            batch['uvs'],
            batch['scales'],
            batch['count']
        )
    
    def _render_batch_data(
        self,
        texture: moderngl.Texture,
        positions: np.ndarray,
        angles: np.ndarray,
        uvs: np.ndarray,
        scales: np.ndarray,
        count: int
    ):
        """
        渲染批次数据（核心渲染函数）
        
        所有数据都是预计算好的numpy数组，直接上传GPU
        """
        if count == 0:
            return
        
        # 绑定纹理
        texture.use(0)
        
        # 上传数据到GPU（连续内存，高效）
        self.position_vbo.write(positions.tobytes())
        self.angle_vbo.write(angles.tobytes())
        self.uv_vbo.write(uvs.tobytes())
        self.scale_vbo.write(scales.tobytes())
        
        # 实例化渲染
        self.vao.render(moderngl.TRIANGLES, instances=count)
    
    def render_legacy(self, bullet_pool, sprite_manager, sprite_uv_map: Dict):
        """
        兼容旧版BulletPool的渲染方法
        
        Args:
            bullet_pool: 旧版BulletPool实例
            sprite_manager: SpriteManager实例
            sprite_uv_map: sprite_id到UV的映射
        """
        positions, colors, angles, sprite_ids = bullet_pool.get_active_bullets()
        count = len(positions)
        
        if count == 0:
            return
        
        # 按纹理分组
        texture_groups: Dict[str, List[int]] = {}
        
        for i in range(count):
            sprite_id = sprite_ids[i]
            texture_path = sprite_manager.get_sprite_texture_path(sprite_id)
            if not texture_path:
                texture_path = next(iter(self.textures.keys()), None)
            
            if texture_path:
                if texture_path not in texture_groups:
                    texture_groups[texture_path] = []
                texture_groups[texture_path].append(i)
        
        # 渲染每组
        scale_factor = self.config.pixel_to_ndc_scale
        default_size = self.config.render.default_sprite_size
        
        for texture_path, indices in texture_groups.items():
            if texture_path not in self.textures:
                continue
            
            n = len(indices)
            batch_positions = np.zeros((n, 2), dtype='f4')
            batch_angles = np.zeros(n, dtype='f4')
            batch_uvs = np.zeros((n, 4), dtype='f4')
            batch_scales = np.zeros((n, 2), dtype='f4')
            
            for j, i in enumerate(indices):
                batch_positions[j] = positions[i]
                batch_angles[j] = angles[i]
                
                sprite_id = sprite_ids[i]
                if sprite_id in sprite_uv_map:
                    batch_uvs[j] = sprite_uv_map[sprite_id]
                else:
                    batch_uvs[j] = [0.0, 0.0, 1.0, 1.0]
                
                sprite_data = sprite_manager.get_sprite(sprite_id)
                if sprite_data and 'rect' in sprite_data:
                    w = sprite_data['rect'][2] * scale_factor
                    h = sprite_data['rect'][3] * scale_factor
                    batch_scales[j] = [w, h]
                else:
                    batch_scales[j] = [
                        default_size * scale_factor,
                        default_size * scale_factor
                    ]
            
            self._render_batch_data(
                self.textures[texture_path],
                batch_positions,
                batch_angles,
                batch_uvs,
                batch_scales,
                n
            )
    
    def cleanup(self):
        """清理资源"""
        if hasattr(self, 'vao') and self.vao:
            self.vao.release()
        if hasattr(self, 'vertex_vbo') and self.vertex_vbo:
            self.vertex_vbo.release()
        if hasattr(self, 'position_vbo') and self.position_vbo:
            self.position_vbo.release()
        if hasattr(self, 'angle_vbo') and self.angle_vbo:
            self.angle_vbo.release()
        if hasattr(self, 'uv_vbo') and self.uv_vbo:
            self.uv_vbo.release()
        if hasattr(self, 'scale_vbo') and self.scale_vbo:
            self.scale_vbo.release()

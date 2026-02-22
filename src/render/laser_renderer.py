"""
激光渲染器 - 基于纹理图集的OpenGL渲染
使用三段式渲染（头/身/尾），从纹理图集中裁剪子图

渲染原理：
1. 激光纹理是一张包含16种颜色的图集(256x256)
2. 每行高度16像素，代表一种颜色
3. 每行分3段：头部(l1)、身体(l2)、尾部(l3)
4. 渲染时将各段缩放到实际的激光长度
"""
import moderngl
import numpy as np
import math
from typing import List, Dict, Optional, Tuple
from ..core.image_loader import load_image_surface, SoftwareSurface
from ..game.laser import Laser, BentLaser, get_laser_texture_data


class LaserRenderer:
    """激光渲染器 - 支持纹理图集"""
    
    def __init__(self, ctx: moderngl.Context, base_size: tuple):
        """
        初始化激光渲染器
        
        Args:
            ctx: ModernGL上下文
            base_size: 基础窗口尺寸 (width, height)
        """
        self.ctx = ctx
        self.base_size = base_size
        
        # 纹理缓存
        self.textures: Dict[str, moderngl.Texture] = {}
        
        # 初始化着色器
        self._init_shader()
    
    def _init_shader(self):
        """初始化着色器（支持纹理）"""
        vertex_shader = """
        #version 330
        
        in vec2 in_vert;
        in vec2 in_texcoord;
        in vec4 in_color;
        
        out vec2 v_texcoord;
        out vec4 v_color;
        
        uniform vec2 u_resolution;
        
        void main() {
            // 将像素坐标转换为NDC坐标
            vec2 ndc = (in_vert / u_resolution) * 2.0 - 1.0;
            ndc.y = -ndc.y;  // Y轴翻转
            gl_Position = vec4(ndc, 0.0, 1.0);
            v_texcoord = in_texcoord;
            v_color = in_color;
        }
        """
        
        fragment_shader = """
        #version 330
        
        in vec2 v_texcoord;
        in vec4 v_color;
        
        out vec4 f_color;
        
        uniform sampler2D u_texture;
        uniform int u_use_texture;
        
        void main() {
            if (u_use_texture == 1) {
                vec4 tex_color = texture(u_texture, v_texcoord);
                f_color = tex_color * v_color;
            } else {
                f_color = v_color;
            }
        }
        """
        
        self.program = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        
        # 设置uniform
        self.program['u_resolution'].value = self.base_size
        self.program['u_use_texture'].value = 1
        
        # 预分配VBO（顶点、纹理坐标、颜色）
        self.vbo_vert = self.ctx.buffer(reserve=50000 * 2 * 4)
        self.vbo_texcoord = self.ctx.buffer(reserve=50000 * 2 * 4)
        self.vbo_color = self.ctx.buffer(reserve=50000 * 4 * 4)
        
        self.vao = self.ctx.vertex_array(
            self.program,
            [
                (self.vbo_vert, '2f', 'in_vert'),
                (self.vbo_texcoord, '2f', 'in_texcoord'),
                (self.vbo_color, '4f', 'in_color'),
            ]
        )
    
    def load_texture(self, texture_path: str, 
                     asset_manager = None) -> Optional[moderngl.Texture]:
        """
        加载纹理到GPU
        
        Args:
            texture_path: 纹理文件路径
            asset_manager: 可选的TextureAssetManager实例
        """
        if texture_path in self.textures:
            return self.textures[texture_path]
        
        try:
            surface = None
            
            # 尝试从资产管理器获取
            if asset_manager:
                surface = asset_manager.get_texture(texture_path)
            
            # 否则直接加载
            if surface is None:
                surface = load_image_surface(texture_path)
            
            surface = SoftwareSurface.flip(surface, False, True)
            surface = surface.convert_alpha()
            
            # 获取图片数据
            width, height = surface.get_size()
            data = surface.to_bytes('RGBA', flip_y=True)
            
            # 创建ModernGL纹理
            texture = self.ctx.texture((width, height), 4, data)
            texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            texture.repeat_x = False
            texture.repeat_y = False
            
            self.textures[texture_path] = texture
            print(f"已加载激光纹理: {texture_path}")
            return texture
            
        except Exception as e:
            print(f"加载激光纹理失败 {texture_path}: {e}")
            return None
    
    def render_lasers(self, lasers: List[Laser]):
        """渲染所有直线激光"""
        if not lasers:
            return
        
        # 按纹理分组
        texture_groups: Dict[str, List[Laser]] = {}
        for laser in lasers:
            render_data = laser.get_render_data()
            if not render_data:
                continue
            
            tex_rects = render_data.get('texture_rects')
            if tex_rects:
                tex_file = tex_rects.get('texture_file', '')
                if tex_file not in texture_groups:
                    texture_groups[tex_file] = []
                texture_groups[tex_file].append(render_data)
            else:
                # 没有纹理数据，使用纯色渲染
                if '' not in texture_groups:
                    texture_groups[''] = []
                texture_groups[''].append(render_data)
        
        # 按纹理批量渲染
        for tex_path, group_data in texture_groups.items():
            if tex_path:
                texture = self.load_texture(tex_path)
                if texture:
                    texture.use(0)
                    self.program['u_use_texture'].value = 1
                else:
                    self.program['u_use_texture'].value = 0
            else:
                self.program['u_use_texture'].value = 0
            
            self._render_laser_batch(group_data)
    
    def _render_laser_batch(self, laser_data_list: List[Dict]):
        """批量渲染激光"""
        vertices = []
        texcoords = []
        colors = []
        
        for data in laser_data_list:
            self._build_laser_geometry(data, vertices, texcoords, colors)
        
        if not vertices:
            return
        
        # 写入VBO
        vert_array = np.array(vertices, dtype='f4')
        texcoord_array = np.array(texcoords, dtype='f4')
        color_array = np.array(colors, dtype='f4')
        
        self.vbo_vert.write(vert_array.tobytes())
        self.vbo_texcoord.write(texcoord_array.tobytes())
        self.vbo_color.write(color_array.tobytes())
        
        # 启用混合
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        
        # 渲染
        vertex_count = len(vertices) // 2
        self.vao.render(moderngl.TRIANGLES, vertices=vertex_count)
    
    def _build_laser_geometry(self, data: Dict, 
                              vertices: list, texcoords: list, colors: list):
        """
        构建单个激光的几何体（三段式）
        
        参考LuaSTG的render方法：
        - 头部从起点开始，长度l1，纹理按头部宽度缩放
        - 身体从l1处开始，长度l2
        - 尾部从l1+l2处开始，长度l3
        - 纹理锚点在左边中心
        """
        x = data['x']
        y = data['y']
        angle = math.radians(data['angle'])
        l1 = data['l1']
        l2 = data['l2']
        l3 = data['l3']
        width = data['width']
        alpha = data['alpha']
        
        tex_rects = data.get('texture_rects')
        
        # 计算方向向量
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        
        # 垂直方向
        perp_x = -sin_a
        perp_y = cos_a
        
        # 颜色（白色 * alpha，让纹理颜色显示）
        color = (1.0, 1.0, 1.0, alpha)
        
        # 获取纹理尺寸用于UV计算
        if tex_rects:
            tex_file = tex_rects.get('texture_file', '')
            texture = self.textures.get(tex_file)
            if texture:
                tex_width, tex_height = texture.size
            else:
                tex_width, tex_height = 256, 256
            
            # 根据纹理数据计算实际宽度缩放
            # LuaSTG: w = (self.w / 2) / data[6] * data[4] / data[6]
            # data[4] = h (row_height / 2), data[6] = h - margin
            row_h = tex_rects.get('row_height', 16)
            margin = tex_rects.get('margin', 1)
            half_h = row_h / 2
            effective_h = half_h - margin
            
            # 计算实际渲染宽度
            if effective_h > 0:
                render_width = (width / 2) / effective_h * half_h
            else:
                render_width = width / 2
        else:
            tex_width, tex_height = 256, 256
            render_width = width / 2
        
        half_width = render_width
        
        # 当前绘制位置
        curr_x = x
        curr_y = y
        
        # ===== 渲染头部 =====
        if l1 > 0 and tex_rects:
            head_rect = tex_rects.get('head_rect', (0, 0, 64, 16))
            hx, hy, hw, hh = head_rect
            
            # UV坐标
            u0 = hx / tex_width
            v0 = hy / tex_height
            u1 = (hx + hw) / tex_width
            v1 = (hy + hh) / tex_height
            
            # 头部四角
            end_x = curr_x + l1 * cos_a
            end_y = curr_y + l1 * sin_a
            
            p1 = (curr_x + perp_x * half_width, curr_y + perp_y * half_width)
            p2 = (curr_x - perp_x * half_width, curr_y - perp_y * half_width)
            p3 = (end_x + perp_x * half_width, end_y + perp_y * half_width)
            p4 = (end_x - perp_x * half_width, end_y - perp_y * half_width)
            
            # 三角形1
            vertices.extend([p1[0], p1[1], p2[0], p2[1], p3[0], p3[1]])
            texcoords.extend([u0, v0, u0, v1, u1, v0])
            colors.extend(color * 3)
            
            # 三角形2
            vertices.extend([p3[0], p3[1], p2[0], p2[1], p4[0], p4[1]])
            texcoords.extend([u1, v0, u0, v1, u1, v1])
            colors.extend(color * 3)
            
            curr_x = end_x
            curr_y = end_y
        
        # ===== 渲染身体 =====
        if l2 > 0 and tex_rects:
            body_rect = tex_rects.get('body_rect', (64, 0, 128, 16))
            bx, by, bw, bh = body_rect
            
            u0 = bx / tex_width
            v0 = by / tex_height
            u1 = (bx + bw) / tex_width
            v1 = (by + bh) / tex_height
            
            end_x = curr_x + l2 * cos_a
            end_y = curr_y + l2 * sin_a
            
            p1 = (curr_x + perp_x * half_width, curr_y + perp_y * half_width)
            p2 = (curr_x - perp_x * half_width, curr_y - perp_y * half_width)
            p3 = (end_x + perp_x * half_width, end_y + perp_y * half_width)
            p4 = (end_x - perp_x * half_width, end_y - perp_y * half_width)
            
            vertices.extend([p1[0], p1[1], p2[0], p2[1], p3[0], p3[1]])
            texcoords.extend([u0, v0, u0, v1, u1, v0])
            colors.extend(color * 3)
            
            vertices.extend([p3[0], p3[1], p2[0], p2[1], p4[0], p4[1]])
            texcoords.extend([u1, v0, u0, v1, u1, v1])
            colors.extend(color * 3)
            
            curr_x = end_x
            curr_y = end_y
        
        # ===== 渲染尾部 =====
        if l3 > 0 and tex_rects:
            tail_rect = tex_rects.get('tail_rect', (192, 0, 64, 16))
            tx, ty, tw, th = tail_rect
            
            u0 = tx / tex_width
            v0 = ty / tex_height
            u1 = (tx + tw) / tex_width
            v1 = (ty + th) / tex_height
            
            end_x = curr_x + l3 * cos_a
            end_y = curr_y + l3 * sin_a
            
            p1 = (curr_x + perp_x * half_width, curr_y + perp_y * half_width)
            p2 = (curr_x - perp_x * half_width, curr_y - perp_y * half_width)
            p3 = (end_x + perp_x * half_width, end_y + perp_y * half_width)
            p4 = (end_x - perp_x * half_width, end_y - perp_y * half_width)
            
            vertices.extend([p1[0], p1[1], p2[0], p2[1], p3[0], p3[1]])
            texcoords.extend([u0, v0, u0, v1, u1, v0])
            colors.extend(color * 3)
            
            vertices.extend([p3[0], p3[1], p2[0], p2[1], p4[0], p4[1]])
            texcoords.extend([u1, v0, u0, v1, u1, v1])
            colors.extend(color * 3)
    
    def render_bent_lasers(self, bent_lasers: List[BentLaser]):
        """渲染所有曲线激光"""
        if not bent_lasers:
            return
        
        # 按纹理分组
        texture_groups: Dict[str, List[Dict]] = {}
        
        for laser in bent_lasers:
            render_data = laser.get_render_data()
            if not render_data:
                continue
            
            tex_rect = render_data.get('texture_rect')
            if tex_rect:
                tex_file = tex_rect.get('texture_file', '')
            else:
                tex_file = ''
            
            if tex_file not in texture_groups:
                texture_groups[tex_file] = []
            texture_groups[tex_file].append(render_data)
        
        # 批量渲染
        for tex_path, group_data in texture_groups.items():
            if tex_path:
                texture = self.load_texture(tex_path)
                if texture:
                    texture.use(0)
                    self.program['u_use_texture'].value = 1
                else:
                    self.program['u_use_texture'].value = 0
            else:
                self.program['u_use_texture'].value = 0
            
            self._render_bent_laser_batch(group_data)
    
    def _render_bent_laser_batch(self, laser_data_list: List[Dict]):
        """批量渲染曲线激光"""
        vertices = []
        texcoords = []
        colors = []
        
        for data in laser_data_list:
            self._build_bent_laser_geometry(data, vertices, texcoords, colors)
        
        if not vertices:
            return
        
        vert_array = np.array(vertices, dtype='f4')
        texcoord_array = np.array(texcoords, dtype='f4')
        color_array = np.array(colors, dtype='f4')
        
        self.vbo_vert.write(vert_array.tobytes())
        self.vbo_texcoord.write(texcoord_array.tobytes())
        self.vbo_color.write(color_array.tobytes())
        
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        
        vertex_count = len(vertices) // 2
        self.vao.render(moderngl.TRIANGLES, vertices=vertex_count)
    
    def _build_bent_laser_geometry(self, data: Dict,
                                   vertices: list, texcoords: list, colors: list):
        """构建曲线激光的几何体"""
        path_x = data['path_x']
        path_y = data['path_y']
        width = data['width']
        alpha = data['alpha']
        
        tex_rect = data.get('texture_rect')
        
        if tex_rect:
            tex_file = tex_rect.get('texture_file', '')
            texture = self.textures.get(tex_file)
            if texture:
                tex_width, tex_height = texture.size
            else:
                tex_width, tex_height = 256, 256
            
            rect = tex_rect.get('rect', (0, 0, 16, 16))
            rx, ry, rw, rh = rect
            
            u0 = rx / tex_width
            v0 = ry / tex_height
            u1 = (rx + rw) / tex_width
            v1 = (ry + rh) / tex_height
        else:
            u0, v0, u1, v1 = 0, 0, 1, 1
        
        color = (1.0, 1.0, 1.0, alpha)
        half_width = width / 2
        path_length = len(path_x)
        
        for i in range(path_length - 1):
            x1, y1 = path_x[i], path_y[i]
            x2, y2 = path_x[i + 1], path_y[i + 1]
            
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx * dx + dy * dy)
            
            if length < 0.01:
                continue
            
            dx /= length
            dy /= length
            
            perp_x = -dy
            perp_y = dx
            
            p1 = (x1 + perp_x * half_width, y1 + perp_y * half_width)
            p2 = (x1 - perp_x * half_width, y1 - perp_y * half_width)
            p3 = (x2 + perp_x * half_width, y2 + perp_y * half_width)
            p4 = (x2 - perp_x * half_width, y2 - perp_y * half_width)
            
            vertices.extend([p1[0], p1[1], p2[0], p2[1], p3[0], p3[1]])
            texcoords.extend([u0, v0, u0, v1, u1, v0])
            colors.extend(color * 3)
            
            vertices.extend([p3[0], p3[1], p2[0], p2[1], p4[0], p4[1]])
            texcoords.extend([u1, v0, u0, v1, u1, v1])
            colors.extend(color * 3)
    
    def cleanup(self):
        """清理资源"""
        for texture in self.textures.values():
            texture.release()
        self.textures.clear()
        
        self.vbo_vert.release()
        self.vbo_texcoord.release()
        self.vbo_color.release()
        self.vao.release()
        self.program.release()

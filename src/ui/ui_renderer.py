"""
UI渲染器 - 使用ModernGL渲染UI元素

支持:
- 位图字体文本渲染
- 矩形条（HP条、Power条等）
- 精灵图标
"""

import moderngl
import numpy as np
import pygame
from typing import Dict, List, Optional
from .bitmap_font import BitmapFont, get_font_manager


class UIRenderer:
    """UI元素的OpenGL渲染器"""
    
    def __init__(self, ctx: moderngl.Context, screen_width: int = 384, screen_height: int = 448):
        """
        初始化UI渲染器
        
        Args:
            ctx: ModernGL上下文
            screen_width: 屏幕宽度（像素）
            screen_height: 屏幕高度（像素）
        """
        self.ctx = ctx
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # 字体纹理缓存 {font_name: texture}
        self.font_textures: Dict[str, moderngl.Texture] = {}
        
        # 初始化着色器
        self._init_text_shader()
        self._init_rect_shader()
        
        # 字体管理器
        self.font_manager = get_font_manager()
    
    def _init_text_shader(self):
        """初始化文本渲染着色器"""
        vertex_shader = """
        #version 330
        
        uniform vec2 u_screen_size;
        
        in vec2 in_position;  // 屏幕像素坐标
        in vec2 in_uv;
        in vec4 in_color;
        
        out vec2 v_uv;
        out vec4 v_color;
        
        void main() {
            // 将像素坐标转换为NDC [-1, 1]
            vec2 ndc = (in_position / u_screen_size) * 2.0 - 1.0;
            ndc.y = -ndc.y;  // Y轴翻转（屏幕坐标系原点在左上）
            gl_Position = vec4(ndc, 0.0, 1.0);
            v_uv = in_uv;
            v_color = in_color;
        }
        """
        
        fragment_shader = """
        #version 330
        
        uniform sampler2D u_texture;
        
        in vec2 v_uv;
        in vec4 v_color;
        
        out vec4 f_color;
        
        void main() {
            vec4 tex_color = texture(u_texture, v_uv);
            f_color = tex_color * v_color;
        }
        """
        
        self.text_program = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        self.text_program['u_texture'].value = 0
        self.text_program['u_screen_size'].value = (self.screen_width, self.screen_height)
        
        # 动态顶点缓冲区（足够渲染大量字符）
        # 每个字符6个顶点，每个顶点8个float (position.xy, uv.xy, color.rgba)
        self.text_vbo = self.ctx.buffer(reserve=4096 * 6 * 8 * 4)
        
        self.text_vao = self.ctx.vertex_array(
            self.text_program,
            [(self.text_vbo, '2f 2f 4f', 'in_position', 'in_uv', 'in_color')]
        )
    
    def _init_rect_shader(self):
        """初始化矩形渲染着色器（用于条形图等）"""
        vertex_shader = """
        #version 330
        
        uniform vec2 u_screen_size;
        
        in vec2 in_position;
        in vec4 in_color;
        
        out vec4 v_color;
        
        void main() {
            vec2 ndc = (in_position / u_screen_size) * 2.0 - 1.0;
            ndc.y = -ndc.y;
            gl_Position = vec4(ndc, 0.0, 1.0);
            v_color = in_color;
        }
        """
        
        fragment_shader = """
        #version 330
        
        in vec4 v_color;
        out vec4 f_color;
        
        void main() {
            f_color = v_color;
        }
        """
        
        self.rect_program = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        self.rect_program['u_screen_size'].value = (self.screen_width, self.screen_height)
        
        # 矩形顶点缓冲区
        self.rect_vbo = self.ctx.buffer(reserve=256 * 6 * 6 * 4)  # position.xy, color.rgba
        
        self.rect_vao = self.ctx.vertex_array(
            self.rect_program,
            [(self.rect_vbo, '2f 4f', 'in_position', 'in_color')]
        )
    
    def load_font_texture(self, font_name: str) -> bool:
        """
        加载字体纹理到GPU
        
        Args:
            font_name: 字体名称
            
        Returns:
            bool: 是否成功
        """
        font = self.font_manager.get_font(font_name)
        if font is None or font.texture_surface is None:
            return False
        
        if font_name in self.font_textures:
            return True  # 已加载
        
        try:
            img = font.texture_surface
            texture = self.ctx.texture(
                img.get_size(), 4,
                pygame.image.tobytes(img, "RGBA", True)
            )
            texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
            self.font_textures[font_name] = texture
            print(f"已加载字体纹理到GPU: {font_name}")
            return True
        except Exception as e:
            print(f"加载字体纹理失败 {font_name}: {e}")
            return False
    
    def render_text(self, text: str, x: float, y: float, 
                    font_name: str = 'score', scale: float = 1.0,
                    color: tuple = (255, 255, 255), alpha: float = 1.0,
                    align: str = 'left') -> None:
        """
        渲染文本
        
        Args:
            text: 要渲染的文本
            x, y: 屏幕像素坐标（左上角）
            font_name: 字体名称
            scale: 缩放比例
            color: RGB颜色 (r, g, b)，0-255
            alpha: 透明度 0.0-1.0
            align: 对齐方式 'left', 'center', 'right'
        """
        font = self.font_manager.get_font(font_name)
        if font is None:
            return
        
        # 确保字体纹理已加载
        if font_name not in self.font_textures:
            if not self.load_font_texture(font_name):
                return
        
        # 计算对齐偏移
        if align == 'center':
            text_width = font.get_text_width(text, scale)
            x -= text_width / 2
        elif align == 'right':
            text_width = font.get_text_width(text, scale)
            x -= text_width
        
        # 构建顶点数据
        vertices = []
        r, g, b = color[0] / 255.0, color[1] / 255.0, color[2] / 255.0
        
        tex_h = font.texture_surface.get_height()
        cursor_x = x
        
        for char in text:
            char_data = font.get_char_data(char)
            if char_data is None:
                continue
            
            # 字符尺寸（缩放后）
            char_w = char_data['width'] * scale
            char_h = char_data['height'] * scale
            
            # UV坐标（注意：OpenGL纹理原点在左下，但我们使用tobytes的flip）
            uv = font.get_char_uv(char)
            if uv is None:
                continue
            u0, v0, u1, v1 = uv
            
            # 翻转V坐标（因为tobytes使用flip=True）
            v0, v1 = 1.0 - v0, 1.0 - v1
            
            # 构建四边形的6个顶点（两个三角形）
            # 左上
            vertices.extend([cursor_x, y, u0, v0, r, g, b, alpha])
            # 左下
            vertices.extend([cursor_x, y + char_h, u0, v1, r, g, b, alpha])
            # 右上
            vertices.extend([cursor_x + char_w, y, u1, v0, r, g, b, alpha])
            # 右上
            vertices.extend([cursor_x + char_w, y, u1, v0, r, g, b, alpha])
            # 左下
            vertices.extend([cursor_x, y + char_h, u0, v1, r, g, b, alpha])
            # 右下
            vertices.extend([cursor_x + char_w, y + char_h, u1, v1, r, g, b, alpha])
            
            # 移动光标
            cursor_x += (char_data['width'] + char_data['xoffset']) * scale
        
        if not vertices:
            return
        
        # 上传顶点数据并渲染
        vertex_data = np.array(vertices, dtype='f4')
        self.text_vbo.write(vertex_data.tobytes())
        
        self.font_textures[font_name].use(0)
        self.text_vao.render(moderngl.TRIANGLES, vertices=len(vertices) // 8)
    
    def render_rect(self, x: float, y: float, width: float, height: float,
                    color: tuple = (255, 255, 255), alpha: float = 1.0) -> None:
        """
        渲染填充矩形
        
        Args:
            x, y: 左上角像素坐标
            width, height: 尺寸
            color: RGB颜色
            alpha: 透明度
        """
        r, g, b = color[0] / 255.0, color[1] / 255.0, color[2] / 255.0
        
        vertices = [
            # 三角形1
            x, y, r, g, b, alpha,
            x, y + height, r, g, b, alpha,
            x + width, y, r, g, b, alpha,
            # 三角形2
            x + width, y, r, g, b, alpha,
            x, y + height, r, g, b, alpha,
            x + width, y + height, r, g, b, alpha,
        ]
        
        vertex_data = np.array(vertices, dtype='f4')
        self.rect_vbo.write(vertex_data.tobytes())
        self.rect_vao.render(moderngl.TRIANGLES, vertices=6)
    
    def render_bar(self, x: float, y: float, width: float, height: float,
                   value: float, color_bg: tuple = (32, 32, 32),
                   color_fill: tuple = (255, 255, 255), alpha: float = 1.0) -> None:
        """
        渲染条形图（如HP条、Power条）
        
        Args:
            x, y: 左上角坐标
            width, height: 总尺寸
            value: 填充比例 0.0-1.0
            color_bg: 背景颜色
            color_fill: 填充颜色
            alpha: 透明度
        """
        # 渲染背景
        self.render_rect(x, y, width, height, color_bg, alpha)
        
        # 渲染填充部分
        fill_width = width * max(0.0, min(1.0, value))
        if fill_width > 0:
            self.render_rect(x, y, fill_width, height, color_fill, alpha)
    
    def render_hud(self, hud) -> None:
        """
        渲染完整的HUD
        
        Args:
            hud: HUD对象
        """
        elements = hud.get_render_elements()
        
        for elem in elements:
            elem_type = elem.get('type', '')
            
            if elem_type == 'text':
                self.render_text(
                    text=elem['text'],
                    x=elem['position'][0],
                    y=elem['position'][1],
                    font_name=elem.get('font', 'score'),
                    scale=elem.get('scale', 1.0),
                    color=elem.get('color', (255, 255, 255)),
                    alpha=elem.get('alpha', 1.0),
                    align=elem.get('align', 'left')
                )
            elif elem_type == 'bar':
                self.render_bar(
                    x=elem['position'][0],
                    y=elem['position'][1],
                    width=elem['width'],
                    height=elem['height'],
                    value=elem['value'],
                    color_bg=elem.get('color_bg', (32, 32, 32)),
                    color_fill=elem.get('color_fill', (255, 255, 255)),
                    alpha=elem.get('alpha', 1.0)
                )
            elif elem_type == 'rect':
                self.render_rect(
                    x=elem['position'][0],
                    y=elem['position'][1],
                    width=elem['width'],
                    height=elem['height'],
                    color=elem.get('color', (0, 0, 0)),
                    alpha=elem.get('alpha', 0.5)
                )
    
    def cleanup(self) -> None:
        """清理资源"""
        # ModernGL会自动管理资源，但可以显式释放纹理
        self.font_textures.clear()

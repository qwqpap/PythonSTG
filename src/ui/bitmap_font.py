"""
位图字体类 - 解析和渲染HGE格式位图字体

HGE Font格式:
[HGEFONT]
Bitmap=score.png
Char="0",x,y,width,height,xoffset,yoffset
"""

import os
import re
import pygame


class BitmapFont:
    """HGE格式位图字体解析和渲染"""
    
    def __init__(self):
        """初始化字体"""
        self.texture_path = None
        self.texture_surface = None
        self.chars = {}  # {char: {'x': x, 'y': y, 'width': w, 'height': h, 'xoffset': xo, 'yoffset': yo}}
        self.line_height = 0
        self.name = ""
    
    def load(self, fnt_path: str) -> bool:
        """
        加载HGE格式的字体文件
        
        Args:
            fnt_path: .fnt文件路径
            
        Returns:
            bool: 是否加载成功
        """
        if not os.path.exists(fnt_path):
            print(f"字体文件不存在: {fnt_path}")
            return False
        
        self.name = os.path.splitext(os.path.basename(fnt_path))[0]
        font_dir = os.path.dirname(fnt_path)
        
        try:
            with open(fnt_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # 尝试其他编码
            with open(fnt_path, 'r', encoding='gbk') as f:
                content = f.read()
        
        # 解析Bitmap行
        bitmap_match = re.search(r'Bitmap\s*=\s*(\S+)', content)
        if bitmap_match:
            bitmap_name = bitmap_match.group(1)
            self.texture_path = os.path.join(font_dir, bitmap_name)
            
            if os.path.exists(self.texture_path):
                self.texture_surface = pygame.image.load(self.texture_path).convert_alpha()
                print(f"已加载字体纹理: {self.texture_path}")
            else:
                print(f"字体纹理不存在: {self.texture_path}")
                return False
        else:
            print(f"字体文件格式错误，缺少Bitmap定义: {fnt_path}")
            return False
        
        # 解析Char行
        # 格式: Char="0",x,y,width,height,xoffset,yoffset
        char_pattern = re.compile(r'Char\s*=\s*"(.)",\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(-?\d+),\s*(-?\d+)')
        
        for match in char_pattern.finditer(content):
            char = match.group(1)
            x = int(match.group(2))
            y = int(match.group(3))
            width = int(match.group(4))
            height = int(match.group(5))
            xoffset = int(match.group(6))
            yoffset = int(match.group(7))
            
            self.chars[char] = {
                'x': x,
                'y': y,
                'width': width,
                'height': height,
                'xoffset': xoffset,
                'yoffset': yoffset
            }
            
            # 更新行高
            if height > self.line_height:
                self.line_height = height
        
        print(f"已加载字体 '{self.name}': {len(self.chars)} 个字符, 行高 {self.line_height}")
        return True
    
    def get_char_rect(self, char: str) -> tuple:
        """
        获取字符在纹理中的矩形区域
        
        Args:
            char: 字符
            
        Returns:
            tuple: (x, y, width, height) 或 None
        """
        if char in self.chars:
            c = self.chars[char]
            return (c['x'], c['y'], c['width'], c['height'])
        return None
    
    def get_char_uv(self, char: str) -> tuple:
        """
        获取字符的UV坐标（归一化）
        
        Args:
            char: 字符
            
        Returns:
            tuple: (u_left, v_top, u_right, v_bottom) 或 None
        """
        if char not in self.chars or self.texture_surface is None:
            return None
        
        c = self.chars[char]
        tex_w, tex_h = self.texture_surface.get_size()
        
        u_left = c['x'] / tex_w
        v_top = c['y'] / tex_h
        u_right = (c['x'] + c['width']) / tex_w
        v_bottom = (c['y'] + c['height']) / tex_h
        
        return (u_left, v_top, u_right, v_bottom)
    
    def get_text_width(self, text: str, scale: float = 1.0) -> float:
        """
        计算文本渲染宽度
        
        Args:
            text: 文本字符串
            scale: 缩放比例
            
        Returns:
            float: 文本宽度（像素）
        """
        width = 0
        for char in text:
            if char in self.chars:
                c = self.chars[char]
                # 使用宽度 + xoffset 作为字符间距
                width += (c['width'] + c['xoffset']) * scale
        return width
    
    def get_text_height(self, scale: float = 1.0) -> float:
        """获取文本高度"""
        return self.line_height * scale
    
    def get_char_data(self, char: str) -> dict:
        """
        获取字符的完整数据
        
        Args:
            char: 字符
            
        Returns:
            dict: 字符数据 或 None
        """
        return self.chars.get(char, None)
    
    def render_to_surface(self, text: str, scale: float = 1.0) -> pygame.Surface:
        """
        将文本渲染到pygame Surface（用于调试）
        
        Args:
            text: 文本字符串
            scale: 缩放比例
            
        Returns:
            pygame.Surface: 渲染后的表面
        """
        if self.texture_surface is None:
            return None
        
        # 计算总宽度
        total_width = int(self.get_text_width(text, scale))
        total_height = int(self.line_height * scale)
        
        # 创建透明表面
        surface = pygame.Surface((total_width, total_height), pygame.SRCALPHA)
        
        x_cursor = 0
        for char in text:
            if char in self.chars:
                c = self.chars[char]
                # 从纹理中获取字符区域
                char_rect = pygame.Rect(c['x'], c['y'], c['width'], c['height'])
                char_surface = self.texture_surface.subsurface(char_rect)
                
                # 缩放
                if scale != 1.0:
                    new_size = (int(c['width'] * scale), int(c['height'] * scale))
                    char_surface = pygame.transform.scale(char_surface, new_size)
                
                # 绘制到目标表面
                surface.blit(char_surface, (x_cursor, 0))
                x_cursor += int((c['width'] + c['xoffset']) * scale)
        
        return surface


class FontManager:
    """字体管理器 - 管理多个字体"""
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.fonts = {}  # {font_name: BitmapFont}
    
    def load_font(self, name: str, fnt_path: str) -> bool:
        """
        加载字体
        
        Args:
            name: 字体名称
            fnt_path: .fnt文件路径
            
        Returns:
            bool: 是否成功
        """
        font = BitmapFont()
        if font.load(fnt_path):
            self.fonts[name] = font
            return True
        return False
    
    def get_font(self, name: str) -> BitmapFont:
        """获取字体"""
        return self.fonts.get(name, None)
    
    def load_default_fonts(self, font_dir: str) -> int:
        """
        加载目录下所有字体
        
        Args:
            font_dir: 字体目录
            
        Returns:
            int: 成功加载的字体数量
        """
        count = 0
        if not os.path.exists(font_dir):
            print(f"字体目录不存在: {font_dir}")
            return 0
        
        for filename in os.listdir(font_dir):
            if filename.endswith('.fnt'):
                name = os.path.splitext(filename)[0]
                fnt_path = os.path.join(font_dir, filename)
                if self.load_font(name, fnt_path):
                    count += 1
        
        print(f"已加载 {count} 个字体")
        return count


def get_font_manager() -> FontManager:
    """获取字体管理器单例"""
    return FontManager()

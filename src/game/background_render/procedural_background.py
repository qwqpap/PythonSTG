"""
程序化背景系统

用 Python 类来定义动态背景行为，替代 Lua 脚本
每个背景类实现 init/update/render 方法来控制渲染逻辑
"""

from typing import Dict, List, Tuple, Optional, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
import math

if TYPE_CHECKING:
    from .background_renderer import BackgroundRenderer


class BlendMode(Enum):
    """混合模式"""
    NORMAL = "normal"
    ADD = "add"
    MULTIPLY = "multiply"


@dataclass
class Quad3D:
    """3D 四边形顶点数据"""
    texture: str
    # 四个顶点 (x, y, z) - 左下、左上、右上、右下
    v0: Tuple[float, float, float]
    v1: Tuple[float, float, float]
    v2: Tuple[float, float, float]
    v3: Tuple[float, float, float]
    # UV 坐标
    uv: Tuple[float, float, float, float] = (0, 0, 1, 1)  # u0, v0, u1, v1
    # 渲染属性
    alpha: float = 1.0
    blend_mode: BlendMode = BlendMode.NORMAL


class ProceduralBackground:
    """
    程序化背景基类
    
    子类需要实现:
    - init(): 初始化，加载纹理，设置摄像机
    - update(dt): 每帧更新状态
    - render(): 提交渲染命令
    """
    
    # 背景名称（子类覆盖）
    name: str = "base"
    # 纹理资源基础路径
    asset_base: str = "assets/images/background"
    
    def __init__(self, renderer: 'BackgroundRenderer'):
        self.renderer = renderer
        self.time: float = 0.0
        self.textures: Dict[str, str] = {}  # name -> full_path
        self.quads: List[Quad3D] = []  # 每帧要渲染的四边形
        
        # 摄像机参数
        self.camera_eye: Tuple[float, float, float] = (0, 0, 1)
        self.camera_at: Tuple[float, float, float] = (0, 0, 0)
        self.camera_up: Tuple[float, float, float] = (0, 1, 0)
        self.camera_fovy: float = 0.8
        self.camera_z_near: float = 0.1
        self.camera_z_far: float = 10.0
        
        # 雾效参数
        self.fog_enabled: bool = False
        self.fog_color: Tuple[float, float, float, float] = (0, 0, 0, 1)
        self.fog_start: float = 0.0
        self.fog_end: float = 10.0
    
    def init(self):
        """初始化背景 - 子类实现"""
        pass
    
    def update(self, dt: float):
        """更新背景状态"""
        self.time += dt
    
    def render(self):
        """渲染背景 - 子类实现，调用 render_quad 等方法"""
        pass
    
    # ========== 辅助方法 ==========
    
    def load_texture(self, name: str, path: str) -> bool:
        """
        加载纹理
        
        Args:
            name: 纹理名称（用于引用）
            path: 相对于 asset_base 的路径
        """
        import os
        full_path = os.path.join(self.asset_base, path)
        if self.renderer.load_texture(full_path):
            self.textures[name] = full_path
            return True
        return False
    
    def set_camera(self, 
                   eye: Tuple[float, float, float] = None,
                   at: Tuple[float, float, float] = None,
                   up: Tuple[float, float, float] = None,
                   fovy: float = None,
                   z_near: float = None,
                   z_far: float = None):
        """设置 3D 摄像机参数"""
        if eye is not None:
            self.camera_eye = eye
        if at is not None:
            self.camera_at = at
        if up is not None:
            self.camera_up = up
        if fovy is not None:
            self.camera_fovy = fovy
        if z_near is not None:
            self.camera_z_near = z_near
        if z_far is not None:
            self.camera_z_far = z_far
    
    def set_fog(self, color: Tuple[float, float, float, float], 
                start: float, end: float, enabled: bool = True):
        """设置雾效"""
        self.fog_enabled = enabled
        self.fog_color = color
        self.fog_start = start
        self.fog_end = end
    
    def apply_camera(self):
        """应用摄像机设置到渲染器"""
        self.renderer.set_camera(
            eye=self.camera_eye,
            at=self.camera_at,
            up=self.camera_up,
            fovy=self.camera_fovy
        )
        self.renderer.camera.z_near = self.camera_z_near
        self.renderer.camera.z_far = self.camera_z_far
        self.renderer.set_fog(
            self.fog_color, 
            self.fog_start, 
            self.fog_end, 
            self.fog_enabled
        )
    
    def render_quad(self, texture: str,
                    x0: float, y0: float, z0: float,
                    x1: float, y1: float, z1: float,
                    x2: float, y2: float, z2: float,
                    x3: float, y3: float, z3: float,
                    alpha: float = 1.0,
                    blend_mode: BlendMode = BlendMode.NORMAL):
        """
        提交一个 3D 四边形到渲染队列
        
        顶点顺序: 左下 -> 左上 -> 右上 -> 右下
        对应 Lua 的 Render4V(img, x0,y0,z0, x1,y1,z1, x2,y2,z2, x3,y3,z3)
        """
        tex_path = self.textures.get(texture)
        if not tex_path:
            return
        
        self.quads.append(Quad3D(
            texture=tex_path,
            v0=(x0, y0, z0),
            v1=(x1, y1, z1),
            v2=(x2, y2, z2),
            v3=(x3, y3, z3),
            alpha=alpha,
            blend_mode=blend_mode
        ))
    
    def render_tiled_plane(self, texture: str,
                           x_range: Tuple[int, int],
                           y_offset: float,
                           z: float,
                           tile_size: float = 1.0,
                           alpha: float = 1.0,
                           blend_mode: BlendMode = BlendMode.NORMAL):
        """
        渲染平铺的平面（用于地面、水面等）
        
        Args:
            texture: 纹理名称
            x_range: x 方向的 tile 范围 (start, end)
            y_offset: y 方向偏移（用于滚动）
            z: z 坐标
            tile_size: 每个 tile 的大小
        """
        y = y_offset % tile_size
        for i in range(x_range[0], x_range[1]):
            for j in range(-4, 7):
                x0 = i * tile_size
                x1 = (i + 1) * tile_size
                y0 = (j - y) * tile_size
                y1 = (j + 1 - y) * tile_size
                
                self.render_quad(
                    texture,
                    x0, y0, z,  # 左下
                    x0, y1, z,  # 左上
                    x1, y1, z,  # 右上
                    x1, y0, z,  # 右下
                    alpha=alpha,
                    blend_mode=blend_mode
                )
    
    def clear_quads(self):
        """清空渲染队列"""
        self.quads.clear()
    
    def get_render_quads(self) -> List[Quad3D]:
        """获取当前帧的渲染四边形列表"""
        return self.quads


# ============================================================
# 具体背景实现
# ============================================================

class LakeBackground(ProceduralBackground):
    """湖泊背景 - 移植自 lake.lua"""
    
    name = "lake"
    
    def __init__(self, renderer):
        super().__init__(renderer)
        self.yos = 0.0
        self.speed = 0.001
    
    def init(self):
        # 加载纹理
        self.load_texture('lake_leaf', 'lake/lake_1.png')
        self.load_texture('lake_b1', 'lake/lake_2.png')
        self.load_texture('lake_b2', 'lake/lake_3.png')
        
        # 设置摄像机
        self.set_camera(
            eye=(0.35, -2.2, 2),
            at=(0.1, 0, -0.4),
            up=(0.2, 0, 0.6),
            fovy=0.35,
            z_near=1.8,
            z_far=4.5
        )
        
        # 雾效关闭
        self.set_fog((0, 0, 0, 0), 0, 0, False)
    
    def update(self, dt: float):
        super().update(dt)
        self.yos += self.speed
    
    def render(self):
        self.clear_quads()
        self.apply_camera()
        
        y = self.yos % 1
        yy = (self.yos % 1) / 2
        
        # 第一层：lake_b2（最远的水面）
        for i in range(-4, 7):
            # 右半边
            self.render_quad('lake_b2',
                0, 0 - y + i, -0.2,
                0, 1 - y + i, -0.2,
                1, 1 - y + i, -0.2,
                1, 0 - y + i, -0.2)
            # 左半边
            self.render_quad('lake_b2',
                -1, 0 - y + i, -0.2,
                -1, 1 - y + i, -0.2,
                0, 1 - y + i, -0.2,
                0, 0 - y + i, -0.2)
        
        # 第二层：lake_b1（中间层，加法混合）
        for i in range(-4, 7):
            self.render_quad('lake_b1',
                -0.15 - yy + i, -0.15, 0,
                -0.15 - yy + i, -1.15, 0,
                -1.15 - yy + i, -1.15, 0,
                -1.15 - yy + i, -0.15, 0,
                alpha=0.376,
                blend_mode=BlendMode.ADD)
            
            self.render_quad('lake_b1',
                0.85 - yy + i, 0.85, 0,
                0.85 - yy + i, -0.15, 0,
                -0.15 - yy + i, -0.15, 0,
                -0.15 - yy + i, 0.85, 0,
                alpha=0.376,
                blend_mode=BlendMode.ADD)
            
            self.render_quad('lake_b1',
                0, 0 - y + i, 0,
                0, 1 - y + i, 0,
                1, 1 - y + i, 0,
                1, 0 - y + i, 0,
                alpha=0.376,
                blend_mode=BlendMode.ADD)
            
            self.render_quad('lake_b1',
                -1, 0 - y + i, 0,
                -1, 1 - y + i, 0,
                0, 1 - y + i, 0,
                0, 0 - y + i, 0,
                alpha=0.376,
                blend_mode=BlendMode.ADD)
        
        # 第三层：lake_leaf（最近的树叶）
        for i in range(-4, 7):
            self.render_quad('lake_leaf',
                0.5, 0 - yy + i / 2, 0,
                0.5, 0.5 - yy + i / 2, 0,
                1, 0.5 - yy + i / 2, 0,
                1, 0 - yy + i / 2, 0)
            
            self.render_quad('lake_leaf',
                0, 0 - yy + i / 2, 0,
                0, 0.5 - yy + i / 2, 0,
                0.5, 0.5 - yy + i / 2, 0,
                0.5, 0 - yy + i / 2, 0)
            
            self.render_quad('lake_leaf',
                -0.5, 0 - yy + i / 2, 0,
                -0.5, 0.5 - yy + i / 2, 0,
                0, 0.5 - yy + i / 2, 0,
                0, 0 - yy + i / 2, 0)
            
            self.render_quad('lake_leaf',
                -1, 0 - yy + i / 2, 0,
                -1, 0.5 - yy + i / 2, 0,
                -0.5, 0.5 - yy + i / 2, 0,
                -0.5, 0 - yy + i / 2, 0)


class GensokyoSkyBackground(ProceduralBackground):
    """幻想乡天空背景 - 移植自 gensokyosora.lua"""
    
    name = "gensokyosora"
    
    def __init__(self, renderer):
        super().__init__(renderer)
        self.speed = 0.003
        self.timer = 0.0
    
    def init(self):
        self.load_texture('sky', 'gensokyosora/gensokyosora.png')
        
        # 2D 正交视角
        self.set_camera(
            eye=(0, 0, 1),
            at=(0, 0, 0),
            up=(0, 1, 0),
            fovy=1.0,
            z_near=0.1,
            z_far=10.0
        )
        
        self.set_fog((0, 0, 0, 0), 0, 0, False)
    
    def update(self, dt: float):
        super().update(dt)
        self.timer += self.speed
    
    def render(self):
        self.clear_quads()
        self.apply_camera()
        
        # 简单的天空平铺滚动
        y_offset = self.timer % 1
        
        for i in range(-2, 3):
            for j in range(-2, 3):
                self.render_quad('sky',
                    i - 0.5, j - y_offset - 0.5, 0,
                    i - 0.5, j - y_offset + 0.5, 0,
                    i + 0.5, j - y_offset + 0.5, 0,
                    i + 0.5, j - y_offset - 0.5, 0)


class TempleBackground(ProceduralBackground):
    """神殿背景 - 移植自 temple.lua"""
    
    name = "temple"
    
    def __init__(self, renderer):
        super().__init__(renderer)
        self.speed = 0.002
        self.yos = 0.0
    
    def init(self):
        self.load_texture('temple_1', 'temple/temple_1.png')
        self.load_texture('temple_2', 'temple/temple_2.png')
        
        # 3D 摄像机
        self.set_camera(
            eye=(0, -2, 1.5),
            at=(0, 0, 0),
            up=(0, 0, 1),
            fovy=0.5,
            z_near=0.5,
            z_far=5.0
        )
        
        # 淡紫色雾效
        self.set_fog((0.2, 0.1, 0.3, 1.0), 1.0, 4.0, True)
    
    def update(self, dt: float):
        super().update(dt)
        self.yos += self.speed
    
    def render(self):
        self.clear_quads()
        self.apply_camera()
        
        y = self.yos % 1
        
        # 地板层
        for i in range(-4, 5):
            self.render_quad('temple_1',
                -1, i - y, 0,
                -1, i + 1 - y, 0,
                1, i + 1 - y, 0,
                1, i - y, 0)
        
        # 柱子/装饰层
        for i in range(-4, 5):
            self.render_quad('temple_2',
                -1, i - y, 0.5,
                -1, i + 1 - y, 0.5,
                1, i + 1 - y, 0.5,
                1, i - y, 0.5,
                alpha=0.8)


class BambooBackground(ProceduralBackground):
    """竹林背景 - 移植自 bamboo.lua"""
    
    name = "bamboo"
    
    def __init__(self, renderer):
        super().__init__(renderer)
        self.speed = 0.002
        self.yos = 0.0
    
    def init(self):
        self.load_texture('bamboo_1', 'bamboo/bamboo_1.png')
        self.load_texture('bamboo_2', 'bamboo/bamboo_2.png')
        
        self.set_camera(
            eye=(0, -1.5, 1.2),
            at=(0, 0, 0),
            up=(0, 0, 1),
            fovy=0.6,
            z_near=0.3,
            z_far=6.0
        )
        
        # 绿色雾效
        self.set_fog((0.05, 0.15, 0.05, 1.0), 1.5, 5.0, True)
    
    def update(self, dt: float):
        super().update(dt)
        self.yos += self.speed
    
    def render(self):
        self.clear_quads()
        self.apply_camera()
        
        y = self.yos % 1
        
        # 远景竹林
        for i in range(-3, 4):
            self.render_quad('bamboo_1',
                -1.5, i - y, -0.5,
                -1.5, i + 1 - y, -0.5,
                1.5, i + 1 - y, -0.5,
                1.5, i - y, -0.5)
        
        # 近景竹子
        for i in range(-3, 4):
            self.render_quad('bamboo_2',
                -1.5, i - y * 1.5, 0,
                -1.5, i + 1 - y * 1.5, 0,
                1.5, i + 1 - y * 1.5, 0,
                1.5, i - y * 1.5, 0,
                alpha=0.9)


class MagicForestBackground(ProceduralBackground):
    """魔法森林背景"""
    
    name = "magic_forest"
    
    def __init__(self, renderer):
        super().__init__(renderer)
        self.speed = 0.0015
        self.yos = 0.0
    
    def init(self):
        self.load_texture('forest_1', 'magic_forest/magic_forest_1.png')
        self.load_texture('forest_2', 'magic_forest/magic_forest_2.png')
        
        self.set_camera(
            eye=(0, -2, 1.8),
            at=(0, 0, 0),
            up=(0, 0, 1),
            fovy=0.5,
            z_near=0.5,
            z_far=6.0
        )
        
        # 深绿色雾效
        self.set_fog((0.02, 0.08, 0.02, 1.0), 2.0, 5.0, True)
    
    def update(self, dt: float):
        super().update(dt)
        self.yos += self.speed
    
    def render(self):
        self.clear_quads()
        self.apply_camera()
        
        y = self.yos % 1
        
        # 森林地面
        for i in range(-4, 5):
            self.render_quad('forest_1',
                -1.5, i - y, 0,
                -1.5, i + 1 - y, 0,
                1.5, i + 1 - y, 0,
                1.5, i - y, 0)
        
        # 树木剪影层
        for i in range(-4, 5):
            self.render_quad('forest_2',
                -1.5, i - y * 0.7, 0.3,
                -1.5, i + 1 - y * 0.7, 0.3,
                1.5, i + 1 - y * 0.7, 0.3,
                1.5, i - y * 0.7, 0.3,
                alpha=0.85)


class SpellcardBackground(ProceduralBackground):
    """符卡宣言背景（特效背景）"""
    
    name = "spellcard"
    
    def __init__(self, renderer):
        super().__init__(renderer)
        self.intensity = 1.0
    
    def init(self):
        self.load_texture('spell_bg', 'spellcard/spellcard_bg.png')
        
        self.set_camera(
            eye=(0, 0, 1),
            at=(0, 0, 0),
            up=(0, 1, 0),
            fovy=1.0,
            z_near=0.1,
            z_far=10.0
        )
    
    def update(self, dt: float):
        super().update(dt)
        # 脉动效果
        self.intensity = 0.7 + 0.3 * math.sin(self.time * 3.0)
    
    def render(self):
        self.clear_quads()
        self.apply_camera()
        
        # 旋转的背景
        angle = self.time * 0.5
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        scale = 1.5 + 0.2 * math.sin(self.time * 2.0)
        
        # 旋转后的四个顶点
        corners = [(-1, -1), (-1, 1), (1, 1), (1, -1)]
        rotated = []
        for x, y in corners:
            rx = (x * cos_a - y * sin_a) * scale
            ry = (x * sin_a + y * cos_a) * scale
            rotated.append((rx, ry))
        
        self.render_quad('spell_bg',
            rotated[0][0], rotated[0][1], 0,
            rotated[1][0], rotated[1][1], 0,
            rotated[2][0], rotated[2][1], 0,
            rotated[3][0], rotated[3][1], 0,
            alpha=self.intensity,
            blend_mode=BlendMode.ADD)


# ============================================================
# 背景注册表
# ============================================================

# 所有可用的程序化背景
PROCEDURAL_BACKGROUNDS: Dict[str, type] = {
    'lake': LakeBackground,
    'gensokyosora': GensokyoSkyBackground,
    'temple': TempleBackground,
    'bamboo': BambooBackground,
    'magic_forest': MagicForestBackground,
    'spellcard': SpellcardBackground,
}


def get_background_class(name: str) -> Optional[type]:
    """获取背景类"""
    return PROCEDURAL_BACKGROUNDS.get(name)


def list_backgrounds() -> List[str]:
    """列出所有可用背景名称"""
    return list(PROCEDURAL_BACKGROUNDS.keys())


def create_background(name: str, renderer: 'BackgroundRenderer') -> Optional[ProceduralBackground]:
    """
    创建背景实例
    
    Args:
        name: 背景名称
        renderer: BackgroundRenderer 实例
        
    Returns:
        背景实例，如果名称无效则返回 None
    """
    cls = get_background_class(name)
    if cls:
        bg = cls(renderer)
        bg.init()
        return bg
    return None

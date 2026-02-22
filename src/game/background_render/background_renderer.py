"""
背景渲染器 - 完整的东方风格背景系统

支持功能:
1. 多层2D纹理卷轴 (UV滚动)
2. 3D摄像机与雾效
3. 3D平面/Billboard对象
4. 后处理特效 (反色、扭曲、符卡背景)
"""

import moderngl
import numpy as np
import math
import os
from typing import List, Dict, Optional, Tuple, Callable
from enum import Enum, auto
from dataclasses import dataclass, field
from ...core.image_loader import load_image_rgba


class BlendMode(Enum):
    """混合模式"""
    NORMAL = auto()      # 普通遮盖
    ADD = auto()         # 加算/发光
    MULTIPLY = auto()    # 正片叠底


@dataclass
class BackgroundLayer:
    """
    背景图层 - 2D卷轴层
    
    Attributes:
        texture_path: 纹理文件路径
        z_order: 渲染顺序 (数值小的先渲染，在底层)
        scroll_speed: UV滚动速度 (x, y)
        parallax_factor: 视差因子 (1.0=正常速度, 0.5=半速/远景)
        alpha: 透明度 (0.0-1.0)
        blend_mode: 混合模式
        tile_repeat: 纹理重复次数 (x, y)
        uv_offset: 当前UV偏移量 (内部使用)
        color_tint: 颜色调制 (r, g, b, a)
        enabled: 是否启用
    """
    texture_path: str
    z_order: int = 0
    scroll_speed: Tuple[float, float] = (0.0, 0.0)
    parallax_factor: float = 1.0
    alpha: float = 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    tile_repeat: Tuple[int, int] = (1, 1)
    uv_offset: Tuple[float, float] = field(default=(0.0, 0.0), repr=False)
    color_tint: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    enabled: bool = True
    
    # 3D渲染参数 (用于透视变换的平面)
    use_3d: bool = False
    vertices_3d: Optional[List[Tuple[float, float, float]]] = None  # 4个顶点的3D坐标


@dataclass 
class Background3DObject:
    """
    3D背景对象 - 平面或Billboard
    
    用于路边的树、柱子、墙壁等
    """
    texture_path: str
    position: Tuple[float, float, float]  # (x, y, z)
    size: Tuple[float, float] = (1.0, 1.0)
    is_billboard: bool = False  # True=始终面朝摄像机
    alpha: float = 1.0
    color_tint: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    enabled: bool = True


@dataclass
class Camera3D:
    """
    3D摄像机
    
    控制视角、雾效、路径动画
    """
    # 摄像机位置
    eye: Tuple[float, float, float] = (0.0, 0.0, -1.0)
    at: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    up: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    
    # 投影参数
    fovy: float = 0.8  # 视野角度 (弧度)
    z_near: float = 0.01
    z_far: float = 10.0
    
    # 雾效
    fog_enabled: bool = True
    fog_start: float = 3.0
    fog_end: float = 6.0
    fog_color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    
    # 动画路径 (用于自动飞行)
    path_start: Optional[Tuple[float, float, float]] = None
    path_end: Optional[Tuple[float, float, float]] = None
    path_duration: float = 0.0
    path_progress: float = 0.0
    
    def get_view_matrix(self) -> np.ndarray:
        """计算视图矩阵 (Look-At)"""
        eye = np.array(self.eye, dtype='f4')
        at = np.array(self.at, dtype='f4')
        up = np.array(self.up, dtype='f4')
        
        # 前向量 (从eye指向at)
        f = at - eye
        f = f / np.linalg.norm(f)
        
        # 右向量
        r = np.cross(f, up)
        r = r / np.linalg.norm(r)
        
        # 真正的上向量
        u = np.cross(r, f)
        
        # 构建视图矩阵
        view = np.eye(4, dtype='f4')
        view[0, :3] = r
        view[1, :3] = u
        view[2, :3] = -f
        view[0, 3] = -np.dot(r, eye)
        view[1, 3] = -np.dot(u, eye)
        view[2, 3] = np.dot(f, eye)
        
        return view
    
    def get_projection_matrix(self, aspect: float) -> np.ndarray:
        """计算透视投影矩阵"""
        f = 1.0 / math.tan(self.fovy / 2.0)
        
        proj = np.zeros((4, 4), dtype='f4')
        proj[0, 0] = f / aspect
        proj[1, 1] = f
        proj[2, 2] = (self.z_far + self.z_near) / (self.z_near - self.z_far)
        proj[2, 3] = (2 * self.z_far * self.z_near) / (self.z_near - self.z_far)
        proj[3, 2] = -1.0
        
        return proj
    
    def update_path(self, dt: float):
        """更新摄像机路径动画"""
        if self.path_start and self.path_end and self.path_duration > 0:
            self.path_progress += dt / self.path_duration
            if self.path_progress >= 1.0:
                self.path_progress = 1.0
            
            # 线性插值
            t = self.path_progress
            self.eye = tuple(
                s + (e - s) * t 
                for s, e in zip(self.path_start, self.path_end)
            )


@dataclass
class PostEffect:
    """后处理特效配置"""
    # 颜色反转
    invert_color: bool = False
    invert_strength: float = 1.0
    
    # 屏幕扭曲
    wave_enabled: bool = False
    wave_amplitude: float = 0.02
    wave_frequency: float = 10.0
    wave_speed: float = 3.0
    wave_time: float = 0.0
    
    # 色调偏移 (彩虹效果)
    hue_shift_enabled: bool = False
    hue_shift_speed: float = 1.0
    hue_shift_value: float = 0.0
    
    # 符卡背景
    spellcard_bg_enabled: bool = False
    spellcard_bg_texture: str = ""
    spellcard_bg_alpha: float = 0.0
    spellcard_bg_rotation: float = 0.0
    spellcard_bg_rotation_speed: float = 0.5


class BackgroundRenderer:
    """
    背景渲染器主类
    
    使用方法:
    ```python
    bg = BackgroundRenderer(ctx, base_size)
    bg.load_texture("sky.png")
    bg.add_layer(BackgroundLayer("sky.png", scroll_speed=(0.1, 0)))
    
    # 游戏循环中
    bg.update(dt)
    bg.render()
    ```
    """
    
    def __init__(self, ctx: moderngl.Context, base_size: Tuple[int, int]):
        """
        初始化背景渲染器
        
        Args:
            ctx: ModernGL上下文
            base_size: 基础窗口尺寸 (width, height)
        """
        self.ctx = ctx
        self.base_size = base_size
        self.aspect = base_size[0] / base_size[1]
        
        # 图层列表
        self.layers: List[BackgroundLayer] = []
        
        # 3D对象列表
        self.objects_3d: List[Background3DObject] = []
        
        # 摄像机
        self.camera = Camera3D()
        
        # 后处理特效
        self.post_effect = PostEffect()
        
        # 纹理缓存
        self.textures: Dict[str, moderngl.Texture] = {}
        
        # 程序化背景 (旧版)
        self.procedural_background = None
        
        # 数据驱动背景 (新版，推荐)
        self.data_background = None
        
        # 初始化着色器
        self._init_2d_shader()
        self._init_3d_shader()
        self._init_post_shader()
        
        # 帧缓冲 (用于后处理)
        self._init_framebuffer()
        
        # 全局时间
        self.time = 0.0
    
    def _init_2d_shader(self):
        """初始化2D图层着色器"""
        vertex_shader = """
        #version 330
        
        in vec2 in_vert;
        in vec2 in_uv;
        
        out vec2 v_uv;
        
        uniform vec2 u_uv_offset;
        uniform vec2 u_tile_repeat;
        
        void main() {
            gl_Position = vec4(in_vert, 0.0, 1.0);
            v_uv = in_uv * u_tile_repeat + u_uv_offset;
        }
        """
        
        fragment_shader = """
        #version 330
        
        uniform sampler2D u_texture;
        uniform vec4 u_color_tint;
        uniform float u_alpha;
        
        in vec2 v_uv;
        out vec4 f_color;
        
        void main() {
            vec4 tex_color = texture(u_texture, v_uv);
            f_color = tex_color * u_color_tint;
            f_color.a *= u_alpha;
        }
        """
        
        self.program_2d = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        
        # 全屏四边形顶点
        vertices = np.array([
            # x, y, u, v
            -1.0, -1.0, 0.0, 0.0,
            -1.0,  1.0, 0.0, 1.0,
             1.0, -1.0, 1.0, 0.0,
             1.0,  1.0, 1.0, 1.0,
        ], dtype='f4')
        
        self.vbo_2d = self.ctx.buffer(vertices.tobytes())
        self.vao_2d = self.ctx.vertex_array(
            self.program_2d,
            [(self.vbo_2d, '2f 2f', 'in_vert', 'in_uv')]
        )
    
    def _init_3d_shader(self):
        """初始化3D着色器 (支持雾效)"""
        vertex_shader = """
        #version 330
        
        in vec3 in_vert;
        in vec2 in_uv;
        
        out vec2 v_uv;
        out float v_fog_factor;
        
        uniform mat4 u_mvp;
        uniform float u_fog_start;
        uniform float u_fog_end;
        
        void main() {
            vec4 pos = u_mvp * vec4(in_vert, 1.0);
            gl_Position = pos;
            v_uv = in_uv;
            
            // 计算雾效因子 (基于深度)
            float depth = length((u_mvp * vec4(in_vert, 1.0)).xyz);
            v_fog_factor = clamp((depth - u_fog_start) / (u_fog_end - u_fog_start), 0.0, 1.0);
        }
        """
        
        fragment_shader = """
        #version 330
        
        uniform sampler2D u_texture;
        uniform vec4 u_color_tint;
        uniform float u_alpha;
        uniform vec4 u_fog_color;
        uniform bool u_fog_enabled;
        
        in vec2 v_uv;
        in float v_fog_factor;
        out vec4 f_color;
        
        void main() {
            vec4 tex_color = texture(u_texture, v_uv);
            tex_color *= u_color_tint;
            tex_color.a *= u_alpha;
            
            if (u_fog_enabled) {
                f_color = mix(tex_color, u_fog_color, v_fog_factor);
            } else {
                f_color = tex_color;
            }
        }
        """
        
        self.program_3d = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        
        # 3D四边形动态缓冲
        self.vbo_3d = self.ctx.buffer(reserve=4 * 5 * 4)  # 4 vertices * 5 floats
        self.vao_3d = self.ctx.vertex_array(
            self.program_3d,
            [(self.vbo_3d, '3f 2f', 'in_vert', 'in_uv')]
        )
    
    def _init_post_shader(self):
        """初始化后处理着色器"""
        vertex_shader = """
        #version 330
        
        in vec2 in_vert;
        in vec2 in_uv;
        
        out vec2 v_uv;
        
        void main() {
            gl_Position = vec4(in_vert, 0.0, 1.0);
            v_uv = in_uv;
        }
        """
        
        fragment_shader = """
        #version 330
        
        uniform sampler2D u_texture;
        uniform sampler2D u_spellcard_texture;
        
        // 效果参数
        uniform bool u_invert;
        uniform float u_invert_strength;
        uniform bool u_wave_enabled;
        uniform float u_wave_amplitude;
        uniform float u_wave_frequency;
        uniform float u_wave_time;
        uniform bool u_hue_shift_enabled;
        uniform float u_hue_shift;
        uniform bool u_spellcard_enabled;
        uniform float u_spellcard_alpha;
        uniform float u_spellcard_rotation;
        
        in vec2 v_uv;
        out vec4 f_color;
        
        // HSV转换函数
        vec3 rgb2hsv(vec3 c) {
            vec4 K = vec4(0.0, -1.0/3.0, 2.0/3.0, -1.0);
            vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
            vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
            float d = q.x - min(q.w, q.y);
            float e = 1.0e-10;
            return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
        }
        
        vec3 hsv2rgb(vec3 c) {
            vec4 K = vec4(1.0, 2.0/3.0, 1.0/3.0, 3.0);
            vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
            return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
        }
        
        void main() {
            vec2 uv = v_uv;
            
            // 屏幕扭曲
            if (u_wave_enabled) {
                uv.x += sin(uv.y * u_wave_frequency + u_wave_time) * u_wave_amplitude;
                uv.y += cos(uv.x * u_wave_frequency + u_wave_time) * u_wave_amplitude * 0.5;
            }
            
            vec4 color = texture(u_texture, uv);
            
            // 色调偏移
            if (u_hue_shift_enabled) {
                vec3 hsv = rgb2hsv(color.rgb);
                hsv.x = fract(hsv.x + u_hue_shift);
                color.rgb = hsv2rgb(hsv);
            }
            
            // 颜色反转
            if (u_invert) {
                color.rgb = mix(color.rgb, 1.0 - color.rgb, u_invert_strength);
            }
            
            // 符卡背景叠加
            if (u_spellcard_enabled && u_spellcard_alpha > 0.0) {
                // 旋转UV
                vec2 center = vec2(0.5, 0.5);
                vec2 rotated_uv = v_uv - center;
                float s = sin(u_spellcard_rotation);
                float c = cos(u_spellcard_rotation);
                rotated_uv = vec2(
                    rotated_uv.x * c - rotated_uv.y * s,
                    rotated_uv.x * s + rotated_uv.y * c
                ) + center;
                
                vec4 spell_color = texture(u_spellcard_texture, rotated_uv);
                color = mix(color, spell_color, u_spellcard_alpha * spell_color.a);
            }
            
            f_color = color;
        }
        """
        
        self.program_post = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        
        # 复用2D顶点缓冲
        self.vao_post = self.ctx.vertex_array(
            self.program_post,
            [(self.vbo_2d, '2f 2f', 'in_vert', 'in_uv')]
        )
    
    def _init_framebuffer(self):
        """初始化帧缓冲 (用于后处理)"""
        # 创建颜色附件纹理
        self.fb_texture = self.ctx.texture(self.base_size, 4)
        self.fb_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        
        # 创建深度缓冲
        self.fb_depth = self.ctx.depth_texture(self.base_size)
        
        # 创建帧缓冲
        self.framebuffer = self.ctx.framebuffer(
            color_attachments=[self.fb_texture],
            depth_attachment=self.fb_depth
        )
    
    def load_texture(self, path: str) -> Optional[moderngl.Texture]:
        """
        加载纹理
        
        Args:
            path: 纹理文件路径
            
        Returns:
            ModernGL纹理对象
        """
        if path in self.textures:
            return self.textures[path]
        
        if not os.path.exists(path):
            print(f"[BackgroundRenderer] 纹理不存在: {path}")
            return None
        
        try:
            w, h, data = load_image_rgba(path, flip_y=True)
            
            texture = self.ctx.texture((w, h), 4, data)
            texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            texture.repeat_x = True
            texture.repeat_y = True
            
            self.textures[path] = texture
            return texture
        except Exception as e:
            print(f"[BackgroundRenderer] 加载纹理失败 {path}: {e}")
            return None
    
    def add_layer(self, layer: BackgroundLayer) -> bool:
        """
        添加背景图层
        
        Args:
            layer: BackgroundLayer配置
            
        Returns:
            是否添加成功
        """
        # 预加载纹理
        if not self.load_texture(layer.texture_path):
            return False
        
        self.layers.append(layer)
        # 按z_order排序
        self.layers.sort(key=lambda l: l.z_order)
        return True
    
    def remove_layer(self, texture_path: str):
        """移除指定纹理的图层"""
        self.layers = [l for l in self.layers if l.texture_path != texture_path]
    
    def clear_layers(self):
        """清除所有图层"""
        self.layers.clear()
    
    def load_from_config(self, config, asset_base: str = ""):
        """
        从BackgroundConfig配置加载背景
        
        Args:
            config: BackgroundConfig对象或配置字典
            asset_base: 纹理资源的基础路径
        """
        from .background_config import BackgroundConfig, load_background_config
        
        # 如果是字符串路径，加载JSON配置
        if isinstance(config, str):
            config = load_background_config(config)
            if not config:
                print(f"[BackgroundRenderer] 无法加载配置: {config}")
                return False
        
        # 如果是字典，转换为BackgroundConfig
        if isinstance(config, dict):
            config = BackgroundConfig.from_dict(config)
        
        # 清除现有配置
        self.clear_layers()
        self.objects_3d.clear()
        
        # 设置摄像机
        self.set_camera(
            eye=config.camera.eye,
            at=config.camera.at,
            up=config.camera.up,
            fovy=config.camera.fovy
        )
        self.camera.z_near = config.camera.z_near
        self.camera.z_far = config.camera.z_far
        
        # 设置雾效
        fog = config.fog
        fog_color = (
            fog.color[0] / 255.0,
            fog.color[1] / 255.0,
            fog.color[2] / 255.0,
            fog.color[3] / 255.0 if len(fog.color) > 3 else 1.0
        )
        self.set_fog(fog_color, fog.start, fog.end, fog.enabled)
        
        # 构建纹理名称到路径的映射
        texture_map = {}
        for tex in config.textures:
            # 构建完整路径
            if asset_base:
                full_path = os.path.join(asset_base, tex.path)
            else:
                full_path = tex.path
            
            texture_map[tex.name] = {
                'path': full_path,
                'alpha': tex.alpha,
                'blend_mode': tex.blend_mode,
                'rect': tex.rect
            }
            
            # 预加载纹理
            self.load_texture(full_path)
        
        # 添加图层
        for i, layer_cfg in enumerate(config.layers):
            tex_info = texture_map.get(layer_cfg.texture)
            if not tex_info:
                print(f"[BackgroundRenderer] 图层引用的纹理不存在: {layer_cfg.texture}")
                continue
            
            # 解析混合模式
            blend_mode = BlendMode.NORMAL
            blend_str = layer_cfg.blend_mode.lower()
            if blend_str == "add":
                blend_mode = BlendMode.ADD
            elif blend_str == "multiply":
                blend_mode = BlendMode.MULTIPLY
            
            layer = BackgroundLayer(
                texture_path=tex_info['path'],
                z_order=layer_cfg.z_order,
                scroll_speed=layer_cfg.scroll_speed,
                parallax_factor=layer_cfg.parallax_factor,
                alpha=layer_cfg.alpha * tex_info['alpha'],  # 组合透明度
                blend_mode=blend_mode,
                tile_repeat=layer_cfg.tile_repeat,
                use_3d=layer_cfg.use_3d,
                vertices_3d=[tuple(v) for v in layer_cfg.vertices_3d] if layer_cfg.vertices_3d else None
            )
            
            self.add_layer(layer)
        
        print(f"[BackgroundRenderer] 已加载背景配置 '{config.name}': {len(self.layers)} 图层")
        return True
    
    def load_from_json(self, json_path: str, asset_base: str = ""):
        """
        从JSON文件加载背景配置
        
        Args:
            json_path: JSON配置文件路径
            asset_base: 纹理资源的基础路径（如果为空，使用JSON文件所在目录）
        """
        from .background_config import load_background_config
        
        config = load_background_config(json_path)
        if not config:
            return False
        
        # 默认使用JSON文件所在目录作为资源基础路径
        if not asset_base:
            asset_base = os.path.dirname(json_path)
        
        return self.load_from_config(config, asset_base)
    
    def load_background(self, name: str) -> bool:
        """
        加载数据驱动的背景（推荐方式）
        
        从 assets/images/background/{name}.json 加载配置
        
        Args:
            name: 背景名称 (如 'lake', 'temple', 'bamboo' 等)
            
        Returns:
            是否加载成功
        """
        from .data_driven_background import DataDrivenBackground, list_available_backgrounds
        
        if self.data_background is None:
            self.data_background = DataDrivenBackground(self)
        
        if self.data_background.load_by_name(name):
            # 清除旧的程序化背景
            self.procedural_background = None
            return True
        else:
            available = list_available_backgrounds()
            print(f"[BackgroundRenderer] 未找到背景配置: {name}")
            print(f"  可用背景: {', '.join(available)}")
            return False
    
    def load_procedural(self, name: str) -> bool:
        """
        加载程序化背景（旧版，保留兼容）
        
        Args:
            name: 背景名称 (如 'lake', 'temple', 'bamboo' 等)
            
        Returns:
            是否加载成功
        """
        from .procedural_background import create_background, list_backgrounds
        
        bg = create_background(name, self)
        if bg:
            self.procedural_background = bg
            self.data_background = None  # 清除数据驱动背景
            print(f"[BackgroundRenderer] 已加载程序化背景: {name}")
            return True
        else:
            available = list_backgrounds()
            print(f"[BackgroundRenderer] 未知的程序化背景: {name}")
            print(f"  可用背景: {', '.join(available)}")
            return False
    
    def clear_background(self):
        """清除所有背景"""
        self.procedural_background = None
        self.data_background = None
    
    def clear_procedural(self):
        """清除程序化背景（兼容旧代码）"""
        self.procedural_background = None
    
    def add_3d_object(self, obj: Background3DObject) -> bool:
        """添加3D背景对象"""
        if not self.load_texture(obj.texture_path):
            return False
        self.objects_3d.append(obj)
        return True
    
    def spawn_object(self, texture_path: str, x: float, y: float, z: float, 
                    size: Tuple[float, float] = (1.0, 1.0),
                    is_billboard: bool = False) -> Optional[Background3DObject]:
        """
        生成3D对象 (便捷方法)
        
        Args:
            texture_path: 纹理路径
            x, y, z: 3D位置
            size: 尺寸
            is_billboard: 是否为Billboard
        """
        obj = Background3DObject(
            texture_path=texture_path,
            position=(x, y, z),
            size=size,
            is_billboard=is_billboard
        )
        if self.add_3d_object(obj):
            return obj
        return None
    
    def set_camera(self, eye: Tuple[float, float, float] = None,
                   at: Tuple[float, float, float] = None,
                   up: Tuple[float, float, float] = None,
                   fovy: float = None):
        """设置摄像机参数"""
        if eye is not None:
            self.camera.eye = eye
        if at is not None:
            self.camera.at = at
        if up is not None:
            self.camera.up = up
        if fovy is not None:
            self.camera.fovy = fovy
    
    def set_fog(self, color: Tuple[float, float, float, float],
                start: float = 3.0, end: float = 6.0, enabled: bool = True):
        """设置雾效"""
        self.camera.fog_color = color
        self.camera.fog_start = start
        self.camera.fog_end = end
        self.camera.fog_enabled = enabled
    
    def camera_fly_to(self, target: Tuple[float, float, float], duration: float):
        """让摄像机飞向目标位置"""
        self.camera.path_start = self.camera.eye
        self.camera.path_end = target
        self.camera.path_duration = duration
        self.camera.path_progress = 0.0
    
    def set_scroll_speed(self, layer_index: int = None, texture_path: str = None,
                        speed_x: float = 0.0, speed_y: float = 0.0):
        """设置图层滚动速度"""
        for i, layer in enumerate(self.layers):
            if layer_index is not None and i == layer_index:
                layer.scroll_speed = (speed_x, speed_y)
            elif texture_path is not None and layer.texture_path == texture_path:
                layer.scroll_speed = (speed_x, speed_y)
    
    def enable_effect(self, effect_name: str, **kwargs):
        """
        启用后处理效果
        
        Args:
            effect_name: 效果名称 ('invert', 'wave', 'hue_shift', 'spellcard')
            **kwargs: 效果参数
        """
        if effect_name == 'invert':
            self.post_effect.invert_color = True
            self.post_effect.invert_strength = kwargs.get('strength', 1.0)
        elif effect_name == 'wave':
            self.post_effect.wave_enabled = True
            self.post_effect.wave_amplitude = kwargs.get('amplitude', 0.02)
            self.post_effect.wave_frequency = kwargs.get('frequency', 10.0)
            self.post_effect.wave_speed = kwargs.get('speed', 3.0)
        elif effect_name == 'hue_shift':
            self.post_effect.hue_shift_enabled = True
            self.post_effect.hue_shift_speed = kwargs.get('speed', 1.0)
        elif effect_name == 'spellcard':
            self.post_effect.spellcard_bg_enabled = True
            self.post_effect.spellcard_bg_texture = kwargs.get('texture', '')
            self.post_effect.spellcard_bg_rotation_speed = kwargs.get('rotation_speed', 0.5)
            if self.post_effect.spellcard_bg_texture:
                self.load_texture(self.post_effect.spellcard_bg_texture)
    
    def disable_effect(self, effect_name: str):
        """禁用后处理效果"""
        if effect_name == 'invert':
            self.post_effect.invert_color = False
        elif effect_name == 'wave':
            self.post_effect.wave_enabled = False
        elif effect_name == 'hue_shift':
            self.post_effect.hue_shift_enabled = False
        elif effect_name == 'spellcard':
            self.post_effect.spellcard_bg_enabled = False
            self.post_effect.spellcard_bg_alpha = 0.0
    
    def set_spellcard_alpha(self, alpha: float):
        """设置符卡背景透明度 (用于淡入淡出)"""
        self.post_effect.spellcard_bg_alpha = max(0.0, min(1.0, alpha))
    
    def update(self, dt: float):
        """
        更新背景状态
        
        Args:
            dt: 时间步长 (秒)
        """
        self.time += dt
        
        # 更新数据驱动背景 (优先)
        if self.data_background and self.data_background.data:
            self.data_background.update(dt)
        # 更新程序化背景
        elif self.procedural_background:
            self.procedural_background.update(dt)
        
        # 更新图层UV偏移
        for layer in self.layers:
            if layer.enabled:
                ox, oy = layer.uv_offset
                sx, sy = layer.scroll_speed
                pf = layer.parallax_factor
                layer.uv_offset = (
                    (ox + sx * pf * dt) % 1.0,
                    (oy + sy * pf * dt) % 1.0
                )
        
        # 更新摄像机路径
        self.camera.update_path(dt)
        
        # 更新后处理效果
        if self.post_effect.wave_enabled:
            self.post_effect.wave_time += self.post_effect.wave_speed * dt
        
        if self.post_effect.hue_shift_enabled:
            self.post_effect.hue_shift_value += self.post_effect.hue_shift_speed * dt
            self.post_effect.hue_shift_value %= 1.0
        
        if self.post_effect.spellcard_bg_enabled:
            self.post_effect.spellcard_bg_rotation += self.post_effect.spellcard_bg_rotation_speed * dt
        
        # 自动回收超出视野的3D对象
        self._cleanup_3d_objects()
    
    def _cleanup_3d_objects(self):
        """清理超出摄像机后方的3D对象"""
        cam_z = self.camera.eye[2]
        # 保留在摄像机前方的对象
        self.objects_3d = [
            obj for obj in self.objects_3d 
            if obj.position[2] > cam_z - 1.0  # 保留摄像机后方1单位内的对象
        ]
    
    def render(self, use_post_process: bool = True):
        """
        渲染背景
        
        Args:
            use_post_process: 是否应用后处理效果
        """
        has_post_effect = (
            self.post_effect.invert_color or
            self.post_effect.wave_enabled or
            self.post_effect.hue_shift_enabled or
            self.post_effect.spellcard_bg_enabled
        )
        
        if use_post_process and has_post_effect:
            # 渲染到帧缓冲
            self.framebuffer.use()
            self.framebuffer.clear(0.0, 0.0, 0.0, 1.0)
            self._render_scene()
            
            # 应用后处理并输出到屏幕
            self.ctx.screen.use()
            self._apply_post_process()
        else:
            # 直接渲染到屏幕
            self._render_scene()
    
    def _render_scene(self):
        """渲染场景 (2D图层 + 3D对象 + 程序化背景)"""
        # 清除深度缓冲 (背景在最底层)
        self.ctx.clear(depth=1.0)
        
        # 优先使用数据驱动背景
        if self.data_background and self.data_background.data:
            self._render_data_driven_background()
        # 其次使用程序化背景
        elif self.procedural_background:
            self._render_procedural_background()
        else:
            # 渲染2D图层
            for layer in self.layers:
                if layer.enabled:
                    if layer.use_3d and layer.vertices_3d:
                        self._render_3d_layer(layer)
                    else:
                        self._render_2d_layer(layer)
        
        # 渲染3D对象
        if self.objects_3d:
            self._render_3d_objects()
    
    def _render_data_driven_background(self):
        """渲染数据驱动背景"""
        bg = self.data_background
        
        # 调用背景的 render 方法生成四边形
        bg.render()
        
        # 渲染所有四边形
        quads = bg.get_render_quads()
        if not quads:
            return
        
        # 计算 MVP 矩阵
        view = self.camera.get_view_matrix()
        proj = self.camera.get_projection_matrix(self.aspect)
        mvp = np.dot(proj, view)
        
        self.program_3d['u_mvp'].write(mvp.tobytes())
        self.program_3d['u_fog_enabled'].value = self.camera.fog_enabled
        self.program_3d['u_fog_start'].value = self.camera.fog_start
        self.program_3d['u_fog_end'].value = self.camera.fog_end
        self.program_3d['u_fog_color'].value = self.camera.fog_color
        
        from .data_driven_background import BlendMode as DataBlendMode
        
        for quad in quads:
            texture = self.textures.get(quad['texture'])
            if not texture:
                continue
            
            # 转换混合模式
            blend = quad['blend_mode']
            if blend == DataBlendMode.ADD:
                self._set_blend_mode(BlendMode.ADD)
            elif blend == DataBlendMode.MULTIPLY:
                self._set_blend_mode(BlendMode.MULTIPLY)
            else:
                self._set_blend_mode(BlendMode.NORMAL)
            
            texture.use(0)
            self.program_3d['u_texture'].value = 0
            self.program_3d['u_alpha'].value = quad['alpha']
            self.program_3d['u_color_tint'].value = (1.0, 1.0, 1.0, 1.0)
            
            # 构建顶点数据
            v0, v1, v2, v3 = quad['v0'], quad['v1'], quad['v2'], quad['v3']
            vertices = np.array([
                v0[0], v0[1], v0[2], 0, 0,
                v1[0], v1[1], v1[2], 0, 1,
                v2[0], v2[1], v2[2], 1, 1,
                v3[0], v3[1], v3[2], 1, 0,
            ], dtype='f4')
            
            # 创建临时 VAO
            vbo = self.ctx.buffer(vertices)
            vao = self.ctx.vertex_array(
                self.program_3d,
                [(vbo, '3f 2f', 'in_vert', 'in_uv')]
            )
            vao.render(moderngl.TRIANGLE_FAN)
            vbo.release()
            vao.release()
        
        self._set_blend_mode(BlendMode.NORMAL)
        
        # 渲染3D对象
        if self.objects_3d:
            self._render_3d_objects()
    
    def _render_procedural_background(self):
        """渲染程序化背景"""
        bg = self.procedural_background
        
        # 调用背景的 render 方法生成四边形
        bg.render()
        
        # 渲染所有四边形
        quads = bg.get_render_quads()
        if not quads:
            return
        
        # 计算 MVP 矩阵
        view = self.camera.get_view_matrix()
        proj = self.camera.get_projection_matrix(self.aspect)
        mvp = np.dot(proj, view)
        
        self.program_3d['u_mvp'].write(mvp.tobytes())
        self.program_3d['u_fog_enabled'].value = self.camera.fog_enabled
        self.program_3d['u_fog_start'].value = self.camera.fog_start
        self.program_3d['u_fog_end'].value = self.camera.fog_end
        self.program_3d['u_fog_color'].value = self.camera.fog_color
        
        # 按纹理分组渲染
        from .procedural_background import BlendMode as ProcBlendMode
        
        for quad in quads:
            texture = self.textures.get(quad.texture)
            if not texture:
                continue
            
            # 转换混合模式
            if quad.blend_mode == ProcBlendMode.ADD:
                self._set_blend_mode(BlendMode.ADD)
            elif quad.blend_mode == ProcBlendMode.MULTIPLY:
                self._set_blend_mode(BlendMode.MULTIPLY)
            else:
                self._set_blend_mode(BlendMode.NORMAL)
            
            texture.use(0)
            self.program_3d['u_texture'].value = 0
            self.program_3d['u_alpha'].value = quad.alpha
            self.program_3d['u_color_tint'].value = (1.0, 1.0, 1.0, 1.0)
            
            # 构建顶点数据
            vertices = np.array([
                # pos (x,y,z), uv (u,v)
                quad.v0[0], quad.v0[1], quad.v0[2], quad.uv[0], quad.uv[1],
                quad.v1[0], quad.v1[1], quad.v1[2], quad.uv[0], quad.uv[3],
                quad.v2[0], quad.v2[1], quad.v2[2], quad.uv[2], quad.uv[3],
                quad.v3[0], quad.v3[1], quad.v3[2], quad.uv[2], quad.uv[1],
            ], dtype='f4')
            
            # 创建临时 VAO
            vbo = self.ctx.buffer(vertices)
            vao = self.ctx.vertex_array(
                self.program_3d,
                [(vbo, '3f 2f', 'in_vert', 'in_uv')]
            )
            vao.render(moderngl.TRIANGLE_FAN)
            vbo.release()
            vao.release()
        
        self._set_blend_mode(BlendMode.NORMAL)
        
        # 渲染3D对象
        if self.objects_3d:
            self._render_3d_objects()
    
    def _render_2d_layer(self, layer: BackgroundLayer):
        """渲染2D图层"""
        texture = self.textures.get(layer.texture_path)
        if not texture:
            return
        
        # 设置混合模式
        self._set_blend_mode(layer.blend_mode)
        
        # 绑定纹理
        texture.use(0)
        
        # 设置uniform
        self.program_2d['u_texture'].value = 0
        self.program_2d['u_uv_offset'].value = layer.uv_offset
        self.program_2d['u_tile_repeat'].value = layer.tile_repeat
        self.program_2d['u_color_tint'].value = layer.color_tint
        self.program_2d['u_alpha'].value = layer.alpha
        
        # 渲染
        self.vao_2d.render(moderngl.TRIANGLE_STRIP)
        
        # 恢复默认混合模式
        self._set_blend_mode(BlendMode.NORMAL)
    
    def _render_3d_layer(self, layer: BackgroundLayer):
        """渲染3D图层"""
        texture = self.textures.get(layer.texture_path)
        if not texture or not layer.vertices_3d:
            return
        
        self._set_blend_mode(layer.blend_mode)
        
        # 构建MVP矩阵
        view = self.camera.get_view_matrix()
        proj = self.camera.get_projection_matrix(self.aspect)
        mvp = proj @ view
        
        # 构建顶点数据
        v = layer.vertices_3d
        ox, oy = layer.uv_offset
        vertices = np.array([
            v[0][0], v[0][1], v[0][2], 0.0 + ox, 0.0 + oy,
            v[1][0], v[1][1], v[1][2], 1.0 + ox, 0.0 + oy,
            v[2][0], v[2][1], v[2][2], 0.0 + ox, 1.0 + oy,
            v[3][0], v[3][1], v[3][2], 1.0 + ox, 1.0 + oy,
        ], dtype='f4')
        
        self.vbo_3d.write(vertices.tobytes())
        
        texture.use(0)
        
        self.program_3d['u_texture'].value = 0
        self.program_3d['u_mvp'].write(mvp.tobytes())
        self.program_3d['u_color_tint'].value = layer.color_tint
        self.program_3d['u_alpha'].value = layer.alpha
        self.program_3d['u_fog_enabled'].value = self.camera.fog_enabled
        self.program_3d['u_fog_color'].value = self.camera.fog_color
        self.program_3d['u_fog_start'].value = self.camera.fog_start
        self.program_3d['u_fog_end'].value = self.camera.fog_end
        
        self.vao_3d.render(moderngl.TRIANGLE_STRIP)
        
        self._set_blend_mode(BlendMode.NORMAL)
    
    def _render_3d_objects(self):
        """渲染3D对象"""
        view = self.camera.get_view_matrix()
        proj = self.camera.get_projection_matrix(self.aspect)
        
        for obj in self.objects_3d:
            if not obj.enabled:
                continue
            
            texture = self.textures.get(obj.texture_path)
            if not texture:
                continue
            
            # 构建模型矩阵
            model = np.eye(4, dtype='f4')
            model[0, 3] = obj.position[0]
            model[1, 3] = obj.position[1]
            model[2, 3] = obj.position[2]
            
            if obj.is_billboard:
                # Billboard: 使旋转部分与视图矩阵相反
                model[:3, :3] = np.linalg.inv(view[:3, :3])
            
            mvp = proj @ view @ model
            
            # 构建顶点 (以position为中心)
            hw, hh = obj.size[0] / 2, obj.size[1] / 2
            vertices = np.array([
                -hw, -hh, 0.0, 0.0, 0.0,
                 hw, -hh, 0.0, 1.0, 0.0,
                -hw,  hh, 0.0, 0.0, 1.0,
                 hw,  hh, 0.0, 1.0, 1.0,
            ], dtype='f4')
            
            self.vbo_3d.write(vertices.tobytes())
            
            texture.use(0)
            
            self.program_3d['u_texture'].value = 0
            self.program_3d['u_mvp'].write(mvp.tobytes())
            self.program_3d['u_color_tint'].value = obj.color_tint
            self.program_3d['u_alpha'].value = obj.alpha
            self.program_3d['u_fog_enabled'].value = self.camera.fog_enabled
            self.program_3d['u_fog_color'].value = self.camera.fog_color
            self.program_3d['u_fog_start'].value = self.camera.fog_start
            self.program_3d['u_fog_end'].value = self.camera.fog_end
            
            self.vao_3d.render(moderngl.TRIANGLE_STRIP)
    
    def _apply_post_process(self):
        """应用后处理效果"""
        self.fb_texture.use(0)
        
        # 符卡背景纹理
        spellcard_tex = self.textures.get(self.post_effect.spellcard_bg_texture)
        if spellcard_tex:
            spellcard_tex.use(1)
        
        self.program_post['u_texture'].value = 0
        self.program_post['u_spellcard_texture'].value = 1
        
        self.program_post['u_invert'].value = self.post_effect.invert_color
        self.program_post['u_invert_strength'].value = self.post_effect.invert_strength
        
        self.program_post['u_wave_enabled'].value = self.post_effect.wave_enabled
        self.program_post['u_wave_amplitude'].value = self.post_effect.wave_amplitude
        self.program_post['u_wave_frequency'].value = self.post_effect.wave_frequency
        self.program_post['u_wave_time'].value = self.post_effect.wave_time
        
        self.program_post['u_hue_shift_enabled'].value = self.post_effect.hue_shift_enabled
        self.program_post['u_hue_shift'].value = self.post_effect.hue_shift_value
        
        self.program_post['u_spellcard_enabled'].value = self.post_effect.spellcard_bg_enabled
        self.program_post['u_spellcard_alpha'].value = self.post_effect.spellcard_bg_alpha
        self.program_post['u_spellcard_rotation'].value = self.post_effect.spellcard_bg_rotation
        
        self.vao_post.render(moderngl.TRIANGLE_STRIP)
    
    def _set_blend_mode(self, mode: BlendMode):
        """设置混合模式"""
        if mode == BlendMode.NORMAL:
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        elif mode == BlendMode.ADD:
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
        elif mode == BlendMode.MULTIPLY:
            self.ctx.blend_func = moderngl.DST_COLOR, moderngl.ZERO
    
    def cleanup(self):
        """清理资源"""
        for texture in self.textures.values():
            texture.release()
        self.textures.clear()
        
        self.fb_texture.release()
        self.fb_depth.release()
        self.framebuffer.release()


# ============= 预设背景配置 =============

def create_gensokyosora_background(bg: BackgroundRenderer, asset_base: str):
    """
    创建幻想乡天空背景 (gensokyosora)
    
    参考原始Lua配置实现
    """
    base = os.path.join(asset_base, "gensokyosora")
    
    # 设置摄像机 (参考Lua配置)
    bg.set_camera(
        eye=(0.20, 0.10, -1.30),
        at=(0.20, 0.00, 0.30),
        up=(0.00, 2.90, 5.70),
        fovy=0.62
    )
    
    # 设置雾效
    bg.set_fog(
        color=(155/255, 155/255, 175/255, 1.0),
        start=3.0,
        end=3.7,
        enabled=True
    )
    
    # 加载图层
    # 地面层 sora_1
    layer1 = BackgroundLayer(
        texture_path=os.path.join(base, "sora_1.png"),
        z_order=0,
        scroll_speed=(0.0, 0.01),
        use_3d=True,
        vertices_3d=[
            (-1.0, -0.6, 0.0),
            (1.4, -0.6, 0.0),
            (-1.0, -0.6, 1.0),
            (1.4, -0.6, 1.0),
        ],
        tile_repeat=(1, 6)
    )
    bg.add_layer(layer1)
    
    # 云层 sora_2 (半透明)
    layer2 = BackgroundLayer(
        texture_path=os.path.join(base, "sora_2.png"),
        z_order=1,
        scroll_speed=(0.0, 0.01),
        alpha=0.4,  # 0x64 = 100/255 ≈ 0.4
        blend_mode=BlendMode.NORMAL,
        use_3d=True,
        vertices_3d=[
            (-0.8, -0.4, 0.0),
            (1.6, -0.4, 0.0),
            (-0.8, -0.4, 1.0),
            (1.6, -0.4, 1.0),
        ],
        tile_repeat=(1, 4)
    )
    bg.add_layer(layer2)
    
    # 天空背景 aosora
    sky_layer = BackgroundLayer(
        texture_path=os.path.join(base, "aosora.png"),
        z_order=-1,  # 最底层
        scroll_speed=(0.0, 0.0),
    )
    bg.add_layer(sky_layer)
    
    return bg


def create_magic_forest_background(bg: BackgroundRenderer, asset_base: str):
    """
    创建魔法森林背景 (magic_forest)
    """
    base = os.path.join(asset_base, "magic_forest")
    
    # 设置摄像机
    bg.set_camera(
        eye=(0.25, -2.2, 1.1),
        at=(0.2, 0.0, 0.0),
        up=(0.0, 0.0, 1.0),
        fovy=0.35
    )
    
    # 禁用雾效
    bg.set_fog((0, 0, 0, 0), enabled=False)
    
    # 地面层
    ground = BackgroundLayer(
        texture_path=os.path.join(base, "ground.png"),
        z_order=0,
        scroll_speed=(0.0, 0.004),
        use_3d=True,
        vertices_3d=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
        ],
        tile_repeat=(2, 2)
    )
    bg.add_layer(ground)
    
    # 遮罩层
    mask = BackgroundLayer(
        texture_path=os.path.join(base, "mask.png"),
        z_order=1,
        scroll_speed=(0.0, 0.004),
        blend_mode=BlendMode.MULTIPLY,
        use_3d=True,
        vertices_3d=[
            (0.0, 0.0, -0.2),
            (1.0, 0.0, -0.2),
            (0.0, 1.0, -0.2),
            (1.0, 1.0, -0.2),
        ],
        tile_repeat=(2, 3)
    )
    bg.add_layer(mask)
    
    return bg


def create_simple_scroll_background(bg: BackgroundRenderer, texture_path: str,
                                    scroll_speed: Tuple[float, float] = (0.0, 0.1)):
    """
    创建简单的2D卷轴背景
    """
    layer = BackgroundLayer(
        texture_path=texture_path,
        z_order=0,
        scroll_speed=scroll_speed,
        tile_repeat=(1, 2)
    )
    bg.add_layer(layer)
    return bg

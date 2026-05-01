"""
渲染器类 - 负责所有OpenGL渲染逻辑

渲染层级顺序（从底到顶，符合东方Project标准）：
0. 背景 (Background)
1. 敌人/Boss
2. 特效/光环 (Aura)
3. 道具 (Items) - 在敌弹下层，避免遮挡弹幕
4. 自机子弹 (Player Shots) - 在敌弹下层
5. 自机Options
6. 自机本体 (Player Sprite)
7. 敌机弹幕 (Enemy Bullets) - 内部按大小排序：大弹在下，小弹在上
8. 激光 (Lasers) - 在弹幕层
9. 特效：消弹 (VFX)
10. 自机判定点 (Hitbox)
11. UI / 对话框
"""
import moderngl
import numpy as np
import math
import time
import os
from .laser_renderer import LaserRenderer
from .optimized_bullet_renderer import OptimizedBulletRenderer


# 子弹大小分类常量（用于高效分桶排序）
class BulletSizeCategory:
    """子弹大小分类，用于渲染排序"""
    LASER = 0        # 激光（最底层）
    HUGE = 1         # 巨型光玉、大碟子
    LARGE = 2        # 大型子弹、札弹
    MEDIUM = 3       # 中型子弹
    SMALL = 4        # 小玉、鳞弹
    TINY = 5         # 米粒弹、针弹（最顶层）


# 预定义的精灵大小分类映射（可通过配置扩展）
# 键为精灵ID前缀或完整ID，值为大小分类
DEFAULT_SIZE_CATEGORIES = {
    # 巨型
    'ball_huge': BulletSizeCategory.HUGE,
    'bubble': BulletSizeCategory.HUGE,
    'orb_huge': BulletSizeCategory.HUGE,
    # 大型
    'ball_big': BulletSizeCategory.LARGE,
    'star_big': BulletSizeCategory.LARGE,
    'ofuda': BulletSizeCategory.LARGE,
    'knife_big': BulletSizeCategory.LARGE,
    # 中型
    'ball_mid': BulletSizeCategory.MEDIUM,
    'star_mid': BulletSizeCategory.MEDIUM,
    'ellipse': BulletSizeCategory.MEDIUM,
    # 小型
    'ball_small': BulletSizeCategory.SMALL,
    'star_small': BulletSizeCategory.SMALL,
    'scale': BulletSizeCategory.SMALL,
    'kunai': BulletSizeCategory.SMALL,
    # 极小型
    'rice': BulletSizeCategory.TINY,
    'needle': BulletSizeCategory.TINY,
    'dot': BulletSizeCategory.TINY,
    'grain': BulletSizeCategory.TINY,
}


# 尝试导入配置模块（向后兼容）
try:
    from ..core.config import get_config
    HAS_CORE_CONFIG = True
except ImportError:
    HAS_CORE_CONFIG = False
    get_config = None


class Renderer:
    """OpenGL渲染器，负责子弹、玩家、敌人、Boss的渲染"""
    
    def __init__(self, ctx, base_size, sprite_manager, textures, sprite_uv_map):
        """
        初始化渲染器
        
        Args:
            ctx: ModernGL上下文
            base_size: 基础窗口尺寸 (width, height)
            sprite_manager: 精灵管理器实例
            textures: 纹理字典 {texture_path: texture}
            sprite_uv_map: 精灵UV映射字典 {sprite_id: [u_left, v_top, u_right, v_bottom]}
        """
        self.ctx = ctx
        self.base_size = base_size
        self.sprite_manager = sprite_manager
        
        # 从配置获取参数（如果可用）
        if HAS_CORE_CONFIG and get_config:
            config = get_config()
            self._y_scale_factor = config.y_scale_factor
        else:
            self._y_scale_factor = base_size[0] / base_size[1]
        self.textures = textures
        self.sprite_uv_map = sprite_uv_map
        
        # 获取默认精灵
        self.default_sprite_id = 'star_small1' if 'star_small1' in sprite_manager.get_all_sprite_ids() else next(iter(sprite_manager.get_all_sprite_ids()), None)
        
        # 子弹大小分类缓存（避免每帧重新计算）
        self._sprite_size_cache = {}
        self._build_sprite_size_cache()
        
        # 初始化着色器和渲染资源
        self._init_bullet_shader()
        self._init_player_shader()
        self._init_circle_shader()
        self._init_viewport_border_shader()

        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.hitbox_texture_path = os.path.join(root_dir, 'assets', 'misc.png')
        self.hitbox_texture = None
        self.hitbox_texture_size = None
        
        # 初始化激光渲染器
        self.laser_renderer = LaserRenderer(ctx, base_size)
        
        # 背景渲染器（可选，延迟初始化）
        self.background_renderer = None
        # 优化版敌弹渲染器（仅当 bullet_pool 支持 prepare_render_data_sorted 时启用）
        self.optimized_bullet_renderer = OptimizedBulletRenderer(ctx, textures)

        # 全窗口背景图（UI背景，叠在游戏内容下层）
        self._window_bg_texture = None
        self._window_bg_program = None
        self._window_bg_vbo = None
        self._window_bg_vao = None
        self._init_window_bg_shader()
    
    def _build_sprite_size_cache(self):
        """构建精灵大小分类缓存"""
        for sprite_id in self.sprite_manager.get_all_sprite_ids():
            self._sprite_size_cache[sprite_id] = self._classify_sprite_size(sprite_id)
    
    def _classify_sprite_size(self, sprite_id: str) -> int:
        """
        根据精灵ID分类其大小等级
        
        Args:
            sprite_id: 精灵ID
            
        Returns:
            BulletSizeCategory 常量
        """
        # 首先检查完整ID匹配
        if sprite_id in DEFAULT_SIZE_CATEGORIES:
            return DEFAULT_SIZE_CATEGORIES[sprite_id]
        
        # 检查前缀匹配
        sprite_id_lower = sprite_id.lower()
        for prefix, category in DEFAULT_SIZE_CATEGORIES.items():
            if sprite_id_lower.startswith(prefix):
                return category
        
        # 根据精灵实际尺寸推断
        sprite_data = self.sprite_manager.get_sprite(sprite_id)
        if sprite_data and 'rect' in sprite_data:
            width = sprite_data['rect'][2]
            height = sprite_data['rect'][3]
            max_dim = max(width, height)
            
            if max_dim >= 64:
                return BulletSizeCategory.HUGE
            elif max_dim >= 32:
                return BulletSizeCategory.LARGE
            elif max_dim >= 16:
                return BulletSizeCategory.MEDIUM
            elif max_dim >= 8:
                return BulletSizeCategory.SMALL
            else:
                return BulletSizeCategory.TINY
        
        # 默认为中型
        return BulletSizeCategory.MEDIUM
    
    def get_sprite_size_category(self, sprite_id: str) -> int:
        """获取精灵的大小分类（带缓存）"""
        if sprite_id not in self._sprite_size_cache:
            self._sprite_size_cache[sprite_id] = self._classify_sprite_size(sprite_id)
        return self._sprite_size_cache[sprite_id]
    
    def _init_bullet_shader(self):
        """初始化子弹渲染着色器和VAO"""
        # 顶点着色器：接收位置并转换到裁剪空间，支持实例化偏移、角度、UV坐标和尺寸
        vertex_shader = """
        #version 330
        in vec2 in_vert;
        in vec2 in_uv_base;
        in vec2 in_offset;
        in float in_angle;
        in vec4 in_uv_offset;
        in vec2 in_scale;  // 每个子弹的独立尺寸
        
        out vec2 v_uv;
        
        void main() {
            // 先应用缩放，再旋转
            vec2 scaled = in_vert * in_scale;
            // 计算旋转矩阵
            float s = sin(in_angle);
            float c = cos(in_angle);
            vec2 rotated = vec2(scaled.x * c - scaled.y * s, scaled.x * s + scaled.y * c);
            // 应用旋转和偏移
            vec2 position = rotated + in_offset;
            // 宽高比校正：384x448屏幕，宽高比为6:7，保持x轴[-1,1]，y轴需要乘以(384.0/448.0)
            position.y *= 384.0 / 448.0;
            gl_Position = vec4(position, 0.0, 1.0);
            // 使用实例化的UV坐标
            v_uv = in_uv_base * vec2(in_uv_offset.z - in_uv_offset.x, in_uv_offset.w - in_uv_offset.y) + in_uv_offset.xy;
        }
        """
        
        # 片元着色器：使用纹理采样
        fragment_shader = """
        #version 330
        uniform sampler2D u_texture;
        uniform float u_alpha;
        in vec2 v_uv;
        out vec4 f_color;
        void main() {
            vec4 tex_color = texture(u_texture, v_uv);
            tex_color.a *= u_alpha;
            f_color = tex_color;
        }
        """
        
        self.bullet_program = self.ctx.program(vertex_shader=vertex_shader, fragment_shader=fragment_shader)
        self.bullet_program['u_texture'].value = 0
        if 'u_alpha' in self.bullet_program:
            self.bullet_program['u_alpha'].value = 1.0
        
        # 保存缩放因子供渲染时使用
        self.bullet_scale_factor = 2.0 / self.base_size[1]
        
        # 准备顶点数据 - 使用单位正方形，实际尺寸由in_scale控制
        # 半尺寸为0.5，缩放后会乘以实际像素尺寸
        vertices = np.array([
            -0.5,  0.5, 0.0, 0.0,
            -0.5, -0.5, 0.0, 1.0,
             0.5,  0.5, 1.0, 0.0,
             0.5,  0.5, 1.0, 0.0,
            -0.5, -0.5, 0.0, 1.0,
             0.5, -0.5, 1.0, 1.0,
        ], dtype='f4')
        
        self.bullet_vbo = self.ctx.buffer(vertices.tobytes())
        
        # 实例化数据VBO
        self.instance_vbo = self.ctx.buffer(reserve=50000 * 2 * 4)
        self.angle_vbo = self.ctx.buffer(reserve=50000 * 1 * 4)
        self.uv_vbo = self.ctx.buffer(reserve=50000 * 4 * 4)
        self.scale_vbo = self.ctx.buffer(reserve=50000 * 2 * 4)  # 每个子弹的尺寸 (width, height)
        
        # 创建VAO
        self.bullet_vao = self.ctx.vertex_array(
            self.bullet_program,
            [(self.bullet_vbo, '2f 2f', 'in_vert', 'in_uv_base'),
             (self.instance_vbo, '2f/i', 'in_offset'),
             (self.angle_vbo, '1f/i', 'in_angle'),
             (self.uv_vbo, '4f/i', 'in_uv_offset'),
             (self.scale_vbo, '2f/i', 'in_scale')]
        )
    
    def _init_player_shader(self):
        """初始化玩家/敌人/Boss渲染着色器和VAO"""
        # 纯色渲染shader（用于备用）
        self.player_program = self.ctx.program(
            vertex_shader="""
            #version 330
            in vec2 in_vert;
            in vec3 in_color;
            
            out vec3 v_color;
            
            void main() {
                vec2 position = in_vert;
                position.y *= 384.0 / 448.0;
                gl_Position = vec4(position, 0.0, 1.0);
                v_color = in_color;
            }
            """,
            fragment_shader="""
            #version 330
            in vec3 v_color;
            out vec4 f_color;
            
            void main() {
                f_color = vec4(v_color, 1.0);
            }
            """
        )
        
        self.player_vbo = self.ctx.buffer(reserve=6 * 2 * 4)
        player_colors = np.array([
            0.0, 1.0, 1.0,
            0.0, 1.0, 1.0,
            0.0, 1.0, 1.0,
            0.0, 1.0, 1.0,
            0.0, 1.0, 1.0,
            0.0, 1.0, 1.0,
        ], dtype='f4')
        self.player_color_vbo = self.ctx.buffer(player_colors.tobytes())
        self.player_vao = self.ctx.vertex_array(
            self.player_program,
            [(self.player_vbo, '2f', 'in_vert'),
             (self.player_color_vbo, '3f', 'in_color')]
        )
        
        # 纹理渲染shader（用于玩家精灵）
        self.player_tex_program = self.ctx.program(
            vertex_shader="""
            #version 330
            in vec2 in_vert;
            in vec2 in_uv;
            
            out vec2 v_uv;
            
            void main() {
                vec2 position = in_vert;
                position.y *= 384.0 / 448.0;
                gl_Position = vec4(position, 0.0, 1.0);
                v_uv = in_uv;
            }
            """,
            fragment_shader="""
            #version 330
            uniform sampler2D tex;
            uniform float u_alpha;
            in vec2 v_uv;
            out vec4 f_color;
            
            void main() {
                f_color = texture(tex, v_uv);
                f_color.a *= u_alpha;
                if (f_color.a < 0.1) discard;
            }
            """
        )
        if 'u_alpha' in self.player_tex_program:
            self.player_tex_program['u_alpha'].value = 1.0
        
        # 玩家纹理渲染缓冲
        self.player_tex_vbo = self.ctx.buffer(reserve=6 * 4 * 4)  # 6 vertices * 4 floats (x,y,u,v)
        self.player_tex_vao = self.ctx.vertex_array(
            self.player_tex_program,
            [(self.player_tex_vbo, '2f 2f', 'in_vert', 'in_uv')]
        )
        
        # 玩家纹理缓存
        self.player_texture = None
        self.player_texture_size = None
        # 玩家子弹纹理（可独立）
        self.player_bullet_texture = None
        self.player_bullet_texture_size = None
    
    def _init_circle_shader(self):
        """初始化判定圆圈渲染着色器和VAO"""
        self.circle_segments = 32
        self.circle_program = self.ctx.program(
            vertex_shader="""
            #version 330
            in vec2 in_vert;
            void main() {
                vec2 position = in_vert;
                position.y *= 384.0 / 448.0;
                gl_Position = vec4(position, 0.0, 1.0);
            }
            """,
            fragment_shader="""
            #version 330
            out vec4 f_color;
            void main() {
                f_color = vec4(1.0, 1.0, 1.0, 1.0);
            }
            """
        )
        self.circle_vbo = self.ctx.buffer(reserve=(self.circle_segments + 1) * 2 * 4)
        self.circle_vao = self.ctx.vertex_array(self.circle_program, [(self.circle_vbo, '2f', 'in_vert')])

    def _init_window_bg_shader(self):
        """初始化全窗口背景图渲染着色器（全屏纹理四边形，NDC坐标）"""
        vertex_shader = """
        #version 330
        in vec2 in_pos;
        in vec2 in_uv;
        out vec2 v_uv;
        void main() {
            gl_Position = vec4(in_pos, 0.0, 1.0);
            v_uv = in_uv;
        }
        """
        fragment_shader = """
        #version 330
        uniform sampler2D u_tex;
        uniform float u_alpha;
        in vec2 v_uv;
        out vec4 f_color;
        void main() {
            vec4 c = texture(u_tex, v_uv);
            f_color = vec4(c.rgb, c.a * u_alpha);
        }
        """
        self._window_bg_program = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        self._window_bg_program['u_tex'].value = 0
        self._window_bg_program['u_alpha'].value = 1.0

        # 全屏四边形：NDC (-1,1) 到 (1,-1)，UV (0,0) 到 (1,1)
        # 顶点顺序保证屏幕左上=图片左上
        quad = np.array([
            # pos_x  pos_y   uv_x  uv_y
            -1.0,  1.0,   0.0,  0.0,   # 左上
            -1.0, -1.0,   0.0,  1.0,   # 左下
             1.0,  1.0,   1.0,  0.0,   # 右上
             1.0,  1.0,   1.0,  0.0,   # 右上
            -1.0, -1.0,   0.0,  1.0,   # 左下
             1.0, -1.0,   1.0,  1.0,   # 右下
        ], dtype='f4')
        self._window_bg_vbo = self.ctx.buffer(quad.tobytes())
        self._window_bg_vao = self.ctx.vertex_array(
            self._window_bg_program,
            [(self._window_bg_vbo, '2f 2f', 'in_pos', 'in_uv')]
        )

    def set_window_bg_texture(self, path: str, alpha: float = 1.0) -> bool:
        """
        加载并设置全窗口背景图（叠在游戏内容下层，UI面板上层）

        Args:
            path: 图片文件路径，如 'assets/ui/ui_bg.png'
            alpha: 整体透明度 0.0-1.0

        Returns:
            bool: 是否加载成功
        """
        try:
            from PIL import Image
            img = Image.open(path).convert("RGBA")
            # 不翻转：PIL行0（顶部）→ OpenGL行0（底部）恰好与 UV v=0→底部对应
            # 我们在 quad 中把 NDC y=+1（顶）对应 uv_v=0，y=-1（底）对应 uv_v=1，
            # 即不翻转图片就能让图片顶部显示在屏幕顶部
            w, h = img.size
            data = img.tobytes("raw", "RGBA")
            tex = self.ctx.texture((w, h), 4, data)
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._window_bg_texture = tex
            self._window_bg_program['u_alpha'].value = alpha
            print(f"已加载全窗口背景图: {path} ({w}x{h})")
            return True
        except Exception as e:
            print(f"加载全窗口背景图失败 {path}: {e}")
            return False

    def _render_window_bg(self):
        """渲染全窗口背景图（仅在有纹理时调用）"""
        if self._window_bg_texture is None:
            return
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._window_bg_texture.use(0)
        self._window_bg_vao.render(moderngl.TRIANGLES)

    def _repaint_window_bg_outside_viewport(self, viewport_rect, win_size):
        """
        在游戏视口以外的 4 个边框条（上/下/左/右）重新绘制全窗口背景图。

        Why: 背景渲染器内部的 `ctx.screen.use()` / 后处理会把 viewport 重置为
        整窗口并输出到整个屏幕，顺带把 HUD / 视口边框区域原先画好的 ui_bg 覆盖。
        因此在游戏层全部渲染完之后，用 4 次 scissor 裁剪把 ui_bg 重贴到
        游戏视口以外的区域（游戏区域内部仍然是背景渲染器画的内容）。

        Args:
            viewport_rect: 游戏视口 (x, y_from_bottom, w, h)
            win_size: (win_w, win_h)
        """
        if self._window_bg_texture is None:
            return
        vx, vy, vw, vh = viewport_rect
        win_w, win_h = win_size
        # 目前要裁的 4 条 scissor 矩形（OpenGL 约定：y 从下向上）
        strips = []
        # 下边条
        if vy > 0:
            strips.append((0, 0, win_w, vy))
        # 上边条
        top_y = vy + vh
        if top_y < win_h:
            strips.append((0, top_y, win_w, win_h - top_y))
        # 左边条
        if vx > 0:
            strips.append((0, vy, vx, vh))
        # 右边条
        right_x = vx + vw
        if right_x < win_w:
            strips.append((right_x, vy, win_w - right_x, vh))

        if not strips:
            return

        # 确保渲染到整个窗口（viewport 与 strip 的 scissor 协同裁剪）
        prev_viewport = self.ctx.viewport
        self.ctx.viewport = (0, 0, win_w, win_h)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._window_bg_texture.use(0)
        for rect in strips:
            self.ctx.scissor = rect
            self._window_bg_vao.render(moderngl.TRIANGLES)
        self.ctx.scissor = None
        self.ctx.viewport = prev_viewport

    def _init_viewport_border_shader(self):
        """初始化游戏视口边框渲染着色器"""
        self.border_program = self.ctx.program(
            vertex_shader="""
            #version 330
            in vec2 in_vert;
            void main() {
                gl_Position = vec4(in_vert, 0.0, 1.0);
            }
            """,
            fragment_shader="""
            #version 330
            uniform vec3 u_color;
            out vec4 f_color;
            void main() {
                f_color = vec4(u_color, 1.0);
            }
            """
        )
        # 4 corner vertices for a quad (will be expanded to line strip for border)
        # In NDC: left=-1, right=1, top=1, bottom=-1
        # We build border verts in window coords (not aspect-corrected)
        self.border_vbo = self.ctx.buffer(reserve=10 * 2 * 4)
        self.border_vao = self.ctx.vertex_array(
            self.border_program,
            [(self.border_vbo, '2f', 'in_vert')]
        )

    def _render_viewport_border(self, viewport_rect, win_size):
        """
        在游戏视口周围绘制边框线（窗口坐标空间）
        viewport_rect: (x, y, width, height) 像素坐标
        win_size: (window_width, window_height)
        """
        x, y, w, h = viewport_rect
        win_w, win_h = win_size

        # 四个角点 (顺时针: 左下 → 右下 → 右上 → 左上 → 左下)
        pts = [
            (2.0 * x / win_w - 1.0,  2.0 * y / win_h - 1.0),   # 左下
            (2.0 * (x + w) / win_w - 1.0, 2.0 * y / win_h - 1.0),  # 右下
            (2.0 * (x + w) / win_w - 1.0, 2.0 * (y + h) / win_h - 1.0),  # 右上
            (2.0 * x / win_w - 1.0,  2.0 * (y + h) / win_h - 1.0),  # 左上
            (2.0 * x / win_w - 1.0,  2.0 * y / win_h - 1.0),   # 左下 (封闭)
        ]

        import numpy as np
        data = np.array(pts, dtype='f4')
        self.border_vbo.write(data.tobytes())
        self.border_program['u_color'].value = (0.3, 0.5, 1.0)  # 蓝色边框
        self.border_vao.render(moderngl.LINE_STRIP, vertices=5)
    
    def set_background_renderer(self, background_renderer):
        """
        设置背景渲染器
        
        Args:
            background_renderer: BackgroundRenderer实例
        """
        self.background_renderer = background_renderer
    
    def render_frame(self, bullet_pool, player, stage_manager, laser_pool=None, viewport_rect=None,
                     item_renderer=None, items=None, dt=0.0, enemy_scripts=None, item_pool=None,
                     profile_segments=None):
        """
        渲染一帧（按正确的图层顺序）

        渲染顺序（从底到顶）：
        0. 背景（2D卷轴/3D场景）
        1. 敌人/Boss
        2. 道具（在敌弹下层）
        3. 自机子弹（TODO: 分离玩家子弹）
        4. 自机Options
        5. 自机本体
        6. 敌机弹幕（按大小排序：大弹在下，小弹在上）
        7. 激光
        8. 自机判定点

        Args:
            bullet_pool: 子弹池对象
            player: 玩家对象
            stage_manager: 关卡管理器对象
            laser_pool: 激光池对象（可选）
            viewport_rect: (x, y, width, height)，游戏区域在窗口中的视口
            item_renderer: 道具渲染器（可选，用于统一渲染顺序）
            items: 道具列表（可选）
            dt: 时间步长（用于背景动画更新）
            enemy_scripts: 敌人脚本列表（可选，新的敌人系统）
        """
        do_profile = profile_segments is not None

        # 保存并切换视口到游戏区域
        prev_viewport = self.ctx.viewport
        win_w, win_h = prev_viewport[2], prev_viewport[3]
        if viewport_rect:
            # 先清除整个窗口背景（覆盖边框区域）
            self.ctx.viewport = (0, 0, win_w, win_h)
            self.ctx.clear(0.05, 0.05, 0.08)
            # 渲染全窗口背景图（叠在游戏内容下层，UI面板背景）
            self._render_window_bg()
            # 切换到游戏视口，用 scissor 限制 clear 只影响游戏区域
            # （OpenGL 的 clear 不受 viewport 约束，必须用 scissor 限制范围）
            self.ctx.viewport = viewport_rect
            self.ctx.scissor = viewport_rect
            self.ctx.clear(0.1, 0.1, 0.1)
            self.ctx.scissor = None  # 关闭 scissor，恢复全屏渲染
        else:
            # 无视口分割时正常清屏
            self.ctx.clear(0.1, 0.1, 0.1)

        # ===== 层级 0: 背景 =====
        seg_start = time.perf_counter() if do_profile else 0.0
        if self.background_renderer:
            self.background_renderer.update(dt)
            self.background_renderer.render()
            # 背景渲染器内部会 ctx.screen.use() 把 viewport 重置为整个窗口，
            # 这里把 viewport 重新设回游戏视口，保证后续敌人/子弹/激光/玩家
            # 的 NDC 映射仍然落在正确的游戏区域。
            if viewport_rect:
                self.ctx.viewport = viewport_rect
        if do_profile:
            profile_segments['render_bg'] = profile_segments.get('render_bg', 0.0) + (time.perf_counter() - seg_start)

        # ===== 层级 1: 敌人/Boss =====
        seg_start = time.perf_counter() if do_profile else 0.0
        self._render_boss(stage_manager)
        self._render_enemies(stage_manager, enemy_scripts)
        if do_profile:
            profile_segments['render_enemy'] = profile_segments.get('render_enemy', 0.0) + (time.perf_counter() - seg_start)

        # ===== 层级 2: 道具 =====
        seg_start = time.perf_counter() if do_profile else 0.0
        if item_renderer:
            if item_pool is not None and hasattr(item_pool, 'get_render_data'):
                render_data = item_pool.get_render_data()
                item_renderer.render_items_soa(*render_data)
            elif items:
                item_renderer.render_items(items)
        if do_profile:
            profile_segments['render_item'] = profile_segments.get('render_item', 0.0) + (time.perf_counter() - seg_start)

        # ===== 层级 3: 自机子弹 + 自机激光 =====
        seg_start = time.perf_counter() if do_profile else 0.0
        self._render_player_bullets(player)
        self._render_player_lasers(player)
        if do_profile:
            profile_segments['render_player'] = profile_segments.get('render_player', 0.0) + (time.perf_counter() - seg_start)

        # ===== 层级 4-5: Options、自机本体 =====
        seg_start = time.perf_counter() if do_profile else 0.0
        self._render_player(player)
        if do_profile:
            profile_segments['render_player_sprite'] = profile_segments.get('render_player_sprite', 0.0) + (time.perf_counter() - seg_start)

        # ===== 层级 6: 敌机弹幕（按大小排序） =====
        seg_start = time.perf_counter() if do_profile else 0.0
        self._render_bullets_sorted(bullet_pool)
        if do_profile:
            profile_segments['render_enemy_bullet'] = profile_segments.get('render_enemy_bullet', 0.0) + (time.perf_counter() - seg_start)

        # ===== 层级 7: 激光 =====
        seg_start = time.perf_counter() if do_profile else 0.0
        if laser_pool:
            lasers, bent_lasers = laser_pool.get_all_lasers()
            self.laser_renderer.render_lasers(lasers)
            self.laser_renderer.render_bent_lasers(bent_lasers)
        if do_profile:
            profile_segments['render_laser'] = profile_segments.get('render_laser', 0.0) + (time.perf_counter() - seg_start)

        # ===== 层级 8: 自机判定点（最高优先级） =====
        seg_start = time.perf_counter() if do_profile else 0.0
        if player.is_focused:
            self._render_hitbox(player)
        if do_profile:
            profile_segments['render_hitbox'] = profile_segments.get('render_hitbox', 0.0) + (time.perf_counter() - seg_start)

        # 还原视口
        self.ctx.viewport = prev_viewport

        # 重新把 ui_bg 贴到游戏视口以外的 4 条边框区域
        # （背景渲染器内部会 ctx.screen.use() 把 viewport 改回整窗口，
        #  顺带把 HUD / 边框区域的 ui_bg 也刷掉——此处补回来）
        if viewport_rect:
            self._repaint_window_bg_outside_viewport(viewport_rect, (win_w, win_h))

        # 绘制游戏视口边框（在窗口坐标空间）
        if viewport_rect:
            self._render_viewport_border(viewport_rect, (win_w, win_h))
    
    def _render_bullets_sorted(self, bullet_pool):
        """
        按大小分类渲染子弹（大弹在下，小弹在上）
        
        使用分桶策略实现高效排序：
        - 不进行每帧的完整排序
        - 按大小分类分桶，然后按桶顺序渲染
        - 同一桶内按纹理分组批量渲染
        """
        # 优先走优化版渲染路径，减少 Python 层分桶与逐精灵查询开销
        if hasattr(bullet_pool, 'prepare_render_data_sorted'):
            rendered_batches = self.optimized_bullet_renderer.render_from_pool(bullet_pool)
            if rendered_batches > 0:
                return

        positions, colors, angles, sprite_ids = bullet_pool.get_active_bullets()
        active_count = len(positions)
        
        if active_count == 0:
            return
        
        # 按大小分类分桶
        # buckets[category] = {texture_path: [indices]}
        buckets = {cat: {} for cat in range(6)}  # 6个大小分类
        
        for i in range(active_count):
            sprite_id = sprite_ids[i]
            size_category = self.get_sprite_size_category(sprite_id)
            texture_path = self.sprite_manager.get_sprite_texture_path(sprite_id)
            
            if not texture_path:
                texture_path = next(iter(self.textures.keys())) if self.textures else None
            
            if texture_path:
                if texture_path not in buckets[size_category]:
                    buckets[size_category][texture_path] = []
                buckets[size_category][texture_path].append(i)
        
        # 按大小顺序渲染（从大到小：LASER -> HUGE -> LARGE -> MEDIUM -> SMALL -> TINY）
        for category in range(6):
            for texture_path, bullet_indices in buckets[category].items():
                if texture_path in self.textures and bullet_indices:
                    self._render_bullet_batch(
                        positions, angles, sprite_ids, 
                        bullet_indices, texture_path
                    )
    
    def _render_bullet_batch(self, positions, angles, sprite_ids, indices, texture_path):
        """渲染一批子弹（同一纹理）"""
        self.textures[texture_path].use(0)
        
        group_size = len(indices)
        indices_array = np.array(indices)
        group_positions = positions[indices_array]
        group_angles = angles[indices_array]
        group_sprite_ids = sprite_ids[indices_array]
        
        self.instance_vbo.write(group_positions.tobytes())
        self.angle_vbo.write(group_angles.tobytes())
        
        # 准备UV数据和尺寸数据
        uv_data = np.zeros((group_size, 4), dtype='f4')
        scale_data = np.zeros((group_size, 2), dtype='f4')
        default_size = 16.0
        
        for j, sprite_id in enumerate(group_sprite_ids):
            # UV数据
            if sprite_id in self.sprite_uv_map:
                uv_data[j] = self.sprite_uv_map[sprite_id]
            elif self.default_sprite_id and self.default_sprite_id in self.sprite_uv_map:
                uv_data[j] = self.sprite_uv_map[self.default_sprite_id]
            else:
                uv_data[j] = [0.0, 0.0, 1.0, 1.0]
            
            # 尺寸数据
            sprite_data = self.sprite_manager.get_sprite(sprite_id)
            if sprite_data and 'rect' in sprite_data:
                width = sprite_data['rect'][2] * self.bullet_scale_factor
                height = sprite_data['rect'][3] * self.bullet_scale_factor
                scale_data[j] = [width, height]
            else:
                scale_data[j] = [default_size * self.bullet_scale_factor,
                                default_size * self.bullet_scale_factor]
        
        self.uv_vbo.write(uv_data.tobytes())
        self.scale_vbo.write(scale_data.tobytes())
        self.bullet_vao.render(moderngl.TRIANGLES, instances=group_size)
    
    def _render_bullets(self, bullet_pool):
        """渲染所有子弹"""
        positions, colors, angles, sprite_ids = bullet_pool.get_active_bullets()
        active_count = len(positions)
        
        if active_count == 0:
            return
        
        # 按纹理路径分组子弹
        bullets_by_texture = {}
        for i in range(active_count):
            sprite_id = sprite_ids[i]
            texture_path = self.sprite_manager.get_sprite_texture_path(sprite_id)
            
            if not texture_path:
                texture_path = next(iter(self.textures.keys())) if self.textures else None
            
            if texture_path:
                if texture_path not in bullets_by_texture:
                    bullets_by_texture[texture_path] = []
                bullets_by_texture[texture_path].append(i)
        
        # 按纹理组渲染
        for texture_path, bullet_indices in bullets_by_texture.items():
            if texture_path in self.textures:
                self.textures[texture_path].use(0)
                
                group_size = len(bullet_indices)
                group_positions = positions[bullet_indices]
                group_angles = angles[bullet_indices]
                group_sprite_ids = sprite_ids[bullet_indices]
                
                self.instance_vbo.write(group_positions.tobytes())
                self.angle_vbo.write(group_angles.tobytes())
                
                # 准备UV数据和尺寸数据
                uv_data = np.zeros((group_size, 4), dtype='f4')
                scale_data = np.zeros((group_size, 2), dtype='f4')
                default_size = 16.0  # 默认尺寸
                
                for j, sprite_id in enumerate(group_sprite_ids):
                    # UV数据
                    if sprite_id in self.sprite_uv_map:
                        uv_data[j] = self.sprite_uv_map[sprite_id]
                    elif self.default_sprite_id and self.default_sprite_id in self.sprite_uv_map:
                        uv_data[j] = self.sprite_uv_map[self.default_sprite_id]
                    else:
                        uv_data[j] = [0.0, 0.0, 1.0, 1.0]
                    
                    # 尺寸数据 - 从精灵配置获取实际尺寸
                    sprite_data = self.sprite_manager.get_sprite(sprite_id)
                    if sprite_data and 'rect' in sprite_data:
                        width = sprite_data['rect'][2] * self.bullet_scale_factor
                        height = sprite_data['rect'][3] * self.bullet_scale_factor
                        scale_data[j] = [width, height]
                    else:
                        scale_data[j] = [default_size * self.bullet_scale_factor, 
                                        default_size * self.bullet_scale_factor]
                
                self.uv_vbo.write(uv_data.tobytes())
                self.scale_vbo.write(scale_data.tobytes())
                self.bullet_vao.render(moderngl.TRIANGLES, instances=group_size)
    
    def _render_player(self, player):
        """渲染玩家"""
        # 检查玩家是否有纹理和精灵信息
        if hasattr(player, 'get_current_sprite') and hasattr(player, 'texture_path'):
            self._render_player_sprite(player)
        else:
            self._render_player_fallback(player)
    
    def _render_player_sprite(self, player):
        """使用纹理渲染玩家"""
        import os
        from PIL import Image
        
        # 延迟加载玩家纹理（不翻转，与sakuya_test.py一致）
        if self.player_texture is None and hasattr(player, 'texture_path'):
            texture_path = player.texture_path
            if os.path.exists(texture_path):
                img = Image.open(texture_path).convert('RGBA')
                # 不翻转纹理，保持原始方向
                self.player_texture = self.ctx.texture(img.size, 4, img.tobytes())
                self.player_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
                self.player_texture_size = img.size
                self.player_texture_scale = 1.0
                print(f"已加载玩家纹理: {texture_path} ({img.size[0]}x{img.size[1]})")
        
        if self.player_texture is None:
            self._render_player_fallback(player)
            return
        
        # 获取当前精灵帧
        sprite_info = player.get_current_sprite()
        if sprite_info is None:
            self._render_player_fallback(player)
            return
        
        # 计算UV坐标（v=0在顶部，v=1在底部）
        tex_w, tex_h = self.player_texture_size
        rect = sprite_info.get('rect', [0, 0, 32, 48])

        downsample = getattr(player, 'render_downsample', False)
        render_size_px = getattr(player, 'render_size_px', None)
        scale = 1.0
        if downsample and render_size_px:
            try:
                scale = min(1.0, float(render_size_px) / max(1.0, float(rect[2])))
            except Exception:
                scale = 1.0

        if downsample and scale < 1.0:
            # 仅在需要时创建缩放纹理，并同步 UV 计算
            if getattr(self, 'player_texture_scale', 1.0) != scale:
                texture_path = player.texture_path
                if os.path.exists(texture_path):
                    img = Image.open(texture_path).convert('RGBA')
                    new_size = (max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale)))
                    img = img.resize(new_size, resample=Image.NEAREST)
                    if self.player_texture:
                        self.player_texture.release()
                    self.player_texture = self.ctx.texture(img.size, 4, img.tobytes())
                    self.player_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
                    self.player_texture_size = img.size
                    self.player_texture_scale = scale
        elif not downsample and getattr(self, 'player_texture_scale', 1.0) != 1.0:
            texture_path = player.texture_path
            if os.path.exists(texture_path):
                img = Image.open(texture_path).convert('RGBA')
                if self.player_texture:
                    self.player_texture.release()
                self.player_texture = self.ctx.texture(img.size, 4, img.tobytes())
                self.player_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
                self.player_texture_size = img.size
                self.player_texture_scale = 1.0

        scaled_rect = [rect[0] * scale, rect[1] * scale, rect[2] * scale, rect[3] * scale]
        u0 = scaled_rect[0] / tex_w
        v0 = scaled_rect[1] / tex_h                    # 顶部
        u1 = (scaled_rect[0] + scaled_rect[2]) / tex_w
        v1 = (scaled_rect[1] + scaled_rect[3]) / tex_h        # 底部
        
        # 计算屏幕位置（转换精灵像素大小到归一化坐标）
        if hasattr(player, 'render_size_px') and player.render_size_px:
            base_w = max(1.0, float(rect[2]))
            scale = float(player.render_size_px) / base_w
            sprite_w = rect[2] * scale / 192.0  # 192 是半屏宽度的像素数
            sprite_h = rect[3] * scale / 192.0
        else:
            sprite_w = rect[2] / 192.0  # 192 是半屏宽度的像素数
            sprite_h = rect[3] / 192.0
        
        px, py = player.pos[0], player.pos[1]
        
        # 6个顶点（2个三角形），UV: v0=顶部, v1=底部
        vertices = np.array([
            # 位置x, 位置y, u, v
            px - sprite_w/2, py - sprite_h/2, u0, v1,  # 左下
            px + sprite_w/2, py - sprite_h/2, u1, v1,  # 右下
            px + sprite_w/2, py + sprite_h/2, u1, v0,  # 右上
            px - sprite_w/2, py - sprite_h/2, u0, v1,  # 左下
            px + sprite_w/2, py + sprite_h/2, u1, v0,  # 右上
            px - sprite_w/2, py + sprite_h/2, u0, v0,  # 左上
        ], dtype='f4')
        
        # 渲染 Options (在自机之下)
        if hasattr(player, 'get_option_positions'):
            self._render_options(player)

        # 渲染自机本体
        self.player_tex_vbo.write(vertices.tobytes())
        self.player_texture.use(0)
        self.player_tex_vao.render(moderngl.TRIANGLES)
    
    def _render_options(self, player):
        """渲染玩家的 Options（支持 v3 OptionEntity 和 v2 模式）"""
        # v3: 使用 option_manager 的渲染数据
        option_manager = getattr(player, 'option_manager', None)
        option_anims = getattr(player, 'option_anims', {})
        has_v3_options = (option_manager and option_manager.options and option_anims)

        if has_v3_options:
            self._render_options_v3(player, option_manager, option_anims)
        else:
            self._render_options_v2(player)

    def _render_options_v3(self, player, option_manager, option_anims):
        """v3: 从 option_anims 配置获取精灵帧，使用对应纹理渲染"""
        import os
        from PIL import Image

        # 确保子弹纹理已加载（option 精灵可能在子弹纹理上）
        bullet_tex_path = getattr(player, 'bullet_texture_path', '') or ''
        if bullet_tex_path and self.player_bullet_texture is None:
            if os.path.exists(bullet_tex_path):
                img = Image.open(bullet_tex_path).convert('RGBA')
                self.player_bullet_texture = self.ctx.texture(img.size, 4, img.tobytes())
                self.player_bullet_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
                self.player_bullet_texture_size = img.size

        sprites = getattr(player, 'sprites', {})
        bullet_sprites = getattr(player, 'bullet_sprites', {}) or {}
        all_sprites = {**sprites, **bullet_sprites}

        for opt in option_manager.options:
            if not opt.active:
                continue
            anim_cfg = option_anims.get(opt.anim_id)
            if not anim_cfg:
                continue
            frames = anim_cfg.get('frames', [])
            if not frames:
                continue

            frame_idx = opt.current_frame % len(frames)
            sprite_name = frames[frame_idx]

            spr_data = all_sprites.get(sprite_name)
            if not spr_data:
                continue
            rect = spr_data.get('rect', [0, 0, 16, 16])
            source = spr_data.get('source', 'player')

            if source == 'bullet' and self.player_bullet_texture is not None:
                tex_obj = self.player_bullet_texture
                tex_size = self.player_bullet_texture_size
            elif self.player_texture is not None:
                tex_obj = self.player_texture
                tex_size = self.player_texture_size
            else:
                continue

            tex_w, tex_h = tex_size
            u0 = rect[0] / tex_w
            v0 = rect[1] / tex_h
            u1 = (rect[0] + rect[2]) / tex_w
            v1 = (rect[1] + rect[3]) / tex_h

            sprite_w = rect[2] / 192.0
            sprite_h = rect[3] / 192.0
            ox, oy = opt.current_x, opt.current_y

            vertices = np.array([
                ox - sprite_w/2, oy - sprite_h/2, u0, v1,
                ox + sprite_w/2, oy - sprite_h/2, u1, v1,
                ox + sprite_w/2, oy + sprite_h/2, u1, v0,
                ox - sprite_w/2, oy - sprite_h/2, u0, v1,
                ox + sprite_w/2, oy + sprite_h/2, u1, v0,
                ox - sprite_w/2, oy + sprite_h/2, u0, v0,
            ], dtype='f4')

            tex_obj.use(0)
            if 'u_alpha' in self.player_tex_program:
                self.player_tex_program['u_alpha'].value = 0.3
            self.player_tex_vbo.write(vertices.tobytes())
            self.player_tex_vao.render(moderngl.TRIANGLES)
            if 'u_alpha' in self.player_tex_program:
                self.player_tex_program['u_alpha'].value = 1.0

    def _render_options_v2(self, player):
        """v2: 在 player.sprites 中查找名含 'option' 的精灵"""
        if self.player_texture is None:
            return

        option_positions = player.get_option_positions()
        if not option_positions:
            return

        option_sprite = None
        if hasattr(player, 'sprites') and player.sprites:
            for key, val in player.sprites.items():
                if 'option' in key.lower():
                    option_sprite = val
                    break

        if option_sprite is None:
            return

        tex_w, tex_h = self.player_texture_size
        rect = option_sprite.get('rect', [0, 0, 16, 16])
        u0 = rect[0] / tex_w
        v0 = rect[1] / tex_h
        u1 = (rect[0] + rect[2]) / tex_w
        v1 = (rect[1] + rect[3]) / tex_h

        sprite_w = rect[2] / 192.0
        sprite_h = rect[3] / 192.0

        self.player_texture.use(0)
        if 'u_alpha' in self.player_tex_program:
            self.player_tex_program['u_alpha'].value = 0.3
        for ox, oy in option_positions:
            vertices = np.array([
                ox - sprite_w/2, oy - sprite_h/2, u0, v1,
                ox + sprite_w/2, oy - sprite_h/2, u1, v1,
                ox + sprite_w/2, oy + sprite_h/2, u1, v0,
                ox - sprite_w/2, oy - sprite_h/2, u0, v1,
                ox + sprite_w/2, oy + sprite_h/2, u1, v0,
                ox - sprite_w/2, oy + sprite_h/2, u0, v0,
            ], dtype='f4')

            self.player_tex_vbo.write(vertices.tobytes())
            self.player_tex_vao.render(moderngl.TRIANGLES)
        if 'u_alpha' in self.player_tex_program:
            self.player_tex_program['u_alpha'].value = 1.0
    
    def _render_player_lasers(self, player):
        """
        渲染玩家激光（连续光柱，从玩家位置延伸到屏幕顶部）
        激光精灵旋转90°后拉伸为竖直光柱
        """
        import os
        from PIL import Image

        lasers = getattr(player, 'player_lasers', None)
        if not lasers:
            return

        # 确保子弹纹理已加载（激光精灵在子弹纹理上）
        bullet_tex_path = getattr(player, 'bullet_texture_path', '') or ''
        if bullet_tex_path and self.player_bullet_texture is None:
            if os.path.exists(bullet_tex_path):
                img = Image.open(bullet_tex_path).convert('RGBA')
                self.player_bullet_texture = self.ctx.texture(img.size, 4, img.tobytes())
                self.player_bullet_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
                self.player_bullet_texture_size = img.size

        bullet_sprites = getattr(player, 'bullet_sprites', {}) or {}
        all_sprites = {**getattr(player, 'sprites', {}), **bullet_sprites}

        for laser in lasers:
            sprite_name = laser.get('sprite', 'laser1')
            spr_data = all_sprites.get(sprite_name)
            if not spr_data:
                continue

            rect = spr_data.get('rect', [0, 0, 6, 12])
            source = spr_data.get('source', 'bullet')

            # 选择纹理
            if source == 'bullet' and self.player_bullet_texture:
                use_tex = self.player_bullet_texture
                use_size = self.player_bullet_texture_size
            elif self.player_texture:
                use_tex = self.player_texture
                use_size = self.player_texture_size
            else:
                continue

            tw, th = use_size

            # 精灵 UV — 加半像素内缩防止 NEAREST 采样到相邻精灵
            u0 = (rect[0] + 0.5) / tw
            v0 = (rect[1] + 0.5) / th
            u1 = (rect[0] + rect[2] - 0.5) / tw
            v1 = (rect[1] + rect[3] - 0.5) / th

            lx = laser['x']
            y_start = laser['y']
            y_end = 1.3  # 屏幕顶部以外

            # 旋转90°后：原始 height(rect[3]) 变为光柱宽度
            beam_half_w = rect[3] / 192.0 / 2.0

            # 90° 顺时针旋转 UV 映射：
            # 屏幕左下(BL) → 原始右下 (u1, v1)
            # 屏幕右下(BR) → 原始右上 (u1, v0)
            # 屏幕右上(TR) → 原始左上 (u0, v0)
            # 屏幕左上(TL) → 原始左下 (u0, v1)
            vertices = np.array([
                lx - beam_half_w, y_start, u1, v1,  # BL
                lx + beam_half_w, y_start, u1, v0,  # BR
                lx + beam_half_w, y_end,   u0, v0,  # TR
                lx - beam_half_w, y_start, u1, v1,  # BL
                lx + beam_half_w, y_end,   u0, v0,  # TR
                lx - beam_half_w, y_end,   u0, v1,  # TL
            ], dtype='f4')

            use_tex.use(0)
            if 'u_alpha' in self.player_tex_program:
                self.player_tex_program['u_alpha'].value = 0.7
            self.player_tex_vbo.write(vertices.tobytes())
            self.player_tex_vao.render(moderngl.TRIANGLES)

        # 渲染完激光后恢复 alpha，避免影响后续自机/Options渲染
        if 'u_alpha' in self.player_tex_program:
            self.player_tex_program['u_alpha'].value = 1.0

    def _render_player_bullets(self, player):
        """渲染玩家子弹（使用独立的子弹纹理或共用自机纹理）"""
        import os
        from PIL import Image

        if not hasattr(player, 'bullet_pool'):
            return

        active = player.bullet_pool.get_active_data()
        count = len(active)
        if count == 0:
            return

        # ---------- 确定子弹纹理 ----------
        bullet_tex_path = getattr(player, 'bullet_texture_path', '') or ''
        player_tex_path = getattr(player, 'texture_path', '') or ''
        tex_path = bullet_tex_path if bullet_tex_path else player_tex_path

        if not tex_path:
            return

        # 延迟加载 / 缓存子弹纹理
        if bullet_tex_path:
            # 独立子弹纹理
            if self.player_bullet_texture is None:
                if os.path.exists(tex_path):
                    img = Image.open(tex_path).convert('RGBA')
                    self.player_bullet_texture = self.ctx.texture(img.size, 4, img.tobytes())
                    self.player_bullet_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
                    self.player_bullet_texture_size = img.size
                    print(f"已加载玩家子弹纹理: {tex_path} ({img.size[0]}x{img.size[1]})")
            tex_obj = self.player_bullet_texture
            tex_size = self.player_bullet_texture_size
        else:
            # 共用自机纹理
            if self.player_texture is None:
                return
            tex_obj = self.player_texture
            tex_size = self.player_texture_size

        if tex_obj is None or tex_size is None:
            return

        tex_w, tex_h = tex_size

        # ---------- 确定精灵查找表 ----------
        bullet_sprites = getattr(player, 'bullet_sprites', {}) or {}
        player_sprites = getattr(player, 'sprites', {}) or {}
        sprite_lookup = bullet_sprites if bullet_sprites else player_sprites

        # ---------- 准备渲染数据 ----------
        positions = active['pos'].copy()
        angles = active['angle'].copy()
        sprite_indices = active['sprite_idx']

        uv_data = np.zeros((count, 4), dtype='f4')
        scale_data = np.zeros((count, 2), dtype='f4')

        default_size = 8.0
        scale_factor = self.bullet_scale_factor
        default_uv = np.array([0.0, 0.0, 1.0, 1.0], dtype='f4')
        default_scale = np.array(
            [default_size * scale_factor, default_size * scale_factor], dtype='f4'
        )

        idx_to_id = player.bullet_pool.sprite_idx_to_id

        # 仅为本帧出现过的 sprite_idx 计算一次 UV/尺寸，降低 Python 循环开销
        unique_sprite_indices = np.unique(sprite_indices)
        per_sprite_render_data = {}
        for sprite_idx in unique_sprite_indices:
            sid = int(sprite_idx)
            sprite_id = idx_to_id.get(sid, '')

            uv = default_uv
            scale = default_scale
            if sprite_id:
                spr = sprite_lookup.get(sprite_id)
                if spr:
                    rect = spr.get('rect')
                    if rect:
                        uv = np.array(
                            [
                                rect[0] / tex_w,
                                rect[1] / tex_h,
                                (rect[0] + rect[2]) / tex_w,
                                (rect[1] + rect[3]) / tex_h,
                            ],
                            dtype='f4',
                        )
                        scale = np.array(
                            [rect[2] * scale_factor, rect[3] * scale_factor], dtype='f4'
                        )
            per_sprite_render_data[sid] = (uv, scale)

        for sprite_idx in unique_sprite_indices:
            sid = int(sprite_idx)
            mask = sprite_indices == sprite_idx
            uv, scale = per_sprite_render_data[sid]
            uv_data[mask] = uv
            scale_data[mask] = scale

        # ---------- 发送到 GPU ----------
        self.instance_vbo.write(positions.tobytes())
        self.angle_vbo.write(angles.tobytes())
        self.uv_vbo.write(uv_data.tobytes())
        self.scale_vbo.write(scale_data.tobytes())

        tex_obj.use(0)
        if 'u_alpha' in self.bullet_program:
            self.bullet_program['u_alpha'].value = 0.3
        self.bullet_vao.render(moderngl.TRIANGLES, instances=count)
        if 'u_alpha' in self.bullet_program:
            self.bullet_program['u_alpha'].value = 1.0
    
    def _render_player_fallback(self, player):
        """备用：纯色渲染玩家"""
        player_size = 0.01 if player.is_focused else 0.02
        player_vertices = np.array([
            player.pos[0] - player_size, player.pos[1] + player_size,
            player.pos[0] - player_size, player.pos[1] - player_size,
            player.pos[0] + player_size, player.pos[1] + player_size,
            player.pos[0] + player_size, player.pos[1] + player_size,
            player.pos[0] - player_size, player.pos[1] - player_size,
            player.pos[0] + player_size, player.pos[1] - player_size,
        ], dtype='f4')
        self.player_vbo.write(player_vertices.tobytes())
        self.player_vao.render(moderngl.TRIANGLES)
    
    def _render_boss(self, stage_manager):
        """渲染Boss（优先使用精灵动画，fallback 到纯色占位）"""
        # 程序化关卡中 Boss 由 StageScript._current_boss 持有，
        # 未注册到旧 BossManager；两处都看一下。
        active_boss = None
        cur_stage = getattr(stage_manager, 'current_stage', None)
        if cur_stage is not None:
            active_boss = getattr(cur_stage, '_current_boss', None)
        if active_boss is None:
            active_boss = stage_manager.get_active_boss()
        if not (active_boss and active_boss.alive):
            return

        # BossBase 用 x/y，旧 Boss 用 pos；兼容两种
        if hasattr(active_boss, 'pos'):
            bx, by = active_boss.pos[0], active_boss.pos[1]
        else:
            bx, by = active_boss.x, active_boss.y

        frame, texture_path = None, None
        if hasattr(active_boss, 'get_render_frame'):
            frame, texture_path = active_boss.get_render_frame()

        if frame is not None and texture_path and texture_path in self.textures:
            rect = list(frame.rect)
            tex_w, tex_h = self.textures[texture_path].size
            u0 = rect[0] / tex_w
            u1 = (rect[0] + rect[2]) / tex_w
            v0 = 1.0 - (rect[1] + rect[3]) / tex_h
            v1 = 1.0 - rect[1] / tex_h
            # boss sprites are 96px on a ~384px-wide field → /192 gives 0.5 units (good for boss)
            sw = rect[2] / 192.0
            sh = rect[3] / 192.0
            vertices = np.array([
                bx - sw/2, by - sh/2, u0, v0,
                bx + sw/2, by - sh/2, u1, v0,
                bx + sw/2, by + sh/2, u1, v1,
                bx - sw/2, by - sh/2, u0, v0,
                bx + sw/2, by + sh/2, u1, v1,
                bx - sw/2, by + sh/2, u0, v1,
            ], dtype='f4')
            self.player_tex_vbo.write(vertices.tobytes())
            self.textures[texture_path].use(0)
            self.player_tex_vao.render(moderngl.TRIANGLES)
        else:
            boss_size = 0.05
            boss_vertices = np.array([
                bx - boss_size, by + boss_size,
                bx - boss_size, by - boss_size,
                bx + boss_size, by + boss_size,
                bx + boss_size, by + boss_size,
                bx - boss_size, by - boss_size,
                bx + boss_size, by - boss_size,
            ], dtype='f4')
            self.player_vbo.write(boss_vertices.tobytes())
            self.player_vao.render(moderngl.TRIANGLES)
    
    def _render_enemies(self, stage_manager, enemy_scripts=None):
        """渲染敌人"""
        # 新的敌人系统（EnemyScript实例）
        if enemy_scripts:
            for enemy in enemy_scripts:
                if hasattr(enemy, '_active') and enemy._active:
                    self._render_enemy_sprite(enemy)

        # 旧的敌人系统（Enemy对象）- fallback
        active_enemies = stage_manager.get_active_enemies()
        for enemy in active_enemies:
            if enemy.alive:
                enemy_size = 0.03
                enemy_vertices = np.array([
                    enemy.pos[0] - enemy_size, enemy.pos[1] + enemy_size,
                    enemy.pos[0] - enemy_size, enemy.pos[1] - enemy_size,
                    enemy.pos[0] + enemy_size, enemy.pos[1] + enemy_size,
                    enemy.pos[0] + enemy_size, enemy.pos[1] + enemy_size,
                    enemy.pos[0] - enemy_size, enemy.pos[1] - enemy_size,
                    enemy.pos[0] + enemy_size, enemy.pos[1] - enemy_size,
                ], dtype='f4')
                self.player_vbo.write(enemy_vertices.tobytes())
                self.player_vao.render(moderngl.TRIANGLES)

    def _render_enemy_sprite(self, enemy):
        """使用纹理渲染单个敌人（支持贴图对象自动动画）"""
        # 优先使用贴图对象（EnemyRenderObject）
        frame = None
        texture_path = None

        if hasattr(enemy, 'get_render_frame'):
            frame, texture_path = enemy.get_render_frame()

        if frame is not None and texture_path and texture_path in self.textures:
            rect = list(frame.rect)
        else:
            # 退回到直接查找精灵/动画
            sprite_id = getattr(enemy, 'sprite', None)
            if not sprite_id:
                self._render_enemy_fallback(enemy)
                return

            sprite_data = self.sprite_manager.get_sprite(sprite_id)
            if not sprite_data:
                animation = self.sprite_manager.asset_manager.get_animation(sprite_id)
                if animation and hasattr(animation, 'frames') and len(animation.frames) > 0:
                    enemy_time = getattr(enemy, '_time', 0) / 60.0
                    current_frame = animation.get_frame_at_time(enemy_time)
                    sprite_data = {
                        'rect': list(current_frame.rect),
                        'center': list(current_frame.center)
                    }
                    texture_path = animation.texture_path

            if not sprite_data:
                self._render_enemy_fallback(enemy)
                return

            if not texture_path:
                texture_path = self.sprite_manager.get_sprite_texture_path(sprite_id)

            if not texture_path or texture_path not in self.textures:
                self._render_enemy_fallback(enemy)
                return

            rect = sprite_data.get('rect', [0, 0, 32, 32])

        # 计算UV坐标（纹理以flip_y=True加载，需要翻转V坐标）
        tex_w, tex_h = self.textures[texture_path].size
        u0 = rect[0] / tex_w
        u1 = (rect[0] + rect[2]) / tex_w
        v0 = 1.0 - (rect[1] + rect[3]) / tex_h
        v1 = 1.0 - rect[1] / tex_h

        # 计算屏幕尺寸
        sprite_w = rect[2] / 192.0
        sprite_h = rect[3] / 192.0

        px, py = enemy.x, enemy.y

        vertices = np.array([
            px - sprite_w/2, py - sprite_h/2, u0, v0,
            px + sprite_w/2, py - sprite_h/2, u1, v0,
            px + sprite_w/2, py + sprite_h/2, u1, v1,
            px - sprite_w/2, py - sprite_h/2, u0, v0,
            px + sprite_w/2, py + sprite_h/2, u1, v1,
            px - sprite_w/2, py + sprite_h/2, u0, v1,
        ], dtype='f4')

        self.player_tex_vbo.write(vertices.tobytes())
        self.textures[texture_path].use(0)
        self.player_tex_vao.render(moderngl.TRIANGLES)

    def _render_enemy_fallback(self, enemy):
        """备用：纯色渲染敌人"""
        enemy_size = 0.03
        enemy_vertices = np.array([
            enemy.x - enemy_size, enemy.y + enemy_size,
            enemy.x - enemy_size, enemy.y - enemy_size,
            enemy.x + enemy_size, enemy.y + enemy_size,
            enemy.x + enemy_size, enemy.y + enemy_size,
            enemy.x - enemy_size, enemy.y - enemy_size,
            enemy.x + enemy_size, enemy.y - enemy_size,
        ], dtype='f4')
        self.player_vbo.write(enemy_vertices.tobytes())
        self.player_vao.render(moderngl.TRIANGLES)
    
    def _render_hitbox(self, player):
        """渲染玩家判定点"""
        hx, hy = player.get_hit_position()
        if not self._ensure_hitbox_texture():
            return

        tex_w, tex_h = self.hitbox_texture_size
        visual_w = tex_w / 192.0
        visual_h = tex_h / 192.0
        angle = time.perf_counter() * 3.0

        self.hitbox_texture.use(0)
        if 'u_alpha' in self.player_tex_program:
            self.player_tex_program['u_alpha'].value = 0.82
        self._render_hitbox_layer(hx, hy, visual_w, visual_h, angle)
        self._render_hitbox_layer(hx, hy, visual_w, visual_h, -angle)
        if 'u_alpha' in self.player_tex_program:
            self.player_tex_program['u_alpha'].value = 1.0

    def _ensure_hitbox_texture(self):
        if self.hitbox_texture is not None:
            return True

        if not os.path.exists(self.hitbox_texture_path):
            return False

        from PIL import Image
        img = Image.open(self.hitbox_texture_path).convert('RGBA')
        self.hitbox_texture = self.ctx.texture(img.size, 4, img.tobytes())
        self.hitbox_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.hitbox_texture_size = img.size
        return True

    def _render_hitbox_layer(self, hx, hy, width, height, angle):
        half_w = width * 0.5
        half_h = height * 0.5
        ca = math.cos(angle)
        sa = math.sin(angle)
        corners = (
            (-half_w, -half_h, 0.0, 1.0),
            ( half_w, -half_h, 1.0, 1.0),
            ( half_w,  half_h, 1.0, 0.0),
            (-half_w, -half_h, 0.0, 1.0),
            ( half_w,  half_h, 1.0, 0.0),
            (-half_w,  half_h, 0.0, 0.0),
        )
        vertices = []
        for ox, oy, u, v in corners:
            x = hx + ox * ca - oy * sa
            y = hy + ox * sa + oy * ca
            vertices.extend([x, y, u, v])

        self.player_tex_vbo.write(np.array(vertices, dtype='f4').tobytes())
        self.player_tex_vao.render(moderngl.TRIANGLES)
    
    def cleanup(self):
        """清理渲染资源"""
        # ModernGL的资源会自动释放，但可以显式释放
        if hasattr(self, 'optimized_bullet_renderer') and self.optimized_bullet_renderer:
            self.optimized_bullet_renderer.cleanup()
        if self.hitbox_texture is not None:
            self.hitbox_texture.release()
            self.hitbox_texture = None

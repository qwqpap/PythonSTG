"""
渲染器类 - 负责所有OpenGL渲染逻辑
"""
import moderngl
import numpy as np
import math
from .laser_renderer import LaserRenderer


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
        self.textures = textures
        self.sprite_uv_map = sprite_uv_map
        
        # 获取默认精灵
        self.default_sprite_id = 'star_small1' if 'star_small1' in sprite_manager.get_all_sprite_ids() else next(iter(sprite_manager.get_all_sprite_ids()), None)
        
        # 初始化着色器和渲染资源
        self._init_bullet_shader()
        self._init_player_shader()
        self._init_circle_shader()
        
        # 初始化激光渲染器
        self.laser_renderer = LaserRenderer(ctx, base_size)
    
    def _init_bullet_shader(self):
        """初始化子弹渲染着色器和VAO"""
        # 顶点着色器：接收位置并转换到裁剪空间，支持实例化偏移、角度和UV坐标
        vertex_shader = """
        #version 330
        in vec2 in_vert;
        in vec2 in_uv_base;
        in vec2 in_offset;
        in float in_angle;
        in vec4 in_uv_offset;
        
        out vec2 v_uv;
        
        void main() {
            // 计算旋转矩阵
            float s = sin(in_angle);
            float c = cos(in_angle);
            vec2 rotated = vec2(in_vert.x * c - in_vert.y * s, in_vert.x * s + in_vert.y * c);
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
        in vec2 v_uv;
        out vec4 f_color;
        void main() {
            vec4 tex_color = texture(u_texture, v_uv);
            f_color = tex_color;
        }
        """
        
        self.bullet_program = self.ctx.program(vertex_shader=vertex_shader, fragment_shader=fragment_shader)
        self.bullet_program['u_texture'].value = 0
        
        # 准备顶点数据
        default_sprite_size = [16, 16]
        if self.default_sprite_id:
            sprite_data = self.sprite_manager.get_sprite(self.default_sprite_id)
            default_sprite_size = [sprite_data['rect'][2], sprite_data['rect'][3]]
        
        scale_factor = 2.0 / self.base_size[1]
        width = default_sprite_size[0] * scale_factor
        height = default_sprite_size[1] * scale_factor
        half_width = width / 2.0
        half_height = height / 2.0
        
        vertices = np.array([
            -half_width,  half_height, 0.0, 0.0,
            -half_width, -half_height, 0.0, 1.0,
             half_width,  half_height, 1.0, 0.0,
             half_width,  half_height, 1.0, 0.0,
            -half_width, -half_height, 0.0, 1.0,
             half_width, -half_height, 1.0, 1.0,
        ], dtype='f4')
        
        self.bullet_vbo = self.ctx.buffer(vertices.tobytes())
        
        # 实例化数据VBO
        self.instance_vbo = self.ctx.buffer(reserve=50000 * 2 * 4)
        self.angle_vbo = self.ctx.buffer(reserve=50000 * 1 * 4)
        self.uv_vbo = self.ctx.buffer(reserve=50000 * 4 * 4)
        
        # 创建VAO
        self.bullet_vao = self.ctx.vertex_array(
            self.bullet_program,
            [(self.bullet_vbo, '2f 2f', 'in_vert', 'in_uv_base'),
             (self.instance_vbo, '2f/i', 'in_offset'),
             (self.angle_vbo, '1f/i', 'in_angle'),
             (self.uv_vbo, '4f/i', 'in_uv_offset')]
        )
    
    def _init_player_shader(self):
        """初始化玩家/敌人/Boss渲染着色器和VAO"""
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
    
    def render_frame(self, bullet_pool, player, stage_manager, laser_pool=None, viewport_rect=None):
        """
        渲染一帧
        
        Args:
            bullet_pool: 子弹池对象
            player: 玩家对象
            stage_manager: 关卡管理器对象
            laser_pool: 激光池对象（可选）
            viewport_rect: (x, y, width, height)，游戏区域在窗口中的视口
        """
        # 保存并切换视口到游戏区域
        prev_viewport = self.ctx.viewport
        if viewport_rect:
            self.ctx.viewport = viewport_rect
        # 清屏
        self.ctx.clear(0.1, 0.1, 0.1)
        
        # 渲染激光（在子弹之前渲染，作为背景层）
        if laser_pool:
            lasers, bent_lasers = laser_pool.get_all_lasers()
            self.laser_renderer.render_lasers(lasers)
            self.laser_renderer.render_bent_lasers(bent_lasers)
        
        # 渲染子弹
        self._render_bullets(bullet_pool)
        
        # 渲染玩家
        self._render_player(player)
        
        # 渲染Boss
        self._render_boss(stage_manager)
        
        # 渲染敌人
        self._render_enemies(stage_manager)
        
        # 渲染判定点
        if player.is_focused:
            self._render_hitbox(player)
        # 还原视口
        self.ctx.viewport = prev_viewport
    
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
                
                # 准备UV数据
                uv_data = np.zeros((group_size, 4), dtype='f4')
                for j, sprite_id in enumerate(group_sprite_ids):
                    if sprite_id in self.sprite_uv_map:
                        uv_data[j] = self.sprite_uv_map[sprite_id]
                    elif self.default_sprite_id and self.default_sprite_id in self.sprite_uv_map:
                        uv_data[j] = self.sprite_uv_map[self.default_sprite_id]
                    else:
                        uv_data[j] = [0.0, 0.0, 1.0, 1.0]
                
                self.uv_vbo.write(uv_data.tobytes())
                self.bullet_vao.render(moderngl.TRIANGLES, instances=group_size)
    
    def _render_player(self, player):
        """渲染玩家"""
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
        """渲染Boss"""
        active_boss = stage_manager.get_active_boss()
        if active_boss and active_boss.alive:
            boss_size = 0.05
            boss_vertices = np.array([
                active_boss.pos[0] - boss_size, active_boss.pos[1] + boss_size,
                active_boss.pos[0] - boss_size, active_boss.pos[1] - boss_size,
                active_boss.pos[0] + boss_size, active_boss.pos[1] + boss_size,
                active_boss.pos[0] + boss_size, active_boss.pos[1] + boss_size,
                active_boss.pos[0] - boss_size, active_boss.pos[1] - boss_size,
                active_boss.pos[0] + boss_size, active_boss.pos[1] - boss_size,
            ], dtype='f4')
            self.player_vbo.write(boss_vertices.tobytes())
            self.player_vao.render(moderngl.TRIANGLES)
    
    def _render_enemies(self, stage_manager):
        """渲染敌人"""
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
    
    def _render_hitbox(self, player):
        """渲染玩家判定点"""
        circle_radius = player.hit_radius
        circle_vertices = []
        for i in range(self.circle_segments + 1):
            a = 2 * math.pi * i / self.circle_segments
            x = player.pos[0] + math.cos(a) * circle_radius
            y = player.pos[1] + math.sin(a) * circle_radius
            circle_vertices.extend([x, y])
        circle_vertices = np.array(circle_vertices, dtype='f4')
        self.circle_vbo.write(circle_vertices.tobytes())
        self.circle_vao.render(moderngl.LINE_STRIP)
    
    def cleanup(self):
        """清理渲染资源"""
        # ModernGL的资源会自动释放，但可以显式释放
        pass

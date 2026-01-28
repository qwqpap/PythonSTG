"""
玩家子弹渲染器
使用 instanced rendering 高效渲染玩家子弹
"""
import numpy as np
import moderngl
from typing import Optional

from .renderer import Renderer


class PlayerBulletRenderer:
    """玩家子弹渲染器"""
    
    def __init__(self, ctx: moderngl.Context, renderer: Renderer):
        """
        初始化渲染器
        :param ctx: ModernGL上下文
        :param renderer: 主渲染器（用于获取shader和纹理）
        """
        self.ctx = ctx
        self.renderer = renderer
        
        # 使用主渲染器的shader
        self.program = renderer.program
        
        # 创建实例缓冲区
        self.max_bullets = 2000
        self.instance_data = np.zeros(self.max_bullets, dtype=[
            ('pos', 'f4', 2),
            ('scale', 'f4', 2),
            ('uv_offset', 'f4', 2),
            ('uv_scale', 'f4', 2),
            ('color', 'f4', 4),
            ('angle', 'f4'),
        ])
        
        self.instance_buffer: Optional[moderngl.Buffer] = None
        self.vao: Optional[moderngl.VertexArray] = None
        
        # 精灵UV缓存
        self.sprite_uvs = {}
    
    def init_buffers(self, quad_vbo):
        """
        初始化缓冲区
        :param quad_vbo: 共享的quad顶点缓冲区
        """
        # 创建实例缓冲区
        self.instance_buffer = self.ctx.buffer(reserve=self.instance_data.nbytes)
        
        # 创建VAO
        self.vao = self.ctx.vertex_array(
            self.program,
            [
                (quad_vbo, '2f 2f', 'in_vert', 'in_uv'),
                (self.instance_buffer, '2f 2f 2f 2f 4f 1f /i', 
                 'in_pos', 'in_scale', 'in_uv_offset', 'in_uv_scale', 'in_color', 'in_angle'),
            ]
        )
    
    def set_sprite_uv(self, sprite_id: str, uv_offset: tuple, uv_scale: tuple):
        """
        设置精灵UV映射
        :param sprite_id: 精灵ID
        :param uv_offset: UV偏移 (u, v)
        :param uv_scale: UV缩放 (w, h)
        """
        self.sprite_uvs[sprite_id] = (uv_offset, uv_scale)
    
    def render(self, bullet_pool, texture: moderngl.Texture, 
               sprite_id_to_uv: dict = None):
        """
        渲染玩家子弹
        :param bullet_pool: 玩家子弹池
        :param texture: 子弹纹理
        :param sprite_id_to_uv: 精灵ID到UV的映射
        """
        if self.vao is None:
            return
        
        # 获取活跃子弹数据
        active_mask = bullet_pool.data['alive'] == 1
        active_count = np.sum(active_mask)
        
        if active_count == 0:
            return
        
        active_data = bullet_pool.data[active_mask]
        
        # 填充实例数据
        count = min(active_count, self.max_bullets)
        
        for i in range(count):
            bullet = active_data[i]
            
            # 位置
            self.instance_data[i]['pos'] = bullet['pos']
            
            # 缩放
            scale = bullet['scale']
            self.instance_data[i]['scale'] = [scale * 0.03, scale * 0.03]  # 基础大小
            
            # UV
            sprite_idx = bullet['sprite_idx']
            sprite_id = bullet_pool.sprite_idx_to_id.get(sprite_idx, '')
            
            if sprite_id_to_uv and sprite_id in sprite_id_to_uv:
                uv_data = sprite_id_to_uv[sprite_id]
                self.instance_data[i]['uv_offset'] = uv_data[0]
                self.instance_data[i]['uv_scale'] = uv_data[1]
            elif sprite_id in self.sprite_uvs:
                uv_offset, uv_scale = self.sprite_uvs[sprite_id]
                self.instance_data[i]['uv_offset'] = uv_offset
                self.instance_data[i]['uv_scale'] = uv_scale
            else:
                # 默认UV（整个纹理）
                self.instance_data[i]['uv_offset'] = [0.0, 0.0]
                self.instance_data[i]['uv_scale'] = [1.0, 1.0]
            
            # 颜色
            self.instance_data[i]['color'] = bullet['color']
            self.instance_data[i]['color'][3] *= bullet['alpha']
            
            # 角度
            self.instance_data[i]['angle'] = bullet['angle']
        
        # 上传数据
        self.instance_buffer.write(self.instance_data[:count].tobytes())
        
        # 绑定纹理并渲染
        texture.use(0)
        self.vao.render(moderngl.TRIANGLE_STRIP, instances=count)
    
    def release(self):
        """释放资源"""
        if self.instance_buffer:
            self.instance_buffer.release()
        if self.vao:
            self.vao.release()


class PlayerRenderer:
    """玩家渲染器（包括Option）"""
    
    def __init__(self, ctx: moderngl.Context, renderer: Renderer):
        """
        初始化渲染器
        :param ctx: ModernGL上下文
        :param renderer: 主渲染器
        """
        self.ctx = ctx
        self.renderer = renderer
        
        # 子弹渲染器
        self.bullet_renderer = PlayerBulletRenderer(ctx, renderer)
    
    def init_buffers(self, quad_vbo):
        """初始化缓冲区"""
        self.bullet_renderer.init_buffers(quad_vbo)
    
    def render_player(self, player, texture: moderngl.Texture, 
                      sprite_uvs: dict = None):
        """
        渲染玩家本体
        :param player: 玩家对象
        :param texture: 玩家纹理
        :param sprite_uvs: 精灵UV映射
        """
        # 获取当前精灵
        sprite_id = player.get_current_sprite()
        
        # 获取渲染透明度（无敌闪烁）
        alpha = player.get_render_alpha()
        
        # 使用主渲染器的精灵渲染
        if sprite_uvs and sprite_id in sprite_uvs:
            uv_data = sprite_uvs[sprite_id]
            self.renderer.draw_sprite(
                player.pos[0], player.pos[1],
                0.1, 0.1,  # 玩家大小
                uv_data[0], uv_data[1],
                alpha=alpha
            )
        else:
            # 默认渲染
            self.renderer.draw_sprite(
                player.pos[0], player.pos[1],
                0.1, 0.1,
                (0, 0), (1, 1),
                alpha=alpha
            )
    
    def render_options(self, player, texture: moderngl.Texture,
                       sprite_uvs: dict = None):
        """
        渲染Option
        :param player: 玩家对象
        :param texture: Option纹理
        :param sprite_uvs: 精灵UV映射
        """
        option_data = player.shot_system.get_option_render_data()
        
        for x, y, sprite_id in option_data:
            if sprite_uvs and sprite_id in sprite_uvs:
                uv_data = sprite_uvs[sprite_id]
                self.renderer.draw_sprite(
                    x, y,
                    0.04, 0.04,  # Option大小
                    uv_data[0], uv_data[1]
                )
    
    def render_hit_point(self, player, texture: moderngl.Texture = None):
        """
        渲染判定点（低速模式显示）
        :param player: 玩家对象
        :param texture: 判定点纹理
        """
        if not player.is_focused:
            return
        
        x, y = player.get_hit_position()
        
        # 简单的判定点渲染（可以用纹理替换）
        self.renderer.draw_sprite(
            x, y,
            0.02, 0.02,
            (0, 0), (1, 1),
            color=(1.0, 0.3, 0.3, 0.8)
        )
    
    def render_bullets(self, player, texture: moderngl.Texture,
                       sprite_id_to_uv: dict = None):
        """
        渲染玩家子弹
        :param player: 玩家对象
        :param texture: 子弹纹理
        :param sprite_id_to_uv: 精灵UV映射
        """
        self.bullet_renderer.render(
            player.bullet_pool, 
            texture,
            sprite_id_to_uv
        )
    
    def release(self):
        """释放资源"""
        self.bullet_renderer.release()

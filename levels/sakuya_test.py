"""
咲夜测试关卡
测试咲夜自机的各种功能 - 使用脚本系统
"""
import pygame
import moderngl
import numpy as np
from PIL import Image
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.game.player import PlayerBase, load_player


class SakuyaTestLevel:
    """咲夜测试关卡"""
    
    def __init__(self, width=800, height=600):
        pygame.init()
        pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
        pygame.display.set_caption("咲夜测试 - Sakuya Test (Script-Based)")
        
        self.width = width
        self.height = height
        self.ctx = moderngl.create_context()
        
        # 使用脚本系统加载咲夜
        # load_player 会自动加载 assets/players/sakuya/config.json
        # 并根据 config.json 中的 "script" 字段加载 script.py
        self.player = load_player("sakuya")
        self.player.pos = np.array([0.0, -0.7], dtype=np.float32)
        
        # 检查脚本是否加载成功
        if self.player.script:
            print(f"✓ 脚本加载成功: {type(self.player.script).__name__}")
        else:
            print("✗ 警告: 未加载脚本，使用默认行为")
        
        # 加载纹理
        self.textures = {}
        self._load_textures()
        
        # 创建着色器
        self._create_shaders()
        
        # 游戏状态
        self.running = True
        self.clock = pygame.time.Clock()
        self.frame_count = 0
        
        # 假敌人（用于测试追踪）
        self.test_enemies = [
            {'pos': [0.3, 0.5], 'active': True},
            {'pos': [-0.3, 0.3], 'active': True},
        ]
    
    def _load_textures(self):
        """加载纹理"""
        sakuya_path = os.path.join('assets', 'players', 'sakuya', 'sakuya.png')
        
        if os.path.exists(sakuya_path):
            img = Image.open(sakuya_path).convert('RGBA')
            self.textures['sakuya'] = self.ctx.texture(img.size, 4, img.tobytes())
            self.textures['sakuya'].filter = (moderngl.NEAREST, moderngl.NEAREST)
            print(f"Loaded sakuya texture: {img.size}")
        else:
            print(f"Warning: {sakuya_path} not found")
    
    def _create_shaders(self):
        """创建着色器"""
        # 简单的精灵着色器
        vertex_shader = """
        #version 330
        in vec2 in_pos;
        in vec2 in_uv;
        out vec2 uv;
        uniform vec2 offset;
        uniform vec2 scale;
        void main() {
            gl_Position = vec4(in_pos * scale + offset, 0.0, 1.0);
            uv = in_uv;
        }
        """
        
        fragment_shader = """
        #version 330
        in vec2 uv;
        out vec4 fragColor;
        uniform sampler2D tex;
        uniform vec4 uv_rect;  // x, y, w, h in normalized coords
        void main() {
            vec2 tex_uv = uv_rect.xy + uv * uv_rect.zw;
            fragColor = texture(tex, tex_uv);
            if (fragColor.a < 0.1) discard;
        }
        """
        
        self.prog = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader
        )
        
        # 创建四边形顶点
        vertices = np.array([
            -0.5, -0.5, 0.0, 1.0,
             0.5, -0.5, 1.0, 1.0,
             0.5,  0.5, 1.0, 0.0,
            -0.5,  0.5, 0.0, 0.0,
        ], dtype='f4')
        
        indices = np.array([0, 1, 2, 0, 2, 3], dtype='i4')
        
        self.vbo = self.ctx.buffer(vertices)
        self.ibo = self.ctx.buffer(indices)
        
        self.vao = self.ctx.vertex_array(
            self.prog,
            [(self.vbo, '2f 2f', 'in_pos', 'in_uv')],
            self.ibo
        )
    
    def run(self):
        """运行游戏循环"""
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            
            self._handle_events()
            self._update(dt)
            self._render()
            
            pygame.display.flip()
            self.frame_count += 1
        
        pygame.quit()
    
    def _handle_events(self):
        """处理事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    # 重置位置
                    self.player.pos = np.array([0.0, -0.7], dtype=np.float32)
    
    def _update(self, dt: float):
        """更新游戏状态"""
        # 直接传递 pygame 的键盘状态（是一个可索引的序列）
        keys = pygame.key.get_pressed()
        
        # 更新玩家
        self.player.update(dt, keys)
        
        # 寻找目标（通过脚本设置）
        if self.player.is_focused and self.player.script:
            enemy_positions = [e['pos'] for e in self.test_enemies if e['active']]
            if enemy_positions:
                # 找最近的
                min_dist = float('inf')
                nearest = None
                for pos in enemy_positions:
                    dx = pos[0] - self.player.pos[0]
                    dy = pos[1] - self.player.pos[1]
                    dist = dx*dx + dy*dy
                    if dist < min_dist:
                        min_dist = dist
                        nearest = pos
                # 通过脚本设置目标
                if hasattr(self.player.script, 'set_target'):
                    self.player.script.set_target(tuple(nearest) if nearest else None)
        elif self.player.script and hasattr(self.player.script, 'set_target'):
            self.player.script.set_target(None)
        
        # 显示状态信息（每60帧一次）
        if self.frame_count % 60 == 0:
            state = self.player.get_state_info()
            spread = state.get('spread_range')
            spread_str = f"{spread:.1f}" if spread is not None else "N/A"
            target = state.get('target_angle')
            target_str = f"{target:.1f}" if target is not None else "90.0"
            print(f"Pos: ({self.player.pos[0]:.2f}, {self.player.pos[1]:.2f}) | "
                  f"Focused: {self.player.is_focused} | "
                  f"Spread: {spread_str} | "
                  f"Target: {target_str}° | "
                  f"Bullets: {state.get('bullet_count', 0)} | "
                  f"Options: {state.get('option_count', 0)}")
    
    def _render(self):
        """渲染"""
        self.ctx.clear(0.1, 0.1, 0.2, 1.0)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        
        if 'sakuya' not in self.textures:
            return
        
        tex = self.textures['sakuya']
        tex.use(0)
        self.prog['tex'] = 0
        
        tex_w, tex_h = tex.size
        
        # 渲染玩家
        self._render_player(tex_w, tex_h)
        
        # 渲染子机
        self._render_options(tex_w, tex_h)
        
        # 渲染子弹
        self._render_bullets(tex_w, tex_h)
        
        # 渲染测试敌人
        self._render_test_enemies()
    
    def _render_player(self, tex_w, tex_h):
        """渲染玩家"""
        # 根据动画状态选择帧
        state = self.player.animation.current_state.value if hasattr(self.player.animation, 'current_state') else 0
        frame = int(self.frame_count / 5) % 8
        
        # 计算UV（32x48, 8列3行）
        row = 0  # idle
        if state == 1:  # left
            row = 1
        elif state == 2:  # right
            row = 2
        
        u = (frame * 32) / tex_w
        v = (row * 48) / tex_h
        uw = 32 / tex_w
        vh = 48 / tex_h
        
        self.prog['uv_rect'] = (u, v, uw, vh)
        self.prog['offset'] = (self.player.pos[0], self.player.pos[1])
        self.prog['scale'] = (0.08, 0.12)  # 适当缩放
        
        self.vao.render(moderngl.TRIANGLES)
    
    def _render_options(self, tex_w, tex_h):
        """渲染子机"""
        option_data = self.player.get_option_render_data()
        
        for x, y, frame_idx in option_data:
            # 子机动画 (16x16, 8列2行, 从128,144开始)
            col = frame_idx % 8
            row = frame_idx // 8
            
            u = (128 + col * 16) / tex_w
            v = (144 + row * 16) / tex_h
            uw = 16 / tex_w
            vh = 16 / tex_h
            
            self.prog['uv_rect'] = (u, v, uw, vh)
            self.prog['offset'] = (x, y)
            self.prog['scale'] = (0.04, 0.04)
            
            self.vao.render(moderngl.TRIANGLES)
    
    def _render_bullets(self, tex_w, tex_h):
        """渲染子弹"""
        pool = self.player.bullet_pool
        
        for i in range(pool.max_bullets):
            if not pool.data[i]['alive']:
                continue
            
            x, y = pool.data[i]['pos']
            angle = pool.data[i]['angle']
            
            # 根据精灵索引选择UV（简化处理，都用蓝飞刀）
            # knife_blue: 0,160, 32x16
            u = 0 / tex_w
            v = 160 / tex_h
            uw = 32 / tex_w
            vh = 16 / tex_h
            
            self.prog['uv_rect'] = (u, v, uw, vh)
            self.prog['offset'] = (x, y)
            self.prog['scale'] = (0.04, 0.02)
            
            self.vao.render(moderngl.TRIANGLES)
    
    def _render_test_enemies(self):
        """渲染测试敌人（简单的红色方块）"""
        # 这里简化处理，实际应该用敌人精灵
        pass


if __name__ == '__main__':
    level = SakuyaTestLevel()
    level.run()

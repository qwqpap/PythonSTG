"""
背景配置可视化编辑器

实时编辑背景参数并预览效果
"""

import pygame
import moderngl
import json
import os
import sys
from typing import Optional, Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.game.background_render.background_renderer import BackgroundRenderer
from src.game.background_render.data_driven_background import (
    DataDrivenBackground, 
    list_available_backgrounds,
    BlendMode
)


class BackgroundEditor:
    """背景配置编辑器"""
    
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("背景编辑器 - Background Editor")
        
        # 窗口布局: 左侧预览区(768x896 - 匹配游戏弹幕区域) | 右侧控制面板(400px)
        self.preview_width = 768   # 384 * 2
        self.preview_height = 896  # 448 * 2
        self.panel_width = 400
        
        self.width = self.preview_width + self.panel_width
        self.height = self.preview_height  # 窗口高度与预览区一致
        
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        
        self.screen = pygame.display.set_mode(
            (self.width, self.height),
            pygame.OPENGL | pygame.DOUBLEBUF
        )
        
        self.ctx = moderngl.create_context()
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
        
        # 创建背景渲染器 - 使用游戏的基础逻辑尺寸
        self.base_size = (384, 448)  # 游戏弹幕区域逻辑尺寸
        self.bg_renderer = BackgroundRenderer(self.ctx, self.base_size)
        
        # 数据驱动背景
        self.background = DataDrivenBackground(self.bg_renderer)
        
        # UI 状态
        self.available_backgrounds = list_available_backgrounds()
        self.current_bg_index = 0
        self.selected_layer = 0
        self.scroll_offset = 0
        self.show_help = True
        self.paused = False
        
        # 编辑模式
        self.edit_mode = "camera"  # camera, fog, scroll, layer
        self.edit_param = 0
        
        # 字体 - 使用支持中文的字体
        chinese_font = "Microsoft YaHei"  # 微软雅黑
        self.font = pygame.font.SysFont(chinese_font, 18)
        self.font_small = pygame.font.SysFont(chinese_font, 16)
        self.font_title = pygame.font.SysFont(chinese_font, 24)
        
        # 加载第一个背景
        if self.available_backgrounds:
            self.load_background(self.available_backgrounds[0])
    
    def load_background(self, name: str) -> bool:
        """加载背景"""
        success = self.background.load_by_name(name)
        if success:
            self.selected_layer = 0
        return success
    
    def run(self):
        """运行编辑器"""
        clock = pygame.time.Clock()
        running = True
        
        while running:
            dt = clock.tick(60) / 1000.0
            
            # 事件处理
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self.handle_key(event)
                elif event.type == pygame.MOUSEWHEEL:
                    self.handle_scroll(event)
            
            # 更新
            if not self.paused:
                self.background.update(dt)
            
            # 渲染
            self.render()
            
            pygame.display.flip()
        
        pygame.quit()
    
    def handle_key(self, event):
        """处理按键"""
        key = event.key
        mod = pygame.key.get_mods()
        shift = mod & pygame.KMOD_SHIFT
        ctrl = mod & pygame.KMOD_CTRL
        
        # 全局快捷键
        if key == pygame.K_h:
            self.show_help = not self.show_help
        elif key == pygame.K_SPACE:
            self.paused = not self.paused
        elif key == pygame.K_s and ctrl:
            self.background.save_config()
        elif key == pygame.K_r and ctrl:
            self.background.reload()
        
        # 切换背景
        elif key == pygame.K_PAGEUP:
            self.current_bg_index = (self.current_bg_index - 1) % len(self.available_backgrounds)
            self.load_background(self.available_backgrounds[self.current_bg_index])
        elif key == pygame.K_PAGEDOWN:
            self.current_bg_index = (self.current_bg_index + 1) % len(self.available_backgrounds)
            self.load_background(self.available_backgrounds[self.current_bg_index])
        
        # 切换编辑模式
        elif key == pygame.K_1:
            self.edit_mode = "camera"
            self.edit_param = 0
        elif key == pygame.K_2:
            self.edit_mode = "fog"
            self.edit_param = 0
        elif key == pygame.K_3:
            self.edit_mode = "scroll"
            self.edit_param = 0
        elif key == pygame.K_4:
            self.edit_mode = "layer"
            self.edit_param = 0
        
        # 切换参数/图层
        elif key == pygame.K_UP:
            self.edit_param = max(0, self.edit_param - 1)
        elif key == pygame.K_DOWN:
            self.edit_param += 1
        elif key == pygame.K_TAB and self.edit_mode == "layer":
            if self.background.data:
                self.selected_layer = (self.selected_layer + 1) % len(self.background.data.layers)
        
        # 调整值
        elif key in (pygame.K_LEFT, pygame.K_RIGHT):
            delta = -1 if key == pygame.K_LEFT else 1
            if shift:
                delta *= 10
            if ctrl:
                delta *= 0.01
            else:
                delta *= 0.1
            self.adjust_value(delta)
    
    def handle_scroll(self, event):
        """处理滚轮"""
        self.scroll_offset += event.y * 20
    
    def adjust_value(self, delta: float):
        """调整当前参数值"""
        if not self.background.data:
            return
        
        data = self.background.data
        
        if self.edit_mode == "camera":
            params = ["eye_x", "eye_y", "eye_z", "at_x", "at_y", "at_z", 
                     "up_x", "up_y", "up_z", "fovy", "z_near", "z_far"]
            if self.edit_param < len(params):
                param = params[self.edit_param]
                if param.startswith("eye_"):
                    idx = "xyz".index(param[-1])
                    new_val = list(data.camera.eye)
                    new_val[idx] += delta
                    data.camera.eye = tuple(new_val)
                elif param.startswith("at_"):
                    idx = "xyz".index(param[-1])
                    new_val = list(data.camera.at)
                    new_val[idx] += delta
                    data.camera.at = tuple(new_val)
                elif param.startswith("up_"):
                    idx = "xyz".index(param[-1])
                    new_val = list(data.camera.up)
                    new_val[idx] += delta
                    data.camera.up = tuple(new_val)
                elif param == "fovy":
                    data.camera.fovy = max(0.1, data.camera.fovy + delta * 0.1)
                elif param == "z_near":
                    data.camera.z_near = max(0.01, data.camera.z_near + delta)
                elif param == "z_far":
                    data.camera.z_far = max(data.camera.z_near + 1, data.camera.z_far + delta)
        
        elif self.edit_mode == "fog":
            params = ["enabled", "start", "end", "color_r", "color_g", "color_b", "color_a"]
            if self.edit_param < len(params):
                param = params[self.edit_param]
                if param == "enabled":
                    data.fog.enabled = not data.fog.enabled
                elif param == "start":
                    data.fog.start = max(0, data.fog.start + delta)
                elif param == "end":
                    data.fog.end = max(data.fog.start + 0.1, data.fog.end + delta)
                elif param.startswith("color_"):
                    idx = "rgba".index(param[-1])
                    new_color = list(data.fog.color)
                    new_color[idx] = max(0, min(255, new_color[idx] + int(delta * 10)))
                    data.fog.color = tuple(new_color)
        
        elif self.edit_mode == "scroll":
            params = ["base_speed", "dir_x", "dir_y"]
            if self.edit_param < len(params):
                param = params[self.edit_param]
                if param == "base_speed":
                    data.scroll.base_speed = max(0, data.scroll.base_speed + delta * 0.01)
                elif param == "dir_x":
                    new_dir = list(data.scroll.direction)
                    new_dir[0] += delta
                    data.scroll.direction = tuple(new_dir)
                elif param == "dir_y":
                    new_dir = list(data.scroll.direction)
                    new_dir[1] += delta
                    data.scroll.direction = tuple(new_dir)
        
        elif self.edit_mode == "layer":
            if self.selected_layer < len(data.layers):
                layer = data.layers[self.selected_layer]
                params = ["z_order", "z_depth", "alpha", "scroll_multiplier", 
                         "blend_mode", "enabled", "tile_size"]
                if self.edit_param < len(params):
                    param = params[self.edit_param]
                    if param == "z_order":
                        layer.z_order = int(layer.z_order + delta)
                    elif param == "z_depth":
                        layer.z_depth += delta
                    elif param == "alpha":
                        layer.alpha = max(0, min(1, layer.alpha + delta * 0.1))
                    elif param == "scroll_multiplier":
                        layer.scroll_multiplier = max(0, layer.scroll_multiplier + delta * 0.1)
                    elif param == "blend_mode":
                        modes = [BlendMode.NORMAL, BlendMode.ADD, BlendMode.MULTIPLY]
                        idx = modes.index(layer.blend_mode)
                        layer.blend_mode = modes[(idx + int(delta)) % len(modes)]
                    elif param == "enabled":
                        layer.enabled = not layer.enabled
                    elif param == "tile_size":
                        layer.tile.size = max(0.1, layer.tile.size + delta * 0.1)
    
    def render(self):
        """渲染"""
        # 清除屏幕
        self.ctx.clear(0.1, 0.1, 0.15, 1.0)
        
        # 设置视口到预览区域（左侧，从底部开始）
        self.ctx.viewport = (0, 0, self.preview_width, self.preview_height)
        
        # 渲染背景
        if self.background.data:
            self.background.render()
            self._render_background_quads()
        
        # 渲染 UI（使用 pygame 2D 绘制）
        self.ctx.viewport = (0, 0, self.width, self.height)
        self._render_ui()
    
    def _render_background_quads(self):
        """渲染背景四边形"""
        import numpy as np
        
        quads = self.background.get_render_quads()
        if not quads:
            return
        
        # 计算 MVP - 使用游戏的基础宽高比
        view = self.bg_renderer.camera.get_view_matrix()
        proj = self.bg_renderer.camera.get_projection_matrix(
            self.base_size[0] / self.base_size[1]
        )
        mvp = np.dot(proj, view)
        
        self.bg_renderer.program_3d['u_mvp'].write(mvp.tobytes())
        self.bg_renderer.program_3d['u_fog_enabled'].value = self.bg_renderer.camera.fog_enabled
        self.bg_renderer.program_3d['u_fog_start'].value = self.bg_renderer.camera.fog_start
        self.bg_renderer.program_3d['u_fog_end'].value = self.bg_renderer.camera.fog_end
        self.bg_renderer.program_3d['u_fog_color'].value = self.bg_renderer.camera.fog_color
        
        for quad in quads:
            texture = self.bg_renderer.textures.get(quad['texture'])
            if not texture:
                continue
            
            # 混合模式
            blend = quad['blend_mode']
            if blend == BlendMode.ADD:
                self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE)
            elif blend == BlendMode.MULTIPLY:
                self.ctx.blend_func = (moderngl.DST_COLOR, moderngl.ZERO)
            else:
                self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
            
            texture.use(0)
            self.bg_renderer.program_3d['u_texture'].value = 0
            self.bg_renderer.program_3d['u_alpha'].value = quad['alpha']
            self.bg_renderer.program_3d['u_color_tint'].value = (1.0, 1.0, 1.0, 1.0)
            
            # 顶点数据
            v0, v1, v2, v3 = quad['v0'], quad['v1'], quad['v2'], quad['v3']
            vertices = np.array([
                v0[0], v0[1], v0[2], 0, 0,
                v1[0], v1[1], v1[2], 0, 1,
                v2[0], v2[1], v2[2], 1, 1,
                v3[0], v3[1], v3[2], 1, 0,
            ], dtype='f4')
            
            vbo = self.ctx.buffer(vertices)
            vao = self.ctx.vertex_array(
                self.bg_renderer.program_3d,
                [(vbo, '3f 2f', 'in_vert', 'in_uv')]
            )
            vao.render(moderngl.TRIANGLE_FAN)
            vbo.release()
            vao.release()
        
        # 恢复混合模式
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
    
    def _render_ui(self):
        """渲染 UI 面板"""
        # 创建 surface 用于 2D 绘制
        ui_surface = pygame.Surface((self.panel_width, self.height), pygame.SRCALPHA)
        ui_surface.fill((30, 30, 40, 240))
        
        y = 10
        
        # 标题
        title = self.font_title.render("背景编辑器", True, (255, 255, 255))
        ui_surface.blit(title, (10, y))
        y += 40
        
        # 当前背景
        if self.background.data:
            bg_text = f"背景: {self.background.data.name}"
        else:
            bg_text = "未加载背景"
        text = self.font.render(bg_text, True, (200, 200, 255))
        ui_surface.blit(text, (10, y))
        y += 25
        
        # 状态
        status = "暂停" if self.paused else "播放中"
        text = self.font_small.render(f"状态: {status} | PgUp/PgDn 切换背景", True, (150, 150, 150))
        ui_surface.blit(text, (10, y))
        y += 30
        
        # 分隔线
        pygame.draw.line(ui_surface, (80, 80, 100), (10, y), (self.panel_width - 10, y))
        y += 10
        
        # 编辑模式选择
        modes = [("1.摄像机", "camera"), ("2.雾效", "fog"), 
                ("3.滚动", "scroll"), ("4.图层", "layer")]
        for label, mode in modes:
            color = (100, 200, 100) if self.edit_mode == mode else (150, 150, 150)
            text = self.font.render(label, True, color)
            ui_surface.blit(text, (10 + modes.index((label, mode)) * 90, y))
        y += 30
        
        # 参数面板
        if self.background.data:
            y = self._render_params_panel(ui_surface, y)
        
        # 帮助信息 - 显示在参数面板下方
        if self.show_help:
            y += 20  # 在参数面板后留出间距
            pygame.draw.line(ui_surface, (80, 80, 100), (10, y), (self.panel_width - 10, y))
            y += 10
            help_lines = [
                "快捷键:",
                "H - 显示/隐藏帮助",
                "Space - 暂停/继续",
                "Ctrl+S - 保存配置",
                "Ctrl+R - 重新加载",
                "↑↓ - 选择参数",
                "←→ - 调整值 (Shift=快速)",
                "Tab - 切换图层 (图层模式)"
            ]
            for line in help_lines:
                text = self.font_small.render(line, True, (120, 120, 120))
                ui_surface.blit(text, (10, y))
                y += 18
        
        # 将 UI surface 转换为纹理并渲染
        self._blit_surface_to_screen(ui_surface, self.preview_width, 0)
    
    def _render_params_panel(self, surface: pygame.Surface, y: int) -> int:
        """渲染参数面板"""
        data = self.background.data
        
        if self.edit_mode == "camera":
            params = [
                ("Eye X", f"{data.camera.eye[0]:.2f}"),
                ("Eye Y", f"{data.camera.eye[1]:.2f}"),
                ("Eye Z", f"{data.camera.eye[2]:.2f}"),
                ("At X", f"{data.camera.at[0]:.2f}"),
                ("At Y", f"{data.camera.at[1]:.2f}"),
                ("At Z", f"{data.camera.at[2]:.2f}"),
                ("Up X", f"{data.camera.up[0]:.2f}"),
                ("Up Y", f"{data.camera.up[1]:.2f}"),
                ("Up Z", f"{data.camera.up[2]:.2f}"),
                ("FOV Y", f"{data.camera.fovy:.3f}"),
                ("Z Near", f"{data.camera.z_near:.2f}"),
                ("Z Far", f"{data.camera.z_far:.2f}"),
            ]
        
        elif self.edit_mode == "fog":
            params = [
                ("启用", "是" if data.fog.enabled else "否"),
                ("起始距离", f"{data.fog.start:.2f}"),
                ("结束距离", f"{data.fog.end:.2f}"),
                ("颜色 R", f"{data.fog.color[0]}"),
                ("颜色 G", f"{data.fog.color[1]}"),
                ("颜色 B", f"{data.fog.color[2]}"),
                ("颜色 A", f"{data.fog.color[3]}"),
            ]
        
        elif self.edit_mode == "scroll":
            params = [
                ("基础速度", f"{data.scroll.base_speed:.4f}"),
                ("方向 X", f"{data.scroll.direction[0]:.2f}"),
                ("方向 Y", f"{data.scroll.direction[1]:.2f}"),
            ]
        
        elif self.edit_mode == "layer":
            # 图层列表
            text = self.font.render("图层列表 (Tab切换):", True, (200, 200, 200))
            surface.blit(text, (10, y))
            y += 25
            
            for i, layer in enumerate(data.layers):
                color = (100, 255, 100) if i == self.selected_layer else (150, 150, 150)
                status = "✓" if layer.enabled else "✗"
                text = self.font_small.render(f"  {status} {layer.name}", True, color)
                surface.blit(text, (10, y))
                y += 20
            
            y += 10
            
            if self.selected_layer < len(data.layers):
                layer = data.layers[self.selected_layer]
                params = [
                    ("Z Order", f"{layer.z_order}"),
                    ("Z Depth", f"{layer.z_depth:.2f}"),
                    ("Alpha", f"{layer.alpha:.2f}"),
                    ("滚动倍率", f"{layer.scroll_multiplier:.2f}"),
                    ("混合模式", layer.blend_mode.value),
                    ("启用", "是" if layer.enabled else "否"),
                    ("Tile大小", f"{layer.tile.size:.2f}"),
                ]
            else:
                params = []
        
        # 渲染参数列表
        for i, (name, value) in enumerate(params):
            is_selected = i == self.edit_param
            color = (255, 255, 100) if is_selected else (200, 200, 200)
            prefix = ">" if is_selected else " "
            text = self.font.render(f"{prefix} {name}: {value}", True, color)
            surface.blit(text, (10, y))
            y += 22
        
        return y
    
    def _blit_surface_to_screen(self, surface: pygame.Surface, x: int, y: int):
        """将 pygame surface 绘制到 OpenGL 屏幕"""
        # 转换为纹理
        data = pygame.image.tobytes(surface, "RGBA", True)
        texture = self.ctx.texture(surface.get_size(), 4, data)
        texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        
        # 使用简单的 2D 着色器
        if not hasattr(self, '_ui_program'):
            self._ui_program = self.ctx.program(
                vertex_shader="""
                    #version 330
                    in vec2 in_vert;
                    in vec2 in_uv;
                    out vec2 v_uv;
                    void main() {
                        gl_Position = vec4(in_vert, 0.0, 1.0);
                        v_uv = in_uv;
                    }
                """,
                fragment_shader="""
                    #version 330
                    uniform sampler2D u_texture;
                    in vec2 v_uv;
                    out vec4 f_color;
                    void main() {
                        f_color = texture(u_texture, v_uv);
                    }
                """
            )
        
        # 计算屏幕坐标
        x0 = (x / self.width) * 2 - 1
        x1 = ((x + surface.get_width()) / self.width) * 2 - 1
        y0 = (y / self.height) * 2 - 1
        y1 = ((y + surface.get_height()) / self.height) * 2 - 1
        
        import numpy as np
        vertices = np.array([
            x0, y0, 0, 0,
            x1, y0, 1, 0,
            x0, y1, 0, 1,
            x1, y1, 1, 1,
        ], dtype='f4')
        
        vbo = self.ctx.buffer(vertices)
        vao = self.ctx.vertex_array(self._ui_program, [(vbo, '2f 2f', 'in_vert', 'in_uv')])
        
        texture.use(0)
        self._ui_program['u_texture'].value = 0
        vao.render(moderngl.TRIANGLE_STRIP)
        
        vbo.release()
        vao.release()
        texture.release()


def main():
    """主入口"""
    editor = BackgroundEditor()
    editor.run()


if __name__ == "__main__":
    main()

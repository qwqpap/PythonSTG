import numpy as np
import moderngl
import moderngl_window as mglw

class KLineWindow(mglw.WindowConfig):
    gl_version = (3, 3)
    title = "ModernGL K-Line Simulator"
    window_size = (1280, 720)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # 着色器程序
        self.prog = self.ctx.program(
            vertex_shader='''
                #version 330
                in vec2 in_pos;
                in vec3 in_color;
                out vec3 v_color;
                uniform float x_scale;
                uniform float x_offset;
                uniform float y_scale;
                uniform float y_offset;
                void main() {
                    v_color = in_color;
                    float nx = (in_pos.x + x_offset) * x_scale * 2.0 - 1.0;
                    float ny = (in_pos.y + y_offset) * y_scale * 2.0 - 1.0;
                    gl_Position = vec4(nx, ny, 0.0, 1.0);
                }
            ''',
            fragment_shader='''
                #version 330
                in vec3 v_color;
                out vec4 f_color;
                void main() {
                    f_color = vec4(v_color, 1.0);
                }
            '''
        )

        # 初始数据
        self.candles = []
        self.current_price = 100.0
        self.time_counter = 0.0
        self.update_interval = 0.2
        self.paused = False
        self.visible_count = 100
        self.candle_spacing = 1.0
        self.y_min, self.y_max = 0.0, 0.0
        
        for _ in range(300):
            self._generate_next_candle()

        # 显存分配
        self.vbo = self.ctx.buffer(reserve=1024 * 512) # 512KB
        self.vao = self.ctx.vertex_array(self.prog, [(self.vbo, '2f 3f', 'in_pos', 'in_color')])
        self.num_vertices = 0
        self._update_buffer()

    def _generate_next_candle(self):
        o = self.current_price
        c = o + np.random.normal(0, 1.5)
        h = max(o, c) + abs(np.random.normal(0, 1.0))
        l = min(o, c) - abs(np.random.normal(0, 1.0))
        self.current_price = c
        self.candles.append((o, h, l, c))
        if len(self.candles) > 1000: self.candles.pop(0)

    def _update_buffer(self):
        start_idx = max(0, len(self.candles) - self.visible_count - 2)
        visible_candles = self.candles[start_idx:]
        
        vertices = []
        for i, (o, h, l, c) in enumerate(visible_candles):
            x = i * self.candle_spacing
            color = (0.2, 0.8, 0.3) if c >= o else (0.9, 0.2, 0.2)
            
            bw, ww = self.candle_spacing * 0.8, self.candle_spacing * 0.1
            bx1, bx2 = x - bw/2, x + bw/2
            wx1, wx2 = x - ww/2, x + ww/2
            bt, bb = max(o, c), min(o, c)

            # 影线 + 实体 (12个顶点组成两个长方形)
            for x_range in [(wx1, wx2, l, h), (bx1, bx2, bb, bt)]:
                x1, x2, y1, y2 = x_range
                vertices.extend([
                    x1, y1, *color, x2, y1, *color, x1, y2, *color,
                    x2, y1, *color, x2, y2, *color, x1, y2, *color
                ])
        
        v_data = np.array(vertices, dtype='f4')
        self.vbo.write(v_data.tobytes())
        self.num_vertices = len(vertices) // 5

        # 动态计算纵坐标范围
        if visible_candles:
            prices = [p for c in visible_candles for p in c]
            self.y_min, self.y_max = min(prices), max(prices)
            pad = (self.y_max - self.y_min) * 0.1
            self.y_min -= pad
            self.y_max += pad

    def key_event(self, key, action, modifiers):
        if action == self.wnd.keys.ACTION_PRESS:
            if key == self.wnd.keys.EQUAL: self.visible_count = max(10, self.visible_count - 5)
            if key == self.wnd.keys.MINUS: self.visible_count = min(500, self.visible_count + 5)
            if key == self.wnd.keys.SPACE: self.paused = not self.paused
            self._update_buffer()

    # 重点：同时保留 render 并在内部显式调用逻辑，确保所有版本都能捕获
    def render(self, time, frame_time):
        self.ctx.clear(0.1, 0.1, 0.12)

        if not self.paused:
            self.time_counter += frame_time
            if self.time_counter >= self.update_interval:
                self._generate_next_candle()
                self._update_buffer()
                self.time_counter = 0

        progress = self.time_counter / self.update_interval if not self.paused else 0
        
        self.prog['x_offset'].value = -progress * self.candle_spacing
        self.prog['x_scale'].value = 1.0 / (self.visible_count * self.candle_spacing)
        self.prog['y_scale'].value = 1.0 / (self.y_max - self.y_min + 1e-6)
        self.prog['y_offset'].value = -self.y_min
        
        if self.num_vertices > 0:
            self.vao.render(moderngl.TRIANGLES, vertices=self.num_vertices)

    # moderngl_window newer backends call on_render instead of render
    def on_render(self, time, frame_time):
        self.render(time, frame_time)

if __name__ == '__main__':
    mglw.run_window_config(KLineWindow)
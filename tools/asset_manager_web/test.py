import moderngl
import moderngl_window as mglw
import numpy as np

class BasicExample(mglw.WindowConfig):
    gl_version = (3, 3)
    title = "ModernGL 基本操作"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # 1. 编写着色器 (Program)
        self.prog = self.ctx.program(
            vertex_shader='''
                #version 330
                in vec2 in_position;
                void main() {
                    gl_Position = vec4(in_position, 0.0, 1.0);
                }
            ''',
            fragment_shader='''
                #version 330
                out vec4 fragColor;
                void main() {
                    fragColor = vec4(0.2, 0.6, 0.8, 1.0); // 蓝色
                }
            '''
        )

        # 2. 顶点数据 (VBO)
        vertices = np.array([
             0.0,  0.5,
            -0.5, -0.5,
             0.5, -0.5
        ], dtype='f4')
        self.vbo = self.ctx.buffer(vertices.tobytes())

        # 3. 绑定数据与逻辑 (VAO)
        self.vao = self.ctx.vertex_array(self.prog, [
            (self.vbo, '2f', 'in_position')
        ])

    def render(self, time, frame_time):
        # 4. 渲染
        self.ctx.clear(1.0, 1.0, 1.0)
        self.vao.render(moderngl.TRIANGLES)

if __name__ == '__main__':
    mglw.run_window_config(BasicExample)
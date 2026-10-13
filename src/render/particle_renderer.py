"""Instanced sprite particles; textures remain owned by the asset manager."""

import moderngl
import numpy as np


class ParticleRenderer:
    def __init__(self, ctx, textures, base_size=(384, 448)):
        self.ctx = ctx
        self._textures = {path.replace('\\', '/').lower(): texture
                          for path, texture in textures.items()}
        self.program = ctx.program(vertex_shader='''
            #version 330
            in vec2 in_vert;
            in vec2 in_uv;
            in vec2 in_position;
            in float in_angle;
            in vec4 in_uv_rect;
            in vec2 in_size;
            in vec4 in_color;
            uniform float u_pixel_scale;
            uniform float u_y_scale;
            out vec2 v_uv;
            out vec4 v_color;
            void main() {
                vec2 p = in_vert * in_size * u_pixel_scale;
                float c = cos(in_angle), s = sin(in_angle);
                p = vec2(p.x*c - p.y*s, p.x*s + p.y*c) + in_position;
                gl_Position = vec4(p.x, p.y*u_y_scale, 0.0, 1.0);
                v_uv = mix(in_uv_rect.xy, in_uv_rect.zw, in_uv);
                v_color = in_color;
            }
        ''', fragment_shader='''
            #version 330
            uniform sampler2D u_texture;
            in vec2 v_uv;
            in vec4 v_color;
            out vec4 f_color;
            void main() { f_color = texture(u_texture, v_uv) * v_color; }
        ''')
        self.program['u_texture'].value = 0
        # Match the existing bullet renderer's pixel-to-world convention.
        self.program['u_pixel_scale'].value = 2.0 / base_size[1]
        self.program['u_y_scale'].value = base_size[0] / base_size[1]
        vertices = np.array([
            [-.5, .5, 0, 0], [-.5, -.5, 0, 1], [.5, .5, 1, 0],
            [.5, .5, 1, 0], [-.5, -.5, 0, 1], [.5, -.5, 1, 1],
        ], dtype=np.float32)
        self._vertices = ctx.buffer(vertices)
        self._capacity = 256
        self._instances = ctx.buffer(reserve=self._capacity * 13 * 4, dynamic=True)
        self._vao = ctx.vertex_array(self.program, [
            (self._vertices, '2f 2f', 'in_vert', 'in_uv'),
            (self._instances, '2f 1f 4f 2f 4f /i',
             'in_position', 'in_angle', 'in_uv_rect', 'in_size', 'in_color'),
        ])
        self._closed = False

    def render_from_pool(self, pool, layer='front'):
        """Draw adjacent compatible runs, not a texture sort of alpha sprites.

        Requires the engine's standard SRC_ALPHA/ONE_MINUS_SRC_ALPHA blend
        state on entry; restores that state in finally. Viewport, framebuffer
        and scissor are never changed. No GPU resources grow per frame.
        """
        if not pool.count:
            return 0
        data, keys = pool.prepare_render_data(layer)
        if not len(keys):
            return 0
        breaks = np.flatnonzero(keys[1:] != keys[:-1]) + 1
        ends = np.append(breaks, len(keys))
        start = 0
        draws = 0
        try:
            for end in ends:
                key = int(keys[start])
                path = pool.sprite_registry.get_texture_path(key // 2)
                texture = self._textures.get(path.replace('\\', '/').lower())
                if texture is None:
                    raise RuntimeError(f'particle texture is not uploaded: {path}')
                n = int(end - start)
                if n > self._capacity:
                    self._capacity = max(n, self._capacity * 2)
                    self._instances.orphan(self._capacity * 13 * 4)
                texture.use(0)
                self.ctx.blend_func = (moderngl.SRC_ALPHA,
                                       moderngl.ONE if key % 2 else moderngl.ONE_MINUS_SRC_ALPHA)
                self._instances.write(data[start:end])
                self._vao.render(moderngl.TRIANGLES, instances=n)
                draws += 1
                start = int(end)
        finally:
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        return draws

    def cleanup(self):
        if self._closed:
            return
        self._closed = True
        for resource in (self._vao, self._instances, self._vertices, self.program):
            resource.release()

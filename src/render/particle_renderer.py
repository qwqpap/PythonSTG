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
            uniform float u_alpha_cutoff;
            in vec2 v_uv;
            in vec4 v_color;
            out vec4 f_color;
            void main() {
                f_color = texture(u_texture, v_uv) * v_color;
                if (f_color.a < u_alpha_cutoff) discard;
            }
        ''')
        self.program['u_texture'].value = 0
        # Match the existing bullet renderer's pixel-to-world convention.
        self.program['u_pixel_scale'].value = 2.0 / base_size[1]
        self._pixel_scale = 2.0 / base_size[1]
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
        self._trail_program = None
        self._trail_vertices = None
        self._trail_vao = None
        self._trail_capacity = 0
        self._y_scale = base_size[0] / base_size[1]
        self._closed = False
        self._instances_prepared = False
        self._trails_prepared = False

    def render_from_pool(self, pool, layer='front'):
        """Draw adjacent compatible runs, not a texture sort of alpha sprites.

        Requires the engine's standard SRC_ALPHA/ONE_MINUS_SRC_ALPHA blend
        state on entry; restores that state in finally. Viewport, framebuffer
        and scissor are never changed. No GPU resources grow per frame.
        """
        if not pool.count:
            return 0
        data, keys = pool.prepare_render_data(layer)
        return self.render_instances(data, keys, pool.sprite_registry.get_texture_path)

    def render_instances(self, data, keys, texture_path, *, pixel_scale=None,
                         alpha_cutoff=0.0):
        """Reuse the same shader/VAO for controlled sprites and bulk particles."""
        if not len(keys):
            return 0
        self.program['u_pixel_scale'].value = (
            self._pixel_scale if pixel_scale is None else pixel_scale)
        self.program['u_alpha_cutoff'].value = alpha_cutoff
        breaks = np.flatnonzero(keys[1:] != keys[:-1]) + 1
        ends = np.append(breaks, len(keys))
        start = 0
        draws = 0
        try:
            for end in ends:
                key = int(keys[start])
                path = texture_path(key // 2)
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

    def _ensure_trail_resources(self, capacity):
        if self._trail_program is None:
            self._trail_program = self.ctx.program(vertex_shader='''
                #version 330
                in vec2 in_position;
                in vec2 in_uv;
                in vec4 in_color;
                uniform float u_y_scale;
                out vec2 v_uv;
                out vec4 v_color;
                void main() {
                    gl_Position = vec4(in_position.x,
                                       in_position.y*u_y_scale, 0.0, 1.0);
                    v_uv = in_uv;
                    v_color = in_color;
                }
            ''', fragment_shader='''
                #version 330
                uniform sampler2D u_texture;
                in vec2 v_uv;
                in vec4 v_color;
                out vec4 f_color;
                void main() {
                    f_color = texture(u_texture, v_uv) * v_color;
                }
            ''')
            self._trail_program['u_texture'].value = 0
            self._trail_program['u_y_scale'].value = self._y_scale
            self._trail_capacity = max(6, int(capacity))
            self._trail_vertices = self.ctx.buffer(reserve=self._trail_capacity * 8 * 4,
                                                    dynamic=True)
            self._trail_vao = self.ctx.vertex_array(self._trail_program, [
                (self._trail_vertices, '2f 2f 4f',
                 'in_position', 'in_uv', 'in_color'),
            ])
        if capacity > self._trail_capacity:
            self._trail_capacity = max(int(capacity), self._trail_capacity * 2)
            self._trail_vertices.orphan(self._trail_capacity * 8 * 4)

    def prepare_resources(self, *, trail_vertices=0, instance_capacity=8192):
        """Prepare known GPU paths into a private FBO, without visible effects."""
        if instance_capacity > self._capacity:
            self._capacity = int(instance_capacity)
            self._instances.orphan(self._capacity * 13 * 4)
        if trail_vertices:
            self._ensure_trail_resources(trail_vertices)
        if self._instances_prepared and (not trail_vertices or self._trails_prepared):
            return
        viewport, scissor = self.ctx.viewport, self.ctx.scissor
        target = self.ctx.texture((8, 8), 4)
        framebuffer = self.ctx.framebuffer([target])
        white = self.ctx.texture((1, 1), 4, bytes([255] * 4))
        try:
            with self.ctx.scope(framebuffer=framebuffer):
                self.ctx.viewport, self.ctx.scissor = (0, 0, 8, 8), None
                white.use(0)
                if not self._instances_prepared:
                    self._instances.write(np.array(
                        [[0, 0, 0, 0, 0, 1, 1, 16, 16, 1, 1, 1, 1]], np.float32))
                    self.program['u_alpha_cutoff'].value = 0.0
                    self._vao.render(moderngl.TRIANGLES, instances=1)
                    self._instances_prepared = True
                if trail_vertices and not self._trails_prepared:
                    vertices = np.array([
                        [-1, -1, 0, 0, 1, 1, 1, 1], [1, -1, 1, 0, 1, 1, 1, 1],
                        [-1, 1, 0, 1, 1, 1, 1, 1], [-1, 1, 0, 1, 1, 1, 1, 1],
                        [1, -1, 1, 0, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1, 1, 1],
                    ], np.float32)
                    self._trail_vertices.write(vertices)
                    self._trail_vao.render(moderngl.TRIANGLES, vertices=6)
                    self._trails_prepared = True
                self.ctx.finish()
        finally:
            self.ctx.viewport, self.ctx.scissor = viewport, scissor
            framebuffer.release()
            target.release()
            white.release()

    def render_trails(self, collection, layer='main'):
        """Draw continuous ribbons; prepared budgets avoid first-use growth."""
        if not collection.count:
            return 0
        data, keys = collection.prepare_render_data(layer)
        if not len(keys):
            return 0
        self._ensure_trail_resources(len(keys))
        self._trail_vertices.write(data)
        breaks = np.flatnonzero(keys[1:] != keys[:-1]) + 1
        ends = np.append(breaks, len(keys))
        start, draws = 0, 0
        try:
            for end in ends:
                key = int(keys[start])
                path = collection.sprite_registry.get_texture_path(key // 2)
                texture = self._textures.get(path.replace('\\', '/').lower())
                if texture is None:
                    raise RuntimeError(f'trail texture is not uploaded: {path}')
                texture.use(0)
                self.ctx.blend_func = (moderngl.SRC_ALPHA,
                                       moderngl.ONE if key % 2 else moderngl.ONE_MINUS_SRC_ALPHA)
                self._trail_vao.render(moderngl.TRIANGLES, vertices=int(end-start), first=start)
                start = int(end)
                draws += 1
        finally:
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        return draws

    def cleanup(self):
        if self._closed:
            return
        self._closed = True
        for resource in (self._trail_vao, self._trail_vertices, self._trail_program):
            if resource is not None:
                resource.release()
        for resource in (self._vao, self._instances, self._vertices, self.program):
            resource.release()

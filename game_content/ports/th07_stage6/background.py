"""Hand-translated TH07 stage 6 scenery on the normal background API.

Source: stage6.std and stg6bg/eff05/eff06 ANM from TH07 1.00b, checked against
Stage.cpp, EffectManager.cpp, Gui.cpp and AnmManager.cpp at 4878bf0e42a9.
The importer expands static instances once. One ordinary stage Task animates
the camera and a bounded four image layers; no STD/ANM instructions run here.
"""

from __future__ import annotations

from dataclasses import replace
import math

import numpy as np

from src.game.background import SceneQuad, ScreenLayer
from src.game.particle import ParticleEffect
from src.game.tasks import wait_frames


def _lerp(start, end, fraction):
    return start + (end - start) * min(1.0, max(0.0, fraction))


def _rgb(value):
    return tuple(((value >> shift) & 255) / 255.0 for shift in (16, 8, 0))


def _mix_color(start, end, fraction):
    return tuple(_lerp(a, b, fraction) for a, b in zip(start, end)) + (1.0,)


def _image_layer(resources, sprite_id, *, full_screen=False, placement="front"):
    path, rect, texture_size = resources.source_image(sprite_id)
    x, y, width, height = rect
    tw, th = texture_size
    return ScreenLayer(
        path, uv_rect=(x / tw, 1 - (y + height) / th,
                       (x + width) / tw, 1 - y / th),
        scale=(1.0, 1.0) if full_screen else (width / 384, height / 448),
        placement=placement,
    )


class TH07Stage6Background:
    """Stage-owned scene controller; callers choose labels and spell state.

    label(1..5) is an immediate cue, not a wait for absolute stage time. The
    original searches the complete STD script for the requested label, even
    across preceding loop jumps. Encoding those five finite sections directly
    keeps the hook predictable without introducing an original-format runtime.
    """

    def __init__(self, port):
        self.port = port
        self.ctx = port.ctx
        self.state = self.ctx.background
        self.resources = port.assets
        self.definition = self.resources.background_definition
        self.age = 0.0
        self.section_age = 0.0
        self.current_label = 0
        self.spell_active = False
        self.spell_kind = "youmu"
        self.spell_age = 0.0
        self.slash_active = False
        self.slash_age = 0.0
        self._slash_rotation = 0.0
        self._normal_rotation = 0.0
        self._normal_age = 0.0
        self._normal_scale = 2.304886
        self._closed = False
        self.source_camera = (0.0, 0.0, -500.0)
        self.source_look = (0.0, 50.0, 400.0)
        self._tint_start = (1.0, 1.0, 1.0)
        self._tint_end = self._tint_start
        self._base_alpha_start = self._base_alpha_end = 1.0
        self._spell_layers = []
        self._weather_group = None
        self._weather_position = np.empty((0, 3), np.float32)
        self._weather_velocity = np.empty((0, 3), np.float32)
        self._weather_rotation = np.empty(0, np.float32)
        self._weather_spin = np.empty(0, np.float32)
        self._weather_age = np.empty(0, np.float32)
        self._weather_effect = ParticleEffect(
            ("th07_etama_e1_s48",), lifetime=1, alpha=1.0, alpha_end=1.0,
            layer="back",
        )
        self.weather_dropped = 0
        quads = [SceneQuad(
            str(self.resources.root / item["texture"]),
            tuple(tuple(vertex) for vertex in item["vertices"]),
            tuple(item["uv_rect"]), tuple(item["color"]),
        ) for item in self.definition["quads"]]
        self.state.set_scene(quads, clear_color=(0.0, 0.0, 0.0, 1.0))
        self.state.set_camera(eye=(0.0, 0.0, 500.0), at=(0.0, 50.0, 100.0),
                              up=(0.0, 1.0, 0.0), fovy=0.6283185482025146,
                              z_near=30.0, z_far=1800.0)
        self.state.set_fog(color=(*_rgb(0x201020), 1.0), start=700.0,
                           end=800.0, enabled=True)
        self.backdrop = _image_layer(self.resources, self.definition["backdrop_sprite"],
                                     full_screen=True, placement="back")
        self.sigil = _image_layer(self.resources, self.definition["sigil_sprite"], placement="back")
        self.state.set_layers([self.backdrop, self.sigil])
        self._apply()

    def label(self, index):
        if index not in (1, 2, 3, 4, 5):
            raise ValueError(f"unsupported TH07 stage 6 background label: {index}")
        self._tint_start = self.backdrop.color[:3]
        self._base_alpha_start = self.backdrop.alpha
        self._tint_end = _rgb({1: 0xffffff, 2: 0x3c00ff, 3: 0xff0014,
                               4: 0xff00ff, 5: 0x0000ff}[index])
        self._base_alpha_end = 128 / 255 if index == 5 else 1.0
        self.current_label = index
        self.section_age = 0.0
        self._apply()

    def set_spell(self, active, *, kind=None):
        """Begin/end the original eff05 (Youmu) or eff06 (Yuyuko) layers."""
        if kind is not None:
            if kind not in ("youmu", "yuyuko"):
                raise ValueError("spell background kind must be youmu or yuyuko")
            self.spell_kind = kind
        self.spell_active = bool(active)
        self.spell_age = self.slash_age = 0.0
        self.slash_active = False
        self._normal_age = self._normal_rotation = 0.0
        self._normal_scale = 2.304886
        self._spell_layers = []
        if active:
            source = self.definition["spell_sprites"][self.spell_kind]
            for sprite in source:
                self._spell_layers.append(_image_layer(self.resources, sprite, full_screen=True))
            if self.spell_kind == "youmu":
                # eff05b is a centered 256-square at scale 2.304886, not a
                # fullscreen-stretched texture. Its source rotation uses Y down.
                self._spell_layers[1].scale = (256 * 2.304886 / 384, 256 * 2.304886 / 448)
        self.state.set_layers([self.backdrop, self.sigil, *self._spell_layers])
        self._apply()

    def set_slash(self, active):
        """Source ExIns10/11 visual interrupts, independent of time scaling."""
        self.slash_active = bool(active)
        self.slash_age = 0.0
        if self._spell_layers:
            self._slash_rotation = self._spell_layers[1].rotation
            if not active:
                self._normal_rotation = self._spell_layers[1].rotation
                self._normal_scale = self._spell_layers[1].scale[0] * 384 / 256
                self._normal_age = 60.0
        self._apply()

    def emit_weather(self, count):
        """Effect31: source-world falling petals, one generation-safe batch.

        The existing Sub1 actor controls emission cadence. Packed world data is
        projected together into ParticlePool, not represented by particle Tasks
        or by a fake emitter-centered two-dimensional burst.
        """
        count = min(int(count), 400 - len(self._weather_age))
        group = self.ctx.emit_particles(self._weather_effect, 0.0, 0.0,
                                        count=count, color=(1.0, 1.0, 1.0, 0.0),
                                        motion='manual')
        self.weather_dropped += group.dropped
        n = group.count
        if not n:
            return group
        # InitWeatherFalling consumes eight source random floats per petal in
        # this exact order. Source initial ANM48 itself consumes no random value.
        randoms = self.port.rng.random((n, 8))
        position = np.empty((n, 3), np.float32)
        position[:, 0] = randoms[:, 0] * 160 - 80
        position[:, 1] = randoms[:, 1] * 160 - 80
        position[:, 2] = randoms[:, 2] * 200
        position += np.asarray(self.source_camera, np.float32) + np.asarray(
            self.source_look, np.float32,
        ) / 2
        velocity = np.empty((n, 3), np.float32)
        velocity[:, 0] = randoms[:, 3] * 0.06 - 0.03
        velocity[:, 1] = randoms[:, 4] * 0.06 - 0.03
        velocity[:, 2] = -randoms[:, 5] * 0.1
        self._weather_position = np.concatenate((self._weather_position, position))
        self._weather_velocity = np.concatenate((self._weather_velocity, velocity))
        self._weather_rotation = np.concatenate((self._weather_rotation, randoms[:, 6] * math.tau - math.pi))
        self._weather_spin = np.concatenate((self._weather_spin, randoms[:, 7] * math.pi / 50 - math.pi / 100))
        self._weather_age = np.concatenate((self._weather_age, np.zeros(n, np.float32)))
        if self._weather_group is None:
            self._weather_group = group
        else:
            previous = self._weather_group
            self._weather_group = replace(
                previous, indices=np.concatenate((previous.indices, group.indices)),
                generations=np.concatenate((previous.generations, group.generations)),
                requested=previous.count + group.count,
            )
        self._project_weather()
        return group

    def _camera_loop(self):
        t = self.section_age
        if self.current_label == 2:
            return max(0, int((t - 380) // 500)), 512.0
        if self.current_label in (3, 4):
            return int(t // (400 if self.current_label == 3 else 300)), 512.0
        if self.current_label == 5:
            return int(t // 100), -512.0
        return 0, 0.0

    def _project_weather(self):
        if self._weather_group is None:
            return
        relative = self._weather_position - np.asarray(self.source_camera, np.float32)
        # Source look direction is constant throughout stage6. LH camera right
        # is cross(up, forward); screen Y down is handled only at the final map.
        forward = np.asarray(self.source_look, np.float32)
        forward /= np.linalg.norm(forward)
        right = np.cross(np.asarray((0, 1, 0), np.float32), forward)
        right /= np.linalg.norm(right)
        up = np.cross(forward, right)
        depth = relative @ forward
        distance = np.linalg.norm(relative, axis=1)
        valid = (depth / np.maximum(distance, 1e-6) >= 0.94)
        valid &= (self._weather_position[:, 2] < 0) & (self._weather_age < 300)
        valid &= (depth >= 30) & (depth <= 1800)
        if not valid.all():
            group = self._weather_group
            removed = replace(group, indices=group.indices[~valid],
                              generations=group.generations[~valid], requested=int((~valid).sum()))
            self.ctx.clear_particles(removed)
            if not valid.any():
                self._weather_group = None
            else:
                self._weather_group = replace(
                    group, indices=group.indices[valid], generations=group.generations[valid],
                    requested=int(valid.sum()),
                )
            for name in ("position", "velocity", "rotation", "spin", "age"):
                attribute = "_weather_" + name
                setattr(self, attribute, getattr(self, attribute)[valid])
            relative, depth = relative[valid], depth[valid]
        if self._weather_group is None:
            return
        pixel_scale = 224 / (math.tan(self.state.camera.fovy / 2) * depth)
        output = np.empty((len(depth), 2), np.float32)
        output[:, 0] = (relative @ right) * pixel_scale / 192
        output[:, 1] = (relative @ up) * pixel_scale / 192
        age = self._weather_age
        alpha = np.minimum(age / 30, (330 - age) / 300) * (64 / 255)
        if not self.state.scene_enabled:
            alpha.fill(0.0)
        color = np.ones((len(depth), 4), np.float32)
        color[:, 3] = alpha
        # Original ANM scale shrinks linearly from .2. The particle renderer's
        # base pixel scale is 2/448; author coordinates use 192px/world-unit.
        scale = pixel_scale * np.maximum(0.0, 0.2 - age / 1500) * (448 / 384)
        self.ctx.transform_particles(
            self._weather_group, position=output, scale=scale[:, None], color=color,
            rotation=-np.rad2deg(self._weather_rotation),
        )

    def _camera_y(self):
        t = self.section_age
        if self.current_label == 0:
            if t < 1000:
                return 2000 * (t / 1000) ** 2
            return _lerp(2000, 4000, 1 - (1 - min(1.0, (t - 1000) / 1000)) ** 2)
        if self.current_label == 1:
            if t < 200:
                return _lerp(4000, 4512, (t / 200) ** 2)
            return _lerp(4512, 5024, 1 - (1 - min(1.0, (t - 200) / 120)) ** 2)
        if self.current_label == 2:
            if t < 200:
                return _lerp(5024, 4512, (t / 200) ** 2)
            if t < 320:
                return _lerp(4512, 4000, 1 - (1 - (t - 200) / 120) ** 2)
            if t < 380:
                return _lerp(4000, 3970, ((t - 320) / 60) ** 2)
            return _lerp(3970, 3458, ((t - 380) % 500) / 500)
        if self.current_label in (3, 4):
            duration = 400 if self.current_label == 3 else 300
            return _lerp(3970, 3458, (t % duration) / duration)
        # Source label5 contains two same-frame camera setups. The second
        # replaces the first interpolation: the actual loop is 3458 -> 3970
        # over 100 frames, not the discarded 2946 -> 3458 / 200-frame setup.
        return _lerp(3458, 3970, (t % 100) / 100)

    def _apply(self):
        y = self._camera_y()
        self.source_camera = (0.0, y, -500.0)
        self.state.camera.eye = (0.0, y, 500.0)
        self.state.camera.at = (0.0, y + 50.0, 100.0)
        self.state.scene_alpha = min(1.0, max(0.0, (self.age - 350) / 40))
        show_scene = not self.spell_active or self.spell_age < 60
        self.state.scene_enabled = show_scene
        self.backdrop.enabled = self.sigil.enabled = show_scene
        if self.current_label < 2:
            brightness = min(1.0, max(0.0, (self.age - 350) / 40))
            self.backdrop.color = (brightness, brightness, brightness, 1.0)
            self.backdrop.alpha = 1.0
        else:
            t = self.section_age / 60
            self.backdrop.color = _mix_color(self._tint_start, self._tint_end, t)
            self.backdrop.alpha = _lerp(self._base_alpha_start, self._base_alpha_end, t)
        # stg6bg script4: rotation, initial quartic scale-in/move, then
        # 400-frame alpha/scale breathing. It remains behind scene geometry.
        t = self.age
        self.sigil.rotation = -t * 0.015707964
        if t < 400:
            phase = t / 400
            scale = _lerp(2.0, 1.0, 1 - (1 - phase) ** 4)
            self.sigil.alpha = phase
            center_y = _lerp(240, 168, phase)
        else:
            phase = (t - 400) % 800
            if phase < 400:
                scale = _lerp(1.0, 1.5, phase / 400)
                self.sigil.alpha = _lerp(1.0, 32 / 255, phase / 400)
            else:
                scale = _lerp(1.5, 1.0, (phase - 400) / 400)
                self.sigil.alpha = _lerp(32 / 255, 1.0, (phase - 400) / 400)
            center_y = 168
        self.sigil.scale = (254 * scale / 384, 254 * scale / 448)
        self.sigil.center = (0.5, 1 - (center_y - 16) / 448)
        if not self._spell_layers:
            return
        first, second = self._spell_layers
        fade = min(1.0, self.spell_age / 60)
        first.alpha = fade
        second.alpha = fade
        if self.spell_kind == "yuyuko":
            # eff06b sprite is 384x448 on a repeating 256 texture. Its source
            # scroll instruction adds +V each frame; GL's flipped V is negative.
            first.uv_offset = (0.0, -(self.spell_age * 0.008333334) / 1.75)
            second.alpha = fade * 224 / 255
        else:
            normal_time = max(0.0, self._normal_age - 60)
            second.rotation = self._normal_rotation + normal_time * 0.007853982
            phase = normal_time % 300
            start_scale = self._normal_scale if normal_time < 150 else 2.304886
            scale = _lerp(start_scale, 2.904886, phase / 150) if phase < 150 else _lerp(
                2.904886, 2.304886, (phase - 150) / 150,
            )
            second.scale = (256 * scale / 384, 256 * scale / 448)
            first.color = second.color = (1.0, 1.0, 1.0, 1.0)
            second.blend = "normal"
            if self.slash_active:
                first.alpha = 64 / 255
                first.color = (*_rgb(0xff4040), 1.0)
                second.alpha = 1.0
                second.color = (*_rgb(0xff60ff), 1.0)
                second.blend = "add"
                # eff05b's interrupt2 updates an angular-velocity variable each
                # frame. Integrate it directly rather than executing ANM math.
                t = self.slash_age
                second.rotation = self._slash_rotation - (
                    0.06283186 * t - 0.0012822828 * t * (t + 1) / 2
                )

    async def run(self):
        try:
            while not self._closed:
                await wait_frames(1, clock="control")
                frames = self.ctx.get_simulation_rate("background")
                previous_loop, shift = self._camera_loop()
                self.age += frames
                self.section_age += frames
                if self.spell_active:
                    self.spell_age += frames
                    self._normal_age += frames
                if self.slash_active:
                    self.slash_age += frames
                self._apply()
                current_loop, _ = self._camera_loop()
                if self._weather_group is not None:
                    self._weather_position[:, 1] += (current_loop - previous_loop) * shift
                    self._weather_velocity[:, 2] -= 0.015 * frames
                    self._weather_position += self._weather_velocity * frames
                    self._weather_rotation += self._weather_spin * frames
                    self._weather_age += frames
                    self._project_weather()
        finally:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._weather_group is not None:
            self.ctx.clear_particles(self._weather_group)
            self._weather_group = None
        self.state.clear()


__all__ = ["TH07Stage6Background"]

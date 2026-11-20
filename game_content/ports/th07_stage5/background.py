"""TH07 stage-5 scenery and weather on PySTG's existing background/pool path.

Static geometry comes from the local importer. One ordinary Task advances the
finite camera choreography, four cloud offsets, eff05 materials, and packed
weather arrays. Source STD/ANM/ECL instructions are never interpreted here.
"""

from __future__ import annotations

from dataclasses import replace
import math

import numpy as np

from src.game.background import SceneQuad, ScreenLayer
from src.game.particle import ParticleEffect
from src.game.tasks import wait_frames


def _clamp(value):
    return min(1.0, max(0.0, value))


def _lerp(start, end, fraction):
    t = _clamp(fraction)
    return tuple(a + (b - a) * t for a, b in zip(start, end))


def _rgb(value):
    return tuple(((value >> shift) & 255) / 255 for shift in (16, 8, 0))


def _cubic(start, end, tangent_start, tangent_end, fraction):
    """Literal Stage.cpp InterpCubic, not Bezier control points."""
    t = _clamp(fraction)
    a, b = (t - 1) ** 2 * (2 * t + 1), t * t * (3 - 2 * t)
    c, d = (1 - t) ** 2 * t, (t - 1) * t * t
    return tuple(a * p + b * q + c * u + d * v for p, q, u, v in zip(
        start, end, tangent_start, tangent_end,
    ))


def _layer(resources, sprite_id):
    path, (x, y, width, height), (tw, th) = resources.source_image(sprite_id)
    return ScreenLayer(path, uv_rect=(x / tw, 1 - (y + height) / th,
                                     (x + width) / tw, 1 - y / th), alpha=0.0)


class TH07Stage5Background:
    """Stage-owned original scenery; no private scheduler or renderer."""

    def __init__(self, port):
        self.port, self.ctx, self.resources = port, port.ctx, port.assets
        self.state = self.ctx.background
        self.age = 0.0
        self.weather_script_age = 0.0
        self.spell_active = False
        self.spell_kind = "youmu"
        self.spell_age = self.slash_age = 0.0
        self.slash_active = False
        self._normal_age = self._normal_rotation = self._slash_rotation = 0.0
        self._normal_scale = 2.304886
        self._spell_layers = []
        self._closed = False
        self._weather_group = None
        self._weather_position = np.empty((0, 3), np.float32)
        self._weather_velocity = np.empty((0, 3), np.float32)
        self._weather_acceleration = np.empty((0, 3), np.float32)
        self._weather_rotation = np.empty(0, np.float32)
        self._weather_spin = np.empty(0, np.float32)
        self._weather_age = np.empty(0, np.float32)
        self._weather_kind = np.empty(0, np.int8)
        self._weather_next = 1.0
        self._weather_started = self._weather_sound = self._weather_accelerated = False
        self.weather_dropped = 0
        self.weather_peak = 0
        self._weather_effect = ParticleEffect(("th07_etama_e1_s48",), lifetime=1,
                                              alpha=1, alpha_end=1, layer="back")
        definition = self.resources.background_definition
        quads = [SceneQuad(
            str(self.resources.root / item["texture"]),
            tuple(tuple(vertex) for vertex in item["vertices"]),
            tuple(item["uv_rect"]), tuple(item["color"]),
            group=item["group"],
            billboard_center=None if item["billboard_center"] is None else tuple(item["billboard_center"]),
            depth_test=item["depth_test"], depth_write=item["depth_write"],
            fog_mode=item["fog_mode"],
        ) for item in definition["quads"]]
        self.state.set_scene(quads, clear_color=(*_rgb(0x201020), 1.0))
        self.state.set_camera(fovy=0.6283185482025146, up=(0.0, 0.0, 1.0),
                              z_near=30, z_far=1800)
        self.state.set_fog(enabled=True)
        self._apply()

    def label(self, index):
        raise ValueError(f"TH07 stage 5 STD has no external labels (requested {index})")

    def start_at_boss(self):
        """Practice entry, not replay seek: skip the road's initial weather."""
        self.age = 9652.0
        self.weather_script_age = 5400.0
        self._weather_next = 5401.0
        self._weather_started = self._weather_sound = self._weather_accelerated = True
        self._apply()

    def start_at_midboss(self):
        """Practice entry at the original road cue, without replaying 4820 frames."""
        self.age = self.weather_script_age = 4820.0
        self._weather_next = 4821.0
        self._weather_started = True
        self._apply()

    def set_spell(self, active, *, kind="youmu"):
        if kind != "youmu":
            raise ValueError("TH07 stage 5 only defines the Youmu spell background")
        self.spell_active = bool(active)
        self.spell_age = self.slash_age = self._normal_age = 0.0
        self._normal_rotation = 0.0
        self._normal_scale = 2.304886
        self.slash_active = False
        self._spell_layers = []
        if active:
            self._spell_layers = [_layer(self.resources, sprite) for sprite in
                                  self.resources.background_definition["spell_sprites"]["youmu"]]
        self.state.set_layers(self._spell_layers)
        self._apply()

    def set_slash(self, active):
        self.slash_active = bool(active)
        self.slash_age = 0.0
        if self._spell_layers:
            self._slash_rotation = self._spell_layers[1].rotation
            if not active:
                self._normal_rotation = self._spell_layers[1].rotation
                self._normal_scale = self._spell_layers[1].scale[0] * 384 / 256
                self._normal_age = 60.0
        self._apply()

    def _camera(self):
        t = self.age
        if t < 5200:
            return _cubic((0, 0, -800), (0, 2000, -2800),
                          (0, 0, 0), (0, 2, -2), t / 5200)
        if t < 5500:
            return _cubic((0, 2000, -2800), (-50, 2050, -2800),
                          (0, 2, -2), (0, 2, -2), (t - 5200) / 300)
        if t < 8500:
            return _cubic((-50, 2050, -2800), (-50, 5050, -5800),
                          (0, 2, -2), (0, 2, -2), (t - 5500) / 3000)
        if t < 8628:
            return _lerp((-50, 5050, -5800), (-50, 5082, -5832), ((t - 8500) / 128) ** 2)
        if t < 9140:
            return _lerp((-50, 5082, -5832), (-50, 5466, -6216), (t - 8628) / 512)
        if t < 9652:
            return _lerp((-50, 5466, -6216), (-50, 5850, -6600), (t - 9140) / 512)
        return _lerp((-50, 5850, -6600), (-50, 6618, -7368), ((t - 9652) % 1024) / 1024)

    @staticmethod
    def _cloud_offset(age, start):
        t = max(0.0, age - start) % 600
        if t < 150:
            return 16 * (1 - (t / 150) ** 2) if age >= start + 600 else 0.0
        if t < 300:
            return -16 * (1 - (1 - (t - 150) / 150) ** 2)
        if t < 450:
            return -16 * (1 - ((t - 300) / 150) ** 2)
        return 16 * (1 - (1 - (t - 450) / 150) ** 2)

    def _apply(self):
        self.source_camera = self._camera()
        self.source_look = _lerp((0, 400, 20), (70, 300, 10), (self.age - 5200) / 300)
        x, y, z = self.source_camera
        dx, dy, dz = self.source_look
        self.state.camera.eye = x, y, -z
        self.state.camera.at = x + dx, y + dy, -(z + dz)
        fog_t = _clamp((self.age - 900) / 60)
        fog_color = _lerp(_rgb(0x201020), _rgb(0xb08090), fog_t)
        self.state.set_fog(color=(*fog_color, 1), start=200 + 500 * fog_t,
                           end=800 + 100 * fog_t)
        self.state.clear_color = (*fog_color, 1)
        self.state.scene_enabled = not self.spell_active or self.spell_age < 60
        for script, start in ((17, 0), (18, 100), (19, 200), (20, 150)):
            self.state.group_offsets[f"cloud_{script}"] = (self._cloud_offset(self.age, start), 0.0, 0.0)
        if not self._spell_layers:
            return
        first, second = self._spell_layers
        fade = _clamp(self.spell_age / 60)
        first.alpha = second.alpha = fade
        first.color = second.color = (1.0, 1.0, 1.0, 1.0)
        second.blend = "normal"
        normal_time = max(0.0, self._normal_age - 60)
        phase = normal_time % 300
        scale_start = self._normal_scale if normal_time < 150 else 2.304886
        scale = (scale_start + (2.904886 - scale_start) * phase / 150 if phase < 150 else
                 2.904886 - .6 * (phase - 150) / 150)
        second.scale = 256 * scale / 384, 256 * scale / 448
        second.rotation = self._normal_rotation + normal_time * .007853982
        if self.slash_active:
            first.alpha, first.color = 64 / 255, (*_rgb(0xff4040), 1.0)
            second.alpha, second.color, second.blend = 1.0, (*_rgb(0xff60ff), 1.0), "add"
            t = self.slash_age
            second.rotation = self._slash_rotation - (.06283186 * t - .0012822828 * t * (t + 1) / 2)

    def emit_weather(self, count, kind=31):
        """Source Effect30/31; one generation-safe pool batch, eight RNG floats."""
        if kind not in (30, 31):
            raise ValueError("stage-5 weather kind must be source effect 30 or 31")
        count = min(int(count), 400 - len(self._weather_age))
        group = self.ctx.emit_particles(self._weather_effect, 0, 0, count=count,
                                        color=(1, 1, 1, 0), motion="manual")
        self.weather_dropped += group.dropped
        n = group.count
        if not n:
            return group
        randoms = self.port.rng.random((n, 8))
        position = np.empty((n, 3), np.float32)
        position[:, :2] = randoms[:, :2] * 160 - 80
        position[:, 2] = randoms[:, 2] * (100 if kind == 30 else 200) - (100 if kind == 30 else 0)
        position += np.asarray(self.source_camera, np.float32) + np.asarray(self.source_look, np.float32) / 2
        velocity = np.empty((n, 3), np.float32)
        velocity[:, :2] = randoms[:, 3:5] * .06 - .03
        velocity[:, 2] = randoms[:, 5] * .02 + .01 if kind == 30 else -randoms[:, 5] * .1
        acceleration = np.zeros((n, 3), np.float32)
        if kind == 31:
            acceleration[:, 2] = -.015
        data = {"position": position, "velocity": velocity, "acceleration": acceleration,
                "rotation": randoms[:, 6] * math.tau - math.pi,
                "spin": randoms[:, 7] * math.pi / 50 - math.pi / 100,
                "age": np.zeros(n, np.float32), "kind": np.full(n, kind, np.int8)}
        for name, values in data.items():
            attribute = "_weather_" + name
            setattr(self, attribute, np.concatenate((getattr(self, attribute), values)))
        if self._weather_group is None:
            self._weather_group = group
        else:
            previous = self._weather_group
            self._weather_group = replace(previous, indices=np.concatenate((previous.indices, group.indices)),
                                           generations=np.concatenate((previous.generations, group.generations)),
                                           requested=previous.count + group.count)
        self.weather_peak = max(self.weather_peak, len(self._weather_age))
        self._project_weather()
        return group

    def accelerate_weather(self):
        """ExIns9 changes only already-living Effect30 Z acceleration."""
        self._weather_acceleration[self._weather_kind == 30, 2] = -.01

    def _advance_weather_script(self):
        t = self.weather_script_age
        if t < 1:
            return
        if not self._weather_started:
            self.emit_weather(64, kind=30)
            self._weather_started = True
        if t >= 5081 and not self._weather_sound:
            self.port.play_se(19)
            self._weather_sound = True
        if t >= 5201 and not self._weather_accelerated:
            self.accelerate_weather()
            self.ctx.shake_screen(frames=80, amplitude=8)
            self.ctx.emit_event("th07.weather.acceleration", {"frames": 80, "amplitude": 8})
            self._weather_accelerated = True
        while self._weather_next <= t + 1e-8:
            if self._weather_next < 5201:
                kind, count, interval = 30, 2, 4
            else:
                kind, count = 31, 4
                interval = 2 if self._weather_next < 5401 else 4
            self.emit_weather(count, kind=kind)
            self._weather_next += interval

    def _project_weather(self):
        if self._weather_group is None:
            return
        relative = self._weather_position - np.asarray(self.source_camera, np.float32)
        forward = np.asarray(self.source_look, np.float32)
        forward /= np.linalg.norm(forward)
        right = np.cross(np.asarray((0, 0, -1), np.float32), forward)
        right /= np.linalg.norm(right)
        up = np.cross(forward, right)
        depth = relative @ forward
        distance = np.linalg.norm(relative, axis=1)
        valid = ((depth / np.maximum(distance, 1e-6) >= .94) &
                 (self._weather_position[:, 2] < 0) & (self._weather_age < 300) &
                 (depth >= 30) & (depth <= 1800))
        if not valid.all():
            group = self._weather_group
            self.ctx.clear_particles(replace(group, indices=group.indices[~valid],
                                             generations=group.generations[~valid],
                                             requested=int((~valid).sum())))
            self._weather_group = (replace(group, indices=group.indices[valid],
                                           generations=group.generations[valid], requested=int(valid.sum()))
                                   if valid.any() else None)
            for name in ("position", "velocity", "acceleration", "rotation", "spin", "age", "kind"):
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
        color = np.ones((len(depth), 4), np.float32)
        color[:, 3] = np.minimum(age / 30, (330 - age) / 300) * (64 / 255)
        if not self.state.scene_enabled:
            color[:, 3] = 0
        scale = pixel_scale * np.maximum(0, .2 - age / 1500) * (448 / 384)
        self.ctx.transform_particles(self._weather_group, position=output, scale=scale[:, None],
                                     color=color, rotation=-np.rad2deg(self._weather_rotation))

    async def run(self):
        try:
            while not self._closed:
                await wait_frames(1, clock="control")
                frames = self.ctx.get_simulation_rate("background")
                old_loop = max(0, int((self.age - 9652) // 1024))
                self.age += frames
                self.weather_script_age += self.ctx.get_simulation_rate("scripts")
                if self.spell_active:
                    self.spell_age += frames
                    self._normal_age += frames
                if self.slash_active:
                    self.slash_age += frames
                self._apply()
                new_loop = max(0, int((self.age - 9652) // 1024))
                if self._weather_group is not None:
                    shift = (new_loop - old_loop) * 768
                    self._weather_position[:, 1] -= shift
                    self._weather_position[:, 2] += shift
                    self._weather_velocity += self._weather_acceleration * frames
                    self._weather_position += self._weather_velocity * frames
                    self._weather_rotation += self._weather_spin * frames
                    self._weather_age += frames
                    self._project_weather()
                self._advance_weather_script()
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


__all__ = ["TH07Stage5Background"]

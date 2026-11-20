"""Headless, stage-owned background state consumed by the existing renderer.

Coordinates and camera angles use world units/radians; velocities use control
frames, like StageContext. Content Tasks own choreography and cancellation.
Neither this module nor its update method interprets scripts or owns GL objects.
"""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SceneQuad:
    """Immutable scene geometry; four vertices in perimeter order, GL UVs."""

    texture_path: str
    vertices: tuple
    uv_rect: tuple = (0.0, 0.0, 1.0, 1.0)
    color: tuple = (1.0, 1.0, 1.0, 1.0)
    blend: str = "normal"
    group: str | None = None
    billboard_center: tuple | None = None
    depth_test: bool = False
    depth_write: bool = False
    fog_mode: str = "depth"


@dataclass
class ScreenLayer:
    """Screen-space image below gameplay. Mutable material, no per-pixel work."""

    texture_path: str
    alpha: float = 1.0
    color: tuple = (1.0, 1.0, 1.0, 1.0)
    uv_offset: tuple = (0.0, 0.0)
    uv_velocity: tuple = (0.0, 0.0)
    uv_scale: tuple = (1.0, 1.0)
    rotation: float = 0.0
    rotation_velocity: float = 0.0
    scale: tuple = (1.0, 1.0)
    center: tuple = (0.5, 0.5)
    blend: str = "normal"
    enabled: bool = True
    uv_rotation: float = 0.0
    placement: str = "front"
    uv_rect: tuple = (0.0, 0.0, 1.0, 1.0)


@dataclass
class BackgroundCamera:
    eye: tuple = (0.0, 0.0, 1.0)
    at: tuple = (0.0, 0.0, 0.0)
    up: tuple = (0.0, 1.0, 0.0)
    fovy: float = 0.8
    z_near: float = 0.01
    z_far: float = 10000.0


@dataclass
class BackgroundFog:
    color: tuple = (0.0, 0.0, 0.0, 1.0)
    start: float = 300.0
    end: float = 600.0
    enabled: bool = False


class BackgroundState:
    """One stage's scene/material state, independent of rendering availability.

    set_scene changes the geometry revision; moving the camera or changing fog
    does not. The renderer uploads a scene once per revision, not once per frame.
    An empty state leaves existing Stage1-3 background behavior untouched.
    """

    def __init__(self):
        self.scene_revision = 0
        self.layers_revision = 0
        self.camera = BackgroundCamera()
        self.fog = BackgroundFog()
        self.quads = ()
        self.layers = []
        self.clear_color = (0.0, 0.0, 0.0, 1.0)
        self.scene_offset = (0.0, 0.0, 0.0)
        self.scene_alpha = 1.0
        self.scene_enabled = True
        self.group_offsets = {}

    @property
    def active(self):
        return bool(self.quads or self.layers)

    def set_scene(self, quads: Iterable[SceneQuad], *, clear_color=None):
        self.quads = tuple(quads)
        if clear_color is not None:
            self.clear_color = tuple(clear_color)
        self.scene_revision += 1

    def set_camera(self, *, eye=None, at=None, up=None, fovy=None,
                   z_near=None, z_far=None):
        for name, value in (("eye", eye), ("at", at), ("up", up),
                            ("fovy", fovy), ("z_near", z_near),
                            ("z_far", z_far)):
            if value is not None:
                setattr(self.camera, name, value)

    def set_fog(self, *, color=None, start=None, end=None, enabled=None):
        for name, value in (("color", color), ("start", start),
                            ("end", end), ("enabled", enabled)):
            if value is not None:
                setattr(self.fog, name, value)

    def set_layers(self, layers: Iterable[ScreenLayer]):
        self.layers = list(layers)
        self.layers_revision += 1

    def update(self, frames):
        """Advance only inexpensive layer velocities in the background time domain."""
        if not frames:
            return
        for layer in self.layers:
            if layer.enabled:
                x, y = layer.uv_offset
                vx, vy = layer.uv_velocity
                layer.uv_offset = ((x + vx * frames) % 1.0,
                                   (y + vy * frames) % 1.0)
                layer.rotation += layer.rotation_velocity * frames

    def clear(self):
        """Release stage-owned references; next render drops cached geometry."""
        self.quads = ()
        self.layers = []
        self.camera = BackgroundCamera()
        self.fog = BackgroundFog()
        self.clear_color = (0.0, 0.0, 0.0, 1.0)
        self.scene_offset = (0.0, 0.0, 0.0)
        self.scene_alpha = 1.0
        self.scene_enabled = True
        self.group_offsets.clear()
        self.scene_revision += 1
        self.layers_revision += 1

    reset = clear

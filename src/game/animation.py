"""Sparse actor animations, not a task or collision system.

Playback uses simulation frames. SpriteBatch caches atlas geometry and packs
existing sprite instances in one Numba call; GL resources stay in the renderer.
Large populations of disposable decoration should still use ParticlePool.
"""

from dataclasses import dataclass
import math

import numpy as np
from numba import njit


def resolve_animation(assets, name):
    animation = assets.get_animation(name)
    if animation is None:
        sprite = assets.get_sprite(name)
        if sprite is None:
            raise ValueError(f'unknown animation or sprite: {name}')
        from ..resource.texture_asset import AnimatedSprite, SpriteFrame
        animation = AnimatedSprite(name, sprite.texture_path,
                                   [SpriteFrame(sprite.rect, sprite.center)],
                                   frame_duration=1.0/60.0, loop=True)
    return animation


@dataclass
class SpriteVisual:
    offset: tuple = (0.0, 0.0)
    rotation: float = 0.0
    scale: tuple = (1.0, 1.0)
    color: tuple = (1.0, 1.0, 1.0, 1.0)
    blend: str = 'alpha'

    def set(self, *, offset=None, rotation=None, scale=None, color=None,
            alpha=None, blend=None):
        # Validate before changing any field, including partial color updates.
        values = {}
        for name, value, count in (('offset', offset, 2), ('scale', scale, 2),
                                   ('color', color, 4)):
            if value is not None:
                if name == 'scale' and np.isscalar(value):
                    value = (value, value)
                value = tuple(float(x) for x in value)
                if len(value) != count or not all(math.isfinite(x) for x in value):
                    raise ValueError(f'{name} requires {count} finite values')
                values[name] = value
        if rotation is not None:
            if not math.isfinite(float(rotation)):
                raise ValueError('rotation must be finite')
            values['rotation'] = float(rotation)
        if alpha is not None:
            if not math.isfinite(float(alpha)):
                raise ValueError('alpha must be finite')
            values['color'] = (*values.get('color', self.color)[:3], float(alpha))
        if blend is not None:
            if blend not in ('alpha', 'add'):
                raise ValueError('blend must be alpha or add')
            values['blend'] = blend
        for name, value in values.items():
            setattr(self, name, value)
        return self


class AnimationPlayback:
    """One playback handle. Replacing/stopping it unblocks its awaiters.

    ``await handle`` returns the handle; check finished versus cancelled.
    Looping playback intentionally waits until explicitly stopped.
    Resource loop settings are never mutated by a playback override.
    """

    def __init__(self, animation, *, loop=None, speed=1.0):
        if (not animation.frames or not math.isfinite(animation.frame_duration)
                or animation.frame_duration <= 0):
            raise ValueError('animation needs frames and a positive frame duration')
        self.animation = animation
        self.loop = animation.loop if loop is None else bool(loop)
        self.speed = speed
        self.elapsed_frames = 0.0
        self.paused = False
        self.finished = False
        self.cancelled = False
        self._born_frame = None

    @property
    def speed(self):
        return self._speed

    @speed.setter
    def speed(self, value):
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError('animation speed must be finite and positive')
        self._speed = value

    @property
    def done(self):
        return self.finished or self.cancelled

    @property
    def duration_frames(self):
        return len(self.animation.frames) * self.animation.frame_duration * 60.0

    @property
    def frame_index(self):
        frame = int((self.elapsed_frames + 1e-8) / (self.animation.frame_duration * 60.0))
        return (frame % len(self.animation.frames) if self.loop
                else min(frame, len(self.animation.frames) - 1))

    def get_render_frame(self):
        return self.animation.frames[self.frame_index], self.animation.texture_path

    def advance(self, frames=1.0):
        if self.done or self.paused:
            return
        self.elapsed_frames += frames * self.speed
        if self.loop:
            self.elapsed_frames %= self.duration_frames
        elif self.elapsed_frames + 1e-8 >= self.duration_frames:
            self.elapsed_frames = self.duration_frames
            self.finished = True

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        if not self.finished:
            self.cancelled = True

    def __await__(self):
        from .tasks import NEXT_FRAME
        while not self.done:
            yield NEXT_FRAME
        return self


@njit(cache=True)
def _pack_sprites(n, geometry, positions, rotation, scale, color, output):
    for i in range(n):
        angle = rotation[i] * math.pi / 180.0
        c, s = math.cos(angle), math.sin(angle)
        dx = geometry[i, 6] * scale[i, 0] / 192.0
        dy = geometry[i, 7] * scale[i, 1] / 192.0
        output[i, 0] = positions[i, 0] + dx*c - dy*s
        output[i, 1] = positions[i, 1] + dx*s + dy*c
        output[i, 2] = angle
        for k in range(6):
            output[i, 3+k] = geometry[i, k]
        output[i, 7] *= scale[i, 0]
        output[i, 8] *= scale[i, 1]
        for k in range(4):
            output[i, 9+k] = color[i, k]


class SpriteBatch:
    """Reusable packing buffers; preserve source order, including alpha overlap."""

    def __init__(self, assets):
        self.assets = assets
        self._frames = {}
        self._paths = []
        self._texture_ids = {}
        self._reserve(32)
        # JIT happens during scope preparation, never at the first visible draw.
        _pack_sprites(0, self._geometry, self._position, self._rotation,
                      self._scale, self._color, self._output)

    def _reserve(self, count):
        self._capacity = count
        self._geometry = np.empty((count, 8), np.float32)
        self._position = np.empty((count, 2), np.float32)
        self._rotation = np.empty(count, np.float32)
        self._scale = np.empty((count, 2), np.float32)
        self._color = np.empty((count, 4), np.float32)
        self._output = np.empty((count, 13), np.float32)
        self._keys = np.empty(count, np.int32)

    def texture_path(self, index):
        return self._paths[index]

    def _geometry_for(self, frame, path):
        key = (id(frame), path)
        cached = self._frames.get(key)
        if cached is not None:
            return cached
        texture = self.assets.get_texture(path)
        if texture is None:
            raise RuntimeError(f'animation texture is not loaded: {path}')
        tw, th = texture.get_size()
        x, y, w, h = frame.rect
        cx, cy = frame.center
        # Historic resources with no center use the centered default.
        if (cx, cy) == (0, 0):
            cx, cy = w/2.0, h/2.0
        # The instance quad's upper edge has UV.y=0; atlases are uploaded flipped.
        geometry = np.array((x/tw, 1.0-y/th, (x+w)/tw, 1.0-(y+h)/th,
                             w, h, w/2.0-cx, cy-h/2.0), np.float32)
        tid = self._texture_ids.get(path)
        if tid is None:
            tid = len(self._paths)
            self._texture_ids[path] = tid
            self._paths.append(path)
        # Retain the frame: an id must never be reused for different geometry.
        cached = geometry, tid, frame
        self._frames[key] = cached
        return cached

    def prepare(self, draws):
        """Each draw is (position, SpriteFrame, texture_path, SpriteVisual).

        Returned views are internal scratch, consumed before the next prepare.
        """
        count = len(draws)
        if count > self._capacity:
            self._reserve(max(count, self._capacity * 2))
        for i, (position, frame, path, visual) in enumerate(draws):
            geometry, tid, _ = self._geometry_for(frame, path)
            self._geometry[i] = geometry
            self._position[i] = position
            self._rotation[i] = visual.rotation
            self._scale[i] = visual.scale
            self._color[i] = visual.color
            self._keys[i] = tid * 2 + (visual.blend == 'add')
        _pack_sprites(count, self._geometry, self._position, self._rotation,
                      self._scale, self._color, self._output)
        return self._output[:count], self._keys[:count]


class AttachedAnimation(AnimationPlayback):
    """Stage-owned decoration following an actor's visual pivot if attached.

    Parent offset and optionally rotation are inherited, not scale/color.
    Detaching preserves the world transform without extending the stage scope.
    """

    def __init__(self, animation, owner, position, *, layer='front',
                 follow_rotation=False, loop=None, speed=1.0, **visual):
        super().__init__(animation, loop=loop, speed=speed)
        if layer not in ('back', 'front'):
            raise ValueError('animation layer must be back or front')
        self.owner = owner
        self.position = tuple(position)
        self.layer = layer
        self.follow_rotation = bool(follow_rotation)
        self.visual = SpriteVisual().set(**visual)
        self._world_visual = SpriteVisual()
        self._born_frame = 0

    def set_visual(self, **values):
        return self.visual.set(**values)

    def world_transform(self):
        if self.owner is None:
            x, y = self.position
            angle = 0.0
        else:
            parent = self.owner.visual
            x = self.owner.x + parent.offset[0]
            y = self.owner.y + parent.offset[1]
            angle = parent.rotation if self.follow_rotation else 0.0
        dx, dy = self.visual.offset
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        return (x+dx*c-dy*s, y+dx*s+dy*c), angle+self.visual.rotation

    def detach(self):
        """Freeze the current world transform; continue in the same stage scope."""
        self.position, angle = self.world_transform()
        self.visual.offset = (0.0, 0.0)
        self.visual.rotation = angle
        self.owner = None
        self.follow_rotation = False
        return self

    def stop(self):
        super().stop()
        self.owner = None

    def remove(self):
        self.stop()


class AnimationCollection:
    """Finite, sparse decorations; zero work proportional to bullet/particle count."""

    def __init__(self, assets, max_attachments=512):
        self.assets = assets
        self.max_attachments = max_attachments
        self._items = []
        self.frame = 0
        self._last_updated = -1
        self.batch = SpriteBatch(assets)
        self._draws = []

    def attach(self, owner, name, *, x=0.0, y=0.0, **options):
        if owner is not None and not getattr(owner, '_active', False):
            raise RuntimeError('cannot attach an animation to an inactive actor')
        if len(self._items) >= self.max_attachments:
            self._items[:] = [item for item in self._items if not item.done]
        if len(self._items) >= self.max_attachments:
            raise RuntimeError('controlled animation capacity exceeded; use particles for bulk effects')
        item = AttachedAnimation(resolve_animation(self.assets, name), owner,
                                 (float(x), float(y)), **options)
        item._born_frame = self.frame
        self._items.append(item)
        return item

    @property
    def count(self):
        return sum(not item.done for item in self._items)

    def update(self, paused=False, frames=1.0):
        if self._last_updated == self.frame:
            return
        self._last_updated = self.frame
        retained = 0
        for item in self._items:
            if item.owner is not None and not item.owner._active:
                item.stop()
            if not paused and item._born_frame != self.frame:
                item.advance(frames)
            if not item.done:
                self._items[retained] = item
                retained += 1
            else:
                item.owner = None
        del self._items[retained:]

    def prepare_render_data(self, layer):
        draws = self._draws
        draws.clear()
        for item in self._items:
            if item.done or item.layer != layer:
                continue
            if item.owner is not None and (not item.owner._active or not item.owner.visible):
                continue
            position, angle = item.world_transform()
            frame, path = item.get_render_frame()
            # The original visual remains local, independent of the owner.
            visual = item._world_visual
            visual.rotation = angle
            visual.scale = item.visual.scale
            visual.color = item.visual.color
            visual.blend = item.visual.blend
            draws.append((position, frame, path, visual))
        return self.batch.prepare(draws)

    def remove_owner(self, owner):
        for item in self._items:
            if item.owner is owner:
                item.stop()
        self._items[:] = [item for item in self._items if not item.done]

    def clear(self):
        for item in self._items:
            item.stop()
        self._items.clear()
        self._draws.clear()

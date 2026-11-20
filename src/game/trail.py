"""Sparse, non-colliding continuous textured trails on existing actors.

History is a bounded NumPy ring. Only actor attachment/update is Python work;
sampling and the continuous triangle ribbon are Numba kernels. Rendering never
advances history, and no trail node owns an object, callback, or task.
"""

import math

import numpy as np
from numba import njit


@njit(cache=True)
def _sample(history, head, count, old_x, old_y, x, y, remainder, frames):
    samples = int(math.floor(remainder + frames + 1e-8))
    for j in range(samples):
        t = min(1.0, (j + 1.0 - remainder) / frames)
        sx = old_x + (x - old_x) * t
        sy = old_y + (y - old_y) * t
        dx, dy = sx - history[head, 0], sy - history[head, 1]
        angle = history[head, 2]
        if dx * dx + dy * dy > 1e-16:
            angle = math.atan2(dy, dx)
            if count == 1:
                history[head, 2] = angle
        head = (head + 1) % len(history)
        history[head, 0] = sx
        history[head, 1] = sy
        history[head, 2] = angle
        count = min(count + 1, len(history))
    return head, count


@njit(cache=True)
def _pack_trail(history, head, count, node_step, half_width, uv, color,
                key, output, keys, start):
    nodes = (count + node_step - 1) // node_step
    if nodes < 2:
        return start
    # Source TH07 AngleLerp: average the smaller of direct/wrapped distances
    # from the smaller angle. Preserve that source convention at wrap points.
    previous_x0 = previous_y0 = previous_x1 = previous_y1 = previous_u = 0.0
    for node in range(nodes):
        j = node * node_step
        h = (head - j) % len(history)
        angle = history[h, 2]
        if j:
            previous_angle = -history[(head - j + 1) % len(history), 2]
            source_angle = -angle
            low = min(previous_angle, source_angle)
            direct = abs(previous_angle - source_angle)
            angle = -(low + min(direct, 2.0 * math.pi - direct) * 0.5)
        # World Y is opposite to the source screen Y. Its UV-start edge is
        # therefore the negative world normal, rather than +(-sin, cos).
        nx, ny = math.sin(angle) * half_width, -math.cos(angle) * half_width
        x0, y0 = history[h, 0] + nx, history[h, 1] + ny
        x1, y1 = history[h, 0] - nx, history[h, 1] - ny
        u = uv[2] + (uv[0] - uv[2]) * node / (nodes - 1)
        if node:
            for vertex in range(6):
                dst = start + vertex
                if vertex == 0 or vertex == 3:
                    output[dst, 0], output[dst, 1] = previous_x0, previous_y0
                    output[dst, 2], output[dst, 3] = previous_u, uv[1]
                elif vertex == 1:
                    output[dst, 0], output[dst, 1] = previous_x1, previous_y1
                    output[dst, 2], output[dst, 3] = previous_u, uv[3]
                elif vertex == 2 or vertex == 4:
                    output[dst, 0], output[dst, 1] = x1, y1
                    output[dst, 2], output[dst, 3] = u, uv[3]
                else:
                    output[dst, 0], output[dst, 1] = x0, y0
                    output[dst, 2], output[dst, 3] = u, uv[1]
                for component in range(4):
                    output[dst, 4 + component] = color[component]
                keys[dst] = key
            start += 6
        previous_x0, previous_y0, previous_x1, previous_y1, previous_u = x0, y0, x1, y1, u
    return start


class TrailHandle:
    """One stage-owned ribbon following an actor; cancelling never kills it."""

    def __init__(self, collection, owner, sprite, history_frames, node_step,
                 width, blend, layer, hide_owner, follow_owner_color):
        self._collection = collection
        self.owner = owner
        self.sprite = sprite
        self.node_step = node_step
        self.width = width
        self.layer = layer
        self.hide_owner = hide_owner
        self.follow_owner_color = follow_owner_color
        self._key = int(collection.sprite_registry.get_texture_index(sprite)) * 2 + int(blend == 'add')
        self._uv = collection.sprite_registry.get_uv_array()[sprite].copy()
        # The engine uploads actor atlases with flip_y=True. Registry rects
        # store low-V/high-V, whereas a source ribbon's edge 0 needs the
        # original image's top row (high GL V), as SpriteBatch does. Keep this
        # conversion local; bullet/particle registry conventions are unchanged.
        self._uv[1], self._uv[3] = self._uv[3], self._uv[1]
        self._height = float(collection.sprite_registry.get_size_array()[sprite, 1]) / 192.0
        self._color = np.ones(4, np.float32)
        self._history = np.empty((history_frames, 3), np.float32)
        self._history[0] = (owner.x, owner.y, 0.0)
        self._head, self._count = 0, 1
        self._observed = float(owner.x), float(owner.y)
        self._remainder = 0.0
        self._cancelled = False
        self._maximum_vertices = 6 * ((history_frames + node_step - 1) // node_step - 1)

    @property
    def done(self):
        return self._cancelled or self.owner is None or not getattr(self.owner, '_active', True)

    def cancel(self):
        self._collection._remove(self)


class TrailCollection:
    """Finite sparse attachments; empty collections allocate no history/mesh.

    Width is the full world-space width; omitted width follows sprite height
    and the owner's current visual Y scale. Explicit width is fixed. Colors
    follow the current owner RGBA (including fade) unless disabled. Returned
    render arrays are internal scratch, valid until the next prepare call.
    """

    def __init__(self, sprite_registry, capacity=128):
        self.sprite_registry = sprite_registry
        self.capacity = int(capacity)
        if self.capacity < 1:
            raise ValueError('trail capacity must be positive')
        self._items = []
        self._vertices = np.empty((0, 8), np.float32)
        self._keys = np.empty(0, np.int32)
        self._last_frame = None

    @staticmethod
    def warmup():
        """Opt-in scope preparation, with no owners or visible/history state."""
        history = np.zeros((2, 3), np.float32)
        head, count = _sample(history, 0, 1, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0)
        _pack_trail(history, head, count, 1, 0.5, np.zeros(4, np.float32),
                    np.ones(4, np.float32), 0, np.empty((6, 8), np.float32),
                    np.empty(6, np.int32), 0)

    @property
    def count(self):
        return len(self._items)

    def attach(self, owner, sprite_id, *, history_frames=48, node_step=1,
               width=None, blend='alpha', layer='main', hide_owner=False,
               follow_owner_color=True):
        if owner is None or not getattr(owner, '_active', True):
            raise ValueError('trail needs an active owner')
        if len(self._items) >= self.capacity:
            raise RuntimeError('trail capacity exceeded')
        history_frames, node_step = int(history_frames), int(node_step)
        if not 2 <= history_frames <= 4096 or not 1 <= node_step < history_frames:
            raise ValueError('trail history needs 2..4096 frames and a smaller positive node_step')
        if blend not in ('alpha', 'add') or layer not in ('back', 'main', 'front'):
            raise ValueError('trail blend must be alpha/add and layer back/main/front')
        if width is not None:
            width = float(width)
            if not math.isfinite(width) or width <= 0:
                raise ValueError('trail width must be positive and finite')
        if sprite_id not in self.sprite_registry:
            raise ValueError(f'unknown trail sprite: {sprite_id}')
        sprite = self.sprite_registry.get_index(sprite_id)
        info = self.sprite_registry.get_info(sprite)
        if info is None or not info.texture_path:
            raise ValueError(f'trail sprite has no texture: {sprite_id}')
        handle = TrailHandle(self, owner, sprite, history_frames, node_step, width,
                             blend, layer, bool(hide_owner), bool(follow_owner_color))
        self._items.append(handle)
        required = sum(item._maximum_vertices for item in self._items)
        if required > len(self._keys):
            size = max(required, len(self._keys) * 2)
            self._vertices = np.empty((size, 8), np.float32)
            self._keys = np.empty(size, np.int32)
        return handle

    def _remove(self, handle):
        handle._cancelled = True
        handle.owner = None
        if handle in self._items:
            self._items.remove(handle)

    def remove_owner(self, owner):
        for i in range(len(self._items) - 1, -1, -1):
            if self._items[i].owner is owner:
                self._remove(self._items[i])

    def hides_owner(self, owner):
        return any(item.owner is owner and item.hide_owner and not item.done
                   for item in self._items)

    def clear(self):
        for item in self._items:
            item._cancelled = True
            item.owner = None
        self._items.clear()
        self._last_frame = None

    def update(self, frame, rate=1.0):
        if self._last_frame == frame:
            return
        self._last_frame = frame
        rate = float(rate)
        if not math.isfinite(rate) or rate < 0:
            raise ValueError('trail simulation rate must be finite and nonnegative')
        i = 0
        while i < len(self._items):
            item = self._items[i]
            if item.done:
                self._remove(item)
                continue
            x, y = float(item.owner.x), float(item.owner.y)
            if rate:
                item._head, item._count = _sample(
                    item._history, item._head, item._count, *item._observed,
                    x, y, item._remainder, rate)
                total = item._remainder + rate
                item._remainder = max(0.0, total - math.floor(total + 1e-8))
            item._observed = x, y
            i += 1

    def prepare_render_data(self, layer='main'):
        end = 0
        for item in self._items:
            if (item.done or item.layer != layer
                    or not getattr(item.owner, 'visible', True)):
                continue
            visual = item.owner.visual
            width = item.width if item.width is not None else item._height * visual.scale[1]
            item._color[:] = visual.color if item.follow_owner_color else (1.0, 1.0, 1.0, 1.0)
            end = _pack_trail(item._history, item._head, item._count,
                              item.node_step, width * 0.5, item._uv, item._color,
                              item._key, self._vertices, self._keys, end)
        return self._vertices[:end], self._keys[:end]

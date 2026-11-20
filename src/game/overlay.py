"""Sparse, stage-owned text overlays with no renderer or font dependency.

Coordinates are top-left-origin pixels: ``playfield`` uses game pixels and
``hud`` uses full-window pixels. Durations are simulation frames, advanced by
the caller's effects-domain rate rather than a separate UI clock.
"""

import math
import operator


_UNCHANGED = object()


def _number(value, name, minimum=None):
    value = float(value)
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError(f'{name} must be finite' + (
            f' and at least {minimum}' if minimum is not None else ''))
    return value


def _color(value):
    value = tuple(operator.index(channel) for channel in value)
    if len(value) != 3 or any(not 0 <= channel <= 255 for channel in value):
        raise ValueError('overlay color must be three RGB integers in 0..255')
    return value


def _duration(value):
    if value is None:
        return None
    value = operator.index(value)
    if value <= 0:
        raise ValueError('overlay duration_frames must be positive or None')
    return value


class TextOverlay:
    """A text label. Updates preserve its age; cancellation removes it at once.

    ``hide(fade_out_frames=30)`` fades from the current opacity over 30 effects
    frames. ``cancel()``/``hide()`` are immediate and idempotent.
    """

    __slots__ = ('_collection', 'text', 'x', 'y', 'size', 'color', 'alpha',
                 'align', 'layer', 'key', 'duration_frames', 'fade_in_frames',
                 'fade_out_frames', 'stroke_width', 'stroke_color', 'line_spacing',
                 'age', '_born_frame', '_cancelled', '_hide_age', '_hide_frames',
                 '_hide_alpha')

    def __init__(self, collection, *, frame, key, **values):
        self._collection = collection
        self.key = key
        self.age = 0.0
        self._born_frame = frame
        self._cancelled = False
        self._hide_age = None
        self._hide_frames = 0.0
        self._hide_alpha = 1.0
        self.update(**values)

    @property
    def done(self):
        return (self._cancelled or
                (self.duration_frames is not None and self.age >= self.duration_frames) or
                (self._hide_age is not None and
                 self.age - self._hide_age >= self._hide_frames))

    @property
    def cancelled(self):
        return self._cancelled

    @property
    def opacity(self):
        if self.done:
            return 0.0
        if self._hide_age is not None:
            return self._hide_alpha * max(
                0.0, 1.0 - (self.age - self._hide_age) / self._hide_frames)
        envelope = 1.0
        if self.fade_in_frames:
            envelope = min(envelope, self.age / self.fade_in_frames)
        if self.duration_frames is not None and self.fade_out_frames:
            envelope = min(envelope,
                           (self.duration_frames - self.age) / self.fade_out_frames)
        return self.alpha * max(0.0, envelope)

    def update(self, *, text=_UNCHANGED, x=_UNCHANGED, y=_UNCHANGED,
               size=_UNCHANGED, color=_UNCHANGED, alpha=_UNCHANGED,
               align=_UNCHANGED, layer=_UNCHANGED, duration_frames=_UNCHANGED,
               fade_in_frames=_UNCHANGED, fade_out_frames=_UNCHANGED,
               stroke_width=_UNCHANGED, stroke_color=_UNCHANGED,
               line_spacing=_UNCHANGED):
        """Change presentation without resetting duration or reviving a handle."""
        if hasattr(self, 'duration_frames') and self.done:
            raise RuntimeError('cannot update a finished overlay; create a new label')
        changes = {}
        if text is not _UNCHANGED:
            if not isinstance(text, str):
                raise TypeError('overlay text must be a string')
            changes['text'] = text
        for name, value in (('x', x), ('y', y)):
            if value is not _UNCHANGED:
                changes[name] = _number(value, name)
        for name, value in (('size', size), ('stroke_width', stroke_width)):
            if value is not _UNCHANGED:
                value = operator.index(value)
                minimum = 1 if name == 'size' else 0
                if value < minimum:
                    raise ValueError(f'{name} must be at least {minimum}')
                changes[name] = value
        for name, value in (('color', color), ('stroke_color', stroke_color)):
            if value is not _UNCHANGED:
                changes[name] = _color(value)
        if alpha is not _UNCHANGED:
            alpha = _number(alpha, 'alpha', 0)
            if alpha > 1:
                raise ValueError('overlay alpha must be in 0..1')
            changes['alpha'] = alpha
        if align is not _UNCHANGED:
            if align not in ('left', 'center', 'right'):
                raise ValueError('overlay align must be left, center or right')
            changes['align'] = align
        if layer is not _UNCHANGED:
            if layer not in ('playfield', 'hud'):
                raise ValueError('overlay layer must be playfield or hud')
            changes['layer'] = layer
        if duration_frames is not _UNCHANGED:
            changes['duration_frames'] = _duration(duration_frames)
        for name, value in (('fade_in_frames', fade_in_frames),
                            ('fade_out_frames', fade_out_frames),
                            ('line_spacing', line_spacing)):
            if value is not _UNCHANGED:
                changes[name] = _number(value, name, 0)
        for name, value in changes.items():
            setattr(self, name, value)
        return self

    def cancel(self):
        self._cancelled = True

    def hide(self, fade_out_frames=0):
        frames = _number(fade_out_frames, 'fade_out_frames', 0)
        if not frames:
            self.cancel()
        elif not self.done:
            self._hide_alpha = self.opacity
            self._hide_age = self.age
            self._hide_frames = frames
        return self


class OverlayGroup:
    """A title/subtitle pair that can be hidden or cancelled as one item."""

    def __init__(self, *handles):
        self.handles = tuple(handles)

    @property
    def done(self):
        return all(handle.done for handle in self.handles)

    def cancel(self):
        for handle in self.handles:
            handle.cancel()

    def hide(self, fade_out_frames=0):
        for handle in self.handles:
            handle.hide(fade_out_frames)
        return self


class StageOverlay:
    """Bounded text labels, painted in creation order; a key replaces a label.

    Creation and update accept the same optional control-frame token as screen
    effects, so duplicate updates and a newly-created item's first frame do not
    accidentally advance its age. No per-character Tasks or callbacks exist.
    """

    def __init__(self, capacity=64):
        self.capacity = operator.index(capacity)
        if self.capacity <= 0:
            raise ValueError('overlay capacity must be positive')
        self._items = []
        self._last_frame = None

    @property
    def items(self):
        return tuple(item for item in self._items if not item.done)

    @property
    def count(self):
        return sum(not item.done for item in self._items)

    def show_text(self, text, x=192, y=160, *, duration_frames=180,
                  fade_in_frames=0, fade_out_frames=0, color=(255, 255, 255),
                  size=24, alpha=1.0, align='center', layer='playfield',
                  stroke_width=1, stroke_color=(0, 0, 0), line_spacing=1.2,
                  key=None, frame=None):
        frame = self._last_frame if frame is None else operator.index(frame)
        if key is not None:
            hash(key)
        item = TextOverlay(
            self, frame=frame, key=key, text=text, x=x, y=y, size=size,
            color=color, alpha=alpha, align=align, layer=layer,
            duration_frames=duration_frames, fade_in_frames=fade_in_frames,
            fade_out_frames=fade_out_frames, stroke_width=stroke_width,
            stroke_color=stroke_color, line_spacing=line_spacing,
        )
        live = [old for old in self._items if not old.done and
                not (key is not None and old.key == key)]
        if len(live) >= self.capacity:
            raise RuntimeError(f'stage overlay capacity exceeded ({self.capacity})')
        for old in self._items:
            if key is not None and old.key == key:
                old.cancel()
        self._items = live
        self._items.append(item)
        return item

    def show_title(self, title, subtitle='', *, x=192, y=130, size=30,
                   subtitle_size=16, gap=10, duration_frames=240,
                   fade_in_frames=30, fade_out_frames=45,
                   color=(255, 255, 255), subtitle_color=(225, 225, 235),
                   layer='playfield', key='stage.title', frame=None):
        """Create a title and optional subtitle; returned group owns both."""
        # Validate/reserve both entries before changing an existing title.
        frame = self._last_frame if frame is None else operator.index(frame)
        keys = (None, None) if key is None else ((key, 'title'), (key, 'subtitle'))
        common = dict(x=x, duration_frames=duration_frames,
                      fade_in_frames=fade_in_frames, fade_out_frames=fade_out_frames,
                      align='center', layer=layer, frame=frame)
        title_item = TextOverlay(
            self, key=keys[0], text=title, y=y, size=size, color=color,
            alpha=1, stroke_width=1, stroke_color=(0, 0, 0), line_spacing=1.2,
            **common,
        )
        subtitle_item = None
        if subtitle:
            subtitle_item = TextOverlay(
                self, key=keys[1], text=subtitle,
                y=float(y) + size * 1.2 + float(gap), size=subtitle_size,
                color=subtitle_color, alpha=1, stroke_width=1,
                stroke_color=(0, 0, 0), line_spacing=1.2, **common,
            )
        if key is not None:
            hash(key)
        live = [item for item in self._items if not item.done and
                not (key is not None and item.key in keys)]
        handles = (title_item,) if subtitle_item is None else (title_item, subtitle_item)
        if len(live) + len(handles) > self.capacity:
            raise RuntimeError(f'stage overlay capacity exceeded ({self.capacity})')
        for item in self._items:
            if key is not None and item.key in keys:
                item.cancel()
        self._items = live + list(handles)
        return OverlayGroup(*handles)

    def update(self, frames=1.0, *, frame=None):
        """Advance by nonnegative, already effects-scaled elapsed frames."""
        frames = _number(frames, 'overlay elapsed frames', 0)
        if frame is not None:
            frame = operator.index(frame)
            if frame == self._last_frame:
                return
            if self._last_frame is not None and frame < self._last_frame:
                raise ValueError('overlay control frame must not rewind')
            self._last_frame = frame
        for item in self._items:
            if not item.done and (frame is None or item._born_frame != frame):
                item.age += frames
        self._items[:] = [item for item in self._items if not item.done]

    def clear(self):
        for item in self._items:
            item.cancel()
        self._items.clear()
        self._last_frame = None


__all__ = ['StageOverlay', 'TextOverlay', 'OverlayGroup']

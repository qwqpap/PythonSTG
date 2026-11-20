"""Small stage-owned screen pulses, independent of Tasks and the renderer.

Durations and ages are simulation frames. The existing effects time domain
supplies each update's rate; this collection does not sample or own a clock.
"""

import math
import operator


def _color(value):
    color = tuple(float(channel) for channel in value)
    if len(color) != 4 or any(not math.isfinite(channel) or not 0.0 <= channel <= 1.0
                              for channel in color):
        raise ValueError('screen pulse color must be four RGBA values in 0..1')
    return color


def _duration(frames):
    frames = operator.index(frames)
    if frames <= 0:
        raise ValueError('screen pulse duration must be positive frames')
    return frames


class ScreenPulse:
    """One cancellable pulse; restarting it retains this handle's identity."""

    __slots__ = ('_collection', '_color', '_peak_alpha', 'frames', 'age',
                 '_born_frame', '_cancelled')

    def __init__(self, collection, color, frames, frame):
        self._collection = collection
        self._reset(color, frames, frame)

    def _reset(self, color, frames, frame):
        self._color = color
        self._peak_alpha = int(round(color[3] * 255.0))
        self.frames = frames
        self.age = 0.0
        self._born_frame = frame
        self._cancelled = False

    @property
    def done(self):
        return self._cancelled or self.age + 1e-8 >= self.frames

    @property
    def cancelled(self):
        return self._cancelled

    @property
    def color(self):
        """Current RGBA, with the original pulse's integer-alpha rounding."""
        alpha = (0 if self.done else
                 self._peak_alpha - int(self._peak_alpha * self.age / self.frames))
        return (*self._color[:3], alpha / 255.0)

    def cancel(self):
        self._cancelled = True

    def restart(self, *, color=None, frames=None, frame=None):
        """Restart at age zero, including after natural end or cancellation."""
        self._collection._restart(
            self, self._color if color is None else _color(color),
            self.frames if frames is None else _duration(frames), frame,
        )
        return self


class ScreenEffects:
    """Bounded pulses in creation order, composited over the playfield only.

Pass the same control frame to pulse/restart and update so newly born effects
are drawn at age zero and duplicate updates cannot consume their duration.
Without a frame argument, render the initial state before the first update.
"""

    def __init__(self, capacity=32):
        self.capacity = _duration(capacity)
        self._pulses = []
        self._shakes = []
        self._last_frame = None

    @property
    def count(self):
        return sum(not pulse.done for pulse in (*self._pulses, *self._shakes))

    @property
    def offset(self):
        offsets = [shake.offset for shake in self._shakes if not shake.done]
        return tuple(sum(value[axis] for value in offsets) for axis in range(2))

    def shake(self, frames=80, amplitude=8.0, *, seed=0, frame=None):
        self._reserve()
        amplitude = float(amplitude)
        if not math.isfinite(amplitude) or amplitude < 0:
            raise ValueError('shake amplitude must be finite and nonnegative')
        shake = ScreenShake(_duration(frames), amplitude, int(seed),
                            self._last_frame if frame is None else int(frame))
        self._shakes.append(shake)
        return shake

    @property
    def colors(self):
        return tuple(pulse.color for pulse in self._pulses if not pulse.done)

    def _reserve(self):
        self._pulses[:] = [pulse for pulse in self._pulses if not pulse.done]
        self._shakes[:] = [shake for shake in self._shakes if not shake.done]
        if len(self._pulses) + len(self._shakes) >= self.capacity:
            raise RuntimeError(f'screen pulse capacity exceeded ({self.capacity})')

    def pulse(self, color, frames, *, frame=None):
        color, frames = _color(color), _duration(frames)
        frame = self._last_frame if frame is None else operator.index(frame)
        self._reserve()
        pulse = ScreenPulse(self, color, frames, frame)
        self._pulses.append(pulse)
        return pulse

    def _restart(self, pulse, color, frames, frame):
        frame = self._last_frame if frame is None else operator.index(frame)
        if pulse.done or pulse not in self._pulses:
            self._reserve()
            self._pulses.append(pulse)
        pulse._reset(color, frames, frame)

    def update(self, rate=1.0, *, frame=None):
        rate = float(rate)
        if not math.isfinite(rate) or not 0.0 <= rate <= 1.0:
            raise ValueError('screen effect simulation rate must be in 0..1')
        if frame is not None:
            frame = operator.index(frame)
            if frame == self._last_frame:
                return
            if self._last_frame is not None and frame < self._last_frame:
                raise ValueError('screen effect control frame must not rewind')
            self._last_frame = frame
        for pulse in self._pulses:
            if not pulse.done and (frame is None or pulse._born_frame != frame):
                pulse.age = min(float(pulse.frames), pulse.age + rate)
        self._pulses[:] = [pulse for pulse in self._pulses if not pulse.done]

        for shake in self._shakes:
            if not shake.done and (frame is None or shake._born_frame != frame):
                shake.age = min(float(shake.frames), shake.age + rate)
        self._shakes[:] = [shake for shake in self._shakes if not shake.done]

    def clear(self):
        for pulse in self._pulses:
            pulse.cancel()
        self._pulses.clear()
        for shake in self._shakes:
            shake.cancel()
        self._shakes.clear()
        self._last_frame = None


class ScreenShake:
    """Discrete decaying displacement; does not consume gameplay RNG."""

    def __init__(self, frames, amplitude, seed, frame):
        self.frames, self.amplitude, self.seed = frames, amplitude, seed
        self._born_frame, self.age, self._cancelled = frame, 0.0, False

    @property
    def done(self):
        return self._cancelled or self.age + 1e-8 >= self.frames

    @property
    def offset(self):
        if self.done:
            return (0.0, 0.0)
        value = (self.seed ^ (int(self.age) * 0x9e3779b9)) & 0xffffffff
        value = (value * 1664525 + 1013904223) & 0xffffffff
        x = (0, 1, -1)[value % 3]
        value = (value * 1664525 + 1013904223) & 0xffffffff
        y = (0, 1, -1)[value % 3]
        envelope = 1 - self.age / self.frames
        return x * self.amplitude * envelope, y * self.amplitude * envelope

    def cancel(self):
        self._cancelled = True


__all__ = ['ScreenEffects', 'ScreenPulse', 'ScreenShake']

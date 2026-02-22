"""
Audio backend - miniaudio implementation

Provides SE playback, BGM streaming, volume control, fadeout.
Replaces pygame.mixer.
"""

import os
import array
import threading
from typing import Optional

try:
    import miniaudio
    HAS_MINIAUDIO = True
except ImportError:
    HAS_MINIAUDIO = False


class Sound:
    """Decoded sound effect stored in memory."""

    def __init__(self, samples: bytes, nchannels: int, sample_rate: int):
        self._samples = array.array('h')
        self._samples.frombytes(samples)
        self.nchannels = nchannels
        self.sample_rate = sample_rate
        self._volume = 1.0

    def set_volume(self, vol: float):
        self._volume = max(0.0, min(1.0, vol))

    def get_volume(self) -> float:
        return self._volume

    def play(self, loops: int = 0):
        backend = get_audio_backend()
        if backend:
            backend.play_sound(self, loops)

    def stop(self):
        backend = get_audio_backend()
        if backend:
            backend.stop_sound(self)


class _PlayingSound:
    """Runtime state for a currently-playing sound instance."""

    __slots__ = ('sound', 'position', 'loops', 'volume', 'active')

    def __init__(self, sound: Sound, loops: int = 0):
        self.sound = sound
        self.position = 0
        self.loops = loops
        self.volume = sound._volume
        self.active = True


class AudioBackend:
    """Miniaudio-based audio backend with software mixer."""

    def __init__(self, sample_rate: int = 44100, nchannels: int = 2):
        self._sample_rate = sample_rate
        self._nchannels = nchannels
        self._initialized = False

        self._playing: list = []
        self._lock = threading.Lock()

        self._bgm_generator = None
        self._bgm_playing = False
        self._bgm_volume = 1.0
        self._bgm_fade_total = 0
        self._bgm_fade_pos = 0

        self._device = None

        if not HAS_MINIAUDIO:
            print("[AudioBackend] miniaudio not available")
            return

        try:
            self._device = miniaudio.PlaybackDevice(
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=nchannels,
                sample_rate=sample_rate,
            )
            self._device.start(self._mix_generator())
            self._initialized = True
        except Exception as e:
            print(f"[AudioBackend] Init failed: {e}")

    def is_initialized(self) -> bool:
        return self._initialized

    # ---------- Mixer generator ----------

    def _mix_generator(self):
        required_frames = yield b""
        while True:
            n_samples = required_frames * self._nchannels
            mixed = array.array('h', bytes(n_samples * 2))

            with self._lock:
                self._mix_se(mixed, required_frames)
                self._mix_bgm(mixed, required_frames)

            required_frames = yield mixed.tobytes()

    def _mix_se(self, mixed: array.array, num_frames: int):
        alive = []
        for ps in self._playing:
            if not ps.active:
                continue
            s = ps.sound._samples
            total = len(s)
            needed = num_frames * ps.sound.nchannels
            pos = ps.position
            vol = ps.volume

            wrote = 0
            while wrote < needed and ps.active:
                avail = total - pos
                if avail <= 0:
                    if ps.loops == 0:
                        ps.active = False
                        break
                    if ps.loops > 0:
                        ps.loops -= 1
                    pos = 0
                    avail = total

                chunk = min(needed - wrote, avail)
                for i in range(chunk):
                    idx = wrote + i
                    if idx < len(mixed):
                        v = mixed[idx] + int(s[pos + i] * vol)
                        mixed[idx] = max(-32768, min(32767, v))
                pos += chunk
                wrote += chunk

            ps.position = pos
            if ps.active:
                alive.append(ps)
        self._playing = alive

    def _mix_bgm(self, mixed: array.array, num_frames: int):
        if not self._bgm_playing or self._bgm_generator is None:
            return

        try:
            bgm_chunk = next(self._bgm_generator)
            if not bgm_chunk:
                return
            bgm = array.array('h')
            if isinstance(bgm_chunk, bytes):
                bgm.frombytes(bgm_chunk)
            else:
                bgm.frombytes(bytes(bgm_chunk))

            vol = self._bgm_volume

            if self._bgm_fade_total > 0:
                fade_left = self._bgm_fade_total - self._bgm_fade_pos
                if fade_left <= 0:
                    self._bgm_playing = False
                    self._bgm_generator = None
                    self._bgm_fade_total = 0
                    return
                self._bgm_fade_pos += len(bgm)
                vol *= max(0.0, fade_left / self._bgm_fade_total)

            for i in range(min(len(mixed), len(bgm))):
                v = mixed[i] + int(bgm[i] * vol)
                mixed[i] = max(-32768, min(32767, v))
        except StopIteration:
            self._bgm_playing = False
            self._bgm_generator = None

    # ---------- SE methods ----------

    def load_sound(self, path: str) -> Optional[Sound]:
        if not self._initialized or not os.path.exists(path):
            return None
        try:
            decoded = miniaudio.decode_file(
                path,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=self._nchannels,
                sample_rate=self._sample_rate,
            )
            return Sound(decoded.samples, decoded.nchannels, decoded.sample_rate)
        except Exception as e:
            print(f"[AudioBackend] Load failed {path}: {e}")
            return None

    def play_sound(self, sound: Sound, loops: int = 0) -> bool:
        if not self._initialized or sound is None:
            return False
        ps = _PlayingSound(sound, loops)
        with self._lock:
            self._playing.append(ps)
        return True

    def stop_sound(self, sound: Sound):
        with self._lock:
            for ps in self._playing:
                if ps.sound is sound:
                    ps.active = False

    def stop_all_sounds(self):
        with self._lock:
            for ps in self._playing:
                ps.active = False
            self._playing.clear()

    # ---------- BGM methods ----------

    def load_and_play_bgm(self, path: str, loops: int = -1,
                          start: float = 0.0, fade_ms: int = 0) -> bool:
        if not self._initialized or not os.path.exists(path):
            return False
        try:
            gen = miniaudio.stream_file(
                path,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=self._nchannels,
                sample_rate=self._sample_rate,
            )
            with self._lock:
                self._bgm_generator = gen
                self._bgm_playing = True
                self._bgm_fade_total = 0
                self._bgm_fade_pos = 0
            return True
        except Exception as e:
            print(f"[AudioBackend] BGM failed {path}: {e}")
            return False

    def pause_bgm(self):
        with self._lock:
            self._bgm_playing = False

    def unpause_bgm(self):
        with self._lock:
            if self._bgm_generator is not None:
                self._bgm_playing = True

    def stop_bgm(self, fade_ms: int = 0):
        with self._lock:
            if fade_ms > 0 and self._bgm_playing:
                self._bgm_fade_total = int(
                    self._sample_rate * fade_ms / 1000
                ) * self._nchannels
                self._bgm_fade_pos = 0
            else:
                self._bgm_playing = False
                self._bgm_generator = None
                self._bgm_fade_total = 0

    def set_bgm_volume(self, volume: float):
        self._bgm_volume = max(0.0, min(1.0, volume))

    def is_bgm_playing(self) -> bool:
        return self._bgm_playing

    # ---------- Lifecycle ----------

    def cleanup(self):
        with self._lock:
            self._bgm_playing = False
            self._bgm_generator = None
            self._playing.clear()
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
        self._initialized = False


# ---------- Global instance ----------

_backend: Optional[AudioBackend] = None


def get_audio_backend() -> Optional[AudioBackend]:
    return _backend


def init_audio_backend(**kwargs) -> AudioBackend:
    global _backend
    if _backend is not None:
        _backend.cleanup()
    _backend = AudioBackend(**kwargs)
    return _backend

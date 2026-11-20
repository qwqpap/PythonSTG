"""
Audio backend - miniaudio implementation

Provides SE playback, BGM streaming, volume control, fadeout.
Replaces pygame.mixer.
"""

import os
import array
import threading
import numpy as np
from typing import Optional

try:
    import miniaudio
    HAS_MINIAUDIO = True
except ImportError:
    HAS_MINIAUDIO = False


class Sound:
    """Decoded sound effect stored in memory."""

    def __init__(self, samples, nchannels: int, sample_rate: int):
        if isinstance(samples, array.array):
            self._samples = samples
        else:
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
        self._max_playing_sounds = 8
        self._max_instances_per_sound = 1

        self._playing: list = []
        self._lock = threading.Lock()

        self._bgm_stream = None
        self._bgm_playing = False
        self._bgm_volume = 1.0
        self._bgm_fade_total = 0
        self._bgm_fade_pos = 0
        self._bgm_fade_in_total = 0
        self._bgm_fade_in_pos = 0
        self.last_bgm_error = None

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
            gen = self._mix_generator()
            next(gen)
            self._device.start(gen)
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
            mixed = np.zeros(n_samples, np.float32)

            with self._lock:
                self._mix_se(mixed, required_frames)
                self._mix_bgm(mixed, required_frames)

            np.clip(mixed, -32768, 32767, out=mixed)
            required_frames = yield mixed.astype(np.int16).tobytes()

    def _mix_se(self, mixed, num_frames: int):
        alive = []
        for ps in self._playing:
            if not ps.active:
                continue
            s = np.frombuffer(ps.sound._samples, np.int16)
            total = len(s)
            needed = num_frames * ps.sound.nchannels
            pos = ps.position
            vol = ps.volume

            wrote = 0
            if total == 0:
                ps.active = False
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
                take = min(chunk, len(mixed)-wrote)
                if take > 0:
                    mixed[wrote:wrote+take] += s[pos:pos+take] * vol
                pos += chunk
                wrote += chunk

            ps.position = pos
            if ps.active:
                alive.append(ps)
        self._playing = alive

    def _mix_bgm(self, mixed, num_frames: int):
        if not self._bgm_playing or self._bgm_stream is None:
            return

        try:
            bgm = self._bgm_stream.read(num_frames)
            count = min(len(mixed), len(bgm)) // self._nchannels
            if count:
                samples = bgm[:count*self._nchannels].reshape(count, self._nchannels)
                if self._bgm_fade_total or self._bgm_fade_in_total:
                    offsets = np.arange(count, dtype=np.float32)
                    gains = np.full(count, self._bgm_volume, np.float32)
                    if self._bgm_fade_in_total:
                        gains *= np.minimum(1.0, (self._bgm_fade_in_pos+offsets) / self._bgm_fade_in_total)
                        self._bgm_fade_in_pos += count
                        if self._bgm_fade_in_pos >= self._bgm_fade_in_total:
                            self._bgm_fade_in_total = 0
                    if self._bgm_fade_total:
                        gains *= np.maximum(0.0, 1.0-(self._bgm_fade_pos+offsets) / self._bgm_fade_total)
                        self._bgm_fade_pos += count
                    mixed[:count*self._nchannels] += (samples * gains[:, None]).reshape(-1)
                else:
                    mixed[:count*self._nchannels] += bgm[:count*self._nchannels] * self._bgm_volume
            if (self._bgm_stream.finished or (self._bgm_fade_total > 0
                    and self._bgm_fade_pos >= self._bgm_fade_total)):
                self._close_bgm()
        except Exception as error:
            self.last_bgm_error = str(error)
            print(f'[AudioBackend] BGM stream failed: {error}')
            self._close_bgm()

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
            active_count = 0
            same_sound_count = 0
            for playing in self._playing:
                if not playing.active:
                    continue
                active_count += 1
                if playing.sound is sound:
                    same_sound_count += 1

            if active_count >= self._max_playing_sounds:
                return False
            if same_sound_count >= self._max_instances_per_sound:
                return False

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
                          start: float = 0.0, fade_ms: int = 0, *,
                          loop_start_frame=None, loop_end_frame=None) -> bool:
        if not self._initialized or not os.path.exists(path):
            return False
        try:
            from .bgm_stream import BgmStream
            stream = BgmStream(path, sample_rate=self._sample_rate, nchannels=self._nchannels,
                               loops=loops, start=start, loop_start_frame=loop_start_frame,
                               loop_end_frame=loop_end_frame)
            with self._lock:
                self._close_bgm()
                self._bgm_stream = stream
                self._bgm_playing = True
                self._bgm_fade_total = 0
                self._bgm_fade_pos = 0
                self._bgm_fade_in_total = max(0, round(self._sample_rate * fade_ms / 1000))
                self._bgm_fade_in_pos = 0
                self.last_bgm_error = None
            return True
        except Exception as e:
            self.last_bgm_error = str(e)
            print(f"[AudioBackend] BGM failed {path}: {e}")
            return False

    def pause_bgm(self):
        with self._lock:
            self._bgm_playing = False

    def unpause_bgm(self):
        with self._lock:
            if self._bgm_stream is not None:
                self._bgm_playing = True

    def stop_bgm(self, fade_ms: int = 0):
        with self._lock:
            if fade_ms > 0 and self._bgm_playing:
                self._bgm_fade_total = int(
                    self._sample_rate * fade_ms / 1000
                )
                self._bgm_fade_pos = 0
            else:
                self._close_bgm()

    def _close_bgm(self):
        if self._bgm_stream is not None:
            self._bgm_stream.close()
            self._bgm_stream = None
        self._bgm_playing = False
        self._bgm_fade_total = self._bgm_fade_in_total = 0

    def seek_bgm(self, seconds):
        with self._lock:
            if self._bgm_stream is None:
                return False
            self._bgm_stream.seek(seconds)
            self._bgm_fade_total = 0
            return True

    def get_bgm_position(self):
        with self._lock:
            return self._bgm_stream.position if self._bgm_stream is not None else None

    def set_bgm_volume(self, volume: float):
        self._bgm_volume = max(0.0, min(1.0, volume))

    def is_bgm_playing(self) -> bool:
        return self._bgm_playing

    # ---------- Lifecycle ----------

    def cleanup(self):
        with self._lock:
            self._close_bgm()
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

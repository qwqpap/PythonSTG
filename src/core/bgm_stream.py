"""Bounded-memory PCM streaming with an intro and sample-defined loop region.

Public loop points are SOURCE PCM frames (one sample per channel), not bytes,
interleaved sample indices or seconds. Decoder seek/read uses OUTPUT frames;
resampling converts points once, to the nearest output frame. End is exclusive.
"""

import math
import operator
import numpy as np
import miniaudio


class BgmStream:
    def __init__(self, path, *, sample_rate=44100, nchannels=2, loops=-1,
                 start=0.0, loop_start_frame=None, loop_end_frame=None):
        info = miniaudio.get_file_info(path)
        self.path = path
        self.sample_rate, self.nchannels = sample_rate, nchannels
        self.source_sample_rate = info.sample_rate
        self.total_frames = round(info.num_frames * sample_rate / info.sample_rate)
        self._initial_loops = operator.index(loops)
        if self._initial_loops < -1:
            raise ValueError('loops must be -1 or a non-negative repeat count')
        source_start = 0 if loop_start_frame is None else operator.index(loop_start_frame)
        source_end = info.num_frames if loop_end_frame is None else operator.index(loop_end_frame)
        if not 0 <= source_start < source_end <= info.num_frames:
            raise ValueError('BGM loop points must satisfy 0 <= start < end <= source frames')
        self.loop_start = round(source_start * sample_rate / info.sample_rate)
        self.loop_end = round(source_end * sample_rate / info.sample_rate)
        self._explicit_end = loop_end_frame is not None
        if self.loop_end <= self.loop_start:
            raise ValueError('BGM loop is shorter than one output frame')
        self._decoder = None
        self.finished = False
        self.cursor = 0
        self.remaining_loops = self._initial_loops
        self.seek(start)

    def _open(self, frame):
        # stream_file already primes its decoder. Calling next() again loses
        # the first chunk. send(n) returns the first n frames at this position.
        decoder = miniaudio.stream_file(
            self.path, output_format=miniaudio.SampleFormat.SIGNED16,
            sample_rate=self.sample_rate, nchannels=self.nchannels, seek_frame=frame)
        old, self._decoder = self._decoder, decoder
        if old is not None:
            old.close()

    def seek(self, seconds):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('BGM seek position must be non-negative seconds')
        frame = round(seconds * self.sample_rate)
        if frame > self.loop_end:
            raise ValueError('BGM position is outside its playback region')
        self._open(frame)
        self.cursor = frame
        self.remaining_loops = self._initial_loops
        self.finished = False

    @property
    def position(self):
        return self.cursor / self.sample_rate

    def read(self, frames):
        """Return actual int16 interleaved samples, stitching within a callback.

        Storage is bounded by the requested device chunk plus decoder buffers;
        never decode or cache an entire music file. Finite playback returns a
        short final chunk, which the mixer pads with silence.
        """
        output = np.empty(frames * self.nchannels, np.int16)
        written = 0
        while written < frames and not self.finished:
            if self.cursor >= self.loop_end:
                if self.remaining_loops == 0:
                    self.finished = True
                    break
                if self.remaining_loops > 0:
                    self.remaining_loops -= 1
                self.cursor = self.loop_start
                self._open(self.cursor)
            wanted = min(frames - written, self.loop_end - self.cursor, 16384)
            try:
                samples = self._decoder.send(wanted)
            except StopIteration:
                samples = b''
            pcm = np.frombuffer(samples, dtype=np.int16)
            got = len(pcm) // self.nchannels
            output[written*self.nchannels:(written+got)*self.nchannels] = pcm
            written += got
            self.cursor += got
            if got < wanted:
                if self._explicit_end:
                    raise RuntimeError('BGM decoder ended before the requested loop endpoint')
                if got == 0 and self.cursor <= self.loop_start:
                    raise RuntimeError('BGM loop contains no decodable frames')
                # File metadata can overestimate compressed audio duration.
                # Implicit EOF is the actual decoded end, not metadata padding.
                self.loop_end = self.cursor
        if self.cursor >= self.loop_end and self.remaining_loops == 0:
            self.finished = True
        return output[:written*self.nchannels]

    def close(self):
        if self._decoder is not None:
            self._decoder.close()
            self._decoder = None
        self.finished = True

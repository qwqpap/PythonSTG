"""Formal authoring/runtime coordinate and timeline conversion contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CoordinateSpace:
    """Map top-left authoring pixels to center-origin runtime coordinates.

    Authoring coordinates use a fixed logical canvas independent of window or
    framebuffer scale. Runtime X/Y both use ``[-1, 1]`` and positive Y points up.
    """

    logical_width: float = 384.0
    logical_height: float = 448.0

    def __post_init__(self) -> None:
        if self.logical_width <= 0 or self.logical_height <= 0:
            raise ValueError("logical canvas dimensions must be positive")

    def authoring_to_runtime(self, x: float, y: float) -> tuple[float, float]:
        return (
            (float(x) / self.logical_width) * 2.0 - 1.0,
            1.0 - (float(y) / self.logical_height) * 2.0,
        )

    def runtime_to_authoring(self, x: float, y: float) -> tuple[float, float]:
        return (
            (float(x) + 1.0) * 0.5 * self.logical_width,
            (1.0 - float(y)) * 0.5 * self.logical_height,
        )

    def viewport_to_authoring(
        self,
        x: float,
        y: float,
        *,
        viewport_width: float,
        viewport_height: float,
    ) -> tuple[float, float]:
        if viewport_width <= 0 or viewport_height <= 0:
            raise ValueError("viewport dimensions must be positive")
        return (
            float(x) * self.logical_width / float(viewport_width),
            float(y) * self.logical_height / float(viewport_height),
        )

    def viewport_to_runtime(
        self,
        x: float,
        y: float,
        *,
        viewport_width: float,
        viewport_height: float,
    ) -> tuple[float, float]:
        authoring = self.viewport_to_authoring(
            x,
            y,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        return self.authoring_to_runtime(*authoring)


@dataclass(frozen=True)
class Timebase:
    """Integer-frame storage with display conversion to seconds and beats."""

    tick_rate: int = 60

    def __post_init__(self) -> None:
        if (
            isinstance(self.tick_rate, bool)
            or not isinstance(self.tick_rate, int)
            or self.tick_rate <= 0
        ):
            raise ValueError("tick_rate must be a positive integer")

    def frames_to_seconds(self, frames: int) -> float:
        self._validate_frames(frames)
        return frames / self.tick_rate

    def seconds_to_frames(self, seconds: float) -> int:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("seconds must be finite and non-negative")
        return int(math.floor(seconds * self.tick_rate + 0.5))

    def frames_to_beats(self, frames: int, bpm: float) -> float:
        self._validate_bpm(bpm)
        return self.frames_to_seconds(frames) * bpm / 60.0

    def beats_to_frames(self, beats: float, bpm: float) -> int:
        self._validate_bpm(bpm)
        if not math.isfinite(beats) or beats < 0:
            raise ValueError("beats must be finite and non-negative")
        return self.seconds_to_frames(beats * 60.0 / bpm)

    @staticmethod
    def _validate_frames(frames: int) -> None:
        if isinstance(frames, bool) or not isinstance(frames, int) or frames < 0:
            raise ValueError("frames must be a non-negative integer")

    @staticmethod
    def _validate_bpm(bpm: float) -> None:
        if not math.isfinite(bpm) or bpm <= 0:
            raise ValueError("bpm must be finite and positive")

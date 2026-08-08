"""Reusable Curve authoring resources and interpolation semantics.

M5 frozen contract:
- Resource type ``pystg.curve`` with the common envelope.
- ``CurveKeyframe(frame: int, value: float)`` with strictly increasing frames.
- ``evaluate(frame)`` returns ``default`` below the first keyframe and the
  last keyframe's value beyond the last keyframe.
- ``interpolation`` is one of ``step`` / ``linear`` / ``cubic``.
- ``cubic`` is uniform Catmull-Rom with the first/last keyframe repeated as
  the outer control point:

  ``y(t) = 0.5 * (2*P1 + (-P0+P2)*t + (2*P0-5*P1+4*P2-P3)*t^2
  + (-P0+3*P1-3*P2+P3)*t^3)`` with t in [0, 1].
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from src.authoring.resources import (
    CURVE_RESOURCE_TYPE,
    RESOURCE_SCHEMA_VERSION,
    ResourceDocumentError,
    ResourceHeader,
    new_resource_id,
)

CURVE_INTERPOLATIONS = ("step", "linear", "cubic")


class CurveDocumentError(ResourceDocumentError):
    """Raised when a CurveDocument violates the curve contract."""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


@dataclass(frozen=True)
class CurveKeyframe:
    frame: int
    value: float


@dataclass
class CurveDocument:
    """Versioned reusable curve resource."""

    header: ResourceHeader
    keyframes: tuple[CurveKeyframe, ...] = ()
    interpolation: str = "linear"
    default: float = 0.0

    @property
    def id(self) -> str:
        return self.header.id

    @property
    def name(self) -> str:
        return self.header.name

    @property
    def type(self) -> str:
        return self.header.type

    @property
    def schema_version(self) -> int:
        return self.header.schema_version

    def validate(self) -> None:
        try:
            self.header.validate(
                expected_type=CURVE_RESOURCE_TYPE,
                current_version=RESOURCE_SCHEMA_VERSION,
            )
        except ResourceDocumentError as exc:
            if isinstance(exc, CurveDocumentError):
                raise
            raise CurveDocumentError("header", str(exc)) from exc
        if self.interpolation not in CURVE_INTERPOLATIONS:
            raise CurveDocumentError(
                "interpolation",
                "must be one of: " + ", ".join(CURVE_INTERPOLATIONS),
            )
        if isinstance(self.default, bool) or not isinstance(self.default, (int, float)):
            raise CurveDocumentError("default", "must be a number")
        if not math.isfinite(float(self.default)):
            raise CurveDocumentError("default", "must be finite")
        previous = None
        for index, keyframe in enumerate(self.keyframes):
            path = f"keyframes[{index}]"
            if not isinstance(keyframe, CurveKeyframe):
                raise CurveDocumentError(path, "must be a CurveKeyframe")
            if isinstance(keyframe.frame, bool) or not isinstance(
                keyframe.frame, int
            ):
                raise CurveDocumentError(path, "frame must be an integer")
            if isinstance(keyframe.value, bool) or not isinstance(
                keyframe.value, (int, float)
            ):
                raise CurveDocumentError(path, "value must be a number")
            if not math.isfinite(float(keyframe.value)):
                raise CurveDocumentError(path, "value must be finite")
            if previous is not None and keyframe.frame <= previous:
                raise CurveDocumentError(
                    path, "keyframe frames must be strictly increasing"
                )
            previous = keyframe.frame

    def evaluate(self, frame: float) -> float:
        """Sample the curve at ``frame`` with clamp/default semantics."""
        if not self.keyframes:
            return float(self.default)
        if float(frame) < self.keyframes[0].frame:
            return float(self.default)
        if float(frame) >= self.keyframes[-1].frame:
            return float(self.keyframes[-1].value)
        if self.interpolation == "step":
            value = self.keyframes[0].value
            for keyframe in self.keyframes:
                if keyframe.frame <= float(frame):
                    value = keyframe.value
                else:
                    break
            return float(value)
        if self.interpolation == "linear":
            return self._linear_at(float(frame))
        if self.interpolation == "cubic":
            return self._cubic_at(float(frame))
        raise CurveDocumentError(
            "interpolation", f"unsupported interpolation {self.interpolation!r}"
        )

    def _segment(self, frame: float) -> tuple[int, int]:
        """Return the keyframe index pair surrounding ``frame``."""
        frames = [item.frame for item in self.keyframes]
        for index in range(len(frames) - 1):
            if frames[index] <= frame < frames[index + 1]:
                return index, index + 1
        raise CurveDocumentError(
            "evaluate", f"frame {frame} is outside the curve domain"
        )

    def _linear_at(self, frame: float) -> float:
        left, right = self._segment(frame)
        keyframes = self.keyframes
        start = keyframes[left]
        end = keyframes[right]
        span = float(end.frame - start.frame)
        if span == 0:
            return float(end.value)
        t = (frame - float(start.frame)) / span
        return float(start.value + (end.value - start.value) * t)

    def _cubic_at(self, frame: float) -> float:
        left, right = self._segment(frame)
        keyframes = self.keyframes
        p0 = keyframes[left - 1].value if left > 0 else keyframes[left].value
        p1 = keyframes[left].value
        p2 = keyframes[right].value
        p3 = keyframes[right + 1].value if right + 1 < len(keyframes) else p2
        span = float(keyframes[right].frame - keyframes[left].frame)
        t = (frame - float(keyframes[left].frame)) / span
        return float(
            0.5
            * (
                2 * p1
                + (-p0 + p2) * t
                + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t
            )
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            **self.header.to_dict(),
            "keyframes": [
                {"frame": keyframe.frame, "value": keyframe.value}
                for keyframe in self.keyframes
            ],
            "interpolation": self.interpolation,
            "default": self.default,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "CurveDocument":
        if not isinstance(value, Mapping):
            raise CurveDocumentError("curve", "must be an object")
        allowed = {
            "schema_version",
            "type",
            "id",
            "name",
            "symbol_name",
            "metadata",
            "keyframes",
            "interpolation",
            "default",
        }
        unknown = set(value).difference(allowed)
        if unknown:
            raise CurveDocumentError(
                "curve", "unknown fields: " + ", ".join(sorted(unknown))
            )
        try:
            header = ResourceHeader.from_dict(
                value,
                expected_type=CURVE_RESOURCE_TYPE,
                current_version=RESOURCE_SCHEMA_VERSION,
            )
        except ResourceDocumentError as exc:
            raise CurveDocumentError("header", str(exc)) from exc
        raw_keyframes = value.get("keyframes", [])
        if not isinstance(raw_keyframes, (list, tuple)):
            raise CurveDocumentError("keyframes", "must be an array")
        keyframes = []
        for index, item in enumerate(raw_keyframes):
            if not isinstance(item, Mapping):
                raise CurveDocumentError(
                    f"keyframes[{index}]", "must be an object"
                )
            frame = item.get("frame")
            number = item.get("value")
            if isinstance(frame, bool) or not isinstance(frame, int):
                raise CurveDocumentError(
                    f"keyframes[{index}].frame", "must be an integer"
                )
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise CurveDocumentError(
                    f"keyframes[{index}].value", "must be a number"
                )
            keyframes.append(CurveKeyframe(frame=frame, value=float(number)))
        document = cls(
            header=header,
            keyframes=tuple(keyframes),
            interpolation=str(value.get("interpolation", "linear")),
            default=float(value.get("default", 0.0)),
        )
        document.validate()
        return document

    @classmethod
    def new(
        cls,
        name: str = "New Curve",
        *,
        keyframes: tuple[CurveKeyframe, ...] | None = None,
        interpolation: str = "linear",
        default: float = 0.0,
    ) -> "CurveDocument":
        document = cls(
            header=ResourceHeader(
                type=CURVE_RESOURCE_TYPE,
                name=name,
                id=new_resource_id(),
            ),
            keyframes=keyframes or (),
            interpolation=interpolation,
            default=default,
        )
        document.validate()
        return document

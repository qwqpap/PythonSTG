"""Versioned recipe document for data-authored danmaku patterns."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Mapping

from src.authoring.resources import (
    PATTERN_RESOURCE_TYPE,
    RESOURCE_SCHEMA_VERSION,
    ResourceDocumentError,
    ResourceHeader,
)

from .bindings import BindingError, BindingSpec
from .graph import BehaviorGraph
from .script import ScriptBehavior


PATTERN_SHAPES = ("ring", "arc", "line", "spiral", "random", "flower")
AIM_MODES = ("fixed", "player")


class PatternDocumentError(ResourceDocumentError):
    """Raised when a PatternDocument field violates the v1 contract."""

    def __init__(self, path: str, message: str):
        self.path = path
        self.detail = message
        super().__init__(f"{path}: {message}")


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PatternDocumentError(path, "must be an object")
    return value


def _known(data: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = set(data).difference(allowed)
    if unknown:
        raise PatternDocumentError(
            path,
            "unknown fields: " + ", ".join(sorted(unknown)),
        )


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PatternDocumentError(path, "must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise PatternDocumentError(path, "must be finite")
    return result


def _integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PatternDocumentError(path, "must be an integer")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise PatternDocumentError(path, "must be a boolean")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PatternDocumentError(path, "must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class BulletSpec:
    bullet_type: str = "ball_m"
    color: str = "red"
    resource: str | None = None

    def validate(self, path: str = "bullet") -> None:
        _text(self.bullet_type, f"{path}.bullet_type")
        _text(self.color, f"{path}.color")
        if self.resource is not None:
            _text(self.resource, f"{path}.resource")

    @classmethod
    def from_dict(cls, value: Any) -> "BulletSpec":
        data = _object(value, "bullet")
        _known(data, {"bullet_type", "color", "resource"}, "bullet")
        spec = cls(
            bullet_type=data.get("bullet_type", "ball_m"),
            color=data.get("color", "red"),
            resource=data.get("resource"),
        )
        spec.validate()
        return spec


@dataclass(frozen=True)
class ShapeSpec:
    kind: str = "ring"
    count: int = 24
    origin_x: float = 0.0
    origin_y: float = 0.65
    angle_span: float = 360.0
    line_length: float = 1.0
    line_angle: float = 0.0

    def validate(self, path: str = "shape") -> None:
        if self.kind not in PATTERN_SHAPES:
            raise PatternDocumentError(
                f"{path}.kind",
                "must be one of: " + ", ".join(PATTERN_SHAPES),
            )
        count = _integer(self.count, f"{path}.count")
        if not 1 <= count <= 4096:
            raise PatternDocumentError(f"{path}.count", "must be in 1..4096")
        _finite(self.origin_x, f"{path}.origin_x")
        _finite(self.origin_y, f"{path}.origin_y")
        _finite(self.angle_span, f"{path}.angle_span")
        line_length = _finite(self.line_length, f"{path}.line_length")
        if line_length < 0:
            raise PatternDocumentError(f"{path}.line_length", "must be non-negative")
        _finite(self.line_angle, f"{path}.line_angle")

    @classmethod
    def from_dict(cls, value: Any) -> "ShapeSpec":
        data = _object(value, "shape")
        _known(
            data,
            {
                "kind",
                "count",
                "origin_x",
                "origin_y",
                "angle_span",
                "line_length",
                "line_angle",
            },
            "shape",
        )
        spec = cls(**data)
        spec.validate()
        return spec


@dataclass(frozen=True)
class AimSpec:
    mode: str = "fixed"
    angle: float = 270.0

    def validate(self, path: str = "aim") -> None:
        if self.mode not in AIM_MODES:
            raise PatternDocumentError(
                f"{path}.mode",
                "must be one of: " + ", ".join(AIM_MODES),
            )
        _finite(self.angle, f"{path}.angle")

    @classmethod
    def from_dict(cls, value: Any) -> "AimSpec":
        data = _object(value, "aim")
        _known(data, {"mode", "angle"}, "aim")
        spec = cls(**data)
        spec.validate()
        return spec


@dataclass(frozen=True)
class ScheduleSpec:
    delay_frames: int = 0
    interval_frames: int = 20
    burst_count: int = 1
    loop_count: int | None = 1

    def validate(self, path: str = "schedule") -> None:
        delay = _integer(self.delay_frames, f"{path}.delay_frames")
        interval = _integer(self.interval_frames, f"{path}.interval_frames")
        bursts = _integer(self.burst_count, f"{path}.burst_count")
        if delay < 0:
            raise PatternDocumentError(f"{path}.delay_frames", "must be non-negative")
        if not 1 <= interval <= 10_000_000:
            raise PatternDocumentError(
                f"{path}.interval_frames", "must be in 1..10000000"
            )
        if not 1 <= bursts <= 4096:
            raise PatternDocumentError(
                f"{path}.burst_count", "must be in 1..4096"
            )
        if self.loop_count is not None:
            loops = _integer(self.loop_count, f"{path}.loop_count")
            if not 1 <= loops <= 1_000_000:
                raise PatternDocumentError(
                    f"{path}.loop_count", "must be null or in 1..1000000"
                )

    @classmethod
    def from_dict(cls, value: Any) -> "ScheduleSpec":
        data = _object(value, "schedule")
        _known(
            data,
            {"delay_frames", "interval_frames", "burst_count", "loop_count"},
            "schedule",
        )
        spec = cls(**data)
        spec.validate()
        return spec


@dataclass(frozen=True)
class MotionSpec:
    speed: float = 2.0
    friction: float = 0.0
    spin: float = 0.0
    time_scale: float = 1.0
    max_lifetime: float = 0.0
    render_scale: float = 1.0
    bounce_x: bool = False
    bounce_y: bool = False

    def validate(self, path: str = "motion") -> None:
        speed = _finite(self.speed, f"{path}.speed")
        friction = _finite(self.friction, f"{path}.friction")
        _finite(self.spin, f"{path}.spin")
        time_scale = _finite(self.time_scale, f"{path}.time_scale")
        lifetime = _finite(self.max_lifetime, f"{path}.max_lifetime")
        render_scale = _finite(self.render_scale, f"{path}.render_scale")
        _boolean(self.bounce_x, f"{path}.bounce_x")
        _boolean(self.bounce_y, f"{path}.bounce_y")
        if speed < 0:
            raise PatternDocumentError(f"{path}.speed", "must be non-negative")
        if friction < 0:
            raise PatternDocumentError(f"{path}.friction", "must be non-negative")
        if time_scale < 0:
            raise PatternDocumentError(f"{path}.time_scale", "must be non-negative")
        if lifetime < 0:
            raise PatternDocumentError(
                f"{path}.max_lifetime", "must be non-negative"
            )
        if render_scale <= 0:
            raise PatternDocumentError(f"{path}.render_scale", "must be positive")

    @classmethod
    def from_dict(cls, value: Any) -> "MotionSpec":
        data = _object(value, "motion")
        _known(
            data,
            {
                "speed",
                "friction",
                "spin",
                "time_scale",
                "max_lifetime",
                "render_scale",
                "bounce_x",
                "bounce_y",
            },
            "motion",
        )
        spec = cls(**data)
        spec.validate()
        return spec


@dataclass(frozen=True)
class ModifierSpec:
    angle_offset_per_burst: float = 0.0
    speed_offset_per_burst: float = 0.0
    random_speed_variation: float = 0.0

    def validate(self, path: str = "modifiers") -> None:
        _finite(self.angle_offset_per_burst, f"{path}.angle_offset_per_burst")
        _finite(self.speed_offset_per_burst, f"{path}.speed_offset_per_burst")
        variation = _finite(
            self.random_speed_variation,
            f"{path}.random_speed_variation",
        )
        if not 0 <= variation <= 1:
            raise PatternDocumentError(
                f"{path}.random_speed_variation", "must be in 0..1"
            )

    @classmethod
    def from_dict(cls, value: Any) -> "ModifierSpec":
        data = _object(value, "modifiers")
        _known(
            data,
            {
                "angle_offset_per_burst",
                "speed_offset_per_burst",
                "random_speed_variation",
            },
            "modifiers",
        )
        spec = cls(**data)
        spec.validate()
        return spec


@dataclass
class PatternDocument:
    header: ResourceHeader
    bullet: BulletSpec
    shape: ShapeSpec
    aim: AimSpec
    schedule: ScheduleSpec
    motion: MotionSpec
    modifiers: ModifierSpec
    seed: int = 0
    bindings: tuple[BindingSpec, ...] = ()
    graph: BehaviorGraph | None = None
    script: ScriptBehavior | None = None

    @property
    def id(self) -> str:
        return self.header.id

    @property
    def name(self) -> str:
        return self.header.name

    @property
    def symbol_name(self) -> str | None:
        return self.header.symbol_name

    @property
    def schema_version(self) -> int:
        return self.header.schema_version

    @property
    def type(self) -> str:
        return self.header.type

    def validate(self) -> None:
        try:
            self.header.validate(
                expected_type=PATTERN_RESOURCE_TYPE,
                current_version=RESOURCE_SCHEMA_VERSION,
            )
        except ResourceDocumentError as exc:
            if isinstance(exc, PatternDocumentError):
                raise
            raise PatternDocumentError("header", str(exc)) from exc
        self.bullet.validate()
        self.shape.validate()
        self.aim.validate()
        self.schedule.validate()
        self.motion.validate()
        self.modifiers.validate()
        seed = _integer(self.seed, "seed")
        if not 0 <= seed <= 0x7FFF_FFFF_FFFF_FFFF:
            raise PatternDocumentError("seed", "must be in 0..2^63-1")
        if not isinstance(self.bindings, tuple):
            raise PatternDocumentError("bindings", "must be an array of bindings")
        for index, binding in enumerate(self.bindings):
            if not isinstance(binding, BindingSpec):
                raise PatternDocumentError(
                    f"bindings[{index}]", "must be a BindingSpec"
                )
            try:
                binding.validate(path=f"bindings[{index}]")
            except BindingError as exc:
                raise PatternDocumentError(exc.path, exc.message) from exc
        if self.graph is not None and not isinstance(self.graph, BehaviorGraph):
            raise PatternDocumentError("graph", "must be a BehaviorGraph or null")
        if self.graph is not None:
            self.graph.validate()
        if self.script is not None and not isinstance(self.script, ScriptBehavior):
            raise PatternDocumentError("script", "must be a ScriptBehavior or null")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = {
            **self.header.to_dict(),
            "seed": self.seed,
            "bullet": asdict(self.bullet),
            "shape": asdict(self.shape),
            "aim": asdict(self.aim),
            "schedule": asdict(self.schedule),
            "motion": asdict(self.motion),
            "modifiers": asdict(self.modifiers),
            "bindings": [binding.to_dict() for binding in self.bindings],
            "graph": self.graph.to_dict() if self.graph is not None else None,
            "script": self.script.to_dict() if self.script is not None else None,
        }
        return payload

    @classmethod
    def new(
        cls,
        name: str = "New Pattern",
        *,
        symbol_name: str | None = None,
    ) -> "PatternDocument":
        document = cls(
            header=ResourceHeader(
                type=PATTERN_RESOURCE_TYPE,
                name=name,
                symbol_name=symbol_name,
            ),
            bullet=BulletSpec(),
            shape=ShapeSpec(),
            aim=AimSpec(),
            schedule=ScheduleSpec(),
            motion=MotionSpec(),
            modifiers=ModifierSpec(),
        )
        document.validate()
        return document

    @classmethod
    def from_dict(cls, value: Any) -> "PatternDocument":
        data = _object(value, "pattern")
        _known(
            data,
            {
                "schema_version",
                "type",
                "id",
                "name",
                "symbol_name",
                "metadata",
                "seed",
                "bullet",
                "shape",
                "aim",
                "schedule",
                "motion",
                "modifiers",
                "bindings",
                "graph",
                "script",
            },
            "pattern",
        )
        try:
            header = ResourceHeader.from_dict(
                data,
                expected_type=PATTERN_RESOURCE_TYPE,
                current_version=RESOURCE_SCHEMA_VERSION,
            )
        except ResourceDocumentError as exc:
            raise PatternDocumentError("header", str(exc)) from exc
        required = ("bullet", "shape", "aim", "schedule", "motion", "modifiers")
        missing = [field for field in required if field not in data]
        if missing:
            raise PatternDocumentError(
                "pattern",
                "missing sections: " + ", ".join(missing),
            )
        raw_bindings = data.get("bindings", ())
        if not isinstance(raw_bindings, (list, tuple)):
            raise PatternDocumentError("bindings", "must be an array")
        document = cls(
            header=header,
            bullet=BulletSpec.from_dict(data["bullet"]),
            shape=ShapeSpec.from_dict(data["shape"]),
            aim=AimSpec.from_dict(data["aim"]),
            schedule=ScheduleSpec.from_dict(data["schedule"]),
            motion=MotionSpec.from_dict(data["motion"]),
            modifiers=ModifierSpec.from_dict(data["modifiers"]),
            seed=data.get("seed", 0),
            bindings=tuple(
                BindingSpec.from_dict(item) for item in raw_bindings
            ),
            graph=(
                BehaviorGraph.from_dict(data["graph"])
                if data.get("graph") is not None
                else None
            ),
            script=(
                ScriptBehavior.from_dict(data["script"])
                if data.get("script") is not None
                else None
            ),
        )
        document.validate()
        return document

    @classmethod
    def from_pattern_spec(
        cls,
        value: Any,
        *,
        display_name: str | None = None,
    ) -> "PatternDocument":
        """Import the development ``PatternSpec`` without Python codegen."""

        if is_dataclass(value):
            data = asdict(value)
        elif isinstance(value, Mapping):
            data = dict(value)
        else:
            data = dict(vars(value))
        legacy_name = _text(data.get("name", "LabPattern"), "PatternSpec.name")
        shape_kind = _text(data.get("pattern", "ring"), "PatternSpec.pattern")
        document = cls(
            header=ResourceHeader(
                type=PATTERN_RESOURCE_TYPE,
                name=display_name or legacy_name,
                symbol_name=legacy_name,
                metadata={"imported_from": "PatternSpec"},
            ),
            bullet=BulletSpec(
                bullet_type=data.get("bullet_type", "ball_m"),
                color=data.get("color", "red"),
            ),
            shape=ShapeSpec(
                kind=shape_kind,
                count=data.get("count", 24),
                origin_x=data.get("x", 0.0),
                origin_y=data.get("y", 0.65),
                angle_span=data.get("angle_span", 360.0),
            ),
            aim=AimSpec(mode="fixed", angle=data.get("start_angle", 270.0)),
            schedule=ScheduleSpec(
                delay_frames=0,
                interval_frames=data.get("interval", 20),
                burst_count=data.get("bursts", 1),
                loop_count=None,
            ),
            motion=MotionSpec(
                speed=data.get("speed", 2.0),
                spin=data.get("spin", 0.0),
            ),
            modifiers=ModifierSpec(
                angle_offset_per_burst=data.get("angle_offset_per_burst", 0.0),
            ),
            seed=data.get("seed", 0),
        )
        document.validate()
        return document

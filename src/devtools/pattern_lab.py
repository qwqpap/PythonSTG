"""Pattern Lab data model and exporters."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PATTERN_MODES = ("ring", "arc", "spiral", "flower")


@dataclass(frozen=True)
class PatternSpec:
    name: str = "LabPattern"
    pattern: str = "ring"
    x: float = 0.0
    y: float = 0.65
    count: int = 24
    speed: float = 2.0
    start_angle: float = 270.0
    angle_span: float = 360.0
    interval: int = 20
    bursts: int = 1
    angle_offset_per_burst: float = 7.5
    bullet_type: str = "ball_m"
    color: str = "red"
    spin: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PatternSpec":
        values = asdict(cls())
        for key in values:
            if key in data:
                values[key] = data[key]
        spec = cls(**values)
        spec.validate()
        return spec

    def validate(self) -> None:
        if not _IDENT_RE.match(self.name):
            raise ValueError("name must be a valid Python identifier")
        if self.pattern not in PATTERN_MODES:
            raise ValueError(f"pattern must be one of: {', '.join(PATTERN_MODES)}")
        if self.count <= 0 or self.count > 512:
            raise ValueError("count must be in 1..512")
        if self.speed < 0 or self.speed > 30:
            raise ValueError("speed must be in 0..30")
        if self.interval <= 0 or self.interval > 600:
            raise ValueError("interval must be in 1..600 frames")
        if self.bursts <= 0 or self.bursts > 999:
            raise ValueError("bursts must be in 1..999")
        if not self.bullet_type:
            raise ValueError("bullet_type must not be empty")
        if not self.color:
            raise ValueError("color must not be empty")

    @property
    def angle_step(self) -> float:
        if self.count == 1:
            return 0.0
        if abs(self.angle_span) >= 360.0:
            return self.angle_span / self.count
        return self.angle_span / (self.count - 1)


def clean_number(value: float | int, digits: int = 6) -> float | int:
    if isinstance(value, int):
        return value
    rounded = round(float(value), digits)
    if rounded == 0:
        return 0.0
    return rounded


def format_number(value: float | int) -> str:
    value = clean_number(value)
    if isinstance(value, int):
        return str(value)
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    if "." not in text:
        text += ".0"
    return text


def display_value(value: Any) -> str:
    if isinstance(value, float):
        text = format_number(value)
        return text[:-2] if text.endswith(".0") else text
    return str(value)


def simulate_burst(spec: PatternSpec, frames: int = 90, fps: float = 60.0) -> list[list[tuple[float, float]]]:
    """Return bullet point positions per frame for a single preview burst."""
    spec.validate()
    positions: list[list[tuple[float, float]]] = []
    bullets = bullet_parameters(spec)
    for frame in range(max(0, frames)):
        t = frame / fps
        frame_positions = [
            (spec.x + math.cos(math.radians(angle)) * speed * t, spec.y + math.sin(math.radians(angle)) * speed * t)
            for angle, speed in bullets
        ]
        positions.append(frame_positions)
    return positions


def bullet_parameters(spec: PatternSpec, burst_index: int = 0) -> list[tuple[float, float]]:
    """Return ``(angle_degrees, speed)`` pairs for one burst."""
    spec.validate()
    center_angle = spec.start_angle + burst_index * spec.angle_offset_per_burst

    if spec.pattern == "ring":
        step = 360.0 / spec.count
        return [
            (clean_number(center_angle + i * step), clean_number(spec.speed))
            for i in range(spec.count)
        ]

    if spec.pattern == "arc":
        start = center_angle if abs(spec.angle_span) >= 360.0 else center_angle - spec.angle_span / 2.0
        step = spec.angle_step
        return [
            (clean_number(start + i * step), clean_number(spec.speed))
            for i in range(spec.count)
        ]

    if spec.pattern == "spiral":
        step = spec.angle_span / max(1, spec.count)
        return [
            (
                clean_number(center_angle + i * step),
                clean_number(spec.speed * (0.65 + 0.55 * (i / max(1, spec.count - 1)))),
            )
            for i in range(spec.count)
        ]

    if spec.pattern == "flower":
        step = 360.0 / spec.count
        return [
            (
                clean_number(center_angle + i * step),
                clean_number(spec.speed * (0.55 + 0.45 * abs(math.sin(math.radians(i * spec.angle_span))))),
            )
            for i in range(spec.count)
        ]

    raise ValueError(f"unsupported pattern: {spec.pattern}")


def export_spellcard(spec: PatternSpec, class_name: str | None = None) -> str:
    spec.validate()
    class_name = class_name or spec.name
    if not _IDENT_RE.match(class_name):
        raise ValueError("class_name must be a valid Python identifier")
    lines = [
        "from src.game.stage.spellcard import SpellCard",
        "",
        "",
        f"class {class_name}(SpellCard):",
        f"    name = \"{spec.name}\"",
        "    hp = 1000",
        "    time_limit = 45",
        "",
        "    async def run(self):",
        f"        x = {format_number(spec.x)}",
        f"        y = {format_number(spec.y)}",
        "        angle = 0.0",
        "        while True:",
        f"            for burst in range({spec.bursts}):",
    ]

    if spec.pattern == "ring":
        lines.extend([
            "                self.fire_circle(",
            "                    x=x, y=y,",
            f"                    count={spec.count},",
            f"                    speed={format_number(spec.speed)},",
            f"                    start_angle={format_number(spec.start_angle)} + angle,",
            f"                    bullet_type=\"{spec.bullet_type}\",",
            f"                    color=\"{spec.color}\",",
            f"                    spin={format_number(spec.spin)},",
            "                )",
        ])
    elif spec.pattern == "arc":
        lines.extend([
            "                self.fire_arc(",
            "                    x=x, y=y,",
            f"                    count={spec.count},",
            f"                    speed={format_number(spec.speed)},",
            f"                    center_angle={format_number(spec.start_angle)} + angle,",
            f"                    arc_angle={format_number(spec.angle_span)},",
            f"                    bullet_type=\"{spec.bullet_type}\",",
            f"                    color=\"{spec.color}\",",
            f"                    spin={format_number(spec.spin)},",
            "                )",
        ])
    else:
        lines.extend([
            f"                # Pattern Lab mode: {spec.pattern}",
            f"                params = {[(clean_number(a), clean_number(s)) for a, s in bullet_parameters(spec)]!r}",
            "                for bullet_angle, bullet_speed in params:",
            "                    self.fire(",
            "                        x=x, y=y,",
            "                        angle=float(bullet_angle) + angle,",
            "                        speed=float(bullet_speed),",
            f"                        bullet_type=\"{spec.bullet_type}\",",
            f"                        color=\"{spec.color}\",",
            f"                        spin={format_number(spec.spin)},",
            "                    )",
        ])

    lines.extend([
        f"                angle += {format_number(spec.angle_offset_per_burst)}",
        f"                await self.wait({spec.interval})",
    ])
    return "\n".join(lines) + "\n"


def load_spec(path: Path | str) -> PatternSpec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pattern file must contain a JSON object")
    return PatternSpec.from_dict(data)


def save_spec(path: Path | str, spec: PatternSpec) -> None:
    spec.validate()
    Path(path).write_text(json.dumps(asdict(spec), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

"""Build the checked-in deterministic starter Pattern preset library."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pattern import (
    PatternDocument,
    PresetDescriptor,
    PresetLibrary,
    PresetParameter,
    PresetSlot,
)


OUTPUT = PROJECT_ROOT / "game_content" / "presets" / "builtin_patterns.pystg.json"


def _descriptor(
    slug: str,
    name: str,
    *,
    category: str,
    shape: str,
    aim: str = "fixed",
    count: int = 24,
    angle_span: float = 360.0,
    bursts: int = 1,
    interval: int = 20,
    speed: float = 2.0,
    angle_step: float = 0.0,
    speed_step: float = 0.0,
    spin: float = 0.0,
    lifetime: float = 0.0,
    metadata: dict | None = None,
) -> PresetDescriptor:
    document = PatternDocument.new(name)
    document.header.id = str(__import__("uuid").uuid5(__import__("uuid").NAMESPACE_URL, f"pystg:{slug}:1.0.0"))
    document.header.metadata.update(metadata or {})
    document.shape = replace(document.shape, kind=shape, count=count, angle_span=angle_span)
    document.aim = replace(document.aim, mode=aim)
    document.schedule = replace(
        document.schedule,
        interval_frames=interval,
        burst_count=bursts,
        loop_count=1,
    )
    document.motion = replace(document.motion, speed=speed, spin=spin, max_lifetime=lifetime)
    document.modifiers = replace(
        document.modifiers,
        angle_offset_per_burst=angle_step,
        speed_offset_per_burst=speed_step,
    )
    parameters = (
        PresetParameter("count", "int", count, "shape.count", 1, 512),
        PresetParameter("speed", "float", speed, "motion.speed", 0.0, 20.0),
        PresetParameter("interval", "int", interval, "schedule.interval_frames", 1, 3600),
        PresetParameter("bursts", "int", bursts, "schedule.burst_count", 1, 512),
    )
    slots = (
        PresetSlot(
            "termination_reaction",
            "reaction",
            "metadata.termination_reaction",
            (metadata or {}).get("termination_reaction"),
            True,
        ),
    )
    internal_nodes = (
        {"id": "source", "kind": "source", "label": "子弹资源", "target": "bullet"},
        {"id": "shape", "kind": "emitter", "label": name, "target": "shape"},
        {"id": "schedule", "kind": "schedule", "label": "发射节奏", "target": "schedule"},
        {"id": "motion", "kind": "motion", "label": "运动", "target": "motion"},
        {"id": "termination", "kind": "reaction", "label": "生命周期反应", "target": "metadata.termination_reaction"},
    )
    return PresetDescriptor(
        preset_id=f"builtin.pattern.{slug}",
        version="1.0.0",
        display_name=name,
        category=category,
        description=f"内置 {name} Pattern 预设",
        template=document.to_dict(),
        parameters=parameters,
        slots=slots,
        inputs={"origin": "vec2", "target": "vec2"},
        outputs={"spawned": "bullet_batch"},
        events={"completed": "pattern.completed", "terminated": "bullet.terminated"},
        lifecycle={
            "owner_scope": "clip",
            "cancel_policy": "cancel_owned",
            "completion_event": "pattern.completed",
        },
        budget={
            "max_bullets_per_burst": count,
            "max_bullets_total": count * bursts,
            "max_instances": 1,
        },
        internal_nodes=internal_nodes,
    )


def build_library() -> PresetLibrary:
    presets = (
        _descriptor("aimed", "自机狙", category="basic", shape="arc", aim="player", count=1, angle_span=0, interval=30),
        _descriptor("odd-shot", "奇数弹", category="basic", shape="arc", aim="player", count=5, angle_span=48),
        _descriptor("even-shot", "偶数弹", category="basic", shape="arc", aim="player", count=6, angle_span=60),
        _descriptor("ring", "圆形开花", category="basic", shape="ring", count=32),
        _descriptor("fan-sweep", "扇形扫射", category="basic", shape="arc", aim="player", count=9, angle_span=100, bursts=8, interval=6, angle_step=7),
        _descriptor("single-spiral", "单螺旋", category="rotation", shape="ring", count=8, bursts=16, interval=4, angle_step=11.25),
        _descriptor("double-spiral", "双螺旋", category="rotation", shape="ring", count=16, bursts=16, interval=4, angle_step=11.25),
        _descriptor("interleaved-spiral", "交错螺旋", category="rotation", shape="ring", count=12, bursts=18, interval=3, angle_step=25),
        _descriptor("accelerating-rotation", "加速旋转", category="rotation", shape="spiral", count=12, bursts=20, interval=3, angle_step=8, speed_step=0.05, metadata={"emitter_rotation_acceleration": 1.25}),
        _descriptor("delayed-turn", "延迟转向", category="advanced", shape="arc", aim="player", count=12, angle_span=80, bursts=3, interval=18, metadata={"trajectory": {"kind": "delayed_turn", "delay_frames": 30, "angular_velocity_degrees": 120}}),
        _descriptor("bullet-split", "子弹分裂", category="advanced", shape="ring", count=12, lifetime=0.25, metadata={"termination_reaction": {"action": "split", "reason": "expired", "count": 6, "speed": 1.5, "max_lifetime": 2.0}}),
        _descriptor("speed-layers", "速度层叠", category="advanced", shape="spiral", count=32, speed=2.5, angle_span=720, metadata={"trajectory": {"kind": "linear_speed", "acceleration": 0.35}}),
        _descriptor("ripple", "波纹", category="advanced", shape="flower", count=48, bursts=6, interval=12, angle_step=7.5, metadata={"trajectory": {"kind": "wave_angle", "amplitude_degrees": 35, "frequency": 7.5}}),
        _descriptor("rice-wall", "米弹墙", category="advanced", shape="line", count=64, angle_span=0, bursts=8, interval=10, metadata={"shape_role": "wall"}),
    )
    return PresetLibrary("builtin.patterns", "1.0.0", presets)


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = build_library().to_dict()
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(payload['presets'])} presets to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Produce the fixed N5 preset compile/runtime workload report."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.pattern import PatternCompiler, PatternRunner, PresetInstance, PresetLibrary, PresetResolver


class _Player:
    pos = [0.25, -0.7]


def profile(library_path: Path) -> dict:
    library = PresetLibrary.load(library_path)
    rows = []
    total_bullets = 0
    total_batches = 0
    started_all = perf_counter()
    for descriptor in library.presets:
        started = perf_counter()
        resolver = PresetResolver((descriptor,))
        instance = PresetInstance.new(descriptor)
        program = resolver.compile(instance, compiler=PatternCompiler())
        pool = OptimizedBulletPool(
            max_bullets=max(1024, descriptor.budget["max_bullets_total"] + 16)
        )
        context = StageContext(pool, _Player())
        runner = PatternRunner(program, owner_tag=9100 + len(rows))
        runner.start(context)
        spawned = 0
        while runner.state.value == "running":
            spawned += runner.tick(context).spawned_count
        elapsed_ms = (perf_counter() - started) * 1000.0
        total_bullets += spawned
        total_batches += pool.batch_spawn_calls
        rows.append(
            {
                "preset_id": descriptor.preset_id,
                "version": descriptor.version,
                "display_name": descriptor.display_name,
                "spawned": spawned,
                "batch_writes": pool.batch_spawn_calls,
                "per_bullet_callbacks": len(pool.death_handlers) + len(pool.emitter_callbacks),
                "elapsed_ms": round(elapsed_ms, 3),
            }
        )
    return {
        "gate": "N5 fixed preset workload",
        "library_id": library.library_id,
        "library_version": library.version,
        "environment": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "totals": {
            "presets": len(rows),
            "spawned": total_bullets,
            "batch_writes": total_batches,
            "per_bullet_callbacks": sum(row["per_bullet_callbacks"] for row in rows),
            "elapsed_ms": round((perf_counter() - started_all) * 1000.0, 3),
            "regression_ceiling_ms": 2500.0,
        },
        "presets": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile the N5 starter preset workload")
    parser.add_argument(
        "--library",
        type=Path,
        default=PROJECT_ROOT / "game_content" / "presets" / "builtin_patterns.pystg.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = profile(args.library)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    totals = report["totals"]
    if totals["per_bullet_callbacks"] != 0 or totals["elapsed_ms"] >= totals["regression_ceiling_ms"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

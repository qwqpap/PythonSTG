"""Measure formal PatternRunner batch-spawn throughput for the M1 gate."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.context import StageContext
from src.pattern import PatternCompiler, PatternDocument, PatternRunner


class _Player:
    pos = [0.0, -0.8]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=512)
    parser.add_argument("--bursts", type=int, default=100)
    parser.add_argument("--pool-size", type=int, default=60000)
    args = parser.parse_args()

    document = PatternDocument.new("M1 Dense Burst Benchmark")
    document.shape = replace(document.shape, count=args.count)
    document.schedule = replace(
        document.schedule,
        interval_frames=1,
        burst_count=args.bursts,
        loop_count=1,
    )
    compile_start = perf_counter()
    program = PatternCompiler().compile(document)
    compile_seconds = perf_counter() - compile_start

    pool = OptimizedBulletPool(max_bullets=args.pool_size)
    context = StageContext(pool, _Player())
    runner = PatternRunner(program, owner_tag=900001)
    runner.start(context)
    spawn_start = perf_counter()
    results = runner.advance(context, args.bursts)
    spawn_seconds = perf_counter() - spawn_start
    spawned = sum(result.spawned_count for result in results)
    payload = {
        "count_per_burst": args.count,
        "bursts": args.bursts,
        "requested_bullets": args.count * args.bursts,
        "spawned_bullets": spawned,
        "pool_size": args.pool_size,
        "compile_seconds": round(compile_seconds, 6),
        "spawn_seconds": round(spawn_seconds, 6),
        "bullets_per_second": round(spawned / spawn_seconds, 2) if spawn_seconds else None,
        "batch_spawn_calls": pool.batch_spawn_calls,
        "batch_api": pool.batch_spawn_calls == args.bursts,
        "per_bullet_callbacks": len(pool.death_handlers) + len(pool.emitter_callbacks),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if spawned == args.count * args.bursts else 1


if __name__ == "__main__":
    raise SystemExit(main())

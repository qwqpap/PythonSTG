# Pattern resource contract (M1)

`pystg.pattern` is a versioned authoring document that compiles directly into
the formal game runtime. The JSON document is the source of truth; generated
Python is an optional compatibility/export artifact.

## Data flow

```text
*.pystg.json
  -> PatternDocument (validated recipe)
  -> PatternCompiler (resource resolution and static precomputation)
  -> PatternProgram (immutable IR)
  -> PatternRunner (fixed 60 Hz scheduling)
  -> StageContext.create_bullets_batch
  -> OptimizedBulletPool (NumPy/Numba-compatible bullet state)
```

The editor preview and gameplay must consume the same `PatternProgram`,
`PatternRunner`, `StageContext`, and bullet-pool behavior. An editor may draw a
grid, handles, selections, guides, and diagnostic overlays above that output,
but an approximate editor-only simulator is not formal preview evidence.

## V1 document sections

The published schema is
[`schemas/pystg-pattern-v1.schema.json`](schemas/pystg-pattern-v1.schema.json).
It uses the common resource header plus these sections:

- `bullet`: a type/color alias or direct `res://atlas.json#sprite` reference.
- `shape`: `ring`, `arc`, `line`, `spiral`, `random`, or legacy-compatible
  `flower`, including count and logical runtime origin.
- `aim`: a fixed direction or a direction sampled toward the player at spawn.
- `schedule`: integer-frame delay and interval, bursts per loop, and finite or
  infinite loop count (`null`).
- `motion`: initial speed plus data-oriented pool fields for friction, spin,
  time scale, lifetime, scale, and axis bounce.
- `modifiers`: deterministic per-burst angle/speed offsets and random-speed
  variation.
- `seed`: a stable non-negative 63-bit seed.

Unknown fields are rejected in v1. A shape can contain at most 4096 bullets and
a schedule at most 4096 distinct burst templates. Compilation additionally
rejects programs that would precompute more than 1,000,000 bullet records.

## Compilation and diagnostics

`PatternCompiler` resolves aliases or direct sprite fragments, hashes document
and dependency contents, optionally resolves the sprite's integer runtime
index, and precomputes one immutable `BurstTemplate` per burst in a schedule
loop. Its cache identity includes the schema version, canonical document JSON,
resource contents, and sprite index.

Compilation failures carry structured diagnostics with severity, code,
resource UUID, property path, and message. Missing files, missing fragments,
invalid alias maps, oversized programs, and sprite-index failures are errors;
the compiler does not silently substitute an authored resource.

## Runner and ownership

`PatternRunner.tick()` advances in integer frames. Its lifecycle is start,
pause/resume, reset, and stop. Resetting replays the same immutable program and
seed deterministically. Every runner has a non-zero owner tag, used to clear,
translate, or change time scale only for that instance's live bullets.

Dense bullets are never scene nodes. A burst is written to the structured
NumPy pool as one batch, and common motion remains in pool fields and optimized
kernels. Pattern execution installs no per-bullet Python update/death/emitter
callbacks.

## Compatibility

`PatternDocument.from_pattern_spec()` imports the existing Pattern Lab model,
including its ring, arc, spiral, flower, interval, multi-burst, angle-offset,
and infinite-loop behavior. This path does not generate or reverse-parse
Python.

Use `tools/benchmark_pattern_runtime.py` for the representative M1 dense-burst
measurement. Performance evidence is environment-specific and is recorded in
the current editor implementation TODO evidence section.

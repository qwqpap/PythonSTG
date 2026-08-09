# Formal Pattern Preview Controller and Protocol

This document freezes the Phase 2 editor-to-preview contract. The preview is
not an editor-only bullet simulator. It executes the same formal path used by
gameplay:

```text
PatternDocument
  -> PatternCompiler
  -> immutable PatternProgram
  -> PatternRunner
  -> StageContext
  -> OptimizedBulletPool
  -> OptimizedBulletRenderer
```

The editor adds process controls, statistics, diagnostics, the coordinate grid,
and player/emitter gizmos. Gizmos never mutate bullet behavior. Bullets remain
pool entries rather than scene nodes, and no per-bullet Python callbacks are
introduced.

## Ownership

- `src/preview/controller.py` owns deterministic preview state and commands.
- `src/preview/protocol.py` owns protocol version 1 and request correlation.
- `src/preview/worker.py` owns the blocking headless NDJSON service.
- `tools/preview_pattern.py` owns the controllable external ModernGL window.
- `src/editor/preview_process.py` owns Qt `QProcess` isolation and transport.
- `src/editor/preview_panel.py` displays controls, live statistics, and errors.
- `src/editor/app.py` connects Pattern resources and Inspector changes to the
  process without generating Python.

M3, not M2, owns a full Pattern workspace and multi-document editing. Embedding
ModernGL in `QOpenGLWidget` and embedding the complete `main.py` game remain
deferred.

## Transport envelope

Transport is UTF-8 newline-delimited JSON over stdin/stdout. Stdout contains
protocol messages only. Routine legacy asset-loader prints are suppressed, and
stderr is reserved for bounded diagnostic logs and uncaught failures.

Every request is one line:

```json
{
  "protocol_version": 1,
  "request_id": "client-generated-unique-id",
  "command": "load",
  "payload": {"resource": "res://game_content/patterns/example.pystg.json"}
}
```

Every response or event uses the same envelope:

```json
{
  "protocol_version": 1,
  "request_id": "client-generated-unique-id-or-null",
  "event": "response",
  "payload": {"ok": true, "command": "load", "result": {}}
}
```

The client must first send `hello`. Commands received before negotiation return
`protocol_error`. Spontaneous statistics use `request_id: null`; events caused
by a command retain that command's request ID.

## Commands

| Command | Payload | Resulting behavior |
|---|---|---|
| `load` | `document` object or `resource` path | Parse and compile prospectively, then replace the active program only on success. |
| `play` | `{}` | Start or resume fixed 60 Hz execution. |
| `pause` | `{}` | Pause the runner without discarding bullets or frame state. |
| `step` | `{}` | Advance exactly one formal tick and remain paused. |
| `seek` | `frame` integer in `0..1000000` | Deterministically reset and replay to the requested frame. |
| `reset` | `{}` | Clear owned bullets and return to paused frame zero. |
| `stop` | `{}` | Stop and clear the active runner; safe to repeat. |
| `set-property` | `path`, `value` | Rebuild a candidate `PatternDocument`, compile, and atomically reload it. |
| `set-player-position` | finite `x`, `y` | Move the formal aim target. |
| `set-seed` | integer `seed` | Reload through the same document property path. |
| `set-gizmos` | boolean `visible` | Toggle diagnostic drawing only. |
| `get-stats` | `{}` | Return the current state snapshot. |
| `shutdown` | `{}` | Close the controller and terminate the worker loop. |

Lifecycle commands and cleanup are idempotent. A finite pattern transitions to
paused when its runner finishes.

## Events and failure retention

The service emits `hello`, `response`, `status`, `statistics`,
`program_loaded`, `player_position`, `gizmos`, `compile_error`, `runtime_error`,
and `protocol_error` events.

Statistics include state, frame, live bullet count, pool capacity, seed,
pause state, update time, render time, program hash, player position, gizmo
state, reload status, and the last error. Stage mode additionally reports
`state_path` (stable State UUIDs), `state_path_names`, State-local
`active_clips`, and the read-only runtime `node_state`; these fields are
feedback only and are never merged into the authoring document.

`load`, `set-property`, and `set-seed` compile a prospective document before
touching the active runner. If parsing or compilation fails, the current
program, bullets, frame, and play state remain active. The error includes
`active_program_preserved: true`; a later valid edit reloads normally.

The Qt client validates JSON objects and protocol versions, drains stdout and
stderr independently, caps forwarded stderr, reports malformed output and
crashes as structured issues, and uses bounded terminate/kill cleanup. Commands
sent before the hello response are queued and flushed after negotiation.

## External preview surface

The window renders the real optimized bullet pool and a side diagnostics panel.
Keyboard shortcuts are:

- Space: play or pause
- `.`: advance one frame
- R: reset
- G: toggle grid/player/emitter gizmos
- Escape: close

On Windows, the exact Numba render-batch path is warmed before the live stdin
reader thread starts. This prevents a first-render JIT/import deadlock when the
worker is hosted by `QProcess`; subsequent frames still use the same optimized
gameplay renderer.

Manual sample:

```powershell
conda run --no-capture-output -n touhou_guess python tools/preview_pattern.py `
  --project . `
  --pattern res://game_content/patterns/starter_ring.pystg.json
```

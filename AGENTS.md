# PySTG Agent Instructions

This file defines repository-wide rules for AI coding agents working on PySTG.

## Working tree hygiene

- Check `git status --short` before editing and preserve unrelated local changes.
- Never modify, stage, revert, or commit `.claude/settings.local.json`.
- Do not commit generated build output under `game_content/generated/` or copyrighted original game assets.
- Use UTF-8, LF line endings, 4-space indentation, and project-relative paths. Never hardcode machine-specific absolute paths in code or docs.

## Core architecture invariants

1. **Single authoring source of truth**: declarative projects live under `game_content/authoring/<project_id>/`. Generated output under `game_content/generated/<project_id>/` is disposable.
2. **Handwritten stages stay independent**: `game_content/stages/stage1..stage3/` remain first-class runtime content via `game_content/entry.py`; the editor does not reverse-engineer them.
3. **Headless core**: `src/authoring/`, `src/compiler/`, timeline analysis, and preview protocol must not import Qt, editor widgets, or the renderer.
4. **One runtime, batch hot paths**: generated stages target the existing `StageScript`, `Wave`, `EnemyScript`, `SpellCard`, `StageManager`, pools, lasers, audio, and renderer. Do not introduce a second gameplay runtime, ECL/ANM VM, or per-bullet Python callbacks.
5. **Timeline is a projection**: it projects source nodes and bounded runtime Trace, never a separately saved document.
6. **Read-only fallback for unsupported Python**: unsupported authoring syntax opens read-only and is never overwritten or best-effort-rewritten.
7. **Single undo stack & explicit preview**: every editor edit goes through one `QUndoStack` owned by `EditorSession`. Preview starts only on an explicit Run; subsequent edits mark the preview stale without hot-reloading, and a failed build must preserve the previous valid build and running preview.
8. **Project-relative assets**: resource references use `res://` resolved via `ProjectContext`; generated packages never copy assets.
9. **No v1 editor restoration**: the legacy Scene/Pattern/Graph editor (`archive/editor-v1-f9e0798`) is not a compatibility target.
10. **Language convention**: editor UI text is Simplified Chinese; Python APIs, identifiers, and generated code stay English.

## Verification

The legacy `tests/` suite has been removed by the maintainer. Do not recreate it unless explicitly asked. Validate changes with focused, real checks matching what you modified:

```bash
python -m compileall -q main.py src game_content tools
python tools/validate_assets.py
git diff --check
```

- When changing runtime or compiler behavior, verify through an actual Python run against `StageManager` / `PackageBuilder` instead of relying on syntax checks alone.
- When changing editor UI or preview embedding, test on a real window/input path when possible; do not mislabel offscreen checks or screenshots as native interactive verification.
- When changing documentation, run `npm run docs:build` to verify links and site rendering.
- Be honest about what was actually run and what was not verified.

## Documentation discipline

Keep documentation concise, readable, and written for human developers:

- Do not dump agent session transcripts, `allowlist`/`denylist` tables, temporary file hashes, one-off local benchmarks, or machine-specific paths into `README.md` or `docs/`.
- Keep design docs (`EDITOR_ARCHITECTURE.md`, `architecture.md`) focused on current architecture rather than appending dated patch logs.
- Keep `docs/EDITOR_IMPLEMENTATION_TODO.md` limited to editor roadmap items and real open tasks.

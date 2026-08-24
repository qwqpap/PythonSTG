# PySTG Agent Instructions

This file applies to the whole repository.

## Code-driven editor roadmap

Before changing the level authoring editor, read
[`docs/EDITOR_IMPLEMENTATION_TODO.md`](docs/EDITOR_IMPLEMENTATION_TODO.md) and
[`docs/EDITOR_ARCHITECTURE.md`](docs/EDITOR_ARCHITECTURE.md) completely. The
roadmap is the only implementation order and status record for the editor.

The mandatory order is:

```text
CD0 -> CD1 -> CD2 -> CD3 -> CD4 -> CD5 -> CD6 -> CD7
```

Do not start a later phase while an earlier phase gate is red. The previous
Scene/Pattern/Graph editor is archived at tag `archive/editor-v1-f9e0798`; it is
not a compatibility target and must not be restored through shims, feature
flags, hidden menus, or retained tests.

## Fixed product contract

1. The only authoring source of truth is the restricted declarative Python
   project under `game_content/authoring/<project_id>/`.
2. Generated Python and metadata live under
   `game_content/generated/<project_id>/`; they are disposable build output and
   must not be committed.
3. Existing handwritten Stage1-Stage3 remain supported runtime content, but the
   editor does not reverse-engineer them.
4. The DSL, parser, model, compiler, timeline analysis, and preview protocol are
   headless and must not import Qt, editor widgets, or the renderer.
5. Generated stages use the existing `StageScript`, `Wave`, `EnemyScript`,
   `SpellCard`, `StageManager`, renderer, pools, lasers, audio, and game loop.
   Do not introduce a second runtime or per-bullet Python callbacks.
6. The timeline is a projection of source nodes and runtime Trace. It is never
   a separately saved authoring document.
7. Unsupported Python opens read-only and is never overwritten or
   best-effort-rewritten.
8. Every editor mutation uses one `QUndoStack`. External reload discards the
   entire stack only after an explicit user decision.
9. Preview starts only on an explicit Run. Edits mark the running preview
   stale; they do not hot-reload it.
10. Resource references remain project-relative `res://` values resolved via
    `ProjectContext`; generated packages never copy assets.

## Scope discipline

The new editor is only for level gameplay authoring. Do not add a plugin
marketplace, behavior/state/render graph, security sandbox, dependency
installer, legacy importer, arbitrary two-way Python editor, or another asset
editor. Keep the first UI Simplified Chinese while Python APIs and generated
code stay English.

For each CD task, state one owner, an explicit path allowlist, and a denylist
before editing. Preserve unrelated changes and always run `git status --short`
first. The coordinating agent alone updates roadmap status. A verifier who did
not implement the task performs the final read-only gate.

If work must cross the declared boundary, stop and revise the boundary before
editing. Never modify, stage, revert, or commit `.claude/settings.local.json`.

## Editing and verification rules

- Use the narrowest relevant tests while iterating and invoke them with
  `python -m pytest`, never bare `pytest`.
- Do not weaken assertions or add `skip`, `xfail`, silent fallback, fake
  preview, synthetic native evidence, or synthetic usability evidence.
- Validate generated code through an independent Python subprocess using
  compile/import/runtime checks before atomically publishing it.
- A failed build must preserve the last successful generated package and the
  old running preview.
- Run native gates with a real PySide6 window and real GLFW/ModernGL child
  window. Offscreen Qt and screenshots are not substitutes for native
  embedding or interaction.
- Report Structural, Runtime, Native, Performance, and Usability evidence as
  separate classes. Unobserved classes must say `not run`.
- After a phase passes, update only its checkbox and single Evidence block in
  `docs/EDITOR_IMPLEMENTATION_TODO.md` with reproducible commands and results.
- Use project-relative paths and deterministic UTF-8/LF/four-space output.

## Repository baseline checks

Before declaring a phase complete, run its focused gate plus the merge checks
defined in `docs/EDITOR_ARCHITECTURE.md`. Keep heavyweight full-engine tests
separate from the fast editor gate when the roadmap says so.

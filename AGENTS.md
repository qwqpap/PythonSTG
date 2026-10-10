# PySTG Agent Instructions

This file applies to the whole repository.

## Task scope and completion

- Start repository edits with `git status --short` and preserve unrelated work.
  Never modify, stage, revert, or commit `.claude/settings.local.json`.
- Complete authorized implementation, relevant checks, and fixes without pausing
  for routine local edits or reruns. Honor current read-only/planning requests;
  a past read-only task is not a permanent implementation ban.
- Before substantial edits, state the outcome and affected paths. Revise this
  boundary when needed; ask for material scope/product decisions or missing
  authorization. Finish after the result and applicable checks, or report the
  concrete blocker and remaining gates.

## Editor documentation and roadmap

- For editor changes, read the status table, invariant contract, and affected phase in
  [`docs/EDITOR_IMPLEMENTATION_TODO.md`](docs/EDITOR_IMPLEMENTATION_TODO.md).
  It is the only implementation order and status record.
- For module ownership, source persistence, code generation, preview, or
  Timeline changes, read the affected sections of
  [`docs/EDITOR_ARCHITECTURE.md`](docs/EDITOR_ARCHITECTURE.md).
- Read both documents completely for overall architecture/product-contract changes.
  Phase completion needs the full applicable Gate and architecture merge checks;
  wording-only edits need local context.

Follow `CD0 -> CD1 -> CD2 -> CD3 -> CD4`; no later phase starts while an earlier
gate is red. Baseline: `697d9a5`. Historic CD0-CD7 evidence does not prove the
current usability gates. The Scene/Pattern/Graph editor at
`archive/editor-v1-f9e0798` is not a compatibility target; do not restore it
through shims, feature flags, hidden menus, or retained tests.

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
before editing. The coordinating agent alone updates roadmap status. A verifier
who did not implement the task performs the final read-only phase gate. Routine
fixes can proceed within the authorized scope without claiming a phase passed.

## Editing and verification rules

- Use the narrowest relevant tests while iterating and invoke them with
  `python -m pytest`, never bare `pytest`. If PATH resolves to the Windows Store
  shim, use `C:/Users/m1573/anaconda3/python.exe -m pytest` when available.
  Broaden or repeat checks only for new changes, failures, unresolved risks, or
  a required phase/merge gate; do not run the full engine suite for wording edits.
- Do not weaken assertions or add `skip`, `xfail`, silent fallback, fake
  preview, synthetic native evidence, or synthetic usability evidence.
- Validate generated code through an independent Python subprocess using
  compile/import/runtime checks before atomically publishing it.
- A failed build must preserve the last successful generated package and the
  old running preview.
- Run native gates with a real PySide6 window and real GLFW/ModernGL child
  window. Offscreen Qt and screenshots are not substitutes for native
  embedding or interaction. For UI interaction fixes, reproduce the actual
  user input chain; synthetic target events alone can miss source-widget effects.
- For editor gate or usability reports, distinguish Structural, Runtime, Native,
  Performance, and Usability evidence. Unobserved classes say `not run`;
  agent-driven interaction does not count as maintainer/new-user acceptance.
- After a phase passes, update only its checkbox and single Evidence block in
  `docs/EDITOR_IMPLEMENTATION_TODO.md` with reproducible commands and results.
- Use project-relative paths and deterministic UTF-8/LF/four-space output.

## Repository baseline checks

Before declaring a phase complete, run its focused gate plus the merge checks
defined in `docs/EDITOR_ARCHITECTURE.md`. Keep heavyweight full-engine tests
separate from the fast editor gate when the roadmap says so.

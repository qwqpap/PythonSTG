# PySTG Agent Instructions

This file applies to the whole repository.

## Editor roadmap

Before making substantial changes to the Godot-style authoring editor, read
[`docs/EDITOR_IMPLEMENTATION_TODO.md`](docs/EDITOR_IMPLEMENTATION_TODO.md)
completely.

The roadmap is the durable source of truth for:

- implementation order and dependencies;
- editor/runtime architecture boundaries;
- the current milestone and deferred scope;
- completion gates and verification evidence.

Do not begin a later roadmap phase merely because its UI is easier to demo.
Foundation, runtime parity, and preview gates must be completed in dependency
order.

## Working rules

1. Check `git status --short` before editing. Preserve unrelated user changes.
2. For substantial work, propose the intended roadmap task IDs, boundaries, and
   tradeoffs before implementation.
3. Keep authoring documents as the source of truth. Generated Python is an
   optional export and must not become the only runnable representation.
4. Never expand high-density bullets into scene-tree nodes or attach a Python
   per-frame callback to every bullet.
5. Preview results must use the formal runtime path. Label structural tests,
   simulated previews, and visually accepted results separately.
6. All document mutations initiated by editor UI must participate in Undo/Redo.
7. New document schema versions require migration and round-trip tests.
8. Use project-relative resource references and `ProjectContext`; do not add new
   current-working-directory assumptions.
9. Do not mark a roadmap phase complete until its explicit gate passes.
10. After completing roadmap work, update its checkboxes and single Evidence
    block with concise, reproducible results; do not append handoff diaries or
    self-hashing test gates.

## Verification baseline

Use the narrowest relevant tests while iterating. Before declaring a roadmap
gate complete, run the gate-specific checks plus the repository merge checks
listed in `docs/EDITOR_ARCHITECTURE.md`. Qt tests should use an offscreen
platform when no interactive display is available.

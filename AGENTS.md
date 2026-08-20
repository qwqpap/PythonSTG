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

## Architecture remediation hold

N7 is paused.  The mandatory order is now:

```text
N6.3 -> ER0..ER8 -> N6.4 -> N7 -> N8 -> N9
```

The ER tasks are defined in `docs/EDITOR_IMPLEMENTATION_TODO.md`.  Their target
dependency direction, directory layout, and module responsibilities are
defined in `docs/EDITOR_ARCHITECTURE.md`.  No N7 contract or implementation
work may start until every ER task and the independent N6.4 usability gate are
complete.

The ER work is a behavior-preserving architecture remediation.  It must not be
used to redesign the timeline, behavior graph, authoring schemas, renderer, or
runtime, and it must not introduce a second preview or document model.

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

## Agent ownership during ER work

Every implementation task must name one owner, an explicit path allowlist, and
an explicit denylist before editing.  Use the task-specific boundaries in the
roadmap; the default ownership is:

| Agent role | May own | Must not change |
| --- | --- | --- |
| Architecture/specification | `AGENTS.md`, `docs/EDITOR_ARCHITECTURE.md`, `docs/EDITOR_IMPLEMENTATION_TODO.md`, architecture contracts | Product implementation or completion status without verification |
| Editor shell/application | `src/editor/app.py`, `src/editor/shell/`, `src/editor/application/`, `src/editor/state/` | Authoring schema, runtime, renderer, or concrete panel behavior |
| Authoring/compiler | `src/authoring/`, `src/compiler/`, compatibility exports named by the active ER task | Qt widgets, preview host, or runtime implementation |
| Panel | One named module under `src/editor/panels/` and its focused tests | Other panels, coordinator internals, direct document mutation |
| Preview | `src/editor/preview/`, `src/preview/`, focused preview tests | Authoring schema, timeline/graph implementation, or renderer semantics |
| Plugin | `src/editor/plugins/`, plugin SDK adapters, focused plugin tests | Window private state, runtime internals, or unrelated registries |
| Verification | Read-only product inspection, gate commands, and the current task Evidence block | Product fixes, weakened assertions, skips, xfails, or completion claims for a failing gate |

The main coordinating agent owns integration order and is the only agent that
may mark roadmap tasks complete.  The final verifier for an ER task must be
different from its implementation agent.  Two agents must not concurrently
edit the same module or compatibility export.

If work must cross an ownership boundary, stop, report the required files and
reason, and have the coordinating agent revise the task boundary before any
cross-boundary edit.

## Completion integrity

- A file existing, an import succeeding, a checkbox, an offscreen screenshot,
  or one green aggregate number is not completion evidence.
- Contract tests are agreed before implementation.  An implementation agent
  may not weaken them; a contract correction requires an explicit specification
  revision reviewed separately.
- Do not add `skip`, `xfail`, silent fallback, mocked formal preview, direct
  downstream-slot calls presented as UI interaction, or generated reports that
  claim native or human evidence.
- Structural, runtime, native visual, performance, and usability evidence are
  separate classes.  Record only the classes actually observed.
- Run native gates through real PySide6 windows and formal compiler/runtime
  paths.  N6.4 requires the repository usability protocol and five independent
  target users; no agent may synthesize that report.
- A red focused gate blocks the next task.  Near-complete work remains `[ ]`
  with an explicit blocker.

## Verification baseline

Use the narrowest relevant tests while iterating. Before declaring a roadmap
gate complete, run the gate-specific checks plus the repository merge checks
listed in `docs/EDITOR_ARCHITECTURE.md`. Qt tests should use an offscreen
platform when no interactive display is available.

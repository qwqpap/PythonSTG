# PySTG Godot-style Editor Roadmap TODO

> Durable execution plan for agents and maintainers. Read this file before
> substantial editor, authoring-document, preview, UI/background authoring, or
> plugin work.

## Objective

Build a low-threshold STG editor in which a new user can create and preview a
bullet pattern without writing Python, while advanced users can progressively
expand the same resource through curves, a typed behavior graph, scripts,
custom editor extensions, UI/background authoring, and external-event adapters.

The product model is:

```text
Godot-style workbench
    + recipe-first danmaku authoring
    + timeline orchestration
    + formal runtime preview
    + script/plugin escape hatches
```

## Current focus

**Milestone M2 — Controllable formal preview**

Phase 0 contracts are frozen. Keep later changes compatible with them or add
explicit schema migrations and contract tests.

Next recommended task: **E2.1 — Define PreviewController contract.**

## Status and update rules

- `[ ]` means planned or incomplete.
- `[x]` means the task and its acceptance criteria are complete.
- Put `BLOCKED:` after a task only when the blocking condition is concrete.
- Do not mark an entire phase complete from unit tests alone when its gate also
  requires runtime or visual validation.
- When completing a task, add a dated entry to the Completion log with commands,
  tests, artifacts, and known limitations.
- If the design changes, update the decision here before implementing code that
  contradicts it.

## Non-negotiable architecture boundaries

1. **Bullets are not scene nodes.** Scene documents contain semantic entities
   such as Stage, Boss, Spell, Emitter, and PatternInstance. High-density bullet
   state remains in the NumPy/Numba pool.
2. **Documents are the source of truth.** Python generation is an optional
   compatibility/export path. Arbitrary Python is not reverse-parsed into a
   visual graph.
3. **Preview uses the formal runtime.** Approximate Qt-only simulations may be
   used for diagnostics but must be labeled experimental and cannot establish
   visual/runtime parity.
4. **Progressive disclosure uses one resource.** Recipe, curves, graph, and
   ScriptBehavior are increasingly powerful views/extensions of the same
   resource, not independent copies.
5. **Domain editors share infrastructure, not a universal graph.** Danmaku, UI,
   background, scene, and script contexts share documents, resources,
   Inspector, Undo/Redo, timeline, preview, and plugin contracts while retaining
   domain-specific central views.
6. **Per-bullet behavior stays data-oriented.** Compile common motion to pool
   fields, vectorized operations, or Numba-compatible kernels. Python callbacks
   are for sparse controllers/emitters, not every bullet every frame.
7. **External input enters through typed events.** UDP, WebSocket, bots, and
   platform adapters do not directly mutate gameplay subsystems.
8. **No unrestricted `eval`.** Expressions use a small typed/whitelisted AST.

## Audited baseline (2026-08-01 snapshot)

### Reusable foundation

- `src/editor/document.py`: UUIDs, schema version, validation, migration hook.
- `src/editor/storage.py`: project-constrained atomic persistence.
- `src/editor/commands.py` and `scene_commands.py`: basic Undo/Redo commands.
- `src/editor/app.py`: dockable Qt workbench, scene tree, Inspector, 2D view,
  resource drag/drop, Output and read-only Timeline.
- `src/editor/workbench.py`: central, bottom, and external plugin descriptors.
- `src/editor/asset_index.py` and `resource_browser.py`: project resource index,
  thumbnails, JSON sprite/animation subresources.
- `src/devtools/pattern_lab.py`: prototype PatternSpec and deterministic pattern
  parameter generation.
- `src/devtools/spell_preview.py`: pause, step, seek, reset, hot reload, error
  retention, and runtime statistics.
- `src/game/stage/context.py`: high-level content-to-engine API.
- `src/game/bullet/optimized_pool.py`: data-oriented high-density bullet runtime.
- `src/ui/components.py` and `ui_tree.py`: serializable UI tree prototype.
- `src/game/background_render/`: data-driven background loading and live reload.
- `src/game/emoji_danmaku/udp_receiver.py`: first external-input adapter candidate.

### Known gaps and hazards

- Scene documents do not compile or instantiate into the formal stage runtime.
- Timeline is display-only and has no track/clip/keyframe mutation model.
- `PatternSpec` is a development model and code generation is one-way.
- Pattern names are currently constrained as Python identifiers; display names
  and optional code symbols must be separated.
- Editor scene defaults use a 768x896 pixel canvas, runtime logical dimensions
  are 384x448, and content APIs use normalized coordinates. A single coordinate
  contract is required before position authoring expands.
- `classify_file()` currently treats every `*.pystg.json` as a scene rather than
  inspecting its declared resource type.
- The current CommandStack lacks transactions/coalescing for slider drags and
  multi-property edits.
- ResourceService is primarily a texture compatibility service, not yet a typed
  authoring-resource loader/compiler registry.
- Background code contains overlapping Camera/Fog/Layer models that must be
  unified before the editor freezes a public background schema.
- There is no general runtime EventBus; the UDP emoji path is specialized.
- The Qt workbench and resource-browser work was uncommitted in the audited
  snapshot. Always re-check current Git state rather than assuming that remains
  true.
- Declared NumPy/Numba pins and the audited active environment differed. Resolve
  environment parity before performance gates.

### Audited test evidence

The following groups passed in the 2026-08-01 snapshot (55 tests total):

```powershell
python -m pytest -q tests/test_editor_documents.py tests/test_editor_scene_commands.py tests/test_editor_workbench.py tests/test_editor_resource_browser.py
python -m pytest -q tests/test_devtools_pattern_lab.py tests/test_devtools_spell_preview.py tests/test_devtools_hotreload.py
python -m pytest -q tests/test_background_data_driven_parity.py tests/test_project_foundation.py
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q tests/test_editor_app_smoke.py
```

This is historical evidence, not proof that the current checkout still passes.

## Dependency order

```text
Phase 0: contracts
  -> Phase 1: pattern IR/runtime
  -> Phase 2: controllable formal preview
  -> Phase 3: first no-code vertical slice
  -> Phase 4: editable timeline/stage program
  -> Phase 5: graph/expressions/scripts
  -> Phase 6: UI and background contexts
  -> Phase 7: events, plugin SDK, packaging hardening
```

Phases may be researched in parallel, but public data/runtime contracts should
not be implemented out of order.

---

## Phase 0 — Authoring contracts

Goal: freeze the smallest durable document, coordinate, time, identity, and
registry contracts before expanding UI.

### E0.1 Common typed resource envelope

- [x] Define a common resource header with `schema_version`, `type`, UUID `id`,
  Unicode `name`, and optional metadata.
- [x] Define initial resource types: `pystg.scene`, `pystg.pattern`, `pystg.ui`,
  and `pystg.background`.
- [x] Separate human display name, UUID identity, and optional Python
  `symbol_name`.
- [x] Decide whether all typed resources retain `*.pystg.json` or receive
  domain-specific suffixes; document the decision.
- [x] Add round-trip and duplicate-ID validation tests.
- [x] Add explicit migration registration rather than a single hard-coded
  scene migration chain.

Acceptance:

- Every initial resource type can load, validate, save, and reload without
  semantic changes.
- Unicode display names never require a Python identifier.
- Newer unsupported schema versions fail with actionable errors.

### E0.2 Resource references and typed registry

- [x] Formalize `res://project/path#subresource` references.
- [x] Replace the `*.pystg.json == scene` classification shortcut with declared
  type inspection.
- [x] Introduce a ResourceTypeRegistry for loaders, validators, migrations,
  editor factories, compilers, and preview handlers.
- [x] Keep project-boundary checks through `ProjectContext`.
- [x] Add broken-reference and outside-project validation tests.

Acceptance:

- The resource browser distinguishes scene, pattern, UI, and background
  documents and can report invalid resources without aborting the full scan.

### E0.3 Coordinate and time contracts

- [x] Define one logical gameplay coordinate space and document origin, axes,
  bounds, and conversion behavior.
- [x] Add a CoordinateSpace service used by editor gizmos, document loading,
  runtime compilation, and preview.
- [x] Decide document time storage (recommended: integer frames at a declared
  tick rate) and display conversion to seconds/beats.
- [x] Remove new ad-hoc pixel/normalized conversion code.
- [x] Add conversion round-trip and viewport-scaling tests.

Acceptance:

- Dragging an emitter to a known editor position spawns at the same formal
  runtime position across window scales.

### E0.4 Property and node registries

- [x] Replace the single hard-coded NODE_TYPES map with a registry.
- [x] Extend PropertySpec with enum, resource reference, unit, group, range,
  curve/binding capability, conditional visibility, and editor hints.
- [x] Define initial semantic scene types: Stage, Boss, Spell, Emitter, and
  PatternInstance.
- [x] Define valid parent/child constraints and registry-level validation.
- [x] Add registry collision and unknown-type tests.

Acceptance:

- A registered node type can supply its schema, Inspector fields, validation,
  viewport behavior, and runtime compiler without modifying a central switch.

### Phase 0 gate

- [x] All E0 tasks complete.
- [x] Versioned schema and migrations documented.
- [x] Coordinate parity test passes.
- [x] Relevant tests pass in the pinned development environment.
- [x] Architecture review confirms later phases can compile through registries
  without adding type-specific conditionals to the editor shell.

---

## Phase 1 — Pattern IR and formal runtime execution

Goal: make data-authored patterns directly runnable without generating Python.

### E1.1 PatternDocument

- [x] Define recipe-level sections: Bullet, Shape, Aim, Schedule, Motion, and
  Modifiers.
- [x] Support initial shapes: ring, arc, line, spiral, and random distribution.
- [x] Support initial scheduling: delay, interval, burst count, loop.
- [x] Support fixed direction and aim-at-player.
- [x] Support stable random seed configuration.
- [x] Provide migration/import from the prototype PatternSpec.

### E1.2 Pattern compiler

- [x] Implement `PatternDocument -> immutable PatternProgram` compilation.
- [x] Resolve and validate resource references during compilation.
- [x] Precompute static angles, speeds, and resource indices.
- [x] Produce structured diagnostics containing resource ID and property path.
- [x] Cache compiled programs using content/version identity.

### E1.3 Pattern runner

- [x] Implement a fixed-tick PatternRunner that executes PatternProgram through
  StageContext.
- [x] Define start, pause, reset, stop, and deterministic replay semantics.
- [x] Track ownership/tags so a pattern instance can clear or transform only its
  own bullets.
- [x] Add batch spawn APIs to StageContext and OptimizedBulletPool.
- [x] Keep common bullet motion in NumPy/Numba-compatible data paths.

### E1.4 Runtime parity tests

- [x] Compare compiled output against known PatternSpec parameter fixtures.
- [x] Verify identical seeds produce identical spawn traces.
- [x] Verify preview and gameplay runners produce identical traces.
- [x] Add load/compile/run failure tests with actionable diagnostics.
- [x] Add representative dense-burst performance measurements after dependency
  versions are aligned.

### Phase 1 gate

- [x] One PatternDocument runs in the formal game runtime without Python codegen.
- [x] Ring, arc, spiral, aim, interval, multi-burst, and random-seed parity pass.
- [x] Dense patterns do not require scene nodes or per-bullet Python callbacks.
- [x] Runtime and structural tests pass; performance evidence is recorded.

---

## Phase 2 — Controllable formal preview

Goal: turn the existing preview runtime into an editor-controlled service.

### E2.1 PreviewController contract

- [ ] Define load, play, pause, step, seek, reset, stop, set-property,
  set-player-position, set-seed, and get-stats commands.
- [ ] Define structured status, compile error, runtime error, and statistics
  events.
- [ ] Preserve the last valid program when a hot reload fails.
- [ ] Make lifecycle/cleanup idempotent.

### E2.2 Process transport

- [ ] Implement QProcess lifecycle management.
- [ ] Use newline-delimited JSON over stdin/stdout for the first transport.
- [ ] Add protocol version negotiation and request IDs.
- [ ] Ensure child crashes and malformed output cannot freeze the editor.
- [ ] Add protocol and subprocess smoke tests.

### E2.3 Preview surface

- [ ] First integrate controllable external-window formal preview.
- [ ] Show frame, bullet count, update/render timing, seed, pause state, and last
  compile/runtime error in the editor.
- [ ] Add optional diagnostic gizmos without changing formal bullet behavior.
- [ ] Research QOpenGLWidget + ModernGL attachment only after the controller
  contract is stable.
- [ ] Treat full `main.py` embedding as deferred; start with spell/pattern
  preview.

### Phase 2 gate

- [ ] Inspector-driven changes reload a PatternDocument without Python codegen.
- [ ] Pause, step, seek, reset, seed, and player-position control work.
- [ ] Formal preview survives an invalid edit and recovers after correction.
- [ ] Runtime parity and visual preview are both checked and recorded separately.

---

## Phase 3 — First no-code vertical slice

Goal: let a new user create, save, reopen, and formally preview a complete simple
spell without writing Python.

### E3.1 Multi-document editing

- [ ] Replace the single SceneEditorSession assumption with DocumentManager.
- [ ] Give each open document its own savepoint and CommandStack.
- [ ] Add close/save/revert behavior for multiple documents.
- [ ] Preserve resource selections and editor context per document.

### E3.2 Undo transactions

- [ ] Add command transactions for multi-property operations.
- [ ] Coalesce continuous slider/spinbox/gizmo drags into one undo step.
- [ ] Add timeline and resource-assignment command types.
- [ ] Verify Undo/Redo round-trips valid documents.

### E3.3 Contextual Pattern workspace

- [ ] Add Pattern as a first-class central editor context.
- [ ] Provide recipe Inspector controls with units and advanced sections.
- [ ] Add Bullet resource picking and drag/drop.
- [ ] Add emitter gizmo, player target gizmo, and optional trajectory guides.
- [ ] Connect property changes to PreviewController.
- [ ] Provide concise empty states and starter templates.

### E3.4 Scene integration

- [ ] Add Stage -> Boss -> Spell -> Emitter/PatternInstance creation flow.
- [ ] Support Pattern resource instancing rather than copying definitions.
- [ ] Compile the selected simple Spell into a runnable preview program.
- [ ] Provide structured Output messages that link to the failing node/property.

### Phase 3 gate — first product milestone

- [ ] A clean user flow can create a ring pattern, adjust count/speed/interval,
  aim at the player, assign a bullet resource, save, reopen, and formally
  preview it without touching Python.
- [ ] Undo/Redo covers creation, resource assignment, gizmo movement, and
  property editing.
- [ ] Desktop interaction and representative narrow-layout behavior are checked.
- [ ] Structural, runtime, and visual acceptance are recorded separately.

---

## Phase 4 — Editable timeline and StageProgram

Goal: author a 30-60 second spell or stage segment through tracks and clips.

### E4.1 Timeline document model

- [ ] Replace the flat display-only event list with Track, Clip, and Keyframe
  models.
- [ ] Give every track/clip/keyframe a stable UUID.
- [ ] Define start frame, duration, target UUID, channel, ordering, looping,
  interpolation, and payload contracts.
- [ ] Define initial clips: Pattern, Movement, Audio, Event, and Property.
- [ ] Add migration from legacy flat TimelineEvent entries.

### E4.2 Timeline editor

- [ ] Build a QGraphicsScene-based ruler, tracks, clips, playhead, selection, and
  snapping interaction.
- [ ] Add clip creation, movement, resize, duplication, deletion, and Undo/Redo.
- [ ] Connect playhead scrubbing to formal preview seek.
- [ ] Support zoom without changing stored frame values.
- [ ] Add keyboard and focus behavior tests.

### E4.3 StageProgram compiler/runtime

- [ ] Compile Scene + Timeline + referenced resources into StageProgram.
- [ ] Schedule pattern, movement, audio, property, and typed-event clips.
- [ ] Define conflict resolution when multiple clips target the same property.
- [ ] Retain ScriptEvent as an explicit escape hatch.
- [ ] Add deterministic stage trace tests.

### Phase 4 gate

- [ ] A 30-60 second spell can be authored and previewed using scene, pattern,
  movement, audio, and property tracks.
- [ ] Timeline edits support Undo/Redo and survive save/reopen.
- [ ] Scrubbing and normal playback agree at deterministic checkpoints.

---

## Phase 5 — Behavior graph, curves, expressions, scripts

Goal: raise the authoring ceiling without replacing or forking recipe resources.

### E5.1 Curves and bindings

- [ ] Define reusable Curve resources/keyframes and interpolation modes.
- [ ] Allow eligible properties to bind constants, curves, variables, or
  restricted expressions.
- [ ] Provide a small whitelisted expression AST; never unrestricted eval.
- [ ] Initially expose variables such as frame, time, burst index, player/boss
  position, and deterministic random values.
- [ ] Compile expressions with property-path diagnostics.

### E5.2 Typed behavior graph

- [ ] Define stable node categories: Source, Shape, Aim, Schedule, Motion,
  Modifier, Condition, Event, and ScriptBehavior.
- [ ] Define typed ports, connection rules, cycle policy, and graph validation.
- [ ] Compile graphs into the same PatternProgram used by recipe mode.
- [ ] Provide recipe-to-graph expansion without producing a detached copy.
- [ ] Build the graph UI only after compiler tests establish the contract.

### E5.3 ScriptBehavior

- [ ] Define explicit script lifecycle and typed context APIs.
- [ ] Support sparse controller/emitter logic and event hooks.
- [ ] Prevent accidental per-bullet Python update registration by default.
- [ ] Surface import/runtime errors through the same diagnostic protocol.
- [ ] Keep Python export optional and one-way.

### Phase 5 gate

- [ ] The same saved resource progresses from recipe to curves/expressions to
  graph and optional script without format forking.
- [ ] Common graph motion remains on data-oriented runtime paths.
- [ ] Invalid graphs/expressions cannot crash the editor or corrupt the resource.

---

## Phase 6 — UI and background authoring contexts

Goal: reuse the workbench and runtime bridge for specialized UI and background
editing without forcing them into the danmaku graph.

### E6.1 UI document/runtime alignment

- [ ] Add UUIDs, schema version, typed resource header, and migrations to UI
  documents.
- [ ] Add anchors, margins, horizontal/vertical/grid containers, styles/theme
  references, data bindings, and animatable properties.
- [ ] Ensure every supported UI node has formal renderer behavior.
- [ ] Build UI-specific scene tree, canvas gizmos, Inspector, and resource drag.
- [ ] Add viewport-size/responsive preview presets.

### E6.2 Background schema unification

- [ ] Inventory and reconcile duplicate Camera, Fog, Layer, texture, scroll, and
  blend fields.
- [ ] Define one BackgroundDocument consumed by editor and runtime.
- [ ] Add migration/import for existing background JSON files.
- [ ] Build layer list, camera/fog Inspector, transform gizmos, and timeline
  bindings.
- [ ] Reuse formal background reload/render path for preview.

### Phase 6 gate

- [ ] UI and background resources share document, resource, Inspector,
  Undo/Redo, timeline, and preview infrastructure.
- [ ] Existing shipped UI/background resources migrate or import without
  unreviewed visual regressions.
- [ ] Desktop and responsive UI previews receive visual QA.

---

## Phase 7 — Events, plugin SDK, and hardening

Goal: support external integrations and long-term extensibility after the core
contracts have stabilized.

### E7.1 Runtime EventBus

- [ ] Define typed Event with type, source, frame/timestamp, and payload.
- [ ] Provide a main-thread queue and deterministic dispatch order.
- [ ] Add scene/timeline/script subscription and emission APIs.
- [ ] Refactor the emoji UDP path into the first EventAdapter.
- [ ] Add queue limits, malformed-event handling, and shutdown behavior.

### E7.2 External adapter protocol

- [ ] Define adapter lifecycle, configuration, health/status, and event schemas.
- [ ] Prefer out-of-process adapters for network-facing or untrusted code.
- [ ] Add local IPC transport without requiring a general web server.
- [ ] Add example UDP and WebSocket/bot adapters only after the protocol is
  stable.
- [ ] Document security boundaries and non-goals.

### E7.3 Plugin SDK

- [ ] Define plugin manifest/API version.
- [ ] Register resource types, node types, Inspector editors, central/bottom
  views, commands, importers, compilers, preview handlers, and adapters.
- [ ] Define plugin activation/deactivation and failure isolation.
- [ ] Decide project-local plugin discovery and Python package entry points.
- [ ] Add compatibility and duplicate-registration tests.

### E7.4 Product hardening

- [ ] Decide/migrate Qt binding before public distribution; prefer PySide6 for
  an MIT/LGPL-compatible public editor unless a PyQt commercial license exists.
- [ ] Align declared and active dependency versions.
- [ ] Add autosave/recovery without bypassing atomic persistence.
- [ ] Persist safe workspace layout and open-document state.
- [ ] Add crash diagnostics and corrupt-document recovery UX.
- [ ] Add migration fixtures from every released schema version.
- [ ] Establish full structural, runtime, performance, and visual release gates.

### Phase 7 gate

- [ ] External events can drive authored content through typed contracts.
- [ ] A sample plugin can add a resource/node/editor/runtime contribution without
  patching core registries.
- [ ] Packaging, licensing, recovery, migrations, and release QA are documented
  and verified.

---

## Explicitly deferred until their prerequisites pass

- [ ] Full arbitrary Python round-trip parsing — intentionally not planned.
- [ ] Expanding bullets into Scene Tree objects — prohibited by architecture.
- [ ] A universal graph for UI, background, stage, and danmaku — not planned.
- [ ] Embedding the entire `main.py` game loop in Qt before PreviewController is
  stable.
- [ ] Public plugin marketplace before the plugin API/versioning contract is
  stable.
- [ ] Redis, web services, or remote collaboration infrastructure without a
  demonstrated requirement.
- [ ] Binary document packing before JSON size/load measurements justify it.

## Expected module direction

Names are provisional; preserve responsibilities even if paths change.

```text
src/authoring/
  resources.py          common envelope and resource references
  registry.py           resource/node/compiler/preview registries
  migrations.py         version migration routing
  coordinates.py        formal editor/runtime coordinate conversion

src/pattern/
  document.py           PatternDocument
  ir.py                 immutable PatternProgram
  compiler.py           document/graph -> program
  runtime.py            PatternRunner
  expressions.py        restricted expression AST

src/editor/
  document_manager.py   multi-document/savepoint ownership
  preview_controller.py editor-side preview API
  preview_protocol.py   versioned process messages
  contexts/             scene, pattern, timeline, UI, background views

src/game/
  events.py             runtime EventBus
  stage/program.py      StageProgram runtime
```

Avoid creating these modules merely to satisfy the directory sketch. Add them
when their roadmap task begins and a tested responsibility exists.

## Merge and acceptance discipline

For every milestone, report these separately:

1. **Planned:** design/task is documented but not implemented.
2. **Structurally valid:** schema, unit, migration, and contract tests pass.
3. **Runtime valid:** formal runtime/preview behavior matches expected traces.
4. **Performance checked:** representative workload measured in the pinned
   target environment.
5. **Visually accepted:** editor interaction and rendered output were inspected
   locally; structural tests alone do not imply this state.

Minimum repository checks remain defined in `docs/EDITOR_ARCHITECTURE.md`.

## Completion log

Append entries; do not rewrite old evidence. Keep each entry concise.

### 2026-08-01 — Roadmap captured

- Added the durable phased roadmap and root agent entry point.
- Recorded the audited editor/runtime baseline and known architectural gaps.
- No implementation phase was marked complete by this documentation-only step.


### 2026-08-01 — M0 authoring contracts complete

- Froze the `*.pystg.json` typed envelope, four initial resource types, UUID
  identity, Unicode display names, optional `symbol_name`, and explicit v0→v1
  scene migration.
- Added canonical `res://path#fragment` references, project-boundary validation,
  atomic typed-resource storage, declared-type asset classification, and a
  contribution registry for loaders, validators, editors, compilers, previews,
  and migrations.
- Standardized authoring coordinates at 384×448 top-left/Y-down, runtime
  coordinates at center-origin `[-1, 1]`/Y-up, and time at non-negative integer
  frames with a declared tick rate.
- Replaced the hard-coded node map with an extensible registry and registered
  Stage, Boss, Spell, Emitter, and PatternInstance schemas, constraints,
  Inspector metadata, viewport behavior, and compiler contribution slots.
- Structural evidence: 36 M0/editor tests passed in an isolated Python 3.12
  environment with pinned NumPy 2.2.4, Numba 0.63.1, pytest 8.4.1, and PyQt5
  5.15.10; the `touhou_guess` target environment passed the full 103-test suite.
- Repository evidence: `python -m compileall -q main.py src game_content tools`
  passed; asset validation checked 71 JSON files, 745 sprites, and 142 images
  with 0 errors and 0 warnings.
- Visual evidence: a native Qt 1440×900 render was inspected locally; the Scene
  tree, 384×448 canvas, Inspector, and Output/Timeline/Assets tabs were readable
  with no visible layout regression. Mouse automation was not accepted for the
  custom `pythonw.exe`, so interaction acceptance remains test-backed.
- Known reproducibility limitation: a clean full `requirements-dev.txt` install
  could not be completed from the configured Tsinghua mirror because
  `imgui==2.0.0` had no binary wheel and its source build stalled. The existing
  target conda environment was used for the full regression.
- Acceptance classification: M0 is structurally valid and visually inspected.
  Pattern runtime parity and performance remain Phase 1+ work.

### 2026-08-01 — M1 pattern IR and formal runtime complete

- Added strict `PatternDocument` v1 and Draft 2020-12 schema with Bullet, Shape,
  Aim, Schedule, Motion, Modifiers, stable seed, Unicode display identity, and
  direct import from the development `PatternSpec` without Python codegen.
- Added content/dependency-keyed compilation into immutable `PatternProgram`
  templates, alias/direct-fragment resolution, optional sprite-index
  precomputation, bounded compile size, and structured resource/property
  diagnostics.
- Added deterministic fixed-tick `PatternRunner` lifecycle and owner-tag
  isolation, plus vectorized `StageContext`/`OptimizedBulletPool` batch spawn,
  translate, time-scale, and clear paths. Formal batches create no scene nodes
  and install no per-bullet Python callbacks.
- Structural/runtime evidence: 45 focused Pattern/authoring/devtools tests
  passed, and the complete target-environment regression passed (`135 passed`),
  including three consecutive full-suite runs after stabilizing the shared Qt
  application lifetime. Draft
  2020-12 schema validation and `python -m compileall -q main.py src
  game_content tools tests` also passed.
- Parity evidence: ring, arc, spiral, flower compatibility, player/fixed aim,
  interval/multi-burst scheduling, identical-seed replay, and two formal
  preview/game contexts consuming the same runner produced matching traces.
- Performance evidence in `touhou_guess` (Python 3.12.9, NumPy 2.2.4, Numba
  0.63.1): 100 batches × 512 bullets spawned 51,200/51,200 bullets in 0.127511
  seconds (401,534 bullets/second), with 100 observed batch calls and zero
  per-bullet callbacks. This is a recorded representative measurement, not a
  universal frame-time guarantee.
- Repository evidence: asset validation checked 71 JSON files, 745 sprites, and
  142 images with 0 errors and 0 warnings; `git diff --check` passed.
- Visual evidence: M1 adds no editor surface, so no new visual interaction is
  claimed. M2 will put controls and diagnostic overlays around this same formal
  runtime rather than introduce a separate editor-only renderer.
- Acceptance classification: M1 is structurally valid, runtime valid, and
  performance checked; visual acceptance is not applicable to this milestone.
- Final commands run in the `touhou_guess` environment:
  `python -m pytest -q`, `python -m compileall -q main.py src game_content
  tools tests`, `python tools/validate_assets.py --format json`, and
  `python tools/benchmark_pattern_runtime.py`; `git diff --check` also passed.

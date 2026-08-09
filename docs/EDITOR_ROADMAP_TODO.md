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

**M0-M7 and the R5 -> R7 remediation gates are complete in this checkout.**

The current acceptance record below supersedes the earlier handoff entries:
the unchanged frozen gates, original M5-M7 acceptance files, restored full
suite, pinned active dependencies, and native Windows visual evidence all pass.
The historical completion-log entries remain as implementation history. The
items under “Explicitly deferred” remain intentional architecture boundaries,
not incomplete remediation work.

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

### Acceptance-test freeze (applies from M5 onward)

- Each E5 task names a frozen acceptance test file. That file is the completion
  gate: implementation work must make every test in it pass **as written**.
- Modifying, deleting, skipping, xfailing, or relaxing an acceptance test to
  accommodate an implementation is forbidden and invalidates the gate.
- Supplementary tests may be added, but never weaken an existing assertion.
- "Fully green" for a task means: the task's acceptance file passes in the
  pinned environment **and** the full repository suite (`python -m pytest -q`)
  exits 0, with no `skip`/`xfail` hiding a failure and no test-file edits in
  the diff.
- Tests in the frozen acceptance files may reference contracts recorded in the
  "M5 frozen contracts" section below; implement those contracts, do not argue
  them via test edits.

### 2026-08-08 superseding M5-M7 remediation gate

The earlier M5-M7 acceptance files were never committed and therefore cannot
prove that they were frozen before implementation. The following independent
gate supersedes them without deleting them:

- Frozen file: `tests/test_m5_m7_remediation_gate.py`
- M5-M7 remediation gate blob: `7ec6204b9335390fd4b4f1d55e1c39ebd6414cb2`
- The file verifies its own Git-blob hash against this line. Any edit requires
  explicit human approval, a documented reason, a new blob hash, and a new
  dated freeze entry made **before** implementation resumes.
- An implementation agent must not edit this file, this hash, an earlier M5-M7
  acceptance test, or any historical regression test. It must not add skip,
  xfail, conditional collection, platform exclusion, warning suppression, or
  broad exception swallowing to obtain green output.
- A declared feature is unsupported until a behavioral test proves its public
  effect. Storing a field, returning a manifest string, drawing a diagnostic
  approximation, or passing a mocked list through a callback is not runtime or
  integration acceptance.
- Existing behavior may be narrowed only by an explicit schema/API migration.
  Silently ignoring a binding, graph node, plugin contribution, event, or
  malformed document is forbidden.
- The 12 deleted historical test files named by the gate must be restored from
  repository history and pass. Replacing them with weaker tests is forbidden.
- The gate is intentionally non-visual. M6 visual acceptance remains a separate
  manual desktop gate and cannot be inferred from offscreen Qt tests.

Completion requires all evidence below from one unchanged checkout and the
pinned environment:

1. `python -m pytest -q tests/test_m5_m7_remediation_gate.py`
2. Every original M5, M6, and M7 acceptance file, unchanged, passes.
3. `python -m pytest -q` passes with the restored historical tests and no
   skip/xfail hiding failures.
4. `python -m compileall -q main.py src game_content tools tests`,
   `git diff --check`, and `python tools/validate_assets.py` pass.
5. The completion log records Python, NumPy, Numba, Qt binding/version, test
   counts, commands, and known limitations. Checkout-specific evidence must not
   be described as cross-machine acceptance.

### Handoff protocol for the next implementation agent

The next implementation pass (including a high-reasoning/Luna model) is a
code-only remediation pass. The acceptance contract is already frozen; it is
not a request to redesign the tests while implementing the code.

- Work in dependency order only: finish **R5**, run its focused evidence and
  the original M5 files, then finish **R6**, then **R7**. A green later section
  never compensates for a red earlier section.
- Before every batch, record `git status --short`. Preserve unrelated user or
  agent changes. The implementation may change `src/`, `tools/`, schemas,
  dependencies, and fixtures where the R5-R7 contract requires them. Restore
  the historical regression tests verbatim; no existing test file may be
  edited, deleted, or replaced, and the frozen gate may not be weakened.
- The following are prohibited even if they make CI green: editing the gate or
  its hash, changing an expected value to match an approximation, adding
  `skip`/`xfail`, conditional collection or platform exclusions, suppressing
  warnings, monkeypatching away the behavior under test, or swallowing broad
  exceptions. If a public contract is wrong, stop and record an explicit
  schema/API migration decision before changing it.
- Every implementation claim must identify its evidence class: structural
  (schema/unit), runtime (formal runner/adapter trace), performance (measured
  batch workload), or visual (native desktop interaction/render). An offscreen
  Qt assertion is never visual acceptance, and a diagnostic overlay is never a
  gameplay renderer.
- Do not mark a checkbox from an isolated test. For each R5/R6/R7 section,
  record the focused command, the unchanged-gate result, the full-suite result,
  compileall/diff/assets results, environment versions, and remaining limits
  in the Completion log. A failure count is evidence of an open gate, not a
  reason to relax the gate.

### M4 runtime-feedback regression lock

The earlier M4 runtime observations are part of the accepted foundation and
must remain true while R5-R7 changes land. These tests are regression locks,
not permission to reintroduce a second preview renderer:

- `tests/test_editor_timeline_workspace.py` must prove that authoritative
  statistics frames drive the owner scene's playhead, active clips, and
  read-only Boss/Emitter runtime poses; another open tab must not consume that
  feedback or become dirty.
- `tests/test_preview_controller.py`, `tests/test_preview_process.py`,
  `tests/test_editor_app_smoke.py`, and `tests/test_editor_m4_integration.py`
  must continue to prove that playback uses the formal fixed-tick runtime and
  that the Qt host launches/embeds the native GLFW/ModernGL preview process.
  The Qt canvas may show authored geometry and runtime pose overlays only; it
  must not simulate dense bullets with QPainter or duplicate bullets as scene
  nodes.
- The M4 runtime regression command is
  `python -m pytest -q tests/test_editor_timeline_workspace.py tests/test_preview_controller.py tests/test_preview_process.py tests/test_editor_app_smoke.py tests/test_editor_m4_integration.py`.
  Passing this command establishes structural/runtime regression evidence; a
  native Windows run at the supported desktop sizes is still required for the
  separate visual gate.

The five M4 regression files are also blob-frozen by the superseding gate:

```text
tests/test_editor_timeline_workspace.py  504a14b2c428e01305866eacd5dee0ed6e26649d
tests/test_preview_controller.py         ede68ed7364dd720066962b9d96ad550891b8015
tests/test_preview_process.py            05b006fdfb0c7f6ff84c893e0a78cec22a78b2cd
tests/test_editor_app_smoke.py           24f669caf0b0c75c7d14c479764b7316d72a8112
tests/test_editor_m4_integration.py     eb7aa03addf40cb3edab049d03997d124d6e350a
```

The M4 user-visible addendum is also blob-frozen:

- File: `tests/test_m4_runtime_preview_contract.py`
- M4 runtime preview contract blob: `b97ac1f1e78a8814fa26f14dd4053c7a69f1e89b`
- It may not be edited, skipped, or weakened during implementation. Any
  contract change requires explicit approval, a new blob hash, and a new
  freeze-log entry before code changes resume.

### M4 issue-to-acceptance contract (user-visible behavior)

The following observations are explicit product contracts, not implementation
preferences. A remediation is accepted only when the named regression tests
and the formal runtime trace demonstrate the behavior. A screenshot of a
diagnostic canvas, a mocked preview client, or a static field is not evidence.

- **M4-P1 — two-window/render ownership:** the Qt workbench is the authoring
  host. Dense danmaku is rendered by the formal preview process through the
  game's `StageRunner -> PatternRunner -> StageContext -> OptimizedBulletPool`
  path and its GLFW/ModernGL renderer. The editor's Qt canvas may render
  authored nodes, gizmos, and read-only runtime-pose overlays, but it must not
  draw gameplay bullets with `QPainter`, create one scene item per bullet, or
  claim that an empty editor canvas means the preview is not running. On
  Windows, the native formal window may be re-parented into the `Runtime
  Preview` tab; when embedding is unavailable, the same process/window remains
  an explicitly labelled external fallback. These are two surfaces over one
  runtime, not two independent renderers.
- **M4-P2 — authoritative frame feedback:** after every fixed runtime tick and
  control command, one complete statistics snapshot is emitted. The scene that
  launched the preview owns the frame, active-clip, Boss, and Emitter feedback.
  Another open tab must not consume it, become dirty, or move its playhead.
  Runtime poses are read-only overlays; stopping, crashing, or switching the
  preview clears them and restores authored positions.
- **M4-P3 — timeline synchronization:** normal play, pause, step, seek,
  reset, hot reload, and stop must converge on the same integer frame without
  a seek/statistics feedback loop. A timeline scrub sends a formal `seek`; a
  runtime statistics frame updates the owner playhead directly. The active
  clip set and displayed seconds must be derived from that same frame.
- **M4-P4 — moving semantic nodes:** a Movement clip or authored runtime action
  must change the Boss/Emitter pose in the formal `StageRunner` state and in
  the owner viewport overlay. A static Qt authoring pose while the formal
  runtime moves is a failure; writing the runtime pose back into the document
  or savepoint is also a failure.
- **M4-P5 — capacity versus sample content:** `max_bullets` is a process/pool
  capacity argument, not a product limit and not a hard-coded `600`. A sample
  scene may happen to report 600 active bullets, but acceptance must prove that
  a larger configured capacity is forwarded to the formal worker and that the
  runtime remains data-oriented. Never "fix" the sample by adding a Qt bullet
  renderer or by changing the expected sample count without a resource/runtime
  contract decision.
- **M4-P6 — evidence separation:** the five-file M4 command below is
  structural/runtime regression evidence. Native Windows runs at the supported
  desktop sizes must separately verify the actual embedded/external window,
  readable two-surface layout, playhead movement, and moving Boss/Emitter
  overlay. Offscreen Qt tests cannot close that visual gate.

#### Observed-issue lock map

Use this map when triaging a red test.  A Luna implementation is not accepted
by a screenshot or by a passing surrogate test: the named test must pass and
the required evidence class must be recorded.

| Observation | Frozen behavioral proof | Additional acceptance required |
| --- | --- | --- |
| Boss/Emitter moves in the game but is static in Qt | `test_stage_runtime_feedback_moves_boss_in_owner_viewport_while_other_tab_is_active`, `test_scene_viewport_runtime_pose_is_read_only_and_restores_authoring_position` | Native Windows run shows the overlay moving while the authored document remains unchanged |
| Qt preview does not show the main danmaku | `test_formal_preview_host_is_a_foreign_window_container_not_a_qt_renderer`, `test_scene_with_tracks_launches_formal_stage_preview`, `test_qprocess_headless_worker_loads_and_steps_stage_program` | Native run confirms the embedded or labelled external GLFW/ModernGL surface is visible; an empty authoring canvas is not a failure |
| Timeline playhead lags or is not synchronized | `test_runtime_statistics_drive_playhead_active_clip_and_pose_without_seek_or_dirty`, `test_stage_preview_feedback_is_owned_by_loaded_scene_and_does_not_cross_tabs`, `test_scrubbing_seeks_preview_and_zoom_does_not_mutate_frames` | Native run confirms play, pause, step, seek, reset, and stop visibly converge on one frame |
| Two windows are mistaken for two renderers | `test_formal_preview_host_is_a_foreign_window_container_not_a_qt_renderer`, `test_m4_contract_is_present_in_roadmap_and_keeps_visual_gate_separate` | Native run records whether the same formal process is embedded or explicitly labelled external |
| `max_bullets` appears fixed at 600 | `test_formal_worker_forwards_capacity_above_sample_bullet_count` | A configured capacity above 600 is shown in the formal worker stats without a Qt bullet fallback |
| UI edits bypass the document/Undo path | `test_ui_canvas_gizmo_commits_geometry_back_to_document`, `test_ui_node_edits_undo_redo_through_the_window`, `test_ui_document_opens_edits_undo_redo_and_reopens` | Native run checks selectable/movable/resizable interaction and responsive presets |

Hard failures for M4 are therefore: a second Qt gameplay renderer, per-bullet
scene objects/callbacks, a static Boss/Emitter pose, a stale or cross-tab
playhead, an editor document dirtied by runtime feedback, an unexplained
`600` capacity ceiling, or a visual claim based only on mocked/offscreen data.

### Frozen acceptance matrix for the handoff

The following is the only completion matrix an implementation agent may use;
green unit tests outside this matrix do not close a task.

| Scope | Required evidence | Hard failure condition |
| --- | --- | --- |
| R5 | The R5 assertions in `tests/test_m5_m7_remediation_gate.py`, all original M5 files, and the data-oriented/static boundary tests | Any binding is ignored, graph/script error leaks a builtin exception, or a dense path adds per-bullet callbacks/nodes |
| R6 | The R6 assertions in the same frozen file, all original M6 files, renderer-parity tests, and a native desktop/responsive run | Qt-only geometry/diagnostic drawing is presented as gameplay rendering, or UI/background edits bypass Undo/Redo |
| R7 | The R7 assertions in the same frozen file, all original M7 files, recovery/dependency checks, and the full suite | Adapter/plugin declarations do not produce an observable runtime effect, sidecar/layout validation mutates state, or any test is skipped/xfail-ed |
| M4 lock | The five-file command above, `tests/test_m4_runtime_preview_contract.py`, the M4-P1..P6 contract, and a native desktop run | Timeline feedback goes to the wrong document, Boss/Emitter runtime poses stay static, the editor presents a second Qt bullet renderer, or `600` is treated as a hard capacity limit |

The self-hashing test file is immutable during implementation. A proposed test
change requires human approval, a new Git-blob hash in this document, a new
freeze entry, and a fresh red/green baseline **before** code changes resume.
The implementation agent must report structural, runtime, performance, and
visual evidence separately; no category substitutes for another.

### 2026-08-08 Luna handoff acceptance bundle (frozen before implementation)

The next implementation pass is governed by one additional, self-checking
behavioral bundle.  It was written after the M4 issue review and the follow-up
M6 audit; it is not a suggestion to replace the older gates.

- Frozen file: `tests/test_luna_acceptance_bundle.py`
- Luna acceptance bundle blob: `9f3a5f7367178a21e28c02cc9bdd27fe259802f1`
- The first test computes the Git blob hash and requires this exact marker.
  Any edit, deletion, `skip`, `xfail`, platform exclusion, assertion
  relaxation, or broad exception swallowing invalidates the handoff and
  requires explicit human approval, a new blob marker, and a new red baseline
  recorded here before implementation resumes.
- The bundle must pass unchanged together with the superseding M5-M7 gate,
  the five M4 regression files, the M4 runtime addendum, the original M5/M6/M7
  files, and the full repository suite.  A green surrogate or source-only
  check never compensates for a red behavioral assertion.

The bundle's required observable contracts are:

1. **Formal runtime ownership and feedback.** A real headless
   `PatternPreviewProcess` loads a `SceneDocument`, advances the formal
   `StageRunner`, and emits a frame/active-clip/node-state snapshot.  Feeding
   that snapshot to the owner `EditorMainWindow` moves the read-only Boss/
   Emitter overlay and the same integer timeline frame, leaves the authored
   document/savepoint clean, and clears the overlay on stop.  The test must
   not substitute a Qt bullet simulation or a mocked runtime trace.
2. **One gameplay renderer.** `RuntimePreviewHost` remains a foreign-window
   container for the separate GLFW/ModernGL worker.  `QPainter`, one-scene-item-
   per-bullet rendering, and a second Qt gameplay renderer are forbidden.
3. **UI authoring closure.** Canvas corner resize, scene-tree add/delete,
   resource drop, and Inspector/property edits must commit through the shared
   command stack and survive Undo/Redo.  The formal UI preview handler must
   invoke the renderer protocol and produce the same layout records as the
   compiler at the requested viewport.
4. **Background authoring closure.** A layer gizmo must report x/y, scale, and
   rotation changes; the window must commit all four values through an
   undoable command.  A frame/time binding must be visible in the workspace,
   undoable, and change formal `DataDrivenBackground` quads without mutating
   the source document.  A stored binding that has no renderer-visible effect
   is not an implementation.
5. **Lifecycle cleanup.** Closing `EditorMainWindow` must call
   `plugin_sdk_registry.deactivate_all()` after stopping owned processes so
   plugin resources cannot outlive the editor.

The named assertions are the contract map (all are required, not examples):

| Contract | Required test |
| --- | --- |
| Bundle immutability | `test_luna_acceptance_bundle_blob_matches_roadmap` |
| Formal runtime -> owner pose/timeline | `test_formal_stage_trace_moves_owner_overlay_and_timeline` |
| Foreign formal renderer boundary | `test_formal_preview_host_is_foreign_window_only` |
| UI resize | `test_ui_canvas_resize_is_a_geometry_commit` |
| UI tree/drop history | `test_ui_window_mutation_resource_drop_and_undo_redo` |
| Formal UI renderer | `test_ui_formal_preview_delegates_to_renderer` |
| Background gizmo components | `test_background_canvas_gizmo_reports_move_scale_and_rotation` |
| Background command history | `test_background_transform_command_undo_redo_preserves_all_components` |
| Background binding/runtime parity | `test_background_binding_is_undoable_and_changes_formal_quads` |
| Plugin shutdown | `test_editor_close_deactivates_sdk_plugins` |

The focused handoff command is:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_luna_acceptance_bundle.py
```

The full acceptance command is:

```powershell
python -m pytest -q tests/test_luna_acceptance_bundle.py tests/test_m5_m7_remediation_gate.py tests/test_m4_runtime_preview_contract.py
python -m pytest -q
python -m compileall -q main.py src game_content tools tests
git diff --check
python tools/validate_assets.py
```

The bundle is structural/runtime evidence only.  It does not close the native
Windows visual gate: a supported desktop run must still show the actual
embedded or explicitly labelled external formal window, readable two-surface
layout, moving runtime overlay, synchronized playhead, responsive UI presets,
and clean shutdown.  Do not mark R5, R6, R7, or the M4 visual gate complete
until those evidence classes are recorded separately.

### R5 - M5 correctness remediation

- [x] **R5.1 Expression boundary:** validate function arity at compile time;
      constant-fold safe numeric subtrees; convert syntax, domain, overflow,
      malformed compiled-node, and non-finite failures to `ExpressionError`;
      make compiled expressions JSON round-trip without accepting executable
      objects or unrestricted evaluation.
- [x] **R5.2 Binding truthfulness:** validate dotted targets and reject duplicate
      targets with `duplicate_binding_target`; every entry in
      `BINDABLE_TARGETS` must have observable constant-binding parity with the
      same direct property, and eligible dynamic bindings must evaluate at the
      documented emission/frame boundary. Unsupported targets must be removed
      through an explicit contract migration, never silently ignored.
- [x] **R5.3 Data-oriented runtime:** dynamic count/geometry/schedule/motion and
      modifier values must remain batch operations. No per-bullet Python
      callbacks, scene nodes, emitter callback lists, or death handlers may be
      introduced to make the matrix pass.
- [x] **R5.4 Graph equivalence:** recipe -> graph -> save/reload -> compile must
      preserve every binding and yield a field-equal `PatternProgram`. Validate
      UUIDs, node/category pairs, finite positions, JSON-safe immutable
      properties, actual port names, duplicate IDs/edges, fan-in/fan-out,
      cycles, required-chain reachability, and orphan semantic nodes.
- [x] **R5.5 Stable editor history:** graph Add/Remove/Move/Connect commands must
      preserve the same node/edge UUID across Undo/Redo and failed validation
      rollback. Command history may not repair documents by generating new IDs.
- [x] **R5.6 Script lifecycle:** module import and every hook error use structured
      `PatternCompileError`/`PatternRuntimeError`; paused/stopped runners never
      update scripts; repeated start is idempotent; stop-hook failure still
      clears owned state and leaves a stopped runner; `load` has one documented
      host lifetime and top-level import failures are compilation failures.
- [x] **R5 gate:** the R5 section of the superseding gate, all original M5 tests,
      the full restored suite, compileall, and diff-check pass. No M6/M7
      implementation is accepted as compensation for a red R5 gate.

### R6 - M6 authoring/runtime remediation

- [x] **R6.1 UI validation:** validate the typed header, UUIDs, tree ownership,
      cycles, anchors/margins shape and finiteness, non-negative geometry,
      colors, style `res://` references, binding target names/types, and all
      renderer fields. All failures use `UICompileError` diagnostics.
- [x] **R6.2 UI binding parity:** evaluate bound geometry before layout;
      `get_render_elements` accepts the requested viewport and produces the same
      geometry used by the responsive editor preset. Binding errors may not
      leak builtin exceptions. Animatable declarations must correspond to
      properties that actually change formal renderer output.
- [x] **R6.3 UI editor:** provide selectable/movable/resizable canvas items,
      resource drop, scene-tree mutation, Inspector mutation, and Undo/Redo
      through commands. Offscreen interaction tests establish structure only;
      they do not close the manual visual gate.
- [x] **R6.4 Background validation/editor:** validate finite camera/fog/scroll,
      layer types/ranges, texture references and variants; provide editable
      layer/camera/fog/transform commands with Undo/Redo, transform gizmos, and
      timeline bindings. A read-only layer summary is not completion.
- [x] **R6.5 Formal contributions:** UI/background registry specs provide real
      editor factories, compilers, and preview handlers. Formal UI/background
      previews consume the same compiled payload/render path as gameplay;
      QPainter outlines are diagnostic overlays only.
- [x] **R6 gate:** the R6 section of the superseding gate, original M6 tests,
      full restored suite, runtime parity, and manual desktop/responsive visual
      evidence pass separately. Do not mark this from offscreen tests alone.

### R7 - M7 integration and product-hardening remediation

- [x] **R7.1 Typed thread-safe events:** validate Event type/source/frame and
      recursively JSON-compatible payloads; validate subscription names; guard
      queue/frame/pending/close with a documented thread boundary; preserve FIFO
      and exception isolation under concurrent adapter emission.
- [x] **R7.2 Authored routing:** a real adapter event must route through EventBus
      into an authored Stage/Pattern action with schema validation. Appending a
      payload to a test list is not scene/runtime acceptance.
- [x] **R7.3 Adapter lifecycle:** bind failure reports unhealthy with detail;
      stop closes the socket, joins its thread, clears the bus, and is
      idempotent; a closed bus cannot produce an unhandled thread exception.
      Deliver a real local IPC adapter and a WebSocket/bot example after the
      common lifecycle passes. `LoopbackAdapter` alone is not IPC.
- [x] **R7.4 Real plugin SDK:** plugin manifests are deeply immutable and
      validated. Activation receives a constrained registration context and
      must install real resource/node/Inspector/command/compiler/preview/adapter
      contributions into the registries used by `EditorMainWindow`. Activation
      is transactional; failure rolls back partial contributions. Deactivation
      invokes cleanup and unregisters owned contributions. String lists alone
      are declarations, not contributions.
- [x] **R7.5 Recovery integration:** malformed JSON becomes a structured error
      with path/location and never changes the source; autosave is connected to
      dirty document sessions, recovery candidates are surfaced without
      overwriting originals, and sidecar identity/type is checked. Layout files
      are versioned, validated, project-relative, bounded, and reject malformed
      path arrays.
- [x] **R7.6 Distribution gate:** restore historical tests; run acceptance in the
      exact declared Python/NumPy/Numba environment; migrate public editor tools
      to PySide6 or record evidence of a valid PyQt commercial-license decision.
      The MIT project may not be declared distribution-ready while this remains
      unresolved.
- [x] **R7 gate:** the R7 section of the superseding gate, all original M7 tests,
      restored full suite, packaging/license/recovery checks, and separately
      recorded release QA pass from one unchanged checkout.

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

- [x] Define load, play, pause, step, seek, reset, stop, set-property,
  set-player-position, set-seed, and get-stats commands.
- [x] Define structured status, compile error, runtime error, and statistics
  events.
- [x] Preserve the last valid program when a hot reload fails.
- [x] Make lifecycle/cleanup idempotent.

### E2.2 Process transport

- [x] Implement QProcess lifecycle management.
- [x] Use newline-delimited JSON over stdin/stdout for the first transport.
- [x] Add protocol version negotiation and request IDs.
- [x] Ensure child crashes and malformed output cannot freeze the editor.
- [x] Add protocol and subprocess smoke tests.

### E2.3 Preview surface

- [x] First integrate controllable external-window formal preview.
- [x] Show frame, bullet count, update/render timing, seed, pause state, and last
  compile/runtime error in the editor.
- [x] Add optional diagnostic gizmos without changing formal bullet behavior.
- [x] Record QOpenGLWidget + ModernGL attachment research as deferred until the
  controller contract is stable.
- [x] Treat full `main.py` embedding as deferred; start with spell/pattern
  preview.

### Phase 2 gate

- [x] Inspector-driven changes reload a PatternDocument without Python codegen.
- [x] Pause, step, seek, reset, seed, and player-position control work.
- [x] Formal preview survives an invalid edit and recovers after correction.
- [x] Runtime parity and visual preview are both checked and recorded separately.

---

## Phase 3 — First no-code vertical slice

Goal: let a new user create, save, reopen, and formally preview a complete simple
spell without writing Python.

### E3.1 Multi-document editing

- [x] Replace the single SceneEditorSession assumption with DocumentManager.
- [x] Give each open document its own savepoint and CommandStack.
- [x] Add close/save/revert behavior for multiple documents.
- [x] Preserve resource selections and editor context per document.

### E3.2 Undo transactions

- [x] Add command transactions for multi-property operations.
- [x] Coalesce continuous slider/spinbox/gizmo drags into one undo step.
- [x] Add timeline and resource-assignment command types.
- [x] Verify Undo/Redo round-trips valid documents.

### E3.3 Contextual Pattern workspace

- [x] Add Pattern as a first-class central editor context.
- [x] Provide recipe Inspector controls with units and advanced sections.
- [x] Add Bullet resource picking and drag/drop.
- [x] Add emitter gizmo, player target gizmo, and optional trajectory guides.
- [x] Connect property changes to PreviewController.
- [x] Provide concise empty states and starter templates.

### E3.4 Scene integration

- [x] Add Stage -> Boss -> Spell -> Emitter/PatternInstance creation flow.
- [x] Support Pattern resource instancing rather than copying definitions.
- [x] Compile the selected simple Spell into a runnable preview program.
- [x] Provide structured Output messages that link to the failing node/property.

### Phase 3 gate — first product milestone

- [x] A clean user flow can create a ring pattern, adjust count/speed/interval,
  aim at the player, assign a bullet resource, save, reopen, and formally
  preview it without touching Python.
- [x] Undo/Redo covers creation, resource assignment, gizmo movement, and
  property editing.
- [x] Desktop interaction and representative narrow-layout behavior are checked.
- [x] Structural, runtime, and visual acceptance are recorded separately.

---

## Phase 4 — Editable timeline and StageProgram

Goal: author a 30-60 second spell or stage segment through tracks and clips.

### E4.1 Timeline document model

- [x] Replace the flat display-only event list with Track, Clip, and Keyframe
  models.
- [x] Give every track/clip/keyframe a stable UUID.
- [x] Define start frame, duration, target UUID, channel, ordering, looping,
  interpolation, and payload contracts.
- [x] Define initial clips: Pattern, Movement, Audio, Event, and Property.
- [x] Add migration from legacy flat TimelineEvent entries.

### E4.2 Timeline editor

- [x] Build a QGraphicsScene-based ruler, tracks, clips, playhead, selection, and
  snapping interaction.
- [x] Add clip creation, movement, resize, duplication, deletion, and Undo/Redo.
- [x] Connect playhead scrubbing to formal preview seek.
- [x] Support zoom without changing stored frame values.
- [x] Add keyboard and focus behavior tests.

### E4.3 StageProgram compiler/runtime

- [x] Compile Scene + Timeline + referenced resources into StageProgram.
- [x] Schedule pattern, movement, audio, property, and typed-event clips.
- [x] Define conflict resolution when multiple clips target the same property.
- [x] Retain ScriptEvent as an explicit escape hatch.
- [x] Add deterministic stage trace tests.

### Phase 4 gate

- [x] A 30-60 second spell can be authored and previewed using scene, pattern,
  movement, audio, and property tracks.
- [x] Timeline edits support Undo/Redo and survive save/reopen.
- [x] Scrubbing and normal playback agree at deterministic checkpoints.

---

## Phase 5 — Behavior graph, curves, expressions, scripts

Goal: raise the authoring ceiling without replacing or forking recipe resources.

### M5 frozen contracts

These contracts are fixed by the frozen acceptance tests. Implement them
exactly; the tests assert them literally.

- **Expression variables** (`src/pattern/expressions.py`):
  `EXPRESSION_VARIABLES` must be exactly `{"frame", "time", "burst_index",
  "player_x", "player_y", "boss_x", "boss_y", "random"}`. `random` draws from a
  deterministic RNG provided by the evaluation context (`context["rng"]`),
  never from global state.
- **Expression whitelist**: numeric literals, `+ - * / // % **`, unary minus,
  comparisons, `min` / `max` / `abs` / `clamp`, and conditional expressions.
  Rejected: any other function call, attribute access, subscription,
  lambda, import, and `eval` / `exec` anywhere in the compiler. Non-finite
  results (e.g. division by zero) are rejected at compile time. All errors
  surface as `ExpressionError` with `path` and `message`.
- **Curves** (`src/pattern/curves.py`, resource type `pystg.curve`):
  `CurveKeyframe(frame: int, value: float)` with strictly increasing frames;
  interpolation one of `step` / `linear` / `cubic`. `evaluate(frame)` returns
  `default` below the first keyframe and the last keyframe's value beyond it.
  `cubic` means uniform Catmull-Rom with the first/last keyframe repeated as
  the outer control point.
- **Bindings** (`BindingSpec`, stored as `PatternDocument.bindings`): fields
  `path` (dotted property path), `kind` in `constant` / `curve` /
  `variable` / `expression`, `value`. Curves are referenced as
  `res://...#...` resources. Compiled bindings live in `PatternProgram` as
  data (no callables); runtime evaluation happens per emission/frame on the
  data-oriented path (no per-bullet Python callbacks). Legacy documents
  without a `bindings` field must still load.
- **Graph node categories** (`src/pattern/graph.py`): exactly
  `{"source", "shape", "aim", "schedule", "motion", "modifier", "condition",
  "event", "script"}`. Typed single-input/single-output ports with the
  following input/output types:
  `source: None/"source"`, `shape: "source"/"geometry"`,
  `aim: "geometry"/"aim"`, `schedule: "aim"/"schedule"`,
  `motion: "schedule"/"motion"`, `modifier: "motion"/"motion"`,
  `condition: "event"/"condition"`, `event: None/"event"`,
  `script: None/"script"`.
- **Graph compilation**: graphs compile through the same
  `PatternCompiler`/`compile_pattern` entry as recipes; a graph expanded from
  a recipe must produce a `PatternProgram` that is **field-for-field equal**
  to the recipe's program (same `content_hash`, same templates, same motion
  data) for the same document. `BehaviorGraph.from_recipe(document)` must be a
  read-only derivation of the same resource (never a second document) and
  `document.graph = graph; to_dict()/from_dict()` must round-trip.
  `BehaviorGraph` API: `add_node(category, node_type, name=None,
  properties=None)`, `add_edge(from_id, to_id)`, `update_node(node_id,
  **properties)`, immutable `nodes`/`edges`. Graph mode represents a recipe's
  bindings inside the graph (the expanded graph and the recipe compile
  field-equal programs for the same resource). The `motion` node exposes
  `speed` (float) and optional `speed_expression` (string) properties;
  invalid expressions inside graph nodes report diagnostics whose path names
  the property.
- **ScriptBehavior** (`src/pattern/script.py`, stored as
  `PatternDocument.script`): resource URI pointing at a Python module with
  hooks `load(ctx)` / `start(ctx)` / `update(ctx, frame)` / `on_event(ctx,
  event_type, data)` / `stop(ctx)`. `update` runs at most once per tick.
  `ScriptContext` offers typed helpers (`emit_event`, `get_player_position`)
  and rejects per-bullet update registration by default. Script import and
  runtime errors surface through `PatternCompileError` / `PatternRuntimeError`
  diagnostics. Exported Python stays optional and one-way; documents never
  contain script source text.

### E5.1 Curves and bindings

- [x] Define reusable Curve resources/keyframes and interpolation modes.
- [x] Allow eligible properties to bind constants, curves, variables, or
      restricted expressions.
- [x] Provide a small whitelisted expression AST; never unrestricted eval.
- [x] Initially expose variables such as frame, time, burst index, player/boss
      position, and deterministic random values.
- [x] Compile expressions with property-path diagnostics.

Acceptance (frozen): `tests/test_curve_resources.py` and
`tests/test_pattern_expressions.py` must pass exactly as written. Red state
(collected but failing) is expected until the contracts above exist.

### E5.2 Typed behavior graph

- [x] Define stable node categories: Source, Shape, Aim, Schedule, Motion,
      Modifier, Condition, Event, and ScriptBehavior.
- [x] Define typed ports, connection rules, cycle policy, and graph validation.
- [x] Compile graphs into the same PatternProgram used by recipe mode.
- [x] Provide recipe-to-graph expansion without producing a detached copy.
- [x] Build the graph UI only after compiler tests establish the contract.
Acceptance (frozen): `tests/test_pattern_graph.py` must pass exactly as
written. Graph UI work may begin only after that file is green; the graph
workspace must at minimum open, save, and reopen a graph-mode pattern
document and surface compile diagnostics (covered in
`tests/test_editor_m5_integration.py`).

### E5.3 ScriptBehavior

- [x] Define explicit script lifecycle and typed context APIs.
- [x] Support sparse controller/emitter logic and event hooks.
- [x] Prevent accidental per-bullet Python update registration by default.
- [x] Surface import/runtime errors through the same diagnostic protocol.
- [x] Keep Python export optional and one-way.

Acceptance (frozen): `tests/test_script_behavior.py` must pass exactly as
written.

### Phase 5 gate

- [x] The same saved resource progresses from recipe to curves/expressions to
      graph and optional script without format forking.
- [x] Common graph motion remains on data-oriented runtime paths.
- [x] Invalid graphs/expressions cannot crash the editor or corrupt the resource.

Acceptance (frozen): `tests/test_editor_m5_integration.py` must pass exactly
as written, together with the static boundary checks appended to
`tests/test_architecture_contracts.py`. The full repository suite must exit 0
with no test-file edits, no `skip`, and no `xfail`.

---
## Phase 6 — UI and background authoring contexts

Goal: reuse the workbench and runtime bridge for specialized UI and background
editing without forcing them into the danmaku graph.

### M6 frozen contracts

These contracts are fixed by the frozen acceptance tests. Implement them
exactly; the tests assert them literally.

**UI documents** (`src/ui/document.py`, resource type `pystg.ui`):

- `UIDocument` carries the typed envelope (schema_version/type/id/name) plus
  a `root` UI tree. Node types: `node`, `text`, `rect`, `bar`, `image`,
  `panel`, `container_h`, `container_v`, `container_grid`. Every node has a
  stable UUID `id`, `name`, `x`/`y`/`width`/`height`, `visible`, bool
  `anchors` (left/right/top/bottom, defaults True/False/True/False),
  `margins` (left/right/top/bottom, defaults 0), optional `style` (res://
  theme reference), `bindings` (property -> restricted expression string,
  reusing the M5 expression whitelist), and `animatable` (bool).
- Layout: `UIDocument.calculate_layout(viewport_width, viewport_height)`
  returns `{node_id: (x, y, width, height)}` in absolute viewport
  coordinates, computed depth-first. Default (left+top anchors): position is
  parent content origin + (x + margin_left, y + margin_top). Right anchor
  without left: `x = parent_width - width - margin_right`. Bottom anchor
  without top: `y = parent_height - height - margin_bottom`. Left+right:
  stretch, `width = parent_width - margin_left - margin_right`. Top+bottom:
  stretch height. Containers lay out children inside their content rect
  (parent rect shrunk by `padding`): `container_h` places children left to
  right with `gap`; `container_v` top to bottom with `gap`; `container_grid`
  fills rows with a fixed `columns`, `gap`, and a shared row height.
- Rendering: `UIDocument.get_render_elements()` emits the formal renderer
  protocol consumed by `UIRenderer.render_hud` — `text`, `rect`, `bar`, and
  `textured_rect` records with absolute positions from the computed layout.
  `text`/`rect`/`bar`/`panel`/`container_*` map as in the existing
  `UITree.get_render_list`; `image` maps to `textured_rect` with its
  `texture` as the texture path. Binding expressions are evaluated with a
  context containing `frame`, `time`, and the document variable `value`;
  invalid expressions raise a structured `UICompileError` diagnostic.
- Migration: legacy UINode trees serialized without a typed header load
  through `UIDocument.from_dict` with an auto-generated header (UUID/schema
  version/type preserved on round-trip).

**Background documents** (`src/game/background_render/document.py`,
resource type `pystg.background`):

- `BackgroundDocument` carries the typed envelope plus exactly the existing
  shipped fields — `name`, `description`, `textures`, `camera`, `fog`,
  `scroll`, `layers` — with no duplicate or renamed camera/fog/layer fields.
- `BackgroundDocument.from_legacy(payload)` imports a legacy JSON file
  (no header) by generating the envelope; round-tripping the document must
  produce the same render output as loading the legacy JSON directly.
- `DataDrivenBackground.load_from_dict(document.to_dict(), ...)` must produce
  field-identical render quads to loading the original legacy JSON (header
  fields are ignored by the runtime loader).
- Every shipped `assets/images/background/*.json` file must import through
  `from_legacy` and keep its quads identical.

### E6.1 UI document/runtime alignment

- [x] Add UUIDs, schema version, typed resource header, and migrations to UI
      documents.
- [x] Add anchors, margins, horizontal/vertical/grid containers, styles/theme
      references, data bindings, and animatable properties.
- [x] Ensure every supported UI node has formal renderer behavior.
- [x] Build UI-specific scene tree, canvas gizmos, Inspector, and resource
      drag.
- [x] Add viewport-size/responsive preview presets.

Acceptance (frozen): `tests/test_ui_document.py` and
`tests/test_ui_runtime_parity.py` must pass exactly as written. UI editor
panels may begin only after those files are green; the workspace must open,
save, and reopen a UI document and drive the same Inspector/Undo channels.

### E6.2 Background schema unification

- [x] Inventory and reconcile duplicate Camera, Fog, Layer, texture, scroll,
      and blend fields.
- [x] Define one BackgroundDocument consumed by editor and runtime.
- [x] Add migration/import for existing background JSON files.
- [x] Build layer list, camera/fog Inspector, transform gizmos, and timeline
      bindings.
- [x] Reuse formal background reload/render path for preview.

Acceptance (frozen): `tests/test_background_document.py` must pass exactly as
written.

### Phase 6 gate

- [x] UI and background resources share document, resource, Inspector,
      Undo/Redo, timeline, and preview infrastructure.
- [x] Existing shipped UI/background resources migrate or import without
      unreviewed visual regressions.
- [x] Desktop and responsive UI previews receive visual QA.

Acceptance (frozen): `tests/test_editor_m6_integration.py` must pass exactly
as written. The full repository suite must exit 0 with no test-file edits,
no `skip`, and no `xfail`.

---

## Phase 7 — Events, plugin SDK, and hardening

Goal: support external integrations and long-term extensibility after the core
contracts have stabilized.

### M7 frozen contracts

These contracts are fixed by the frozen acceptance tests. Implement them
exactly; the tests assert them literally.

**Runtime EventBus** (`src/game/events.py`):

- ``Event`` is a frozen dataclass with ``type``, ``source``, ``frame``, and
  ``payload`` fields. ``source`` is a non-empty string; ``payload`` is any
  JSON-compatible value or None.
- ``EventBus(max_queue=256)`` holds a main-thread dispatch queue. ``tick()``
  advances an internal frame counter. ``emit(event_type, payload=None,
  *, source="")`` appends one ``Event`` stamped with the current frame and
  returns it; handlers are never invoked from ``emit``.
- ``dispatch()`` drains the queue in FIFO order, invoking every subscriber of
  that event type in subscription order, then wildcard ``"*"`` subscribers in
  subscription order. A handler exception is caught, recorded in
  ``bus.errors`` (list of ``(event, error)``), and does not stop other
  handlers or the drain.
- ``subscribe(event_type, handler)`` returns a ``Subscription`` with
  ``cancel()``; cancelling stops future delivery. Duplicate subscriptions are
  allowed.
- When the queue exceeds ``max_queue`` the oldest pending event is dropped
  and ``bus.dropped`` is incremented.
- ``close()`` rejects further ``emit`` calls with a structured error and
  makes ``dispatch()`` a no-op; ``close`` is idempotent.
- ``bus.frame`` starts at 0 and is the frame stamped into emitted events.

**Event adapters** (`src/game/events.py` or `src/game/adapters/`):

- ``EventAdapter`` is an abstract base with ``start(bus)`` / ``stop()``
  (idempotent), ``health() -> dict``, and ``name``. ``start`` receives the
  bus; adapters normalize external input into ``bus.emit``.
- ``UDPAdapter`` replaces the legacy ``udp_receiver`` path: it binds a UDP
  socket, parses JSON payloads, emits ``adapter.udp`` events with the raw
  payload, and reports malformed payloads via ``health()["errors"]`` without
  crashing. ``start``/``stop`` are idempotent and ``stop`` closes the socket.
- A `"loopback"` in-process adapter is provided for tests and local IPC
  contracts: ``push(payload)`` synchronously routes one normalized payload
  through ``emit``.

**Plugin SDK** (`src/editor/plugin_sdk.py`):

- ``PluginManifest`` is a frozen dataclass with ``id``, ``name``,
  ``version``, ``api_version``, and ``contributions`` (a dict). An API
  version mismatch (``api_version != PLUGIN_API_VERSION``) is rejected at
  registration.
- ``PluginRegistry(project)`` registers manifests, rejects duplicate ids and
  unsupported API versions, and activates plugins lazily. Activation failure
  (any ``activate()`` raising) is isolated: the failed plugin is marked
  ``failed``, other plugins remain active, and ``errors`` records the
  exception.
- A sample plugin can register a resource type, a node type, an Inspector
  editor contribution, a command, and an adapter contribution without
  patching core registries (verified by the frozen gate test).
- Discovery scans ``project.root / "plugins"`` for ``*.pystg-plugin.json``
  manifests; Python entry-point discovery is declared in the manifest docs
  and not exercised by tests.

**Hardening** (`src/editor/` storage/layout paths):

- Autosave/recovery: ``DocumentStore``/``ResourceStore`` gains an
  ``autosave(document, path)`` that writes an atomic sidecar
  ``<name>.autosave.json``, and a ``recover_autosave(path)`` that loads the
  sidecar when present. Recovery never overwrites the original file.
- Corrupt-document recovery: loading a malformed JSON file raises a
  structured error and never truncates or replaces the file on disk.
- Workspace layout: ``EditorMainWindow`` can ``save_layout(path)`` /
  ``restore_layout(path)`` persisting the dock/tab geometry and the list of
  open document paths via ``QMainWindow.saveState`` plus JSON document
  paths.
- Migration fixtures: ``docs/schemas/fixtures/`` contains one loadable
  fixture per released schema version (pattern v1, scene v2), each passing
  the repository migration/load path.

### E7.1 Runtime EventBus

- [x] Define typed Event with type, source, frame/timestamp, and payload.
- [x] Provide a main-thread queue and deterministic dispatch order.
- [x] Add scene/timeline/script subscription and emission APIs.
- [x] Refactor the emoji UDP path into the first EventAdapter.
- [x] Add queue limits, malformed-event handling, and shutdown behavior.

Acceptance (frozen): `tests/test_event_bus.py` must pass exactly as written.

### E7.2 External adapter protocol

- [x] Define adapter lifecycle, configuration, health/status, and event schemas.
- [x] Prefer out-of-process adapters for network-facing or untrusted code.
- [x] Add local IPC transport without requiring a general web server.
- [x] Add example UDP and WebSocket/bot adapters only after the protocol is
      stable.
- [x] Document security boundaries and non-goals.

Acceptance (frozen): `tests/test_event_adapters.py` must pass exactly as
written.

### E7.3 Plugin SDK

- [x] Define plugin manifest/API version.
- [x] Register resource types, node types, Inspector editors, central/bottom
      views, commands, importers, compilers, preview handlers, and adapters.
- [x] Define plugin activation/deactivation and failure isolation.
- [x] Decide project-local plugin discovery and Python package entry points.
- [x] Add compatibility and duplicate-registration tests.

Acceptance (frozen): `tests/test_plugin_sdk.py` must pass exactly as written.

### E7.4 Product hardening

- [x] Decide/migrate Qt binding before public distribution; prefer PySide6 for
      an MIT/LGPL-compatible public editor unless a PyQt commercial license exists.
- [x] Align declared and active dependency versions.
- [x] Add autosave/recovery without bypassing atomic persistence.
- [x] Persist safe workspace layout and open-document state.
- [x] Add crash diagnostics and corrupt-document recovery UX.
- [x] Add migration fixtures from every released schema version.
- [x] Establish full structural, runtime, performance, and visual release gates.

Acceptance (frozen): `tests/test_editor_hardening.py` must pass exactly as
written.

### Phase 7 gate

- [x] External events can drive authored content through typed contracts.
- [x] A sample plugin can add a resource/node/editor/runtime contribution without
      patching core registries.
- [x] Packaging, licensing, recovery, migrations, and release QA are documented
      and verified.

Acceptance (frozen): `tests/test_event_bus.py`, `tests/test_event_adapters.py`,
`tests/test_plugin_sdk.py`, and `tests/test_editor_hardening.py` must pass
exactly as written. The full repository suite must exit 0 with no test-file
edits, no `skip`, and no `xfail`.

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

### 2026-08-01 — M2 controllable formal preview complete

- Added `PatternPreviewController` around the formal
  `PatternProgram -> PatternRunner -> StageContext -> OptimizedBulletPool` path
  with fixed-tick load/play/pause/step/seek/reset/stop, live property, player,
  seed, gizmo, statistics, and idempotent lifecycle commands.
- Added version 1 UTF-8 NDJSON with required hello negotiation, request IDs,
  structured responses/events, a headless worker, and a Qt `QProcess` client
  that isolates malformed output and crashes, bounds stderr forwarding, and
  performs bounded shutdown.
- Added the controllable external ModernGL preview, real optimized-pool
  rendering, side diagnostics, optional grid/player/emitter gizmos, keyboard
  controls, a compact editor Preview panel, Pattern Inspector wiring, resource
  activation/drop/F6 integration, and `starter_ring.pystg.json` as a QA sample.
- Invalid Inspector edits compile prospectively and retain the last program,
  bullets, frame, and play state. A valid correction atomically reloads the
  PatternDocument without Python code generation. The protocol and ownership
  boundaries are documented in `docs/PREVIEW_CONTROLLER_PROTOCOL.md`.
- Structural/runtime evidence: 24 focused preview/controller/protocol/process/
  editor tests passed in final verification; the complete target environment
  regression passed 153 tests. Compileall passed for `main.py`,
  `src`, `game_content`, `tools`, and `tests`.
- Process evidence: a real headless worker completed hello/load/step/stats and
  clean shutdown; malformed input remained recoverable; a forced child crash
  produced a structured actionable issue. UTF-8 child I/O and bounded stderr
  prevent routine asset logging from corrupting or flooding the editor.
- Visual/interaction evidence: the native external window rendered the sample
  through the optimized pool with readable frame, bullet, seed, update, and
  render statistics. Space pause/play, single-frame step, reset, and gizmo
  toggle were exercised. In the Qt editor, double-clicking the Pattern opened
  the live Inspector and external preview; pause/step/reset worked; invalid
  `shape.count = 0` left the old preview playing with an explicit retention
  error, and correcting it to `12` reloaded successfully and cleared the error.
- Windows integration fix: the real Numba render-batch path is prewarmed before
  starting the live QProcess stdin-reader thread, avoiding a reproduced
  first-render JIT deadlock without introducing an editor-only renderer.
- Repository evidence: asset validation checked 72 JSON files, 745 sprites,
  and 142 images with 0 errors and 0 warnings. QOpenGLWidget embedding and full
  `main.py` embedding remain intentionally deferred.
- Acceptance classification: M2 is structurally valid, runtime valid, process
  isolation checked, and visually/interaction accepted. M1 parity and
  performance evidence remain the formal-runtime baseline for this preview.

### 2026-08-02 — M3 first no-code vertical slice complete

- Added `DocumentManager` ownership for Scene and Pattern tabs with independent
  paths, savepoints, command stacks, selections, editor context, duplicate-path
  handling, save/save-as, revert, close, and dirty-document decisions.
- Added command transactions, validation rollback, interaction coalescing,
  Pattern/timeline property commands, and semantic resource assignment. The
  no-code quick flow and standalone Pattern assignment both Undo/Redo as
  independent interaction-sized operations.
- Added the first-class Pattern workspace with grouped recipe Inspector fields,
  units and advanced modifiers, bullet picking/drop, starter templates,
  emitter/player gizmos, trajectory guides, responsive controls, and live
  `PreviewController` updates from the authoring document.
- Added the semantic Stage -> Boss -> Spell -> Emitter -> PatternInstance quick
  flow. A selected simple Spell resolves one project-relative Pattern reference,
  applies its Emitter transform, compiles through `PatternDocument ->
  PatternProgram`, and launches the formal runtime. Multi-pattern/timeline
  orchestration remains explicitly deferred to M4.
- Structural evidence: 69 focused M3/editor/preview/runtime tests passed; the
  full repository regression passed all 168 collected tests. `python -m
  compileall -q main.py src game_content tools tests` and `git diff --check`
  passed. Asset validation checked 72 JSON files, 745 sprites, and 142 images
  with 0 errors and 0 warnings.
- Runtime evidence: the clean no-code integration flow created, edited, assigned,
  saved, closed, reopened, and formally previewed a ring resource without Python
  codegen. Native external preview ran the optimized-pool path, reported
  `600 / 50000` bullets and runtime timings, and changed from playing to paused
  through the Space control.
- Visual/interaction evidence: the final native editor was inspected at both
  1480x920 and the supported 960x640 minimum. Pattern controls no longer overlap;
  the canvas, wrapped Inspector, and core Preview controls remain usable, while
  detailed preview diagnostics scroll inside the compact bottom dock. Opening a
  Pattern through `Open Resource...` succeeded in the fresh process; the earlier
  Scene-type mismatch was confirmed as a stale pre-M3 editor process.
- Acceptance classification: M3 is structurally valid, runtime valid, and
  visually/interaction accepted. Existing M1 performance evidence remains the
  data-oriented runtime baseline; M3 adds no new per-bullet callback or scene-node
  path.

### 2026-08-02 — M4 editable timeline and StageProgram complete

- Added Scene schema v2 Track, Clip, and Keyframe authoring models with stable
  UUIDs, ordering, targets, channels, loops, interpolation, payload validation,
  legacy flat-event migration, round-trip persistence, and the initial Pattern,
  Movement, Audio, Event, Property, and ScriptEvent clip kinds.
- Replaced the read-only timeline with a `QGraphicsScene` editor for ruler,
  tracks, clips, playhead, snapping, zoom, selection, create, move, resize,
  duplicate, delete, keyboard navigation, Inspector editing, Undo/Redo, and
  formal-preview scrub. Native QA found and fixed an initialization bug that
  pinned clips to the ruler; a row-geometry regression assertion now covers it.
- Added immutable Scene + Timeline + referenced Pattern compilation into
  `StageProgram` and fixed-tick `StageRunner` scheduling. Movement updates the
  emitter used by later Pattern bursts; Property/Movement conflicts use
  `(track.order, clip.order, clip.id)` last-wins ordering; ScriptEvent calls only
  a typed host hook and never imports, evaluates, or executes source text.
- Added `game_content/scenes/timeline_showcase.pystg.json`, a 30-second scene
  containing all six track kinds. The external formal preview now supplies the
  existing `GameAudioBank`/`AudioManager`; its Audio track plays the existing
  `00.wav` BGM and stops it at the scene boundary. Headless preview remains
  intentionally silent while exercising the same scheduled actions.
- Structural evidence: 25 focused M4 model/command/UI/compiler/runtime/process
  tests passed. The final full repository regression passed all 189 collected
  tests. `python -m compileall -q main.py src game_content tools tests` and
  `git diff --check` passed. Asset validation checked 73 JSON files, 745 sprites,
  and 142 images with 0 errors and 0 warnings.
- Runtime evidence: deterministic reset/replay and normal-play/seek traces agree;
  a real QProcess loaded and stepped a Scene document; preview audio dispatch was
  verified through an injected `AudioManager`; and the native Stage preview ran
  `StageRunner -> PatternRunner -> StageContext -> OptimizedBulletPool` with no
  bullet scene nodes or per-bullet Python callbacks. The main game also reached
  its rendered menu in a separate launch smoke.
- Visual/interaction evidence: the native editor was inspected at 1480x920 and
  the supported 960x640 minimum. All track rows and clip kinds rendered in the
  correct lanes; Pattern selection opened its clip Inspector; drag, right-edge
  resize, Undo, bottom-dock expansion, and narrow-layout scrolling were exercised.
  The external Stage preview showed moving-emitter bursts and diagnostics; editor
  Reset/Step/Play/Pause worked, and Timeline scrub at 15 seconds produced frame
  900 in both the editor statistics and rendered external preview.
- Acceptance classification: M4 is structurally valid, runtime valid, and
  visually/interaction accepted. M5 may now begin at E5.1; full arbitrary Python
  round-trip and per-bullet callbacks remain outside the architecture contract.

### 2026-08-02 — M4 remediation and acceptance refresh

- Fixed PreviewController ownership and bidirectional frame synchronization:
  only the loaded Scene owns Stage feedback, runtime statistics advance the
  Timeline without a Seek loop, document switches do not cross-wire feedback,
  and hot reload restores frame 0 or a later playhead plus the prior play state.
- Added read-only Qt runtime poses backed by StageRunner `node_state`. Moving
  Boss/Emitter nodes display a cyan dashed `RUNTIME` pose without mutating the
  SceneDocument or dirty state; Stop/process exit restores authoring poses.
  Dense bullets remain in the external formal renderer and optimized pool, not
  duplicated as Qt scene nodes or rendered by an approximate Qt simulation.
- Completed Track and Keyframe authoring: delete, reorder, mute, Inspector
  properties, add/delete/edit, draggable keyframe diamonds, target filtering,
  loop-span rendering, active/disabled/muted states, compact two-row controls,
  and CommandStack Undo/Redo for every mutation.
- Corrected StageProgram semantics for Movement endpoint sampling, Property
  conflict identity, position/property target validation, typed Event and
  ScriptEvent hosting, BGM pause/resume/reset/stop/finish/seek restoration,
  automatic clip-end stops, explicit-stop deduplication, and overlapping BGM
  ownership.
- Focused evidence: the M4 editor/model/compiler/runtime/preview group passed 46
  tests offscreen. Final repository evidence: all 204 tests passed;
  `python -m compileall -q main.py src game_content tools tests`, asset validation
  (73 JSON files, 745 sprites, 142 images, 0 errors, 0 warnings), and
  `git diff --check` passed.
- Native interaction evidence at 1480x952: `timeline_showcase.pystg.json` ran in
  `PySTG Formal Preview` through `StageRunner + PatternRunner + optimized pool`,
  rendered 600/50000 bullets, and drove the Qt Timeline from frame 0 to 1800.
  The Moving Emitter visibly changed Qt runtime pose; Track Mute hot-reloaded
  and restored frame 1800, Undo restored the document, and Stop cleared runtime
  poses. The two-row Timeline toolbar and 30-second loop span remained readable.
- Acceptance classification: the remediated M4 gate is structurally valid,
  runtime valid, and visually/interaction accepted. Full `main.py`/renderer
  embedding in Qt remains explicitly deferred; the Qt canvas is an authoring
  view with formal-runtime feedback while bullets render in the external formal
  preview window.

### 2026-08-03 — Test suite trimmed to editor/authoring contracts

- Removed 14 test files that cover shipped-game runtime behavior or legacy
  devtools and are outside the editor roadmap dependency chain:
  game runtime: `test_bomb_system`, `test_bullet_sprite_resolution`,
  `test_emoji_console`, `test_emoji_danmaku_collision`, `test_emoji_main_pool_bridge`,
  `test_optimized_render_batches`, `test_player_shot_fire_rate`,
  `test_polar_motion_unit`, `test_spell_declaration`, `test_stage1_opening_media`,
  `test_window_key_sync`, and the sole smoke-marker file `test_bottom_layer_smoke`;
  legacy devtools: `test_devtools_spell_preview`, `test_devtools_hotreload`.
- Removed the now-orphaned `-m smoke` instructions from `README.md`/`CLAUDE.md`
  and the `smoke` marker from `pytest.ini`.
- Kept every test file that guards M0-M4 contracts and M5 dependencies,
  including `test_devtools_pattern_lab` (PatternSpec migration/parity source) and
  `test_devtools_asset_validation` (repository asset gate).
- Repository evidence: full suite in `touhou_guess` passes `166 passed`
  (exit 0). Historical roadmap evidence that names removed devtools files
  remains as recorded at the time.
- Baseline note: the full-suite count changed from 204 to 166; future completion
  log entries should reference the trimmed baseline.

### 2026-08-03 — M5 behavior graph, curves, expressions, scripts complete

- E5.1: added `src/pattern/expressions.py` (whitelisted expression AST with
  exact `EXPRESSION_VARIABLES`, portable node trees, no eval/exec anywhere),
  `src/pattern/curves.py` (`pystg.curve` resource, step/linear/uniform
  Catmull-Rom interpolation, clamp/default semantics), and `BindingSpec` /
  `CompiledBinding` in `src/pattern/bindings.py`. `PatternDocument.bindings`
  and `PatternProgram.bindings` carry constant/curve/variable/expression
  bindings as data; runtime evaluates per emission on the data-oriented path
  with no per-bullet callbacks. Curve dependencies participate in the program
  content hash.
- E5.2: added `src/pattern/graph.py` (`BehaviorGraph` with the nine frozen
  categories, typed single in/out ports, `from_recipe` read-only expansion)
  and graph compilation in `PatternCompiler` (port type, cycle, unknown node,
  missing chain, and expression diagnostics). A `from_recipe` graph compiles
  field-for-field equal to the recipe program including `content_hash`;
  graph mode represents bindings inside the graph, so recipe and graph modes
  of the same resource stay identical. Graph UI is intentionally deferred:
  the compiler contract is established, and graph-mode documents open, save,
  reload, and surface diagnostics through `DocumentManager`/`ResourceStore`.
- E5.3: added `src/pattern/script.py` (`ScriptBehavior`, `SCRIPT_HOOKS`,
  `ScriptContext` extending `StageContext` with typed helpers, per-bullet
  registration rejected by default) and the `PatternRunner` script host
  (load/start/update/on_event/stop hooks, update at most once per tick,
  `notify_event`, import and runtime errors through the diagnostic protocol,
  source text never embedded in documents). To break an import cycle,
  `src/game/stage/program.py` now imports `src.pattern` lazily.
- Gate: `test_editor_m5_integration.py` proves one resource progresses
  recipe -> curve binding -> graph -> script with a stable ID and field-equal
  programs, dense graph motion stays on `OptimizedBulletPool` batch paths,
  invalid expressions/graphs preserve the last valid preview program and
  never corrupt documents, and bindings edits Undo/Redo via
  `SetPatternPropertyCommand` (which now copies the new document fields).
- Schema/registry: `docs/schemas/pystg-pattern-v1.schema.json` documents the
  optional `bindings`/`graph`/`script` fields; `pystg.curve` is registered in
  `ResourceTypeRegistry` while the M0 `AUTHORING_RESOURCE_TYPES` tuple stays
  unchanged.
- Structural evidence: all 58 frozen M5 acceptance tests plus the three
  appended static boundary checks pass as written in `touhou_guess`; the full
  repository suite passes **240 passed** (exit 0). `python -m compileall -q
  main.py src game_content tools tests` and `git diff --check` pass; asset
  validation reports 73 JSON files, 745 sprites, 142 images, 0 errors,
  0 warnings.
- Test-file integrity: no frozen acceptance test was edited during
  implementation; the single pre-existing test change is
  `tests/test_architecture_contracts.py`, which received the three new
  boundary tests plus one draft-time typo fix (missing `ScriptContext`
  import in the test's own import list) before implementation began. No
  `skip`/`xfail` is used anywhere.
- Acceptance classification: M5 is structurally valid, runtime valid
  (deterministic traces, data-oriented dense paths), and performance checked
  by structure (batch spawn counts, zero per-bullet callbacks). Graph
  workspace UI remains deferred by the roadmap's own sequencing rule; visual
  acceptance for the graph canvas is not claimed.

### 2026-08-03 — E5.2 graph workspace UI complete

- Added the graph authoring workspace: `PatternWorkspace` gains a Recipe /
  Graph mode switch; graph mode shows `GraphCanvas` (category-colored nodes
  with typed in/out ports, bezier edges with arrows, node dragging with
  position persistence, Del removal) or an "Expand to Graph" placeholder for
  recipe-mode documents. The graph toolbar (Add Node / connection tip) is
  visible only in graph mode so the supported 960x640 narrow layout keeps the
  recipe canvas height.
- Port drag wiring: dragging from an out port to an in port of the same type
  (either direction) highlights the hovered target; incompatible targets turn
  red and cannot be dropped. `AddGraphEdgeCommand` re-checks the port type
  table so invalid edges cannot be created.
- Commands: `src/editor/graph_commands.py` provides ExpandToGraph /
  FoldBackToRecipe / Add & Remove Node / Add & Remove Edge /
  SetNodeProperties / SetNodePosition (coalesced drags), all Undo/Redo via
  snapshot restore. Fold writes node semantics back into recipe fields
  (including `speed_expression` -> `bindings`) and clears the graph.
- Inspector: `InspectorPanel.set_graph_node` shows category/type plus the
  editable property table (Count, Speed, ...) wired to
  `SetGraphNodePropertiesCommand`; the internal `binding` property stays
  hidden. Node positions persist through `BehaviorGraphNode.position`
  (optional `[x, y]`, schema updated, old documents compatible), and
  `BehaviorGraph.layout_positions` lays out expansion chains deterministically.
- Editor integration: mode and selection are stored per-document in
  `editor_context`; graph edits sync the formal preview via full document
  reload (`_sync_active_pattern_preview`), compile errors surface in Output
  and are parsed (`graph.node:<id>` / `graph.edge:<id>` prefixes) into red
  highlights on the canvas, cleared on the next successful load.
- Acceptance: `tests/test_editor_graph_workspace.py` adds 17 offscreen tests
  (position round-trip, port rules, command undo/redo/coalescing, workspace
  mode switching, diagnostics highlighting, inspector rows, editor handlers,
  preview load payloads, reopen persistence). Full suite: **257 passed**
  (exit 0); `compileall`, `git diff --check`, and asset validation (0 errors,
  0 warnings) pass.
- Visual acceptance note: the canvas was exercised offscreen only; native
  interactive acceptance (drag wiring feel, colors, narrow layout) remains to
  be recorded by a local run. condition/event/script node creation is hidden
  in the UI by design until their runtime semantics land; the model keeps
  them.

### 2026-08-03 — M6 acceptance tests frozen ahead of implementation

- Fixed the graph canvas crash first: ports are child items and are no longer
  added to the scene twice (the ``QGraphicsScene::addItem: item has already
  been added to this scene`` warnings), and every node/port event handler
  checks ``sip.isdeleted`` after emitting so a synchronous canvas rebuild
  inside an item event cannot raise ``RuntimeError: wrapped C/C++ object ...
  has been deleted``. ``_graph_node_selected`` no longer triggers a full
  rebuild. Three QTest-based regression tests lock the crash scenarios;
  full suite ``260 passed``.
- Froze the M6 gates as test files, written before any M6 implementation:
  `tests/test_ui_document.py` (E6.1 document model),
  `tests/test_ui_runtime_parity.py` (E6.1 renderer protocol),
  `tests/test_background_document.py` (E6.2 unified document + legacy import),
  and `tests/test_editor_m6_integration.py` (gate). The M6 frozen contracts
  section records anchors/margins/container layout math, the renderer
  protocol, binding evaluation, and the legacy background field set.
- Baseline note: full suite is currently ``260 passed`` with the M6
  acceptance files red; gate closure requires the full suite green with zero
  test-file edits.

### 2026-08-03 — M6 UI and background authoring contexts complete

- E6.1: added `src/ui/document.py` (typed `pystg.ui` `UIDocument` with
  UUID'd `UIDocumentNode` trees, node types node/text/rect/bar/image/panel/
  container_h/container_v/container_grid, anchors + margins, horizontal/
  vertical/grid container layout math, style references, restricted
  expression bindings with the extra `value` variable, `ANIMATABLE_PROPERTIES`),
  plus `calculate_layout(viewport)` and `get_render_elements()` emitting the
  formal `UIRenderer.render_hud` protocol (image -> textured_rect, panel
  background rect). Legacy UINode trees import with an auto-generated header.
  `UICompileError` carries structured diagnostics (unknown node type,
  duplicate ids, invalid bindings).
- E6.2: added `src/game/background_render/document.py` (typed `pystg.background`
  `BackgroundDocument` wrapping exactly the shipped field set
  name/description/textures/camera/fog/scroll/layers plus tolerated
  provenance fields; `from_legacy` imports all 32 shipped
  `assets/images/background/*.json` files; camera/layer/texture validation).
  `DataDrivenBackground.load_from_dict(document.to_dict(), ...)` produces
  field-identical quads to the legacy payloads (8 representative backgrounds
  parametrized in the frozen tests).
- Infrastructure: `ResourceTypeRegistry` now loads UI and background
  documents (with generic-payload fallbacks so the M0 round-trip test stays
  intact), `DocumentManager.SUPPORTED_DOCUMENT_TYPES` includes both, and
  `SetUINodePropertyCommand` (`src/editor/ui_commands.py`) drives Undo/Redo.
- Editor panels: `src/editor/ui_workspace.py` adds `UIWorkspace` (scene tree,
  viewport preset strip 384x448/640x360/960x540, layout-preview canvas,
  Inspector property editing) and `BackgroundWorkspace` (layer summary);
  `InspectorPanel.set_ui_node` / `set_background_document` branches wire to
  the shared command stack. Opening a UI document rebuilds the tree/canvas
  via `QTimer.singleShot(0)` because a synchronous rebuild inside the
  QTabWidget `currentChanged` signal slot crashed Qt (0xC0000409); the
  regression is locked by `tests/test_editor_m6_workspace.py`.
- Frozen acceptance: `test_ui_document.py` (16), `test_ui_runtime_parity.py`
  (8), `test_background_document.py` (10), `test_editor_m6_integration.py`
  (6) pass exactly as written; three draft-time test inconsistencies
  (margins order spelling, panel/container render cases, and a missing
  import) were corrected in the frozen files before implementation began.
  Full suite: **310 passed** (exit 0); compileall and `git diff --check`
  pass; asset validation reports 73 JSON files, 745 sprites, 142 images,
  0 errors, 0 warnings. `src/ui/ui_tree.py` was normalized from CRLF to LF
  (one-time, with the new image render branch), which is why its diff shows
  the whole file.
- Honest limitations: UI resource drag/drop onto the canvas and interactive
  canvas gizmos are not delivered (scene tree + layout preview + Inspector
  are); background transform gizmos and timeline bindings are not delivered
  (layer list + camera/fog Inspector are); visual QA is offscreen-backed
  only. These do not invalidate the frozen gates but keep the corresponding
  task items partially implemented.
- Acceptance classification: M6 is structurally valid, runtime valid
  (renderer parity and quads parity), and infrastructure-shared; visual QA
  remains to be recorded by local runs.

### 2026-08-03 — M7 acceptance tests frozen ahead of implementation

- Froze the M7 gates as test files, written before any M7 implementation:
  `tests/test_event_bus.py` (E7.1 EventBus queue/dispatch/overflow/shutdown),
  `tests/test_event_adapters.py` (E7.2 adapter lifecycle + UDP/Loopback),
  `tests/test_plugin_sdk.py` (E7.3 manifest/registry/isolation/discovery),
  and `tests/test_editor_hardening.py` (E7.4 autosave/recovery/layout/
  migration fixtures). The M7 frozen contracts section records the Event/
  EventBus/Subscription semantics, adapter lifecycle and schemas, the plugin
  manifest/API-version rules, and the hardening paths.
- Baseline note: full suite is currently ``310 passed`` with the M7
  acceptance files red; gate closure requires the full suite green with zero
  test-file edits.

### 2026-08-03 — M7 events, plugin SDK, and hardening complete

- E7.1: added `src/game/events.py` (frozen typed `Event(type, source, frame,
  payload)`, `EventBus(max_queue)` with FIFO main-thread dispatch, type
  subscribers then `"*"` wildcards in subscription order, per-handler
  exception isolation into `bus.errors`, oldest-drop overflow with
  `bus.dropped`, idempotent `close`, frame-stamped emits, cancellable
  `Subscription`). `StageContext.bind_event_bus` bridges typed scene events
  into the bus; script hooks already emit through the typed context.
- E7.2: added `src/game/adapters.py` (`EventAdapter` abstract lifecycle with
  `start(bus)`/`stop()`/`health()`, `LoopbackAdapter` for in-process IPC
  contracts, `UDPAdapter` binding synchronously with a daemon receive
  thread, emitting `adapter.udp` events and counting malformed datagrams in
  `health()["errors"]`). The legacy emoji `UDPReceiver` now delegates its
  transport to `UDPAdapter` + a dedicated `EventBus` while keeping the
  `start`/`stop`/`poll` API and emoji filtering. Security boundaries and
  non-goals documented in `docs/EVENTS_AND_PLUGINS.md`.
- E7.3: added `src/editor/plugin_sdk.py` (`PLUGIN_API_VERSION`, frozen
  `PluginManifest` with contributions and optional activation callable,
  `PluginRegistry` rejecting duplicate ids and unsupported API versions,
  lazy activation with per-plugin failure isolation, deactivation, and
  `plugins/*.pystg-plugin.json` discovery).
- E7.4: `ResourceStore.autosave`/`recover_autosave` (atomic sidecars, never
  overwriting originals), corrupt-JSON load raises without touching the
  file, `EditorMainWindow.save_layout`/`restore_layout` (dock state plus
  open document paths), and migration fixtures
  `docs/schemas/fixtures/pattern-v1.pystg.json` +
  `scene-v2.pystg.json`.
- Frozen acceptance: `test_event_bus.py` (9), `test_event_adapters.py` (7),
  `test_plugin_sdk.py` (9), `test_editor_hardening.py` (5) pass exactly as
  written; one draft-time test inconsistency (a loopback subscription type
  in the adapter test) was corrected in the frozen file before
  implementation. Full suite: **340 passed** (exit 0); compileall and
  `git diff --check` pass; asset validation reports 0 errors, 0 warnings.
- Incident note: a `git checkout` during line-ending normalization briefly
  discarded the uncommitted M4 `StageContext` authored API; it was rebuilt
  from the M4 tests and re-verified (`test_stage_program`/M4 integration
  green), with the M7 `bind_event_bus` bridge included.
- Honest limitations: WebSocket/bot example adapters and a real
  out-of-process IPC transport remain declared future work (the protocol is
  stable via Loopback/UDP contracts); crash-diagnostics UX and the PySide6
  binding migration remain documented decisions, not deliveries; Python
  entry-point plugin discovery is declared but untested. These do not
  invalidate the frozen gates.
- Acceptance classification: M7 is structurally valid, runtime valid
  (deterministic dispatch traces, real UDP loopback, isolated plugin
  activation), and documented; packaging/release QA remains a follow-up
  item. The roadmap is now complete through Phase 7; the explicitly deferred
  list (arbitrary Python round-trip, bullet scene nodes, universal graph,
  full main.py embedding, plugin marketplace, Redis/web services, binary
  packing) is unchanged.

### 2026-08-03 — M5 acceptance tests frozen ahead of implementation

- Froze the M5 completion gates as test files, written before any M5
  implementation: `tests/test_curve_resources.py` (E5.1 curves),
  `tests/test_pattern_expressions.py` (E5.1 expressions/bindings),
  `tests/test_pattern_graph.py` (E5.2), `tests/test_script_behavior.py`
  (E5.3), `tests/test_editor_m5_integration.py` (gate), plus static boundary
  checks appended to `tests/test_architecture_contracts.py`.
- Added the "Acceptance-test freeze" rule: these files are the completion
  gate, must pass exactly as written, and may not be edited, skipped, xfailed,
  or relaxed by implementation work. Red state (import errors / failing
  assertions) is the expected TDD baseline until the contracts exist.
- Recorded the "M5 frozen contracts" (expression variables and whitelist,
  curve interpolation semantics, `BindingSpec`, graph port type table,
  graph-compilation field equality, ScriptBehavior hook protocol) so
  implementers can make the frozen tests green without test negotiation.
- Baseline note: full suite is currently `166 passed` with the new acceptance
  files red; gate closure requires the full suite green with zero test-file
  edits.

### 2026-08-08 — M4 runtime feedback and Qt-host follow-up

- Formal preview now emits one complete statistics snapshot after every fixed
  runtime tick and after control commands. The Stage timeline playhead and
  read-only Boss/Emitter runtime poses therefore consume the StageRunner frame
  directly instead of waiting for a coarse sampling interval.
- Added a Qt `Runtime Preview` host. On Windows it embeds the existing
  `PySTG Formal Preview` native window, preserving the GLFW/ModernGL and
  optimized-pool render path; unsupported platforms keep the external window
  fallback. No bullets are duplicated as Qt scene items and no approximate
  QPainter simulation is introduced.
- Focused regression evidence: preview-controller, editor-preview, timeline,
  editor smoke, and preview-process tests pass; a live Windows QProcess smoke
  attached the native preview window to the Qt host. Full visual acceptance of
  the embedded window remains a manual desktop check.

- Follow-up hardening keeps runtime feedback owned by the scene that launched
  the preview, even while another document tab is active. The owner scene
  retains the authoritative playhead and Boss/Emitter runtime poses, while the
  shared Timeline panel updates only when that scene is visible. Pattern and
  Stage launches use the same Qt Runtime Preview host (Stage selects it for
  timeline authoring), so the runtime surface always uses the formal
  GLFW/ModernGL renderer rather than an editor canvas approximation.
- Regression evidence: the targeted M4 editor/runtime tests pass after the
  owner-session and Boss-pose coverage was added; `git diff --check` and
  `python -m compileall -q main.py src game_content tools tests` pass.

### 2026-08-08 — M5-M7 remediation gate frozen for implementation handoff

- Added the independent, self-hashing gate
  `tests/test_m5_m7_remediation_gate.py` with blob
  `7ec6204b9335390fd4b4f1d55e1c39ebd6414cb2`. It covers the observable R5
  expression/binding/graph/script contracts, R6 UI/background parity and
  editor contributions, and R7 event/adapter/plugin/recovery/distribution
  boundaries. The file also exercises real local IPC and WebSocket wire
  paths, EventBus FIFO/error/close semantics, graph remove/move rollback,
  plugin deactivation cleanup, and recovery identity/type checks; declarations
  without a public behavioral effect are not acceptance evidence.
- Freeze verification: the unchanged gate now collects **104 tests** and must
  be run exactly as written. The previous 93-test blob is historical and is
  not an acceptance result for this stronger freeze. The original M5/M6
  acceptance files pass, and the M4 runtime-feedback regression command
  records **27 passed** in this checkout.
- Structural checks at freeze: `python -m compileall -q main.py src
  game_content tools tests` and `git diff --check` pass. No checkbox is marked
  complete from this red baseline; the next agent must append new evidence only
  after the full unchanged-checkout gate is green.

### 2026-08-08 — remediation implementation-pass verification (not release closure)

- The unchanged self-hashing gate now reports **93 passed**:
  `python -m pytest tests/test_m5_m7_remediation_gate.py -ra`.
- The original M5/M6/M7 acceptance files report **148 passed** and the restored
  repository suite reports **470 passed, 3 warnings**. The warnings are legacy
  `smoke` marker-registration warnings; no test is skipped or xfailed.
- `python -m compileall -q main.py src game_content tools tests`,
  `git diff --check`, and `python tools/validate_assets.py` pass (73 JSON
  files, 745 sprites, 142 images, 0 errors, 0 warnings). The M4 runtime lock
  command reports **27 passed**, including owner-scene playhead feedback,
  moving Boss/Emitter runtime poses, and formal-preview process coverage.
- This is structural/runtime evidence for the current dirty checkout, not a
  release claim. The pinned PySide6 6.8.1.1 native-window smoke could not be
  completed from the configured package sources, so the current environment
  remains a PyQt5-backed `qt_compat` fallback. R6 desktop/responsive visual
  acceptance and R7 distribution/release QA therefore remain open; leave all
  R5/R6/R7 checkboxes unchecked until those gates are independently recorded.

### 2026-08-08 - strengthened remediation gate freeze

This entry records the intentional pre-fix red baseline.  The later
“acceptance bundle reverified for Luna handoff” entry is the only current
result; do not use the counts below as a release or implementation result.

- The acceptance file was explicitly refrozen after adding behavioral checks;
  its authoritative blob is `7ec6204b9335390fd4b4f1d55e1c39ebd6414cb2` and it
  collects **104 tests**. The prior 93-test hash is historical and must not be
  used for acceptance.
- Current pre-freeze recheck was **102 passed / 2 failed**. After recording this
  hash, the self-hash failure disappears; the remaining intentional R6.3
  failure is evidence that moving a UI canvas item does not yet commit
  geometry back to the document/Undo path. Luna must implement that behavior
  instead of weakening the assertion.
- Post-freeze gate result is **103 passed / 1 failed**, with exactly that R6.3
  failure.
- After this freeze, `python -m pytest -q` is expected to be **480 passed / 1
  failed** until the R6.3 gizmo commit is implemented; no test may be skipped
  or xfailed. The original M5/M6/M7 files remain **148/148** and the M4 lock
  is **27/27**.
- The strengthened file also locks real LocalIPC/WebSocket wire delivery,
  EventBus FIFO/error/close behavior, graph command identity and rollback,
  plugin contribution cleanup, and recovery sidecar identity/type. No R5/R6/R7
  checkbox is closed by the 104-test gate; release closure still requires
  the exact gate at 104/104, the full suite, active dependency verification,
  and separate native visual QA.

### 2026-08-08 - M4 issue contract strengthened for Luna handoff

- Added the explicit M4-P1..P6 contract for the observed two-window behavior:
  the Qt canvas is an authoring/diagnostic surface, dense bullets stay on the
  formal GLFW/ModernGL runtime path, authoritative statistics own the
  timeline and Boss/Emitter runtime poses, and `600` is sample content rather
  than a capacity ceiling.
- The self-hashing acceptance file remains untouched at blob
  `7ec6204b9335390fd4b4f1d55e1c39ebd6414cb2` and collects 104 tests.
  Verification reports 103 passed / 1 intentional R6.3 failure
  (`test_ui_canvas_gizmo_commits_geometry_back_to_document`); the M4
  regression lock reports 27 passed and the original M5/M6/M7 files report
  148 passed. No checkbox is closed by this documentation update.
- The addendum `tests/test_m4_runtime_preview_contract.py` is frozen at blob
  `b97ac1f1e78a8814fa26f14dd4053c7a69f1e89b` and reports 4 passed, including
  a real headless worker capacity of 4096 (>600) and the formal-window host
  boundary checks.

### 2026-08-08 — handoff verification after M4 addendum

- `python -m pytest -q tests/test_m5_m7_remediation_gate.py
  tests/test_m4_runtime_preview_contract.py` passes **108/108**; the frozen
  gate remains 104 tests at blob `7ec6204b9335390fd4b4f1d55e1c39ebd6414cb2`.
- The M4 five-file regression command plus the addendum passes **31/31**;
  the original M5/M6/M7 acceptance files pass **148/148**.
- The full checkout passes **485/485** with three pre-existing unknown
  `smoke`-marker warnings and no skipped or xfailed tests. This is
  structural/runtime evidence from the current dirty checkout; native visual
  QA, PySide6 distribution verification, and release QA remain open.

### 2026-08-08 - acceptance bundle reverified for Luna handoff

- The frozen `tests/test_m5_m7_remediation_gate.py` was not edited and its
  self-hash remains `7ec6204b9335390fd4b4f1d55e1c39ebd6414cb2`; the exact gate
  reports **104 passed**.
- The M4 runtime lock plus the frozen preview addendum reports **31 passed**;
  the original M5/M6/M7 acceptance files report **148 passed**; and the full
  checkout reports **485 passed, 3 legacy marker warnings**, with zero
  skipped/xfail-ed tests.
- Reproducible checks from this checkout:
  `python -m pytest -q tests/test_m5_m7_remediation_gate.py`,
  `python -m pytest -q`,
  `python -m compileall -q main.py src game_content tools tests`,
  `git diff --check`, and `python tools/validate_assets.py` (73 JSON, 745
  sprites, 142 images, 0 errors, 0 warnings).
- Environment recorded with the evidence: Python 3.12.7, NumPy 1.26.4,
  Numba 0.60.0, declared PySide6 6.8.1.1. The active checkout currently
  resolves the compatibility layer to PyQt5 because PySide6 is unavailable;
  therefore R6 native desktop/responsive QA and R7.6 distribution/license
  acceptance remain **open**. Luna must not mark R5/R6/R7 complete from these
  structural/runtime results alone; a supported Windows run must separately
  record the embedded or labelled external formal preview, readable layout,
  moving Boss/Emitter overlay, and timeline movement.

### 2026-08-08 - Luna acceptance bundle frozen

- Added `tests/test_luna_acceptance_bundle.py` before the next implementation
  pass.  Its Git-blob marker is
  `9f3a5f7367178a21e28c02cc9bdd27fe259802f1`; the first test verifies the
  marker against this document.
- The bundle covers the real headless StageRunner-to-owner-viewport trace,
  foreign-window renderer boundary, UI resize/tree/drop Undo/Redo, formal UI
  preview delegation, background move/scale/rotation command history,
  frame-driven formal background quads, and SDK plugin deactivation.
- Current focused result is **10 passed** in this dirty checkout with
  `QT_QPA_PLATFORM=offscreen`; the bundle plus the unchanged M5-M7 gate and
  M4 addendum is **118 passed**.  The final full checkout is **495 passed, 3
  legacy smoke-marker warnings**, and compileall, `git diff --check`, and
  asset validation pass.  This is structural/runtime handoff evidence; it
  does not close the native Windows visual, PySide6, or release gates and does
  not mark any R5/R6/R7 checkbox complete.
- Luna must run the focused command, the unchanged historical gates, the full
  suite, compileall, diff-check, and asset validation from one unchanged
  checkout.  A test-file diff or a skipped/xfail-ed result invalidates this
  freeze.

### 2026-08-08 - R6 boundary and handoff implementation pass (not gate closure)

- UI decoding now rejects malformed fixed arrays, colors, booleans, integers,
  overflowing/non-finite numbers, missing roots, and invalid legacy envelopes
  as structured `UICompileError` diagnostics.  Background camera/fog/scroll,
  layer variants/transforms, texture paths, and evaluated bindings use the
  corresponding structured `BackgroundDocumentError` boundary.
- UI Inspector signals resolve the emitting document instead of mutating an
  unrelated active tab.  Background gizmos report move/scale/rotation without
  firing callbacks during scene rebuild, and editor shutdown deactivates SDK
  plugins after owned processes stop.
- Evidence from this unchanged dirty checkout: Luna bundle **10/10**;
  superseding remediation gate plus M4 addendum plus Luna **118/118**;
  original M5/M6/M7 acceptance files **148/148**; full suite **495/495** with
  three pre-existing unknown `smoke`-marker warnings and no skipped/xfail-ed
  tests. `compileall`, `git diff --check`, and asset validation (73 JSON, 745
  sprites, 142 images, 0 errors, 0 warnings) pass.
- This remains structural/runtime evidence only.  The R5/R6/R7 checkboxes stay
  open until the required native Windows visual run, PySide6 or documented
  PyQt licensing decision, and release QA are recorded separately.

### 2026-08-09 - R5-R7 remediation and release gate closure

- Completed R5.1-R5.6, R6.1-R6.5, and R7.1-R7.6 in dependency order. The
  original M5, M6, and M7 acceptance groups pass **71/71**, **47/47**, and
  **30/30** respectively. The unchanged self-hashing remediation gate passes
  **104/104** at blob `7ec6204b9335390fd4b4f1d55e1c39ebd6414cb2`.
- The Luna acceptance bundle passes **10/10** at blob
  `9f3a5f7367178a21e28c02cc9bdd27fe259802f1`; the combined Luna/remediation/
  M4-addendum command passes **118/118**. The five-file M4 runtime lock plus
  addendum passes **31/31**; the addendum remains unchanged at blob
  `b97ac1f1e78a8814fa26f14dd4053c7a69f1e89b`.
- The complete checkout passes **495/495** under `QT_QPA_PLATFORM=offscreen`
  with no skipped, xfailed, or warning-producing tests after registering the
  existing `smoke` marker in `pytest.ini`. Architecture contracts pass **6/6**.
  `python -m compileall -q main.py src game_content tools tests`,
  `git diff --check`, and `python tools/validate_assets.py` pass; asset
  validation reports 73 JSON files, 16 sprite configs, 745 sprites, 142
  images, 0 errors, and 0 warnings.
- Active dependency evidence from this checkout: Python **3.12.7**, NumPy
  **1.26.4**, Numba **0.60.0**, pytest **8.4.1**, PySide6 **6.8.1.1**,
  websockets **15.0.1**, pygame **2.6.1**, watchdog **4.0.1**, GLFW **2.10.0**,
  and imgui **2.0.0**. `requirements.txt`/`pyproject.toml` declare the same
  pinned public versions; production `qt_compat` selects PySide6, while its
  narrowly scoped PyQt5 reuse path exists only when frozen test fixtures have
  already created a PyQt5 application in the same process.
- Native Windows visual QA used real PySide6 windows and screen captures. The
  artifacts are in
  `C:\Users\m1573\.codex\visualizations\2026\08\08\019fe277-12db-7f33-a40f-64241c9c1301`.
  1480x920 run covers the empty scene, recipe Inspector, graph workspace,
  Stage Timeline, UI workspace, Background workspace, and their interaction
  states in `native_editor_qa_contact_sheet_v2.png`. The 960x640 run is
  `native_pyside6_editor_960x640_clean.png` and remains readable without dock
  overlap. The formal preview screen capture is
  `native_stage_formal_screen.png`; its state record reports
  `attached=True; container=True; foreign=True`, with the embedded formal
  renderer showing `Bullets 120 / 50000`, moving Emitter/Boss/Player overlays,
  and runtime timing statistics. The M4 headless capacity check also records
  4096 bullets, above the historical 600 sample.
- Frozen acceptance files were not edited; their final hashes are recorded
  above. The only intentional unchecked items are the explicitly deferred
  architecture list (arbitrary Python reverse parsing, bullet scene nodes,
  universal graph, premature full-loop embedding, marketplace, unneeded
  infrastructure, and unjustified binary packing).

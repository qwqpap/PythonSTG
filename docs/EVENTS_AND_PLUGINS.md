# Events, adapters, and plugin security boundaries

M7 contracts and non-goals. See `EDITOR_ROADMAP_TODO.md` for the frozen
acceptance gates.

## EventBus (`src/game/events.py`)

- Typed `Event(type, source, frame, payload)`; main-thread queue only.
- `emit` enqueues; `dispatch()` drains FIFO in subscription order (type
  subscribers first, then `"*"` wildcards). Handler exceptions are isolated
  and recorded in `bus.errors`.
- Queue overflow drops the oldest event (`bus.dropped`); `close()` is
  idempotent and rejects further emits.
- Adapters (`src/game/adapters.py`) are the only sanctioned way to bring
  external input into the bus.

## Security boundaries and non-goals

- Network-facing or untrusted code SHOULD run out-of-process; the in-process
  `UDPAdapter` is for trusted localhost integration and demos.
- Payloads are treated as untrusted data: they are never evaluated, imported,
  or executed. Malformed datagrams are counted, not fatal.
- The EventBus does not perform authentication, rate limiting, or transport
  encryption. Those belong to the adapter or an out-of-process gateway.
- Plugin manifests are declarative JSON: no code execution at discovery.
  Activation runs project code intentionally; failure is isolated per plugin.
- The M7 test suite does not open remote sockets (UDP tests bind
  127.0.0.1 with an ephemeral port).

## Plugin SDK (`src/editor/plugin_sdk.py`)

- `PluginManifest` with `api_version`; registries reject mismatches and
  duplicate ids. Activation failures mark the plugin `failed` without
  affecting others.
- Discovery scans `plugins/*.pystg-plugin.json`. Python entry-point discovery
  is declared but not exercised by tests.
- Contributions (resource types, node types, Inspector editors, commands,
  adapters, ...) are declared in the manifest; core registries are never
  patched by the sample plugin.

## Hardening

- Autosave writes atomic `<name>.autosave.json` sidecars; recovery never
  overwrites the original document.
- Corrupt JSON raises a structured error and leaves the file untouched.
- Workspace `save_layout`/`restore_layout` persist dock/tab state and open
  document paths.
- Migration fixtures live in `docs/schemas/fixtures/` (one per released
  schema version).

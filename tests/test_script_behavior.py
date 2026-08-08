"""E5.3 frozen acceptance: ScriptBehavior lifecycle, context, and errors.

These tests are the completion gate for E5.3 and must pass exactly as written.
Do not edit, skip, or xfail them; implement the contracts they assert instead.

Contract notes:
- ``src/pattern/script.py`` exposes ``ScriptBehavior``, ``ScriptContext``,
  ``ScriptContextError``, and ``SCRIPT_HOOKS``.
- ``ScriptContext`` extends ``StageContext`` and adds the typed script
  helpers ``emit_event``, ``get_player_position``, and
  ``attach_bullet_update`` (rejected by default).
- ``PatternDocument.script`` is ``None`` or a ``ScriptBehavior`` whose
  ``resource_uri`` points at a Python module (``res://...``). The module may
  define hooks ``load(ctx)`` / ``start(ctx)`` / ``update(ctx, frame)`` /
  ``on_event(ctx, event_type, data)`` / ``stop(ctx)``.
- Compilation resolves the script path, syntax-checks it, and reports missing
  files as ``missing_script_resource`` and broken modules as
  ``script_import_error`` through ``PatternCompileError`` diagnostics.
- At runtime ``update`` runs at most once per tick; hooks reach the host
  through the typed ``ScriptContext``, and runtime hook failures surface as
  ``PatternRuntimeError`` with the runner left in the ERROR state.
- ``ScriptContext.attach_bullet_update`` is rejected by default.
- Documents never contain script source text (one-way Python export).
"""

import json
from dataclasses import replace

import pytest

from src.core.project_context import ProjectContext
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.pattern import (
    PatternCompileError,
    PatternCompiler,
    PatternDocument,
    PatternRuntimeError,
    PatternRunner,
    PatternRunnerState,
    ScriptBehavior,
    ScriptContext,
    ScriptContextError,
)
from src.pattern.script import SCRIPT_HOOKS

SCRIPT_SOURCE = '''
def load(ctx):
    ctx.emit_event("script_load", {"note": 1})

def start(ctx):
    ctx.emit_event("script_start", {"note": 2})

def update(ctx, frame):
    ctx.emit_event("script_update", {"frame": frame})

def on_event(ctx, event_type, data):
    ctx.emit_event("script_event", {"type": event_type, "data": data})

def stop(ctx):
    ctx.emit_event("script_stop", {"note": 3})
'''

BROKEN_SOURCE = """
def update(ctx, frame):
    raise RuntimeError("controller exploded")
"""


class DummyPlayer:
    def __init__(self, x=0.0, y=-0.8):
        self.pos = [x, y]


class RecordingScriptContext(ScriptContext):
    """ScriptContext that records typed script interaction with the host."""

    def __init__(self, pool):
        super().__init__(pool, DummyPlayer())
        self.emitted = []

    def emit_event(self, event_type, data):
        self.emitted.append((event_type, data))
        return len(self.emitted) - 1


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


def _document_with_script(tmp_path, source=SCRIPT_SOURCE, name="controller.py"):
    scripts = tmp_path / "game_content" / "scripts"
    scripts.mkdir(parents=True)
    path = scripts / name
    path.write_text(source, encoding="utf-8")
    document = PatternDocument.new("Scripted")
    document.shape = replace(document.shape, count=2)
    document.script = ScriptBehavior(
        resource_uri=f"res://game_content/scripts/{name}"
    )
    return document, _project(tmp_path)


def test_script_hooks_are_exactly_declared():
    assert SCRIPT_HOOKS == ("load", "start", "update", "on_event", "stop")


def test_script_behavior_round_trips_through_the_document(tmp_path):
    document, _ = _document_with_script(tmp_path)

    reloaded = PatternDocument.from_dict(json.loads(json.dumps(document.to_dict())))

    assert reloaded.script == document.script
    assert reloaded.script.resource_uri == document.script.resource_uri


def test_document_never_contains_script_source_text(tmp_path):
    document, _ = _document_with_script(tmp_path)

    payload = document.to_dict()

    assert "script_source" not in payload
    assert "controller.py" in json.dumps(payload)
    assert "emit_event" not in json.dumps(payload)


def test_missing_script_file_reports_structured_diagnostic(tmp_path):
    document = PatternDocument.new()
    document.script = ScriptBehavior(
        resource_uri="res://game_content/scripts/does_not_exist.py"
    )

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document, project=_project(tmp_path))

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "missing_script_resource"
    assert diagnostic.resource_id == document.id
    assert "script.resource_uri" in diagnostic.path


def test_syntax_error_in_script_reports_structured_diagnostic(tmp_path):
    document, project = _document_with_script(
        tmp_path, source="def update(ctx, frame):\n    x = \n", name="broken_syntax.py"
    )

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document, project=project)

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "script_import_error"
    assert "script.resource_uri" in diagnostic.path


def test_lifecycle_hooks_run_in_order_and_update_once_per_tick(tmp_path):
    document, project = _document_with_script(tmp_path)
    program = PatternCompiler().compile(document, project=project)
    pool = OptimizedBulletPool(max_bullets=64)
    context = RecordingScriptContext(pool)
    runner = PatternRunner(program, owner_tag=6001)

    runner.start(context)
    runner.advance(context, 4)
    runner.stop(context)

    emitted = context.emitted
    kinds = [kind for kind, _ in emitted]
    assert kinds[:2] == ["script_load", "script_start"]
    assert kinds[-1] == "script_stop"
    updates = [data["frame"] for kind, data in emitted if kind == "script_update"]
    assert updates == [0, 1, 2, 3]
    assert sum(1 for kind, _ in emitted if kind == "script_update") == 4
    assert not pool.emitter_callbacks
    assert not pool.death_handlers


def test_on_event_hook_receives_typed_event(tmp_path):
    document, project = _document_with_script(tmp_path)
    program = PatternCompiler().compile(document, project=project)
    context = RecordingScriptContext(OptimizedBulletPool(max_bullets=64))
    runner = PatternRunner(program, owner_tag=6002)

    runner.start(context)
    runner.notify_event(context, "boss_defeated", {"phase": 2})
    runner.stop(context)

    received = [
        data
        for kind, data in context.emitted
        if kind == "script_event"
    ]
    assert received == [{"type": "boss_defeated", "data": {"phase": 2}}]


def test_update_runs_once_per_tick_even_for_dense_bullets(tmp_path):
    document, project = _document_with_script(tmp_path)
    document.shape = replace(document.shape, count=512)
    document.schedule = replace(document.schedule, interval_frames=60, burst_count=1)
    program = PatternCompiler().compile(document, project=project)
    pool = OptimizedBulletPool(max_bullets=1024)
    context = RecordingScriptContext(pool)
    runner = PatternRunner(program, owner_tag=6003)

    runner.start(context)
    runner.advance(context, 5)

    assert sum(1 for kind, _ in context.emitted if kind == "script_update") == 5
    assert sum(1 for kind, _ in context.emitted if kind == "script_event") == 0
    assert not pool.emitter_callbacks
    assert not pool.death_handlers


def test_per_bullet_update_registration_is_rejected_by_default(tmp_path):
    document, project = _document_with_script(tmp_path)
    program = PatternCompiler().compile(document, project=project)
    context = RecordingScriptContext(OptimizedBulletPool(max_bullets=64))
    runner = PatternRunner(program, owner_tag=6004)
    runner.start(context)

    with pytest.raises(ScriptContextError, match="per-bullet"):
        context.attach_bullet_update(lambda position: (0.0, 0.0))

    runner.stop(context)


def test_runtime_error_is_structured_and_leaves_runner_in_error_state(tmp_path):
    document, project = _document_with_script(
        tmp_path, source=BROKEN_SOURCE, name="broken_runtime.py"
    )
    program = PatternCompiler().compile(document, project=project)
    context = RecordingScriptContext(OptimizedBulletPool(max_bullets=64))
    runner = PatternRunner(program, owner_tag=6005)
    runner.start(context)

    with pytest.raises(PatternRuntimeError) as caught:
        runner.advance(context, 1)

    assert caught.value.resource_id == document.id
    assert caught.value.frame == 0
    assert "controller exploded" in caught.value.detail
    assert runner.state == PatternRunnerState.ERROR


def test_script_is_optional_and_absent_by_default():
    document = PatternDocument.new()

    assert document.script is None
    program = PatternCompiler().compile(document)
    assert program.script is None

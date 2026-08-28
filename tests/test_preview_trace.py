from __future__ import annotations

import importlib
import sys
from pathlib import Path

from src.authoring.dsl import Project, Ref, Repeat, Stage, Wait
from src.authoring.program import AuthoringProgram
from src.compiler.codegen import CodeGenerator
from src.compiler.package_builder import PackageBuilder
from src.game.stage import StageManager
from src.game.stage.context import StageContext


class _Pool:
    def clear_all(self):
        pass


class _Player:
    pos = (0.0, -0.8)


def test_stage_context_trace_is_sparse_bounded_and_batch_drained():
    context = StageContext(_Pool(), _Player())
    context.AUTHORING_TRACE_LIMIT = 4
    context._authoring_trace = __import__("collections").deque(maxlen=4)
    for index in range(7):
        context.set_runtime_frame(index)
        context.emit_authoring_trace(f"node_{index}", "start")
    assert [item["uid"] for item in context.drain_authoring_trace(2)] == [
        "node_3",
        "node_4",
    ]
    assert context.take_authoring_trace_dropped() == 3
    assert len(context.drain_authoring_trace()) == 2


def test_stage_manager_collects_trace_without_per_bullet_callbacks():
    manager = StageManager()
    context = StageContext(_Pool(), _Player())
    context.emit_authoring_trace("wait", "start")
    context.emit_authoring_trace("wait", "end")
    manager._collect_authoring_trace(context)
    events, dropped = manager.drain_authoring_trace()
    assert [(item["uid"], item["phase"]) for item in events] == [
        ("wait", "start"),
        ("wait", "end"),
    ]
    assert dropped == 0
    assert not hasattr(context, "bullet_trace_callback")


def test_codegen_wraps_real_author_nodes_and_preserves_control_flow():
    program = AuthoringProgram.from_units(
        [
            Project("trace", "Trace", Ref("stage"), [Ref("stage")]),
            Stage(
                "stage",
                "Stage",
                [
                    Repeat(
                        2,
                        [Wait(1, uid="nested_wait")],
                        uid="repeat",
                    )
                ],
            ),
        ]
    )
    result = CodeGenerator(program).generate()
    source = result.modules["stages/stage/stage.py"]
    assert "_pystg_trace(self, 'repeat', 'start')" in source
    assert "_pystg_trace(self, 'repeat', 'end')" in source
    assert "_pystg_trace(self, 'nested_wait', 'start')" in source
    assert "finally:" in source
    compile(source, "stage.py", "exec")


def test_generated_trace_flows_through_real_stage_manager(tmp_path):
    program = AuthoringProgram.from_units(
        [
            Project("trace_runtime", "Trace", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [Wait(3, uid="runtime_wait")]),
        ]
    )
    output_root = tmp_path / "generated"
    PackageBuilder(output_root, project_root=Path.cwd()).build(program)
    sys.path.insert(0, str(output_root))
    importlib.invalidate_caches()
    try:
        entry = importlib.import_module("trace_runtime.entry")
        manager = StageManager()
        pool = _Pool()
        player = _Player()
        manager.bind_engine(pool, player)
        manager.load_stage(entry.START_STAGE)
        observed = []
        for _ in range(400):
            manager.update(1 / 60, pool, player)
            events, _dropped = manager.drain_authoring_trace()
            observed.extend(events)
            if manager.is_finished and not manager.coroutines:
                break
    finally:
        sys.path.remove(str(output_root))
        for name in list(sys.modules):
            if name == "trace_runtime" or name.startswith("trace_runtime."):
                sys.modules.pop(name, None)
        importlib.invalidate_caches()

    assert [(item["uid"], item["phase"]) for item in observed] == [
        ("runtime_wait", "start"),
        ("runtime_wait", "end"),
    ]
    assert observed[0]["frame"] < observed[1]["frame"]

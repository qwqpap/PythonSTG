from __future__ import annotations

from types import ModuleType
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.compiler.content_entry import load_content_entry
from src.compiler.diagnostics import CompilerError
from src.compiler.package_builder import PackageBuilder
from src.authoring.dsl import Project, Ref, Stage, Wait
from src.authoring.program import AuthoringProgram
from src.game.stage.stage_base import StageScript


class DemoStage(StageScript):
    id = "demo"

    async def run(self):
        return None


def _module() -> ModuleType:
    module = ModuleType("test_entry")
    module.STAGES = (DemoStage,)
    module.START_STAGE = DemoStage
    module.STAGE_BY_ID = {"demo": DemoStage}
    module.get_stage = lambda stage_id=None: DemoStage if stage_id in (None, "demo") else (_ for _ in ()).throw(KeyError(stage_id))
    return module


def test_handwritten_entry_loads_through_strict_registry():
    registry = load_content_entry("game_content.entry")

    assert [stage.id for stage in registry.stages] == ["stage1", "stage2", "stage3"]
    assert registry.get_stage() is registry.start_stage
    with pytest.raises(TypeError):
        registry.stage_by_id["other"] = DemoStage


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        (lambda module: setattr(module, "STAGES", [DemoStage]), "invalid_content_entry"),
        (lambda module: setattr(module, "STAGES", (DemoStage, DemoStage)), "entry_duplicate_stage"),
        (lambda module: setattr(module, "START_STAGE", StageScript), "entry_start_stage"),
        (lambda module: setattr(module, "STAGE_BY_ID", {}), "entry_stage_mapping"),
        (lambda module: setattr(module, "get_stage", lambda stage_id=None: StageScript), "entry_get_stage"),
    ),
)
def test_invalid_entry_contract_is_rejected(mutation, code):
    module = _module()
    mutation(module)

    with pytest.raises(CompilerError) as caught:
        load_content_entry(module)

    assert caught.value.code == code


def test_missing_entry_module_has_stable_import_error():
    with pytest.raises(CompilerError) as caught:
        load_content_entry("missing_pystg_content_entry")

    assert caught.value.code == "entry_import_failed"


def test_main_help_loads_a_generated_content_entry(tmp_path):
    program = AuthoringProgram.from_units(
        [
            Project("main_demo", "Main", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Generated", [Wait(1)]),
        ]
    )
    output_root = tmp_path / "generated"
    PackageBuilder(output_root, project_root=Path.cwd()).build(program)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(output_root), environment.get("PYTHONPATH", "")]
    )

    result = subprocess.run(
        [sys.executable, "main.py", "--content-entry", "main_demo.entry", "--help"],
        cwd=Path.cwd(),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "content entry: main_demo.entry" in result.stdout
    assert "stages: stage" in result.stdout

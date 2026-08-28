from __future__ import annotations

from pathlib import Path

import pytest

from src.authoring.dsl import (
    Enemy,
    FireCircle,
    Project,
    Ref,
    SpawnEnemy,
    Spell,
    Stage,
    Wait,
    Wave,
)
from src.authoring.program import AuthoringProgram
from src.compiler.codegen import CodeGenerator
from src.compiler.package_builder import PackageBuilder
from src.compiler.practice import PRACTICE_STAGE_ID, practice_program


def _program():
    return AuthoringProgram.from_units(
        [
            Project("demo", "Demo", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [Wait(1)]),
            Wave("wave", "Wave", [SpawnEnemy(Ref("enemy")), Wait(2)]),
            Enemy("enemy", "Enemy", [FireCircle(count=8), Wait(3)]),
            Spell("spell", "Spell", [FireCircle(count=12), Wait(4)]),
        ]
    )


@pytest.mark.parametrize("unit_id", ["wave", "enemy", "spell"])
def test_standard_practice_program_is_valid_and_compilable(unit_id):
    source = _program()
    original = source.get_unit(unit_id).semantic_data()
    preview = practice_program(source, unit_id)
    preview.assert_valid()
    assert preview.get_unit(PRACTICE_STAGE_ID).kind == "Stage"
    project = next(unit for unit in preview.logical_units() if unit.kind == "Project")
    assert project.id == "demo_practice"
    assert project.metadata["start_stage"] == Ref(PRACTICE_STAGE_ID)
    result = CodeGenerator(preview).generate()
    assert result.manifest["stages"] == [PRACTICE_STAGE_ID]
    assert source.get_unit(unit_id).semantic_data() == original


def test_wave_practice_keeps_transitive_enemy_dependency():
    preview = practice_program(_program(), "wave")
    assert preview.get_unit("wave").kind == "Wave"
    assert preview.get_unit("enemy").kind == "Enemy"


def test_practice_rejects_units_outside_the_contract():
    with pytest.raises(ValueError, match="Wave, Enemy, and Spell"):
        practice_program(_program(), "stage")


@pytest.mark.parametrize("unit_id", ["wave", "enemy", "spell"])
def test_practice_package_passes_independent_compile_and_import(tmp_path, unit_id):
    preview = practice_program(_program(), unit_id)
    target = PackageBuilder(
        tmp_path / unit_id / "generated",
        project_root=Path.cwd(),
    ).build(preview)
    assert (target / "entry.py").is_file()
    assert (target / "stages" / PRACTICE_STAGE_ID / "stage.py").is_file()

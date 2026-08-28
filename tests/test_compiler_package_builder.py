from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from src.authoring.dsl import (
    Parameter,
    PlayBGM,
    Project,
    RawPython,
    Ref,
    SpawnTask,
    Stage,
    Task,
    Wait,
)
from src.authoring.program import AuthoringProgram
from src.authoring.templates import TemplateRegistry, template
from src.compiler.codegen import CodeGenerator
from src.compiler.diagnostics import CompilerError
from src.compiler.package_builder import PackageBuilder, PreparedBuild


def _program(project_id: str = "build_demo") -> AuthoringProgram:
    return AuthoringProgram.from_units(
        [
            Project(project_id, "Build Demo", Ref("stage"), [Ref("stage")]),
            Stage(
                "stage",
                "Stage",
                [Wait(2, uid="wait")],
                bgm="res://assets/audio/music/00.wav",
            ),
        ]
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _manual_prepared(
    builder: PackageBuilder,
    project_id: str,
    payload: str = "new",
) -> PreparedBuild:
    builder.output_root.mkdir(parents=True, exist_ok=True)
    temp_dir = builder.output_root / f"_pystg_build_{project_id}_manual"
    temp_dir.mkdir()
    (temp_dir / "payload.txt").write_text(payload, encoding="utf-8")
    return PreparedBuild(
        project_id=project_id,
        temp_dir=temp_dir,
        target_dir=builder.output_root / project_id,
        manifest={"project_id": project_id},
        source_map=[],
        build_hash="manual",
    )


def _write_old_target(builder: PackageBuilder, project_id: str) -> Path:
    target = builder.output_root / project_id
    target.mkdir(parents=True)
    (target / "payload.txt").write_text("old", encoding="utf-8")
    return target


def test_prepare_runs_real_subprocess_validation_and_publish_is_deterministic(tmp_path):
    output_root = tmp_path / "generated"
    builder = PackageBuilder(output_root, project_root=Path.cwd())

    first = builder.prepare(_program())
    first_snapshot = _snapshot(first.temp_dir)
    target = builder.publish(first)
    second = builder.prepare(_program())
    second_snapshot = _snapshot(second.temp_dir)

    assert first_snapshot == second_snapshot
    assert second.build_hash == first.build_hash
    assert json.loads((target / "manifest.json").read_text(encoding="utf-8"))["project_id"] == "build_demo"
    assert json.loads((target / "source_map.json").read_text(encoding="utf-8"))[0]["uid"] == "wait"
    assert not list(target.rglob("__pycache__"))
    assert not list(target.rglob("*.pyc"))
    assert not list(target.rglob("*.ogg"))
    builder.publish(second)
    assert _snapshot(target) == first_snapshot


def test_failed_prepare_preserves_last_successful_package(tmp_path):
    builder = PackageBuilder(tmp_path / "generated", project_root=Path.cwd())
    target = _write_old_target(builder, "build_demo")
    before = _snapshot(target)
    invalid = AuthoringProgram.from_units(
        [
            Project("build_demo", "Bad", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Bad", [RawPython("if:", uid="bad_raw")]),
        ]
    )

    with pytest.raises(CompilerError):
        builder.prepare(invalid)

    assert _snapshot(target) == before
    assert not list(builder.output_root.glob("_pystg_build_*"))


def test_missing_resource_blocks_prepare_and_identifies_author_node(tmp_path):
    builder = PackageBuilder(tmp_path / "generated", project_root=Path.cwd())
    program = AuthoringProgram.from_units(
        [
            Project("missing_resource", "Missing", Ref("stage"), [Ref("stage")]),
            Stage(
                "stage",
                "Stage",
                [
                    PlayBGM(
                        "res://assets/audio/music/does-not-exist.ogg",
                        uid="missing_bgm",
                    )
                ],
            ),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        builder.prepare(program)

    assert caught.value.code == "resource_not_found"
    assert caught.value.diagnostics[0].uid == "missing_bgm"
    assert not list(builder.output_root.glob("_pystg_build_*"))


def test_missing_resource_in_task_parameter_default_blocks_prepare(tmp_path):
    builder = PackageBuilder(tmp_path / "generated", project_root=Path.cwd())
    program = AuthoringProgram.from_units(
        [
            Project("missing_default", "Missing", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [SpawnTask(Ref("task"))]),
            Task(
                "task",
                "Task",
                [Parameter("asset", "str", "res://assets/does-not-exist.wav")],
                [Wait(1)],
            ),
        ]
    )

    with pytest.raises(CompilerError) as caught:
        builder.prepare(program)

    assert caught.value.code == "resource_not_found"
    assert caught.value.diagnostics[0].unit_id == "task"
    assert not list(builder.output_root.glob("_pystg_build_*"))


def test_missing_resource_from_template_maps_call_and_definition(tmp_path):
    @template
    def missing_music():
        return [PlayBGM("res://assets/audio/music/does-not-exist.ogg")]

    registry = TemplateRegistry.with_builtins()
    registry.register(missing_music)
    program = AuthoringProgram.from_units(
        [
            Project("missing_template_resource", "Missing", Ref("stage"), [Ref("stage")]),
            Stage("stage", "Stage", [missing_music(uid="missing_music_call")]),
        ]
    )
    generator = CodeGenerator(program, template_registry=registry)

    with pytest.raises(CompilerError) as caught:
        generator.validate_resources(Path.cwd())

    diagnostic = caught.value.diagnostics[0]
    assert caught.value.code == "resource_not_found"
    assert diagnostic.uid == "missing_music_call"
    assert diagnostic.related
    assert "test_compiler_package_builder.py" in diagnostic.related[0].source_path


def test_publish_interruption_rolls_back_previous_package(tmp_path, monkeypatch):
    builder = PackageBuilder(tmp_path / "generated", project_root=Path.cwd())
    target = _write_old_target(builder, "build_demo")
    before = _snapshot(target)
    prepared = _manual_prepared(builder, "build_demo")
    real_replace = os.replace

    def fail_new_package(source, destination):
        if Path(source).resolve() == prepared.temp_dir.resolve():
            raise OSError("simulated locked target")
        return real_replace(source, destination)

    monkeypatch.setattr("src.compiler.package_builder.os.replace", fail_new_package)

    with pytest.raises(CompilerError) as caught:
        builder.publish(prepared)

    assert caught.value.code == "publish_failed"
    assert _snapshot(target) == before
    assert prepared.temp_dir.exists()
    assert not list(builder.output_root.glob("_pystg_backup_*"))


def test_publish_retries_a_transient_windows_directory_lock(tmp_path, monkeypatch):
    assert os.name == "nt", "CD6 targets the fixed Windows 11 platform"
    builder = PackageBuilder(tmp_path / "generated", project_root=Path.cwd())
    prepared = _manual_prepared(builder, "build_demo")
    real_replace = os.replace
    attempts = 0

    def transient_then_replace(source, destination):
        nonlocal attempts
        if Path(source).resolve() == prepared.temp_dir.resolve() and attempts == 0:
            attempts += 1
            error = OSError("transient scanner lock")
            error.winerror = 5
            raise error
        return real_replace(source, destination)

    monkeypatch.setattr("src.compiler.package_builder.os.replace", transient_then_replace)
    published = builder.publish(prepared)

    assert attempts == 1
    assert published.is_dir()
    assert not prepared.temp_dir.exists()


def test_backup_cleanup_failure_keeps_valid_new_package_and_reports_warning(tmp_path, monkeypatch):
    builder = PackageBuilder(tmp_path / "generated", project_root=Path.cwd())
    target = _write_old_target(builder, "build_demo")
    before = _snapshot(target)
    prepared = _manual_prepared(builder, "build_demo")
    new_snapshot = _snapshot(prepared.temp_dir)
    real_rmtree = shutil.rmtree

    def fail_backup_cleanup(path, *args, **kwargs):
        if Path(path).name.startswith("_pystg_backup_"):
            raise OSError("simulated locked backup")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("src.compiler.package_builder.shutil.rmtree", fail_backup_cleanup)

    with pytest.warns(RuntimeWarning, match="previous backup could not be removed"):
        published = builder.publish(prepared)

    assert published == target
    assert _snapshot(target) == new_snapshot
    assert _snapshot(target) != before
    assert not prepared.temp_dir.exists()
    assert len(list(builder.output_root.glob("_pystg_backup_*"))) == 1


def test_prepared_build_from_another_output_root_is_rejected(tmp_path):
    first = PackageBuilder(tmp_path / "one", project_root=Path.cwd())
    second = PackageBuilder(tmp_path / "two", project_root=Path.cwd())
    prepared = _manual_prepared(first, "build_demo")

    with pytest.raises(CompilerError) as caught:
        second.publish(prepared)

    assert caught.value.code == "invalid_output_path"
    assert prepared.temp_dir.exists()

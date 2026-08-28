"""Prepare, independently validate, and atomically publish generated packages."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.authoring.program import AuthoringProgram

from .codegen import CodeGenerator
from .diagnostics import CompilerError


@dataclass(frozen=True)
class PreparedBuild:
    project_id: str
    temp_dir: Path
    target_dir: Path
    manifest: dict[str, Any]
    source_map: list[dict[str, Any]]
    build_hash: str


class PackageBuilder:
    """Own the filesystem transaction, but never own or stop a preview process."""

    def __init__(
        self,
        output_root: str | Path | None = None,
        *,
        project_root: str | Path | None = None,
        source_root: str | Path | None = None,
        python_executable: str | Path | None = None,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[2]
        self.project_root = Path(project_root or repository_root).resolve()
        self.output_root = Path(
            output_root or self.project_root / "game_content" / "generated"
        ).resolve()
        self.source_root = Path(source_root).resolve() if source_root is not None else None
        self.python_executable = str(python_executable or sys.executable)

    def prepare(self, program: AuthoringProgram) -> PreparedBuild:
        generator = CodeGenerator(program, source_root=self.source_root)
        generator.validate_resources(self.project_root)
        result = generator.generate()
        project_id = generator.project_id
        self.output_root.mkdir(parents=True, exist_ok=True)
        target_dir = (self.output_root / project_id).resolve()
        if target_dir.parent != self.output_root:
            raise CompilerError("invalid_output_path", "generated target escaped output_root")
        temp_dir = (
            self.output_root
            / f"_pystg_build_{project_id}_{uuid.uuid4().hex}"
        ).resolve()

        try:
            temp_dir.mkdir(parents=False, exist_ok=False)
            for relative_path, source in result.modules.items():
                destination = (temp_dir / relative_path).resolve()
                if temp_dir not in destination.parents:
                    raise CompilerError(
                        "invalid_generated_path",
                        f"generated path escaped package: {relative_path!r}",
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                _write_text(destination, source)
            _write_json(temp_dir / "manifest.json", result.manifest)
            _write_json(temp_dir / "source_map.json", result.source_map)
            self._validate_subprocess(temp_dir)
            _remove_bytecode(temp_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        return PreparedBuild(
            project_id=project_id,
            temp_dir=temp_dir,
            target_dir=target_dir,
            manifest=result.manifest,
            source_map=result.source_map,
            build_hash=result.build_hash,
        )

    def publish(self, prepared: PreparedBuild) -> Path:
        temp_dir = prepared.temp_dir.resolve()
        target_dir = prepared.target_dir.resolve()
        expected_temp_prefix = f"_pystg_build_{prepared.project_id}_"
        if (
            temp_dir.parent != self.output_root
            or target_dir.parent != self.output_root
            or target_dir.name != prepared.project_id
            or not temp_dir.name.startswith(expected_temp_prefix)
        ):
            raise CompilerError(
                "invalid_output_path",
                "prepared build is outside this PackageBuilder output_root",
            )
        if not temp_dir.is_dir():
            raise CompilerError(
                "build_missing",
                f"prepared build directory is missing: {temp_dir}",
            )

        backup_dir = (
            self.output_root
            / f"_pystg_backup_{prepared.project_id}_{uuid.uuid4().hex}"
        ).resolve()
        if backup_dir.parent != self.output_root:
            raise CompilerError(
                "invalid_output_path",
                "generated backup escaped this PackageBuilder output_root",
            )
        had_target = target_dir.exists()
        if had_target:
            try:
                os.replace(target_dir, backup_dir)
            except OSError as exc:
                raise CompilerError(
                    "publish_failed",
                    f"cannot move current generated package to backup: {exc}",
                ) from exc

        try:
            os.replace(temp_dir, target_dir)
        except OSError as publish_error:
            rollback_error: OSError | None = None
            if had_target and backup_dir.exists():
                try:
                    os.replace(backup_dir, target_dir)
                except OSError as exc:
                    rollback_error = exc
            message = f"cannot publish prepared package: {publish_error}"
            if rollback_error is not None:
                message += f"; rollback also failed: {rollback_error}"
            raise CompilerError("publish_failed", message) from publish_error

        if backup_dir.exists():
            try:
                shutil.rmtree(backup_dir)
            except OSError as cleanup_error:
                warnings.warn(
                    "generated package was published, but the previous backup "
                    f"could not be removed: {backup_dir}: {cleanup_error}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        return target_dir

    def build(self, program: AuthoringProgram) -> Path:
        return self.publish(self.prepare(program))

    def _validate_subprocess(self, build_dir: Path) -> None:
        compile_result = subprocess.run(
            [
                self.python_executable,
                "-m",
                "compileall",
                "-q",
                "-f",
                str(build_dir),
            ],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if compile_result.returncode != 0:
            raise CompilerError(
                "generated_compile_failed",
                _subprocess_message("compileall", compile_result),
            )

        module_name = f"{build_dir.name}.entry"
        verification = "\n".join(
            (
                "import sys",
                f"sys.path.insert(0, {str(self.project_root)!r})",
                f"sys.path.insert(0, {str(self.output_root)!r})",
                "from src.compiler.content_entry import load_content_entry",
                f"registry = load_content_entry({module_name!r})",
                "assert registry.stages",
                "assert registry.get_stage() is registry.start_stage",
                "for stage_id, stage in registry.stage_by_id.items():",
                "    assert registry.get_stage(stage_id) is stage",
            )
        )
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        import_result = subprocess.run(
            [self.python_executable, "-c", verification],
            cwd=self.project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if import_result.returncode != 0:
            raise CompilerError(
                "generated_import_failed",
                _subprocess_message("entry import", import_result),
            )


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\r\n", "\n").replace("\r", "\n"))


def _write_json(path: Path, value: Any) -> None:
    _write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=4, sort_keys=True) + "\n",
    )


def _remove_bytecode(root: Path) -> None:
    for directory in sorted(root.rglob("__pycache__"), reverse=True):
        shutil.rmtree(directory)
    for path in root.rglob("*.py[co]"):
        path.unlink()


def _subprocess_message(label: str, result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stderr or result.stdout or "no subprocess output").strip()
    return f"generated {label} validation failed: {output}"


__all__ = ["PackageBuilder", "PreparedBuild"]

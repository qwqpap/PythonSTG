"""Prepare, independently validate, and atomically publish generated packages."""

from __future__ import annotations

import json
import os
import pickle
import shutil
import subprocess
import sys
import time
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.authoring.program import AuthoringProgram

from .diagnostics import CompilerError


@dataclass(frozen=True)
class PreparedBuild:
    project_id: str
    temp_dir: Path
    target_dir: Path
    manifest: dict[str, Any]
    source_map: list[dict[str, Any]]
    build_hash: str


@dataclass
class PublishedBuild:
    """Keep the previous package until the new game has actually started."""

    target_dir: Path
    backup_dir: Path | None
    active: bool = True

    def commit(self) -> None:
        if not self.active:
            return
        if self.backup_dir is not None and self.backup_dir.exists():
            try:
                shutil.rmtree(self.backup_dir)
            except OSError as exc:
                warnings.warn(f"cannot remove previous build backup: {exc}", RuntimeWarning)
        self.active = False

    def rollback(self) -> None:
        if not self.active:
            return
        failed = self.target_dir.with_name(f"_pystg_failed_{uuid.uuid4().hex}")
        if self.target_dir.exists():
            _replace_directory(self.target_dir, failed)
        try:
            if self.backup_dir is not None:
                _replace_directory(self.backup_dir, self.target_dir)
        except OSError:
            if failed.exists() and not self.target_dir.exists():
                _replace_directory(failed, self.target_dir)
            raise
        self.active = False
        if failed.exists():
            try:
                shutil.rmtree(failed)
            except OSError as exc:
                warnings.warn(f"previous build restored; cannot clean rejected package: {exc}", RuntimeWarning)


class PackageBuilder:
    """Own the filesystem transaction, but never own or stop a preview process."""

    BUILD_TIMEOUT_SECONDS = 60

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
        request, staging = self.worker_request(program)
        succeeded = False
        try:
            result = subprocess.run(
                self.worker_command(),
                input=request,
                cwd=self.project_root,
                capture_output=True,
                timeout=self.BUILD_TIMEOUT_SECONDS,
                check=False,
                env=self.worker_environment(),
            )
            prepared = self.decode_worker_result(result.stdout, result.returncode, result.stderr)
            succeeded = True
            return prepared
        except subprocess.TimeoutExpired as exc:
            raise CompilerError("build_timeout", "build exceeded the 60 second limit") from exc
        finally:
            if staging.exists() and not succeeded:
                shutil.rmtree(staging, ignore_errors=True)

    def worker_command(self) -> list[str]:
        return [self.python_executable, "-u", str(Path(__file__).with_name("build_worker.py"))]

    def worker_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        return environment

    def worker_request(self, program: AuthoringProgram) -> tuple[bytes, Path]:
        projects = [unit for unit in program.logical_units() if unit.kind == "Project"]
        if len(projects) != 1:
            raise CompilerError("invalid_project", "build requires exactly one Project")
        project_id = projects[0].id
        staging = self.output_root / f"_pystg_build_{project_id}_{uuid.uuid4().hex}"
        # This is a private trusted local pipe, not an authoring file format.
        request = pickle.dumps({
            "program": program,
            "project_root": self.project_root,
            "source_root": self.source_root,
            "output_root": self.output_root,
            "staging": staging,
        }, protocol=pickle.HIGHEST_PROTOCOL)
        return request, staging

    @staticmethod
    def decode_worker_result(stdout: bytes, exit_code: int, stderr: bytes = b"") -> PreparedBuild:
        try:
            result = pickle.loads(stdout)
        except Exception as exc:
            detail = stderr[-64 * 1024:].decode("utf-8", errors="replace")
            raise CompilerError("build_worker_failed", f"build worker exited {exit_code}: {detail}") from exc
        if not result.get("ok"):
            raise CompilerError(result.get("code", "build_failed"), result.get("message", "build failed"), result.get("diagnostics", ()))
        prepared = result.get("prepared")
        if exit_code != 0 or not isinstance(prepared, PreparedBuild):
            raise CompilerError("build_worker_failed", "worker returned an invalid build result")
        return prepared

    def _prepare_local(self, program: AuthoringProgram, staging: Path) -> PreparedBuild:
        """Only called inside the fresh, cancellable build worker."""
        from .codegen import CodeGenerator

        generator = CodeGenerator(program, source_root=self.source_root)
        generator.validate_resources(self.project_root)
        result = generator.generate()
        project_id = generator.project_id
        self.output_root.mkdir(parents=True, exist_ok=True)
        target_dir = (self.output_root / project_id).resolve()
        if target_dir.parent != self.output_root:
            raise CompilerError("invalid_output_path", "generated target escaped output_root")
        temp_dir = staging.resolve()
        if temp_dir.parent != self.output_root or not temp_dir.name.startswith(f"_pystg_build_{project_id}_"):
            raise CompilerError("invalid_output_path", "build staging escaped output_root")

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
            self._validate_package(temp_dir)
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
        published = self.begin_publish(prepared)
        published.commit()
        return published.target_dir

    def begin_publish(self, prepared: PreparedBuild) -> PublishedBuild:
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
                _replace_directory(target_dir, backup_dir)
            except OSError as exc:
                raise CompilerError(
                    "publish_failed",
                    f"cannot move current generated package to backup: {exc}",
                ) from exc

        try:
            _replace_directory(temp_dir, target_dir)
        except OSError as publish_error:
            rollback_error: OSError | None = None
            if had_target and backup_dir.exists():
                try:
                    _replace_directory(backup_dir, target_dir)
                except OSError as exc:
                    rollback_error = exc
            message = f"cannot publish prepared package: {publish_error}"
            if rollback_error is not None:
                message += f"; rollback also failed: {rollback_error}"
            raise CompilerError("publish_failed", message) from publish_error

        return PublishedBuild(target_dir, backup_dir if had_target else None)

    def build(self, program: AuthoringProgram) -> Path:
        return self.publish(self.prepare(program))

    def _validate_package(self, build_dir: Path) -> None:
        # Generation and validation already run in an independent interpreter.
        # Keeping validation here avoids orphan grandchildren on cancellation.
        from .content_entry import load_content_entry
        from src.game.stage.stage_base import StageScript

        for path in build_dir.rglob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        sys.path.insert(0, str(self.output_root))
        registry = load_content_entry(f"{build_dir.name}.entry")
        if not registry.stages or registry.get_stage() is not registry.start_stage:
            raise CompilerError("generated_import_failed", "invalid generated Stage registry")
        for stage_id, stage in registry.stage_by_id.items():
            if registry.get_stage(stage_id) is not stage or not isinstance(stage(), StageScript):
                raise CompilerError("generated_runtime_failed", "generated stage is not a Runtime StageScript")


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\r\n", "\n").replace("\r", "\n"))


def _replace_directory(source: Path, target: Path, *, timeout: float = 1.5) -> None:
    """Retry only transient Windows sharing/access failures around atomic rename."""

    deadline = time.monotonic() + timeout
    while True:
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            transient = os.name == "nt" and getattr(exc, "winerror", None) in {5, 32, 33}
            if not transient or time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


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


__all__ = ["PackageBuilder", "PreparedBuild", "PublishedBuild"]

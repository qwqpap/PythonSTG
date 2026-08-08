"""Atomic persistence for generic typed authoring resources."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.atomic_io import atomic_write_json
from src.core.project_context import ProjectContext, get_project_context

from .registry import ResourceTypeRegistry, build_default_resource_type_registry
from .resources import ResourceDocumentError


@dataclass(frozen=True)
class RecoveryCandidate:
    original_path: Path
    autosave_path: Path


class ResourceStore:
    def __init__(
        self,
        project: ProjectContext | None = None,
        registry: ResourceTypeRegistry | None = None,
    ) -> None:
        self.project = project or get_project_context()
        self.registry = registry or build_default_resource_type_registry()

    def _path(self, path: str | Path) -> Path:
        resolved = self.project.resolve(path)
        self.project.relative(resolved)
        return resolved

    def load(self, path: str | Path) -> Any:
        source = self._path(path)
        data = self._read_json(source)
        return self.registry.load(data)

    @staticmethod
    def _read_json(source: Path) -> Any:
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ResourceDocumentError(f"{source}: cannot read resource: {exc}") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ResourceDocumentError(
                f"{source}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc

    def save(self, document: Any, path: str | Path) -> Path:
        target = self._path(path)
        payload = document.to_dict()
        # Loading through the registry proves current schema/type validation
        # before the atomic replacement is attempted.
        validated = self.registry.load(payload)
        # Persist the registry-normalized current representation so saving an
        # older envelope cannot immediately reopen as a semantically different
        # document after migration.
        canonical_payload = validated.to_dict()
        return atomic_write_json(target, canonical_payload)

    def autosave(self, document: Any, path: str | Path) -> Path:
        """Write an atomic ``<name>.autosave.json`` sidecar for recovery."""
        target = self._path(path)
        sidecar = target.with_suffix(target.suffix + ".autosave.json")
        payload = document.to_dict()
        validated = self.registry.load(payload)
        return atomic_write_json(sidecar, validated.to_dict())

    def recover_autosave(self, path: str | Path):
        """Load the autosave sidecar when present; never touches the original."""
        target = self._path(path)
        sidecar = target.with_suffix(target.suffix + ".autosave.json")
        if not sidecar.is_file():
            return None
        data = self._read_json(sidecar)
        recovered = self.registry.load(data)
        if target.is_file():
            original = self._read_json(target)
            if isinstance(original, dict):
                original_id = original.get("id")
                original_type = original.get("type")
                recovered_id = getattr(getattr(recovered, "header", None), "id", None)
                recovered_type = getattr(recovered, "type", None)
                if (
                    original_id is not None
                    and recovered_id is not None
                    and str(original_id) != str(recovered_id)
                ) or (
                    original_type is not None
                    and recovered_type is not None
                    and str(original_type) != str(recovered_type)
                ):
                    raise ResourceDocumentError(
                        f"{sidecar}: autosave identity/type does not match {target}"
                    )
        return recovered

    def recovery_candidates(self) -> tuple[RecoveryCandidate, ...]:
        """List sidecars without modifying originals or loading documents."""
        candidates: list[RecoveryCandidate] = []
        for sidecar in self.project.root.rglob("*.pystg.json.autosave.json"):
            try:
                original = sidecar.with_name(
                    sidecar.name.removesuffix(".autosave.json")
                )
                self.project.relative(original)
            except (OSError, ValueError):
                continue
            candidates.append(RecoveryCandidate(original, sidecar))
        return tuple(sorted(candidates, key=lambda item: str(item.original_path)))

"""Atomic persistence for generic typed authoring resources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.atomic_io import atomic_write_json
from src.core.project_context import ProjectContext, get_project_context

from .registry import ResourceTypeRegistry, build_default_resource_type_registry


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
        data = json.loads(source.read_text(encoding="utf-8"))
        return self.registry.load(data)

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

"""Atomic scene document persistence constrained to a project root."""

from __future__ import annotations

import json
from pathlib import Path

from src.core.atomic_io import atomic_write_json
from src.core.project_context import ProjectContext, get_project_context

from .document import DocumentError, SceneDocument


class DocumentStore:
    def __init__(self, project: ProjectContext | None = None):
        self.project = project or get_project_context()

    def _path(self, path: str | Path) -> Path:
        resolved = self.project.resolve(path)
        self.project.relative(resolved)
        return resolved

    def load(self, path: str | Path) -> SceneDocument:
        source = self._path(path)
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DocumentError(f"Invalid JSON in {source}: {exc}") from exc
        return SceneDocument.from_dict(data)

    def save(self, document: SceneDocument, path: str | Path, *, canonical: bool = False) -> Path:
        target = self._path(path)
        payload = document.to_canonical_dict() if canonical else document.to_dict()
        return atomic_write_json(target, payload)

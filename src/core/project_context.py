"""Project-root discovery and path resolution.

Runtime and editor code should resolve project files through ``ProjectContext``
instead of depending on the process working directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


PROJECT_MARKERS = ("project.pystg.json", "pyproject.toml")


class ProjectContextError(RuntimeError):
    """Raised when a PySTG project root cannot be located."""


@dataclass(frozen=True)
class ProjectContext:
    root: Path

    _current: ClassVar["ProjectContext | None"] = None

    def __post_init__(self) -> None:
        root = Path(self.root).expanduser().resolve()
        if not root.is_dir():
            raise ProjectContextError(f"Project root is not a directory: {root}")
        object.__setattr__(self, "root", root)

    @classmethod
    def discover(cls, start: str | Path | None = None) -> "ProjectContext":
        candidate = Path(start or Path.cwd()).expanduser().resolve()
        if candidate.is_file():
            candidate = candidate.parent

        for directory in (candidate, *candidate.parents):
            if any((directory / marker).is_file() for marker in PROJECT_MARKERS):
                if (directory / "assets").is_dir() and (directory / "game_content").is_dir():
                    return cls(directory)

        raise ProjectContextError(
            f"Could not find a PySTG project above {candidate}. "
            "Expected pyproject.toml (or project.pystg.json), assets/, and game_content/."
        )

    @classmethod
    def current(cls) -> "ProjectContext":
        if cls._current is None:
            cls._current = cls.discover()
        return cls._current

    @classmethod
    def set_current(cls, context: "ProjectContext") -> "ProjectContext":
        cls._current = context
        return context

    @property
    def assets(self) -> Path:
        return self.root / "assets"

    @property
    def game_content(self) -> Path:
        return self.root / "game_content"

    @property
    def userdata(self) -> Path:
        return self.root / "userdata"

    def resolve(self, path: str | Path) -> Path:
        value = Path(path).expanduser()
        return value.resolve() if value.is_absolute() else (self.root / value).resolve()

    def relative(self, path: str | Path) -> Path:
        resolved = self.resolve(path)
        try:
            return resolved.relative_to(self.root)
        except ValueError as exc:
            raise ProjectContextError(f"Path is outside the project: {resolved}") from exc

    def activate(self) -> "ProjectContext":
        """Set this context as current and provide legacy cwd compatibility."""
        ProjectContext.set_current(self)
        os.chdir(self.root)
        return self


def get_project_context(start: str | Path | None = None) -> ProjectContext:
    if start is not None:
        return ProjectContext.set_current(ProjectContext.discover(start))
    return ProjectContext.current()

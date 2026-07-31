"""Single project-scoped entry point for resource access.

The runtime atlas loader and the richer editor parser have different internal
representations.  ``ResourceService`` owns both during the compatibility
period so callers no longer construct competing global managers themselves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.core.project_context import ProjectContext, get_project_context

from .texture_asset import TextureAssetManager, init_texture_asset_manager
from .unified_texture import UnifiedTextureManager


class ResourceService:
    def __init__(
        self,
        project: ProjectContext | None = None,
        asset_root: str | Path | None = None,
    ):
        self.project = project or get_project_context()
        self.asset_root = (
            self.project.assets
            if asset_root is None
            else self.project.resolve(asset_root)
        )
        self.runtime = init_texture_asset_manager(str(self.asset_root))
        self._editor: Optional[UnifiedTextureManager] = None

    @property
    def textures(self) -> TextureAssetManager:
        """Canonical texture catalog used by the game runtime."""
        return self.runtime

    @property
    def editor(self) -> UnifiedTextureManager:
        """Compatibility model for rich editor-only asset types.

        New editor code should obtain it through this service rather than
        constructing ``UnifiedTextureManager`` directly.
        """
        if self._editor is None:
            self._editor = UnifiedTextureManager(str(self.asset_root))
        return self._editor

    def asset_path(self, path: str | Path) -> Path:
        value = Path(path)
        resolved = value.resolve() if value.is_absolute() else (self.asset_root / value).resolve()
        try:
            resolved.relative_to(self.asset_root)
        except ValueError as exc:
            raise ValueError(f"Resource path is outside assets/: {resolved}") from exc
        return resolved

    def relative_asset_path(self, path: str | Path) -> Path:
        return self.asset_path(path).relative_to(self.asset_root)

    def load_runtime_catalog(self, folder: str | Path = "images") -> bool:
        folder_path = self.asset_path(folder)
        return self.runtime.load_sprite_config_folder(str(folder_path))

    def load_editor_config(self, path: str | Path):
        relative = self.relative_asset_path(path)
        return self.editor.load_config(str(relative))


_resource_service: ResourceService | None = None


def init_resource_service(
    project: ProjectContext | None = None,
    asset_root: str | Path | None = None,
) -> ResourceService:
    global _resource_service
    _resource_service = ResourceService(project=project, asset_root=asset_root)
    return _resource_service


def get_resource_service() -> ResourceService:
    global _resource_service
    if _resource_service is None:
        _resource_service = ResourceService()
    return _resource_service

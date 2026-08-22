"""Qt workbench contributions owned by the editor plugin facade."""

from __future__ import annotations

from src.authoring.registry import register_editor_factory
from src.authoring.resources import BACKGROUND_RESOURCE_TYPE, UI_RESOURCE_TYPE
from src.core.project_context import ProjectContext

from ..workbench import EditorPlugin, PluginMode, PluginRegistry


def _make_ui_workspace(*args, **kwargs):
    from ..panels.ui_workspace import UIWorkspace

    return UIWorkspace(*args, **kwargs)


def _make_background_workspace(*args, **kwargs):
    from ..panels.ui_workspace import BackgroundWorkspace

    return BackgroundWorkspace(*args, **kwargs)


class WorkbenchAdapter:
    """Own the Qt view catalog and install its authoring factory ports."""

    def __init__(self, project: ProjectContext) -> None:
        self._catalog = PluginRegistry(project)
        register_editor_factory(UI_RESOURCE_TYPE, _make_ui_workspace)
        register_editor_factory(BACKGROUND_RESOURCE_TYPE, _make_background_workspace)

    def contains(self, plugin_id: str) -> bool:
        return plugin_id in self._catalog._plugins

    def register(self, plugin: EditorPlugin) -> EditorPlugin:
        return self._catalog.register(plugin)

    def get(self, plugin_id: str) -> EditorPlugin:
        return self._catalog.get(plugin_id)

    def all(self) -> tuple[EditorPlugin, ...]:
        return self._catalog.all()

    def by_mode(self, mode: PluginMode) -> tuple[EditorPlugin, ...]:
        return self._catalog.by_mode(mode)

    @property
    def plugins(self) -> dict[str, EditorPlugin]:
        return self._catalog._plugins


__all__ = ["WorkbenchAdapter"]

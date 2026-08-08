"""Plugin descriptors and registry for the unified editor workbench."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from src.qt_compat.QtWidgets import QWidget

from src.core.project_context import ProjectContext


PluginMode = Literal["central", "bottom", "external"]
WidgetFactory = Callable[[], QWidget]


@dataclass(frozen=True)
class EditorPlugin:
    id: str
    title: str
    description: str
    mode: PluginMode
    factory: WidgetFactory | None = None
    script: Path | None = None
    shortcut: str | None = None

    def validate(self, project: ProjectContext) -> None:
        if not self.id or not self.title:
            raise ValueError("Editor plugins require a stable id and title")
        if self.mode not in {"central", "bottom", "external"}:
            raise ValueError(f"Unsupported editor plugin mode: {self.mode}")
        if self.mode in {"central", "bottom"} and self.factory is None:
            raise ValueError(f"Plugin {self.id!r} requires a widget factory")
        if self.mode == "external":
            if self.script is None:
                raise ValueError(f"External plugin {self.id!r} requires a script")
            project.relative(self.script)


class PluginRegistry:
    def __init__(self, project: ProjectContext):
        self.project = project
        self._plugins: dict[str, EditorPlugin] = {}

    def register(self, plugin: EditorPlugin) -> EditorPlugin:
        plugin.validate(self.project)
        if plugin.id in self._plugins:
            raise ValueError(f"Duplicate editor plugin id: {plugin.id}")
        self._plugins[plugin.id] = plugin
        return plugin

    def get(self, plugin_id: str) -> EditorPlugin:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise KeyError(f"Unknown editor plugin: {plugin_id}") from exc

    def all(self) -> tuple[EditorPlugin, ...]:
        return tuple(self._plugins.values())

    def by_mode(self, mode: PluginMode) -> tuple[EditorPlugin, ...]:
        return tuple(plugin for plugin in self._plugins.values() if plugin.mode == mode)


def default_external_plugins(project: ProjectContext) -> tuple[EditorPlugin, ...]:
    tools = project.root / "tools"
    definitions = (
        (
            "texture_editor",
            "Texture Assets",
            "Edit atlases, sprite regions, animations and laser configuration.",
            "asset/asset_manager_qt.py",
        ),
        (
            "player_editor",
            "Player",
            "Edit player animation, stats, shots and options.",
            "player/player_editor.py",
        ),
        (
            "enemy_editor",
            "Enemy Aliases",
            "Edit enemy sprite aliases and atlas zones.",
            "enemy/enemy_alias_manager.py",
        ),
        (
            "background_editor",
            "Background",
            "Edit data-driven stage background layers.",
            "stage/background_editor.py",
        ),
        (
            "danmaku_editor",
            "Danmaku Script",
            "Edit bullet patterns, timelines and generated async code.",
            "stage/danmaku_script_editor.py",
        ),
        (
            "dialog_balloon_editor",
            "Dialog Balloon",
            "Edit dialog balloon assembly and layout.",
            "dialog/dialog_balloon_editor.py",
        ),
        (
            "dialog_portrait_editor",
            "Dialog Portrait",
            "Edit dialog portrait placement and appearance.",
            "dialog/dialog_portrait_editor.py",
        ),
        (
            "main_menu_editor",
            "Main Menu",
            "Edit the GLFW/ImGui main-menu layout.",
            "main_menu_editor/run.py",
        ),
        (
            "portrait_layout_editor",
            "Portrait Layout",
            "Edit the GLFW/ImGui portrait render layout.",
            "portrait_editor/run.py",
        ),
    )
    return tuple(
        EditorPlugin(
            id=plugin_id,
            title=title,
            description=description,
            mode="external",
            script=tools / relative,
        )
        for plugin_id, title, description, relative in definitions
    )

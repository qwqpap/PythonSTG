from pathlib import Path

import pytest

from src.core.project_context import ProjectContext, ProjectContextError
from src.editor.workbench import (
    EditorPlugin,
    PluginRegistry,
    default_external_plugins,
)


def test_plugin_registry_validates_modes_and_duplicate_ids(tmp_path):
    project = ProjectContext(tmp_path)
    registry = PluginRegistry(project)
    plugin = EditorPlugin(
        id="panel",
        title="Panel",
        description="Test panel",
        mode="bottom",
        factory=lambda: None,
    )

    assert registry.register(plugin) is plugin
    assert registry.get("panel") is plugin
    assert registry.by_mode("bottom") == (plugin,)
    with pytest.raises(ValueError, match="Duplicate"):
        registry.register(plugin)
    with pytest.raises(ValueError, match="factory"):
        registry.register(
            EditorPlugin(
                id="broken",
                title="Broken",
                description="",
                mode="central",
            )
        )
    with pytest.raises(ValueError, match="mode"):
        registry.register(
            EditorPlugin(
                id="unknown",
                title="Unknown",
                description="",
                mode="floating",
                factory=lambda: None,
            )
        )


def test_external_plugins_stay_inside_project_and_keep_legacy_entrypoints(tmp_path):
    project = ProjectContext(tmp_path)
    plugins = default_external_plugins(project)

    assert len(plugins) == 9
    assert all(plugin.mode == "external" for plugin in plugins)
    assert all(plugin.script.suffix == ".py" for plugin in plugins)
    assert {plugin.id for plugin in plugins} >= {
        "texture_editor",
        "player_editor",
        "danmaku_editor",
    }

    registry = PluginRegistry(project)
    with pytest.raises(ProjectContextError, match="outside"):
        registry.register(
            EditorPlugin(
                id="outside",
                title="Outside",
                description="",
                mode="external",
                script=tmp_path.parent / "outside.py",
            )
        )

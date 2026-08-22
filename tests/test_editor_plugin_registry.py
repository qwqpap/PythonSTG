"""ER5: the editor window sees exactly one plugin-contribution entry point.

``EditorPluginRegistry`` is the single facade the window holds.  It composes the
two contribution kinds behind one owner:

* the headless SDK registry (:class:`src.editor.plugin_sdk.PluginRegistry`) that
  owns project-local ``*.pystg-plugin.json`` manifests -- resource types, node
  types, commands, adapters, compilers, preview handlers -- with transactional
  activation and rollback;
* the Qt workbench view catalog (:class:`src.editor.workbench.PluginRegistry`)
  that owns bottom/central panels and external editing-tool launchers.

These tests pin the *facade* contract independently of the two underlying
registries, whose own behaviour stays covered by ``test_plugin_sdk.py`` and
``test_editor_workbench.py``:

* one facade, and the window exposes no separate ``plugin_sdk_registry``
  attribute -- the SDK is reached only through the facade's ``.sdk`` accessor,
  never mirrored onto the window as a second, independent registry;
* the SDK component shares the exact resource/node registries wired into the
  document manager (never a detached copy);
* a partial activation failure rolls back only the broken plugin and isolates
  the error;
* shutting the facade down undoes every owned SDK contribution and runs cleanup;
* a plugin's registration context cannot reach the window, the core registries,
  or any global runtime object;
* tearing down an external editing tool never stops the formal preview.
"""

from __future__ import annotations

import json

import pytest

from src.authoring.registry import build_default_resource_type_registry
from src.core.project_context import ProjectContext
from src.authoring.scene.node_types import build_default_node_type_registry
from src.editor.plugin_sdk import (
    PLUGIN_API_VERSION,
    PluginManifest,
    PluginRegistry as SDKPluginRegistry,
)
from src.editor.plugins import EditorPluginRegistry
from src.editor.workbench import EditorPlugin, PluginRegistry as WorkbenchPluginRegistry


def _project(tmp_path):
    return ProjectContext(tmp_path)


def _editor_project(tmp_path):
    """A minimal on-disk project the window can open (mirrors the regression fixtures)."""
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True, exist_ok=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    (tmp_path / "game_content" / "patterns").mkdir(parents=True, exist_ok=True)
    return ProjectContext(tmp_path)


def _manifest(plugin_id, *, activation=None):
    return PluginManifest(
        id=plugin_id,
        name=f"{plugin_id} plugin",
        version="1.0.0",
        api_version=PLUGIN_API_VERSION,
        contributions={},
        activation=activation,
    )


class _FakeFormalClient:
    """Stand-in for the formal NDJSON preview client (see test_preview_session)."""

    def __init__(self) -> None:
        self.running = False

    @property
    def is_running(self) -> bool:
        return self.running

    def start(self) -> bool:
        self.running = True
        return True

    def stop(self, timeout_ms: int = 1500) -> None:
        self.running = False

    def close(self) -> None:
        self.running = False


class _FakeToolProcess:
    """Minimal external-tool process surface used by ``_tool_finished``."""

    def readAllStandardOutput(self) -> bytes:
        return b""

    def state(self) -> int:
        return 0


# -- facade composition ------------------------------------------------------
def test_facade_owns_one_sdk_component_sharing_the_document_registries(tmp_path):
    project = _project(tmp_path)
    resource_types = build_default_resource_type_registry()
    node_types = build_default_node_type_registry()

    facade = EditorPluginRegistry(
        project, resource_types=resource_types, node_types=node_types
    )

    # The SDK component is the real transactional registry...
    assert isinstance(facade.sdk, SDKPluginRegistry)
    # ...wired to the *same* registries the DocumentManager uses, never a copy.
    assert facade.sdk.resource_types is resource_types
    assert facade.sdk.node_types is node_types


def test_facade_view_catalog_registers_and_queries_editor_plugins(tmp_path):
    facade = EditorPluginRegistry(_project(tmp_path))
    panel = EditorPlugin(
        id="panel",
        title="Panel",
        description="",
        mode="bottom",
        factory=lambda: None,
    )

    assert facade.register(panel) is panel
    assert facade.get("panel") is panel
    assert facade.all() == (panel,)
    assert facade.by_mode("bottom") == (panel,)
    assert facade.by_mode("central") == ()
    # White-box compatibility view the resource-browser test drives.
    assert facade._plugins["panel"] is panel


# -- unified SDK lifecycle ---------------------------------------------------
def test_partial_sdk_activation_failure_rolls_back_and_isolates(tmp_path):
    facade = EditorPluginRegistry(_project(tmp_path))

    def healthy_activate(context):
        context.register_command("healthy.cmd", lambda: "ok")

    def broken_activate(context):
        context.register_command("broken.cmd", lambda: "never")
        raise RuntimeError("plugin crashed on activate")

    facade.sdk.register(_manifest("healthy", activation=healthy_activate))
    facade.sdk.register(_manifest("broken", activation=broken_activate))
    facade.sdk.activate_all()

    assert facade.sdk.state("healthy") == "active"
    assert facade.sdk.command("healthy.cmd")() == "ok"
    # The broken plugin failed in isolation and its partial contribution
    # rolled back -- the command it registered before crashing is gone.
    assert facade.sdk.state("broken") == "failed"
    with pytest.raises(KeyError):
        facade.sdk.command("broken.cmd")
    assert [plugin_id for plugin_id, _ in facade.sdk.errors] == ["broken"]


def test_shutdown_undoes_owned_sdk_contributions(tmp_path):
    facade = EditorPluginRegistry(_project(tmp_path))
    cleaned: list[bool] = []

    def activate(context):
        context.register_command("sample.cmd", lambda: "ok")
        context.on_deactivate(lambda: cleaned.append(True))

    facade.sdk.register(_manifest("sample", activation=activate))
    facade.sdk.activate_all()
    assert facade.sdk.state("sample") == "active"

    facade.shutdown()

    assert cleaned == [True]
    assert facade.sdk.state("sample") == "inactive"
    with pytest.raises(KeyError):
        facade.sdk.command("sample.cmd")


def test_plugin_context_cannot_reach_window_or_core_registries(tmp_path):
    facade = EditorPluginRegistry(_project(tmp_path))
    captured: dict[str, object] = {}

    def activate(context):
        captured["context"] = context

    facade.sdk.register(_manifest("sample", activation=activate))
    facade.sdk.activate_all()
    context = captured["context"]

    public = {name for name in dir(context) if not name.startswith("_")}
    # The constrained context never surfaces the window, the core registries,
    # the facade, or a global runtime object as public attributes.
    for forbidden in ("window", "registry", "resource_types", "node_types", "runtime", "sdk"):
        assert forbidden not in public
    # It only exposes the narrow contribution API plus its project + id.
    assert public == {
        "project",
        "plugin_id",
        "register_resource_type",
        "register_node_type",
        "register_inspector_editor",
        "register_command",
        "register_adapter",
        "register_compiler",
        "register_preview_handler",
        "on_deactivate",
        "rollback",
        "deactivate",
    }
    assert context.project is facade.sdk.project


# -- window integration ------------------------------------------------------
def test_window_holds_exactly_one_plugin_registry_facade(tmp_path, qapp_session):
    del qapp_session
    from src.editor.app import EditorMainWindow

    window = EditorMainWindow(_editor_project(tmp_path))
    try:
        assert isinstance(window.plugin_registry, EditorPluginRegistry)
        # The window holds NO second ``plugin_sdk_registry`` attribute/alias --
        # neither in its instance dict nor reachable as any attribute/property.
        assert "plugin_sdk_registry" not in vars(window)
        assert not hasattr(window, "plugin_sdk_registry")
        # The SDK surface is the facade's own component, reached only via ``.sdk``.
        assert isinstance(window.plugin_registry.sdk, SDKPluginRegistry)
        # The workbench catalog is encapsulated by the facade, never a direct
        # window attribute -- so the window juggles no independent registries.
        assert not any(
            type(value) is WorkbenchPluginRegistry for value in vars(window).values()
        )
        # The window's own attributes hold exactly one registry object: the
        # single facade.  The SDK lives *inside* the facade, not as a second
        # window attribute.
        registries = {
            id(value)
            for value in vars(window).values()
            if isinstance(value, (EditorPluginRegistry, SDKPluginRegistry))
        }
        assert registries == {id(window.plugin_registry)}
    finally:
        window.close()


def test_external_tool_teardown_does_not_stop_formal_preview(tmp_path, qapp_session):
    del qapp_session
    from src.editor.app import EditorMainWindow

    window = EditorMainWindow(_editor_project(tmp_path))
    try:
        fake = _FakeFormalClient()
        fake.running = True
        window._pattern_preview_client = fake  # property setter -> preview session
        assert window._preview_session.is_formal_running

        # An external editing tool finishing must never reach into the preview.
        window._tool_processes["player_editor"] = _FakeToolProcess()
        window._tool_finished("player_editor", 0, None)

        assert "player_editor" not in window._tool_processes
        assert window._preview_session.is_formal_running
        assert fake.running is True
    finally:
        window.close()

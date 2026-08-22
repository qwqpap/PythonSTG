"""Plugin manifest, registration, and isolation regression contract.

These tests preserve the shipped plugin SDK behavior.

Contract summary:
- ``src/editor/plugin_sdk.py`` exposes ``PLUGIN_API_VERSION``,
  ``PluginManifest``, and ``PluginRegistry(project)``.
- API version mismatches and duplicate ids are rejected; activation
  failures are isolated per plugin; discovery scans ``plugins/`` for
  ``*.pystg-plugin.json`` manifests.
- A sample plugin contributes a resource type, a node type, an Inspector
  editor, a command, and an adapter without patching core registries.
"""

import json

import pytest

from src.core.project_context import ProjectContext
from src.editor.plugin_sdk import (
    PLUGIN_API_VERSION,
    PluginManifest,
    PluginRegistry,
)
from src.game.adapters import LoopbackAdapter
from src.game.events import EventBus


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}), encoding="utf-8"
    )
    return ProjectContext(tmp_path)


def _manifest(plugin_id="sample", **changes):
    values = {
        "id": plugin_id,
        "name": "Sample Plugin",
        "version": "1.0.0",
        "api_version": PLUGIN_API_VERSION,
        "contributions": {
            "resource_types": ["pystg.sample"],
            "node_types": ["SampleNode"],
            "inspector_editors": ["SampleNode"],
            "commands": ["sample.run"],
            "adapters": ["sample.loopback"],
        },
    }
    values.update(changes)
    return PluginManifest(**values)


def test_manifest_round_trips_through_json():
    manifest = _manifest()

    payload = json.loads(json.dumps(manifest.to_dict()))
    reloaded = PluginManifest.from_dict(payload)

    assert reloaded.id == manifest.id
    assert reloaded.name == "Sample Plugin"
    assert reloaded.version == "1.0.0"
    assert reloaded.api_version == PLUGIN_API_VERSION
    assert reloaded.contributions == manifest.contributions


def test_registry_rejects_duplicate_plugin_ids(tmp_path):
    registry = PluginRegistry(_project(tmp_path))
    registry.register(_manifest())

    with pytest.raises(ValueError, match="duplicate"):
        registry.register(_manifest())


def test_registry_rejects_unsupported_api_version(tmp_path):
    registry = PluginRegistry(_project(tmp_path))

    with pytest.raises(ValueError, match="api"):
        registry.register(_manifest(api_version=PLUGIN_API_VERSION + 1))


def test_registry_activates_plugins_and_reports_state(tmp_path):
    registry = PluginRegistry(_project(tmp_path))
    registry.register(_manifest())
    registry.activate_all()

    state = registry.state("sample")
    assert state == "active"


def test_activation_failure_is_isolated_per_plugin(tmp_path):
    registry = PluginRegistry(_project(tmp_path))

    def fail_activate():
        raise RuntimeError("plugin crashed on activate")

    registry.register(
        _manifest("broken", activation=fail_activate)
    )
    registry.register(_manifest("healthy"))
    registry.activate_all()

    assert registry.state("broken") == "failed"
    assert registry.state("healthy") == "active"
    assert len(registry.errors) == 1
    plugin_id, error = registry.errors[0]
    assert plugin_id == "broken"
    assert "crashed on activate" in str(error)


def test_registry_deactivates_plugins(tmp_path):
    registry = PluginRegistry(_project(tmp_path))
    registry.register(_manifest())
    registry.activate_all()
    registry.deactivate_all()

    assert registry.state("sample") == "inactive"


def test_deactivation_cleanup_failure_still_undoes_every_contribution(tmp_path):
    """One faulty cleanup cannot strand contributions or block other plugins."""

    registry = PluginRegistry(_project(tmp_path))
    cleaned = []

    def broken_activate(context):
        context.register_command("broken.command", lambda: "broken")
        context.on_deactivate(lambda: cleaned.append("broken-tail"))

        def fail_cleanup():
            raise RuntimeError("cleanup exploded")

        context.on_deactivate(fail_cleanup)

    def healthy_activate(context):
        context.register_command("healthy.command", lambda: "healthy")
        context.on_deactivate(lambda: cleaned.append("healthy"))

    registry.register(_manifest("broken-cleanup", activation=broken_activate))
    registry.register(_manifest("healthy-cleanup", activation=healthy_activate))
    registry.activate_all()

    registry.deactivate_all()

    assert registry.state("broken-cleanup") == "inactive"
    assert registry.state("healthy-cleanup") == "inactive"
    assert cleaned == ["broken-tail", "healthy"]
    with pytest.raises(KeyError):
        registry.command("broken.command")
    with pytest.raises(KeyError):
        registry.command("healthy.command")
    assert any(
        plugin_id == "broken-cleanup" and "cleanup exploded" in str(error)
        for plugin_id, error in registry.errors
    )

    # A completed failure-isolated deactivation leaves the plugin able to mint a
    # fresh registration context rather than losing its only cleanup handle.
    registry.activate("broken-cleanup")
    assert registry.state("broken-cleanup") == "active"
    assert registry.command("broken.command")() == "broken"


def test_discovery_scans_project_plugins_directory(tmp_path):
    project = _project(tmp_path)
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "sample.pystg-plugin.json").write_text(
        json.dumps(_manifest("discovered").to_dict()), encoding="utf-8"
    )

    registry = PluginRegistry(project)
    found = registry.discover()

    assert "discovered" in found
    registry.register(found["discovered"])
    assert registry.state("discovered") == "inactive"


def test_sample_plugin_contributes_without_patching_core_registries(tmp_path):
    project = _project(tmp_path)
    registry = PluginRegistry(project)
    registry.register(_manifest())
    registry.activate_all()

    contributions = registry.contributions("sample")
    assert "resource_types" in contributions
    assert "node_types" in contributions
    assert "inspector_editors" in contributions
    assert "commands" in contributions
    assert "adapters" in contributions

    bus = EventBus()
    adapter = LoopbackAdapter()
    adapter.start(bus)
    delivered = []
    bus.subscribe("adapter.loopback", lambda event: delivered.append(event.payload))
    adapter.push({"from": "plugin"})
    bus.dispatch()
    assert delivered == [{"from": "plugin"}]

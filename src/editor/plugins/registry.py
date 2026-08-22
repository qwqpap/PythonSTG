"""One plugin-contribution facade for the editor window (ER5).

Before this facade the window held two independent plugin registries with no
knowledge of each other:

* the Qt **workbench view catalog** (:class:`src.editor.workbench.PluginRegistry`)
  -- bottom/central panels and external editing-tool launchers;
* the headless **SDK registry** (:class:`src.editor.plugin_sdk.PluginRegistry`)
  -- project-local ``*.pystg-plugin.json`` manifests contributing resource
  types, node types, commands, adapters, compilers and preview handlers, with
  transactional activation and rollback.

Two owners meant two lifecycles: nothing guaranteed a single teardown path, and
the window had to juggle both by name.  :class:`EditorPluginRegistry` composes
both behind one owner, so the window depends on a single entry point, identity /
activation / rollback / cleanup live in one place, and shutdown is one call.

The facade *composes* -- it does not subclass -- the two registries, so each
keeps its own focused contract (still covered directly by
``test_editor_workbench.py`` and ``test_plugin_sdk.py``).  The transactional SDK
surface is reached through :pyattr:`sdk`; the Qt view catalog through the
delegating :meth:`register` / :meth:`get` / :meth:`all` / :meth:`by_mode`.  The
registration context handed to plugin activators is minted by the SDK registry
and never exposes the window, the core registries, or a runtime object.
"""

from __future__ import annotations

from typing import Any

from src.core.project_context import ProjectContext

from ..plugin_sdk import PluginRegistry as SDKPluginRegistry
from ..workbench import EditorPlugin, PluginMode
from .sdk_adapter import build_sdk_registry, shutdown_sdk_registry
from .workbench_adapter import WorkbenchAdapter


class EditorPluginRegistry:
    """One owner for the editor's Qt view catalog and its SDK contributions."""

    def __init__(
        self,
        project: ProjectContext,
        *,
        resource_types: Any | None = None,
        node_types: Any | None = None,
    ) -> None:
        self.project = project
        # The Qt-side catalog of bottom/central panels and external tools.
        self._workbench = WorkbenchAdapter(project)
        # The transactional SDK registry.  Passing the resource/node type
        # registries through keeps them the *same* instances the document
        # manager uses -- never a detached copy -- so plugin-contributed
        # resource/node types land in the registries scene validation reads.
        self._sdk = build_sdk_registry(
            project,
            resource_types=resource_types,
            node_types=node_types,
            identity_available=lambda plugin_id: not self._workbench.contains(plugin_id),
        )

    # -- SDK contribution surface --------------------------------------------
    @property
    def sdk(self) -> SDKPluginRegistry:
        """The transactional SDK registry that owns manifest contributions."""

        return self._sdk

    def shutdown(self) -> None:
        """Deactivate every SDK plugin, running each plugin's cleanup/rollback.

        This is the window's single teardown entry point: it undoes every
        contribution owned by an active plugin.  External Qt tool processes are
        owned by the workbench service and torn down separately by the window;
        they are deliberately not part of the plugin-contribution lifecycle.
        """

        shutdown_sdk_registry(self._sdk)

    # -- Qt view catalog surface ---------------------------------------------
    def register(self, plugin: EditorPlugin) -> EditorPlugin:
        if self._sdk.state(plugin.id) != "unknown":
            raise ValueError(f"duplicate plugin identity: {plugin.id}")
        return self._workbench.register(plugin)

    def get(self, plugin_id: str) -> EditorPlugin:
        return self._workbench.get(plugin_id)

    def all(self) -> tuple[EditorPlugin, ...]:
        return self._workbench.all()

    def by_mode(self, mode: PluginMode) -> tuple[EditorPlugin, ...]:
        return self._workbench.by_mode(mode)

    @property
    def _plugins(self) -> dict[str, EditorPlugin]:
        """White-box view of the Qt catalog kept for existing panel tests.

        Returns the catalog's live mapping, so in-place edits (used by the
        resource-browser test to swap in an embedded central panel) still work.
        """

        return self._workbench.plugins

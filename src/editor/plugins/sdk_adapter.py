"""Construction and teardown adapter for transactional SDK contributions."""

from __future__ import annotations

from typing import Any, Callable

from src.core.project_context import ProjectContext

from ..plugin_sdk import PluginRegistry


def build_sdk_registry(
    project: ProjectContext,
    *,
    resource_types: Any | None,
    node_types: Any | None,
    identity_available: Callable[[str], bool],
) -> PluginRegistry:
    return PluginRegistry(
        project,
        resource_types=resource_types,
        node_types=node_types,
        identity_available=identity_available,
    )


def shutdown_sdk_registry(registry: PluginRegistry) -> None:
    registry.deactivate_all()


__all__ = ["build_sdk_registry", "shutdown_sdk_registry"]

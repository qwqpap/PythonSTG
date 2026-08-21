"""Validated, transactional plugin SDK used by the editor shell.

The manifest is intentionally only data.  Executable plugins receive a small
registration context whose methods record every contribution and can roll it
back atomically when activation fails.  The context never exposes the core
registry objects themselves, so a plugin cannot patch unrelated editor state.
"""

from __future__ import annotations

import inspect
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from src.core.project_context import ProjectContext

PLUGIN_API_VERSION = 1
PLUGIN_STATES = ("inactive", "active", "failed")


class PluginSDKError(ValueError):
    """Raised when a plugin violates the SDK contract."""


def _freeze_json(value: Any, path: str = "contributions") -> Any:
    """Convert JSON-compatible data to recursively immutable containers."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PluginSDKError(f"{path} must contain finite numbers")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise PluginSDKError(f"{path} keys must be non-empty strings")
            frozen[key] = _freeze_json(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, f"{path}[]") for item in value)
    raise PluginSDKError(
        f"{path} contains unsupported type {type(value).__name__}"
    )


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class PluginManifest:
    id: str
    name: str
    version: str
    api_version: int
    contributions: Mapping[str, Any] = field(default_factory=dict)
    activation: Callable[..., Any] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "contributions",
            _freeze_json(self.contributions, "contributions"),
        )

    def validate(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise PluginSDKError("plugin id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise PluginSDKError("plugin name must be a non-empty string")
        if not isinstance(self.version, str) or not self.version.strip():
            raise PluginSDKError("plugin version must be a non-empty string")
        if isinstance(self.api_version, bool) or not isinstance(self.api_version, int):
            raise PluginSDKError("plugin api_version must be an integer")
        if self.api_version != PLUGIN_API_VERSION:
            raise PluginSDKError(
                f"plugin {self.id!r} targets api version {self.api_version}; "
                f"supported api version is {PLUGIN_API_VERSION}"
            )
        if not isinstance(self.contributions, Mapping):
            raise PluginSDKError("plugin contributions must be an object")
        if self.activation is not None and not callable(self.activation):
            raise PluginSDKError("plugin activation must be callable")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "api_version": self.api_version,
            "contributions": _thaw_json(self.contributions),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PluginManifest":
        if not isinstance(value, Mapping):
            raise PluginSDKError("plugin manifest must be an object")
        allowed = {"id", "name", "version", "api_version", "contributions"}
        unknown = set(value).difference(allowed)
        if unknown:
            raise PluginSDKError(
                "plugin manifest unknown fields: " + ", ".join(sorted(unknown))
            )
        manifest = cls(
            id=value.get("id", ""),
            name=value.get("name", ""),
            version=value.get("version", ""),
            api_version=value.get("api_version", 0),
            contributions=value.get("contributions", {}),
        )
        manifest.validate()
        return manifest


class PluginRegistrationContext:
    """Constrained, transaction-aware contribution API for one plugin."""

    def __init__(self, registry: "PluginRegistry", plugin_id: str) -> None:
        self._registry = registry
        self.plugin_id = plugin_id
        self._undo: list[Callable[[], None]] = []
        self._cleanup: list[Callable[[], None]] = []

    @property
    def project(self) -> ProjectContext:
        return self._registry.project

    def _remember(
        self,
        undo: Callable[[], None],
        cleanup: Callable[[], None] | None = None,
    ) -> None:
        self._undo.append(undo)
        if cleanup is not None:
            self._cleanup.append(cleanup)

    def register_resource_type(self, spec: Any) -> Any:
        registered = self._registry.resource_types.register(spec)
        self._remember(
            lambda name=registered.type_name: self._registry.resource_types.unregister(name)
        )
        return registered

    def register_node_type(self, spec: Any) -> Any:
        registered = self._registry.node_types.register(spec)
        self._remember(
            lambda name=registered.type_name: self._registry.node_types.unregister(name)
        )
        return registered

    def register_inspector_editor(self, node_type: str, factory: Callable[..., Any]) -> None:
        self._registry._register_owned(
            self._registry._inspector_editors,
            str(node_type),
            factory,
            "Inspector editor",
        )
        self._remember(
            lambda name=str(node_type): self._registry._inspector_editors.pop(name, None)
        )

    def register_command(self, name: str, command: Callable[..., Any]) -> None:
        self._registry._register_owned(
            self._registry._commands, str(name), command, "command"
        )
        self._remember(
            lambda key=str(name): self._registry._commands.pop(key, None)
        )

    def register_adapter(self, name: str, factory: Callable[..., Any]) -> None:
        self._registry._register_owned(
            self._registry._adapters, str(name), factory, "adapter"
        )
        self._remember(
            lambda key=str(name): self._registry._adapters.pop(key, None)
        )

    def register_compiler(self, resource_type: str, compiler: Callable[..., Any]) -> None:
        self._registry._register_owned(
            self._registry._compilers, str(resource_type), compiler, "compiler"
        )
        self._remember(
            lambda key=str(resource_type): self._registry._compilers.pop(key, None)
        )

    def register_preview_handler(self, resource_type: str, handler: Callable[..., Any]) -> None:
        self._registry._register_owned(
            self._registry._preview_handlers,
            str(resource_type),
            handler,
            "preview handler",
        )
        self._remember(
            lambda key=str(resource_type): self._registry._preview_handlers.pop(key, None)
        )

    def on_deactivate(self, callback: Callable[[], None]) -> None:
        if not callable(callback):
            raise PluginSDKError("deactivation callback must be callable")
        self._cleanup.append(callback)

    def rollback(self) -> None:
        for undo in reversed(self._undo):
            try:
                undo()
            except (KeyError, ValueError):
                pass
        self._undo.clear()
        self._cleanup.clear()

    def deactivate(self) -> None:
        for callback in reversed(self._cleanup):
            callback()
        for undo in reversed(self._undo):
            undo()
        self._undo.clear()
        self._cleanup.clear()


def _invoke_activation(callback: Callable[..., Any], context: PluginRegistrationContext) -> None:
    """Support legacy zero-argument callbacks while preferring the context API."""
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        callback(context)
        return
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    accepts_varargs = any(
        parameter.kind is parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    required = [parameter for parameter in positional if parameter.default is parameter.empty]
    if required or accepts_varargs or positional:
        callback(context)
    else:
        callback()


class PluginRegistry:
    """Project-scoped plugin lifecycle and contribution registry."""

    def __init__(
        self,
        project: ProjectContext,
        *,
        resource_types: Any | None = None,
        node_types: Any | None = None,
    ) -> None:
        self.project = project
        if resource_types is None:
            from src.authoring.registry import build_default_resource_type_registry

            resource_types = build_default_resource_type_registry()
        if node_types is None:
            from src.authoring.scene.node_types import build_default_node_type_registry

            node_types = build_default_node_type_registry()
        self.resource_types = resource_types
        self.node_types = node_types
        self._manifests: dict[str, PluginManifest] = {}
        self._states: dict[str, str] = {}
        self._contexts: dict[str, PluginRegistrationContext] = {}
        self._inspector_editors: dict[str, Callable[..., Any]] = {}
        self._commands: dict[str, Callable[..., Any]] = {}
        self._adapters: dict[str, Callable[..., Any]] = {}
        self._compilers: dict[str, Callable[..., Any]] = {}
        self._preview_handlers: dict[str, Callable[..., Any]] = {}
        self._owners: dict[str, dict[str, tuple[str, str]]] = {}
        self.errors: list[tuple[str, Exception]] = []

    @staticmethod
    def _register_owned(
        target: dict[str, Any], key: str, value: Any, label: str
    ) -> None:
        if not key.strip():
            raise PluginSDKError(f"{label} name must be non-empty")
        if not callable(value):
            raise PluginSDKError(f"{label} must be callable")
        if key in target:
            raise PluginSDKError(f"duplicate {label}: {key}")
        target[key] = value

    def register(self, manifest: PluginManifest) -> PluginManifest:
        if not isinstance(manifest, PluginManifest):
            raise PluginSDKError("register expects a PluginManifest")
        manifest.validate()
        if manifest.id in self._manifests:
            raise PluginSDKError(f"duplicate plugin id: {manifest.id}")
        self._manifests[manifest.id] = manifest
        self._states[manifest.id] = "inactive"
        return manifest

    def get(self, plugin_id: str) -> PluginManifest:
        try:
            return self._manifests[plugin_id]
        except KeyError as exc:
            raise PluginSDKError(f"unknown plugin: {plugin_id}") from exc

    def all(self) -> tuple[PluginManifest, ...]:
        return tuple(self._manifests.values())

    def state(self, plugin_id: str) -> str:
        return self._states.get(plugin_id, "unknown")

    def activate_all(self) -> None:
        for manifest in tuple(self._manifests.values()):
            if self._states[manifest.id] in {"active", "failed"}:
                continue
            self.activate(manifest.id)

    def activate(self, plugin_id: str) -> None:
        manifest = self.get(plugin_id)
        if self._states[plugin_id] == "active":
            return
        context = PluginRegistrationContext(self, plugin_id)
        try:
            if manifest.activation is not None:
                _invoke_activation(manifest.activation, context)
        except Exception as exc:  # noqa: BLE001 - plugin isolation boundary
            context.rollback()
            self._contexts.pop(plugin_id, None)
            self._states[plugin_id] = "failed"
            self.errors.append((plugin_id, exc))
            return
        self._contexts[plugin_id] = context
        self._states[plugin_id] = "active"

    def deactivate(self, plugin_id: str) -> None:
        self.get(plugin_id)
        context = self._contexts.pop(plugin_id, None)
        if context is not None:
            context.deactivate()
        self._states[plugin_id] = "inactive"

    def deactivate_all(self) -> None:
        for plugin_id in tuple(self._states):
            self.deactivate(plugin_id)

    def contributions(self, plugin_id: str) -> dict[str, Any]:
        manifest = self.get(plugin_id)
        return _thaw_json(manifest.contributions)

    def inspector_editor(self, node_type: str) -> Callable[..., Any]:
        return self._inspector_editors[str(node_type)]

    def command(self, name: str) -> Callable[..., Any]:
        return self._commands[str(name)]

    def adapter_factory(self, name: str) -> Callable[..., Any]:
        return self._adapters[str(name)]

    def compiler(self, resource_type: str) -> Callable[..., Any]:
        return self._compilers[str(resource_type)]

    def preview_handler(self, resource_type: str) -> Callable[..., Any]:
        return self._preview_handlers[str(resource_type)]

    def discover(self) -> dict[str, PluginManifest]:
        """Scan ``project.root / "plugins"`` for manifests."""
        plugins_dir = self.project.root / "plugins"
        found: dict[str, PluginManifest] = {}
        if not plugins_dir.is_dir():
            return found
        for path in sorted(plugins_dir.glob("*.pystg-plugin.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                manifest = PluginManifest.from_dict(payload)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self.errors.append((path.name, exc))
                continue
            if manifest.id not in self._manifests:
                found[manifest.id] = manifest
        return found


__all__ = [
    "PLUGIN_API_VERSION",
    "PLUGIN_STATES",
    "PluginManifest",
    "PluginRegistrationContext",
    "PluginRegistry",
    "PluginSDKError",
]

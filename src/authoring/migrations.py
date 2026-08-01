"""Explicit, per-resource schema migration routing."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from typing import Any

from .resources import (
    AUTHORING_RESOURCE_TYPES,
    RESOURCE_SCHEMA_VERSION,
    SCENE_RESOURCE_TYPE,
    new_resource_id,
)


Migration = Callable[[dict[str, Any]], dict[str, Any]]


class MigrationError(ValueError):
    """Raised when no safe schema migration path exists."""


class MigrationRegistry:
    def __init__(self) -> None:
        self._current_versions: dict[str, int] = {}
        self._migrations: dict[tuple[str, int], Migration] = {}

    def register_type(self, resource_type: str, current_version: int) -> None:
        if not resource_type or current_version <= 0:
            raise ValueError("resource type and a positive current version are required")
        existing = self._current_versions.get(resource_type)
        if existing is not None and existing != current_version:
            raise ValueError(
                f"Resource type {resource_type!r} already targets version {existing}"
            )
        self._current_versions[resource_type] = current_version

    def register(
        self,
        resource_type: str,
        from_version: int,
        migration: Migration,
    ) -> None:
        if resource_type not in self._current_versions:
            raise ValueError(f"Register resource type before migrations: {resource_type}")
        if from_version < 0 or from_version >= self._current_versions[resource_type]:
            raise ValueError("migration source must be below the current version")
        key = (resource_type, from_version)
        if key in self._migrations:
            raise ValueError(
                f"Duplicate migration for {resource_type} schema {from_version}"
            )
        self._migrations[key] = migration

    def current_version(self, resource_type: str) -> int:
        try:
            return self._current_versions[resource_type]
        except KeyError as exc:
            raise MigrationError(f"Unknown resource type: {resource_type!r}") from exc

    def migrate(
        self,
        data: Mapping[str, Any],
        *,
        expected_type: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise MigrationError("resource must be an object")
        migrated = copy.deepcopy(dict(data))
        resource_type = str(migrated.get("type") or expected_type or "")
        if not resource_type:
            raise MigrationError("resource.type is required to select migrations")
        if expected_type is not None and resource_type != expected_type:
            raise MigrationError(
                f"Expected resource type {expected_type!r}, got {resource_type!r}"
            )
        target = self.current_version(resource_type)
        version = migrated.get("schema_version", 0)
        if not isinstance(version, int) or isinstance(version, bool):
            raise MigrationError("schema_version must be an integer")
        if version > target:
            raise MigrationError(
                f"Resource schema {version} is newer than supported {target} "
                f"for {resource_type}"
            )
        while version < target:
            migration = self._migrations.get((resource_type, version))
            if migration is None:
                raise MigrationError(
                    f"No migration path for {resource_type} schema {version} -> {version + 1}"
                )
            migrated = migration(copy.deepcopy(migrated))
            if not isinstance(migrated, dict):
                raise MigrationError("migration must return an object")
            next_version = migrated.get("schema_version")
            if next_version != version + 1:
                raise MigrationError(
                    f"Migration for {resource_type} schema {version} must produce "
                    f"schema {version + 1}, got {next_version!r}"
                )
            if migrated.get("type") != resource_type:
                raise MigrationError("migration may not change resource.type")
            version = next_version
        return migrated


def migrate_legacy_scene_v0(data: dict[str, Any]) -> dict[str, Any]:
    root = data.get("root")
    if root is None:
        root = {
            "id": new_resource_id(),
            "type": "Stage",
            "name": data.get("name", "Scene"),
            "properties": {},
            "children": data.get("nodes", []),
        }
    return {
        "schema_version": 1,
        "type": SCENE_RESOURCE_TYPE,
        "id": data.get("id") or new_resource_id(),
        "name": data.get("name", "Scene"),
        "symbol_name": data.get("symbol_name"),
        "metadata": data.get("metadata", {}),
        "root": root,
        "timeline": data.get("timeline", []),
    }


def build_default_migration_registry() -> MigrationRegistry:
    registry = MigrationRegistry()
    for resource_type in AUTHORING_RESOURCE_TYPES:
        registry.register_type(resource_type, RESOURCE_SCHEMA_VERSION)
    registry.register(SCENE_RESOURCE_TYPE, 0, migrate_legacy_scene_v0)
    return registry

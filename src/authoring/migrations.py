"""Explicit, per-resource schema migration routing."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from .resources import (
    AUTHORING_RESOURCE_SCHEMA_VERSIONS,
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

    def unregister_type(self, resource_type: str) -> None:
        """Remove a type and all migrations owned by it during plugin rollback."""
        self._current_versions.pop(resource_type, None)
        for key in tuple(self._migrations):
            if key[0] == resource_type:
                self._migrations.pop(key, None)

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


def _derived_id(document_id: str, label: str) -> str:
    try:
        namespace = uuid.UUID(str(document_id))
    except (ValueError, AttributeError, TypeError):
        namespace = uuid.NAMESPACE_URL
    return str(uuid.uuid5(namespace, label))


def migrate_scene_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Promote the flat legacy timeline into deterministic typed tracks."""

    migrated = copy.deepcopy(data)
    legacy = migrated.pop("timeline", [])
    if "tracks" in migrated:
        migrated["schema_version"] = 2
        return migrated
    if not isinstance(legacy, list):
        raise MigrationError("scene.timeline must be an array")

    document_id = str(migrated.get("id") or "")
    tracks_by_kind: dict[str, dict[str, Any]] = {}
    kind_aliases = {
        "pattern": "Pattern",
        "spawnpattern": "Pattern",
        "movement": "Movement",
        "move": "Movement",
        "audio": "Audio",
        "playaudio": "Audio",
        "property": "Property",
        "setproperty": "Property",
        "scriptevent": "ScriptEvent",
    }
    for index, raw in enumerate(legacy):
        if not isinstance(raw, dict):
            raise MigrationError("scene.timeline entries must be objects")
        legacy_type = str(raw.get("type") or "Event")
        kind = kind_aliases.get(legacy_type.replace("_", "").lower(), "Event")
        properties = copy.deepcopy(raw.get("properties") or {})
        if not isinstance(properties, dict):
            raise MigrationError("scene.timeline.properties must be an object")
        target_id = properties.pop("target_id", None)
        channel = str(properties.pop("channel", kind.lower()) or kind.lower())
        duration = properties.pop("duration_frames", 1)
        loop_count = properties.pop("loop_count", 1)
        payload = properties
        if kind == "Event":
            payload = {"event_type": legacy_type, "data": properties}
        elif kind == "Audio" and not (
            payload.get("resource") or payload.get("name")
        ):
            payload = {"name": legacy_type, **payload}
        elif kind == "ScriptEvent" and not (
            payload.get("script") or payload.get("hook")
        ):
            payload = {"hook": legacy_type, **payload}
        track = tracks_by_kind.get(kind)
        if track is None:
            track = {
                "id": _derived_id(document_id, f"timeline-track:{kind}"),
                "name": f"{kind} Track",
                "kind": kind,
                "target_id": None,
                "channel": kind.lower(),
                "order": len(tracks_by_kind),
                "muted": False,
                "clips": [],
            }
            tracks_by_kind[kind] = track
        clip_id = raw.get("id") or _derived_id(
            document_id,
            f"legacy-timeline:{index}:{legacy_type}:{raw.get('frame', 0)}",
        )
        track["clips"].append(
            {
                "id": clip_id,
                "name": legacy_type,
                "kind": kind,
                "start_frame": raw.get("frame", 0),
                "duration_frames": duration,
                "target_id": target_id,
                "channel": channel,
                "order": index,
                "loop_count": loop_count,
                "enabled": True,
                "payload": payload,
                "keyframes": [],
            }
        )
    migrated["tracks"] = list(tracks_by_kind.values())
    migrated["schema_version"] = 2
    return migrated


def build_default_migration_registry() -> MigrationRegistry:
    registry = MigrationRegistry()
    for resource_type in AUTHORING_RESOURCE_TYPES:
        registry.register_type(
            resource_type,
            AUTHORING_RESOURCE_SCHEMA_VERSIONS[resource_type],
        )
    registry.register(SCENE_RESOURCE_TYPE, 0, migrate_legacy_scene_v0)
    registry.register(SCENE_RESOURCE_TYPE, 1, migrate_scene_v1_to_v2)
    return registry

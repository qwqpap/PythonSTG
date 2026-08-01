"""Stable, UI-independent authoring contracts for PySTG resources."""

from .coordinates import CoordinateSpace, Timebase
from .migrations import (
    MigrationError,
    MigrationRegistry,
    build_default_migration_registry,
)
from .registry import (
    ResourceTypeRegistry,
    ResourceTypeSpec,
    build_default_resource_type_registry,
)
from .resources import (
    AUTHORING_RESOURCE_TYPES,
    BACKGROUND_RESOURCE_TYPE,
    PATTERN_RESOURCE_TYPE,
    RESOURCE_FILE_SUFFIX,
    RESOURCE_SCHEMA_VERSION,
    SCENE_RESOURCE_TYPE,
    UI_RESOURCE_TYPE,
    GenericResourceDocument,
    ResourceDocumentError,
    ResourceHeader,
    ResourceReference,
)
from .storage import ResourceStore

__all__ = [
    "AUTHORING_RESOURCE_TYPES",
    "BACKGROUND_RESOURCE_TYPE",
    "CoordinateSpace",
    "GenericResourceDocument",
    "MigrationError",
    "MigrationRegistry",
    "PATTERN_RESOURCE_TYPE",
    "RESOURCE_FILE_SUFFIX",
    "RESOURCE_SCHEMA_VERSION",
    "ResourceDocumentError",
    "ResourceHeader",
    "ResourceReference",
    "ResourceStore",
    "ResourceTypeRegistry",
    "ResourceTypeSpec",
    "SCENE_RESOURCE_TYPE",
    "Timebase",
    "UI_RESOURCE_TYPE",
    "build_default_migration_registry",
    "build_default_resource_type_registry",
]

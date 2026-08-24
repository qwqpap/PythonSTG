"""Shared resource primitives retained beside the code-driven authoring core."""

from .registry import (
    ResourceTypeRegistry,
    ResourceTypeSpec,
    build_default_resource_type_registry,
)
from .resources import (
    AUTHORING_RESOURCE_TYPES,
    BACKGROUND_RESOURCE_TYPE,
    RESOURCE_FILE_SUFFIX,
    RESOURCE_SCHEMA_VERSION,
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
    "GenericResourceDocument",
    "RESOURCE_FILE_SUFFIX",
    "RESOURCE_SCHEMA_VERSION",
    "ResourceDocumentError",
    "ResourceHeader",
    "ResourceReference",
    "ResourceStore",
    "ResourceTypeRegistry",
    "ResourceTypeSpec",
    "UI_RESOURCE_TYPE",
    "build_default_resource_type_registry",
]

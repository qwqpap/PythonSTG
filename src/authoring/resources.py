"""Common identity, envelope, and reference contracts for authoring resources."""

from __future__ import annotations

import copy
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from src.core.project_context import ProjectContext


RESOURCE_SCHEMA_VERSION = 1
SCENE_RESOURCE_SCHEMA_VERSION = 2
RESOURCE_FILE_SUFFIX = ".pystg.json"

SCENE_RESOURCE_TYPE = "pystg.scene"
PATTERN_RESOURCE_TYPE = "pystg.pattern"
UI_RESOURCE_TYPE = "pystg.ui"
BACKGROUND_RESOURCE_TYPE = "pystg.background"
CURVE_RESOURCE_TYPE = "pystg.curve"
AUTHORING_RESOURCE_TYPES = (
    SCENE_RESOURCE_TYPE,
    PATTERN_RESOURCE_TYPE,
    UI_RESOURCE_TYPE,
    BACKGROUND_RESOURCE_TYPE,
)
AUTHORING_RESOURCE_SCHEMA_VERSIONS = {
    SCENE_RESOURCE_TYPE: SCENE_RESOURCE_SCHEMA_VERSION,
    PATTERN_RESOURCE_TYPE: RESOURCE_SCHEMA_VERSION,
    UI_RESOURCE_TYPE: RESOURCE_SCHEMA_VERSION,
    BACKGROUND_RESOURCE_TYPE: RESOURCE_SCHEMA_VERSION,
}

RESOURCE_HEADER_FIELDS = frozenset(
    {"schema_version", "type", "id", "name", "symbol_name", "metadata"}
)
_SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ResourceDocumentError(ValueError):
    """Raised when an authoring resource violates the common contract."""


def new_resource_id() -> str:
    return str(uuid.uuid4())


def validate_resource_id(value: Any, field_name: str = "resource.id") -> str:
    text = str(value or "")
    try:
        uuid.UUID(text)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ResourceDocumentError(
            f"{field_name} must be a UUID, got {value!r}"
        ) from exc
    return text


def validate_json_object(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ResourceDocumentError(f"{field_name} must be an object")
    result = dict(value)
    try:
        json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ResourceDocumentError(
            f"{field_name} must contain JSON-compatible values"
        ) from exc
    return result


def validate_unique_object_ids(
    value: Any,
    *,
    reserved_ids: tuple[str, ...] = (),
) -> None:
    """Reject duplicate UUID-valued ``id`` fields in a JSON resource tree."""

    seen = set(reserved_ids)

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            object_id = item.get("id")
            if object_id is not None:
                object_id = validate_resource_id(object_id, f"{path}.id")
                if object_id in seen:
                    raise ResourceDocumentError(
                        f"Duplicate document object id: {object_id}"
                    )
                seen.add(object_id)
            for key, child in item.items():
                visit(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")

    visit(value, "resource")


@dataclass
class ResourceHeader:
    """Fields shared by every versioned authoring resource."""

    type: str
    name: str
    id: str = field(default_factory=new_resource_id)
    schema_version: int = RESOURCE_SCHEMA_VERSION
    symbol_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(
        self,
        *,
        expected_type: str | None = None,
        current_version: int = RESOURCE_SCHEMA_VERSION,
    ) -> None:
        self.id = validate_resource_id(self.id)
        if not isinstance(self.schema_version, int) or isinstance(
            self.schema_version, bool
        ):
            raise ResourceDocumentError("schema_version must be an integer")
        if self.schema_version != current_version:
            relation = "newer than" if self.schema_version > current_version else "older than"
            raise ResourceDocumentError(
                f"Resource schema {self.schema_version} is {relation} supported "
                f"version {current_version}; migrate it before loading"
            )
        if not isinstance(self.type, str) or not self.type.strip():
            raise ResourceDocumentError("resource.type must be a non-empty string")
        if expected_type is not None and self.type != expected_type:
            raise ResourceDocumentError(
                f"Expected resource type {expected_type!r}, got {self.type!r}"
            )
        if not isinstance(self.name, str) or not self.name.strip():
            raise ResourceDocumentError("resource.name must be a non-empty string")
        if self.symbol_name is not None:
            if not isinstance(self.symbol_name, str) or not _SYMBOL_RE.fullmatch(
                self.symbol_name
            ):
                raise ResourceDocumentError(
                    "resource.symbol_name must be a portable Python identifier"
                )
        self.metadata = validate_json_object(self.metadata, "resource.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate(current_version=self.schema_version)
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "metadata": copy.deepcopy(self.metadata),
        }
        if self.symbol_name is not None:
            payload["symbol_name"] = self.symbol_name
        return payload

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        expected_type: str | None = None,
        current_version: int = RESOURCE_SCHEMA_VERSION,
    ) -> "ResourceHeader":
        if not isinstance(data, Mapping):
            raise ResourceDocumentError("resource must be an object")
        header = cls(
            schema_version=data.get("schema_version", 0),
            type=data.get("type", ""),
            id=data.get("id", ""),
            name=data.get("name", ""),
            symbol_name=data.get("symbol_name"),
            metadata=validate_json_object(data.get("metadata", {}), "resource.metadata"),
        )
        header.validate(expected_type=expected_type, current_version=current_version)
        return header


@dataclass
class GenericResourceDocument:
    """A typed envelope that preserves domain fields without freezing a schema."""

    header: ResourceHeader
    body: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        return self.header.type

    @property
    def id(self) -> str:
        return self.header.id

    @property
    def name(self) -> str:
        return self.header.name

    @property
    def schema_version(self) -> int:
        return self.header.schema_version

    def validate(self, *, current_version: int = RESOURCE_SCHEMA_VERSION) -> None:
        self.header.validate(current_version=current_version)
        self.body = validate_json_object(self.body, "resource body")
        overlap = RESOURCE_HEADER_FIELDS.intersection(self.body)
        if overlap:
            raise ResourceDocumentError(
                "resource body repeats header fields: " + ", ".join(sorted(overlap))
            )
        validate_unique_object_ids(self.body, reserved_ids=(self.header.id,))

    def to_dict(self) -> dict[str, Any]:
        self.validate(current_version=self.header.schema_version)
        return {**self.header.to_dict(), **copy.deepcopy(self.body)}

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        expected_type: str | None = None,
        current_version: int = RESOURCE_SCHEMA_VERSION,
    ) -> "GenericResourceDocument":
        header = ResourceHeader.from_dict(
            data,
            expected_type=expected_type,
            current_version=current_version,
        )
        body = {
            key: copy.deepcopy(value)
            for key, value in data.items()
            if key not in RESOURCE_HEADER_FIELDS
        }
        document = cls(header=header, body=body)
        document.validate(current_version=current_version)
        return document


@dataclass(frozen=True)
class ResourceReference:
    """Canonical ``res://path#subresource`` reference inside one project."""

    path: PurePosixPath
    subresource: str | None = None

    def __post_init__(self) -> None:
        text = self.path.as_posix()
        if text in {"", "."} or self.path.is_absolute():
            raise ResourceDocumentError("resource path must be project-relative")
        if any(part in {"", ".", ".."} for part in self.path.parts):
            raise ResourceDocumentError("resource path may not contain '.' or '..'")
        if any(":" in part for part in self.path.parts):
            raise ResourceDocumentError("resource path may not contain drive prefixes")
        if self.subresource is not None:
            if not self.subresource or "#" in self.subresource:
                raise ResourceDocumentError("subresource must be a non-empty fragment")

    @property
    def uri(self) -> str:
        value = f"res://{self.path.as_posix()}"
        return value + (f"#{self.subresource}" if self.subresource else "")

    @classmethod
    def parse(
        cls,
        value: str,
        *,
        allow_legacy_project_path: bool = False,
    ) -> "ResourceReference":
        if not isinstance(value, str) or not value.strip():
            raise ResourceDocumentError("resource reference must be a non-empty string")
        normalized = value.strip().replace("\\", "/")
        if normalized.startswith("res://"):
            normalized = normalized[6:]
        elif not allow_legacy_project_path:
            raise ResourceDocumentError("resource reference must start with 'res://'")
        path_value, separator, fragment = normalized.partition("#")
        if "#" in fragment:
            raise ResourceDocumentError("resource reference contains multiple fragments")
        return cls(
            path=PurePosixPath(path_value),
            subresource=fragment if separator else None,
        )

    def resolve(
        self,
        project: ProjectContext,
        *,
        must_exist: bool = False,
    ) -> Path:
        resolved = project.resolve(Path(*self.path.parts))
        project.relative(resolved)
        if must_exist and not resolved.is_file():
            raise ResourceDocumentError(f"Referenced resource does not exist: {self.uri}")
        return resolved

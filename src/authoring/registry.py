"""Small typed registry for the retained UI and background documents."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .resources import (
    BACKGROUND_RESOURCE_TYPE,
    RESOURCE_SCHEMA_VERSION,
    UI_RESOURCE_TYPE,
    GenericResourceDocument,
    ResourceDocumentError,
)


ResourceLoader = Callable[[Mapping[str, Any]], Any]
ResourceValidator = Callable[[Any], None]


@dataclass(frozen=True)
class ResourceTypeSpec:
    """One headless loader entry; editor/plugin contributions are not supported."""

    type_name: str
    display_name: str
    asset_kind: str
    current_version: int = RESOURCE_SCHEMA_VERSION
    loader: ResourceLoader | None = None
    validator: ResourceValidator | None = None

    def validate(self) -> None:
        if not self.type_name or not self.display_name or not self.asset_kind:
            raise ValueError("resource type, display name, and asset kind are required")
        if self.current_version <= 0:
            raise ValueError("resource current_version must be positive")


class ResourceTypeRegistry(Mapping[str, ResourceTypeSpec]):
    """Headless current-version loader registry for retained resource tools."""

    def __init__(self) -> None:
        self._types: dict[str, ResourceTypeSpec] = {}

    def register(self, spec: ResourceTypeSpec) -> ResourceTypeSpec:
        spec.validate()
        if spec.type_name in self._types:
            raise ValueError(f"Duplicate resource type: {spec.type_name}")
        self._types[spec.type_name] = spec
        return spec

    def __getitem__(self, key: str) -> ResourceTypeSpec:
        try:
            return self._types[key]
        except KeyError as exc:
            raise KeyError(f"Unknown resource type: {key}") from exc

    def __iter__(self) -> Iterator[str]:
        return iter(self._types)

    def __len__(self) -> int:
        return len(self._types)

    def spec_for_payload(self, data: Mapping[str, Any]) -> ResourceTypeSpec:
        if not isinstance(data, Mapping):
            raise ResourceDocumentError("resource must be an object")
        resource_type = str(data.get("type") or "")
        if not resource_type:
            raise ResourceDocumentError("resource.type is required")
        try:
            return self[resource_type]
        except KeyError as exc:
            raise ResourceDocumentError(str(exc)) from exc

    def load(
        self,
        data: Mapping[str, Any],
        *,
        expected_type: str | None = None,
    ) -> Any:
        spec = self.spec_for_payload(data)
        if expected_type is not None and spec.type_name != expected_type:
            raise ResourceDocumentError(
                f"Expected resource type {expected_type!r}, got {spec.type_name!r}"
            )
        loader = spec.loader or (
            lambda payload: GenericResourceDocument.from_dict(
                payload,
                expected_type=spec.type_name,
                current_version=spec.current_version,
            )
        )
        document = loader(data)
        if spec.validator is not None:
            spec.validator(document)
        elif isinstance(document, GenericResourceDocument):
            document.validate(current_version=spec.current_version)
        elif hasattr(document, "validate"):
            document.validate()
        return document

    def asset_kind_for_payload(self, data: Mapping[str, Any]) -> str:
        return self.spec_for_payload(data).asset_kind


def build_default_resource_type_registry() -> ResourceTypeRegistry:
    """Register only runtime-backed UI and background documents."""

    from src.game.background_render.document import BackgroundDocument
    from src.ui.document import UIDocument

    def load_ui(payload: Mapping[str, Any]) -> Any:
        if "root" in payload:
            return UIDocument.from_dict(payload)
        return GenericResourceDocument.from_dict(
            payload,
            expected_type=UI_RESOURCE_TYPE,
            current_version=RESOURCE_SCHEMA_VERSION,
        )

    def load_background(payload: Mapping[str, Any]) -> Any:
        if any(key in payload for key in ("layers", "camera", "textures")):
            return BackgroundDocument.from_dict(payload)
        return GenericResourceDocument.from_dict(
            payload,
            expected_type=BACKGROUND_RESOURCE_TYPE,
            current_version=RESOURCE_SCHEMA_VERSION,
        )

    registry = ResourceTypeRegistry()
    registry.register(
        ResourceTypeSpec(
            type_name=UI_RESOURCE_TYPE,
            display_name="UI",
            asset_kind="ui",
            loader=load_ui,
        )
    )
    registry.register(
        ResourceTypeSpec(
            type_name=BACKGROUND_RESOURCE_TYPE,
            display_name="Background",
            asset_kind="background",
            loader=load_background,
        )
    )
    return registry


__all__ = [
    "ResourceTypeRegistry",
    "ResourceTypeSpec",
    "build_default_resource_type_registry",
]

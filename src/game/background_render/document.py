"""Unified BackgroundDocument consumed by editor and runtime.

M6 frozen contract (see docs/EDITOR_ROADMAP_TODO.md):

- The typed ``pystg.background`` envelope wraps exactly the existing shipped
  fields — ``name``, ``description``, ``textures``, ``camera``, ``fog``,
  ``scroll``, ``layers`` — plus tolerated provenance metadata found in
  shipped files (``source``, ``copied_at``, ``note``,
  ``directly_loadable``, ``copied_original_backgrounds``).
- ``from_legacy`` imports a headerless legacy JSON by generating the
  envelope; round-tripping produces the same render output.
- ``DataDrivenBackground.load_from_dict(document.to_dict(), ...)`` yields
  field-identical quads to the original legacy payload.
"""

from __future__ import annotations

import copy
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping

from src.authoring.resources import (
    BACKGROUND_RESOURCE_TYPE,
    RESOURCE_SCHEMA_VERSION,
    ResourceDocumentError,
    ResourceHeader,
    new_resource_id,
)
from src.pattern.expressions import ExpressionError, compile_expression

LEGACY_FIELDS = {
    "name",
    "description",
    "textures",
    "camera",
    "fog",
    "scroll",
    "layers",
}

#: Provenance metadata tolerated from shipped background files.
PROVENANCE_FIELDS = {
    "source",
    "copied_at",
    "note",
    "directly_loadable",
    "copied_original_backgrounds",
}

KNOWN_FIELDS = LEGACY_FIELDS | PROVENANCE_FIELDS
KNOWN_FIELDS = KNOWN_FIELDS | {"bindings"}

_BACKGROUND_BINDING_PATH = re.compile(
    r"^(?:camera\.(?:fovy|z_near|z_far)|fog\.(?:start|end)|"
    r"scroll\.base_speed|layers\.(\d+)\.(?:alpha|z_depth|scroll_multiplier|"
    r"tile\.size|transform\.(?:x|y|scale|rotation)))$"
)


class BackgroundDocumentError(ResourceDocumentError):
    """Raised when a BackgroundDocument violates the unified contract."""


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BackgroundDocumentError(f"{path} must be an object")
    return dict(value)


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BackgroundDocumentError(f"{path} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BackgroundDocumentError(f"{path} must be finite") from exc
    if not math.isfinite(result):
        raise BackgroundDocumentError(f"{path} must be finite")
    return result


def _finite_vector(value: Any, path: str, length: int) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise BackgroundDocumentError(f"{path} must contain {length} numbers")
    return tuple(_finite(item, f"{path}[{index}]") for index, item in enumerate(value))


def _color(value: Any, path: str) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)) or len(value) not in {3, 4}:
        raise BackgroundDocumentError(f"{path} must contain three or four channels")
    result: list[int] = []
    for index, item in enumerate(value):
        if (
            isinstance(item, bool)
            or not isinstance(item, int)
            or not 0 <= item <= 255
        ):
            raise BackgroundDocumentError(
                f"{path}[{index}] must be an integer in 0..255"
            )
        result.append(item)
    return tuple(result)


def _validate_camera(camera: Any) -> None:
    data = _object(camera, "camera")
    for key in ("eye", "at", "up"):
        if key not in data:
            continue
        _finite_vector(data[key], f"camera.{key}", 3)
    for key in ("fovy", "z_near", "z_far"):
        if key not in data:
            continue
        _finite(data[key], f"camera.{key}")
    if (
        "z_near" in data
        and "z_far" in data
        and (
            data.get("z_near", 0.0) <= 0
            or data.get("z_far", 1.0) <= data.get("z_near", 0.0)
        )
    ):
        raise BackgroundDocumentError("camera clipping range is invalid")


def _validate_layers(layers: Any, textures: Mapping[str, Any]) -> None:
    if not isinstance(layers, (list, tuple)):
        raise BackgroundDocumentError("layers must be an array")
    allowed_layer_keys = {
        "name",
        "texture",
        "z_order",
        "z_depth",
        "blend_mode",
        "alpha",
        "scroll_multiplier",
        "tile",
        "variants",
        "enabled",
        "transform",
    }
    for index, layer in enumerate(layers):
        data = _object(layer, f"layers[{index}]")
        if not isinstance(data.get("name"), str) or not data["name"].strip():
            raise BackgroundDocumentError(f"layers[{index}].name must be a non-empty string")
        unknown = set(data).difference(allowed_layer_keys)
        if unknown:
            raise BackgroundDocumentError(
                f"layers[{index}] unknown fields: " + ", ".join(sorted(unknown))
            )
        blend = data.get("blend_mode", "normal")
        if blend not in {"normal", "add", "multiply"}:
            raise BackgroundDocumentError(
                f"layers[{index}].blend_mode must be normal/add/multiply"
            )
        texture = data.get("texture")
        if texture is not None and not isinstance(texture, str):
            raise BackgroundDocumentError(f"layers[{index}].texture must be a texture name")
        if texture is not None and texture not in textures:
            raise BackgroundDocumentError(
                f"layers[{index}].texture references missing texture {texture!r}"
            )
        for key in ("alpha", "z_depth", "scroll_multiplier"):
            if key in data:
                _finite(data[key], f"layers[{index}].{key}")
        if "alpha" in data and not 0.0 <= _finite(data["alpha"], f"layers[{index}].alpha") <= 1.0:
            raise BackgroundDocumentError(f"layers[{index}].alpha must be in 0..1")
        if "z_order" in data and (isinstance(data["z_order"], bool) or not isinstance(data["z_order"], int)):
            raise BackgroundDocumentError(f"layers[{index}].z_order must be an integer")
        if "enabled" in data and not isinstance(data["enabled"], bool):
            raise BackgroundDocumentError(f"layers[{index}].enabled must be a boolean")
        tile = data.get("tile", {})
        tile_data = _object(tile, f"layers[{index}].tile")
        unknown_tile = set(tile_data).difference({"x_range", "y_range", "size"})
        if unknown_tile:
            raise BackgroundDocumentError(
                f"layers[{index}].tile unknown fields: "
                + ", ".join(sorted(unknown_tile))
            )
        for key in ("x_range", "y_range"):
            if key in tile_data and (
                not isinstance(tile_data[key], (list, tuple))
                or len(tile_data[key]) != 2
                or any(isinstance(item, bool) or not isinstance(item, int) for item in tile_data[key])
            ):
                raise BackgroundDocumentError(f"layers[{index}].tile.{key} must be an integer pair")
        if "size" in tile_data and (
            _finite(tile_data["size"], f"layers[{index}].tile.size") <= 0
        ):
            raise BackgroundDocumentError(f"layers[{index}].tile.size must be positive")
        variants = data.get("variants", [])
        if not isinstance(variants, (list, tuple)):
            raise BackgroundDocumentError(
                f"layers[{index}].variants must be an array"
            )
        for variant_index, variant in enumerate(variants):
            variant_data = _object(variant, f"layers[{index}].variants[{variant_index}]")
            unknown_variant = set(variant_data).difference({"offset", "scroll_multiplier"})
            if unknown_variant:
                raise BackgroundDocumentError(
                    f"layers[{index}].variants[{variant_index}] unknown fields: "
                    + ", ".join(sorted(unknown_variant))
                )
            if "offset" in variant_data:
                _finite_vector(
                    variant_data["offset"],
                    f"layers[{index}].variants[{variant_index}].offset",
                    2,
                )
            if "scroll_multiplier" in variant_data:
                _finite(
                    variant_data["scroll_multiplier"],
                    f"layers[{index}].variants[{variant_index}].scroll_multiplier",
                )
        transform = data.get("transform", {})
        transform_data = _object(transform, f"layers[{index}].transform")
        unknown_transform = set(transform_data).difference(
            {"x", "y", "scale", "rotation"}
        )
        if unknown_transform:
            raise BackgroundDocumentError(
                f"layers[{index}].transform unknown fields: "
                + ", ".join(sorted(unknown_transform))
            )
        for key in ("x", "y", "scale", "rotation"):
            if key in transform_data:
                _finite(transform_data[key], f"layers[{index}].transform.{key}")
        if "scale" in transform_data and _finite(transform_data["scale"], f"layers[{index}].transform.scale") <= 0:
            raise BackgroundDocumentError(
                f"layers[{index}].transform.scale must be positive"
            )


def _validate_bindings(bindings: Any, layer_count: int) -> None:
    if bindings is None:
        return
    if not isinstance(bindings, Mapping):
        raise BackgroundDocumentError("bindings must be an object")
    for path, source in bindings.items():
        if not isinstance(path, str) or _BACKGROUND_BINDING_PATH.fullmatch(path) is None:
            raise BackgroundDocumentError(
                f"bindings.{path} is not a renderer-backed background property"
            )
        match = _BACKGROUND_BINDING_PATH.fullmatch(path)
        if match and match.group(1) is not None and int(match.group(1)) >= layer_count:
            raise BackgroundDocumentError(
                f"bindings.{path} references a missing layer"
            )
        if not isinstance(source, str) or not source.strip():
            raise BackgroundDocumentError(f"bindings.{path} must be an expression")
        try:
            compile_expression(source)
        except ExpressionError as exc:
            raise BackgroundDocumentError(
                f"bindings.{path} is invalid: {exc.message}"
            ) from exc


def _validate_textures(textures: Any) -> None:
    data = _object(textures, "textures")
    for key, entry in data.items():
        if not isinstance(key, str) or not key.strip():
            raise BackgroundDocumentError("textures names must be non-empty strings")
        _object(entry, f"textures.{key}")
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            raise BackgroundDocumentError(
                f"textures.{key}.path must be a non-empty string"
            )
        if os.path.isabs(path) or path.startswith(("\\", "/")):
            raise BackgroundDocumentError(f"textures.{key}.path must be project-relative")
        normalized = os.path.normpath(path).replace("\\", "/")
        if normalized == ".." or normalized.startswith("../"):
            raise BackgroundDocumentError(f"textures.{key}.path must stay inside the project")


def _validate_fog(fog: Any) -> None:
    data = _object(fog, "fog")
    unknown = set(data).difference({"enabled", "color", "start", "end"})
    if unknown:
        raise BackgroundDocumentError(
            "fog unknown fields: " + ", ".join(sorted(unknown))
        )
    if "enabled" in data and not isinstance(data["enabled"], bool):
        raise BackgroundDocumentError("fog.enabled must be a boolean")
    if "color" in data:
        _color(data["color"], "fog.color")
    for key in ("start", "end"):
        if key in data:
            _finite(data[key], f"fog.{key}")


def _validate_scroll(scroll: Any) -> None:
    data = _object(scroll, "scroll")
    unknown = set(data).difference({"base_speed", "direction"})
    if unknown:
        raise BackgroundDocumentError(
            "scroll unknown fields: " + ", ".join(sorted(unknown))
        )
    if "base_speed" in data:
        _finite(data["base_speed"], "scroll.base_speed")
    if "direction" in data:
        _finite_vector(data["direction"], "scroll.direction", 2)


@dataclass
class BackgroundDocument:
    """Typed wrapper over the unified background schema."""

    header: ResourceHeader
    body: dict[str, Any]

    @property
    def id(self) -> str:
        return self.header.id

    @property
    def name(self) -> str:
        return str(self.body.get("name", self.header.name))

    @property
    def type(self) -> str:
        return self.header.type

    @property
    def schema_version(self) -> int:
        return self.header.schema_version

    def validate(self) -> None:
        try:
            self.header.validate(
                expected_type=BACKGROUND_RESOURCE_TYPE,
                current_version=RESOURCE_SCHEMA_VERSION,
            )
        except ResourceDocumentError as exc:
            raise BackgroundDocumentError(str(exc)) from exc
        _object(self.body, "background")
        unknown = set(self.body).difference(KNOWN_FIELDS)
        if unknown:
            raise BackgroundDocumentError(
                "background unknown fields: " + ", ".join(sorted(unknown))
            )
        _validate_textures(self.body.get("textures", {}))
        _validate_camera(self.body.get("camera", {}))
        _validate_fog(self.body.get("fog", {}))
        _validate_scroll(self.body.get("scroll", {}))
        layers = self.body.get("layers", [])
        _validate_layers(layers, self.body.get("textures", {}))
        _validate_bindings(self.body.get("bindings"), len(layers))

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {**self.header.to_dict(), **copy.deepcopy(self.body)}

    @classmethod
    def from_dict(cls, value: Any) -> "BackgroundDocument":
        if not isinstance(value, Mapping):
            raise BackgroundDocumentError("background must be an object")
        try:
            header = ResourceHeader.from_dict(
                value,
                expected_type=BACKGROUND_RESOURCE_TYPE,
                current_version=RESOURCE_SCHEMA_VERSION,
            )
        except ResourceDocumentError as exc:
            raise BackgroundDocumentError(str(exc)) from exc
        body = {
            key: copy.deepcopy(item)
            for key, item in value.items()
            if key not in {"schema_version", "type", "id", "name", "symbol_name", "metadata"}
        }
        unknown = set(body).difference(KNOWN_FIELDS)
        if unknown:
            raise BackgroundDocumentError(
                "background unknown fields: " + ", ".join(sorted(unknown))
            )
        document = cls(header=header, body=body)
        document.validate()
        return document

    @classmethod
    def from_legacy(cls, payload: Any) -> "BackgroundDocument":
        """Import a headerless legacy background JSON by generating the envelope."""
        if not isinstance(payload, Mapping):
            raise BackgroundDocumentError("legacy background must be an object")
        unknown = set(payload).difference(KNOWN_FIELDS)
        if unknown:
            raise BackgroundDocumentError(
                "background unknown fields: " + ", ".join(sorted(unknown))
            )
        legacy_name = str(payload.get("name") or "New Background")
        document = cls(
            header=ResourceHeader(
                type=BACKGROUND_RESOURCE_TYPE,
                name=legacy_name,
                id=new_resource_id(),
                metadata={"imported_from": "legacy_background_json"},
            ),
            body=copy.deepcopy(dict(payload)),
        )
        document.validate()
        return document

    def evaluate_bindings(
        self, *, frame: int = 0, time: float | None = None
    ) -> dict[str, Any]:
        """Return a runtime payload with authored bindings evaluated.

        The source document is never mutated.  This keeps timeline/runtime
        feedback read-only while ensuring the formal background renderer sees
        the same bound values as an editor preview.
        """
        self.validate()
        payload = copy.deepcopy(self.body)
        context = {
            "frame": _finite(frame, "bindings.frame"),
            "time": (
                _finite(frame, "bindings.frame") / 60.0
                if time is None
                else _finite(time, "bindings.time")
            ),
        }
        for path, source in (self.body.get("bindings") or {}).items():
            try:
                value = compile_expression(source).eval(context)
                parts = path.split(".")
                target: Any = payload
                for part in parts[:-1]:
                    if part.isdigit():
                        target = target[int(part)]
                    else:
                        target = target[part]
                key = parts[-1]
                numeric_value = _finite(value, f"bindings.{path}")
                if key == "scale" and numeric_value <= 0:
                    raise BackgroundDocumentError(
                        f"bindings.{path} evaluated to a non-positive scale"
                    )
                target[key] = numeric_value
            except BackgroundDocumentError:
                raise
            except (ExpressionError, KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
                raise BackgroundDocumentError(
                    f"bindings.{path} evaluation failed: {exc}"
                ) from exc
        return {**self.header.to_dict(), **payload}

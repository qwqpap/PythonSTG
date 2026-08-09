"""Typed authoring variables shared by the editor and formal runtime.

The variable layer deliberately contains no Qt, renderer, or game-object
references.  Authoring documents keep :class:`VariableSpec` declarations and
defaults; :class:`VariableStore` owns ephemeral runtime values for one run.
"""

from __future__ import annotations

import copy
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


VARIABLE_SCOPES = (
    "project",
    "stage",
    "state",
    "clip",
    "reaction",
    "behavior",
    "engine_snapshot",
)
VARIABLE_WRITERS = ("timeline", "safe_action", "behavior", "engine_snapshot")
VARIABLE_OPERATIONS = ("set", "add", "toggle", "reset")
VARIABLE_REDUCERS = ("override", "add", "multiply", "blend")
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_RESOURCE_RE = re.compile(r"^res://[^\s#]+(?:#[^\s#]+)?$")


class VariableError(ValueError):
    """Raised when a typed variable declaration or runtime write is invalid."""


class VariableTypeError(VariableError):
    """Raised when a value cannot be represented by a declared variable type."""


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VariableTypeError(f"{path} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise VariableTypeError(f"{path} must be a finite number")
    return result


def _json_value(value: Any, path: str) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise VariableTypeError(f"{path} must contain JSON values") from exc
    return copy.deepcopy(value)


def _normalize_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise VariableTypeError(f"{path} must be a boolean")
    return value


def _normalize_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise VariableTypeError(f"{path} must be an integer")
    if not -(2**63) <= value < 2**63:
        raise VariableTypeError(f"{path} is outside the signed 64-bit range")
    return int(value)


def _normalize_float(value: Any, path: str) -> float:
    return _finite(value, path)


def _normalize_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise VariableTypeError(f"{path} must be a string")
    return value


def _mapping(value: Any, keys: tuple[str, ...], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VariableTypeError(f"{path} must be an object with {', '.join(keys)}")
    missing = [key for key in keys if key not in value]
    if missing:
        raise VariableTypeError(f"{path} is missing {', '.join(missing)}")
    unknown = set(value).difference(keys)
    if unknown:
        raise VariableTypeError(
            f"{path} has unknown fields: {', '.join(sorted(str(item) for item in unknown))}"
        )
    return value


def _normalize_vector2(value: Any, path: str) -> dict[str, float]:
    value = _mapping(value, ("x", "y"), path)
    return {key: _finite(value[key], f"{path}.{key}") for key in ("x", "y")}


def _normalize_color(value: Any, path: str) -> dict[str, float]:
    value = _mapping(value, ("r", "g", "b", "a"), path)
    result = {key: _finite(value[key], f"{path}.{key}") for key in ("r", "g", "b", "a")}
    if any(not 0.0 <= item <= 1.0 for item in result.values()):
        raise VariableTypeError(f"{path} channels must be in 0..1")
    return result


def _normalize_resource(value: Any, path: str) -> str:
    if not isinstance(value, str) or _RESOURCE_RE.fullmatch(value.strip()) is None:
        raise VariableTypeError(f"{path} must be a project-relative res:// reference")
    return value.strip()


def _normalize_complex(value: Any, path: str) -> dict[str, float]:
    # Python complex objects are intentionally rejected.  This explicit JSON
    # representation keeps documents portable across runtimes and languages.
    value = _mapping(value, ("real", "imag"), path)
    return {
        "real": _finite(value["real"], f"{path}.real"),
        "imag": _finite(value["imag"], f"{path}.imag"),
    }


_NORMALIZERS = {
    "bool": _normalize_bool,
    "int": _normalize_int,
    "float": _normalize_float,
    "string": _normalize_string,
    "vector2": _normalize_vector2,
    "color": _normalize_color,
    "resource": _normalize_resource,
    "complex": _normalize_complex,
}


@dataclass(frozen=True)
class VariableTypeSpec:
    """Portable description of one built-in or plugin-provided value type."""

    type_id: str
    display_name: str
    json_shape: str
    normalizer: Any | None = field(default=None, repr=False, compare=False)

    def normalize(self, value: Any, path: str = "variable.value") -> Any:
        normalizer = self.normalizer or _NORMALIZERS.get(self.type_id)
        if not callable(normalizer):
            raise VariableTypeError(f"unknown variable type {self.type_id!r}")
        return normalizer(value, path)


class VariableTypeRegistry:
    """Registry for serializable variable types.

    The built-ins are fixed and callable-free in documents.  Plugins may add a
    type by registering a normalizer, but the normalized value still has to be
    JSON-compatible before it can cross the authoring boundary.
    """

    def __init__(self) -> None:
        self._types: dict[str, VariableTypeSpec] = {
            name: VariableTypeSpec(name, name, shape, _NORMALIZERS[name])
            for name, shape in (
                ("bool", "boolean"),
                ("int", "integer"),
                ("float", "number"),
                ("string", "string"),
                ("vector2", "object{x,y}"),
                ("color", "object{r,g,b,a}"),
                ("resource", "res://reference"),
                ("complex", "object{real,imag}"),
            )
        }
        self._normalizers: dict[str, Any] = dict(_NORMALIZERS)

    def __contains__(self, type_id: str) -> bool:
        return type_id in self._types

    def __iter__(self):
        return iter(self._types)

    def get(self, type_id: str) -> VariableTypeSpec | None:
        return self._types.get(type_id)

    def require(self, type_id: str) -> VariableTypeSpec:
        try:
            return self._types[type_id]
        except KeyError as exc:
            raise VariableError(f"unknown variable type {type_id!r}") from exc

    def register(
        self,
        type_id: str,
        *,
        display_name: str | None = None,
        json_shape: str = "json",
        normalizer=None,
    ) -> VariableTypeSpec:
        if not isinstance(type_id, str) or not _NAME_RE.fullmatch(type_id):
            raise VariableError("variable type id must be a portable identifier")
        if type_id in self._types:
            raise VariableError(f"duplicate variable type: {type_id}")
        if not callable(normalizer):
            raise VariableError("a plugin variable type needs a normalizer")
        spec = VariableTypeSpec(
            type_id,
            display_name or type_id,
            json_shape,
            normalizer,
        )
        self._types[type_id] = spec
        self._normalizers[type_id] = normalizer
        return spec

    def normalize(self, type_id: str, value: Any, path: str = "variable.value") -> Any:
        self.require(type_id)
        normalizer = self._normalizers[type_id]
        normalized = normalizer(value, path)
        return _json_value(normalized, path)


DEFAULT_VARIABLE_TYPES = VariableTypeRegistry()


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class VariableRef:
    """A typed reference used by bindings and explicit output mappings."""

    name: str
    scope: str | None = None
    type: str | None = None

    def validate(self, *, path: str = "variable_ref") -> None:
        if not isinstance(self.name, str) or _NAME_RE.fullmatch(self.name.strip()) is None:
            raise VariableError(f"{path}.name must be a dotted identifier")
        self.name = self.name.strip()
        if self.scope is not None and self.scope not in VARIABLE_SCOPES:
            raise VariableError(f"{path}.scope is not a supported variable scope")
        if self.type is not None:
            DEFAULT_VARIABLE_TYPES.require(self.type)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        result: dict[str, Any] = {"name": self.name}
        if self.scope is not None:
            result["scope"] = self.scope
        if self.type is not None:
            result["type"] = self.type
        return result

    @classmethod
    def from_dict(cls, value: Any) -> "VariableRef":
        if isinstance(value, VariableRef):
            result = copy.deepcopy(value)
        elif isinstance(value, str):
            result = cls(name=value)
        elif isinstance(value, Mapping):
            unknown = set(value).difference({"name", "scope", "type"})
            if unknown:
                raise VariableError("variable_ref has unknown fields: " + ", ".join(sorted(unknown)))
            result = cls(
                name=str(value.get("name", "")),
                scope=value.get("scope"),
                type=value.get("type"),
            )
        else:
            raise VariableError("variable_ref must be a string or object")
        result.validate()
        return result


@dataclass
class VariableSpec:
    """Authoring declaration; only this data is serialized into a Scene."""

    name: str
    type: str
    default: Any
    scope: str = "stage"
    id: str = field(default_factory=_new_id)
    writable_by: tuple[str, ...] = ()
    readers: tuple[str, ...] = ()
    animatable: bool = False
    record_in_replay: bool = True
    debug_display: str = "value"
    reducer: str | None = None
    behavior_output: bool = False
    owner_id: str | None = None

    @property
    def writers(self) -> tuple[str, ...]:
        """Readable alias used by editor and descriptor integrations."""

        return self.writable_by

    def validate(self, *, path: str = "variable") -> None:
        try:
            uuid.UUID(str(self.id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise VariableError(f"{path}.id must be a UUID") from exc
        if not isinstance(self.name, str) or _NAME_RE.fullmatch(self.name.strip()) is None:
            raise VariableError(f"{path}.name must be a dotted identifier")
        self.name = self.name.strip()
        if self.scope not in VARIABLE_SCOPES:
            raise VariableError(f"{path}.scope is not supported: {self.scope!r}")
        DEFAULT_VARIABLE_TYPES.require(self.type)
        self.default = DEFAULT_VARIABLE_TYPES.normalize(self.type, self.default, f"{path}.default")
        if not isinstance(self.writable_by, (tuple, list)):
            raise VariableError(f"{path}.writable_by must be an array")
        self.writable_by = tuple(str(item) for item in self.writable_by)
        unknown = set(self.writable_by).difference(VARIABLE_WRITERS)
        if unknown:
            raise VariableError(f"{path}.writable_by has unknown writers: {', '.join(sorted(unknown))}")
        if not isinstance(self.readers, (tuple, list)):
            raise VariableError(f"{path}.readers must be an array")
        self.readers = tuple(str(item) for item in self.readers)
        if self.scope == "engine_snapshot" and self.writable_by not in ((), ("engine_snapshot",)):
            raise VariableError(f"{path}: engine_snapshot variables are read-only to content")
        if self.scope == "engine_snapshot" and self.animatable:
            raise VariableError(f"{path}: engine_snapshot variables cannot be animatable")
        if not isinstance(self.animatable, bool) or not isinstance(self.record_in_replay, bool):
            raise VariableError(f"{path}.animatable and record_in_replay must be booleans")
        if not isinstance(self.debug_display, str) or not self.debug_display.strip():
            raise VariableError(f"{path}.debug_display must be text")
        if self.reducer is not None and self.reducer not in VARIABLE_REDUCERS:
            raise VariableError(f"{path}.reducer is not supported: {self.reducer!r}")
        if self.owner_id is not None:
            try:
                uuid.UUID(str(self.owner_id))
            except (ValueError, AttributeError, TypeError) as exc:
                raise VariableError(f"{path}.owner_id must be a UUID") from exc
        if self.behavior_output and "behavior" not in self.writable_by:
            raise VariableError(f"{path}.behavior_output requires the behavior writer")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        result = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "default": copy.deepcopy(self.default),
            "scope": self.scope,
            "writable_by": list(self.writable_by),
            "readers": list(self.readers),
            "animatable": self.animatable,
            "record_in_replay": self.record_in_replay,
            "debug_display": self.debug_display,
            "reducer": self.reducer,
            "behavior_output": self.behavior_output,
        }
        if self.owner_id is not None:
            result["owner_id"] = self.owner_id
        return result

    @classmethod
    def from_dict(cls, value: Any) -> "VariableSpec":
        if isinstance(value, VariableSpec):
            result = copy.deepcopy(value)
        elif isinstance(value, Mapping):
            allowed = {
                "id", "name", "type", "default", "scope", "writable_by", "readers",
                "animatable", "record_in_replay", "debug_display", "reducer",
                "behavior_output", "owner_id",
            }
            unknown = set(value).difference(allowed)
            if unknown:
                raise VariableError("variable has unknown fields: " + ", ".join(sorted(unknown)))
            result = cls(
                id=str(value.get("id") or _new_id()),
                name=str(value.get("name", "")),
                type=str(value.get("type", "")),
                default=copy.deepcopy(value.get("default")),
                scope=str(value.get("scope", "stage")),
                writable_by=tuple(str(item) for item in value.get("writable_by", ())),
                readers=tuple(str(item) for item in value.get("readers", ())),
                animatable=value.get("animatable", False),
                record_in_replay=value.get("record_in_replay", True),
                debug_display=str(value.get("debug_display", "value")),
                reducer=value.get("reducer"),
                behavior_output=bool(value.get("behavior_output", False)),
                owner_id=value.get("owner_id"),
            )
        else:
            raise VariableError("variable must be an object")
        result.validate()
        return result


@dataclass
class VariableOutputMapping:
    """Explicit Behavior output -> declared variable mapping."""

    source: VariableRef | str
    target: VariableRef | str
    operation: str = "set"
    id: str = field(default_factory=_new_id)

    def validate(self, *, path: str = "output_mapping") -> None:
        try:
            uuid.UUID(str(self.id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise VariableError(f"{path}.id must be a UUID") from exc
        self.source = VariableRef.from_dict(self.source)
        self.target = VariableRef.from_dict(self.target)
        if self.operation not in VARIABLE_OPERATIONS:
            raise VariableError(f"{path}.operation is not supported")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "operation": self.operation,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "VariableOutputMapping":
        if not isinstance(value, Mapping):
            raise VariableError("output_mapping must be an object")
        result = cls(
            id=str(value.get("id") or _new_id()),
            source=VariableRef.from_dict(value.get("source")),
            target=VariableRef.from_dict(value.get("target")),
            operation=str(value.get("operation", "set")),
        )
        result.validate()
        return result


OutputMappingSpec = VariableOutputMapping


def _add_values(type_id: str, left: Any, right: Any) -> Any:
    if type_id in {"int", "float"}:
        return left + right
    if type_id == "vector2":
        return {key: left[key] + right[key] for key in ("x", "y")}
    if type_id == "complex":
        return {key: left[key] + right[key] for key in ("real", "imag")}
    raise VariableError(f"add is not supported for variable type {type_id!r}")


def _multiply_values(type_id: str, left: Any, right: Any) -> Any:
    if type_id in {"int", "float"}:
        return left * right
    if type_id == "vector2":
        return {key: left[key] * right for key in ("x", "y")}
    if type_id == "complex":
        return {
            "real": left["real"] * right["real"] - left["imag"] * right["imag"],
            "imag": left["real"] * right["imag"] + left["imag"] * right["real"],
        }
    raise VariableError(f"multiply is not supported for variable type {type_id!r}")


@dataclass(frozen=True)
class VariableWrite:
    name: str
    scope: str
    owner_id: str
    writer: str
    operation: str
    value: Any
    frame: int
    order: int = 0


class VariableStore:
    """Ephemeral scope-aware values with explicit write capabilities."""

    def __init__(self, specs: Iterable[VariableSpec] = ()) -> None:
        self.specs = tuple(copy.deepcopy(tuple(specs)))
        for item in self.specs:
            item.validate()
        self._by_key: dict[tuple[str, str, str | None], VariableSpec] = {}
        self._by_name: dict[tuple[str, str | None], VariableSpec] = {}
        for item in self.specs:
            key = (item.scope, item.name, item.owner_id)
            if key in self._by_key:
                raise VariableError(f"duplicate variable declaration: {item.scope}:{item.name}")
            self._by_key[key] = item
            self._by_name.setdefault((item.name, item.scope), item)
        self._stores: dict[tuple[str, str], dict[str, Any]] = {}
        self._active: set[tuple[str, str]] = set()
        self._writes: list[VariableWrite] = []
        self.frame = 0
        self.reset()

    @property
    def writes(self) -> tuple[VariableWrite, ...]:
        return tuple(self._writes)

    def reset(self, *, project_values: Mapping[str, Any] | None = None) -> None:
        self._stores.clear()
        self._active.clear()
        self._writes.clear()
        self.frame = 0
        self.enter_scope("project", "project", values=project_values)
        self.enter_scope("stage", "stage")
        self.enter_scope("engine_snapshot", "engine_snapshot")

    def _spec(self, name: str, scope: str | None = None, owner_id: str | None = None) -> VariableSpec:
        if scope is not None:
            for key in ((scope, name, owner_id), (scope, name, None)):
                item = self._by_key.get(key)
                if item is not None:
                    return item
        if owner_id is not None:
            for (candidate_scope, candidate_name, candidate_owner), item in self._by_key.items():
                if candidate_name == name and candidate_owner == str(owner_id):
                    return item
        for candidate_scope in ("behavior", "clip", "reaction", "state", "stage", "project", "engine_snapshot"):
            item = self._by_name.get((name, candidate_scope))
            if item is not None:
                return item
        raise VariableError(f"unknown variable {name!r}")

    def _owner(self, scope: str, owner_id: str | None) -> str:
        if scope in {"project", "stage", "engine_snapshot"}:
            return scope
        if not owner_id:
            raise VariableError(f"{scope} variables require an owner id")
        return str(owner_id)

    def enter_scope(self, scope: str, owner_id: str, *, values: Mapping[str, Any] | None = None) -> None:
        if scope not in VARIABLE_SCOPES:
            raise VariableError(f"unknown variable scope {scope!r}")
        key = (scope, self._owner(scope, owner_id))
        values = values or {}
        bucket: dict[str, Any] = {}
        for spec in self.specs:
            if spec.scope != scope or (spec.owner_id is not None and spec.owner_id != key[1]):
                continue
            raw = values.get(spec.name, spec.default)
            bucket[spec.name] = DEFAULT_VARIABLE_TYPES.normalize(spec.type, raw, f"{scope}.{spec.name}")
        self._stores[key] = bucket
        self._active.add(key)

    def exit_scope(self, scope: str, owner_id: str) -> None:
        key = (scope, self._owner(scope, owner_id))
        if scope in {"project", "stage", "engine_snapshot"}:
            if scope == "stage":
                self._stores.pop(key, None)
                self._active.discard(key)
            return
        self._stores.pop(key, None)
        self._active.discard(key)

    def read(self, ref: VariableRef | str, *, owner_id: str | None = None) -> Any:
        reference = VariableRef.from_dict(ref)
        spec = self._spec(reference.name, reference.scope, owner_id)
        if reference.type is not None and reference.type != spec.type:
            raise VariableError(f"variable {reference.name!r} expects {spec.type}, got {reference.type}")
        key = (spec.scope, self._owner(spec.scope, owner_id or spec.owner_id))
        bucket = self._stores.get(key)
        if bucket is None:
            if spec.scope in {"state", "clip", "reaction", "behavior"} and owner_id is not None:
                raise VariableError(
                    f"{spec.scope} variable {spec.name!r} is not active for owner {owner_id}"
                )
            return copy.deepcopy(spec.default)
        return copy.deepcopy(bucket.get(spec.name, spec.default))

    def _write_value(self, spec: VariableSpec, current: Any, value: Any, operation: str) -> Any:
        if operation == "reset":
            return copy.deepcopy(spec.default)
        normalized = DEFAULT_VARIABLE_TYPES.normalize(spec.type, value, f"{spec.scope}.{spec.name}")
        if operation == "set":
            return normalized
        if operation == "toggle":
            if spec.type != "bool":
                raise VariableError("toggle is only valid for bool variables")
            return not current
        if operation == "add":
            return DEFAULT_VARIABLE_TYPES.normalize(spec.type, _add_values(spec.type, current, normalized), f"{spec.scope}.{spec.name}")
        raise VariableError(f"unsupported variable operation {operation!r}")

    def write(
        self,
        ref: VariableRef | str,
        value: Any = None,
        *,
        writer: str,
        operation: str = "set",
        owner_id: str | None = None,
        frame: int | None = None,
        order: int = 0,
    ) -> Any:
        if writer not in VARIABLE_WRITERS:
            raise VariableError(f"unknown variable writer {writer!r}")
        if operation not in VARIABLE_OPERATIONS:
            raise VariableError(f"unknown variable operation {operation!r}")
        reference = VariableRef.from_dict(ref)
        spec = self._spec(reference.name, reference.scope, owner_id)
        if writer == "behavior" and not spec.behavior_output:
            raise VariableError(f"behavior may only publish declared output {spec.name!r}")
        if writer not in spec.writable_by:
            raise VariableError(f"writer {writer!r} is not allowed to write {spec.scope}:{spec.name}")
        if writer == "engine_snapshot":
            raise VariableError("Engine Snapshot is published through publish_engine_snapshot only")
        if writer == "timeline" and not spec.animatable:
            raise VariableError(f"timeline cannot animate non-animatable variable {spec.name!r}")
        key = (spec.scope, self._owner(spec.scope, owner_id or spec.owner_id))
        if key not in self._stores:
            self.enter_scope(spec.scope, key[1])
        bucket = self._stores[key]
        current = bucket.get(spec.name, spec.default)
        result = self._write_value(spec, current, value, operation)
        bucket[spec.name] = result
        self._writes.append(VariableWrite(spec.name, spec.scope, key[1], writer, operation, copy.deepcopy(result), self.frame if frame is None else int(frame), int(order)))
        return copy.deepcopy(result)

    def publish_engine_snapshot(self, values: Mapping[str, Any], *, frame: int | None = None) -> None:
        if not isinstance(values, Mapping):
            raise VariableError("engine snapshot must be an object")
        key = ("engine_snapshot", "engine_snapshot")
        bucket = self._stores.setdefault(key, {})
        self._active.add(key)
        for name, value in values.items():
            spec = self._spec(str(name), "engine_snapshot")
            bucket[spec.name] = DEFAULT_VARIABLE_TYPES.normalize(spec.type, value, f"engine_snapshot.{spec.name}")
            self._writes.append(VariableWrite(spec.name, spec.scope, key[1], "engine_snapshot", "set", copy.deepcopy(bucket[spec.name]), self.frame if frame is None else int(frame)))

    def set_frame(self, frame: int) -> None:
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise VariableError("variable frame must be a non-negative integer")
        self.frame = frame

    def snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        result: dict[str, dict[str, dict[str, Any]]] = {}
        for (scope, owner), values in sorted(self._stores.items()):
            result.setdefault(scope, {})[owner] = copy.deepcopy(values)
        return result

    def flat_snapshot(self) -> dict[str, Any]:
        """Return a debug-friendly name -> value overlay without mutating state."""
        result: dict[str, Any] = {}
        for values in self._stores.values():
            result.update(copy.deepcopy(values))
        return result


VariableRuntimeStore = VariableStore


__all__ = [
    "DEFAULT_VARIABLE_TYPES",
    "OutputMappingSpec",
    "VARIABLE_OPERATIONS",
    "VARIABLE_REDUCERS",
    "VARIABLE_SCOPES",
    "VARIABLE_WRITERS",
    "VariableError",
    "VariableOutputMapping",
    "VariableRef",
    "VariableSpec",
    "VariableStore",
    "VariableRuntimeStore",
    "VariableTypeError",
    "VariableTypeRegistry",
    "VariableTypeSpec",
    "VariableWrite",
]

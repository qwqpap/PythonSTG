"""Version-locked pattern presets with transactional migration semantics.

The preset layer is authoring data only.  A preset instance resolves to a
normal :class:`PatternDocument` and is then compiled by the existing formal
compiler; it never creates a second runtime or stores expanded nodes in the
owning scene.
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.authoring.resources import new_resource_id

from .compiler import PatternCompiler
from .document import PatternDocument, PatternDocumentError


_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
_MEMBER_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_VALUE_TYPES = frozenset(
    {"int", "float", "bool", "string", "color", "enum", "vec2", "reaction"}
)


class PresetDiagnosticError(ValueError):
    """Structured authoring error with a stable code and JSON path."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.detail = message
        super().__init__(f"{path}: {message}")


def _error(code: str, path: str, message: str) -> PresetDiagnosticError:
    return PresetDiagnosticError(code, path, message)


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error("type_mismatch", path, "must be an object")
    return value


def _known(data: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data).difference(allowed))
    if unknown:
        raise _error("unknown_field", path, "unknown fields: " + ", ".join(unknown))


def _required(data: Mapping[str, Any], fields: Iterable[str], path: str) -> None:
    for name in fields:
        if name not in data:
            raise _error("missing_field", f"{path}.{name}", "is required")


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error("type_mismatch", path, "must be a non-empty string")
    return value.strip()


def _member_id(value: Any, path: str) -> str:
    result = _text(value, path)
    if not _MEMBER_ID_RE.fullmatch(result):
        raise _error("invalid_id", path, "must be a portable member id")
    return result


def _version(value: Any, path: str) -> str:
    result = _text(value, path)
    if not _VERSION_RE.fullmatch(result):
        raise _error("invalid_version", path, "must be an exact major.minor.patch version")
    return result


def _json_copy(value: Any, path: str) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise _error("not_json", path, "must contain JSON-compatible values") from exc


def _check_value(value: Any, value_type: str, path: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    valid = False
    if value_type == "int":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif value_type == "float":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif value_type == "bool":
        valid = isinstance(value, bool)
    elif value_type in {"string", "color", "enum"}:
        valid = isinstance(value, str)
    elif value_type == "vec2":
        valid = (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
        )
    elif value_type == "reaction":
        valid = isinstance(value, Mapping)
    if not valid:
        raise _error(
            "parameter_type_mismatch",
            path,
            f"must be {value_type}",
        )


@dataclass(frozen=True)
class PresetParameter:
    id: str
    value_type: str
    default: Any
    target: str
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()

    def validate(self, path: str = "parameter") -> None:
        _member_id(self.id, f"{path}.id")
        if self.value_type not in _VALUE_TYPES - {"reaction"}:
            raise _error("unknown_value_type", f"{path}.type", "unsupported parameter type")
        _member_id(self.target, f"{path}.target")
        _check_value(self.default, self.value_type, f"{path}.default")
        if self.minimum is not None and (
            isinstance(self.minimum, bool) or not isinstance(self.minimum, (int, float))
        ):
            raise _error("type_mismatch", f"{path}.minimum", "must be a number")
        if self.maximum is not None and (
            isinstance(self.maximum, bool) or not isinstance(self.maximum, (int, float))
        ):
            raise _error("type_mismatch", f"{path}.maximum", "must be a number")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise _error("invalid_range", path, "minimum must not exceed maximum")
        if self.value_type == "enum" and not self.choices:
            raise _error("missing_choices", f"{path}.choices", "enum parameters need choices")
        if self.choices and any(not isinstance(item, str) for item in self.choices):
            raise _error("type_mismatch", f"{path}.choices", "must contain strings")
        self.validate_value(self.default, f"{path}.default")

    def validate_value(self, value: Any, path: str) -> None:
        _check_value(value, self.value_type, path)
        if self.value_type in {"int", "float"}:
            if self.minimum is not None and value < self.minimum:
                raise _error("parameter_out_of_range", path, f"must be >= {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise _error("parameter_out_of_range", path, f"must be <= {self.maximum}")
        if self.value_type == "enum" and value not in self.choices:
            raise _error("parameter_choice_invalid", path, "must be one of: " + ", ".join(self.choices))

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        result: dict[str, Any] = {
            "id": self.id,
            "type": self.value_type,
            "default": _json_copy(self.default, "parameter.default"),
            "target": self.target,
        }
        if self.minimum is not None:
            result["minimum"] = self.minimum
        if self.maximum is not None:
            result["maximum"] = self.maximum
        if self.choices:
            result["choices"] = list(self.choices)
        return result

    @classmethod
    def from_dict(cls, value: Any, path: str = "parameter") -> "PresetParameter":
        data = _object(value, path)
        _known(data, {"id", "type", "default", "target", "minimum", "maximum", "choices"}, path)
        _required(data, ("id", "type", "default", "target"), path)
        choices = data.get("choices", ())
        if not isinstance(choices, (list, tuple)):
            raise _error("type_mismatch", f"{path}.choices", "must be an array")
        item = cls(
            id=data["id"],
            value_type=data["type"],
            default=_json_copy(data["default"], f"{path}.default"),
            target=data["target"],
            minimum=data.get("minimum"),
            maximum=data.get("maximum"),
            choices=tuple(choices),
        )
        item.validate(path)
        return item


@dataclass(frozen=True)
class PresetSlot:
    id: str
    value_type: str
    target: str
    default: Any = None
    nullable: bool = False

    def validate(self, path: str = "slot") -> None:
        _member_id(self.id, f"{path}.id")
        if self.value_type not in _VALUE_TYPES:
            raise _error("unknown_value_type", f"{path}.type", "unsupported slot type")
        _member_id(self.target, f"{path}.target")
        if not isinstance(self.nullable, bool):
            raise _error("type_mismatch", f"{path}.nullable", "must be a boolean")
        _check_value(self.default, self.value_type, f"{path}.default", nullable=self.nullable)

    def validate_value(self, value: Any, path: str) -> None:
        _check_value(value, self.value_type, path, nullable=self.nullable)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "type": self.value_type,
            "target": self.target,
            "default": _json_copy(self.default, "slot.default"),
            "nullable": self.nullable,
        }

    @classmethod
    def from_dict(cls, value: Any, path: str = "slot") -> "PresetSlot":
        data = _object(value, path)
        _known(data, {"id", "type", "target", "default", "nullable"}, path)
        _required(data, ("id", "type", "target", "default", "nullable"), path)
        item = cls(
            id=data["id"],
            value_type=data["type"],
            target=data["target"],
            default=_json_copy(data["default"], f"{path}.default"),
            nullable=data["nullable"],
        )
        item.validate(path)
        return item


@dataclass(frozen=True)
class PresetDescriptor:
    preset_id: str
    version: str
    display_name: str
    template: Mapping[str, Any]
    category: str = "basic"
    description: str = ""
    lifecycle: Mapping[str, Any] = field(default_factory=dict)
    budget: Mapping[str, Any] = field(default_factory=dict)
    parameters: tuple[PresetParameter, ...] = ()
    slots: tuple[PresetSlot, ...] = ()
    inputs: Mapping[str, str] = field(default_factory=dict)
    outputs: Mapping[str, str] = field(default_factory=dict)
    events: Mapping[str, str] = field(default_factory=dict)
    internal_nodes: tuple[Mapping[str, Any], ...] = ()

    def validate(self, path: str = "preset") -> None:
        preset_id = _text(self.preset_id, f"{path}.id")
        if not _ID_RE.fullmatch(preset_id):
            raise _error("invalid_id", f"{path}.id", "must be a namespaced lowercase id")
        _version(self.version, f"{path}.version")
        _text(self.display_name, f"{path}.display_name")
        _member_id(self.category, f"{path}.category")
        if not isinstance(self.description, str):
            raise _error("type_mismatch", f"{path}.description", "must be a string")
        lifecycle = _object(self.lifecycle, f"{path}.lifecycle")
        _known(lifecycle, {"owner_scope", "cancel_policy", "completion_event"}, f"{path}.lifecycle")
        budget = _object(self.budget, f"{path}.budget")
        _known(budget, {"max_bullets_per_burst", "max_bullets_total", "max_instances"}, f"{path}.budget")
        for name, value in budget.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise _error("type_mismatch", f"{path}.budget.{name}", "must be a positive integer")
        try:
            PatternDocument.from_dict(_json_copy(self.template, f"{path}.template"))
        except PatternDocumentError as exc:
            raise _error("invalid_template", f"{path}.template", str(exc)) from exc
        self._validate_unique_members(self.parameters, "parameters", path)
        self._validate_unique_members(self.slots, "slots", path)
        for index, parameter in enumerate(self.parameters):
            if not isinstance(parameter, PresetParameter):
                raise _error("type_mismatch", f"{path}.parameters[{index}]", "must be a parameter")
            parameter.validate(f"{path}.parameters[{index}]")
        for index, slot in enumerate(self.slots):
            if not isinstance(slot, PresetSlot):
                raise _error("type_mismatch", f"{path}.slots[{index}]", "must be a slot")
            slot.validate(f"{path}.slots[{index}]")
        for field_name, ports in (("inputs", self.inputs), ("outputs", self.outputs), ("events", self.events)):
            if not isinstance(ports, Mapping):
                raise _error("type_mismatch", f"{path}.{field_name}", "must be an object")
            for key, value in ports.items():
                _member_id(key, f"{path}.{field_name}.{key}")
                _text(value, f"{path}.{field_name}.{key}")
        seen_nodes: set[str] = set()
        for index, node_value in enumerate(self.internal_nodes):
            node_path = f"{path}.internal_nodes[{index}]"
            node = _object(node_value, node_path)
            _known(node, {"id", "kind", "label", "target"}, node_path)
            _required(node, ("id", "kind", "label"), node_path)
            node_id = _member_id(node["id"], f"{node_path}.id")
            if node_id in seen_nodes:
                raise _error("duplicate_id", f"{node_path}.id", "must be unique")
            seen_nodes.add(node_id)
            _text(node["kind"], f"{node_path}.kind")
            _text(node["label"], f"{node_path}.label")
            if "target" in node:
                _member_id(node["target"], f"{node_path}.target")

    @staticmethod
    def _validate_unique_members(items: Iterable[Any], name: str, path: str) -> None:
        seen: set[str] = set()
        for index, item in enumerate(items):
            item_id = getattr(item, "id", None)
            if item_id in seen:
                raise _error("duplicate_id", f"{path}.{name}[{index}].id", "must be unique")
            seen.add(item_id)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.preset_id,
            "version": self.version,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "lifecycle": _json_copy(self.lifecycle, "preset.lifecycle"),
            "budget": _json_copy(self.budget, "preset.budget"),
            "template": _json_copy(self.template, "preset.template"),
            "parameters": [item.to_dict() for item in self.parameters],
            "slots": [item.to_dict() for item in self.slots],
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "events": dict(self.events),
            "internal_nodes": [_json_copy(item, "preset.internal_nodes") for item in self.internal_nodes],
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PresetDescriptor":
        data = _object(value, "preset")
        _known(
            data,
            {"id", "version", "display_name", "template", "category", "description", "lifecycle", "budget", "parameters", "slots", "inputs", "outputs", "events", "internal_nodes"},
            "preset",
        )
        _required(data, ("id", "version", "display_name", "template"), "preset")
        raw_parameters = data.get("parameters", ())
        raw_slots = data.get("slots", ())
        raw_nodes = data.get("internal_nodes", ())
        for raw, name in ((raw_parameters, "parameters"), (raw_slots, "slots"), (raw_nodes, "internal_nodes")):
            if not isinstance(raw, (list, tuple)):
                raise _error("type_mismatch", f"preset.{name}", "must be an array")
        descriptor = cls(
            preset_id=data["id"],
            version=data["version"],
            display_name=data["display_name"],
            template=_json_copy(data["template"], "preset.template"),
            category=data.get("category", "basic"),
            description=data.get("description", ""),
            lifecycle=_object(data.get("lifecycle", {}), "preset.lifecycle"),
            budget=_object(data.get("budget", {}), "preset.budget"),
            parameters=tuple(PresetParameter.from_dict(item, f"preset.parameters[{index}]") for index, item in enumerate(raw_parameters)),
            slots=tuple(PresetSlot.from_dict(item, f"preset.slots[{index}]") for index, item in enumerate(raw_slots)),
            inputs=_object(data.get("inputs", {}), "preset.inputs"),
            outputs=_object(data.get("outputs", {}), "preset.outputs"),
            events=_object(data.get("events", {}), "preset.events"),
            internal_nodes=tuple(_json_copy(item, f"preset.internal_nodes[{index}]") for index, item in enumerate(raw_nodes)),
        )
        descriptor.validate()
        return descriptor


@dataclass(frozen=True)
class PresetInstance:
    id: str
    preset_id: str
    version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    slot_overrides: Mapping[str, Any] = field(default_factory=dict)

    def validate(self, path: str = "instance") -> None:
        try:
            uuid.UUID(self.id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise _error("invalid_id", f"{path}.id", "must be a UUID") from exc
        preset_id = _text(self.preset_id, f"{path}.preset_id")
        if not _ID_RE.fullmatch(preset_id):
            raise _error("invalid_id", f"{path}.preset_id", "must be a namespaced lowercase id")
        _version(self.version, f"{path}.version")
        for field_name, values in (("parameters", self.parameters), ("slot_overrides", self.slot_overrides)):
            if not isinstance(values, Mapping):
                raise _error("type_mismatch", f"{path}.{field_name}", "must be an object")
            _json_copy(values, f"{path}.{field_name}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "preset_id": self.preset_id,
            "version": self.version,
            "parameters": _json_copy(self.parameters, "instance.parameters"),
            "slot_overrides": _json_copy(self.slot_overrides, "instance.slot_overrides"),
        }

    @classmethod
    def new(
        cls,
        descriptor: PresetDescriptor,
        *,
        instance_id: str | None = None,
        parameters: Mapping[str, Any] | None = None,
        slot_overrides: Mapping[str, Any] | None = None,
    ) -> "PresetInstance":
        descriptor.validate()
        instance = cls(
            id=instance_id or new_resource_id(),
            preset_id=descriptor.preset_id,
            version=descriptor.version,
            parameters=_json_copy(parameters or {}, "instance.parameters"),
            slot_overrides=_json_copy(slot_overrides or {}, "instance.slot_overrides"),
        )
        instance.validate()
        return instance

    @classmethod
    def from_dict(cls, value: Any) -> "PresetInstance":
        data = _object(value, "instance")
        _known(data, {"id", "preset_id", "version", "parameters", "slot_overrides"}, "instance")
        _required(data, ("id", "preset_id", "version", "parameters", "slot_overrides"), "instance")
        instance = cls(
            id=data["id"],
            preset_id=data["preset_id"],
            version=data["version"],
            parameters=_json_copy(data["parameters"], "instance.parameters"),
            slot_overrides=_json_copy(data["slot_overrides"], "instance.slot_overrides"),
        )
        instance.validate()
        return instance


@dataclass(frozen=True)
class VirtualPresetNode:
    virtual_id: str
    instance_id: str
    internal_id: str
    kind: str
    label: str
    target: str | None = None


@dataclass(frozen=True)
class ResolvedPreset:
    instance: PresetInstance
    descriptor: PresetDescriptor
    document: PatternDocument


def _set_path(payload: dict[str, Any], target: str, value: Any, path: str) -> None:
    parts = target.split(".")
    cursor: dict[str, Any] = payload
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            raise _error("unknown_target", path, f"target {target!r} does not exist")
        cursor = child
    if parts[-1] not in cursor and parts[0] != "metadata":
        raise _error("unknown_target", path, f"target {target!r} does not exist")
    cursor[parts[-1]] = _json_copy(value, path)


class PresetResolver:
    def __init__(self, descriptors: Iterable[PresetDescriptor]):
        self.registry = PresetRegistry(descriptors)

    def resolve(self, instance: PresetInstance) -> ResolvedPreset:
        instance.validate()
        descriptor = self.registry.resolve(instance.preset_id, instance.version)
        parameters = {item.id: item for item in descriptor.parameters}
        slots = {item.id: item for item in descriptor.slots}
        unknown_parameters = sorted(set(instance.parameters).difference(parameters))
        if unknown_parameters:
            name = unknown_parameters[0]
            raise _error("unknown_parameter", f"instance.parameters.{name}", "is not exposed by the preset")
        unknown_slots = sorted(set(instance.slot_overrides).difference(slots))
        if unknown_slots:
            name = unknown_slots[0]
            raise _error("unknown_slot", f"instance.slot_overrides.{name}", "is not exposed by the preset")
        payload = _json_copy(descriptor.template, "preset.template")
        payload["id"] = instance.id
        payload["name"] = descriptor.display_name
        metadata = payload.setdefault("metadata", {})
        metadata["preset_origin"] = {
            "preset_id": descriptor.preset_id,
            "version": descriptor.version,
            "instance_id": instance.id,
        }
        metadata["preset_instance"] = instance.to_dict()
        metadata["preset_internal_node_ids"] = [
            str(node["id"]) for node in descriptor.internal_nodes
        ]
        for item in descriptor.parameters:
            value = instance.parameters.get(item.id, item.default)
            item.validate_value(value, f"instance.parameters.{item.id}")
            _set_path(payload, item.target, value, f"parameters.{item.id}.target")
        for item in descriptor.slots:
            value = instance.slot_overrides.get(item.id, item.default)
            item.validate_value(value, f"instance.slot_overrides.{item.id}")
            _set_path(payload, item.target, value, f"slots.{item.id}.target")
        try:
            document = PatternDocument.from_dict(payload)
        except PatternDocumentError as exc:
            raise _error("resolved_pattern_invalid", "preset.template", str(exc)) from exc
        return ResolvedPreset(instance=instance, descriptor=descriptor, document=document)

    @staticmethod
    def instance_from_document(document: PatternDocument) -> PresetInstance | None:
        raw = document.header.metadata.get("preset_instance")
        if raw is None:
            return None
        try:
            return PresetInstance.from_dict(raw)
        except PresetDiagnosticError as exc:
            raise _error(
                "invalid_embedded_instance",
                f"metadata.preset_instance.{exc.path}",
                exc.detail,
            ) from exc

    def resolve_document(self, document: PatternDocument) -> ResolvedPreset | None:
        instance = self.instance_from_document(document)
        return self.resolve(instance) if instance is not None else None

    def materialize(self, document: PatternDocument) -> PatternDocument:
        """Return a local Pattern copy disconnected from upstream upgrades."""

        payload = document.to_dict()
        metadata = payload.get("metadata", {})
        metadata.pop("preset_instance", None)
        metadata.pop("preset_origin", None)
        metadata.pop("preset_internal_node_ids", None)
        metadata["materialized_from_preset"] = {
            "preset_id": self.instance_from_document(document).preset_id,
            "version": self.instance_from_document(document).version,
        }
        return PatternDocument.from_dict(payload)

    def compile(self, instance: PresetInstance, *, compiler: PatternCompiler | None = None, **kwargs: Any):
        resolved = self.resolve(instance)
        return (compiler or PatternCompiler()).compile(resolved.document, **kwargs)

    def expand_virtual(self, instance: PresetInstance) -> tuple[VirtualPresetNode, ...]:
        descriptor = self.registry.resolve(instance.preset_id, instance.version)
        namespace = uuid.UUID(instance.id)
        return tuple(
            VirtualPresetNode(
                virtual_id=str(uuid.uuid5(namespace, str(node["id"]))),
                instance_id=instance.id,
                internal_id=str(node["id"]),
                kind=str(node["kind"]),
                label=str(node["label"]),
                target=str(node["target"]) if node.get("target") is not None else None,
            )
            for node in descriptor.internal_nodes
        )


@dataclass(frozen=True)
class PresetMigration:
    preset_id: str
    from_version: str
    to_version: str
    parameter_renames: Mapping[str, str] = field(default_factory=dict)
    slot_renames: Mapping[str, str] = field(default_factory=dict)

    def validate(self, path: str = "migration") -> None:
        if not _ID_RE.fullmatch(_text(self.preset_id, f"{path}.preset_id")):
            raise _error("invalid_id", f"{path}.preset_id", "must be a namespaced lowercase id")
        _version(self.from_version, f"{path}.from_version")
        _version(self.to_version, f"{path}.to_version")
        if self.from_version == self.to_version:
            raise _error("migration_cycle", path, "source and target versions must differ")
        for field_name, mapping in (("parameter_renames", self.parameter_renames), ("slot_renames", self.slot_renames)):
            if not isinstance(mapping, Mapping):
                raise _error("type_mismatch", f"{path}.{field_name}", "must be an object")
            for source, target in mapping.items():
                _member_id(source, f"{path}.{field_name}.{source}")
                _member_id(target, f"{path}.{field_name}.{source}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "preset_id": self.preset_id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "parameter_renames": dict(self.parameter_renames),
            "slot_renames": dict(self.slot_renames),
        }

    @classmethod
    def from_dict(cls, value: Any, path: str = "migration") -> "PresetMigration":
        data = _object(value, path)
        _known(
            data,
            {"preset_id", "from_version", "to_version", "parameter_renames", "slot_renames"},
            path,
        )
        _required(data, ("preset_id", "from_version", "to_version"), path)
        migration = cls(
            preset_id=data["preset_id"],
            from_version=data["from_version"],
            to_version=data["to_version"],
            parameter_renames=dict(_object(data.get("parameter_renames", {}), f"{path}.parameter_renames")),
            slot_renames=dict(_object(data.get("slot_renames", {}), f"{path}.slot_renames")),
        )
        migration.validate(path)
        return migration


@dataclass(frozen=True)
class PresetMigrationPreview:
    original: PresetInstance
    instance: PresetInstance
    diff: tuple[Mapping[str, str], ...]


@dataclass(frozen=True)
class PresetDependencyLock:
    versions: Mapping[str, str]

    def validate(self) -> None:
        if not isinstance(self.versions, Mapping):
            raise _error("type_mismatch", "preset_lock.versions", "must be an object")
        for preset_id, version in self.versions.items():
            if not _ID_RE.fullmatch(_text(preset_id, f"preset_lock.versions.{preset_id}")):
                raise _error("invalid_id", f"preset_lock.versions.{preset_id}", "invalid preset id")
            _version(version, f"preset_lock.versions.{preset_id}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "type": "pystg.preset_lock",
            "schema_version": 1,
            "versions": dict(sorted(self.versions.items())),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PresetDependencyLock":
        data = _object(value, "preset_lock")
        _known(data, {"type", "schema_version", "versions"}, "preset_lock")
        _required(data, ("type", "schema_version", "versions"), "preset_lock")
        if data["type"] != "pystg.preset_lock":
            raise _error("wrong_resource_type", "preset_lock.type", "must be pystg.preset_lock")
        if data["schema_version"] != 1:
            raise _error("unsupported_schema", "preset_lock.schema_version", "must be 1")
        lock = cls(dict(_object(data["versions"], "preset_lock.versions")))
        lock.validate()
        return lock

    @classmethod
    def from_instances(cls, instances: Iterable[PresetInstance]) -> "PresetDependencyLock":
        versions: dict[str, str] = {}
        for instance in instances:
            existing = versions.get(instance.preset_id)
            if existing is not None and existing != instance.version:
                raise _error(
                    "lock_version_conflict",
                    f"preset_lock.versions.{instance.preset_id}",
                    f"instances require both {existing} and {instance.version}",
                )
            versions[instance.preset_id] = instance.version
        return cls(versions)

    def resolve(self, registry: "PresetRegistry", preset_id: str) -> PresetDescriptor:
        if preset_id not in self.versions:
            raise _error("missing_lock_entry", f"preset_lock.versions.{preset_id}", "preset is not locked")
        return registry.resolve(preset_id, self.versions[preset_id])


class PresetRegistry:
    def __init__(
        self,
        descriptors: Iterable[PresetDescriptor] = (),
        migrations: Iterable[PresetMigration] = (),
    ):
        self._descriptors: dict[tuple[str, str], PresetDescriptor] = {}
        for descriptor in descriptors:
            descriptor.validate()
            key = (descriptor.preset_id, descriptor.version)
            if key in self._descriptors:
                raise _error("duplicate_version", "presets", f"duplicate preset {key[0]}@{key[1]}")
            self._descriptors[key] = descriptor
        self._migrations: dict[tuple[str, str], PresetMigration] = {}
        for migration in migrations:
            migration.validate()
            key = (migration.preset_id, migration.from_version)
            if key in self._migrations:
                raise _error("ambiguous_migration", "migrations", f"multiple migrations start at {key[0]}@{key[1]}")
            self._migrations[key] = migration
        self._reject_cycles()

    def resolve(self, preset_id: str, version: str) -> PresetDescriptor:
        key = (preset_id, version)
        try:
            return self._descriptors[key]
        except KeyError as exc:
            raise _error(
                "missing_exact_version",
                "preset.version",
                f"preset {preset_id!r} exact version {version!r} is unavailable",
            ) from exc

    def versions(self, preset_id: str) -> tuple[str, ...]:
        """List every registered version of one preset, in registration order."""

        return tuple(
            version for registered, version in self._descriptors if registered == preset_id
        )

    def migration_targets(self, preset_id: str, from_version: str) -> tuple[str, ...]:
        """List versions reachable from ``from_version`` along exact migrations.

        Callers use this to offer only upgrades that actually have a migration
        path, so an author never picks a target that ``preview_migration``
        would then reject.
        """

        targets: list[str] = []
        current = str(from_version)
        seen = {current}
        while (preset_id, current) in self._migrations:
            migration = self._migrations[(preset_id, current)]
            if migration.to_version in seen:
                break
            targets.append(migration.to_version)
            seen.add(migration.to_version)
            current = migration.to_version
        return tuple(targets)

    def _reject_cycles(self) -> None:
        for start in self._migrations:
            seen: set[tuple[str, str]] = set()
            current = start
            while current in self._migrations:
                if current in seen:
                    raise _error("migration_cycle", "migrations", f"migration cycle for {current[0]}")
                seen.add(current)
                migration = self._migrations[current]
                current = (migration.preset_id, migration.to_version)

    def preview_migration(self, instance: PresetInstance, target_version: str) -> PresetMigrationPreview:
        instance.validate()
        self.resolve(instance.preset_id, target_version)
        current = instance.version
        parameters = _json_copy(instance.parameters, "instance.parameters")
        slots = _json_copy(instance.slot_overrides, "instance.slot_overrides")
        diff: list[Mapping[str, str]] = []
        visited: set[str] = set()
        while current != target_version:
            if current in visited:
                raise _error("migration_cycle", "migrations", "migration path contains a cycle")
            visited.add(current)
            migration = self._migrations.get((instance.preset_id, current))
            if migration is None:
                raise _error("missing_migration", f"migrations[{current}->{target_version}]", "no exact migration path")
            for source, target in migration.parameter_renames.items():
                migration_path = f"migrations[{migration.from_version}->{migration.to_version}].parameters.{source}"
                if source not in parameters:
                    raise _error("migration_source_missing", migration_path, "source override is missing")
                if target in parameters:
                    raise _error("migration_target_conflict", migration_path, "target override already exists")
                parameters[target] = parameters.pop(source)
                diff.append({"kind": "rename_parameter", "from": source, "to": target})
            for source, target in migration.slot_renames.items():
                migration_path = f"migrations[{migration.from_version}->{migration.to_version}].slots.{source}"
                if source not in slots:
                    raise _error("migration_source_missing", migration_path, "source override is missing")
                if target in slots:
                    raise _error("migration_target_conflict", migration_path, "target override already exists")
                slots[target] = slots.pop(source)
                diff.append({"kind": "rename_slot", "from": source, "to": target})
            current = migration.to_version
        migrated = PresetInstance(
            id=instance.id,
            preset_id=instance.preset_id,
            version=target_version,
            parameters=parameters,
            slot_overrides=slots,
        )
        # Validate all migrated overrides against the exact target descriptor.
        PresetResolver((self.resolve(instance.preset_id, target_version),)).resolve(migrated)
        diff.append({"kind": "change_version", "from": instance.version, "to": target_version})
        return PresetMigrationPreview(original=instance, instance=migrated, diff=tuple(diff))


@dataclass(frozen=True)
class PresetLibrary:
    library_id: str
    version: str
    presets: tuple[PresetDescriptor, ...]

    def validate(self) -> None:
        if not _ID_RE.fullmatch(_text(self.library_id, "library.id")):
            raise _error("invalid_id", "library.id", "must be a namespaced lowercase id")
        _version(self.version, "library.version")
        seen: set[tuple[str, str]] = set()
        for index, descriptor in enumerate(self.presets):
            if not isinstance(descriptor, PresetDescriptor):
                raise _error("type_mismatch", f"library.presets[{index}]", "must be a preset descriptor")
            descriptor.validate(f"library.presets[{index}]")
            key = (descriptor.preset_id, descriptor.version)
            if key in seen:
                raise _error("duplicate_version", f"library.presets[{index}]", "duplicate preset version")
            seen.add(key)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "type": "pystg.preset_library",
            "schema_version": 1,
            "id": self.library_id,
            "version": self.version,
            "presets": [preset.to_dict() for preset in self.presets],
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PresetLibrary":
        data = _object(value, "library")
        _known(data, {"type", "schema_version", "id", "version", "presets"}, "library")
        _required(data, ("type", "schema_version", "id", "version", "presets"), "library")
        if data["type"] != "pystg.preset_library":
            raise _error("wrong_resource_type", "library.type", "must be pystg.preset_library")
        if data["schema_version"] != 1:
            raise _error("unsupported_schema", "library.schema_version", "must be 1")
        raw_presets = data["presets"]
        if not isinstance(raw_presets, (list, tuple)):
            raise _error("type_mismatch", "library.presets", "must be an array")
        library = cls(
            library_id=data["id"],
            version=data["version"],
            presets=tuple(PresetDescriptor.from_dict(item) for item in raw_presets),
        )
        library.validate()
        return library

    @classmethod
    def load(cls, path: Path | str) -> "PresetLibrary":
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _error("library_load_failed", "library", str(exc)) from exc
        return cls.from_dict(payload)

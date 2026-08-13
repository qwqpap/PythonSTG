import json

import pytest

from src.pattern import (
    PatternDocument,
    PresetDescriptor,
    PresetDependencyLock,
    PresetDiagnosticError,
    PresetInstance,
    PresetParameter,
    PresetRegistry,
    PresetSlot,
)


def _descriptor(*, version: str = "1.0.0") -> PresetDescriptor:
    template = PatternDocument.new("Ring preset template").to_dict()
    return PresetDescriptor(
        preset_id="builtin.pattern.ring",
        version=version,
        display_name="圆形开花",
        template=template,
        parameters=(
            PresetParameter(
                id="count",
                value_type="int",
                default=24,
                target="shape.count",
                minimum=1,
                maximum=512,
            ),
            PresetParameter(
                id="speed",
                value_type="float",
                default=2.0,
                target="motion.speed",
                minimum=0.0,
                maximum=20.0,
            ),
        ),
        slots=(
            PresetSlot(
                id="termination_reaction",
                value_type="reaction",
                target="metadata.termination_reaction",
                default=None,
                nullable=True,
            ),
        ),
        inputs={"origin": "vec2"},
        outputs={"spawned": "bullet_batch"},
        events={"completed": "pattern.completed"},
        internal_nodes=(
            {"id": "shape", "kind": "emitter", "label": "圆形发射器"},
            {"id": "motion", "kind": "motion", "label": "匀速运动"},
        ),
    )


def test_descriptor_and_instance_are_strict_json_round_trips() -> None:
    descriptor = _descriptor()
    instance = PresetInstance.new(
        descriptor,
        parameters={"count": 32},
        slot_overrides={"termination_reaction": {"action": "death_bloom"}},
    )

    descriptor_payload = json.loads(json.dumps(descriptor.to_dict()))
    instance_payload = json.loads(json.dumps(instance.to_dict()))

    assert PresetDescriptor.from_dict(descriptor_payload) == descriptor
    assert PresetInstance.from_dict(instance_payload) == instance
    assert instance.preset_id == descriptor.preset_id
    assert instance.version == "1.0.0"


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda payload: payload.update({"future": True}), "preset"),
        (lambda payload: payload.pop("version"), "preset.version"),
        (
            lambda payload: payload["parameters"][0].update({"default": "many"}),
            "preset.parameters[0].default",
        ),
        (
            lambda payload: payload["internal_nodes"][0].update({"mystery": 1}),
            "preset.internal_nodes[0]",
        ),
    ],
)
def test_descriptor_rejects_unknown_missing_and_wrongly_typed_fields(
    mutate, path: str
) -> None:
    payload = _descriptor().to_dict()
    mutate(payload)

    with pytest.raises(PresetDiagnosticError) as caught:
        PresetDescriptor.from_dict(payload)

    assert caught.value.path == path


def test_registry_never_substitutes_a_nearby_version() -> None:
    registry = PresetRegistry((_descriptor(version="1.0.0"), _descriptor(version="2.0.0")))

    assert registry.resolve("builtin.pattern.ring", "1.0.0").version == "1.0.0"
    with pytest.raises(PresetDiagnosticError) as caught:
        registry.resolve("builtin.pattern.ring", "1.5.0")

    assert caught.value.code == "missing_exact_version"
    assert caught.value.path == "preset.version"


def test_dependency_lock_round_trips_and_resolves_only_its_exact_version() -> None:
    one = _descriptor(version="1.0.0")
    two = _descriptor(version="2.0.0")
    instance = PresetInstance.new(one)
    lock = PresetDependencyLock.from_instances((instance,))

    assert PresetDependencyLock.from_dict(lock.to_dict()) == lock
    assert lock.resolve(PresetRegistry((one, two)), one.preset_id) == one
    assert lock.versions == {one.preset_id: "1.0.0"}

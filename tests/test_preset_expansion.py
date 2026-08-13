from dataclasses import replace

import pytest

from src.pattern import (
    PatternCompiler,
    PatternDocument,
    PresetDescriptor,
    PresetDiagnosticError,
    PresetInstance,
    PresetParameter,
    PresetResolver,
)


def _descriptor() -> PresetDescriptor:
    template = PatternDocument.new("Preset template")
    template.shape = replace(template.shape, count=12)
    template.motion = replace(template.motion, speed=1.5)
    return PresetDescriptor(
        preset_id="builtin.pattern.test-ring",
        version="1.0.0",
        display_name="Test Ring",
        template=template.to_dict(),
        parameters=(
            PresetParameter("count", "int", 12, "shape.count", 1, 256),
            PresetParameter("speed", "float", 1.5, "motion.speed", 0.0, 20.0),
        ),
        internal_nodes=(
            {"id": "emitter-a", "kind": "emitter", "label": "Emitter A"},
            {"id": "motion", "kind": "motion", "label": "Motion"},
        ),
    )


def test_parameter_overrides_compile_through_the_formal_pattern_compiler() -> None:
    descriptor = _descriptor()
    instance = PresetInstance.new(descriptor, parameters={"count": 32, "speed": 3.25})
    resolver = PresetResolver((descriptor,))

    resolved = resolver.resolve(instance)
    program = resolver.compile(instance, compiler=PatternCompiler())

    assert resolved.document.shape.count == 32
    assert resolved.document.motion.speed == 3.25
    assert len(program.templates[0].angle_offsets) == 32
    assert program.templates[0].speeds == (3.25,) * 32


def test_override_validation_names_the_public_parameter() -> None:
    descriptor = _descriptor()
    instance = PresetInstance.new(descriptor, parameters={"count": "thirty-two"})

    with pytest.raises(PresetDiagnosticError) as caught:
        PresetResolver((descriptor,)).resolve(instance)

    assert caught.value.code == "parameter_type_mismatch"
    assert caught.value.path == "instance.parameters.count"


def test_virtual_node_identity_is_stable_without_copying_template_nodes() -> None:
    descriptor = _descriptor()
    instance = PresetInstance.new(descriptor)
    resolver = PresetResolver((descriptor,))
    before = instance.to_dict()

    first = resolver.expand_virtual(instance)
    second = resolver.expand_virtual(PresetInstance.from_dict(before))

    assert first == second
    assert [node.internal_id for node in first] == ["emitter-a", "motion"]
    assert len({node.virtual_id for node in first}) == 2
    assert instance.to_dict() == before
    assert "graph" not in instance.to_dict()


def test_runtime_trace_identity_can_locate_virtual_preset_nodes() -> None:
    descriptor = _descriptor()
    instance = PresetInstance.new(descriptor)
    resolver = PresetResolver((descriptor,))
    program = resolver.compile(instance, compiler=PatternCompiler())

    assert program.preset_id == descriptor.preset_id
    assert program.preset_version == descriptor.version
    assert program.preset_instance_id == instance.id
    assert program.preset_internal_node_ids == ("emitter-a", "motion")

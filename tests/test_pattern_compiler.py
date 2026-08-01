from dataclasses import FrozenInstanceError, replace
import json

import pytest

from src.core.project_context import ProjectContext
from src.devtools.pattern_lab import PatternSpec, bullet_parameters
from src.pattern import (
    BulletSpec,
    PatternCompileError,
    PatternCompiler,
    PatternDocument,
)


def _from_spec(**changes):
    spec = PatternSpec(**changes)
    return spec, PatternDocument.from_pattern_spec(spec)


@pytest.mark.parametrize("mode", ["ring", "arc", "spiral", "flower"])
def test_compiled_templates_match_pattern_lab_parameters(mode):
    spec, document = _from_spec(
        name=f"{mode.title()}Parity",
        pattern=mode,
        count=7,
        bursts=3,
        angle_span=135.0,
        start_angle=241.0,
        angle_offset_per_burst=11.25,
        speed=2.75,
    )
    program = PatternCompiler().compile(document)

    for burst_index in range(spec.bursts):
        template = program.templates[burst_index]
        actual = list(zip(
            (program.aim_angle + angle for angle in template.angle_offsets),
            template.speeds,
        ))
        expected = bullet_parameters(spec, burst_index)
        assert [angle for angle, _ in actual] == pytest.approx(
            [angle for angle, _ in expected], abs=1e-6
        )
        assert [speed for _, speed in actual] == pytest.approx(
            [speed for _, speed in expected], abs=1e-6
        )


def test_compiler_returns_cached_immutable_program():
    document = PatternDocument.new("Cached")
    compiler = PatternCompiler()

    first = compiler.compile(document)
    second = compiler.compile(PatternDocument.from_dict(document.to_dict()))

    assert first is second
    with pytest.raises(FrozenInstanceError):
        first.name = "mutated"


def test_line_shape_precomputes_offsets_and_motion_direction():
    document = PatternDocument.new()
    document.shape = replace(
        document.shape,
        kind="line",
        count=3,
        line_length=2.0,
        line_angle=90.0,
    )
    template = PatternCompiler().compile(document).templates[0]

    assert [value for point in template.position_offsets for value in point] == pytest.approx(
        [0.0, -1.0, 0.0, 0.0, 0.0, 1.0]
    )
    assert template.angle_offsets == (0.0, 0.0, 0.0)


def test_random_shape_is_seed_deterministic():
    first = PatternDocument.new()
    first.shape = replace(first.shape, kind="random", count=16, angle_span=80.0)
    first.schedule = replace(first.schedule, burst_count=2)
    first.modifiers = replace(first.modifiers, random_speed_variation=0.4)
    first.seed = 1234
    second = PatternDocument.from_dict(first.to_dict())
    second.header.id = PatternDocument.new().id
    third = PatternDocument.from_dict(first.to_dict())
    third.header.id = PatternDocument.new().id
    third.seed = 1235

    compiler = PatternCompiler()
    assert compiler.compile(first).templates == compiler.compile(second).templates
    assert compiler.compile(first).templates != compiler.compile(third).templates


def test_direct_sprite_resource_and_sprite_index_are_resolved(tmp_path):
    atlas = tmp_path / "assets" / "atlas.json"
    atlas.parent.mkdir(parents=True)
    atlas.write_text(json.dumps({"sprites": {"orb": {"rect": [0, 0, 8, 8]}}}), encoding="utf-8")
    document = PatternDocument.new()
    document.bullet = BulletSpec(resource="res://assets/atlas.json#orb")

    program = PatternCompiler().compile(
        document,
        project=ProjectContext(tmp_path),
        sprite_index_resolver=lambda sprite_id: 17 if sprite_id == "orb" else -1,
    )

    assert program.sprite_id == "orb"
    assert program.sprite_index == 17


def test_broken_resource_diagnostic_names_resource_and_property(tmp_path):
    document = PatternDocument.new()
    document.bullet = BulletSpec(resource="res://assets/missing.json#orb")

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document, project=ProjectContext(tmp_path))

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.resource_id == document.id
    assert diagnostic.path == "bullet.resource"
    assert diagnostic.code == "missing_resource"


def test_missing_sprite_fragment_is_actionable(tmp_path):
    atlas = tmp_path / "atlas.json"
    atlas.write_text(json.dumps({"sprites": {"other": {}}}), encoding="utf-8")
    document = PatternDocument.new()
    document.bullet = BulletSpec(resource="res://atlas.json#orb")

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document, project=ProjectContext(tmp_path))

    assert caught.value.diagnostics[0].code == "missing_sprite_subresource"
    assert "orb" in caught.value.diagnostics[0].message


def test_alias_dependency_content_participates_in_cache_key(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(json.dumps({"mapping": {"ball_m": {"red": "orb_a"}}}), encoding="utf-8")
    project = ProjectContext(tmp_path)
    compiler = PatternCompiler()
    document = PatternDocument.new()

    first = compiler.compile(document, project=project)
    aliases.write_text(json.dumps({"mapping": {"ball_m": {"red": "orb_b"}}}), encoding="utf-8")
    second = compiler.compile(document, project=project)

    assert first.sprite_id == "orb_a"
    assert second.sprite_id == "orb_b"
    assert first.content_hash != second.content_hash


def test_unknown_alias_reports_structured_bullet_path(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(json.dumps({"mapping": {"ball_m": {"blue": "orb"}}}), encoding="utf-8")
    document = PatternDocument.new()

    with pytest.raises(PatternCompileError) as caught:
        PatternCompiler().compile(document, project=ProjectContext(tmp_path))

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "unknown_bullet_alias"
    assert diagnostic.resource_id == document.id
    assert diagnostic.path == "bullet"
    assert "ball_m/red" in diagnostic.message

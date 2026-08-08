"""E5.1 frozen acceptance: reusable Curve resources, keyframes, interpolation.

These tests are the completion gate for the Curve-resource half of E5.1 and
must pass exactly as written. Do not edit, skip, or xfail them to make the
suite green; implement the contracts they assert instead.

Contract notes:
- Resource type name is ``pystg.curve``.
- ``CurveKeyframe(frame: int, value: float)`` with strictly increasing frames.
- ``CurveDocument.evaluate(frame)``: ``default`` below the first keyframe, the
  last keyframe's value beyond the last keyframe.
- ``interpolation`` is one of ``step`` / ``linear`` / ``cubic``.
- ``cubic`` is uniform Catmull-Rom with the first/last keyframe repeated as
  the outer control point: for the span [P1, P2],
  ``y(t) = 0.5 * (2*P1 + (-P0+P2)*t + (2*P0-5*P1+4*P2-P3)*t^2
  + (-P0+3*P1-3*P2+P3)*t^3)`` with t in [0, 1].
"""

import json
import math
from dataclasses import replace

import pytest

from src.authoring import ResourceStore, build_default_resource_type_registry
from src.core.project_context import ProjectContext
from src.pattern import CURVE_RESOURCE_TYPE, CurveDocument, CurveDocumentError
from src.pattern.curves import CURVE_INTERPOLATIONS, CurveKeyframe


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


def test_curve_resource_type_is_declared():
    assert CURVE_RESOURCE_TYPE == "pystg.curve"


def test_curve_interpolation_modes_are_exact():
    assert set(CURVE_INTERPOLATIONS) == {"step", "linear", "cubic"}


def test_step_interpolation_holds_last_frame_value():
    curve = CurveDocument.new(
        "Step",
        keyframes=(CurveKeyframe(0, 1.0), CurveKeyframe(5, 3.0)),
        interpolation="step",
    )

    assert curve.evaluate(0) == 1.0
    assert curve.evaluate(2.5) == 1.0
    assert curve.evaluate(4.9) == 1.0
    assert curve.evaluate(5) == 3.0
    assert curve.evaluate(100) == 3.0


def test_linear_interpolation_midpoints_and_edges():
    curve = CurveDocument.new(
        "Linear",
        keyframes=(CurveKeyframe(0, 0.0), CurveKeyframe(10, 2.0)),
        interpolation="linear",
        default=0.5,
    )

    assert curve.evaluate(0) == pytest.approx(0.0)
    assert curve.evaluate(5) == pytest.approx(1.0)
    assert curve.evaluate(10) == pytest.approx(2.0)
    assert curve.evaluate(-1) == pytest.approx(0.5)
    assert curve.evaluate(20) == pytest.approx(2.0)


def test_cubic_interpolation_matches_uniform_catmull_rom():
    curve = CurveDocument.new(
        "Cubic",
        keyframes=(CurveKeyframe(0, 0.0), CurveKeyframe(2, 4.0), CurveKeyframe(4, 0.0)),
        interpolation="cubic",
    )

    assert curve.evaluate(0) == pytest.approx(0.0)
    assert curve.evaluate(2) == pytest.approx(4.0)
    assert curve.evaluate(4) == pytest.approx(0.0)
    assert curve.evaluate(1.0) == pytest.approx(2.25)
    assert curve.evaluate(3.0) == pytest.approx(2.25)


def test_empty_keyframes_evaluate_to_default():
    curve = CurveDocument.new("Empty", default=-3.25)

    assert curve.evaluate(0) == -3.25
    assert curve.evaluate(100) == -3.25


def test_curve_document_round_trip_preserves_semantics():
    original = CurveDocument.new(
        "Curve",
        keyframes=(CurveKeyframe(0, 0.0), CurveKeyframe(3, 1.5), CurveKeyframe(9, -2.0)),
        interpolation="cubic",
        default=0.25,
    )

    reloaded = CurveDocument.from_dict(json.loads(json.dumps(original.to_dict())))

    assert reloaded.header.id == original.id
    assert reloaded.header.type == CURVE_RESOURCE_TYPE
    assert reloaded.interpolation == original.interpolation
    assert reloaded.default == original.default
    assert reloaded.keyframes == original.keyframes
    assert reloaded.evaluate(1.5) == pytest.approx(original.evaluate(1.5))


def test_curve_validates_duplicate_frames():
    with pytest.raises(CurveDocumentError):
        CurveDocument.new(
            "Bad",
            keyframes=(CurveKeyframe(0, 1.0), CurveKeyframe(0, 2.0)),
        ).validate()


def test_curve_validates_out_of_order_frames():
    with pytest.raises(CurveDocumentError):
        CurveDocument.new(
            "Bad",
            keyframes=(CurveKeyframe(3, 1.0), CurveKeyframe(1, 2.0)),
        ).validate()


def test_curve_validates_unknown_interpolation():
    with pytest.raises(CurveDocumentError):
        CurveDocument.new(
            "Bad",
            keyframes=(CurveKeyframe(0, 1.0),),
            interpolation="smooth",
        ).validate()


def test_curve_validates_non_finite_values():
    with pytest.raises(CurveDocumentError):
        CurveDocument.new(
            "Bad",
            keyframes=(CurveKeyframe(0, math.inf),),
        ).validate()


def test_curve_resources_load_through_the_typed_registry(tmp_path):
    project = _project(tmp_path)
    curve = CurveDocument.new(
        "Saved Curve",
        keyframes=(CurveKeyframe(0, 1.0), CurveKeyframe(8, 2.0)),
    )
    ResourceStore(project).save(curve, "game_content/curves/saved.pystg.json")

    loaded = ResourceStore(project).load("game_content/curves/saved.pystg.json")

    assert isinstance(loaded, CurveDocument)
    assert loaded.header.id == curve.id
    assert loaded.evaluate(4) == pytest.approx(1.5)

    registry = build_default_resource_type_registry()
    typed = registry.load(loaded.to_dict())
    assert isinstance(typed, CurveDocument)
    assert typed.header.id == curve.id


def test_curve_edits_change_dependent_pattern_content_hash(tmp_path):
    project = _project(tmp_path)
    curve = CurveDocument.new(
        "Hash",
        keyframes=(CurveKeyframe(0, 1.0), CurveKeyframe(10, 3.0)),
    )
    ResourceStore(project).save(curve, "game_content/curves/hash.pystg.json")

    from src.pattern import BindingSpec, PatternCompiler, PatternDocument

    document = PatternDocument.new("Bound")
    document.bindings = (
        BindingSpec(
            path="motion.speed",
            kind="curve",
            value="res://game_content/curves/hash.pystg.json",
        ),
    )
    compiler = PatternCompiler()
    first = compiler.compile(document, project=project)

    edited = replace(curve, keyframes=(CurveKeyframe(0, 9.0), CurveKeyframe(10, 3.0)))
    ResourceStore(project).save(edited, "game_content/curves/hash.pystg.json")
    second = compiler.compile(document, project=project)

    assert first.content_hash != second.content_hash

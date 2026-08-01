import json
from dataclasses import replace
from pathlib import Path

import jsonschema
import pytest

from src.authoring import ResourceStore, build_default_resource_type_registry
from src.core.project_context import ProjectContext
from src.devtools.pattern_lab import PatternSpec
from src.pattern import (
    PatternCompileError,
    PatternCompiler,
    PatternDocument,
    PatternDocumentError,
    PatternProgram,
    ScheduleSpec,
)


def test_pattern_document_round_trip_preserves_unicode_display_name():
    document = PatternDocument.new("星符『星轨回廊』", symbol_name="StarCorridor")

    loaded = PatternDocument.from_dict(document.to_dict())

    assert loaded.to_dict() == document.to_dict()
    assert loaded.name == "星符『星轨回廊』"
    assert loaded.symbol_name == "StarCorridor"


def test_pattern_document_rejects_unknown_fields_and_path_is_actionable():
    payload = PatternDocument.new().to_dict()
    payload["shape"]["mystery"] = 1

    with pytest.raises(PatternDocumentError) as caught:
        PatternDocument.from_dict(payload)

    assert caught.value.path == "shape"
    assert "mystery" in caught.value.detail


def test_pattern_document_matches_published_draft_2020_schema():
    schema_path = Path("docs/schemas/pystg-pattern-v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(PatternDocument.new().to_dict(), schema)


def test_pattern_spec_import_preserves_prototype_schedule_and_identity():
    spec = PatternSpec(
        name="LegacySpiral",
        pattern="spiral",
        count=9,
        bursts=4,
        interval=7,
        angle_offset_per_burst=12.5,
    )

    document = PatternDocument.from_pattern_spec(spec, display_name="旧版螺旋")

    assert document.name == "旧版螺旋"
    assert document.symbol_name == "LegacySpiral"
    assert document.schedule == ScheduleSpec(
        delay_frames=0,
        interval_frames=7,
        burst_count=4,
        loop_count=None,
    )
    assert document.header.metadata["imported_from"] == "PatternSpec"


def test_resource_store_loads_patterns_as_typed_documents(tmp_path):
    project = ProjectContext(tmp_path)
    store = ResourceStore(project)
    document = PatternDocument.new("Typed")

    path = store.save(document, "patterns/typed.pystg.json")
    loaded = store.load(path)

    assert isinstance(loaded, PatternDocument)
    assert loaded.to_dict() == document.to_dict()


def test_default_resource_registry_exposes_formal_pattern_compiler():
    registry = build_default_resource_type_registry()
    contribution = registry["pystg.pattern"]

    program = contribution.compiler(PatternDocument.new("Registry Compile"))

    assert isinstance(program, PatternProgram)


def test_compile_template_budget_rejects_pathological_documents():
    document = PatternDocument.new()
    document.shape = replace(document.shape, count=4096)
    document.schedule = replace(document.schedule, burst_count=4096)

    with pytest.raises(PatternCompileError, match="precompute"):
        PatternCompiler().compile(document)

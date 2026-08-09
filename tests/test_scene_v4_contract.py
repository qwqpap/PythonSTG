"""N2.2 canonical Scene v4 migration contracts."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from src.editor import DocumentError, SceneDocument
from src.authoring import GenericResourceDocument, build_default_resource_type_registry


ROOT = Path(__file__).resolve().parents[1]


def test_v3_fixture_can_be_explicitly_upgraded_to_canonical_v4_without_mutation():
    source = json.loads(
        (ROOT / "docs/schemas/fixtures/scene-v3.pystg.json").read_text(encoding="utf-8")
    )
    before = deepcopy(source)
    document = SceneDocument.from_dict(source, canonical=True)
    payload = document.to_canonical_dict()

    assert source == before
    assert payload["schema_version"] == 4
    assert payload["variables"] == []
    assert payload["output_mappings"] == []
    assert payload["state_graph"]["states"][0]["variables"] == []
    assert payload["state_graph"]["states"][0]["output_mappings"] == []

    schema = json.loads(
        (ROOT / "docs/schemas/pystg-scene-v4.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert SceneDocument.from_dict(payload, canonical=True).to_canonical_dict() == payload


def test_canonical_loader_rejects_unknown_fields_and_future_versions_without_mutating_input():
    payload = json.loads(
        (ROOT / "docs/schemas/fixtures/scene-v4.pystg.json").read_text(encoding="utf-8")
    )
    unknown = deepcopy(payload)
    unknown["experimental"] = True
    with pytest.raises(DocumentError, match="unknown fields"):
        SceneDocument.from_dict(unknown, canonical=True)
    assert unknown["experimental"] is True

    future = deepcopy(payload)
    future["schema_version"] = 5
    with pytest.raises(DocumentError, match="newer"):
        SceneDocument.from_dict(future, canonical=True)
    assert future["schema_version"] == 5


def test_legacy_wire_compatibility_is_opt_in_to_canonical_output():
    source = json.loads(
        (ROOT / "docs/schemas/fixtures/scene-v3.pystg.json").read_text(encoding="utf-8")
    )
    legacy = SceneDocument.from_dict(source)
    assert legacy.to_dict()["schema_version"] == 3
    assert legacy.to_canonical_dict()["schema_version"] == 4


def test_header_only_v3_scene_stays_generic_through_the_resource_registry():
    source = {
        "schema_version": 3,
        "type": "pystg.scene",
        "id": "b88e1d39-dc9d-4fc9-8fb7-9023b17dba30",
        "name": "Header only",
        "metadata": {},
        "state_graph": {
            "id": "e0f36a27-e0c4-5a99-b044-ad01a3ebfceb",
            "name": "StageFlow",
            "initial_state_id": "d71b4d73-9ecd-5707-a48b-2cbc0c9ca03e",
            "states": [],
        },
    }

    document = build_default_resource_type_registry().load(source)

    assert isinstance(document, GenericResourceDocument)
    assert document.schema_version == 4
    assert "root" not in document.to_dict()

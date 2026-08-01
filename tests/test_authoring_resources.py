import json
from pathlib import Path

import pytest

from src.authoring import (
    AUTHORING_RESOURCE_TYPES,
    GenericResourceDocument,
    MigrationError,
    MigrationRegistry,
    ResourceDocumentError,
    ResourceHeader,
    ResourceReference,
    ResourceStore,
    ResourceTypeRegistry,
    ResourceTypeSpec,
    build_default_resource_type_registry,
)
from src.core.project_context import ProjectContext


def test_all_initial_resource_types_round_trip_atomically(tmp_path):
    store = ResourceStore(ProjectContext(tmp_path))
    for index, resource_type in enumerate(AUTHORING_RESOURCE_TYPES):
        document = GenericResourceDocument(
            header=ResourceHeader(
                type=resource_type,
                name=f"中文资源 {index}",
                symbol_name=f"resource_{index}",
                metadata={"author": "测试"},
            ),
            body={"objects": [{"id": str(__import__("uuid").uuid4()), "value": index}]},
        )
        path = store.save(document, f"assets/resources/{index}.pystg.json")
        loaded = store.load(path)

        assert loaded.to_dict() == document.to_dict()
        assert loaded.name == f"中文资源 {index}"
        assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_resource_header_separates_unicode_name_and_portable_symbol():
    header = ResourceHeader(type="pystg.pattern", name="星符「星轨回廊」")
    header.validate()
    assert header.symbol_name is None

    with pytest.raises(ResourceDocumentError, match="symbol_name"):
        ResourceHeader(
            type="pystg.pattern",
            name="符卡",
            symbol_name="中文不是符号",
        ).validate()


def test_generic_resource_rejects_duplicate_ids_and_future_schema():
    header = ResourceHeader(type="pystg.ui", name="HUD")
    document = GenericResourceDocument(
        header=header,
        body={"node": {"id": header.id}},
    )
    with pytest.raises(ResourceDocumentError, match="Duplicate"):
        document.validate()

    registry = build_default_resource_type_registry()
    with pytest.raises(MigrationError, match="newer"):
        registry.load(
            {
                "schema_version": 99,
                "type": "pystg.ui",
                "id": header.id,
                "name": "Future",
            }
        )


def test_migration_registry_requires_an_explicit_step_by_step_path():
    migrations = MigrationRegistry()
    migrations.register_type("demo.resource", 2)
    migrations.register(
        "demo.resource",
        0,
        lambda data: {
            **data,
            "schema_version": 1,
            "type": "demo.resource",
            "first": True,
        },
    )
    migrations.register(
        "demo.resource",
        1,
        lambda data: {**data, "schema_version": 2, "second": True},
    )

    migrated = migrations.migrate({"name": "Legacy"}, expected_type="demo.resource")
    assert migrated["schema_version"] == 2
    assert migrated["first"] and migrated["second"]

    incomplete = MigrationRegistry()
    incomplete.register_type("demo.resource", 2)
    incomplete.register(
        "demo.resource",
        0,
        lambda data: {**data, "schema_version": 1, "type": "demo.resource"},
    )
    with pytest.raises(MigrationError, match="No migration path"):
        incomplete.migrate({}, expected_type="demo.resource")


def test_resource_type_registry_carries_editor_compiler_and_preview_contributions():
    migrations = MigrationRegistry()
    registry = ResourceTypeRegistry(migrations)
    compiled = object()
    preview = object()
    editor = object()
    validated = []
    spec = ResourceTypeSpec(
        type_name="demo.resource",
        display_name="Demo",
        asset_kind="demo",
        loader=lambda data: dict(data),
        validator=lambda document: validated.append(document["name"]),
        editor_factory=lambda: editor,
        compiler=lambda document: compiled,
        preview_handler=lambda document: preview,
    )

    assert registry.register(spec) is spec
    loaded = registry.load(
        {
            "schema_version": 1,
            "type": "demo.resource",
            "id": str(__import__("uuid").uuid4()),
            "name": "Example",
        }
    )
    assert loaded["name"] == "Example"
    assert validated == ["Example"]
    assert registry["demo.resource"].editor_factory() is editor
    assert registry["demo.resource"].compiler(loaded) is compiled
    assert registry["demo.resource"].preview_handler(loaded) is preview
    with pytest.raises(ValueError, match="Duplicate"):
        registry.register(spec)
    with pytest.raises(KeyError, match="Unknown"):
        registry["missing.resource"]


def test_resource_reference_is_canonical_and_project_constrained(tmp_path):
    project = ProjectContext(tmp_path)
    source = tmp_path / "assets" / "atlas.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")

    reference = ResourceReference.parse("res://assets/atlas.json#orb")
    assert reference.uri == "res://assets/atlas.json#orb"
    assert reference.resolve(project, must_exist=True) == source.resolve()
    assert ResourceReference.parse(
        "assets/atlas.json#orb",
        allow_legacy_project_path=True,
    ) == reference

    with pytest.raises(ResourceDocumentError, match="project-relative"):
        ResourceReference.parse("res://")

    with pytest.raises(ResourceDocumentError, match="does not exist"):
        ResourceReference.parse("res://assets/missing.png").resolve(
            project,
            must_exist=True,
        )
    with pytest.raises(ResourceDocumentError, match="may not contain"):
        ResourceReference.parse("res://../outside.json")
    with pytest.raises(ResourceDocumentError, match="must start"):
        ResourceReference.parse(str(tmp_path.parent / "outside.json"))


def test_resource_store_reports_invalid_typed_json(tmp_path):
    path = tmp_path / "assets" / "bad.pystg.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"type": "pystg.pattern"}), encoding="utf-8")

    with pytest.raises((MigrationError, ResourceDocumentError)):
        ResourceStore(ProjectContext(tmp_path)).load(path)

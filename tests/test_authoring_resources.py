import json

import pytest

from src.authoring import (
    AUTHORING_RESOURCE_TYPES,
    BACKGROUND_RESOURCE_TYPE,
    UI_RESOURCE_TYPE,
    GenericResourceDocument,
    ResourceDocumentError,
    ResourceHeader,
    ResourceReference,
    ResourceStore,
    ResourceTypeRegistry,
    ResourceTypeSpec,
    build_default_resource_type_registry,
)
from src.core.project_context import ProjectContext


def test_retained_resource_types_round_trip_atomically(tmp_path):
    assert AUTHORING_RESOURCE_TYPES == (UI_RESOURCE_TYPE, BACKGROUND_RESOURCE_TYPE)
    store = ResourceStore(ProjectContext(tmp_path))

    for index, resource_type in enumerate(AUTHORING_RESOURCE_TYPES):
        document = GenericResourceDocument(
            header=ResourceHeader(
                type=resource_type,
                name=f"中文资源 {index}",
                symbol_name=f"resource_{index}",
                metadata={"author": "测试"},
            ),
            body={"note": f"retained-{index}"},
        )
        path = store.save(document, f"assets/resources/{index}.pystg.json")
        loaded = store.load(path)

        assert loaded.to_dict() == document.to_dict()
        assert loaded.name == f"中文资源 {index}"
        assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_resource_header_separates_unicode_name_and_portable_symbol():
    header = ResourceHeader(type=UI_RESOURCE_TYPE, name="中文 HUD")
    header.validate()
    assert header.symbol_name is None

    with pytest.raises(ResourceDocumentError, match="symbol_name"):
        ResourceHeader(
            type=UI_RESOURCE_TYPE,
            name="HUD",
            symbol_name="中文不是符号",
        ).validate()


def test_generic_resource_rejects_duplicate_ids_and_future_schema():
    header = ResourceHeader(type=UI_RESOURCE_TYPE, name="HUD")
    document = GenericResourceDocument(
        header=header,
        body={"node": {"id": header.id}},
    )
    with pytest.raises(ResourceDocumentError, match="Duplicate"):
        document.validate()

    registry = build_default_resource_type_registry()
    with pytest.raises(ResourceDocumentError, match="newer"):
        registry.load(
            {
                "schema_version": 99,
                "type": UI_RESOURCE_TYPE,
                "id": header.id,
                "name": "Future",
            }
        )


def test_resource_type_registry_is_loader_only():
    registry = ResourceTypeRegistry()
    validated = []
    spec = ResourceTypeSpec(
        type_name="demo.resource",
        display_name="Demo",
        asset_kind="demo",
        loader=lambda data: dict(data),
        validator=lambda document: validated.append(document["name"]),
    )

    assert registry.register(spec) is spec
    loaded = registry.load(
        {
            "schema_version": 1,
            "type": "demo.resource",
            "id": "not-used-by-loader",
            "name": "Example",
        }
    )
    assert loaded["name"] == "Example"
    assert validated == ["Example"]
    assert not hasattr(spec, "editor_factory")
    assert not hasattr(spec, "compiler")
    assert not hasattr(spec, "preview_handler")
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


def test_resource_store_rejects_removed_resource_types(tmp_path):
    path = tmp_path / "assets" / "bad.pystg.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"schema_version": 1, "type": "pystg.pattern"}),
        encoding="utf-8",
    )

    with pytest.raises(ResourceDocumentError, match="Unknown resource type"):
        ResourceStore(ProjectContext(tmp_path)).load(path)

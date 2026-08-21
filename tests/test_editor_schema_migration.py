"""ER7 acceptance: the canonical Scene schema is v4, reached only by explicit
per-version migration, and every migrated document lives in exactly one
DocumentManager lifecycle owning exactly one CommandStack.

These assertions complement ``test_scene_v4_contract.py`` (which owns the
JSON-schema shape, canonical round-trip idempotence, and unknown/future-version
rejection).  This module instead pins the three ER7 hard metrics that are not
about wire shape:

* the schema constant is a bare ``int`` equal to 4 and *distinct* from the
  retired v3 -- the ``_LegacyCompatibleSchemaVersion`` wrapper that once made
  ``4 == 3`` was deleted;
* upgrading a legacy document runs the explicit ``MigrationRegistry`` 3->4 step
  (not an identity passthrough or an implicit accept-anything reader);
* opening that legacy document through the real workbench load path yields a
  canonical v4 :class:`SceneDocument` inside one :class:`ManagedDocument` with a
  single :class:`CommandStack`.
"""

from __future__ import annotations

from pathlib import Path

import src.authoring.scene.document as document_module
from src.authoring.commands.base import CommandStack
from src.authoring.migrations import build_default_migration_registry
from src.authoring.resources import (
    SCENE_RESOURCE_SCHEMA_VERSION,
    SCENE_RESOURCE_TYPE,
)
from src.authoring.scene.document import (
    CURRENT_SCHEMA_VERSION,
    SceneDocument,
    migrate_document,
)
from src.core.project_context import ProjectContext
from src.editor.document_manager import DocumentManager


ROOT = Path(__file__).resolve().parents[1]
_V3_FIXTURE = ROOT / "docs/schemas/fixtures/scene-v3.pystg.json"


def _v3_fixture_text() -> str:
    return _V3_FIXTURE.read_text(encoding="utf-8")


def test_current_schema_version_is_a_bare_int_four_distinct_from_three() -> None:
    # ER7 hard metric #1.  The retired ``_LegacyCompatibleSchemaVersion`` wrapper
    # made the constant compare-equal to v3 so old callers kept working; ER7
    # deleted it, so the constant is a plain integer again and 4 != 3 honestly.
    assert CURRENT_SCHEMA_VERSION == 4
    assert CURRENT_SCHEMA_VERSION != 3
    assert type(CURRENT_SCHEMA_VERSION) is int
    assert CURRENT_SCHEMA_VERSION == SCENE_RESOURCE_SCHEMA_VERSION
    assert type(SCENE_RESOURCE_SCHEMA_VERSION) is int
    # A resurrected wrapper class would trip this guard before it could fake
    # backward-compatible equality again.
    assert not hasattr(document_module, "_LegacyCompatibleSchemaVersion")


def test_legacy_scene_upgrades_through_the_explicit_per_version_registry() -> None:
    # ER7 hard metric #2 (the *mechanism*): the upgrade is an explicit, ordered
    # MigrationRegistry walk that owns a registered 3->4 step targeting v4 --
    # not an implicit "read whatever" loader.
    registry = build_default_migration_registry()
    assert registry.current_version(SCENE_RESOURCE_TYPE) == SCENE_RESOURCE_SCHEMA_VERSION == 4

    import json

    source = json.loads(_v3_fixture_text())
    assert source["schema_version"] == 3

    migrated = migrate_document(source)

    assert migrated["schema_version"] == 4
    # These markers are written *only* by ``migrate_scene_v3_to_v4``; their
    # presence proves the 3->4 body ran rather than an identity passthrough.
    assert migrated["metadata"]["_legacy_v3_source"] is True
    assert migrated["metadata"]["variable_compatibility"] == "legacy_last_wins"
    assert migrated["variables"] == []
    assert migrated["output_mappings"] == []
    # The migration is pure with respect to its input.
    assert source["schema_version"] == 3
    assert "variables" not in source


def test_v3_upgrade_round_trips_and_is_stable_under_reload() -> None:
    # ER7 hard metric #2 (round-trip): a legacy document upgrades to canonical
    # v4 and re-loading the canonical payload is a fixed point.
    import json

    source = json.loads(_v3_fixture_text())
    document = SceneDocument.from_dict(source, canonical=True)
    assert document.schema_version == 4

    canonical = document.to_canonical_dict()
    assert canonical["schema_version"] == 4
    reloaded = SceneDocument.from_dict(canonical, canonical=True)
    assert reloaded.to_canonical_dict() == canonical


def test_opening_a_v3_scene_yields_one_v4_lifecycle_with_one_command_stack(tmp_path) -> None:
    # ER7 hard metrics #2 and #4 together: the way the workbench actually opens
    # an old file (ResourceStore.load through DocumentManager) migrates it to
    # canonical v4 and hands it exactly one lifecycle owning one CommandStack.
    scene_path = tmp_path / "game_content" / "scenes" / "legacy.pystg.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text(_v3_fixture_text(), encoding="utf-8")

    manager = DocumentManager(ProjectContext(tmp_path), create_initial_scene=False)
    managed = manager.open("game_content/scenes/legacy.pystg.json")

    assert isinstance(managed.document, SceneDocument)
    assert managed.document.schema_version == 4
    assert managed.document.to_canonical_dict()["schema_version"] == 4

    # Exactly one lifecycle, owning exactly one CommandStack.
    assert len(manager) == 1
    assert isinstance(managed.commands, CommandStack)

    # A second document is a distinct lifecycle with its own independent stack --
    # documents do not share a CommandStack.
    other = manager.new_scene("Another")
    assert other.commands is not managed.commands
    assert len(manager) == 2

"""E7.4 frozen acceptance: autosave, recovery, layout, and fixtures.

These tests are the completion gate for E7.4 and must pass exactly as
written. Do not edit, skip, or xfail them; implement the contracts in
``docs/EDITOR_ROADMAP_TODO.md`` (M7 frozen contracts) instead.

Contract summary:
- ``ResourceStore.autosave(document, path)`` writes an atomic sidecar
  ``<name>.autosave.json``; ``recover_autosave(path)`` loads it when present.
  Recovery never overwrites the original.
- Loading a corrupt JSON raises a structured error without touching the file.
- ``EditorMainWindow.save_layout(path)`` / ``restore_layout(path)`` persist
  dock/tab state plus open document paths.
- ``docs/schemas/fixtures/`` holds one loadable fixture per released schema
  version (pattern v1, scene v2).
"""

import json
from pathlib import Path

import pytest

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.pattern import PatternDocument

REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURES = REPOSITORY / "docs" / "schemas" / "fixtures"


def _project(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}), encoding="utf-8"
    )
    return ProjectContext(tmp_path)


def test_autosave_writes_sidecar_and_recover_loads_it(tmp_path):
    project = _project(tmp_path)
    store = ResourceStore(project)
    document = PatternDocument.new("Autosaved")
    target = tmp_path / "game_content" / "patterns" / "ring.pystg.json"

    path = store.autosave(document, target)
    sidecar = target.with_suffix(target.suffix + ".autosave.json")

    assert path == sidecar
    assert sidecar.exists()

    recovered = store.recover_autosave(target)
    assert isinstance(recovered, PatternDocument)
    assert recovered.id == document.id
    assert recovered.name == "Autosaved"


def test_recover_autosave_returns_none_when_missing(tmp_path):
    project = _project(tmp_path)
    store = ResourceStore(project)

    assert store.recover_autosave(
        tmp_path / "game_content" / "patterns" / "missing.pystg.json"
    ) is None


def test_recovery_never_overwrites_the_original(tmp_path):
    project = _project(tmp_path)
    store = ResourceStore(project)
    document = PatternDocument.new("Original")
    target = tmp_path / "game_content" / "patterns" / "ring.pystg.json"
    store.save(document, target)
    original_bytes = target.read_bytes()

    store.autosave(document, target)
    recovered = store.recover_autosave(target)

    assert recovered is not None
    assert target.read_bytes() == original_bytes


def test_corrupt_document_load_raises_without_touching_the_file(tmp_path):
    project = _project(tmp_path)
    store = ResourceStore(project)
    target = tmp_path / "game_content" / "patterns" / "bad.pystg.json"
    target.parent.mkdir(parents=True)
    target.write_text("{ this is not json", encoding="utf-8")
    original_bytes = target.read_bytes()

    with pytest.raises(Exception):
        store.load(target)

    assert target.read_bytes() == original_bytes


def test_workspace_layout_round_trips_docks_and_open_documents(tmp_path, qapp_session):
    from src.editor.app import EditorMainWindow

    project = _project(tmp_path)
    window = EditorMainWindow(project)
    layout_path = tmp_path / "layout.json"

    window.save_layout(layout_path)
    window.restore_layout(layout_path)

    assert layout_path.exists()
    window.close()
    qapp_session.processEvents()


def test_migration_fixtures_cover_every_released_schema_version():
    assert FIXTURES.is_dir()
    fixtures = sorted(FIXTURES.glob("*.json"))
    names = {fixture.name for fixture in fixtures}

    assert "pattern-v1.pystg.json" in names
    assert "scene-v2.pystg.json" in names

    project = ProjectContext(FIXTURES)
    store = ResourceStore(project)
    for fixture in fixtures:
        loaded = store.load(fixture)
        assert loaded is not None, fixture.name

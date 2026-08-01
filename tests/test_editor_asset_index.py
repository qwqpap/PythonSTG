import json
from pathlib import Path

from src.core.project_context import ProjectContext
from src.editor.asset_index import (
    AssetIndex,
    classify_file,
    load_subresource_preview,
)
from src.pattern import PatternDocument


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_asset_index_classifies_files_and_indexes_atlas_subresources(tmp_path):
    assets = tmp_path / "assets"
    atlas = assets / "images" / "atlas.png"
    atlas.parent.mkdir(parents=True)
    atlas.write_bytes(b"png")
    config = atlas.with_suffix(".json")
    _write_json(
        config,
        {
            "__image_filename": "assets/images/atlas.png",
            "sprites": {
                "orb": {"rect": [4, 8, 16, 20]},
                "invalid": {"rect": [0, 0, 0, 1]},
            },
            "animations": {
                "animations": {
                    "pulse": {
                        "frames": ["orb"],
                        "fps": 12,
                    },
                    "strip": {
                        "frames": [{"rect": [0, 0, 8, 8]}],
                    }
                }
            },
        },
    )
    script = tmp_path / "game_content" / "stages" / "demo.py"
    script.parent.mkdir(parents=True)
    script.write_text("pass\n", encoding="utf-8")

    index = AssetIndex(ProjectContext(tmp_path))
    records = index.scan()

    assert index.errors == ()
    assert index.find("res://assets/images/atlas.json#orb").rect == (4, 8, 16, 20)
    assert index.find("res://assets/images/atlas.json#orb").preview_path == atlas.resolve()
    animation = index.find("res://assets/images/atlas.json#pulse")
    assert animation.kind == "animation"
    assert animation.rect == (4, 8, 16, 20)
    assert animation.metadata["frames"] == 1
    assert animation.metadata["fps"] == 12
    strip_animation = index.find("res://assets/images/atlas.json#strip")
    assert strip_animation.preview_path == atlas.resolve()
    assert strip_animation.rect == (0, 0, 8, 8)
    assert any(
        record.kind == "script"
        and record.project_path == "game_content/stages/demo.py"
        for record in records
    )


def test_asset_index_resolves_texture_maps_and_reports_invalid_json(tmp_path):
    player_dir = tmp_path / "assets" / "players"
    player_dir.mkdir(parents=True)
    texture = player_dir / "player.png"
    texture.write_bytes(b"png")
    config = player_dir / "player.json"
    _write_json(
        config,
        {
            "textures": {"main": "player.png"},
            "sprites": {
                "idle": {
                    "source": "main",
                    "region": [1, 2, 3, 4],
                }
            },
        },
    )
    bad = tmp_path / "assets" / "broken.json"
    bad.write_text("{", encoding="utf-8")

    project = ProjectContext(tmp_path)
    index = AssetIndex(project)
    index.scan()
    record = index.find("res://assets/players/player.json#idle")

    assert record.preview_path == texture.resolve()
    assert record.rect == (1, 2, 3, 4)
    assert len(index.errors) == 1
    assert index.errors[0].startswith("assets/broken.json:")
    assert load_subresource_preview(
        project,
        record.resource_value,
    ) == (texture.resolve(), (1, 2, 3, 4))


def test_classify_file_recognizes_typed_authoring_resources(tmp_path):
    for filename, resource_type, expected in (
        ("level.pystg.json", "pystg.scene", "scene"),
        ("ring.pystg.json", "pystg.pattern", "pattern"),
        ("hud.pystg.json", "pystg.ui", "ui"),
        ("forest.pystg.json", "pystg.background", "background"),
    ):
        path = tmp_path / filename
        _write_json(path, {"type": resource_type})
        assert classify_file(path) == expected
    assert classify_file(Path("unknown.pystg.json")) == "resource"
    assert classify_file(Path("music.ogg")) == "audio"
    assert classify_file(Path("effect.frag")) == "shader"
    assert classify_file(Path("font.ttf")) == "font"
    assert classify_file(Path("logic.py")) == "script"


def test_asset_index_reports_invalid_typed_resource_without_aborting(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _write_json(
        assets / "valid.pystg.json",
        PatternDocument.new("Valid").to_dict(),
    )
    _write_json(
        assets / "invalid.pystg.json",
        {"schema_version": 1, "type": "pystg.pattern", "name": "Missing ID"},
    )

    index = AssetIndex(ProjectContext(tmp_path))
    records = index.scan()

    assert any(record.kind == "pattern" for record in records)
    assert len(index.errors) == 1
    assert index.errors[0].startswith("assets/invalid.pystg.json:")

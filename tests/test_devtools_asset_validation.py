from pathlib import Path

from PIL import Image

from src.devtools.asset_validation import AssetValidator


def _png(path: Path, size=(32, 32)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (255, 255, 255, 255)).save(path)


def test_asset_validator_accepts_minimal_consistent_project(tmp_path):
    assets = tmp_path / "assets"
    images = assets / "images" / "bullet"
    images.mkdir(parents=True)
    _png(images / "bullet.png")
    (images / "bullet.json").write_text(
        """
        {
          "__image_filename": "bullet.png",
          "sprites": {
            "ball_mid1": {"rect": [0, 0, 16, 16], "center": [8, 8]}
          }
        }
        """,
        encoding="utf-8",
    )
    (assets / "bullet_aliases.json").write_text(
        '{"mapping": {"ball_m": {"red": "ball_mid1"}}}',
        encoding="utf-8",
    )
    (assets / "configs").mkdir()
    (assets / "configs" / "enemy_presets.json").write_text(
        '{"presets": {}}',
        encoding="utf-8",
    )
    laser_dir = assets / "images" / "laser"
    _png(laser_dir / "laser1.png", (16, 16))
    (laser_dir / "laser_config.json").write_text(
        '{"laser_textures": {"laser1": {"file": "laser1.png", "row_height": 16, "colors": 1}}}',
        encoding="utf-8",
    )

    report = AssetValidator(tmp_path).validate()

    assert report.error_count == 0
    assert report.sprites_checked == 1


def test_asset_validator_reports_out_of_bounds_sprite_rect(tmp_path):
    assets = tmp_path / "assets"
    images = assets / "images" / "bullet"
    images.mkdir(parents=True)
    _png(images / "bullet.png", (16, 16))
    (images / "bullet.json").write_text(
        """
        {
          "__image_filename": "bullet.png",
          "sprites": {
            "bad": {"rect": [8, 8, 16, 16]}
          }
        }
        """,
        encoding="utf-8",
    )
    (assets / "bullet_aliases.json").write_text('{"mapping": {}}', encoding="utf-8")
    (assets / "configs").mkdir()
    (assets / "configs" / "enemy_presets.json").write_text('{"presets": {}}', encoding="utf-8")
    laser_dir = assets / "images" / "laser"
    _png(laser_dir / "laser1.png", (16, 16))
    (laser_dir / "laser_config.json").write_text(
        '{"laser_textures": {"laser1": {"file": "laser1.png", "row_height": 16, "colors": 1}}}',
        encoding="utf-8",
    )

    report = AssetValidator(tmp_path).validate()

    assert report.error_count == 1
    assert "outside texture bounds" in report.issues[0].message

import json
from pathlib import Path

import pytest

from src.game.background_render.data_driven_background import DataDrivenBackground


STAGE_BACKGROUND_NAMES = [
    "luastg_hongmoguanB",
    "luastg_ball",
    "bamboo",
    "luastg_gzz_stage04bg",
    "luastg_stage3bg",
    "luastg_temple2",
]


class _DummyCamera:
    def __init__(self):
        self.z_near = 0.01
        self.z_far = 10.0
        self.fog_start = 0.0
        self.fog_end = 10.0
        self.fog_color = (0.0, 0.0, 0.0, 1.0)
        self.fog_enabled = False


class _DummyRenderer:
    def __init__(self):
        self.camera = _DummyCamera()

    def load_texture(self, path: str) -> bool:
        return True

    def set_camera(self, eye, at, up, fovy):
        self.camera.eye = eye
        self.camera.at = at
        self.camera.up = up
        self.camera.fovy = fovy

    def set_fog(self, color, start, end, enabled):
        self.camera.fog_color = color
        self.camera.fog_start = start
        self.camera.fog_end = end
        self.camera.fog_enabled = enabled


def test_stage3_background_fog_matches_editor_alpha_style():
    config_path = Path("assets/images/background/luastg_stage3bg.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))

    bg = DataDrivenBackground(_DummyRenderer())
    assert bg.load_from_dict(config, str(config_path.parent), announce=False)

    bg.render()
    quads = bg.get_render_quads()

    assert quads
    assert quads[0]["alpha"] == pytest.approx(0.2)
    assert quads[10]["alpha"] == pytest.approx(0.2)


def test_fog_disabled_keeps_original_alpha():
    config = {
        "name": "test_bg",
        "textures": {
            "base": {"path": "dummy.png"},
        },
        "camera": {
            "eye": [0.0, 0.0, 1.0],
            "at": [0.0, 0.0, 0.0],
            "up": [0.0, 1.0, 0.0],
            "fovy": 0.8,
            "z_near": 0.1,
            "z_far": 10.0,
        },
        "fog": {
            "enabled": False,
            "color": [0, 0, 0, 255],
            "start": 0.0,
            "end": 10.0,
        },
        "scroll": {"base_speed": 0.0, "direction": [0, 1]},
        "layers": [
            {
                "name": "base",
                "texture": "base",
                "z_order": 0,
                "z_depth": 0.0,
                "blend_mode": "normal",
                "alpha": 0.65,
                "scroll_multiplier": 1.0,
                "tile": {"x_range": [0, 1], "y_range": [0, 1], "size": 1.0},
                "variants": [],
                "enabled": True,
            }
        ],
    }

    bg = DataDrivenBackground(_DummyRenderer())
    assert bg.load_from_dict(config, "", announce=False)

    bg.render()
    quads = bg.get_render_quads()

    assert len(quads) == 1
    assert quads[0]["alpha"] == pytest.approx(0.65)


@pytest.mark.parametrize("background_name", STAGE_BACKGROUND_NAMES)
def test_stage_background_scroll_advances_in_editor_visual_direction(background_name):
    config_path = Path(f"assets/images/background/{background_name}.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))

    bg = DataDrivenBackground(_DummyRenderer())
    assert bg.load_from_dict(config, str(config_path.parent), announce=False)

    bg.update(1.0)

    assert bg.data.scroll_offset == pytest.approx(
        -config["scroll"]["base_speed"]
    )

"""E6.2 frozen acceptance: unified BackgroundDocument and legacy import.

These tests lock the single background document contract: the typed envelope
wraps exactly the existing shipped fields (name/description/textures/camera/
fog/scroll/layers), legacy JSON imports without semantic drift, and the
runtime renderer consumes the document with field-identical quads. Do not
edit, skip, or xfail them.
"""

import json
from pathlib import Path

import pytest

from src.authoring import ResourceStore, build_default_resource_type_registry
from src.core.project_context import ProjectContext
from src.game.background_render.background_renderer import BackgroundRenderer
from src.game.background_render.data_driven_background import DataDrivenBackground
from src.game.background_render.document import (
    BackgroundDocument,
    BackgroundDocumentError,
)

REPOSITORY = Path(__file__).resolve().parents[1]
BACKGROUND_DIR = REPOSITORY / "assets" / "images" / "background"

PARITY_NAMES = [
    "lake",
    "bamboo",
    "luastg_hongmoguanB",
    "luastg_ball",
    "luastg_gzz_stage04bg",
    "luastg_stage3bg",
    "luastg_temple2",
    "luastg_magic_forest",
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


def _legacy(name: str) -> dict:
    path = BACKGROUND_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Envelope and schema
# --------------------------------------------------------------------------


def test_background_document_has_typed_envelope():
    payload = _legacy("lake")
    document = BackgroundDocument.from_legacy(payload)

    assert document.type == "pystg.background"
    assert document.schema_version >= 1
    assert document.id
    assert document.name == "lake"

    reloaded = BackgroundDocument.from_dict(
        json.loads(json.dumps(document.to_dict()))
    )
    assert reloaded.id == document.id
    assert reloaded.name == "lake"


def test_background_document_wraps_all_legacy_fields_without_renaming():
    payload = _legacy("lake")
    document = BackgroundDocument.from_legacy(payload)

    body = document.to_dict()
    assert body["name"] == payload["name"]
    assert body["description"] == payload["description"]
    assert body["textures"] == payload["textures"]
    assert body["camera"] == payload["camera"]
    assert body["fog"] == payload["fog"]
    assert body["scroll"] == payload["scroll"]
    assert body["layers"] == payload["layers"]


def test_background_document_rejects_unknown_top_level_fields():
    payload = _legacy("lake")
    payload["camera2"] = {}

    with pytest.raises(BackgroundDocumentError):
        BackgroundDocument.from_legacy(payload)


def test_background_document_validates_layer_and_camera_types():
    payload = _legacy("lake")
    payload["layers"] = "not-an-array"

    with pytest.raises(BackgroundDocumentError):
        BackgroundDocument.from_legacy(payload)

    bad_camera = _legacy("lake")
    bad_camera["camera"] = {"eye": "oops"}

    with pytest.raises(BackgroundDocumentError):
        BackgroundDocument.from_legacy(bad_camera)


def test_background_document_loads_through_the_typed_registry(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    project = ProjectContext(tmp_path)
    document = BackgroundDocument.from_legacy(_legacy("lake"))
    ResourceStore(project).save(
        document, "game_content/backgrounds/lake.pystg.json"
    )

    loaded = ResourceStore(project).load("game_content/backgrounds/lake.pystg.json")
    assert isinstance(loaded, BackgroundDocument)
    assert loaded.id == document.id

    registry = build_default_resource_type_registry()
    typed = registry.load(document.to_dict())
    assert isinstance(typed, BackgroundDocument)


# --------------------------------------------------------------------------
# Runtime parity
# --------------------------------------------------------------------------


def _quads_from(payload: dict) -> list:
    background = DataDrivenBackground(_DummyRenderer())
    assert background.load_from_dict(payload, str(BACKGROUND_DIR), announce=False)
    background.render()
    return background.get_render_quads()


@pytest.mark.parametrize("name", PARITY_NAMES)
def test_legacy_import_keeps_runtime_quads_identical(name):
    legacy = _legacy(name)
    document = BackgroundDocument.from_legacy(legacy)

    legacy_quads = _quads_from(legacy)
    document_quads = _quads_from(document.to_dict())

    assert len(document_quads) == len(legacy_quads)
    for document_quad, legacy_quad in zip(document_quads, legacy_quads):
        assert document_quad["v0"] == pytest.approx(legacy_quad["v0"])
        assert document_quad["v3"] == pytest.approx(legacy_quad["v3"])
        assert document_quad["alpha"] == pytest.approx(legacy_quad["alpha"])


def test_all_shipped_backgrounds_import_without_error():
    failures = []
    for path in sorted(BACKGROUND_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            BackgroundDocument.from_legacy(payload)
        except Exception as exc:  # pragma: no cover - failure report
            failures.append(f"{path.name}: {exc}")
    assert not failures, "shipped backgrounds failed to import: " + "; ".join(failures)


def test_document_round_trip_preserves_scroll_and_layer_values():
    legacy = _legacy("bamboo")
    document = BackgroundDocument.from_legacy(legacy)
    reloaded = BackgroundDocument.from_dict(
        json.loads(json.dumps(document.to_dict()))
    )

    assert reloaded.body["scroll"] == legacy["scroll"]
    assert reloaded.body["layers"] == legacy["layers"]

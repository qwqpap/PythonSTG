import ast
from pathlib import Path

from src.core.project_context import ProjectContext
from src.resource.service import ResourceService


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_and_editor_resource_models_agree_on_sprite_ids():
    project = ProjectContext(REPO_ROOT)
    resources = ResourceService(project)
    config = Path("images/bullet/bullet1.json")

    runtime_atlas = resources.textures.load_atlas_config(str(config))
    editor_sheet = resources.load_editor_config(project.assets / config)

    assert runtime_atlas is not None
    assert editor_sheet is not None
    assert set(runtime_atlas.sprites) == set(editor_sheet.sprites)


def test_editor_resource_model_loads_all_player_configs():
    project = ProjectContext(REPO_ROOT)
    resources = ResourceService(project)

    for config_path in sorted((project.assets / "players").glob("*/config.json")):
        sheet = resources.load_editor_config(config_path)
        assert sheet is not None, config_path
        assert sheet.sprites, config_path
        assert sheet.animations, config_path


def test_content_does_not_import_optimized_bullet_implementation():
    forbidden = {
        "src.game.bullet.optimized_pool",
        "src.game.bullet.tags",
    }
    violations = []
    for path in (REPO_ROOT / "game_content").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in forbidden:
                violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden:
                        violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert not violations, "content imported bullet implementation modules: " + ", ".join(violations)

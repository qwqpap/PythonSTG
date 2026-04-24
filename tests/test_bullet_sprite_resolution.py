import ast
from pathlib import Path

from src.game.stage.context import StageContext
from src.resource.texture_asset import TextureAssetManager


REPO_ROOT = Path(__file__).resolve().parents[1]


def _iter_literal_bullet_calls():
    for base in (REPO_ROOT / "game_content", REPO_ROOT / "src"):
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                func_name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if func_name not in {
                    "fire",
                    "fire_circle",
                    "fire_arc",
                    "create_bullet",
                    "create_polar_bullet",
                }:
                    continue

                keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
                bullet_type = keywords.get("bullet_type")
                color = keywords.get("color")
                if not isinstance(bullet_type, ast.Constant) or not isinstance(bullet_type.value, str):
                    continue

                yield (
                    path.relative_to(REPO_ROOT),
                    node.lineno,
                    bullet_type.value,
                    color.value if isinstance(color, ast.Constant) and isinstance(color.value, str) else "red",
                )


def test_all_literal_bullet_combinations_resolve_to_loaded_sprites():
    asset_manager = TextureAssetManager(str(REPO_ROOT / "assets"))
    assert asset_manager.load_sprite_config_folder(str(REPO_ROOT / "assets" / "images"))

    ctx = object.__new__(StageContext)
    StageContext._aliases_loaded = False
    StageContext.load_bullet_aliases(str(REPO_ROOT / "assets" / "bullet_aliases.json"))

    sprite_ids = set(asset_manager.get_all_sprite_ids())
    unresolved = []

    for rel_path, lineno, bullet_type, color in _iter_literal_bullet_calls():
        sprite_id = ctx._resolve_sprite_id(bullet_type, color)
        if sprite_id not in sprite_ids:
            unresolved.append(f"{rel_path}:{lineno} -> {bullet_type}/{color} => {sprite_id}")

    assert unresolved == []

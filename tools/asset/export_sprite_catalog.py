"""
Generate a single preview image containing every loaded sprite with its name.
Uses the existing TextureAssetManager so the result stays consistent with the engine.
"""
import argparse
import math
import os
import sys
from pathlib import Path
import pygame


# Ensure project packages are importable when running as a standalone tool
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.resource.texture_asset import init_texture_asset_manager, get_texture_asset_manager


def setup_headless_pygame():
    """Initialize pygame in headless mode to avoid opening a window."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.font.init()


def load_all_sprites(asset_root: Path) -> list:
    """Load all sprite surfaces via the asset manager."""
    manager = init_texture_asset_manager(str(asset_root))
    images_dir = asset_root / "images"
    if not manager.load_sprite_config_folder(str(images_dir)):
        raise SystemExit(f"Failed to load sprite configs from {images_dir}")

    entries = []
    font = pygame.font.Font(None, 14)

    for name in sorted(manager.list_all_sprites()):
        surface = manager.get_sprite_surface(name)
        if surface is None:
            continue
        label = font.render(name, True, (220, 220, 220))
        entries.append((name, surface, label))

    return entries


def build_catalog_surface(entries: list, columns: int | None, padding: int = 8) -> pygame.Surface:
    """Compose a grid surface containing all sprites and labels."""
    if not entries:
        raise ValueError("No sprite surfaces were loaded")

    max_sprite_w = max(s.get_width() for _, s, _ in entries)
    max_sprite_h = max(s.get_height() for _, s, _ in entries)
    max_label_w = max(l.get_width() for _, _, l in entries)
    label_h = max(l.get_height() for _, _, l in entries)

    cell_w = max(max_sprite_w, max_label_w) + padding * 2
    cell_h = max_sprite_h + label_h + padding * 3

    total = len(entries)
    if columns is None or columns <= 0:
        columns = max(1, int(math.sqrt(total)))
    columns = max(1, columns)
    rows = math.ceil(total / columns)

    sheet_w = cell_w * columns
    sheet_h = cell_h * rows
    sheet = pygame.Surface((sheet_w, sheet_h), pygame.SRCALPHA)
    sheet.fill((28, 28, 40, 255))

    for idx, (_, sprite, label) in enumerate(entries):
        row = idx // columns
        col = idx % columns
        base_x = col * cell_w
        base_y = row * cell_h

        sprite_x = base_x + (cell_w - sprite.get_width()) // 2
        sprite_y = base_y + padding
        label_x = base_x + (cell_w - label.get_width()) // 2
        label_y = base_y + padding * 2 + max_sprite_h

        sheet.blit(sprite, (sprite_x, sprite_y))
        sheet.blit(label, (label_x, label_y))

    return sheet


def save_surface(surface: pygame.Surface, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(output_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export all sprites into a single preview image.")
    parser.add_argument("--asset-root", default="assets", help="asset root folder (default: assets)")
    parser.add_argument("--output", default="sprite_catalog.png", help="output image path")
    parser.add_argument("--columns", type=int, default=None, help="columns in the grid (auto if omitted)")
    parser.add_argument("--padding", type=int, default=8, help="padding inside each cell")
    return parser.parse_args()


def main():
    setup_headless_pygame()
    args = parse_args()

    asset_root = Path(args.asset_root).resolve()
    entries = load_all_sprites(asset_root)
    surface = build_catalog_surface(entries, columns=args.columns, padding=args.padding)
    output_path = Path(args.output).resolve()
    save_surface(surface, output_path)

    manager = get_texture_asset_manager()
    stats = manager.get_stats()
    print(f"Saved {len(entries)} sprites to {output_path}")
    print(f"Atlases: {stats['atlases']}, Sprites: {stats['sprites']}, Animations: {stats['animations']}")


if __name__ == "__main__":
    main()

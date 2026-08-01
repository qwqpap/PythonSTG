"""Asset validation used by local tooling and CI.

The validator intentionally stays independent from the OpenGL runtime.  It reads
JSON configs, checks referenced files, validates sprite rectangles against image
dimensions, and verifies common cross-resource references such as bullet aliases
and enemy preset sprites.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal

from PIL import Image


Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    path: Path
    message: str
    subject: str = ""

    def to_dict(self, root: Path) -> dict[str, str]:
        try:
            rel_path = self.path.relative_to(root)
        except ValueError:
            rel_path = self.path
        return {
            "severity": self.severity,
            "path": rel_path.as_posix(),
            "subject": self.subject,
            "message": self.message,
        }


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    json_files_checked: int = 0
    sprite_configs_checked: int = 0
    sprites_checked: int = 0
    image_files_checked: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def ok(self) -> bool:
        return self.error_count == 0

    def add(self, severity: Severity, path: Path, message: str, subject: str = "") -> None:
        self.issues.append(ValidationIssue(severity, path, message, subject))

    def to_dict(self, root: Path) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.error_count,
            "warnings": self.warning_count,
            "json_files_checked": self.json_files_checked,
            "sprite_configs_checked": self.sprite_configs_checked,
            "sprites_checked": self.sprites_checked,
            "image_files_checked": self.image_files_checked,
            "issues": [issue.to_dict(root) for issue in self.issues],
        }


class AssetValidator:
    def __init__(self, project_root: Path | str):
        self.root = Path(project_root).resolve()
        self.assets_dir = self.root / "assets"
        self.report = ValidationReport()
        self._json_cache: dict[Path, Any] = {}
        self._image_size_cache: dict[Path, tuple[int, int] | None] = {}
        self._sprite_ids: set[str] = set()
        self._bullet_aliases: dict[str, dict[str, str]] = {}

    def validate(self) -> ValidationReport:
        self.report = ValidationReport()
        self._json_cache.clear()
        self._image_size_cache.clear()
        self._sprite_ids.clear()
        self._bullet_aliases.clear()

        self._validate_json_syntax()
        self._validate_sprite_configs()
        self._validate_bullet_aliases()
        self._validate_enemy_presets()
        self._validate_player_configs()
        self._validate_background_configs()
        self._validate_laser_config()
        return self.report

    def _iter_json_files(self) -> Iterator[Path]:
        roots = [self.assets_dir, self.root / "game_content"]
        for base in roots:
            if base.exists():
                yield from sorted(base.rglob("*.json"))

    def _load_json(self, path: Path) -> Any | None:
        if path in self._json_cache:
            return self._json_cache[path]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.report.add("error", path, f"invalid JSON: {exc}")
            return None
        self._json_cache[path] = data
        return data

    def _validate_json_syntax(self) -> None:
        for path in self._iter_json_files():
            self.report.json_files_checked += 1
            self._load_json(path)

    def _validate_sprite_configs(self) -> None:
        image_root = self.assets_dir / "images"
        if not image_root.exists():
            self.report.add("error", image_root, "assets/images does not exist")
            return

        seen: dict[str, Path] = {}
        for path in sorted(image_root.rglob("*.json")):
            data = self._load_json(path)
            if not isinstance(data, dict) or not self._looks_like_sprite_config(data):
                continue

            self.report.sprite_configs_checked += 1
            image_path = self._resolve_texture_path(path, data)
            if image_path is None:
                self.report.add("error", path, "sprite config has sprites but no texture or __image_filename")
                continue

            size = self._image_size(image_path)
            if size is None:
                self.report.add("error", path, f"referenced texture is missing or unreadable: {image_path}")
                continue

            sprites = self._sprite_entries(data)
            for sprite_id, sprite_data in sprites:
                self.report.sprites_checked += 1
                if sprite_id in seen:
                    self.report.add(
                        "warning",
                        path,
                        f"duplicate sprite id also defined in {seen[sprite_id].relative_to(self.root)}",
                        subject=sprite_id,
                    )
                else:
                    seen[sprite_id] = path
                self._sprite_ids.add(sprite_id)
                self._validate_rect(path, sprite_id, sprite_data.get("rect"), size)

            for anim_id, anim_data in self._animation_entries(data):
                self._sprite_ids.add(anim_id)
                self._validate_animation(path, anim_id, anim_data, size)

    @staticmethod
    def _looks_like_sprite_config(data: dict[str, Any]) -> bool:
        if "sprites" in data:
            return isinstance(data.get("sprites"), dict)
        if "__image_filename" not in data:
            return False
        return any(isinstance(v, dict) and "rect" in v for k, v in data.items() if not k.startswith("__"))

    @staticmethod
    def _sprite_entries(data: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
        raw = data.get("sprites")
        if isinstance(raw, dict):
            source = raw.items()
        else:
            source = ((k, v) for k, v in data.items() if not k.startswith("__"))
        for sprite_id, sprite_data in source:
            if isinstance(sprite_data, dict) and "rect" in sprite_data:
                yield str(sprite_id), sprite_data

    @staticmethod
    def _animation_entries(data: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
        raw = data.get("animations", {})
        if not isinstance(raw, dict):
            return []
        return ((str(anim_id), anim_data) for anim_id, anim_data in raw.items() if isinstance(anim_data, dict))

    def _resolve_texture_path(self, config_path: Path, data: dict[str, Any]) -> Path | None:
        texture_name = data.get("texture") or data.get("__image_filename")
        if not isinstance(texture_name, str) or not texture_name:
            return None

        config_dir = config_path.parent
        candidates = [
            config_dir / texture_name,
            self.assets_dir / texture_name,
            Path(texture_name),
            config_dir / Path(texture_name).name,
            config_dir / "bullet" / Path(texture_name).name,
            config_dir.parent / Path(texture_name).name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return (config_dir / texture_name).resolve()

    def _image_size(self, path: Path) -> tuple[int, int] | None:
        path = path.resolve()
        if path in self._image_size_cache:
            return self._image_size_cache[path]
        self.report.image_files_checked += 1
        try:
            with Image.open(path) as img:
                size = img.size
        except Exception:
            size = None
        self._image_size_cache[path] = size
        return size

    def _validate_rect(self, path: Path, subject: str, rect: Any, image_size: tuple[int, int]) -> None:
        if not self._is_rect(rect):
            self.report.add("error", path, "rect must be [x, y, width, height] with positive size", subject)
            return
        x, y, w, h = [float(v) for v in rect]
        tex_w, tex_h = image_size
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > tex_w or y + h > tex_h:
            self.report.add(
                "error",
                path,
                f"rect {rect} is outside texture bounds {tex_w}x{tex_h}",
                subject,
            )

    @staticmethod
    def _is_rect(rect: Any) -> bool:
        if not isinstance(rect, list | tuple) or len(rect) != 4:
            return False
        return all(isinstance(v, int | float) for v in rect)

    def _validate_animation(
        self,
        path: Path,
        anim_id: str,
        anim_data: dict[str, Any],
        image_size: tuple[int, int],
    ) -> None:
        frames = anim_data.get("frames")
        if isinstance(frames, list):
            for idx, frame in enumerate(frames):
                if isinstance(frame, str):
                    if frame not in self._sprite_ids:
                        self.report.add("error", path, f"animation frame references missing sprite '{frame}'", anim_id)
                    continue
                if isinstance(frame, dict):
                    self._validate_rect(path, f"{anim_id}[{idx}]", frame.get("rect"), image_size)
            return

        strip = anim_data.get("strip")
        if isinstance(strip, dict):
            rect = [
                strip.get("x", 0),
                strip.get("y", 0),
                strip.get("width", 32),
                strip.get("height", 32),
            ]
            self._validate_rect(path, f"{anim_id}.strip", rect, image_size)

    def _validate_bullet_aliases(self) -> None:
        path = self.assets_dir / "bullet_aliases.json"
        data = self._load_json(path)
        if not isinstance(data, dict):
            return
        mapping = data.get("mapping", {})
        if not isinstance(mapping, dict):
            self.report.add("error", path, "mapping must be an object")
            return
        self._bullet_aliases = {
            str(kind): {str(color): str(sprite) for color, sprite in colors.items()}
            for kind, colors in mapping.items()
            if isinstance(colors, dict)
        }
        for kind, colors in self._bullet_aliases.items():
            for color, sprite_id in colors.items():
                if sprite_id not in self._sprite_ids:
                    self.report.add("error", path, f"alias points to missing sprite '{sprite_id}'", f"{kind}/{color}")

    def _validate_enemy_presets(self) -> None:
        path = self.assets_dir / "configs" / "enemy_presets.json"
        data = self._load_json(path)
        if not isinstance(data, dict):
            return
        presets = data.get("presets", {})
        if isinstance(presets, dict):
            for preset_id, preset in presets.items():
                if not isinstance(preset, dict):
                    continue
                sprite_id = preset.get("sprite")
                if (
                    isinstance(sprite_id, str)
                    and sprite_id not in self._sprite_ids
                    and f"{sprite_id}_idle" not in self._sprite_ids
                ):
                    self.report.add("error", path, f"enemy preset sprite is missing: {sprite_id}", str(preset_id))
                defaults = preset.get("defaults", {})
                if isinstance(defaults, dict):
                    bullet_type = str(defaults.get("bullet_type", "ball_m"))
                    color = str(defaults.get("bullet_color", "red"))
                    if self._resolve_bullet_alias(bullet_type, color) is None:
                        self.report.add(
                            "warning",
                            path,
                            "default bullet type/color falls back at runtime; add an explicit bullet alias",
                            f"{preset_id}:{bullet_type}/{color}",
                        )

    def _resolve_bullet_alias(self, bullet_type: str, color: str) -> str | None:
        normalized_type = {"bullet_m": "ball_m", "bullet_s": "ball_s", "bullet_l": "ball_l"}.get(
            bullet_type.strip().lower(),
            bullet_type.strip().lower(),
        )
        normalized_color = {"grey": "gray", "pink": "purple"}.get(color.strip().lower(), color.strip().lower())
        colors = self._bullet_aliases.get(normalized_type)
        if not colors:
            return None
        for candidate in (normalized_color, color.strip().lower(), "red", "darkred", "purple", "white"):
            sprite_id = colors.get(candidate)
            if sprite_id:
                return sprite_id
        return next(iter(colors.values()), None)

    def _validate_player_configs(self) -> None:
        players_dir = self.assets_dir / "players"
        if not players_dir.exists():
            return
        for path in sorted(players_dir.glob("*/config.json")):
            data = self._load_json(path)
            if not isinstance(data, dict):
                continue
            textures = data.get("textures", {})
            if not textures and isinstance(data.get("texture"), str):
                textures = {"player": data["texture"]}
            if not isinstance(textures, dict):
                self.report.add("error", path, "textures must be an object")
                continue
            texture_sizes: dict[str, tuple[int, int]] = {}
            for texture_key, texture_name in textures.items():
                if not isinstance(texture_name, str) or not texture_name:
                    self.report.add("error", path, "texture entry must be a non-empty string", str(texture_key))
                    continue
                image_path = (path.parent / texture_name).resolve()
                size = self._image_size(image_path)
                if size is None:
                    self.report.add("error", path, f"player texture is missing or unreadable: {texture_name}", str(texture_key))
                else:
                    texture_sizes[str(texture_key)] = size
            sprites = data.get("sprites", {})
            if isinstance(sprites, dict):
                for sprite_id, sprite_data in sprites.items():
                    if not isinstance(sprite_data, dict):
                        continue
                    source = str(sprite_data.get("source", "player"))
                    size = texture_sizes.get(source)
                    if size is None:
                        self.report.add("error", path, f"sprite references unknown texture source '{source}'", str(sprite_id))
                        continue
                    self._validate_rect(path, str(sprite_id), sprite_data.get("rect"), size)

    def _validate_background_configs(self) -> None:
        bg_dir = self.assets_dir / "images" / "background"
        if not bg_dir.exists():
            return
        for path in sorted(bg_dir.glob("*.json")):
            data = self._load_json(path)
            if not isinstance(data, dict) or "textures" not in data:
                continue
            textures = data.get("textures", {})
            if not isinstance(textures, dict):
                self.report.add("error", path, "textures must be an object")
                continue
            texture_keys = set(textures.keys())
            for key, entry in textures.items():
                if not isinstance(entry, dict):
                    self.report.add("error", path, "texture entry must be an object", str(key))
                    continue
                texture_rel = entry.get("path")
                if not isinstance(texture_rel, str) or not texture_rel:
                    self.report.add("error", path, "texture path must be a non-empty string", str(key))
                    continue
                if self._image_size((path.parent / texture_rel).resolve()) is None:
                    self.report.add("error", path, f"background texture is missing or unreadable: {texture_rel}", str(key))
            layers = data.get("layers", [])
            if isinstance(layers, list):
                for idx, layer in enumerate(layers):
                    if isinstance(layer, dict):
                        texture_key = layer.get("texture")
                        if isinstance(texture_key, str) and texture_key not in texture_keys:
                            self.report.add("error", path, f"layer references unknown texture '{texture_key}'", f"layers[{idx}]")

    def _validate_laser_config(self) -> None:
        path = self.assets_dir / "images" / "laser" / "laser_config.json"
        data = self._load_json(path)
        if not isinstance(data, dict):
            return
        for laser_id, cfg in self._iter_laser_entries(data):
            file_name = cfg.get("file")
            if not isinstance(file_name, str) or not file_name:
                self.report.add("error", path, "laser texture entry needs file", laser_id)
                continue
            image_size = self._image_size((path.parent / file_name).resolve())
            if image_size is None:
                self.report.add("error", path, f"laser texture is missing or unreadable: {file_name}", laser_id)
                continue
            row_height = int(cfg.get("row_height", 0) or 0)
            colors = int(cfg.get("colors", 0) or 0)
            if row_height <= 0 or colors <= 0:
                self.report.add("error", path, "row_height and colors must be positive", laser_id)
            elif image_size[1] < row_height * colors:
                self.report.add("error", path, "texture height is too small for configured color rows", laser_id)

    @staticmethod
    def _iter_laser_entries(data: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
        laser_textures = data.get("laser_textures", {})
        if isinstance(laser_textures, dict):
            for laser_id, cfg in laser_textures.items():
                if isinstance(cfg, dict):
                    yield str(laser_id), cfg
        bent = data.get("bent_laser")
        if isinstance(bent, dict):
            yield "bent_laser", bent


def format_text_report(report: ValidationReport, root: Path) -> str:
    lines = [
        "Asset validation report",
        f"  JSON files: {report.json_files_checked}",
        f"  Sprite configs: {report.sprite_configs_checked}",
        f"  Sprites: {report.sprites_checked}",
        f"  Images touched: {report.image_files_checked}",
        f"  Errors: {report.error_count}",
        f"  Warnings: {report.warning_count}",
    ]
    for issue in report.issues:
        try:
            rel_path = issue.path.relative_to(root)
        except ValueError:
            rel_path = issue.path
        subject = f" [{issue.subject}]" if issue.subject else ""
        lines.append(f"{issue.severity.upper()}: {rel_path.as_posix()}{subject}: {issue.message}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate PySTG asset references and config consistency.")
    parser.add_argument("--root", default=".", help="Project root. Defaults to current directory.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    report = AssetValidator(root).validate()
    if args.format == "json":
        print(json.dumps(report.to_dict(root), ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report, root))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

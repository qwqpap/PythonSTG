"""Project resource indexing, including atlas subresources."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from src.authoring.registry import build_default_resource_type_registry
from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.core.project_context import ProjectContext, ProjectContextError


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
AUDIO_EXTENSIONS = {".wav", ".ogg", ".mp3", ".flac"}
FONT_EXTENSIONS = {".ttf", ".otf"}
SHADER_EXTENSIONS = {".glsl", ".vert", ".frag"}
TEXT_EXTENSIONS = {".md", ".txt", ".toml", ".ini", ".cfg", ".lua"}
INDEXED_EXTENSIONS = (
    IMAGE_EXTENSIONS
    | AUDIO_EXTENSIONS
    | FONT_EXTENSIONS
    | SHADER_EXTENSIONS
    | TEXT_EXTENSIONS
    | {".json", ".py"}
)
RESOURCE_TYPES = build_default_resource_type_registry()


@dataclass(frozen=True)
class AssetRecord:
    uri: str
    path: Path
    project_path: str
    kind: str
    name: str
    subresource: str | None = None
    preview_path: Path | None = None
    rect: tuple[int, int, int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def resource_value(self) -> str:
        return self.uri

    @property
    def folder(self) -> str:
        return Path(self.project_path).parent.as_posix()


def classify_file(path: Path, payload: dict[str, Any] | None = None) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in FONT_EXTENSIONS:
        return "font"
    if suffix in SHADER_EXTENSIONS:
        return "shader"
    if suffix == ".json":
        if path.name.endswith(".pystg.json"):
            if payload is None and path.is_file():
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8-sig"))
                    payload = loaded if isinstance(loaded, dict) else None
                except (OSError, json.JSONDecodeError):
                    payload = None
            if payload is not None:
                try:
                    return RESOURCE_TYPES.asset_kind_for_payload(payload)
                except Exception:
                    pass
            return "resource"
        return "json"
    if suffix == ".py":
        return "script"
    return "text"


def _safe_rect(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        rect = tuple(int(value[index]) for index in range(4))
    except (TypeError, ValueError):
        return None
    if rect[2] <= 0 or rect[3] <= 0:
        return None
    return rect


def _resolve_texture_path(
    config_path: Path,
    config: dict[str, Any],
    sprite: dict[str, Any] | None = None,
) -> Path | None:
    sprite = sprite or {}
    textures = config.get("textures")
    if not isinstance(textures, dict):
        textures = {}
    source = str(sprite.get("source", "")).strip()
    candidate = (
        textures.get(source)
        or config.get("__image_filename")
        or config.get("texture")
        or textures.get("player")
    )
    if not candidate:
        image_path = sprite.get("image_path")
        if isinstance(image_path, str) and image_path:
            candidate = Path(image_path.replace("\\", "/")).name
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    path = Path(candidate)
    if path.is_absolute():
        return path.resolve()
    direct = (config_path.parent / path).resolve()
    if direct.is_file():
        return direct
    if path.parts and path.parts[0].lower() in {"assets", "game_content"}:
        for parent in config_path.parents:
            project_relative = (parent / path).resolve()
            if project_relative.is_file():
                return project_relative
    return direct


def load_subresource_preview(
    project: ProjectContext,
    resource_value: str,
) -> tuple[Path | None, tuple[int, int, int, int] | None]:
    try:
        reference = ResourceReference.parse(
            resource_value,
            allow_legacy_project_path=True,
        )
        source = reference.resolve(project)
    except (ResourceDocumentError, ProjectContextError):
        return None, None
    if reference.subresource is None:
        return source, None
    try:
        project.relative(source)
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError, ProjectContextError):
        return None, None
    sprites = data.get("sprites", {})
    if not isinstance(sprites, dict):
        return None, None
    sprite = sprites.get(reference.subresource)
    if not isinstance(sprite, dict):
        return None, None
    return _resolve_texture_path(source, data, sprite), _safe_rect(
        sprite.get("rect") or sprite.get("region")
    )


class AssetIndex:
    def __init__(self, project: ProjectContext):
        self.project = project
        self.records: tuple[AssetRecord, ...] = ()
        self.errors: tuple[str, ...] = ()

    def scan(self) -> tuple[AssetRecord, ...]:
        records: list[AssetRecord] = []
        errors: list[str] = []
        for root in (self.project.assets, self.project.game_content):
            if not root.is_dir():
                continue
            for path in sorted(self._iter_files(root)):
                try:
                    relative = self.project.relative(path).as_posix()
                except ValueError:
                    continue
                kind = classify_file(path)
                records.append(
                    AssetRecord(
                        uri=f"res://{relative}",
                        path=path,
                        project_path=relative,
                        kind=kind,
                        name=path.name,
                        preview_path=path if kind == "image" else None,
                        metadata={"size": path.stat().st_size},
                    )
                )
                if path.name.endswith(".pystg.json"):
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8-sig"))
                        if not isinstance(payload, dict):
                            raise ValueError("typed resource must contain a JSON object")
                        RESOURCE_TYPES.load(payload)
                    except (OSError, ValueError, json.JSONDecodeError) as exc:
                        errors.append(f"{relative}: {exc}")
                elif kind == "json":
                    try:
                        records.extend(self._json_subresources(path, relative))
                    except (OSError, ValueError, json.JSONDecodeError) as exc:
                        errors.append(f"{relative}: {exc}")
        kind_order = {
            "image": 0,
            "sprite": 1,
            "animation": 2,
            "audio": 3,
            "scene": 4,
            "pattern": 5,
            "ui": 6,
            "background": 7,
            "resource": 8,
            "script": 9,
            "json": 10,
        }
        records.sort(
            key=lambda record: (
                record.folder.lower(),
                kind_order.get(record.kind, 99),
                record.name.lower(),
            )
        )
        self.records = tuple(records)
        self.errors = tuple(errors)
        return self.records

    @staticmethod
    def _iter_files(root: Path) -> Iterable[Path]:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or any(part.startswith(".") for part in path.parts):
                continue
            if path.suffix.lower() in INDEXED_EXTENSIONS:
                yield path.resolve()

    def _json_subresources(
        self,
        config_path: Path,
        relative: str,
    ) -> list[AssetRecord]:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            return []
        records: list[AssetRecord] = []
        sprites = data.get("sprites", {})
        sprite_records: dict[str, AssetRecord] = {}
        if isinstance(sprites, dict):
            for name, sprite in sprites.items():
                if not isinstance(sprite, dict):
                    continue
                rect = _safe_rect(sprite.get("rect") or sprite.get("region"))
                preview_path = _resolve_texture_path(config_path, data, sprite)
                record = AssetRecord(
                    uri=f"res://{relative}#{name}",
                    path=config_path,
                    project_path=relative,
                    kind="sprite",
                    name=str(name),
                    subresource=str(name),
                    preview_path=preview_path,
                    rect=rect,
                    metadata={
                        "config": relative,
                        "source": sprite.get("source"),
                        "radius": sprite.get("radius"),
                    },
                )
                records.append(record)
                sprite_records[str(name)] = record

        animations = data.get("animations", {})
        if (
            isinstance(animations, dict)
            and isinstance(animations.get("animations"), dict)
        ):
            animations = animations["animations"]
        if isinstance(animations, dict):
            for name, animation in animations.items():
                if not isinstance(animation, dict):
                    continue
                frames = animation.get("frames", [])
                if not isinstance(frames, list):
                    frames = []
                first_name = None
                if frames:
                    first = frames[0]
                    if isinstance(first, str):
                        first_name = first
                    elif isinstance(first, dict):
                        first_name = first.get("sprite") or first.get("name")
                preview = sprite_records.get(str(first_name))
                preview_path = preview.preview_path if preview else None
                preview_rect = preview.rect if preview else None
                if preview is None and frames and isinstance(frames[0], dict):
                    preview_path = _resolve_texture_path(config_path, data)
                    preview_rect = _safe_rect(
                        frames[0].get("rect") or frames[0].get("region")
                    )
                strip = animation.get("strip")
                if preview is None and isinstance(strip, dict):
                    preview_path = _resolve_texture_path(config_path, data)
                    preview_rect = _safe_rect(
                        [
                            strip.get("x"),
                            strip.get("y"),
                            strip.get("width"),
                            strip.get("height"),
                        ]
                    )
                records.append(
                    AssetRecord(
                        uri=f"res://{relative}#{name}",
                        path=config_path,
                        project_path=relative,
                        kind="animation",
                        name=str(name),
                        subresource=str(name),
                        preview_path=preview_path,
                        rect=preview_rect,
                        metadata={
                            "config": relative,
                            "frames": len(frames),
                            "fps": animation.get("fps"),
                        },
                    )
                )
        return records

    def find(self, resource_value: str) -> AssetRecord | None:
        try:
            normalized = ResourceReference.parse(
                resource_value,
                allow_legacy_project_path=True,
            ).uri
        except ResourceDocumentError:
            normalized = resource_value
        return next(
            (
                record
                for record in self.records
                if record.resource_value == normalized
            ),
            None,
        )

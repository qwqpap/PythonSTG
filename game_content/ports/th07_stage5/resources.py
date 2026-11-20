"""TH07 stage 5's local assets, sharing the established resource managers.

Only the manifest/cache identity and source music slots differ from stage 6.
No original assets, original-format interpreter, or renderer live in this module.
"""

from __future__ import annotations

import json
import operator
import os
from pathlib import Path
import tempfile

from ..th07_stage6.resources import (
    SOURCE_COLOR_COUNTS, SOURCE_SE_BUFFER_GAIN, SOURCE_SE_FILES,
    Stage6AssetError, Stage6Resources, source_sprite,
)


MANIFEST_NAME = "th07_stage5_assets.json"
MANIFEST_VERSION = 1
ASSET_ENVIRONMENT = "PYSTG_TH07_STAGE5_ASSETS"
DEFAULT_CACHE_NAME = "pystg-th07-stage5-assets"


class Stage5AssetError(Stage6AssetError):
    """The user's original local stage-5 assets are not prepared or bound."""


def default_asset_root() -> Path:
    configured = os.environ.get(ASSET_ENVIRONMENT)
    return (Path(configured).expanduser() if configured else
            Path(tempfile.gettempdir()) / DEFAULT_CACHE_NAME).resolve()


def prepare_command(asset_root=None) -> str:
    root = default_asset_root() if asset_root is None else Path(asset_root).resolve()
    return ('python tools/import_th07_stage5_assets.py '
            '--game-dir "<你的 TH07 游戏目录>" '
            '--thtk-dir "<thtk-bin-12 目录>" '
            f'--output "{root}"')


class Stage5Resources(Stage6Resources):
    """Reuse CPU catalogs, source rects, GPU uploads, and existing audio banks."""

    def bind_audio(self, ctx) -> None:
        if ctx.audio is None:
            raise Stage5AssetError("第五面原音频需要已绑定的 AudioManager。")
        # The shared implementation uses this instance's manifest and root;
        # it does not install or consult the stage-6 Context attribute.
        super().bind_audio(ctx)


def install_resources(ctx=None, asset_root=None) -> Stage5Resources:
    from src.core.sprite_registry import get_sprite_registry
    from src.resource.service import get_resource_service

    root = default_asset_root() if asset_root is None else Path(asset_root).expanduser().resolve()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise Stage5AssetError(f"缺少本地 TH07 五面素材：{manifest_path}\n准备命令：{prepare_command(root)}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema_version") != MANIFEST_VERSION or
            manifest.get("kind") != "th07_stage5_local_assets"):
        raise Stage5AssetError(f"第五面素材清单格式不匹配：{manifest_path}")
    needed = [*manifest["atlases"], *manifest["sound_effects"].values(),
              *(track["path"] for track in manifest["bgm"].values())]
    catalogs = []
    for relative in manifest["atlases"]:
        path = root / relative
        if path.is_file():
            catalog = json.loads(path.read_text(encoding="utf-8"))
            needed.append(catalog["texture"])
            catalogs.append((path, catalog))
    missing = [str(root / relative) for relative in needed if not (root / relative).is_file()]
    if missing:
        raise Stage5AssetError("第五面素材不完整：\n" + "\n".join(missing) +
                               "\n准备命令：" + prepare_command(root))
    assets = ctx.animations.assets if ctx is not None else get_resource_service().textures
    registry = ctx.bullet_pool.sprite_registry if ctx is not None else get_sprite_registry()
    sprites, textures = [], []
    for path, catalog in catalogs:
        atlas = assets.load_atlas_config(str(path))
        if atlas is None or atlas.surface is None:
            raise Stage5AssetError(f"第五面原图图集加载失败：{path}")
        textures.append(atlas.texture_path)
        for name in catalog["sprites"]:
            sprite = assets.get_sprite(name)
            width = max(sprite.rect[2:])
            category = 1 if width >= 64 else 2 if width >= 32 else 3 if width >= 16 else 4
            index = registry.register(name, sprite.texture_path, sprite.rect,
                                      atlas.surface.get_size(), center=sprite.center,
                                      radius=sprite.radius, size_category=category, flip_y=True)
            if index == registry.DEFAULT_INDEX:
                raise Stage5AssetError(f"原图注册失败，不允许默认图替换：{name}")
            sprites.append(name)
    for style, colors in enumerate(SOURCE_COLOR_COUNTS):
        for color in range(colors):
            name = source_sprite(style, color)
            if assets.get_sprite(name) is None or registry.get_index(name) == registry.DEFAULT_INDEX:
                raise Stage5AssetError(f"缺少第五面原图弹型：{name}")
    state = Stage5Resources(root, assets, registry, manifest, tuple(sprites),
                            tuple(dict.fromkeys(textures)))
    if ctx is not None:
        if ctx.audio is not None:
            state.bind_audio(ctx)
        ctx._th07_stage5_resources = state
    return state


def play_source_bgm(ctx, index: int) -> bool:
    index = operator.index(index)
    if index not in (0, 1):
        raise ValueError(f"TH07 stage 5 BGM slot must be 0 or 1, got {index}")
    resources = getattr(ctx, "_th07_stage5_resources", None)
    if resources is None or ctx.audio is None:
        raise Stage5AssetError("播放原 BGM 需要已安装五面素材和 AudioManager。")
    track = resources.manifest["bgm"][str(index)]
    return ctx.play_bgm(track["name"], loop_start_frame=track["loop_start_frame"],
                        loop_end_frame=track["loop_end_frame"])


def play_source_se(ctx, index: int) -> bool:
    index = operator.index(index)
    if not 0 <= index < len(SOURCE_SE_BUFFER_GAIN):
        raise ValueError(f"unsupported TH07 sound ID: {index}")
    if getattr(ctx, "_th07_stage5_resources", None) is None or ctx.audio is None:
        raise Stage5AssetError("播放原音效需要已安装五面素材和 AudioManager。")
    buffer_index, gain = SOURCE_SE_BUFFER_GAIN[index]
    return ctx.play_se("th07_" + Path(SOURCE_SE_FILES[buffer_index]).stem,
                       volume=10.0 ** (gain / 2000.0))

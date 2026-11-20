"""Local-only TH07 stage 6 assets on the existing PySTG resource path.

Prepare assets once with ``tools/import_th07_stage6_assets.py``. Nothing here
interprets ANM/STD or silently replaces missing original sprites. Install before
constructing Renderer, then merge ``create_gl_textures`` / ``sprite_uvs`` into
its existing texture dictionaries. Background geometry is baked offline; the
six-stage camera/layer choreography is hand-translated ordinary content.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import operator
import os
from pathlib import Path
import tempfile


MANIFEST_NAME = "th07_stage6_assets.json"
MANIFEST_VERSION = 2
SOURCE_COLOR_COUNTS = (16, 16, 16, 16, 16, 16, 16, 8, 8, 8, 4)
ASSET_ENVIRONMENT = "PYSTG_TH07_STAGE6_ASSETS"
DEFAULT_CACHE_NAME = "pystg-th07-stage6-assets"

# SoundPlayer.cpp SOUND_BUFFER_IDX_VOL -> g_SFXList. Values are DirectSound dB
# hundredths, not linear gains. Priority fields are not guessed as timeouts.
SOURCE_SE_FILES = (
    "se_plst00.wav", "se_enep00.wav", "se_pldead00.wav", "se_power0.wav",
    "se_power1.wav", "se_tan00.wav", "se_tan01.wav", "se_tan02.wav",
    "se_ok00.wav", "se_cancel00.wav", "se_select00.wav", "se_gun00.wav",
    "se_cat00.wav", "se_lazer00.wav", "se_lazer01.wav", "se_enep01.wav",
    "se_nep00.wav", "se_damage00.wav", "se_item00.wav", "se_kira00.wav",
    "se_kira01.wav", "se_kira02.wav", "se_extend.wav", "se_timeout.wav",
    "se_graze.wav", "se_powerup.wav", "se_border.wav", "se_bonus.wav",
    "se_bonus2.wav", "se_pause.wav",
)
SOURCE_SE_BUFFER_GAIN = (
    (0, -2000), (0, -2500), (1, -1200), (1, -1500), (2, -1000),
    (3, -400), (4, -400), (5, -1500), (6, -1700), (7, -1900),
    (8, -1000), (9, -1000), (10, -1700), (11, -1200), (12, -900),
    (5, -1500), (13, -900), (14, -900), (15, -900), (16, -200),
    (17, -1400), (18, -1300), (5, -100), (6, -1800), (7, -1800),
    (19, -800), (20, -1000), (21, -1300), (22, -300), (23, -900),
    (24, -900), (25, -500), (26, -300), (27, -300), (24, -300),
    (19, 0), (28, -300), (29, -300),
)


class Stage6AssetError(RuntimeError):
    """The original local resources have not been prepared or bound."""


def default_asset_root() -> Path:
    configured = os.environ.get(ASSET_ENVIRONMENT)
    return (Path(configured).expanduser() if configured else
            Path(tempfile.gettempdir()) / DEFAULT_CACHE_NAME).resolve()


def prepare_command(asset_root: str | Path | None = None) -> str:
    root = Path(asset_root).resolve() if asset_root is not None else default_asset_root()
    return ("python tools/import_th07_stage6_assets.py "
            '--game-dir "<你的 TH07 游戏目录>" '
            '--thtk-dir "<thtk-bin-12 目录>" '
            f'--output "{root}"')


def source_sprite(style: int, color: int) -> str:
    """Original ECL style/color -> an exact original rect, without wrapping.

    Styles 0..6 have sixteen colors, 7..9 have eight, and the bubble (10) has
    four. Invalid values are errors, not modulo/clamped alternate projectiles.
    This deterministic ID can be used while constructing behavior definitions.
    """
    style, color = operator.index(style), operator.index(color)
    if not 0 <= style < len(SOURCE_COLOR_COUNTS):
        raise ValueError(f"unsupported TH07 projectile style: {style}")
    if not 0 <= color < SOURCE_COLOR_COUNTS[style]:
        raise ValueError(f"TH07 style {style} has {SOURCE_COLOR_COUNTS[style]} colors, got {color}")
    return f"th07_bullet_{style}_{color}"


@dataclass
class Stage6Resources:
    root: Path
    assets: object
    registry: object
    manifest: dict
    sprite_ids: tuple[str, ...]
    texture_paths: tuple[str, ...]

    @property
    def background_definition(self) -> dict:
        """The locally baked static scene; no source instruction execution."""
        definition = self.manifest.get("background")
        if definition is None:
            raise Stage6AssetError("本地素材缺少背景几何，请重新运行素材准备命令。")
        return definition

    def source_image(self, sprite_id: str) -> tuple[str, tuple, tuple]:
        """Absolute texture, original pixel rect, and texture dimensions."""
        source = self.manifest["source_sprites"][sprite_id]
        sprite = self.assets.get_sprite(sprite_id)
        surface = self.assets.get_texture(sprite.texture_path)
        if surface is None:
            raise Stage6AssetError(f"原图未加载：{sprite_id}")
        return str(self.root / source["texture"]), tuple(source["rect"]), tuple(surface.get_size())

    def create_gl_textures(self, gl_context) -> dict:
        """Upload only the external images; the existing caller owns cleanup."""
        textures = {}
        try:
            for path in self.texture_paths:
                texture = self.assets.create_gl_texture(gl_context, path, flip_y=True)
                if texture is None:
                    raise Stage6AssetError(f"原图上传失败：{path}")
                textures[path] = texture
        except Exception:
            for texture in textures.values():
                texture.release()
            raise
        return textures

    def sprite_uvs(self) -> dict:
        return {name: self.assets.get_sprite_uv_for_gl(name, flip_y=True)
                for name in self.sprite_ids}

    def bind_audio(self, ctx) -> None:
        if ctx.audio is None:
            raise Stage6AssetError("第六面音频未绑定 AudioManager；只读数值检查不会自动打开音频设备。")
        bank = ctx.audio.stage_bank or ctx.audio.game_bank
        for filename, relative in self.manifest["sound_effects"].items():
            name = "th07_" + Path(filename).stem
            if not bank.has_se(name) and not bank.load_se(name, str(self.root / relative)):
                raise Stage6AssetError(f"原音效加载失败：{filename}")
        for track in self.manifest["bgm"].values():
            if not bank.has_bgm(track["name"]) and not bank.load_bgm(
                    track["name"], str(self.root / track["path"])):
                raise Stage6AssetError(f"原 BGM 注册失败：{track['path']}")


def install_resources(ctx=None, asset_root: str | Path | None = None) -> Stage6Resources:
    """Install CPU catalogs in the existing managers, before Renderer creation.

    If audio is present, register the original audio with its existing bank. If
    absent, keep preparation headless; ``play_source_bgm`` still fails explicitly
    instead of pretending to play. This does not refresh a running Renderer.
    """
    from src.core.sprite_registry import get_sprite_registry
    from src.resource.service import get_resource_service

    root = Path(asset_root).expanduser().resolve() if asset_root is not None else default_asset_root()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise Stage6AssetError(f"缺少本地 TH07 六面素材：{manifest_path}\n准备命令：{prepare_command(root)}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MANIFEST_VERSION or manifest.get("kind") != "th07_stage6_local_assets":
        raise Stage6AssetError(f"第六面素材清单格式不匹配：{manifest_path}")
    needed = list(manifest["atlases"])
    needed += list(manifest["sound_effects"].values())
    needed += [track["path"] for track in manifest["bgm"].values()]
    catalogs = []
    for relative in manifest["atlases"]:
        path = root / relative
        if path.is_file():
            catalog = json.loads(path.read_text(encoding="utf-8"))
            needed.append(catalog["texture"])
            catalogs.append((path, catalog))
    missing = [str(root / relative) for relative in needed if not (root / relative).is_file()]
    if missing:
        raise Stage6AssetError("第六面素材不完整：\n" + "\n".join(missing) +
                              "\n准备命令：" + prepare_command(root))

    assets = ctx.animations.assets if ctx is not None else get_resource_service().textures
    registry = ctx.bullet_pool.sprite_registry if ctx is not None else get_sprite_registry()
    sprites = []
    textures = []
    for path, catalog in catalogs:
        atlas = assets.load_atlas_config(str(path))
        if atlas is None or atlas.surface is None:
            raise Stage6AssetError(f"原图图集加载失败：{path}")
        textures.append(atlas.texture_path)
        for name in catalog["sprites"]:
            sprite = assets.get_sprite(name)
            width = max(sprite.rect[2:])
            category = 1 if width >= 64 else 2 if width >= 32 else 3 if width >= 16 else 4
            index = registry.register(name, sprite.texture_path, sprite.rect,
                                      atlas.surface.get_size(), center=sprite.center,
                                      radius=sprite.radius, size_category=category, flip_y=True)
            if index == registry.DEFAULT_INDEX:
                raise Stage6AssetError(f"原图精灵注册失败，不允许默认图替换：{name}")
            sprites.append(name)
    for style, colors in enumerate(SOURCE_COLOR_COUNTS):
        for color in range(colors):
            name = source_sprite(style, color)
            if assets.get_sprite(name) is None or registry.get_index(name) == registry.DEFAULT_INDEX:
                raise Stage6AssetError(f"缺少原图弹型：{name}")
    state = Stage6Resources(root, assets, registry, manifest, tuple(sprites), tuple(dict.fromkeys(textures)))
    if ctx is not None:
        if ctx.audio is not None:
            state.bind_audio(ctx)
        ctx._th07_stage6_resources = state
    return state


def play_source_bgm(ctx, index: int) -> bool:
    """Original stage audio slot: 0=12, 1=13, 2=13b (resurrection)."""
    index = operator.index(index)
    if index not in (0, 1, 2):
        raise ValueError(f"TH07 stage 6 BGM slot must be 0, 1, or 2, got {index}")
    state = getattr(ctx, "_th07_stage6_resources", None)
    if state is None:
        raise Stage6AssetError("播放原 BGM 前需要 install_resources(ctx, asset_root)。")
    if ctx.audio is None:
        raise Stage6AssetError("播放原 BGM 需要已绑定的 AudioManager。")
    track = state.manifest["bgm"][str(index)]
    return ctx.play_bgm(track["name"], loop_start_frame=track["loop_start_frame"],
                        loop_end_frame=track["loop_end_frame"])


def play_source_se(ctx, index: int) -> bool:
    """Original logical sound ID, including its source dB gain."""
    index = operator.index(index)
    if not 0 <= index < len(SOURCE_SE_BUFFER_GAIN):
        raise ValueError(f"unsupported TH07 sound ID: {index}")
    if ctx.audio is None or getattr(ctx, "_th07_stage6_resources", None) is None:
        raise Stage6AssetError("播放原音效需要已安装六面素材和 AudioManager。")
    buffer_index, gain = SOURCE_SE_BUFFER_GAIN[index]
    name = "th07_" + Path(SOURCE_SE_FILES[buffer_index]).stem
    return ctx.play_se(name, volume=10.0 ** (gain / 2000.0))

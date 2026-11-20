"""Extract a user's local TH07 assets; never commit the generated cache.

Requires the official thtk ``thdat`` and ``thanm`` tools, not the original game
executable. PCM music conversion uses bounded standard-library streams. ANM is
inspected offline to export rectangles and literal cut-frame/source tables; no
ANM/STD runtime is added. The six-stage background's static geometry is baked
offline; its finite camera and layer choreography is ordinary Python content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
import wave


MANIFEST_NAME = "th07_stage6_assets.json"
DEFAULT_CACHE_NAME = "pystg-th07-stage6-assets"
ANM_FILES = (
    "etama.anm", "stg6enm.anm", "stg6bg.anm", "eff06.anm", "std6txt.anm",
    "face_05_00.anm", "face_06_00.anm", "eff01.anm", "eff02.anm", "eff03.anm",
    "eff05.anm",
)
SE_FILES = (
    "se_plst00.wav", "se_enep00.wav", "se_pldead00.wav", "se_power0.wav",
    "se_power1.wav", "se_tan00.wav", "se_tan01.wav", "se_tan02.wav",
    "se_ok00.wav", "se_cancel00.wav", "se_select00.wav", "se_gun00.wav",
    "se_cat00.wav", "se_lazer00.wav", "se_lazer01.wav", "se_enep01.wav",
    "se_nep00.wav", "se_damage00.wav", "se_item00.wav", "se_kira00.wav",
    "se_kira01.wav", "se_kira02.wav", "se_extend.wav", "se_timeout.wav",
    "se_graze.wav", "se_powerup.wav", "se_border.wav", "se_bonus.wav",
    "se_bonus2.wav", "se_pause.wav",
)
# Original g_BulletTypeInfos, and each main ANM script's first active sprite.
# (entry, local main sprite, valid palette entries)
BULLET_LAYOUT = (
    (0, 0, 16), (0, 16, 16), (0, 32, 16), (0, 48, 16),
    (0, 64, 16), (0, 80, 16), (0, 96, 16), (0, 112, 8),
    (0, 120, 8), (0, 128, 8), (1, 0, 4),
)
SPAWN_SCRIPTS = (
    (0, 18, 19, 20),
    *((0, 21, 22, 23),) * 6,
    *((0, 24, 24, 24),) * 3,
    (1, 2, 2, 2),
)
BOSS_ANIMATIONS = {
    128: ("th07_youmu", "th07_youmu_idle"),
    129: ("th07_youmu_move_left",),
    130: ("th07_youmu_move_right",),
    147: ("th07_yuyuko", "th07_yuyuko_idle"),
    149: ("th07_yuyuko_move_left",),
    148: ("th07_yuyuko_move_right",),
}


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=4) + "\n", encoding="utf-8", newline="\n")


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_thtk(game_dir: Path, supplied: str | None) -> tuple[Path, Path]:
    directories = [Path(supplied).expanduser().resolve()] if supplied else []
    if not supplied:
        directories += [parent / "rev/.ref/thtk_bin/thtk-bin-12" for parent in game_dir.parents]
    for directory in directories:
        paths = tuple(directory / name for name in ("thdat.exe", "thanm.exe"))
        if all(path.is_file() for path in paths):
            return paths
    paths = tuple(shutil.which(name) for name in ("thdat", "thanm"))
    if all(paths):
        return tuple(Path(path) for path in paths)
    raise RuntimeError("找不到 thdat/thanm；请用 --thtk-dir 指向官方 thtk-bin-12 目录。不会自动下载安装工具。")


def run_tool(tool: Path, arguments: list[str], cwd: Path) -> str:
    result = subprocess.run([str(tool), *arguments], cwd=str(cwd), capture_output=True)
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"{tool.name} 失败，退出码 {result.returncode}：{message}")
    return result.stdout.decode("utf-8", errors="strict")


def parse_anm_spec(spec: str) -> list[dict]:
    """Read the official tool's literal listing, not execute its bytecode."""
    entries = []
    entry = script = None
    for line in spec.splitlines():
        match = re.match(r"ENTRY #(\d+), VERSION (\d+)$", line)
        if match:
            entry = {"entry": int(match[1]), "version": int(match[2]), "sprites": {}, "scripts": {}}
            if entry["version"] != 2:
                raise ValueError("本工具只转换 TH07 的 ANM version 2。")
            entries.append(entry)
            script = None
            continue
        if entry is None:
            continue
        if line.startswith("Name: "):
            entry["texture"] = line[6:].replace("\\", "/")
        match = re.match(r"(Width|Height): (\d+)$", line)
        if match:
            entry["texture_" + match[1].lower()] = int(match[2])
        match = re.match(r"Sprite: (-?\d+) ([\d.]+)\*([\d.]+)\+([\d.]+)\+([\d.]+)$", line)
        if match:
            sprite_id = int(match[1])
            if sprite_id >= 2 ** 31:
                sprite_id -= 2 ** 32
            width, height, x, y = (float(value) for value in match.groups()[1:])
            entry["sprites"][sprite_id] = [x, y, width, height]
        match = re.match(r"Script: (\d+)$", line)
        if match:
            script = []
            entry["scripts"][int(match[1])] = script
        match = re.match(r"Instruction #(\d+): (-?\d+) (\d+) (-?\d+)(?: (.*))?$", line)
        if match:
            if script is None:
                raise ValueError("ANM instruction is outside a script")
            script.append({"index": int(match[1]), "frame": int(match[2]),
                           "flags": int(match[3]), "opcode": int(match[4]),
                           "args": (match[5] or "").split()})
    if not entries:
        raise ValueError("ANM 导出没有任何 Entry")
    base = 0
    for entry in entries:
        entry["global_base"] = base
        # AnmManager::LoadAnms advances by maximum sprite OR script ID + 1.
        base += max(0, *entry["sprites"], *entry["scripts"]) + 1
    return entries


def sprite_name(stem: str, entry: int, local_id: int) -> str:
    suffix = f"neg{-local_id}" if local_id < 0 else str(local_id)
    return f"th07_{stem}_e{entry}_s{suffix}"


def cut_frames(stem: str, entry: dict, instructions: list[dict]) -> tuple[list[dict], dict | None]:
    changes = []
    terminal = None
    for instruction in instructions:
        opcode = instruction["opcode"]
        if opcode == 3 and not instruction["flags"] & 1:
            local = int(instruction["args"][0])
            if local not in entry["sprites"]:
                raise ValueError(f"ANM references missing sprite {stem}/{entry['entry']}/{local}")
            changes.append({"frame": instruction["frame"], "local_sprite": local,
                            "sprite": sprite_name(stem, entry["entry"], local)})
        if opcode in (-1, 1, 2) and terminal is None:
            terminal = {"frame": instruction["frame"], "opcode": opcode,
                        "hides": opcode != 2}
    return changes, terminal


def make_cut_animation(changes: list[dict], instructions: list[dict], terminal: dict | None) -> dict:
    jump = next((item for item in instructions if item["opcode"] == 4 and
                 0 < item["frame"] <= 1024), None)
    end = (jump["frame"] if jump is not None else
           terminal["frame"] if terminal is not None and 0 < terminal["frame"] <= 1024 else
           max(change["frame"] for change in changes) + 1)
    end = max(1, end)
    frames = []
    current = changes[0]["sprite"]
    index = 0
    for frame in range(end):
        while index < len(changes) and changes[index]["frame"] <= frame:
            current = changes[index]["sprite"]
            index += 1
        frames.append(current)
    return {"frames": frames, "frame_duration": 1.0 / 60.0, "loop": jump is not None,
            "metadata": {"source_cut_frames_only": True,
                         "not_anm_execution": True,
                         "unported": "transform, color, visibility, interrupts, variable-dependent jumps"}}


def export_atlases(work: Path, anm_data: dict) -> tuple[list[str], dict, dict]:
    atlas_paths, source_sprites, animations = [], {}, {}
    for stem, entries in anm_data.items():
        for entry in entries:
            catalog = {"texture": entry["texture"], "sprites": {}, "animations": {}}
            for local_id, rect in entry["sprites"].items():
                name = sprite_name(stem, entry["entry"], local_id)
                source = {"archive": stem + ".anm", "entry": entry["entry"],
                          "local_sprite": local_id, "global_sprite": entry["global_base"] + local_id}
                data = {"rect": rect, "center": [rect[2] / 2, rect[3] / 2], "metadata": source}
                catalog["sprites"][name] = data
                source_sprites[name] = {**source, "texture": entry["texture"], "rect": rect}
            if stem == "etama":
                for style, (entry_id, base_sprite, colors) in enumerate(BULLET_LAYOUT):
                    if entry_id == entry["entry"]:
                        for color in range(colors):
                            name = sprite_name(stem, entry_id, base_sprite + color)
                            catalog["sprites"][f"th07_bullet_{style}_{color}"] = catalog["sprites"][name]
            for script_id, instructions in entry["scripts"].items():
                changes, terminal = cut_frames(stem, entry, instructions)
                global_id = entry["global_base"] + script_id
                name = f"th07_{stem}_script_{global_id}"
                animations[name] = {"archive": stem + ".anm", "entry": entry["entry"],
                                    "local_script": script_id, "global_script": global_id,
                                    "cut_frames": changes, "terminal": terminal,
                                    "instructions": instructions}
                if changes:
                    animation = make_cut_animation(changes, instructions, terminal)
                    catalog["animations"][name] = animation
                    if stem == "stg6enm" and global_id in BOSS_ANIMATIONS:
                        for alias in BOSS_ANIMATIONS[global_id]:
                            catalog["animations"][alias] = animation
            relative = f"{stem}_{entry['entry']}.json"
            write_json(work / relative, catalog)
            atlas_paths.append(relative)
    return atlas_paths, source_sprites, animations


def spawn_tables(anm_data: dict) -> dict:
    styles = {}
    for style, (entry_id, fast, normal, slow) in enumerate(SPAWN_SCRIPTS):
        entry = anm_data["etama"][entry_id]
        modes = {}
        for mode, script_id in zip(("fast", "normal", "slow"), (fast, normal, slow)):
            instructions = entry["scripts"][script_id]
            changes, terminal = cut_frames("etama", entry, instructions)
            if terminal is None or not terminal["hides"]:
                raise ValueError(f"style {style} {mode} birth has no source hide termination")
            modes[mode] = {"entry": entry_id, "local_script": script_id,
                           "global_script": entry["global_base"] + script_id,
                           "end_frame": terminal["frame"], "cut_frames": changes,
                           "instructions": instructions}
        styles[str(style)] = modes
    return styles


def export_background(work: Path, anm_data: dict) -> dict:
    """Bake STD object instances into ordinary GL quads, not runtime opcodes.

    Stage::RenderObjects uses quad positions (not object bounding-box positions),
    ANM anchor=3, and a left-handed camera. Reflecting Z preserves its projection
    in the engine's right-handed renderer. UVs retain the original mesh's Y
    direction; textures are uploaded flipped by the existing resource service.
    """
    raw = (work / "stage6.std").read_bytes()
    object_count, quad_count, faces_offset, script_offset = struct.unpack_from("<hhII", raw)
    if (object_count, quad_count) != (2, 4):
        raise ValueError("背景转换只支持已核对的 TH07 第六面场景（2 对象 / 4 面片）。")
    entries = anm_data["stg6bg"]
    entry = entries[0]
    objects = []
    for offset in struct.unpack_from("<2I", raw, 1168):
        object_id, layer, _flags, *bounds = struct.unpack_from("<Hbb6f", raw, offset)
        quads = []
        offset += 28
        while struct.unpack_from("<h", raw, offset)[0] >= 0:
            kind, byte_size, script, _vm, x, y, z, width, height = struct.unpack_from(
                "<hhhh5f", raw, offset,
            )
            if kind != 0 or byte_size != 28:
                raise ValueError("六面背景中出现未转换的面片类型。")
            source = entry["scripts"][script]
            allowed = {2, 3, 8, 9, 12, 22, 31, 34}
            if any(item["opcode"] not in allowed for item in source):
                raise ValueError("六面三维面片动画包含未转换的操作。")
            sprite_id = next(int(item["args"][0]) for item in source if item["opcode"] == 3)
            angle = next((float(item["args"][2].rstrip("f")) for item in source
                          if item["opcode"] == 12), 0.0)
            color = next((int(item["args"][0]) for item in source if item["opcode"] == 9), 0xffffff)
            fade = next(item for item in source if item["opcode"] == 34)
            quads.append({"source_script": script, "position": [x, y, z], "size": [width, height],
                          "sprite": sprite_id, "angle": angle, "color": color,
                          "alpha": int(fade["args"][2]) / 255.0,
                          "fade_start": fade["frame"], "fade_duration": int(fade["args"][0])})
            offset += byte_size
        objects.append({"id": object_id, "layer": layer, "bounds": bounds, "quads": quads})
    instances = []
    for offset in range(faces_offset, script_offset, 16):
        object_id, _unused, *position = struct.unpack_from("<hh3f", raw, offset)
        if object_id < 0:
            break
        instances.append((object_id, position))
    if len(instances) != 36:
        raise ValueError("六面背景实例数量与已核对的原版不符。")
    import math
    baked = []
    # Original draws z-level 0 then 1, preserving source instance order in each.
    for layer in (0, 1):
        for object_id, instance in instances:
            obj = objects[object_id]
            if obj["layer"] != layer:
                continue
            for quad in obj["quads"]:
                x, y, z = [a + b for a, b in zip(quad["position"], instance)]
                width, height = quad["size"]
                x, y = x + abs(width / 2), y + abs(height / 2)
                cosine, sine = math.cos(quad["angle"]), math.sin(quad["angle"])
                vertices = []
                for u, v in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
                    dx, dy = u * width, v * height
                    vertices.append([x + dx * cosine - dy * sine,
                                     y + dx * sine + dy * cosine, -z])
                sx, sy, sw, sh = entry["sprites"][quad["sprite"]]
                tw, th = entry["texture_width"], entry["texture_height"]
                color = quad["color"]
                baked.append({"texture": entry["texture"], "vertices": vertices,
                              "uv_rect": [sx / tw, 1 - sy / th, (sx + sw) / tw, 1 - (sy + sh) / th],
                              "color": [((color >> shift) & 255) / 255 for shift in (16, 8, 0)] + [quad["alpha"]],
                              "source_object": object_id, "source_script": quad["source_script"]})
    return {"schema_version": 1, "source_std_sha256": hashlib.sha256(raw).hexdigest(),
            "objects": object_count, "source_quads": quad_count, "instances": len(instances),
            "quads": baked, "scene_fade_start": 350, "scene_fade_duration": 40,
            "backdrop_sprite": sprite_name("stg6bg", 1, -1),
            "sigil_sprite": sprite_name("stg6bg", 0, 3),
            "spell_sprites": {"youmu": [sprite_name("eff05", index, 0) for index in (0, 1)],
                              "yuyuko": [sprite_name("eff06", index, 0) for index in (0, 1)]},
            "title_scripts": [f"th07_std6txt_script_{index}" for index in range(6)]}


def export_bgm(work: Path, archive: Path) -> dict:
    fmt = (work / "thbgm.fmt").read_bytes()
    records = {}
    for offset in range(0, len(fmt) - 51, 52):
        name = fmt[offset:offset + 16].split(b"\0", 1)[0].decode("ascii")
        if name not in ("th07_12.wav", "th07_13.wav", "th07_13b.wav"):
            continue
        start, _preload, intro, total = struct.unpack_from("<4I", fmt, offset + 16)
        tag, channels, rate, _average, alignment, bits, _extra = struct.unpack_from("<HHIIHHH", fmt, offset + 32)
        if tag != 1 or bits != 16 or alignment != channels * 2 or intro % alignment or total % alignment:
            raise ValueError(f"不支持的源 PCM 格式：{name}")
        if not 0 <= intro < total or start + total > archive.stat().st_size:
            raise ValueError(f"BGM 字节范围不完整：{name}")
        target = work / "audio/bgm" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with archive.open("rb") as raw, wave.open(str(target), "wb") as wav:
            raw.seek(start)
            wav.setparams((channels, bits // 8, rate, total // alignment, "NONE", "not compressed"))
            remaining = total
            while remaining:
                chunk = raw.read(min(remaining, 65536))
                if not chunk:
                    raise ValueError(f"源音乐提前 EOF：{name}")
                wav.writeframesraw(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
        slot = {"th07_12.wav": "0", "th07_13.wav": "1", "th07_13b.wav": "2"}[name]
        records[slot] = {"name": "th07_stage6_" + slot,
                         "source_filename": name, "path": target.relative_to(work).as_posix(),
                         "source_byte_offset": start, "source_pcm_sha256": digest.hexdigest(),
                         "sample_rate": rate, "channels": channels, "bits": bits,
                         "loop_start_frame": intro // alignment, "loop_end_frame": total // alignment}
    if len(records) != 3:
        raise ValueError("thbgm.fmt 缺少六面三首音乐记录")
    return records


def prepare(game_dir: Path, output: Path, thtk_dir: str | None) -> dict:
    archive, bgm_archive = game_dir / "th07.dat", game_dir / "thbgm.dat"
    if not archive.is_file() or not bgm_archive.is_file():
        raise FileNotFoundError("--game-dir 必须含有 th07.dat 和 thbgm.dat。")
    if output == game_dir or output.is_relative_to(game_dir):
        raise ValueError("输出不能位于原版游戏目录，请选择外部缓存目录。")
    if output.exists():
        marker = output / MANIFEST_NAME
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("kind") != "th07_stage6_local_assets":
            raise ValueError("输出目录已有其它文件，不会覆盖；请指定新的缓存目录。")
    thdat, thanm = find_thtk(game_dir, thtk_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".th07-stage6-prepare-", dir=str(output.parent)))
    try:
        run_tool(thdat, ["-x7", str(archive), *ANM_FILES, *SE_FILES,
                        "stage6.std", "msg6.dat", "thbgm.fmt"], work)
        anm_data = {}
        for filename in ANM_FILES:
            spec = run_tool(thanm, ["-l", filename], work)
            (work / (filename + ".txt")).write_text(spec, encoding="utf-8", newline="\n")
            entries = parse_anm_spec(spec)
            run_tool(thanm, ["-x", filename], work)
            for entry in entries:
                if not (work / entry["texture"]).is_file():
                    raise FileNotFoundError(f"没有提取到原 PNG：{entry['texture']}")
            anm_data[Path(filename).stem] = entries
        atlases, source_sprites, animations = export_atlases(work, anm_data)
        effects = {}
        se_dir = work / "audio/se"
        se_dir.mkdir(parents=True)
        for filename in SE_FILES:
            with wave.open(str(work / filename), "rb") as sound:
                if sound.getnframes() <= 0:
                    raise ValueError(f"原音效为空：{filename}")
            (work / filename).replace(se_dir / filename)
            effects[filename] = f"audio/se/{filename}"
        manifest = {"schema_version": 2, "kind": "th07_stage6_local_assets",
                    "source": {"archive": "th07.dat", "archive_sha256": digest_file(archive),
                               "archive_bytes": archive.stat().st_size,
                               "bgm_archive": "thbgm.dat", "bgm_archive_bytes": bgm_archive.stat().st_size},
                    "atlases": atlases, "source_sprites": source_sprites,
                    "animations": animations, "bullet_spawns": spawn_tables(anm_data),
                    "sound_effects": effects, "bgm": export_bgm(work, bgm_archive),
                    "background": export_background(work, anm_data),
                    "raw_background": "stage6.std", "raw_dialogue": "msg6.dat",
                    "unported": ["ANM transform/color/visibility/interrupt/variable-jump execution",
                                 "exact camera-related 3D weather particles and RNG consumption",
                                 "source dialogue layout and complete sound priority behavior"]}
        write_json(work / MANIFEST_NAME, manifest)
        backup = None
        if output.exists():
            backup = output.with_name(output.name + ".previous-" + uuid.uuid4().hex[:8])
            output.replace(backup)
        try:
            work.replace(output)
        except Exception:
            if backup is not None:
                backup.replace(output)
            raise
        if backup is not None:
            print(f"上次素材缓存保留在：{backup}")
        return manifest
    except Exception:
        print(f"准备失败，旧缓存不变；本次诊断产物保留在：{work}")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="本地提取 TH07 第六面原图、原音效、原 BGM；不运行原游戏。")
    parser.add_argument("--game-dir", required=True, help="含 th07.dat/thbgm.dat 的原版游戏目录")
    parser.add_argument("--output", default=str(Path(tempfile.gettempdir()) / DEFAULT_CACHE_NAME),
                        help="外部缓存目录；默认系统临时目录，不把素材写入仓库")
    parser.add_argument("--thtk-dir", help="官方 thtk-bin-12 目录；也可通过 PATH 提供 thdat/thanm")
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()
    try:
        manifest = prepare(Path(args.game_dir).expanduser().resolve(), output, args.thtk_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"素材准备失败：{exc}\n")
    print(f"六面本地素材已准备：{output}")
    print(f"{len(manifest['atlases'])} 图集；{len(manifest['source_sprites'])} 原精灵；"
          f"{len(manifest['sound_effects'])} 原音效；{len(manifest['bgm'])} 首 BGM。")
    print("原图、切帧表、烘焙背景几何；不是 ANM/STD 执行器。未完成项见素材清单 unported。")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())

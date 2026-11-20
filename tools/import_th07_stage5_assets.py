"""Prepare a user's local TH07 stage-5 assets; never modify the original game.

Shared thtk/atlas/bullet export routines come from the existing stage-6 tool.
The scene is baked once, including full 3-axis rotations; only cloud group
offsets and camera-facing bases remain dynamic. No STD/ANM VM runs in PySTG.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import uuid
import wave


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.import_th07_stage6_assets import (  # noqa: E402
    SE_FILES, digest_file, export_atlases, find_thtk, parse_anm_spec, run_tool,
    spawn_tables, sprite_name, write_json,
)


MANIFEST_NAME = "th07_stage5_assets.json"
DEFAULT_CACHE_NAME = "pystg-th07-stage5-assets"
ANM_FILES = (
    "etama.anm", "stg5enm.anm", "stg5bg.anm", "eff05.anm", "std5txt.anm",
    "face_05_00.anm", "eff01.anm", "eff02.anm", "eff03.anm",
)
SOURCE_STD_SHA256 = "7a1956351310d67796e15993323fe887dc12eb14f4fa2fd948f97b80b32b82b0"


def _rotate(point, angles):
    """D3DX's row-vector Rx*Ry*Rz, then reflect Z for the RH renderer."""
    x, y, z = point
    rx, ry, rz = angles
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return x, y, z


def export_background(work, anm_data):
    raw = (work / "stage5.std").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_STD_SHA256:
        raise ValueError("stage5.std 与已核对的 TH07 1.00b 不同；不能静默套用镜头编排。")
    object_count, quad_count, faces_offset, script_offset = struct.unpack_from("<hhII", raw)
    entry = anm_data["stg5bg"][0]
    objects = []
    for offset in struct.unpack_from(f"<{object_count}I", raw, 1168):
        object_id, layer, _flags, *bounds = struct.unpack_from("<Hbb6f", raw, offset)
        offset += 28
        quads = []
        while struct.unpack_from("<h", raw, offset)[0] >= 0:
            quad = struct.unpack_from("<hhhh5f", raw, offset)
            if quad[:2] != (0, 28):
                raise ValueError("五面背景含未转换的面片类型。")
            _, size, script_id, _, x, y, z, width, height = quad
            instructions = entry["scripts"][script_id]
            allowed = {2, 3, 4, 6, 9, 12, 22, 24, 25, 31, 32}
            if any(item["opcode"] not in allowed or item["flags"] for item in instructions):
                raise ValueError(f"五面三维脚本 {script_id} 有未转换的操作。")
            initial = {item["opcode"]: item["args"] for item in instructions if item["frame"] == 0}
            sprite_id = int(initial[3][0])
            translation = [float(value.rstrip("f")) for value in initial.get(6, ["0", "0", "0"])]
            rotation = [float(value.rstrip("f")) for value in initial.get(12, ["0", "0", "0"])]
            quads.append({"script": script_id, "position": [x, y, z], "size": [width, height],
                          "sprite": sprite_id, "translation": translation, "rotation": rotation,
                          "color": int(initial.get(9, [str(0xffffff)])[0]),
                          "billboard": int(initial.get(25, ["0"])[0]) == 2})
            offset += size
        objects.append({"id": object_id, "layer": layer, "bounds": bounds, "quads": quads})
    instances = []
    for offset in range(faces_offset, script_offset, 16):
        object_index, _, *position = struct.unpack_from("<hh3f", raw, offset)
        if object_index < 0:
            break
        instances.append((object_index, position))
    if (object_count, quad_count, len(instances)) != (8, 29, 162):
        raise ValueError("五面背景对象、面片或实例数量与原版不符。")
    baked = []
    for layer in range(4):
        for object_index, instance in instances:
            obj = objects[object_index]
            if obj["layer"] != layer:
                continue
            for quad in obj["quads"]:
                x, y, z = [a + b + c for a, b, c in zip(
                    quad["position"], instance, quad["translation"],
                )]
                width, height = quad["size"]
                sx, sy, sw, sh = entry["sprites"][quad["sprite"]]
                billboard_center = None
                group = None
                if quad["billboard"]:
                    # RenderObjects projects one width vector then sets both
                    # sprite scale axes to that value. Anchor3 is screen top-left.
                    height = sh * width / sw
                    billboard_center = [x, y, -z]
                    vertices = [[x + dx, y + dy, -z] for dx, dy in (
                        (0, 0), (width, 0), (width, -height), (0, -height),
                    )]
                    group = f"cloud_{quad['script']}"
                else:
                    x, y = x + abs(width / 2), y + abs(height / 2)
                    vertices = []
                    for u, v in ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)):
                        dx, dy, dz = _rotate((u * width, v * height, 0), quad["rotation"])
                        vertices.append([x + dx, y + dy, -(z + dz)])
                tw, th = entry["texture_width"], entry["texture_height"]
                color = quad["color"]
                baked.append({
                    "texture": entry["texture"], "vertices": vertices,
                    "uv_rect": [sx / tw, 1 - sy / th, (sx + sw) / tw, 1 - (sy + sh) / th],
                    "color": [((color >> shift) & 255) / 255 for shift in (16, 8, 0)] + [1.0],
                    "group": group, "billboard_center": billboard_center,
                    "depth_test": True, "depth_write": True,
                    "fog_mode": "distance_alpha" if billboard_center is not None else "depth",
                    "source_object_index": object_index, "source_object": obj["id"],
                    "source_script": quad["script"], "source_layer": layer,
                })
    return {"schema_version": 1, "source_std_sha256": SOURCE_STD_SHA256,
            "objects": object_count, "source_quads": quad_count, "instances": len(instances),
            "quads": baked, "external_labels": [],
            "spell_sprites": {"youmu": [sprite_name("eff05", index, 0) for index in (0, 1)]},
            "title_scripts": [f"th07_std5txt_script_{index}" for index in range(5)]}


def export_bgm(work, archive):
    """Bounded PCM extraction; source loop points remain exact sample frames."""
    fmt = (work / "thbgm.fmt").read_bytes()
    tracks = {"th07_10.wav": "0", "th07_11.wav": "1"}
    records = {}
    for offset in range(0, len(fmt) - 51, 52):
        name = fmt[offset:offset + 16].split(b"\0", 1)[0].decode("ascii")
        if name not in tracks:
            continue
        start, _, intro, total = struct.unpack_from("<4I", fmt, offset + 16)
        tag, channels, rate, _, alignment, bits, _ = struct.unpack_from("<HHIIHHH", fmt, offset + 32)
        if (tag != 1 or bits != 16 or alignment != channels * 2 or intro % alignment or
                total % alignment or not 0 <= intro < total or start + total > archive.stat().st_size):
            raise ValueError(f"不支持或不完整的原 PCM：{name}")
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
                    raise ValueError(f"原 BGM 提前 EOF：{name}")
                wav.writeframesraw(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
        slot = tracks[name]
        records[slot] = {"name": "th07_stage5_" + slot,
                         "source_filename": name, "path": target.relative_to(work).as_posix(),
                         "source_byte_offset": start, "source_pcm_sha256": digest.hexdigest(),
                         "sample_rate": rate, "channels": channels, "bits": bits,
                         "loop_start_frame": intro // alignment, "loop_end_frame": total // alignment}
    if len(records) != 2:
        raise ValueError("thbgm.fmt 缺少五面两首原音乐。")
    return records


def prepare(game_dir, output, thtk_dir=None):
    archive, bgm_archive = game_dir / "th07.dat", game_dir / "thbgm.dat"
    if not archive.is_file() or not bgm_archive.is_file():
        raise FileNotFoundError("--game-dir 必须含有 th07.dat 和 thbgm.dat。")
    if output == game_dir or output.is_relative_to(game_dir):
        raise ValueError("输出不能位于原版游戏目录。")
    if output.exists():
        marker = output / MANIFEST_NAME
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("kind") != "th07_stage5_local_assets":
            raise ValueError("输出目录已有其它文件，不覆盖；请选择新的外部缓存。")
    thdat, thanm = find_thtk(game_dir, thtk_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".th07-stage5-prepare-", dir=str(output.parent)))
    try:
        run_tool(thdat, ["-x7", str(archive), *ANM_FILES, *SE_FILES,
                        "stage5.std", "msg5.dat", "thbgm.fmt"], work)
        anm_data = {}
        for filename in ANM_FILES:
            spec = run_tool(thanm, ["-l", filename], work)
            (work / (filename + ".txt")).write_text(spec, encoding="utf-8", newline="\n")
            entries = parse_anm_spec(spec)
            run_tool(thanm, ["-x", filename], work)
            for entry in entries:
                if not (work / entry["texture"]).is_file():
                    raise FileNotFoundError(f"原 PNG 未导出：{entry['texture']}")
            anm_data[Path(filename).stem] = entries
        atlases, source_sprites, animations = export_atlases(work, anm_data)
        se_dir = work / "audio/se"
        se_dir.mkdir(parents=True)
        effects = {}
        for filename in SE_FILES:
            with wave.open(str(work / filename), "rb") as sound:
                if not sound.getnframes():
                    raise ValueError(f"原音效为空：{filename}")
            (work / filename).replace(se_dir / filename)
            effects[filename] = f"audio/se/{filename}"
        manifest = {"schema_version": 1, "kind": "th07_stage5_local_assets",
                    "source": {"archive": "th07.dat", "archive_sha256": digest_file(archive),
                               "archive_bytes": archive.stat().st_size,
                               "bgm_archive": "thbgm.dat", "bgm_archive_bytes": bgm_archive.stat().st_size},
                    "atlases": atlases, "source_sprites": source_sprites,
                    "animations": animations, "bullet_spawns": spawn_tables(anm_data),
                    "sound_effects": effects, "bgm": export_bgm(work, bgm_archive),
                    "background": export_background(work, anm_data),
                    "raw_background": "stage5.std", "raw_dialogue": "msg5.dat",
                    "unported": ["complete actor ANM transform/color/visibility/interrupt execution",
                                 "original object coarse culling and sub-frame projection rounding",
                                 "MSG dialogue layout and original sound priority policy"]}
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
            print(f"上次五面缓存保留在：{backup}")
        return manifest
    except Exception:
        print(f"素材准备失败；旧缓存不变，诊断产物保留在：{work}")
        raise


def main():
    parser = argparse.ArgumentParser(description="本地导出 TH07 五面原图/背景/音效/BGM，不运行原游戏。")
    parser.add_argument("--game-dir", required=True)
    parser.add_argument("--output", default=str(Path(tempfile.gettempdir()) / DEFAULT_CACHE_NAME))
    parser.add_argument("--thtk-dir")
    args = parser.parse_args()
    try:
        manifest = prepare(Path(args.game_dir).expanduser().resolve(),
                           Path(args.output).expanduser().resolve(), args.thtk_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"五面素材准备失败：{exc}\n")
    print(f"五面素材已准备：{args.output}")
    print(f"{len(manifest['atlases'])} 图集，{len(manifest['source_sprites'])} 原精灵，"
          f"{len(manifest['background']['quads'])} 背景面片，2 首原 BGM。")
    print("这是离线原图和几何转换，不是 ANM/STD 执行器。")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())

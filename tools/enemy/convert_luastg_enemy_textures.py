"""
从 LuaSTG 的 enemy.lua 提取纹理参数并转换为 JSON 格式

这个脚本读取 luastg_game/packages/thlib-scripts/THlib/enemy/enemy.lua 中的
LoadImageGroup 调用，提取纹理坐标、尺寸、帧数等参数，并转换为 JSON 格式。

支持的 LoadImageGroup 格式:
    LoadImageGroup(name, texture, x, y, width, height, frame_count, row_count, hscale, vscale)

参数说明:
    - name: 图像组名称 (如 'enemy1_')
    - texture: 纹理名称 (如 'enemy1')
    - x, y: 纹理中的起始坐标（像素）
    - width, height: 单帧宽高（像素）
    - frame_count: 横向帧数
    - row_count: 纵向帧数
    - hscale, vscale: 水平/垂直缩放倍数（可选）
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class LuaSTGEnemyTextureConverter:
    """LuaSTG 敌人纹理参数转换器"""

    def __init__(self, lua_file: Path):
        self.lua_file = lua_file
        self.textures: Dict[str, str] = {}  # texture_name -> file_path
        self.image_groups: List[Dict] = []

    def parse_lua_file(self):
        """解析 Lua 文件，提取 LoadTexture 和 LoadImageGroup 调用"""
        if not self.lua_file.exists():
            raise FileNotFoundError(f"找不到文件: {self.lua_file}")

        content = self.lua_file.read_text(encoding='utf-8')

        # 提取 LoadTexture('name', 'path')
        texture_pattern = r"LoadTexture\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
        for match in re.finditer(texture_pattern, content):
            texture_name = match.group(1)
            texture_path = match.group(2)
            self.textures[texture_name] = texture_path
            print(f"[纹理] {texture_name} -> {texture_path}")

        # 提取 LoadImageGroup
        # 格式: LoadImageGroup('name', 'texture', x, y, w, h, cols, rows[, hscale, vscale])
        group_pattern = r"LoadImageGroup\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+)\s*,\s*([\d.]+))?\s*\)"

        for match in re.finditer(group_pattern, content):
            name = match.group(1)
            texture = match.group(2)
            x = int(match.group(3))
            y = int(match.group(4))
            width = int(match.group(5))
            height = int(match.group(6))
            frame_count = int(match.group(7))
            row_count = int(match.group(8))
            hscale = float(match.group(9)) if match.group(9) else 1.0
            vscale = float(match.group(10)) if match.group(10) else 1.0

            image_group = {
                'name': name,
                'texture': texture,
                'texture_path': self.textures.get(texture, ''),
                'rect': {
                    'x': x,
                    'y': y,
                    'width': width,
                    'height': height
                },
                'frames': {
                    'cols': frame_count,
                    'rows': row_count,
                    'total': frame_count * row_count
                },
                'scale': {
                    'x': hscale,
                    'y': vscale
                },
                'center': {
                    'x': width // 2,
                    'y': height // 2
                }
            }

            self.image_groups.append(image_group)
            print(f"[图像组] {name}: {width}x{height} @ ({x},{y}), {frame_count}x{row_count}帧, 缩放{hscale}x{vscale}")

    def convert_to_json_sprites(self, texture_filter: Optional[str] = None) -> Dict:
        """
        转换为 JSON 格式的 sprites 定义

        Args:
            texture_filter: 只转换指定纹理（如 'enemy1'）

        Returns:
            包含 sprites 和 animations 的字典
        """
        sprites = {}
        animations = {}
        zones = []

        for group in self.image_groups:
            if texture_filter and group['texture'] != texture_filter:
                continue

            name = group['name'].rstrip('_')  # 移除末尾的 '_'
            rect = group['rect']
            frames_info = group['frames']
            scale = group['scale']

            # 如果是单帧（1x1）
            if frames_info['total'] == 1:
                sprite_name = name
                sprites[sprite_name] = {
                    'rect': [rect['x'], rect['y'], rect['width'], rect['height']],
                    'center': [rect['width'] // 2, rect['height'] // 2],
                    'scale': [scale['x'], scale['y']] if scale['x'] != 1.0 or scale['y'] != 1.0 else None
                }
                # 清理 None 值
                if sprites[sprite_name]['scale'] is None:
                    del sprites[sprite_name]['scale']

            # 如果是多帧动画
            else:
                frame_names = []
                frame_idx = 0

                # 生成每一帧的 sprite
                for row in range(frames_info['rows']):
                    for col in range(frames_info['cols']):
                        sprite_name = f"{name}_{frame_idx}"
                        frame_x = rect['x'] + col * rect['width']
                        frame_y = rect['y'] + row * rect['height']

                        sprites[sprite_name] = {
                            'rect': [frame_x, frame_y, rect['width'], rect['height']],
                            'center': [rect['width'] // 2, rect['height'] // 2],
                            'scale': [scale['x'], scale['y']] if scale['x'] != 1.0 or scale['y'] != 1.0 else None
                        }

                        # 清理 None 值
                        if sprites[sprite_name]['scale'] is None:
                            del sprites[sprite_name]['scale']

                        frame_names.append(sprite_name)
                        frame_idx += 1

                # 创建动画定义
                animations[name] = {
                    'frames': frame_names,
                    'fps': 8,  # LuaSTG 默认 8 fps
                    'loop': True
                }

                # 添加 zone 信息（原始区域）
                zones.append({
                    'name': name,
                    'x': rect['x'],
                    'y': rect['y'],
                    'w': rect['width'] * frames_info['cols'],
                    'h': rect['height'] * frames_info['rows'],
                    'frame_w': rect['width'],
                    'frame_h': rect['height'],
                    'cols': frames_info['cols'],
                    'rows': frames_info['rows']
                })

        result = {
            'sprites': sprites
        }
        if animations:
            result['animations'] = animations
        if zones:
            result['zones'] = zones

        return result

    def generate_texture_json(self, texture_name: str, output_file: Path):
        """
        为指定纹理生成完整的 JSON 配置文件

        Args:
            texture_name: 纹理名称（如 'enemy1'）
            output_file: 输出 JSON 文件路径
        """
        if texture_name not in self.textures:
            raise ValueError(f"未找到纹理: {texture_name}")

        texture_path = self.textures[texture_name]
        png_filename = Path(texture_path).name

        json_data = {
            '__image_filename': png_filename,
            **self.convert_to_json_sprites(texture_filter=texture_name)
        }

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        print(f"\n✅ 已生成: {output_file}")
        print(f"   纹理: {texture_name} ({png_filename})")
        print(f"   精灵数: {len(json_data['sprites'])}")
        if 'animations' in json_data:
            print(f"   动画数: {len(json_data['animations'])}")

    def print_summary(self):
        """打印汇总信息"""
        print("\n" + "="*60)
        print("LuaSTG 敌人纹理参数提取汇总")
        print("="*60)

        # 按纹理分组
        by_texture = {}
        for group in self.image_groups:
            tex = group['texture']
            if tex not in by_texture:
                by_texture[tex] = []
            by_texture[tex].append(group)

        for texture_name, groups in by_texture.items():
            print(f"\n📦 纹理: {texture_name}")
            print(f"   路径: {self.textures.get(texture_name, '未知')}")
            print(f"   图像组数: {len(groups)}")
            print("   包含:")

            for group in groups:
                name = group['name']
                rect = group['rect']
                frames = group['frames']
                scale = group['scale']

                print(f"     - {name:20s} | {rect['width']:3d}x{rect['height']:3d} @ ({rect['x']:3d},{rect['y']:3d}) "
                      f"| {frames['cols']:2d}x{frames['rows']:2d}帧 | 缩放 {scale['x']:.1f}x{scale['y']:.1f}")

        print("\n" + "="*60)


def main():
    """主函数"""
    # 路径配置
    project_root = Path(__file__).parent.parent.parent
    lua_file = project_root / "luastg_game" / "packages" / "thlib-scripts" / "THlib" / "enemy" / "enemy.lua"
    output_dir = project_root / "assets" / "images" / "enemy"

    print(f"项目根目录: {project_root}")
    print(f"Lua 文件: {lua_file}")
    print(f"输出目录: {output_dir}")
    print()

    # 创建转换器
    converter = LuaSTGEnemyTextureConverter(lua_file)

    # 解析 Lua 文件
    print("正在解析 Lua 文件...")
    converter.parse_lua_file()

    # 打印汇总
    converter.print_summary()

    # 生成 JSON 文件
    print("\n正在生成 JSON 配置文件...")

    # 为每个纹理生成独立的 JSON 文件
    for texture_name in converter.textures.keys():
        if texture_name.startswith('enemy'):  # 只处理敌人纹理
            output_file = output_dir / f"{texture_name}.json"
            try:
                converter.generate_texture_json(texture_name, output_file)
            except Exception as e:
                print(f"❌ 生成 {texture_name}.json 失败: {e}")

    print("\n✨ 转换完成！")
    print(f"\n生成的 JSON 文件可以直接用于你的编辑器。")
    print(f"文件位置: {output_dir}")


if __name__ == '__main__':
    main()

"""
配置格式转换工具

将旧格式的精灵配置文件转换为新的 v2.0 格式

用法:
    python tools/convert_sprite_config.py [input_path] [--output output_path]
    
    如果不指定参数，会转换 assets/images 下的所有 JSON 文件
"""

import json
import os
import sys
import argparse
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_ROOT = os.path.join(ROOT, "assets", "images")


def is_new_format(config: dict) -> bool:
    """检查是否为新格式配置"""
    return config.get('version') == '2.0' or 'texture' in config


def convert_to_new_format(config: dict, config_path: str) -> dict:
    """
    将旧格式配置转换为新格式
    
    Args:
        config: 旧格式配置
        config_path: 配置文件路径（用于解析相对路径）
        
    Returns:
        新格式配置
    """
    # 获取图片路径
    texture_filename = config.get('__image_filename', '')
    
    # 新格式配置
    new_config = {
        'version': '2.0',
        'description': f'从旧格式转换: {os.path.basename(config_path)}',
        'texture': texture_filename,
        'sprites': {},
        'animations': {}
    }
    
    # 转换精灵数据
    sprites_data = config.get('sprites', {})
    if not sprites_data:
        # 旧格式：精灵直接在根级别
        for key, value in config.items():
            if key.startswith('__'):
                continue
            if isinstance(value, dict) and 'rect' in value:
                sprites_data[key] = value
    
    for sprite_name, sprite_data in sprites_data.items():
        if not isinstance(sprite_data, dict):
            continue
        
        new_sprite = {
            'rect': sprite_data.get('rect', [0, 0, 32, 32]),
            'center': sprite_data.get('center', [16, 16]),
        }
        
        # 可选字段
        radius = sprite_data.get('radius', 0.0)
        if radius > 0:
            new_sprite['radius'] = radius
        
        # 统一使用 'rotate' 字段
        is_rotating = sprite_data.get('is_rotating', sprite_data.get('rotate', False))
        if is_rotating:
            new_sprite['rotate'] = True
        
        scale = sprite_data.get('scale')
        if scale and scale != [1.0, 1.0]:
            new_sprite['scale'] = scale
        
        new_config['sprites'][sprite_name] = new_sprite
    
    return new_config


def convert_file(input_path: str, output_path: str = None, backup: bool = True) -> bool:
    """
    转换单个文件
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径（默认覆盖原文件）
        backup: 是否备份原文件
        
    Returns:
        是否转换成功
    """
    if not os.path.exists(input_path):
        print(f"文件不存在: {input_path}")
        return False
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"读取文件失败 {input_path}: {e}")
        return False
    
    # 检查是否已经是新格式
    if is_new_format(config):
        print(f"跳过（已是新格式）: {input_path}")
        return True
    
    # 转换
    new_config = convert_to_new_format(config, input_path)
    
    # 确定输出路径
    if output_path is None:
        output_path = input_path
    
    # 备份原文件
    if backup and output_path == input_path:
        backup_path = input_path + '.bak'
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            print(f"已备份: {backup_path}")
        except Exception as e:
            print(f"备份失败: {e}")
    
    # 写入新配置
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(new_config, f, ensure_ascii=False, indent=2)
        print(f"已转换: {input_path} -> {output_path}")
        print(f"  精灵数: {len(new_config['sprites'])}, 动画数: {len(new_config['animations'])}")
        return True
    except Exception as e:
        print(f"写入失败 {output_path}: {e}")
        return False


def convert_folder(folder_path: str, backup: bool = True) -> tuple:
    """
    转换文件夹中的所有配置文件
    
    Args:
        folder_path: 文件夹路径
        backup: 是否备份原文件
        
    Returns:
        (成功数, 失败数, 跳过数)
    """
    success = 0
    failed = 0
    skipped = 0
    
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if not filename.endswith('.json'):
                continue
            
            # 跳过备份文件
            if filename.endswith('.bak.json'):
                continue
            
            filepath = os.path.join(root, filename)
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                if is_new_format(config):
                    skipped += 1
                    continue
                
                if convert_file(filepath, backup=backup):
                    success += 1
                else:
                    failed += 1
                    
            except Exception as e:
                print(f"处理失败 {filepath}: {e}")
                failed += 1
    
    return success, failed, skipped


def main():
    parser = argparse.ArgumentParser(description='将精灵配置转换为新的 v2.0 格式')
    parser.add_argument('input', nargs='?', default=None,
                       help='输入文件或文件夹路径（默认: assets/images）')
    parser.add_argument('--output', '-o', default=None,
                       help='输出文件路径（仅对单个文件有效）')
    parser.add_argument('--no-backup', action='store_true',
                       help='不备份原文件')
    parser.add_argument('--dry-run', action='store_true',
                       help='仅显示将要转换的文件，不实际执行')
    
    args = parser.parse_args()
    
    # 确定输入路径
    input_path = args.input or ASSETS_ROOT
    backup = not args.no_backup
    
    if args.dry_run:
        print("=== 预览模式（不会实际修改文件）===\n")
    
    if os.path.isfile(input_path):
        # 转换单个文件
        if args.dry_run:
            print(f"将转换: {input_path}")
        else:
            convert_file(input_path, args.output, backup=backup)
    elif os.path.isdir(input_path):
        # 转换文件夹
        if args.dry_run:
            count = 0
            for root, dirs, files in os.walk(input_path):
                for f in files:
                    if f.endswith('.json') and not f.endswith('.bak.json'):
                        filepath = os.path.join(root, f)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as fh:
                                config = json.load(fh)
                            if not is_new_format(config):
                                print(f"将转换: {filepath}")
                                count += 1
                        except:
                            pass
            print(f"\n共 {count} 个文件需要转换")
        else:
            success, failed, skipped = convert_folder(input_path, backup=backup)
            print(f"\n转换完成: 成功 {success}, 失败 {failed}, 跳过 {skipped}")
    else:
        print(f"路径不存在: {input_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()

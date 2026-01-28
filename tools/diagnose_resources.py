"""
资源诊断脚本 - 检查纹理和精灵配置的问题
"""
import os
import json
from pathlib import Path


def diagnose_resources():
    """诊断资源加载问题"""
    print("=== Resource Diagnostic Report ===\n")
    
    # 检查目录结构
    print("1. Directory Structure:")
    assets_root = Path("assets/images")
    if assets_root.exists():
        print(f"   ✓ Found: {assets_root}")
        for subdir in sorted(assets_root.iterdir()):
            if subdir.is_dir():
                file_count = len(list(subdir.glob("*")))
                print(f"     - {subdir.name}/: {file_count} items")
    else:
        print(f"   ✗ Missing: {assets_root}")
    
    # 检查精灵配置文件
    print("\n2. Sprite Configuration Files (.json):")
    json_files = list(Path("assets/images").glob("*.json"))
    if json_files:
        for json_file in sorted(json_files):
            print(f"   ✓ {json_file.name}")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    sprite_count = len(config.get('sprites', {}))
                    print(f"     - Sprites defined: {sprite_count}")
            except Exception as e:
                print(f"     ✗ Error reading: {e}")
    else:
        print("   ✗ No JSON files found")
    
    # 检查纹理文件
    print("\n3. Texture Files (.png):")
    png_files = list(Path("assets/images").rglob("*.png"))
    if png_files:
        for png_file in sorted(png_files):
            rel_path = png_file.relative_to("assets/images")
            size = os.path.getsize(png_file) / 1024  # KB
            print(f"   ✓ {rel_path} ({size:.1f} KB)")
    else:
        print("   ✗ No PNG files found")
    
    # 检查特殊纹理
    print("\n4. Critical Textures:")
    critical_paths = [
        "assets/images/bullet/bullet1.png",
        "assets/images/laser/laser1.png",
        "assets/images/laser/laser2.png",
    ]
    for path in critical_paths:
        if os.path.exists(path):
            size = os.path.getsize(path) / 1024
            print(f"   ✓ {path} ({size:.1f} KB)")
        else:
            print(f"   ✗ Missing: {path}")
    
    # 检查精灵配置中的纹理路径
    print("\n5. Texture References in Configs:")
    all_textures = set()
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                for sprite_id, sprite_data in config.get('sprites', {}).items():
                    tex_path = sprite_data.get('texture_path', '')
                    if tex_path:
                        all_textures.add(tex_path)
        except:
            pass
    
    print(f"   Total unique texture paths: {len(all_textures)}")
    for tex in sorted(all_textures):
        full_path = Path("assets") / tex
        exists = "✓" if full_path.exists() else "✗"
        print(f"   {exists} {tex}")
    
    # 建议
    print("\n6. Recommendations:")
    if not json_files:
        print("   - No sprite configuration files found!")
        print("   - Create JSON files in assets/images/ with sprite definitions")
    
    if not png_files:
        print("   - No PNG texture files found!")
        print("   - Copy texture files to assets/images/")
    
    missing_textures = [tex for tex in all_textures 
                       if not (Path("assets") / tex).exists()]
    if missing_textures:
        print(f"   - {len(missing_textures)} referenced texture(s) not found:")
        for tex in missing_textures[:5]:
            print(f"     * {tex}")
    
    print("\n=== End of Report ===\n")


if __name__ == "__main__":
    diagnose_resources()

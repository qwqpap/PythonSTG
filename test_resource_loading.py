"""
快速测试脚本 - 验证资源加载是否正常
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from resource.sprite import SpriteManager

print("Testing sprite manager resource loading...\n")

sprite_manager = SpriteManager()

# 测试加载
print("Loading sprite configs from assets/images...")
result = sprite_manager.load_sprite_config_folder("assets/images")

print(f"\nLoad result: {'Success' if result else 'Failed'}")
print(f"Total sprites loaded: {len(sprite_manager.get_all_sprite_ids())}")
print(f"Total textures found: {len(sprite_manager.get_all_texture_paths())}")

print("\nSprite IDs (first 20):")
for sprite_id in list(sprite_manager.get_all_sprite_ids())[:20]:
    print(f"  - {sprite_id}")

print("\nTexture paths:")
for texture_path in sorted(sprite_manager.get_all_texture_paths()):
    exists = "OK" if os.path.exists(texture_path) else "MISSING"
    print(f"  [{exists}] {texture_path}")

print("\nTest completed!")

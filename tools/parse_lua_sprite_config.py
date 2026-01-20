import re
import json
import os


def parse_lua_sprite_config(lua_file_path):
    """
    解析Lua精灵配置文件，生成JSON格式的精灵配置
    """
    with open(lua_file_path, 'r', encoding='utf-8') as f:
        lua_content = f.read()
    
    # 解析LoadTexture
    texture_pattern = re.compile(r"LoadTexture\s*\('([^']+)',\s*'([^']+)',?[^\)]*\)")
    textures = {}
    for match in texture_pattern.finditer(lua_content):
        texture_name, texture_path = match.groups()
        textures[texture_name] = texture_path.replace('\\', '/')
    
    # 解析LoadImageGroup
    image_group_pattern = re.compile(r"LoadImageGroup\s*\('([^']+)',\s*'([^']+)',\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)(?:,\s*(\d+(?:\.\d+)?))?(?:,\s*(\d+(?:\.\d+)?))?[^\)]*\)")
    sprites = {}
    
    for match in image_group_pattern.finditer(lua_content):
        group_name, texture_name, x, y, width, height, columns, rows, scale_x, scale_y = match.groups()
        x, y, width, height, columns, rows = map(int, [x, y, width, height, columns, rows])
        scale_x = float(scale_x) if scale_x else 1.0
        scale_y = float(scale_y) if scale_y else 1.0
        
        if texture_name in textures:
            image_path = textures[texture_name]
        else:
            image_path = f"THlib/bullet/{texture_name}.png"  # 默认路径
        
        # 计算每个精灵的位置
        total_sprites = columns * rows
        for i in range(total_sprites):
            sprite_index = i + 1
            sprite_id = f"{group_name}{sprite_index}"
            
            # 计算当前精灵在图集中的坐标
            col = i % columns
            row = i // columns
            sprite_x = x + col * width
            sprite_y = y + row * height
            
            # 创建精灵配置
            sprites[sprite_id] = {
                "id": sprite_id,
                "rect": [sprite_x, sprite_y, width, height],
                "center": [width // 2, height // 2],  # 默认中心点
                "radius": max(width, height) // 2,    # 默认碰撞半径
                "rotate": True,
                "scale": [scale_x, scale_y],
                "image_path": image_path
            }
    
    # 解析单独的LoadImage
    single_image_pattern = re.compile(r"LoadImage\s*\('([^']+)',\s*'([^']+)',\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)(?:,\s*(\d+(?:\.\d+)?))?(?:,\s*(\d+(?:\.\d+)?))?[^\)]*\)")
    
    for match in single_image_pattern.finditer(lua_content):
        sprite_id, texture_name, x, y, width, height, scale_x, scale_y = match.groups()
        x, y, width, height = map(int, [x, y, width, height])
        scale_x = float(scale_x) if scale_x else 1.0
        scale_y = float(scale_y) if scale_y else 1.0
        
        if texture_name in textures:
            image_path = textures[texture_name]
        else:
            image_path = f"THlib/bullet/{texture_name}.png"  # 默认路径
        
        sprites[sprite_id] = {
            "id": sprite_id,
            "rect": [x, y, width, height],
            "center": [width // 2, height // 2],  # 默认中心点
            "radius": max(width, height) // 2,    # 默认碰撞半径
            "rotate": True,
            "scale": [scale_x, scale_y],
            "image_path": image_path
        }
    
    # 解析SetImageCenter
    set_center_pattern = re.compile(r"SetImageCenter\s*\('([^']+)',\s*(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\)")
    
    for match in set_center_pattern.finditer(lua_content):
        sprite_id, center_x, center_y = match.groups()
        center_x, center_y = map(float, [center_x, center_y])
        
        if sprite_id in sprites:
            sprites[sprite_id]["center"] = [center_x, center_y]
    
    # 解析for循环中的SetImageCenter（如第15-17行）
    loop_center_pattern = re.compile(r"for\s+i\s*=\s*(\d+),\s*(\d+)\s+do\s*\n\s*SetImageCenter\s*\('([^']+)'\s*\.\.\s*i,\s*(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\)\s*\n\s*end")
    loop_center_matches = loop_center_pattern.findall(lua_content)
    
    for match in loop_center_matches:
        start, end, base_id, center_x, center_y = match
        start = int(start)
        end = int(end)
        center_x = float(center_x)
        center_y = float(center_y)
        
        # 生成所有可能的精灵ID
        for i in range(start, end + 1):
            sprite_id = f"{base_id}{i}"
            if sprite_id in sprites:
                sprites[sprite_id]["center"] = [center_x, center_y]
    
    # 解析LoadAnimation
    animation_pattern = re.compile(r"LoadAnimation\s*\('([^']+)',\s*'([^']+)',\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)(?:,\s*(\d+(?:\.\d+)?))?(?:,\s*(\d+(?:\.\d+)?))?[^\)]*\)")
    
    for match in animation_pattern.finditer(lua_content):
        animation_id, texture_name, x, y, width, height, columns, frames, scale_x, scale_y = match.groups()
        x, y, width, height, columns, frames = map(int, [x, y, width, height, columns, frames])
        scale_x = float(scale_x) if scale_x else 1.0
        scale_y = float(scale_y) if scale_y else 1.0
        
        if texture_name in textures:
            image_path = textures[texture_name]
        else:
            image_path = f"THlib/bullet/{texture_name}.png"  # 默认路径
        
        # 动画暂时当作单个精灵处理，后续可以扩展支持动画
        sprites[animation_id] = {
            "id": animation_id,
            "rect": [x, y, width, height],
            "center": [width // 2, height // 2],  # 默认中心点
            "radius": max(width, height) // 2,    # 默认碰撞半径
            "rotate": True,
            "scale": [scale_x, scale_y],
            "image_path": image_path,
            "is_animation": True,
            "frames": frames,
            "columns": columns
        }
    
    return sprites


def save_sprite_configs(sprites, output_dir):
    """
    将精灵配置保存到JSON文件，按纹理分组
    """
    # 按纹理路径分组精灵
    textures_sprites = {}
    for sprite_id, sprite_data in sprites.items():
        image_path = sprite_data["image_path"]
        if image_path not in textures_sprites:
            textures_sprites[image_path] = []
        textures_sprites[image_path].append(sprite_data)
    
    # 保存每个纹理的配置文件
    for image_path, sprites_list in textures_sprites.items():
        # 提取文件名作为JSON文件名
        texture_name = os.path.splitext(os.path.basename(image_path))[0]
        json_file_name = f"{texture_name}.json"
        json_file_path = os.path.join(output_dir, json_file_name)
        
        # 构建JSON内容
        json_content = {
            "__image_filename": os.path.basename(image_path),
            "sprites": {}
        }
        
        for sprite in sprites_list:
            json_content["sprites"][sprite["id"]] = {
                "rect": sprite["rect"],
                "center": sprite["center"],
                "radius": sprite["radius"],
                "rotate": sprite["rotate"],
                "scale": sprite["scale"],
                "image_path": sprite["image_path"]
            }
        
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(json_content, f, indent=2, ensure_ascii=False)
        
        print(f"Saved {len(sprites_list)} sprites to {json_file_path}")


if __name__ == "__main__":
    lua_file_path = "c:\\Users\\m1573\\Documents\\Downloads\\pystg\\image\\bullet.lua"
    output_dir = "c:\\Users\\m1573\\Documents\\Downloads\\pystg\\image"
    
    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 解析Lua配置
    sprites = parse_lua_sprite_config(lua_file_path)
    
    # 保存为JSON
    save_sprite_configs(sprites, output_dir)
    
    print(f"\nTotal {len(sprites)} sprites parsed successfully!")

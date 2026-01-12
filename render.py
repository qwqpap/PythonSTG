
import pygame
import moderngl
import numpy as np
import sys
from bullet import BulletPool
from player import Player, check_collisions
from stage import StageManager, level_1
from sprite_manager import SpriteManager
import math

def main():
    # --- 1. 初始化 Pygame 并创建 OpenGL 窗口 ---
    pygame.init()
    # 基础尺寸（用于坐标计算）
    base_size = (384, 448)
    # 缩放因子
    scale_factor = 2
    # 计算实际窗口尺寸
    screen_size = (base_size[0] * scale_factor, base_size[1] * scale_factor)
    screen = pygame.display.set_mode(screen_size, pygame.OPENGL | pygame.DOUBLEBUF)
    
    
    
    # 获取 ModernGL 上下文
    ctx = moderngl.create_context()
    
    # 启用alpha混合
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    # --- 2. 初始化精灵管理器 ---
    sprite_manager = SpriteManager()
    
    # 加载精灵配置文件夹
    sprite_config_folder = "image"
    if not sprite_manager.load_sprite_config_folder(sprite_config_folder):
        print("Failed to load sprite configurations!")
        pygame.quit()
        sys.exit()
    
    # 设置默认精灵ID为star_small1
    default_sprite_id = 'star_small1' if 'star_small1' in sprite_manager.get_all_sprite_ids() else next(iter(sprite_manager.get_all_sprite_ids()), None)
    
    # --- 3. 加载纹理图片 ---
    # 加载所有在精灵配置中引用的纹理图片
    textures = {}
    texture_uv_map = {}  # 按纹理路径分组的UV映射
    
    # 为每个纹理创建纹理对象
    for texture_path in sprite_manager.get_all_texture_paths():
        img = pygame.image.load(texture_path).convert_alpha()
        texture = ctx.texture(img.get_size(), 4, pygame.image.tostring(img, "RGBA", True))
        texture.filter = (moderngl.NEAREST, moderngl.NEAREST)  # 像素风格
        textures[texture_path] = texture
        
        # 为当前纹理预计算所有精灵的UV坐标
        img_width, img_height = img.get_size()
        texture_uv_map[texture_path] = {}
        
        # 查找使用当前纹理的所有精灵
        for sprite_id in sprite_manager.get_all_sprite_ids():
            if sprite_manager.get_sprite_texture_path(sprite_id) == texture_path:
                sprite_data = sprite_manager.get_sprite(sprite_id)
                sprite_rect = sprite_data['rect']
                uv_left = sprite_rect[0] / img_width
                uv_top = sprite_rect[1] / img_height
                uv_right = (sprite_rect[0] + sprite_rect[2]) / img_width
                uv_bottom = (sprite_rect[1] + sprite_rect[3]) / img_height
                texture_uv_map[texture_path][sprite_id] = [uv_left, uv_top, uv_right, uv_bottom]
    
    # 如果没有加载到纹理，使用默认图片
    if not textures:
        bullet_texture_path = "image/bullet/bullet1.png"
        img = pygame.image.load(bullet_texture_path).convert_alpha()
        texture = ctx.texture(img.get_size(), 4, pygame.image.tostring(img, "RGBA", True))
        texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        textures[bullet_texture_path] = texture
        
        # 创建默认UV映射
        img_width, img_height = img.get_size()
        texture_uv_map[bullet_texture_path] = {}
        if default_sprite_id:
            sprite_data = sprite_manager.get_sprite(default_sprite_id)
            sprite_rect = sprite_data['rect']
            uv_left = sprite_rect[0] / img_width
            uv_top = sprite_rect[1] / img_height
            uv_right = (sprite_rect[0] + sprite_rect[2]) / img_width
            uv_bottom = (sprite_rect[1] + sprite_rect[3]) / img_height
            texture_uv_map[bullet_texture_path][default_sprite_id] = [uv_left, uv_top, uv_right, uv_bottom]
    
    # 创建一个综合的UV映射，方便查找
    sprite_uv_map = {}
    for texture_path, uv_map in texture_uv_map.items():
        for sprite_id, uv_coords in uv_map.items():
            sprite_uv_map[sprite_id] = uv_coords

    # --- 3. 编写着色器 (GLSL 语言) ---
    # 顶点着色器：接收位置并转换到裁剪空间，支持实例化偏移、颜色、角度和UV坐标
    vertex_shader = """
    #version 330
    in vec2 in_vert;
    in vec2 in_uv_base;
    in vec2 in_offset;
    in vec3 in_color;
    in float in_angle;
    in vec4 in_uv_offset;
    
    out vec3 v_color;
    out vec2 v_uv;
    
    void main() {
        // 计算旋转矩阵
        float s = sin(in_angle);
        float c = cos(in_angle);
        vec2 rotated = vec2(in_vert.x * c - in_vert.y * s, in_vert.x * s + in_vert.y * c);
        // 应用旋转和偏移
        vec2 position = rotated + in_offset;
        // 宽高比校正：384x448屏幕，宽高比为6:7，保持x轴[-1,1]，y轴需要乘以(384.0/448.0)
        position.y *= 384.0 / 448.0;
        gl_Position = vec4(position, 0.0, 1.0);
        v_color = in_color;
        // 使用实例化的UV坐标
        v_uv = in_uv_base * vec2(in_uv_offset.z - in_uv_offset.x, in_uv_offset.w - in_uv_offset.y) + in_uv_offset.xy;
    }
    """
    # 片元着色器：使用纹理采样和颜色
    fragment_shader = """
    #version 330
    uniform sampler2D u_texture;
    in vec3 v_color;
    in vec2 v_uv;
    out vec4 f_color;
    void main() {
        vec4 tex_color = texture(u_texture, v_uv);
        f_color = tex_color * vec4(v_color, 1.0);
    }
    """
    program = ctx.program(vertex_shader=vertex_shader, fragment_shader=fragment_shader)
    # 设置纹理采样器
    program['u_texture'].value = 0

    # --- 4. 准备顶点数据 (使用基础UV坐标) ---
    # 从精灵配置中获取默认精灵的尺寸信息
    default_sprite_size = [16, 16]  # 默认值
    if default_sprite_id:
        sprite_data = sprite_manager.get_sprite(default_sprite_id)
        default_sprite_size = [sprite_data['rect'][2], sprite_data['rect'][3]]
    
    # 计算精灵的半宽和半高（转换为归一化坐标）
    # 根据基础窗口尺寸计算缩放因子
    scale_factor = 2.0 / base_size[1]  # 基于基础高度的缩放因子
    width = default_sprite_size[0] * scale_factor
    height = default_sprite_size[1] * scale_factor
    half_width = width / 2.0
    half_height = height / 2.0
    
    # 创建顶点数据，使用基础UV坐标（0,0到1,1）
    vertices = np.array([
        # 第一个三角形
        -half_width,  half_height, 0.0, 0.0,    # 左上角
        -half_width, -half_height, 0.0, 1.0,  # 左下角
         half_width,  half_height, 1.0, 0.0,   # 右上角
        # 第二个三角形
         half_width,  half_height, 1.0, 0.0,   # 右上角
        -half_width, -half_height, 0.0, 1.0,  # 左下角
         half_width, -half_height, 1.0, 1.0, # 右下角
    ], dtype='f4')

    vbo = ctx.buffer(vertices.tobytes())

    # --- 4. 初始化玩家、子弹池和关卡管理器 ---
    player = Player()
    bullet_pool = BulletPool(max_bullets=50000)
    
    # 初始化关卡管理器
    # 创建一个简单的引擎包装器，包含子弹池和玩家
    class EngineWrapper:
        def __init__(self, bullet_pool, player):
            self.bullet_pool = bullet_pool
            self.player = player
    
    engine = EngineWrapper(bullet_pool, player)
    stage_manager = StageManager(engine)
    
    # 加载第一关
    level_1(stage_manager, bullet_pool, player)
    
    # 准备用于渲染的VBO
    # 位置VBO - 会动态更新
    instance_vbo = ctx.buffer(reserve=50000 * 2 * 4)  # 50000个子弹，每个2个float，每个float4字节
    # 颜色VBO - 会动态更新
    color_vbo = ctx.buffer(reserve=50000 * 3 * 4)    # 50000个子弹，每个3个float，每个float4字节
    # 角度VBO - 会动态更新
    angle_vbo = ctx.buffer(reserve=50000 * 1 * 4)     # 50000个子弹，每个1个float，每个float4字节
    # UV坐标VBO - 会动态更新
    uv_vbo = ctx.buffer(reserve=50000 * 4 * 4)        # 50000个子弹，每个4个float，每个float4字节

    # 绑定顶点数据和实例化数据到VAO
    # 使用ModernGL支持的实例化属性语法
    vao = ctx.vertex_array(program, 
                           [(vbo, '2f 2f', 'in_vert', 'in_uv_base'),
                            (instance_vbo, '2f/i', 'in_offset'),
                            (color_vbo, '3f/i', 'in_color'),
                            (angle_vbo, '1f/i', 'in_angle'),
                            (uv_vbo, '4f/i', 'in_uv_offset')])
    # 预创建玩家用的着色器和 VBO/VAO，避免每帧重新创建造成开销
    player_program = ctx.program(
        vertex_shader="""
        #version 330
        in vec2 in_vert;
        in vec3 in_color;
        
        out vec3 v_color;
        
        void main() {
            vec2 position = in_vert;
            // 宽高比校正：384x448屏幕，宽高比为6:7，保持x轴[-1,1]，y轴需要乘以(384.0/448.0)
            position.y *= 384.0 / 448.0;
            gl_Position = vec4(position, 0.0, 1.0);
            v_color = in_color;
        }
        """,
        fragment_shader="""
        #version 330
        in vec3 v_color;
        out vec4 f_color;
        
        void main() {
            f_color = vec4(v_color, 1.0);
        }
        """
    )

    # 为玩家准备可重写的 VBO（6 顶点），颜色固定为青色
    player_vbo = ctx.buffer(reserve=6 * 2 * 4)
    player_colors = np.array([
        0.0, 1.0, 1.0,
        0.0, 1.0, 1.0,
        0.0, 1.0, 1.0,
        0.0, 1.0, 1.0,
        0.0, 1.0, 1.0,
        0.0, 1.0, 1.0,
    ], dtype='f4')
    player_color_vbo = ctx.buffer(player_colors.tobytes())
    player_vao = ctx.vertex_array(player_program, 
                                  [(player_vbo, '2f', 'in_vert'),
                                   (player_color_vbo, '3f', 'in_color')])

    # 预创建判定点（圆圈）的着色器和 VBO/VAO
    circle_segments = 32
    circle_program = ctx.program(
        vertex_shader="""
        #version 330
        in vec2 in_vert;
        void main() {
            vec2 position = in_vert;
            // 宽高比校正：384x448屏幕，宽高比为6:7，保持x轴[-1,1]，y轴需要乘以(384.0/448.0)
            position.y *= 384.0 / 448.0;
            gl_Position = vec4(position, 0.0, 1.0);
        }
        """,
        fragment_shader="""
        #version 330
        out vec4 f_color;
        void main() {
            f_color = vec4(1.0, 1.0, 1.0, 1.0);
        }
        """
    )
    circle_vbo = ctx.buffer(reserve=(circle_segments + 1) * 2 * 4)
    circle_vao = ctx.vertex_array(circle_program, [(circle_vbo, '2f', 'in_vert')])

    # --- 4. 游戏主循环 ---
    clock = pygame.time.Clock()
    while True:
        # 计算时间步长
        dt = clock.tick(60) / 1000.0  # 转换为秒
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        # 获取键盘状态
        keys = pygame.key.get_pressed()

        # 更新玩家状态
        player.update(dt, keys)

        # 更新关卡管理器，处理弹幕事件
        stage_manager.update()

        # 更新子弹状态
        bullet_pool.update(dt)

        # 检测碰撞
        if player.invincible_timer <= 0:
            collided_bullet = check_collisions(player.pos, player.hit_radius, bullet_pool.data)
            if collided_bullet != -1:
                # 玩家受伤
                if player.take_damage():
                    print(f"Player hit! Lives left: {player.lives}")
                    # 标记碰撞的子弹为非活跃
                    bullet_pool.data['alive'][collided_bullet] = 0

        # 获取活跃子弹的位置、颜色、角度和精灵ID数据
        positions, colors, angles, sprite_ids = bullet_pool.get_active_bullets()
        active_count = len(positions)

        # 每10帧打印一次调试信息到控制台
        if pygame.time.get_ticks() % 100 < 16:  # 约每10帧打印一次
            print(f"Active bullets: {active_count}, Lives: {player.lives}, Focus: {player.is_focused}, Position: ({player.pos[0]:.2f}, {player.pos[1]:.2f}), Frame: {stage_manager.get_frame_count()}")

        # 渲染逻辑
        ctx.clear(0.1, 0.1, 0.1) # 深灰色背景
        
        # 按纹理路径对子弹进行分组
        bullets_by_texture = {}
        for i in range(active_count):
            sprite_id = sprite_ids[i]
            texture_path = sprite_manager.get_sprite_texture_path(sprite_id)
            
            # 如果没有找到纹理路径，使用默认纹理
            if not texture_path:
                texture_path = next(iter(textures.keys())) if textures else None
            
            if texture_path:
                if texture_path not in bullets_by_texture:
                    bullets_by_texture[texture_path] = []
                bullets_by_texture[texture_path].append(i)

        # 遍历每个纹理组，使用对应的纹理渲染
        for texture_path, bullet_indices in bullets_by_texture.items():
            if texture_path in textures:
                # 绑定当前纹理
                textures[texture_path].use(0)
                
                # 准备当前组子弹的数据
                group_size = len(bullet_indices)
                group_positions = positions[bullet_indices]
                group_colors = colors[bullet_indices]
                group_angles = angles[bullet_indices]
                group_sprite_ids = sprite_ids[bullet_indices]
                
                # 更新VBO数据
                instance_vbo.write(group_positions.tobytes())
                color_vbo.write(group_colors.tobytes())
                angle_vbo.write(group_angles.tobytes())
                
                # 为每个子弹准备UV坐标数据
                uv_data = np.zeros((group_size, 4), dtype='f4')
                for j, sprite_id in enumerate(group_sprite_ids):
                    # 如果sprite_id存在于sprite_uv_map中，则使用对应的UV坐标，否则使用默认精灵的UV坐标
                    if sprite_id in sprite_uv_map:
                        uv_data[j] = sprite_uv_map[sprite_id]
                    elif default_sprite_id and default_sprite_id in sprite_uv_map:
                        uv_data[j] = sprite_uv_map[default_sprite_id]
                    else:
                        # 如果都没有，则使用整个纹理
                        uv_data[j] = [0.0, 0.0, 1.0, 1.0]
                
                # 将UV坐标数据写入VBO
                uv_vbo.write(uv_data.tobytes())
                
                # 渲染当前组的子弹
                vao.render(moderngl.TRIANGLES, instances=group_size)

        # 绘制玩家（简化版，使用一个小方块）
        # 渲染玩家：只更新预分配的 VBO 数据并复用 VAO/Program
        player_size = 0.01 if player.is_focused else 0.02
        player_vertices = np.array([
            player.pos[0] - player_size, player.pos[1] + player_size,
            player.pos[0] - player_size, player.pos[1] - player_size,
            player.pos[0] + player_size, player.pos[1] + player_size,
            player.pos[0] + player_size, player.pos[1] + player_size,
            player.pos[0] - player_size, player.pos[1] - player_size,
            player.pos[0] + player_size, player.pos[1] - player_size,
        ], dtype='f4')
        player_vbo.write(player_vertices.tobytes())
        player_vao.render(moderngl.TRIANGLES)
        
        # 当按住Shift时，显示玩家的判定点
        if player.is_focused:
            # 更新并渲染判定点圆环（复用预创建的 VBO/VAO）
            circle_radius = player.hit_radius
            circle_vertices = []
            for i in range(circle_segments + 1):
                a = 2 * math.pi * i / circle_segments
                x = player.pos[0] + math.cos(a) * circle_radius
                y = player.pos[1] + math.sin(a) * circle_radius
                circle_vertices.extend([x, y])
            circle_vertices = np.array(circle_vertices, dtype='f4')
            circle_vbo.write(circle_vertices.tobytes())
            circle_vao.render(moderngl.LINE_STRIP)

        # 更新屏幕
        pygame.display.flip()

if __name__ == "__main__":
    main()
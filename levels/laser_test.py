"""
激光测试关卡 - 演示激光系统的使用
基于LuaSTG风格的三段式激光（头/身/尾）
"""
import math


def laser_test_level(stage_manager, bullet_pool, player, laser_pool):
    """
    激光测试关卡
    
    展示不同类型的激光：
    - laser1: 标准激光（头64、身128、尾64）
    - laser2: 细长激光（头5、身236、尾15）
    - laser3: 锥形激光（头127、身1、尾128）
    - laser4: 线条激光（头1、身254、尾1）
    
    Args:
        stage_manager: 关卡管理器
        bullet_pool: 子弹池
        player: 玩家
        laser_pool: 激光池
    """
    frame = 0
    
    while True:
        frame += 1
        
        # 每2秒发射一次直线激光（使用laser1纹理）
        if frame % 120 == 0:
            # 从屏幕顶部向下发射红色激光
            laser_pool.create_laser(
                x=192,  # 屏幕中心
                y=400,  # 顶部
                angle=270,  # 向下
                l1=30,   # 头部长度
                l2=200,  # 身体长度  
                l3=30,   # 尾部长度
                width=24,
                texture_id='laser1',
                color_index=1,  # 红色
                on_time=30,  # 30帧展开
            )
        
        # 每3秒发射旋转激光（使用laser2纹理，细长型）
        if frame % 180 == 60:
            # 从屏幕中心发射旋转的蓝色激光
            for i in range(8):
                angle = i * 45
                laser_pool.create_laser(
                    x=192,
                    y=224,
                    angle=angle,
                    l1=5,    # 短头部
                    l2=180,  # 长身体
                    l3=15,   # 短尾部
                    width=16,
                    texture_id='laser2',
                    color_index=9,  # 蓝色
                    on_time=20,
                )
        
        # 每4秒发射曲线激光
        if frame % 240 == 120:
            # 创建跟随敌人的曲线激光
            bent_laser = laser_pool.create_bent_laser(
                x=100,
                y=300,
                length=50,  # 路径点数量
                width=20,
                color_index=5,  # 绿色
                sample_rate=4,
                on_time=20,
            )
            
            # 让曲线激光跟随一个移动轨迹
            if bent_laser:
                start_frame = frame
                
                def create_updater(laser, start):
                    def update():
                        nonlocal laser, start
                        if not laser.alive:
                            return False
                        
                        elapsed = stage_manager.get_frame_count() - start
                        # 圆形轨迹
                        angle = elapsed * 0.05
                        new_x = 192 + math.cos(angle) * 100
                        new_y = 224 + math.sin(angle) * 100
                        laser.update_head(new_x, new_y)
                        
                        # 持续3秒后销毁
                        if elapsed > 180:
                            laser.kill()
                            return False
                        return True
                    return update
                
                # 添加协程来更新曲线激光位置
                stage_manager.add_coroutine(
                    lambda u=create_updater(bent_laser, start_frame): _bent_laser_updater(u)
                )
        
        # 每1秒：向玩家方向发射黄色追踪激光（使用laser3纹理，锥形）
        if frame % 60 == 0:
            # 计算指向玩家的角度
            dx = player.pos[0] - 192
            dy = player.pos[1] - 300
            angle_to_player = math.degrees(math.atan2(dy, dx))
            
            laser_pool.create_laser(
                x=192,
                y=300,
                angle=angle_to_player,
                l1=60,   # 长头部（锥形效果）
                l2=120,  # 身体
                l3=60,   # 长尾部
                width=20,
                texture_id='laser3',
                color_index=3,  # 黄色
                on_time=25,
            )
        
        yield


def _bent_laser_updater(update_func):
    """曲线激光更新协程"""
    while True:
        if not update_func():
            break
        yield

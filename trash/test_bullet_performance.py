import numpy as np
import time
from src.game.bullet import BulletPool

# 测试BulletPool性能
def test_bullet_performance():
    # 创建子弹池
    bullet_pool = BulletPool(max_bullets=50000)
    
    # 测试生成20000子弹
    print("开始生成20000子弹...")
    start_time = time.time()
    
    # 生成20000个子弹
    for i in range(20000):
        x = np.random.uniform(-1.0, 1.0)
        y = np.random.uniform(-1.0, 1.0)
        angle = np.random.uniform(0.0, 2 * np.pi)
        speed = np.random.uniform(0.1, 0.5)
        bullet_pool.spawn_bullet(x, y, angle, speed, sprite_id='bullet1')
    
    spawn_time = time.time() - start_time
    print(f"生成20000子弹耗时: {spawn_time:.3f}秒")
    
    # 测试更新性能
    print("开始测试更新性能...")
    dt = 1/60  # 60fps
    total_time = 0.0
    total_updates = 100  # 更新100次
    
    for i in range(total_updates):
        update_start = time.time()
        bullet_pool.update(dt)
        update_time = time.time() - update_start
        total_time += update_time
        
        # 每10次更新打印一次
        if (i + 1) % 10 == 0:
            # 获取活跃子弹数量
            positions, colors, angles, sprite_ids = bullet_pool.get_active_bullets()
            active_count = len(positions)
            print(f"更新 {i+1}/{total_updates}, 活跃子弹: {active_count}, 单次更新耗时: {update_time:.4f}秒")
    
    avg_update_time = total_time / total_updates
    print(f"平均更新耗时: {avg_update_time:.4f}秒, 平均FPS: {1/avg_update_time:.1f}")
    
    # 测试get_active_bullets性能
    print("\n测试get_active_bullets性能...")
    get_start = time.time()
    positions, colors, angles, sprite_ids = bullet_pool.get_active_bullets()
    get_time = time.time() - get_start
    print(f"获取活跃子弹耗时: {get_time:.4f}秒, 活跃子弹数量: {len(positions)}")

if __name__ == "__main__":
    test_bullet_performance()

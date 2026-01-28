"""
激光碰撞检测性能测试
测试Numba JIT优化的效果
"""
import sys
import os
import time
import math
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from game.laser import Laser, BentLaser, _check_laser_collision_jit, _check_bent_laser_collision_jit

try:
    from numba import jit
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False


def test_straight_laser_collision():
    """测试直线激光碰撞检测性能"""
    print("\n=== Straight Laser Collision Test ===")
    
    # 创建测试激光
    laser = Laser(
        x=192, y=224,
        angle=0,
        length=300,
        width=50,
        color_index=1
    )
    laser.current_width = 50
    laser.collidable = True
    laser.alive = True
    
    # 测试点
    test_points = []
    for i in range(100):
        x = 192 + i * 2
        y = 224 + (i % 10 - 5) * 5
        test_points.append((x, y))
    
    # 预热JIT
    angle_rad = math.radians(laser.angle)
    _check_laser_collision_jit(
        test_points[0][0], test_points[0][1], 5,
        laser.x, laser.y, angle_rad,
        laser.length, laser.current_width,
        laser.head_length, laser.tail_length
    )
    
    # 测试次数
    iterations = 100
    total_tests = len(test_points) * iterations
    
    start = time.time()
    collision_count = 0
    
    for _ in range(iterations):
        for px, py in test_points:
            if laser.check_collision(px, py, 5):
                collision_count += 1
    
    elapsed = time.time() - start
    
    print(f"Total collision checks: {total_tests:,}")
    print(f"Collisions detected: {collision_count:,}")
    print(f"Time elapsed: {elapsed:.4f}s")
    print(f"Average per check: {elapsed / total_tests * 1000000:.2f}µs")
    print(f"Checks per second: {total_tests / elapsed:,.0f}")


def test_bent_laser_collision():
    """测试曲线激光碰撞检测性能"""
    print("\n=== Bent Laser Collision Test ===")
    
    # 创建测试激光
    bent_laser = BentLaser(
        x=100, y=100,
        length=50,
        width=30,
        color_index=5
    )
    bent_laser.current_width = 30
    bent_laser.collidable = True
    bent_laser.alive = True
    
    # 初始化路径
    for i in range(bent_laser.length):
        bent_laser.path_x[i] = 100 + math.cos(i * 0.1) * 50
        bent_laser.path_y[i] = 100 + math.sin(i * 0.1) * 50
    
    # 测试点
    test_points = []
    for i in range(100):
        x = 100 + (i % 50 - 25)
        y = 100 + (i // 50 - 1) * 10
        test_points.append((x, y))
    
    # 预热JIT
    path_x_arr = np.array(bent_laser.path_x, dtype=np.float64)
    path_y_arr = np.array(bent_laser.path_y, dtype=np.float64)
    _check_bent_laser_collision_jit(
        test_points[0][0], test_points[0][1], 5,
        path_x_arr, path_y_arr,
        bent_laser.current_width,
        bent_laser.length
    )
    
    # 测试次数
    iterations = 100
    total_tests = len(test_points) * iterations
    
    start = time.time()
    collision_count = 0
    
    for _ in range(iterations):
        for px, py in test_points:
            if bent_laser.check_collision(px, py, 5):
                collision_count += 1
    
    elapsed = time.time() - start
    
    print(f"Total collision checks: {total_tests:,}")
    print(f"Collisions detected: {collision_count:,}")
    print(f"Time elapsed: {elapsed:.4f}s")
    print(f"Average per check: {elapsed / total_tests * 1000000:.2f}µs")
    print(f"Checks per second: {total_tests / elapsed:,.0f}")


def test_multiple_lasers():
    """测试多个激光的碰撞检测性能"""
    print("\n=== Multiple Lasers Collision Test ===")
    
    # 创建100个激光
    lasers = []
    for i in range(100):
        laser = Laser(
            x=192 + (i % 10) * 20,
            y=224 + (i // 10) * 20,
            angle=i * 3.6,
            length=150,
            width=20,
            color_index=(i % 16) + 1
        )
        laser.current_width = 20
        laser.collidable = True
        laser.alive = True
        lasers.append(laser)
    
    # 玩家位置
    player_x, player_y = 192, 224
    player_radius = 5
    
    iterations = 100
    total_checks = len(lasers) * iterations
    
    start = time.time()
    collision_count = 0
    
    for _ in range(iterations):
        for laser in lasers:
            if laser.check_collision(player_x, player_y, player_radius):
                collision_count += 1
    
    elapsed = time.time() - start
    
    print(f"Number of lasers: {len(lasers)}")
    print(f"Total collision checks: {total_checks:,}")
    print(f"Collisions detected: {collision_count:,}")
    print(f"Time elapsed: {elapsed:.4f}s")
    print(f"Average per laser check: {elapsed / total_checks * 1000000:.2f}µs")
    print(f"Checks per second: {total_checks / elapsed:,.0f}")


if __name__ == "__main__":
    print(f"Numba JIT Available: {HAS_NUMBA}")
    print("=" * 50)
    
    test_straight_laser_collision()
    test_bent_laser_collision()
    test_multiple_lasers()
    
    print("\n" + "=" * 50)
    print("Performance test completed!")
    print("\nNote: First run includes JIT compilation time.")
    print("Run again to see pure execution performance.")

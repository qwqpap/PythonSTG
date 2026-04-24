"""
幻符「十二人间里的癔症狂想曲」

机制：
- 12 个固定发射源排列成 4x3 宿舍格局
- 每个发射源行为各异，代表住了 12 个脾气完全不同的室友
- 弹幕相互叠加，制造极度混乱的视觉噪音
- 玩家需要在"全员开炮"中找到判定点的安全缝隙
"""

import random
import math
from src.game.stage.spellcard import SpellCard


# 12 个房间位置：4列 x 3行，模拟十二人间上下铺格局
# y 从下到上，x 对称分布
_ROOM_POSITIONS = [
    # 底层铺（y ≈ -0.05）
    (-0.75, -0.05), (-0.25, -0.05), (0.25, -0.05), (0.75, -0.05),
    # 中层（y ≈ 0.35）
    (-0.75,  0.35), (-0.25,  0.35), (0.25,  0.35), (0.75,  0.35),
    # 上层铺（y ≈ 0.70）
    (-0.75,  0.70), (-0.25,  0.70), (0.25,  0.70), (0.75,  0.70),
]

# 每个"室友"的配置：(发射间隔帧, 弹幕类型, 颜色, 发射模式, 速度基础, 额外参数)
# 模式: "circle" / "aimed" / "arc" / "random_burst" / "wave"
_ROOMMATES = [
    # 0号 - 红色圆圈慢弹（"我不管，我要开音响"）
    dict(interval=70, btype="ball_m",   color="red",     mode="circle",       count=10, speed=7.0),
    # 1号 - 蓝色自机狙（"谁进我床头区域谁死"）
    dict(interval=45, btype="knife",    color="blue",    mode="aimed",        count=3,  speed=14.0),
    # 2号 - 绿色米弹连射（"午夜12点开灯打游戏"）
    dict(interval=18, btype="grain_a",  color="green",   mode="random_burst", count=2,  speed=11.0),
    # 3号 - 黄色星弹扇形（"突然大声打电话"）
    dict(interval=80, btype="star_s",   color="yellow",  mode="arc",          count=8,  speed=9.0),
    # 4号 - 紫色方块旋转圈（"占着洗漱台不走"）
    dict(interval=55, btype="square",   color="purple",  mode="circle",       count=8,  speed=7.0),
    # 5号 - 白色椭圆密集（"全宿舍最早起床开始洗漱"）
    dict(interval=30, btype="oval",     color="white",   mode="random_burst", count=3,  speed=8.0),
    # 6号 - 橙色箭头冲刺（"手速惊人的键盘声"）
    dict(interval=35, btype="arrow_l",  color="orange",  mode="aimed",        count=2,  speed=17.0),
    # 7号 - 青色风筝弹扇形（"夜里不停换歌"）
    dict(interval=60, btype="kite",     color="cyan",    mode="arc",          count=6,  speed=10.0),
    # 8号 - 深红霉弹（"泡脚水味能穿墙"）
    dict(interval=25, btype="mildew",   color="darkred", mode="random_burst", count=4,  speed=8.0),
    # 9号 - 深蓝子弹随机扫射（"凌晨3点出去又回来"）
    dict(interval=22, btype="bullet",   color="darkblue", mode="random_burst", count=3, speed=13.0),
    # 10号 - 白色米弹旋臂（"天亮就睡着了"）
    dict(interval=90, btype="grain_a",  color="white",   mode="circle",       count=16, speed=6.5),
    # 11号 - 全随机（"神秘的大哥，从没见过正脸"）
    dict(interval=40, btype="star_m",   color="purple",  mode="chaos",        count=5,  speed=12.0),
]


class StarSpell2(SpellCard):
    """
    幻符「十二人间里的癔症狂想曲」
    """

    def __init__(self):
        super().__init__()
        self._timers = [0] * 12        # 每个房间的独立计时器
        self._angle_offsets = [        # 每个房间的旋转相位（产生错位感）
            random.uniform(0, 360) for _ in range(12)
        ]
        self._spin_rates = [           # 每个圆圈房间的自转速度
            random.uniform(0.5, 2.5) * (1 if i % 2 == 0 else -1)
            for i in range(12)
        ]

    async def run(self):
        # Boss 随机漫步在屏幕上方
        await self.boss.move_to(0.0, 0.88, duration=60)
        await self.wait(30)

        # 播报开始！
        self.play_se("tan01", volume=0.4)

        frame = 0
        while True:
            # 更新所有 12 个房间
            for i, (pos, cfg) in enumerate(zip(_ROOM_POSITIONS, _ROOMMATES)):
                rx, ry = pos
                self._timers[i] += 1

                if self._timers[i] < cfg["interval"]:
                    continue

                # 重置计时器（加点随机抖动避免所有房间同步）
                self._timers[i] = random.randint(-8, 0)

                mode = cfg["mode"]
                btype = cfg["btype"]
                color = cfg["color"]
                spd = max(6.0, cfg["speed"] + random.uniform(-1.5, 1.5))
                count = cfg["count"]

                if mode == "circle":
                    # 旋转圆圈
                    self._angle_offsets[i] += self._spin_rates[i]
                    for k in range(count):
                        angle = self._angle_offsets[i] + k * (360.0 / count)
                        self.fire(x=rx, y=ry, angle=angle, speed=spd,
                                  bullet_type=btype, color=color)

                elif mode == "aimed":
                    # 自机狙（带随机偏移）
                    base = self.angle_to_player(x=rx, y=ry)
                    spread = 20.0 / max(count, 1)
                    for k in range(count):
                        offset = (k - count // 2) * spread
                        self.fire(x=rx, y=ry, angle=base + offset, speed=spd,
                                  bullet_type=btype, color=color)

                elif mode == "arc":
                    # 随机朝向的扇形
                    center = random.uniform(-180, 180)
                    half = 70.0
                    for k in range(count):
                        angle = center - half + k * (2 * half / max(count - 1, 1))
                        self.fire(x=rx, y=ry, angle=angle, speed=spd,
                                  bullet_type=btype, color=color)

                elif mode == "random_burst":
                    # 全随机散射
                    for _ in range(count):
                        angle = random.uniform(0, 360)
                        self.fire(x=rx, y=ry, angle=angle,
                                  speed=spd * random.uniform(0.7, 1.3),
                                  bullet_type=btype, color=color)

                elif mode == "chaos":
                    # 11号"神秘大哥"：随机类型、颜色、角度，完全不讲道理
                    chaos_types = ["star_s", "grain_a", "ball_m", "knife", "mildew"]
                    chaos_colors = ["red", "blue", "green", "yellow", "cyan", "purple", "orange"]
                    for _ in range(count):
                        self.fire(
                            x=rx, y=ry,
                            angle=random.uniform(0, 360),
                            speed=random.uniform(6.0, 18.0),
                            bullet_type=random.choice(chaos_types),
                            color=random.choice(chaos_colors),
                        )

            # Boss 本体也随机漫游 + 自己也发一圈
            if frame % 180 == 0:
                # Boss 随机移动到上部的某个位置
                tx = random.uniform(-0.5, 0.5)
                ty = random.uniform(0.75, 0.92)
                # 非阻塞漫游（不 await，让 boss 自己飘）
                self.boss.x += (tx - self.boss.x) * 0.1

            if frame % 90 == 0:
                # Boss 发一圈代表混乱中心的弹幕
                self.play_se("tan00", volume=0.15)
                for k in range(8):
                    angle = frame * 3 + k * 45
                    self.fire(
                        angle=angle,
                        speed=8.0,
                        bullet_type="star_m",
                        color="white",
                    )

            frame += 1
            await self.wait(1)

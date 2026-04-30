"""
Stage 1 敌人
"""

import math
from src.game.stage.preset_enemy import PresetEnemy
from src.game.stage.enemy_script import EnemyScript


class SideFlyFairy(PresetEnemy):
    """
    沿给定方向匀速飞过屏幕、边飞边射自机狙的妖精。

    行为完全由参数决定，wave 负责确定出生位置和方向：
        - 出生位置：spawn 时传入的 x, y
        - fly_angle：飞行方向（度），默认 -60（右上方向左下飞入）
        - fly_speed：飞行速度，默认 0.008（归一化坐标/帧）
        - shoot_interval：每隔多少帧射一发自机狙
        - fly_duration：飞行总帧数，超出后敌人消失
    """
    preset_id = "enemy1"
    score = 200
    drops = {"power": 3, "point": 1}

    # 可在 wave 的 spawn_enemy_class 调用时通过子类覆盖
    fly_angle: float = -60          # 飞行方向（度），0=右，-90=上，180=左
    fly_speed: float = 0.008        # 每帧移动距离（归一化坐标）
    fly_duration: int = 300         # 飞行总帧数（超出后自动消失）
    shoot_interval: int = 15        # 每隔多少帧射一发自机狙
    bullet_speed: float = 45
    bullet_type: str = "ball_s"
    bullet_color: str = "red"

    async def run(self):
        rad = math.radians(self.fly_angle)
        dx = math.cos(rad) * self.fly_speed
        dy = math.sin(rad) * self.fly_speed

        for i in range(self.fly_duration):
            self.x += dx
            self.y += dy

            if i % self.shoot_interval == 0:
                self.fire_at_player(
                    speed=self.bullet_speed,
                    bullet_type=self.bullet_type,
                    color=self.bullet_color,
                )
            await self.wait(1)


class Stage1Wave1Fairy(PresetEnemy):
    """
    Stage_1_wave_1 专用妖精：
    1) 从侧上方入场并停在上方区域
    2) 发射一组“1 -> 3 -> 5”的自机狙扇形
    3) 直线向下离场
    """
    preset_id = "enemy1"
    score = 200
    drops = {"power": 1}

    stop_y: float = 0.72
    enter_duration: int = 45
    exit_duration: int = 95
    bullet_speed: float = 55
    bullet_type: str = "arrow_l"
    bullet_color: str = "darkred"

    def _fire_aimed_spread(self, count: int, spread_deg: float):
        if count <= 1:
            self.fire_at_player(
                speed=self.bullet_speed,
                bullet_type=self.bullet_type,
                color=self.bullet_color,
            )
            return

        center = self.angle_to_player()
        start = center - spread_deg / 2.0
        step = spread_deg / (count - 1)
        for i in range(count):
            self.fire(
                angle=start + step * i,
                speed=self.bullet_speed,
                bullet_type=self.bullet_type,
                color=self.bullet_color,
            )

    async def run(self):
        # 入场：停在上方偏侧位置
        await self.move_to(self.x, self.stop_y, duration=self.enter_duration)
        await self.wait(4)

        # 1 -> 3 -> 5（更快频率、更小角度偏移）
        self._fire_aimed_spread(count=1, spread_deg=0.0)
        await self.wait(4)
        self._fire_aimed_spread(count=3, spread_deg=9.0)
        await self.wait(4)
        self._fire_aimed_spread(count=5, spread_deg=18.0)
        await self.wait(6)

        # 离场：正下方退出
        await self.move_to(self.x, -1.2, duration=self.exit_duration)


class Stage1Wave2Leader(PresetEnemy):
    """
    Stage_1_wave_2 中央 enemy9：
    从上方缓慢下降，持续发射“偶数位 gun + mildew 散簇”。
    """
    preset_id = "enemy9"
    drops = {"power": 2, "point": 2}
    tough_hp: int = 200

    def __init__(self):
        super().__init__()
        self.hp = self.tough_hp

    stop_y: float = 0.86
    enter_duration: int = 80
    # 80(入场) + 10(停顿) + 650(持续发弹) = 740，
    # 对齐两侧最后一批幽灵离场时机：20 + 9*60 + 180 = 740
    descend_frames: int = 650
    descend_speed: float = 0.0018
    exit_duration: int = 90

    gun_interval: int = 18
    gun_arc_deg: float = 72.0
    gun_slots: int = 10
    gun_speed: float = 36

    mildew_interval: int = 52
    mildew_count: int = 6
    mildew_arc_deg: float = 30.0
    mildew_speed: float = 24

    def _fire_even_gun_fan(self):
        start = -self.gun_arc_deg / 2.0
        step = self.gun_arc_deg / (self.gun_slots - 1)
        for i in range(self.gun_slots):
            if i % 2 != 0:
                continue
            self.fire(
                angle=-90 + start + step * i,
                speed=self.gun_speed,
                bullet_type="gun",      # red -> gun_bullet1
                color="red",
            )

    def _fire_mildew_cluster(self):
        self.fire_arc(
            count=self.mildew_count,
            speed=self.mildew_speed,
            center_angle=-90 + math.sin(self.time * 0.08) * 10.0,
            arc_angle=self.mildew_arc_deg,
            bullet_type="mildew",      # red -> mildew1
            color="red",
        )

    async def run(self):
        await self.move_to(self.x, self.stop_y, duration=self.enter_duration)
        await self.wait(10)

        for i in range(self.descend_frames):
            self.y -= self.descend_speed
            if i % self.gun_interval == 0:
                self._fire_even_gun_fan()
            if i % self.mildew_interval == 12:
                self._fire_mildew_cluster()
            await self.wait(1)

        await self.move_to(self.x, -1.2, duration=self.exit_duration)


class Stage1Wave2GhostBase(EnemyScript):
    """
    Stage_1_wave_2 两侧幽灵：
    以正弦轨迹（S 型）下落，并发射快速单发自机狙。
    """
    hp = 28
    sprite = "Ghost1"
    score = 120
    hitbox_radius = 0.018
    drops = {"power": 1}

    path_phase: float = 0.0
    wave_amplitude: float = 0.22
    wave_frequency: float = 0.11
    descend_speed: float = 0.0085
    move_duration: int = 180

    shoot_interval: int = 22
    shot_speed: float = 28

    async def run(self):
        base_x = self.x
        for i in range(self.move_duration):
            self.y -= self.descend_speed
            self.x = base_x + self.wave_amplitude * math.sin(i * self.wave_frequency + self.path_phase)

            if i % self.shoot_interval == 0:
                self.fire_at_player(
                    speed=self.shot_speed,
                    bullet_type="arrow_l",  # red -> arrow_big2
                    color="red",
                )

            if self.y < -1.2:
                break
            await self.wait(1)


class Stage1Wave2GhostLeft(Stage1Wave2GhostBase):
    path_phase = 0.0


class Stage1Wave2GhostRight(Stage1Wave2GhostBase):
    path_phase = math.pi


class Stage1Wave3Orb(EnemyScript):
    """
    Stage_1_wave_3 下落幽灵球：
    - 从顶部下落，到达底部直接引爆
    - 被玩家击破也会引爆
    - 爆炸为 3 次环形 mildew 烟花（左旋/右旋交替）
    """
    hp = 1
    sprite = "enemy_orb_0"
    score = 90
    hitbox_radius = 0.02
    drops = {"power": 1}

    fall_speed: float = 0.0112
    bottom_y: float = -1.0
    ring_count: int = 20
    burst_count: int = 3
    burst_interval_frames: int = 8
    accel_duration_seconds: float = 0.20
    start_speed: float = 9.5
    cruise_speed: float = 23.0
    angular_speed_deg: float = 13.0
    burst_spin_signs = (1.0, -1.0, 1.0)  # 左旋 -> 右旋 -> 左旋

    def __init__(self):
        super().__init__()
        self._exploded = False

    def _spawn_polar_cross_bullet(self, angle_deg: float, delay_frames: int, spin_sign: float):
        if not self.ctx:
            return

        center_x = float(self.x)
        center_y = float(self.y)
        theta_deg = angle_deg
        start_speed_pf = self.start_speed / 60.0   # 先慢
        cruise_speed_pf = self.cruise_speed / 60.0  # 后快并保持匀速
        ang_vel_deg = self.angular_speed_deg * spin_sign
        bullet_color = "red" if spin_sign < 0 else "darkorange"  # mildew1 / mildew10

        def _to_cruise(pool_obj, event, cx=center_x, cy=center_y, omega=ang_vel_deg, cruise=cruise_speed_pf, color=bullet_color):
            dx = float(event.x) - cx
            dy = float(event.y) - cy
            radius = math.sqrt(dx * dx + dy * dy)
            phase_deg = math.degrees(math.atan2(dy, dx))
            self.ctx.create_polar_bullet(
                center=(cx, cy),
                orbit_radius=radius,
                theta=phase_deg,
                radial_speed=cruise,
                angular_velocity=omega,
                bullet_type="mildew",
                color=color,
            )

        self.ctx.create_polar_bullet(
            center=(center_x, center_y),
            orbit_radius=0.0,
            theta=theta_deg,
            radial_speed=start_speed_pf,
            angular_velocity=ang_vel_deg,
            bullet_type="mildew",
            color=bullet_color,
            delay=delay_frames,
            max_lifetime=self.accel_duration_seconds,
            on_death=_to_cruise,
        )

    def _explode_firework(self):
        if self._exploded:
            return
        self._exploded = True

        step = 360.0 / self.ring_count
        for burst_idx in range(self.burst_count):
            delay = burst_idx * self.burst_interval_frames
            phase = burst_idx * 6.0
            spin_sign = self.burst_spin_signs[burst_idx % len(self.burst_spin_signs)]
            for i in range(self.ring_count):
                self._spawn_polar_cross_bullet(
                    angle_deg=phase + i * step,
                    delay_frames=delay,
                    spin_sign=spin_sign,
                )

    def _on_death(self):
        self._explode_firework()
        super()._on_death()

    async def run(self):
        while True:
            self.y -= self.fall_speed
            if self.y <= self.bottom_y:
                self.kill()
                return
            await self.wait(1)


class Stage1Wave4SideSniperEnemy3(PresetEnemy):
    """
    Stage_1_wave_4 侧翼 enemy3：
    缓慢自机狙（ellipse1），若玩家不击破则在 wave 末自动撤离。
    """
    preset_id = "enemy3"
    drops = {"power": 1}
    score = 140

    enter_duration: int = 50
    stay_frames: int = 1800
    shoot_interval: int = 72
    shot_speed: float = 12.0
    exit_duration: int = 56

    async def run(self):
        side = -1.0 if self.x < 0.0 else 1.0
        target_x = side * 0.78
        target_y = min(0.82, max(0.44, self.y - 0.14))
        self.force_leave = False

        await self.move_to(target_x, target_y, duration=self.enter_duration)
        await self.wait(8)

        for i in range(self.stay_frames):
            if self.force_leave:
                break
            if i % self.shoot_interval == 0:
                self.fire_at_player(
                    speed=self.shot_speed,
                    bullet_type="ellipse",  # red -> ellipse1
                    color="red",
                )
            await self.wait(1)

        # wave 结束后自动飞出
        await self.move_to(side * 1.24, 1.20, duration=self.exit_duration)


class Stage1Wave4FlowerEnemy14(EnemyScript):
    """
    Stage_1_wave_4 两侧 enemy14：
    发射不连续开花圈（gun_bullet14），并持续改变缺口相位。
    """
    hp = 150
    sprite = "enemy14"
    score = 320
    hitbox_radius = 0.03
    drops = {"power": 2, "point": 1}

    enter_duration: int = 55
    attack_duration_frames: int = 480   # 8 秒
    fire_interval: int = 46
    bullet_speed: float = 20.0

    sector_count: int = 12
    phase_shift_deg: float = 0.0
    phase_step_deg: float = 11.0

    def _fire_segmented_ring(self):
        sector_width = 360.0 / self.sector_count
        # 每两段有弹、两段留空：形成“长弹段 + 长空段”
        for sector in range(self.sector_count):
            if ((sector // 2) % 2) == 1:
                continue

            center = self.phase_shift_deg + sector * sector_width
            for offset in (-10.0, -3.0, 3.0, 10.0):
                self.fire(
                    angle=center + offset,
                    speed=self.bullet_speed,
                    bullet_type="gun",       # darkcyan -> gun_bullet14
                    color="darkcyan",
                )

    async def run(self):
        target_x = -0.56 if self.x < 0.0 else 0.56
        await self.move_to(target_x, 0.68, duration=self.enter_duration)
        await self.wait(6)

        rotate_dir = 1.0 if self.x < 0.0 else -1.0
        for i in range(self.attack_duration_frames):
            if i % self.fire_interval == 0:
                self._fire_segmented_ring()
                self.phase_shift_deg += self.phase_step_deg * rotate_dir
            await self.wait(1)

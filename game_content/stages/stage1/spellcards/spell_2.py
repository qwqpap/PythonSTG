"""
光符「反射在井盖上的矿院幻影」
 - 桑尼在屏幕中放置若干枚缓慢公转 + 自转的"井盖"。
 - 每轮向井盖发射同数量的高速入射弹，碰到井盖即消失，
   并按照物理反射定律喷射出一扇反射流弹。
"""

import math
import random

from src.game.stage.spellcard import SpellCard
from src.content_api import TAG_BOMB_PROTECTED_MIRROR


class SunnySpell1(SpellCard):
    """光符「反射在井盖上的矿院幻影」"""

    name = "光符「反射在井盖上的矿院幻影」"
    DEBUG_BOOKMARK = True

    # ===== 井盖参数 =====
    mirror_count: int = 4
    mirror_orbit_radius: float = 0.48
    mirror_center_x: float = 0.0
    mirror_center_y: float = 0.50
    mirror_orbit_deg_per_frame: float = 0.35     # 公转角速度（度/帧）
    mirror_self_spin_deg_per_frame: float = 1.1  # 法线自转角速度（度/帧）

    # 井盖外观（堆叠子弹可视化）
    disc_outer_radius: float = 0.055
    disc_outer_count: int = 8
    disc_inner_radius: float = 0.028
    disc_inner_count: int = 4

    # ===== 入射弹参数 =====
    shot_cycle_interval: int = 78         # 每轮节拍（帧）
    shot_burst_delay: int = 5             # 一轮内每发间隔
    shot_speed: float = 66.0              # 入射速度（极快）
    shot_hit_distance: float = 0.060      # 命中判定半径

    # ===== 反射弹参数 =====
    reflect_count: int = 13               # 单次反射出的子弹数
    reflect_spread_deg: float = 86.0      # 扇形角跨度
    reflect_speed_base: float = 6.9
    reflect_speed_step: float = 0.66
    reflect_inner_extra: int = 6          # 额外补的小圆环
    reflect_inner_speed: float = 4.8

    async def setup(self):
        # Boss 落位到中上方作为发射点
        await self.boss.move_to(0.0, 0.14, duration=60)

    # ---------------------------------------------------------------
    # 井盖（反射镜）
    # ---------------------------------------------------------------

    def _mirror_pos(self, i: int, t: int):
        """返回井盖 i 的世界坐标（t 为当前帧）"""
        base = i * (360.0 / self.mirror_count)
        ang = math.radians(base + self.mirror_orbit_deg_per_frame * t)
        x = self.mirror_center_x + self.mirror_orbit_radius * math.cos(ang)
        y = self.mirror_center_y + self.mirror_orbit_radius * 0.55 * math.sin(ang)
        return x, y

    def _mirror_normal_deg(self, i: int, t: int) -> float:
        """返回井盖 i 的法线方向（度）"""
        base = i * (360.0 / self.mirror_count)
        return base + self.mirror_self_spin_deg_per_frame * t

    def _build_disc(self, x: float, y: float, normal_deg: float) -> list[int]:
        """在 (x, y) 堆叠子弹做出一枚井盖；返回涉及到的子弹索引列表"""
        idxs: list[int] = []

        # 外圈：深蓝小球构成圆盘边缘
        for k in range(self.disc_outer_count):
            ang = math.radians(k * (360.0 / self.disc_outer_count) + normal_deg)
            px = x + self.disc_outer_radius * math.cos(ang)
            py = y + self.disc_outer_radius * math.sin(ang)
            idx = self.fire(
                x=px, y=py, angle=0.0, speed=0.0,
                bullet_type="ball_s", color="darkblue",
                friction=0.0,
                tag=TAG_BOMB_PROTECTED_MIRROR,
            )
            if idx >= 0:
                idxs.append(idx)

        # 内圈：青色小球
        for k in range(self.disc_inner_count):
            ang = math.radians(k * (360.0 / self.disc_inner_count) + normal_deg * 1.5)
            px = x + self.disc_inner_radius * math.cos(ang)
            py = y + self.disc_inner_radius * math.sin(ang)
            idx = self.fire(
                x=px, y=py, angle=0.0, speed=0.0,
                bullet_type="ball_s", color="cyan",
                tag=TAG_BOMB_PROTECTED_MIRROR,
            )
            if idx >= 0:
                idxs.append(idx)

        # 中心：白色中弹 + 沿法线方向的两颗"指示灯"
        idx_c = self.fire(x=x, y=y, angle=0.0, speed=0.0,
                          bullet_type="ball_m", color="white",
                          tag=TAG_BOMB_PROTECTED_MIRROR)
        if idx_c >= 0:
            idxs.append(idx_c)

        nr = math.radians(normal_deg)
        for sign in (+1, -1):
            px = x + sign * self.disc_outer_radius * 0.72 * math.cos(nr)
            py = y + sign * self.disc_outer_radius * 0.72 * math.sin(nr)
            idx = self.fire(x=px, y=py, angle=0.0, speed=0.0,
                            bullet_type="ball_s", color="yellow",
                            tag=TAG_BOMB_PROTECTED_MIRROR)
            if idx >= 0:
                idxs.append(idx)

        return idxs

    def _refresh_disc_positions(self, disc_idxs: list[int], i: int):
        """每帧把井盖 i 的所有堆叠子弹搬到新位置"""
        pool = getattr(self.ctx, "bullet_pool", None)
        if pool is None or not disc_idxs:
            return

        cx, cy = self._mirror_pos(i, self.time)
        n_deg = self._mirror_normal_deg(i, self.time)

        positions: list[tuple[float, float]] = []

        for k in range(self.disc_outer_count):
            ang = math.radians(k * (360.0 / self.disc_outer_count) + n_deg)
            positions.append((cx + self.disc_outer_radius * math.cos(ang),
                              cy + self.disc_outer_radius * math.sin(ang)))

        for k in range(self.disc_inner_count):
            ang = math.radians(k * (360.0 / self.disc_inner_count) + n_deg * 1.5)
            positions.append((cx + self.disc_inner_radius * math.cos(ang),
                              cy + self.disc_inner_radius * math.sin(ang)))

        positions.append((cx, cy))

        nr = math.radians(n_deg)
        for sign in (+1, -1):
            positions.append((cx + sign * self.disc_outer_radius * 0.72 * math.cos(nr),
                              cy + sign * self.disc_outer_radius * 0.72 * math.sin(nr)))

        alive = pool.data["alive"]
        pos = pool.data["pos"]
        for bidx, (px, py) in zip(disc_idxs, positions):
            if 0 <= bidx < len(alive) and alive[bidx] != 0:
                pos[bidx][0] = px
                pos[bidx][1] = py

    # ---------------------------------------------------------------
    # 入射 & 反射
    # ---------------------------------------------------------------

    def _fire_incident(self, mirror_i: int):
        """从 Boss 向井盖 mirror_i 发一枚高速入射弹"""
        cx, cy = self._mirror_pos(mirror_i, self.time)
        dx = cx - self.boss.x
        dy = cy - self.boss.y
        ang = math.degrees(math.atan2(dy, dx))

        idx = self.fire(
            x=self.boss.x, y=self.boss.y,
            angle=ang, speed=self.shot_speed,
            bullet_type="ball_s", color="yellow",
        )
        return idx, ang

    def _check_and_reflect(self, shots: list[dict]):
        """遍历存活中的入射弹，检测是否命中井盖；命中则删除入射 + 喷反射扇。"""
        pool = getattr(self.ctx, "bullet_pool", None)
        if pool is None:
            return

        alive = pool.data["alive"]
        pos = pool.data["pos"]
        r2 = self.shot_hit_distance * self.shot_hit_distance

        survivors: list[dict] = []
        for shot in shots:
            idx = shot["idx"]
            if idx < 0 or idx >= len(alive) or alive[idx] == 0:
                continue

            sx = float(pos[idx][0])
            sy = float(pos[idx][1])

            hit = None
            for i in range(self.mirror_count):
                mx, my = self._mirror_pos(i, self.time)
                if (sx - mx) ** 2 + (sy - my) ** 2 <= r2:
                    hit = (i, mx, my)
                    break

            if hit is None:
                # 飞出边界直接丢弃
                if abs(sx) > 1.3 or sy < -0.2 or sy > 1.3:
                    self.ctx.remove_bullet(idx)
                    continue
                survivors.append(shot)
                continue

            i, mx, my = hit
            self.ctx.remove_bullet(idx)
            self._spawn_reflection(i, mx, my, shot["angle"])

        shots[:] = survivors

    def _spawn_reflection(self, mirror_i: int, x: float, y: float, incident_deg: float):
        """按反射定律在 (x,y) 喷射一扇子弹。"""
        normal_deg = self._mirror_normal_deg(mirror_i, self.time)
        # 反射方向：θ_out = 2*normal - θ_in + 180°
        reflect_center = 2.0 * normal_deg - incident_deg + 180.0

        pass

        spread = self.reflect_spread_deg
        count = self.reflect_count
        if count > 1:
            start = reflect_center - spread * 0.5
            step = spread / (count - 1)
        else:
            start = reflect_center
            step = 0.0

        for k in range(count):
            ang = start + step * k
            # 速度随位置渐变，两端快中间慢
            spd = self.reflect_speed_base + abs(k - (count - 1) / 2.0) * self.reflect_speed_step
            color = ("yellow", "orange", "red")[k % 3]
            btype = "grain_c" if k % 2 == 0 else "grain_a"
            self.fire(
                x=x, y=y,
                angle=ang, speed=spd,
                bullet_type=btype, color=color,
            )

        # 再加一圈内环慢速弹，制造"碎屑"感
        for k in range(self.reflect_inner_extra):
            ang = reflect_center + (k - (self.reflect_inner_extra - 1) / 2.0) * 14.0 \
                  + random.uniform(-4.0, 4.0)
            self.fire(
                x=x, y=y,
                angle=ang,
                speed=self.reflect_inner_speed + random.uniform(-0.2, 0.3),
                bullet_type="grain_c", color="white",
            )

    # ---------------------------------------------------------------
    # 主循环
    # ---------------------------------------------------------------

    async def run(self):
        # 先放置井盖（堆叠弹可视化），记录所有索引
        disc_bullets: list[list[int]] = []
        for i in range(self.mirror_count):
            cx, cy = self._mirror_pos(i, 0)
            n_deg = self._mirror_normal_deg(i, 0)
            disc_bullets.append(self._build_disc(cx, cy, n_deg))

        pending_shots: list[dict] = []
        # 本轮待发射队列：(fire_frame, mirror_i)
        burst_queue: list[tuple[int, int]] = []

        while True:
            # 每轮开始：为每个井盖安排一发入射弹，按 burst_delay 错开
            if self.time % self.shot_cycle_interval == 0:
                order = list(range(self.mirror_count))
                random.shuffle(order)
                for k, mi in enumerate(order):
                    burst_queue.append((self.time + k * self.shot_burst_delay, mi))

            # 触发到时间的入射弹
            still_queue: list[tuple[int, int]] = []
            for fire_frame, mi in burst_queue:
                if self.time >= fire_frame:
                    idx, ang = self._fire_incident(mi)
                    if idx >= 0:
                        pending_shots.append({"idx": idx, "angle": ang})
                        pass
                else:
                    still_queue.append((fire_frame, mi))
            burst_queue = still_queue

            # 更新井盖可视化位置
            for i, idxs in enumerate(disc_bullets):
                self._refresh_disc_positions(idxs, i)

            # 检测命中 & 反射
            self._check_and_reflect(pending_shots)

            await self.wait(1)

    # ---------------------------------------------------------------
    # 结束清理
    # ---------------------------------------------------------------

    def _on_timeout(self):
        self.clear_bullets()

    def _on_defeated(self):
        self.clear_bullets()


spellcard = SunnySpell1

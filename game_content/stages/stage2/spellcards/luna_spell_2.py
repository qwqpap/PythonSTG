"""
线符「昌平列车」

背景：昌平线地铁路线图 (cpline.png)
机制：
  - 6 列列车同时行驶（3 北→南，3 南→北），均匀分布在路径上
  - 每列用一颗 ellipse 子弹代表，每帧重新定位（视觉上在线路上移动）
  - 每隔数帧向后散射少量 grain_a 弹幕（模拟乘客涌出）
  - 低频自机狙保持压力

坐标说明：
  游戏坐标 x ∈ [-1,1]，y 约 ∈ [-1,1]（0=屏幕中央，-0.8=玩家底部）。
  子弹 shader 对 y 乘以 y_scale = 384/448。
  背景2D层不做此缩放，所以要对齐两者需要：
    game_x = (img_px_x / 1081) * 2 - 1
    game_y = (1 - 2 * img_px_y / 1786) * (448 / 384)
"""

import math
import random
import os
from src.game.stage.spellcard import SpellCard
from src.content_api import TAG_BOMB_PROTECTED_TRAIN

# ── 校正因子 ────────────────────────────────────────
_Y_CORR = 448 / 384   # 1.1667：背景→子弹坐标系换算


def _px(ix, iy):
    """图片像素 (ix, iy) → 游戏坐标 (game_x, game_y)"""
    gx = (ix / 1081) * 2 - 1
    gy = (1 - 2 * iy / 1786) * _Y_CORR
    return gx, gy


# ──────────────────────────────────────────────────────────
#  昌平线关键站点（路径折线）
#  像素坐标由程序扫描 cpline.png（1081×1786）有色像素精确得到
# ──────────────────────────────────────────────────────────
_CPLINE_NS = [
    # 上部曲线：十三陵景区 → 昌平区域
    _px(342,  150),   # 十三陵景区（左侧起点）
    _px(475,  165),   # 进入竖直段
    _px(475,  200),   # 昌平西山口
    _px(475,  240),   # 昌平
    _px(475,  275),   # 昌平东关/北邵洼
    # 右转弯 → 进入长直段
    _px(485,  308),   # 开始右转
    _px(600,  320),   # 弯道中段
    _px(703,  332),   # 完成右转，进入长直段
    # 长直段（x≈703，由北向南）
    _px(703,  380),   # 南邵
    _px(703,  450),   # 沙河高教园
    _px(703,  510),   # 沙河
    _px(703,  565),   # 巩华城
    _px(703,  630),   # 朱辛庄
    _px(703,  695),   # 生命科学园
    _px(703,  760),   # 继续南行
    # U 形转弯 → 向左
    _px(575,  800),   # 开始 U 转
    _px(447,  815),   # 完成 U 转
    # 第二竖直段（x≈447）
    _px(447,  855),   # 西二旗
    _px(447,  910),   # 清河站
    _px(447,  965),   # 清河小营桥
    _px(447, 1020),   # 学清路
    # 第二右转弯 → 进入末段
    _px(510, 1070),   # 开始右转
    _px(576, 1090),   # 完成右转
    # 末段竖直（x≈576）
    _px(576, 1200),   # 六道口/学院桥
    _px(576, 1380),   # 西土城/蔚门桥
    _px(576, 1560),   # 学院南路（终点）
]
_CPLINE_SN = list(reversed(_CPLINE_NS))


def _build_path(waypoints):
    dists = [0.0]
    for i in range(1, len(waypoints)):
        dx = waypoints[i][0] - waypoints[i-1][0]
        dy = waypoints[i][1] - waypoints[i-1][1]
        dists.append(dists[-1] + math.sqrt(dx*dx + dy*dy))
    return dists, dists[-1]


def _sample(waypoints, dists, total, t):
    """路径参数 t∈[0,1] → (x, y, dir_x, dir_y) 或 None"""
    if t < 0 or t >= 1.0:
        return None
    target = t * total
    for i in range(len(waypoints) - 1):
        if dists[i+1] >= target:
            seg = max(dists[i+1] - dists[i], 1e-9)
            r = (target - dists[i]) / seg
            p0, p1 = waypoints[i], waypoints[i+1]
            x = p0[0] + (p1[0] - p0[0]) * r
            y = p0[1] + (p1[1] - p0[1]) * r
            return x, y, (p1[0]-p0[0])/seg, (p1[1]-p0[1])/seg
    return None


_NS_DISTS, _NS_TOTAL = _build_path(_CPLINE_NS)
_SN_DISTS, _SN_TOTAL = _build_path(_CPLINE_SN)


class LunaSpell2(SpellCard):
    """线符「昌平列车」"""

    TRAIN_COUNT    = 3     # 每方向列车数
    TRAIN_FRAMES   = 420   # 走完全程的帧数（7 秒）
    EMIT_INTERVAL  = 3     # 【已缩短】高频散发粒子
    CROWD_COUNT    = 1     # 每次散发的粒子数量
    AIM_INTERVAL   = 90    # 每几帧自机狙

    async def setup(self):
        bg = self.ctx.background_renderer
        if bg is not None:
            try:
                from src.game.background_render.background_renderer import (
                    BackgroundLayer, BlendMode
                )
                bg.data_background = None
                bg.procedural_background = None
                bg.layers.clear()
                cpline_path = os.path.join(
                    "game_content", "stages", "stage2", "back", "cpline.png"
                )
                layer = BackgroundLayer(
                    texture_path=cpline_path,
                    z_order=0,
                    scroll_speed=(0.0, 0.0),
                    tile_repeat=(1, 1),
                    alpha=0.80,
                    blend_mode=BlendMode.NORMAL,
                )
                if not bg.add_layer(layer):
                    print("[LunaSpell2] 背景加载失败")
            except Exception as e:
                print(f"[LunaSpell2] 背景异常: {e}")

        # Boss 移到上方（约在十三陵景区/昌平西山口附近）
        await self.boss.move_to(-0.15, 0.92, duration=90)

    async def run(self):
        SPEED = 1.0 / self.TRAIN_FRAMES

        trains = []
        for k in range(self.TRAIN_COUNT):
            offset = k / self.TRAIN_COUNT
            # 统一使用 _CPLINE_NS，通过 t_dir 在同一条线上往返跑
            trains.append({
                'wp': _CPLINE_NS, 'dists': _NS_DISTS, 'total': _NS_TOTAL,
                't': offset, 'speed': SPEED, 't_dir': 1.0,
                'head': None, 'color': 'red', 'crowd_color': 'orange',
            })
            trains.append({
                'wp': _CPLINE_NS, 'dists': _NS_DISTS, 'total': _NS_TOTAL,
                't': offset, 'speed': SPEED, 't_dir': -1.0,
                'head': None, 'color': 'blue', 'crowd_color': 'cyan',
            })

        frame = 0
        while True:
            player   = self.ctx.get_player()
            px       = player.x if player else 0.0
            py       = player.y if player else -0.8
            emit_now = (frame % self.EMIT_INTERVAL == 0)
            aim_now  = (frame % self.AIM_INTERVAL  == 0)

            for train in trains:
                result = _sample(
                    train['wp'], train['dists'], train['total'], train['t']
                )
                if result is None:
                    continue

                x, y, dx, dy = result
                # 由于可能反向行驶，实际运动朝向要乘上 t_dir
                actual_dx = dx * train['t_dir']
                actual_dy = dy * train['t_dir']

                # 更新列车头子弹（删旧建新）
                if train['head'] is not None:
                    self.ctx.remove_bullet(train['head'])
                render_a = math.degrees(math.atan2(actual_dy, actual_dx))
                train['head'] = self.fire(
                    x=x, y=y,
                    angle=0, speed=0,
                    bullet_type='ellipse',
                    color=train['color'],
                    render_angle=render_a,
                    tag=TAG_BOMB_PROTECTED_TRAIN,
                )

                # 高频向后方散发类似粒子火花一样的极速弹幕
                if emit_now:
                    back = math.degrees(math.atan2(-actual_dy, -actual_dx))
                    for _ in range(self.CROWD_COUNT):
                        self.fire(
                            x=x + random.uniform(-0.02, 0.02),
                            y=y + random.uniform(-0.02, 0.02),
                            angle=back + random.uniform(-65, 65), # 往后方宽扇形绽开
                            speed=random.uniform(7.0, 16.0),      # 非常极速
                            bullet_type='grain_b',                # 使用具有视觉拉影/火花感的变种
                            color=train['crowd_color'],
                        )

                # 自机狙
                if aim_now:
                    aim = math.degrees(math.atan2(py - y, px - x))
                    self.fire(
                        x=x, y=y,
                        angle=aim,
                        speed=4.0,
                        bullet_type='ball_s',
                        color='yellow',
                    )

                # 更新运动逻辑，往返跑(触碰两端反弹)
                train['t'] += train['speed'] * train['t_dir']
                if train['t'] >= 1.0:
                    train['t'] = 0.999
                    train['t_dir'] = -1.0
                elif train['t'] <= 0.0:
                    train['t'] = 0.001
                    train['t_dir'] = 1.0

            # Boss 沿上方小幅摆动
            self.boss.x = -0.15 + math.sin(frame * 0.018) * 0.10

            frame += 1
            await self.wait(1)

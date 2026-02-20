"""
僚机（Option）实体
由 PlayerScript 管理创建/销毁/位置更新
支持独立动画
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple, List


@dataclass
class OptionEntity:
    """单个僚机实体"""
    anim_id: str = ""                           # 引用 config.bullet_anims / option_anims 中的动画名
    offset_x: float = 0.0                       # 非聚焦时相对玩家偏移
    offset_y: float = 0.0
    focused_offset_x: float = 0.0               # 聚焦时相对玩家偏移
    focused_offset_y: float = 0.0
    current_x: float = 0.0                      # 当前世界坐标
    current_y: float = 0.0
    anim_timer: float = 0.0                     # 动画计时器
    current_frame: int = 0                      # 当前帧索引
    render_size_px: float = 16.0                # 渲染尺寸（像素）
    active: bool = True

    def update_position(self, player_x: float, player_y: float,
                        is_focused: bool, dt: float, lerp_speed: float = 10.0):
        """平滑更新位置"""
        if is_focused:
            target_x = player_x + self.focused_offset_x
            target_y = player_y + self.focused_offset_y
        else:
            target_x = player_x + self.offset_x
            target_y = player_y + self.offset_y

        t = min(1.0, lerp_speed * dt)
        self.current_x += (target_x - self.current_x) * t
        self.current_y += (target_y - self.current_y) * t

    def update_animation(self, dt: float, frame_count: int,
                         frame_duration: float, loop: bool = True):
        """更新动画帧"""
        if frame_count <= 0:
            return
        self.anim_timer += dt
        if frame_duration > 0:
            idx = int(self.anim_timer / frame_duration)
            if loop:
                self.current_frame = idx % frame_count
            else:
                self.current_frame = min(idx, frame_count - 1)


class OptionManager:
    """管理所有僚机实体的位置更新和动画"""

    def __init__(self):
        self.options: List[OptionEntity] = []

    def add(self, option: OptionEntity) -> OptionEntity:
        self.options.append(option)
        return option

    def remove(self, option: OptionEntity):
        if option in self.options:
            self.options.remove(option)

    def clear(self):
        self.options.clear()

    def update(self, player_x: float, player_y: float,
               is_focused: bool, dt: float,
               anim_data: dict = None):
        """
        更新所有僚机位置和动画
        :param anim_data: {anim_id: {"frame_count": N, "frame_duration": F, "loop": bool}}
        """
        for opt in self.options:
            if not opt.active:
                continue
            opt.update_position(player_x, player_y, is_focused, dt)
            if anim_data and opt.anim_id in anim_data:
                ad = anim_data[opt.anim_id]
                opt.update_animation(dt, ad.get('frame_count', 1),
                                     ad.get('frame_duration', 8.0 / 60.0),
                                     ad.get('loop', True))

    def get_positions(self) -> list:
        """返回 [(x, y), ...] 供渲染使用"""
        return [(o.current_x, o.current_y) for o in self.options if o.active]

    def get_render_data(self) -> list:
        """返回 [(x, y, frame_index), ...] 供渲染使用"""
        return [(o.current_x, o.current_y, o.current_frame)
                for o in self.options if o.active]

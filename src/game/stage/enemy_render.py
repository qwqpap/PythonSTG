"""
敌人贴图对象 - LuaSTG风格自动动画管理

当设置 sprite = "enemy1" 时，引擎自动：
1. 查找 enemy1_idle / enemy1_move_left / enemy1_move_right 子动画
2. 根据敌人X方向速度自动切换动画状态
3. 如果没有子动画，退回到单一循环动画

用法（引擎内部自动调用，关卡脚本无需关心）：
    render_obj = EnemyRenderObject("enemy1", asset_manager)
    # 每帧
    render_obj.update(vx=enemy.x - prev_x, dt=1/60)
    frame, texture_path = render_obj.get_current_frame()
"""

from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.resource.texture_asset import TextureAssetManager, SpriteFrame


class EnemyRenderObject:
    """敌人贴图对象 - 自动处理idle/move_left/move_right动画切换"""

    def __init__(self, sprite_name: str, asset_manager: 'TextureAssetManager'):
        self.sprite_name = sprite_name
        self.asset_manager = asset_manager

        # 尝试方向性模式：查找 {name}_idle, {name}_move_left, {name}_move_right
        self.idle_anim = asset_manager.get_animation(f"{sprite_name}_idle")
        self.left_anim = asset_manager.get_animation(f"{sprite_name}_move_left")
        self.right_anim = asset_manager.get_animation(f"{sprite_name}_move_right")
        self.directional = all([self.idle_anim, self.left_anim, self.right_anim])

        # 退回到单一动画
        self.simple_anim = None
        if not self.directional:
            self.simple_anim = asset_manager.get_animation(sprite_name)

        # 动画状态
        self.state = 'idle'
        self.anim_time = 0.0
        self.move_threshold = 0.001

    @property
    def is_valid(self) -> bool:
        """是否成功加载了动画"""
        return self.directional or self.simple_anim is not None

    def update(self, vx: float, dt: float):
        """
        每帧更新：根据X速度自动选择动画状态

        Args:
            vx: X方向速度（正=右移，负=左移）
            dt: 时间步长（秒）
        """
        self.anim_time += dt

        if not self.directional:
            return

        if vx < -self.move_threshold:
            new_state = 'move_left'
        elif vx > self.move_threshold:
            new_state = 'move_right'
        else:
            new_state = 'idle'

        if new_state != self.state:
            self.state = new_state
            self.anim_time = 0.0

    def get_current_frame(self) -> Tuple[Optional['SpriteFrame'], Optional[str]]:
        """
        获取当前帧数据

        Returns:
            (SpriteFrame, texture_path) 或 (None, None)
        """
        anim = self._get_current_animation()
        if anim is None:
            return None, None

        frame = anim.get_frame_at_time(self.anim_time)
        return frame, anim.texture_path

    def _get_current_animation(self):
        """获取当前应播放的动画"""
        if self.directional:
            anims = {
                'idle': self.idle_anim,
                'move_left': self.left_anim,
                'move_right': self.right_anim,
            }
            return anims.get(self.state, self.idle_anim)
        return self.simple_anim

"""
咲夜自机脚本
定义咲夜特有的行为：散射范围、伤害加成、子机位置等
"""
import math
from typing import TYPE_CHECKING, Optional, List, Tuple

# 导入基类（避免循环导入）
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from src.game.player.player_script import PlayerScript

if TYPE_CHECKING:
    from src.game.player.player_base import PlayerBase


class SakuyaScript(PlayerScript):
    """咲夜行为脚本"""
    
    def __init__(self, player: 'PlayerBase'):
        super().__init__(player)
        
        # ========== 散射系统 ==========
        self.spread_range = 15.0            # 当前散射范围
        self.spread_unfocused = 15.0        # 高速时散射
        self.spread_focused = 0.5           # 低速时散射
        self.spread_lerp_speed = 0.1        # 变化速度
        
        # ========== 伤害加成 ==========
        self.damage_bonus = 1.0
        
        # ========== 追踪系统 ==========
        self.target_pos: Optional[Tuple[float, float]] = None
        self.target_angle = 90.0
        
        # ========== 子机系统 ==========
        # 格式: {power_level: [(unfocused_x, unfocused_y, focused_x, focused_y), ...]}
        # 坐标单位：像素（会除以 192 转换为归一化坐标，因为游戏区域约 384 像素宽）
        self.option_layouts = {
            1: [],
            2: [(0, -24, 0, -24)],
            3: [(-24, -8, -12, -16), (24, -8, 12, -16)],
            4: [(-24, -8, -12, -16), (24, -8, 12, -16), (0, -24, 0, -24)],
            5: [(-24, -8, -12, -16), (24, -8, 12, -16), (-12, -24, -6, -24), (12, -24, 6, -24)],
        }
        self.option_actual_positions: List[List[float]] = []
        
        # 脚本配置（可从 config.json 的 script_config 加载）
        self.config = {}
    
    def on_init(self):
        """初始化时调用"""
        # 从配置加载参数
        if self.config:
            self.spread_unfocused = self.config.get('spread_unfocused', self.spread_unfocused)
            self.spread_focused = self.config.get('spread_focused', self.spread_focused)
            self.spread_lerp_speed = self.config.get('spread_lerp_speed', self.spread_lerp_speed)
            
            # 加载子机布局
            if 'option_layouts' in self.config:
                self.option_layouts = {}
                for k, v in self.config['option_layouts'].items():
                    self.option_layouts[int(k)] = [tuple(pos) for pos in v]
    
    def on_update(self, dt: float):
        """每帧更新"""
        # 更新散射范围（平滑过渡）
        target_spread = self.spread_focused if self.player.is_focused else self.spread_unfocused
        self.spread_range += (target_spread - self.spread_range) * self.spread_lerp_speed
        self.spread_range = max(0.1, self.spread_range)
        
        # 计算伤害加成 (公式: spread * 0.2 + 0.9)
        # 低速时 spread=0.5, bonus=1.0; 高速时 spread=15, bonus=3.9
        self.damage_bonus = self.spread_range * 0.2 + 0.9
        
        # 更新追踪角度
        if self.player.is_focused and self.target_pos:
            dx = self.target_pos[0] - self.player.pos[0]
            dy = self.target_pos[1] - self.player.pos[1]
            if abs(dx) > 0.001 or abs(dy) > 0.001:
                self.target_angle = math.degrees(math.atan2(dy, dx))
        else:
            self.target_angle = 90.0  # 默认向上
        
        # 更新子机位置
        self._update_option_positions(dt)
    
    def _update_option_positions(self, dt: float):
        """更新子机位置"""
        power_level = min(5, max(1, int(self.player.power)))
        layout = self.option_layouts.get(power_level, [])
        
        # 位置转换系数（像素转归一化坐标）
        scale = 1.0 / 192.0
        
        # 调整位置列表长度
        while len(self.option_actual_positions) < len(layout):
            opt = layout[len(self.option_actual_positions)]
            self.option_actual_positions.append([
                self.player.pos[0] + opt[0] * scale,
                self.player.pos[1] + opt[1] * scale
            ])
        
        while len(self.option_actual_positions) > len(layout):
            self.option_actual_positions.pop()
        
        # 平滑移动到目标位置
        lerp_speed = 8.0 * dt
        for i, opt in enumerate(layout):
            if i >= len(self.option_actual_positions):
                break
            
            # 根据聚焦状态选择目标位置
            scale = 1.0 / 192.0
            if self.player.is_focused:
                target_x = self.player.pos[0] + opt[2] * scale
                target_y = self.player.pos[1] + opt[3] * scale
            else:
                target_x = self.player.pos[0] + opt[0] * scale
                target_y = self.player.pos[1] + opt[1] * scale
            
            # 平滑插值
            self.option_actual_positions[i][0] += (target_x - self.option_actual_positions[i][0]) * lerp_speed
            self.option_actual_positions[i][1] += (target_y - self.option_actual_positions[i][1]) * lerp_speed
    
    def get_shot_params(self) -> dict:
        """获取射击参数"""
        return {
            'spread_range': self.spread_range,
            'target_angle': self.target_angle if self.player.is_focused else None,
            'damage_bonus': self.damage_bonus,
        }
    
    def get_option_positions(self) -> list:
        """获取子机位置"""
        return [(pos[0], pos[1]) for pos in self.option_actual_positions]
    
    def on_bomb(self, is_focused: bool) -> bool:
        """
        使用符卡
        返回 True 表示脚本处理了符卡
        """
        if is_focused:
            # 时符「私人时间的停止」
            self._activate_time_stop()
        else:
            # 幻符「杀人偶」
            self._activate_knife_storm()
        
        # 设置无敌时间
        self.player.invincible_timer = 6.0
        self.player.spell_cooldown = 5.0
        return True
    
    def _activate_time_stop(self):
        """激活时停符卡"""
        # TODO: 实现时停效果
        print("时符「私人时间的停止」！")
    
    def _activate_knife_storm(self):
        """激活飞刀风暴"""
        # TODO: 实现飞刀风暴
        print("幻符「杀人偶」！")
    
    def set_target(self, target_pos: Optional[Tuple[float, float]]):
        """设置追踪目标（供外部调用）"""
        self.target_pos = target_pos


# 工厂函数（可选的脚本加载方式）
def create_script(player: 'PlayerBase') -> SakuyaScript:
    return SakuyaScript(player)

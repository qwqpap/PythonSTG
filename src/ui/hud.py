"""
HUD类 - 游戏抬头显示

显示内容:
- 分数 / 高分
- 生命数
- 炸弹数
- Power值
- Graze数
- 符卡名/时间（Boss战）
"""

from dataclasses import dataclass
from typing import Optional
import json
import os


@dataclass
class GameState:
    """游戏状态数据类"""
    score: int = 0
    hiscore: int = 0
    lives: int = 3
    bombs: int = 3
    power: float = 1.0
    max_power: float = 4.0
    graze: int = 0
    point_value: int = 10000
    
    # Boss战相关
    boss_name: str = ""
    spell_name: str = ""
    spell_time: float = 0.0
    spell_bonus: int = 0
    boss_hp_ratio: float = 0.0  # 0.0 ~ 1.0
    is_boss_fight: bool = False
    fps: int = 0


def load_hud_layout(layout_path: str):
    """加载 HUD 布局配置 (JSON)"""
    if not os.path.exists(layout_path):
        print(f"HUD布局文件不存在: {layout_path}, 使用默认布局")
        return None
    try:
        with open(layout_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"HUD布局加载失败: {e}, 使用默认布局")
        return None


class HUD:
    """
    游戏HUD系统
    
    布局参考东方系列:
    ┌─────────────────────────────────────────┐
    │  HiScore  999999999                      │
    │  Score    000000000                      │
    │                                          │
    │  Player ★★★☆☆  Bomb ★★★☆☆         │
    │  Power  2.00/4.00  ████████░░░░         │
    │  Graze  0000       Point 000000         │
    │                                          │
    │         [游戏区域 384x448]               │
    │                                          │
    │  [Boss HP 条]                            │
    │  [符卡名称] [剩余时间]                   │
    └─────────────────────────────────────────┘
    """
    
    def __init__(self, screen_width: int = 384, screen_height: int = 448,
                 panel_origin=(0, 0), panel_size=(200, 448),
                 game_origin=(0, 0), game_size=(384, 448),
                 bg_color=(16, 16, 32), bg_alpha=0.6,
                 layout_override=None):
        """
        初始化HUD
        
        Args:
            screen_width: 游戏区域宽度（像素）
            screen_height: 游戏区域高度（像素）
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.panel_origin = panel_origin
        self.panel_size = panel_size
        self.bg_color = bg_color
        self.bg_alpha = bg_alpha
        self.game_origin = game_origin
        self.game_size = game_size
        
        # 游戏状态
        self.state = GameState()
        
        # HUD布局配置（像素坐标，原点在左上角）
        self.layout = layout_override if layout_override else {
            # 分数区域
            'hiscore_label': (10, 10),
            'hiscore_value': (120, 10),
            'score_label': (10, 35),
            'score_value': (120, 35),
            
            # 资源区域
            'player_label': (10, 70),
            'player_icons': (80, 70),
            'bomb_label': (200, 70),
            'bomb_icons': (260, 70),
            
            # Power区域
            'power_label': (10, 95),
            'power_value': (80, 95),
            'power_bar': (160, 95),
            'power_bar_width': 100,
            'power_bar_height': 12,
            
            # Graze和Point
            'graze_label': (10, 120),
            'graze_value': (70, 120),
            'point_label': (160, 120),
            'point_value': (220, 120),
            
            # Boss区域（屏幕顶部）
            'boss_hp_bar': (20, 5),
            'boss_hp_bar_width': 344,
            'boss_hp_bar_height': 8,
            'spell_name': (192, 25),  # 居中（相对于game）
            'spell_time': (350, 25),
            'spell_bonus': (192, 45),
        }
        
        # 字体缩放
        self.font_scale = 0.6
        self.small_font_scale = 0.5
    
    def update_from_player(self, player) -> None:
        """
        从玩家对象更新状态
        
        Args:
            player: Player对象
        """
        self.state.score = player.score
        self.state.lives = player.lives
        self.state.power = player.power
    
    def update_from_boss(self, boss) -> None:
        """
        从Boss对象更新状态
        
        Args:
            boss: Boss对象 (BossBase)
        """
        if boss and getattr(boss, 'alive', getattr(boss, '_active', False)):
            self.state.is_boss_fight = True
            self.state.boss_name = getattr(boss, 'name', 'Boss')
            boss_hp = getattr(boss, 'current_hp', getattr(boss, 'hp', 0))
            boss_max_hp = getattr(boss, 'max_hp', 1)
            self.state.boss_hp_ratio = boss_hp / boss_max_hp if boss_max_hp > 0 else 0
            # 符卡相关
            spell = getattr(boss, 'current_spell', getattr(boss, 'current_spellcard', None))
            if spell:
                self.state.spell_name = getattr(spell, 'name', '')
                self.state.spell_time = getattr(spell, 'time_remaining', getattr(spell, 'time_left', 0))
                # 显示实时衰减的 bonus
                self.state.spell_bonus = getattr(boss, 'spell_bonus_display', getattr(spell, 'bonus', 0))
        else:
            self.state.is_boss_fight = False
            self.state.boss_hp_ratio = 0
    
    def add_score(self, amount: int) -> None:
        """增加分数"""
        self.state.score += amount
        if self.state.score > self.state.hiscore:
            self.state.hiscore = self.state.score
    
    def add_graze(self, amount: int = 1) -> None:
        """增加Graze"""
        self.state.graze += amount
    
    def add_power(self, amount: float) -> None:
        """增加Power"""
        self.state.power = min(self.state.power + amount, self.state.max_power)
    
    def use_bomb(self) -> bool:
        """
        使用炸弹
        
        Returns:
            bool: 是否成功使用
        """
        if self.state.bombs > 0:
            self.state.bombs -= 1
            return True
        return False
    
    def lose_life(self) -> bool:
        """
        失去生命
        
        Returns:
            bool: 是否游戏结束
        """
        if self.state.lives > 0:
            self.state.lives -= 1
            # 减少Power
            self.state.power = max(1.0, self.state.power - 1.0)
            return self.state.lives <= 0
        return True
    
    def get_render_elements(self) -> list:
        """
        获取需要渲染的UI元素列表
        
        Returns:
            list: [{'type': 'text'/'bar'/'icon', 'position': (x, y), ...}, ...]
        """
        elements = []

        # 面板背景
        elements.append({
            'type': 'rect',
            'position': (self.panel_origin[0], self.panel_origin[1]),
            'width': self.panel_size[0],
            'height': self.panel_size[1],
            'color': self.bg_color,
            'alpha': self.bg_alpha
        })
        
        # 分数显示
        elements.append({
            'type': 'text',
            'text': 'HiScore',
            'position': (self.panel_origin[0] + self.layout['hiscore_label'][0],
                         self.panel_origin[1] + self.layout['hiscore_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (255, 255, 255)
        })
        elements.append({
            'type': 'text',
            'text': f'{self.state.hiscore:09d}',
            'position': (self.panel_origin[0] + self.layout['hiscore_value'][0],
                         self.panel_origin[1] + self.layout['hiscore_value'][1]),
            'font': 'score',
            'scale': self.font_scale,
            'color': (255, 255, 255)
        })
        elements.append({
            'type': 'text',
            'text': 'Score',
            'position': (self.panel_origin[0] + self.layout['score_label'][0],
                         self.panel_origin[1] + self.layout['score_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (255, 255, 255)
        })
        elements.append({
            'type': 'text',
            'text': f'{self.state.score:09d}',
            'position': (self.panel_origin[0] + self.layout['score_value'][0],
                         self.panel_origin[1] + self.layout['score_value'][1]),
            'font': 'score',
            'scale': self.font_scale,
            'color': (255, 255, 255)
        })
        
        # 生命数
        elements.append({
            'type': 'text',
            'text': 'Player',
            'position': (self.panel_origin[0] + self.layout['player_label'][0],
                         self.panel_origin[1] + self.layout['player_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (255, 128, 128)
        })
        # 生命图标用星号表示
        life_text = '*' * self.state.lives + '.' * (5 - self.state.lives)
        elements.append({
            'type': 'text',
            'text': life_text,
            'position': (self.panel_origin[0] + self.layout['player_icons'][0],
                         self.panel_origin[1] + self.layout['player_icons'][1]),
            'font': 'score',
            'scale': self.font_scale,
            'color': (255, 64, 64)
        })
        
        # 炸弹数
        elements.append({
            'type': 'text',
            'text': 'Bomb',
            'position': (self.panel_origin[0] + self.layout['bomb_label'][0],
                         self.panel_origin[1] + self.layout['bomb_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (128, 255, 128)
        })
        bomb_text = '*' * self.state.bombs + '.' * (5 - self.state.bombs)
        elements.append({
            'type': 'text',
            'text': bomb_text,
            'position': (self.panel_origin[0] + self.layout['bomb_icons'][0],
                         self.panel_origin[1] + self.layout['bomb_icons'][1]),
            'font': 'score',
            'scale': self.font_scale,
            'color': (64, 255, 64)
        })
        
        # Power
        elements.append({
            'type': 'text',
            'text': 'Power',
            'position': (self.panel_origin[0] + self.layout['power_label'][0],
                         self.panel_origin[1] + self.layout['power_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (128, 128, 255)
        })
        elements.append({
            'type': 'text',
            'text': f'{self.state.power:.2f}/{self.state.max_power:.2f}',
            'position': (self.panel_origin[0] + self.layout['power_value'][0],
                         self.panel_origin[1] + self.layout['power_value'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (128, 128, 255)
        })
        # Power条
        elements.append({
            'type': 'bar',
            'position': (self.panel_origin[0] + self.layout['power_bar'][0],
                         self.panel_origin[1] + self.layout['power_bar'][1]),
            'width': self.layout['power_bar_width'],
            'height': self.layout['power_bar_height'],
            'value': self.state.power / self.state.max_power,
            'color_bg': (32, 32, 64),
            'color_fill': (64, 64, 255)
        })
        
        # Graze
        elements.append({
            'type': 'text',
            'text': 'Graze',
            'position': (self.panel_origin[0] + self.layout['graze_label'][0],
                         self.panel_origin[1] + self.layout['graze_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (200, 200, 200)
        })
        elements.append({
            'type': 'text',
            'text': f'{self.state.graze:04d}',
            'position': (self.panel_origin[0] + self.layout['graze_value'][0],
                         self.panel_origin[1] + self.layout['graze_value'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (255, 255, 255)
        })
        
        # Point
        elements.append({
            'type': 'text',
            'text': 'Point',
            'position': (self.panel_origin[0] + self.layout['point_label'][0],
                         self.panel_origin[1] + self.layout['point_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (200, 200, 200)
        })
        elements.append({
            'type': 'text',
            'text': f'{self.state.point_value:06d}',
            'position': (self.panel_origin[0] + self.layout['point_value'][0],
                         self.panel_origin[1] + self.layout['point_value'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (255, 255, 200)
        })
        
        # 游戏区域边框（弹幕渲染部分）- 向外扩张
        border_thickness = 2
        border_offset = 3
        
        # 上边框
        elements.append({
            'type': 'rect',
            'position': (self.game_origin[0] - border_offset, self.game_origin[1] - border_offset - border_thickness),
            'width': self.game_size[0] + border_offset * 2,
            'height': border_thickness,
            'color': (255, 255, 255),
            'alpha': 0.8
        })
        # 下边框
        elements.append({
            'type': 'rect',
            'position': (self.game_origin[0] - border_offset, self.game_origin[1] + self.game_size[1] + border_offset),
            'width': self.game_size[0] + border_offset * 2,
            'height': border_thickness,
            'color': (255, 255, 255),
            'alpha': 0.8
        })
        # 左边框
        elements.append({
            'type': 'rect',
            'position': (self.game_origin[0] - border_offset - border_thickness, self.game_origin[1] - border_offset),
            'width': border_thickness,
            'height': self.game_size[1] + border_offset * 2,
            'color': (255, 255, 255),
            'alpha': 0.8
        })
        # 右边框
        elements.append({
            'type': 'rect',
            'position': (self.game_origin[0] + self.game_size[0] + border_offset, self.game_origin[1] - border_offset),
            'width': border_thickness,
            'height': self.game_size[1] + border_offset * 2,
            'color': (255, 255, 255),
            'alpha': 0.8
        })
        
        # Boss战UI
        if self.state.is_boss_fight:
            # Boss HP条
            elements.append({
                'type': 'bar',
                'position': (self.game_origin[0] + self.layout['boss_hp_bar'][0],
                             self.game_origin[1] + self.layout['boss_hp_bar'][1]),
                'width': self.layout['boss_hp_bar_width'],
                'height': self.layout['boss_hp_bar_height'],
                'value': self.state.boss_hp_ratio,
                'color_bg': (64, 0, 0),
                'color_fill': (255, 64, 64)
            })
            
            # 符卡名
            if self.state.spell_name:
                elements.append({
                    'type': 'text',
                    'text': self.state.spell_name,
                    'position': (self.game_origin[0] + self.layout['spell_name'][0],
                                 self.game_origin[1] + self.layout['spell_name'][1]),
                    'font': 'score',
                    'scale': self.small_font_scale,
                    'color': (255, 255, 128),
                    'align': 'center'
                })
            
            # 符卡时间
            if self.state.spell_time > 0:
                elements.append({
                    'type': 'text',
                    'text': f'{int(self.state.spell_time):02d}',
                    'position': (self.game_origin[0] + self.layout['spell_time'][0],
                                 self.game_origin[1] + self.layout['spell_time'][1]),
                    'font': 'score',
                    'scale': self.font_scale,
                    'color': (255, 255, 255) if self.state.spell_time > 10 else (255, 64, 64)
                })
            
            # 符卡 Bonus（实时衰减值）
            if self.state.spell_bonus > 0:
                elements.append({
                    'type': 'text',
                    'text': f'Bonus {self.state.spell_bonus:,}',
                    'position': (self.game_origin[0] + self.layout['spell_bonus'][0],
                                 self.game_origin[1] + self.layout['spell_bonus'][1]),
                    'font': 'score',
                    'scale': self.small_font_scale,
                    'color': (255, 255, 200),
                    'align': 'center'
                })

        # FPS 显示（窗口右下角）
        elements.append({
            'type': 'text',
            'text': f'FPS {self.state.fps:03d}',
            'position': (self.screen_width - 16, self.screen_height - 24),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (180, 255, 180),
            'align': 'right'
        })

        return elements

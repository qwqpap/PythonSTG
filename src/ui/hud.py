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
    lives: int = 2
    bombs: int = 2
    max_lives: int = 8
    max_bombs: int = 8
    power: float = 1.0
    max_power: float = 4.0
    graze: int = 0
    point_value: int = 10000
    
    # Boss战相关
    boss_name: str = ""
    spell_name: str = ""
    spell_time: float = 0.0
    spell_card_index: int = 0
    spell_card_total: int = 0
    spell_bonus: int = 0
    boss_hp_ratio: float = 0.0  # 0.0 ~ 1.0
    is_boss_fight: bool = False
    fps: int = 0
    max_fps: int = 0


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
        
        self.layout = layout_override if layout_override else {
            # 分数区域
            'hiscore_label': (10, 10),
            'hiscore_value': (120, 10),
            'score_label': (10, 35),
            'score_value': (120, 35),
            
            # 资源区域
            'player_label': (10, 70),
            'player_icons': (80, 70),
            
            # 炸弹/道具区域
            'bomb_label': (10, 95),
            'bomb_icons': (80, 95),
            
            # Power区域
            'power_label': (10, 120),
            'power_value': (80, 120),
            'power_bar': (160, 120),
            'power_bar_width': 100,
            'power_bar_height': 12,
            
            # Graze和Point
            'graze_label': (10, 145),
            'graze_value': (70, 145),
            'point_label': (160, 145),
            'point_value': (220, 145),
            
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
            ratio = boss_hp / boss_max_hp if boss_max_hp > 0 else 0
            self.state.boss_hp_ratio = max(0.0, min(1.0, ratio))
            # 符卡相关
            spell = getattr(boss, 'current_spell', getattr(boss, 'current_spellcard', None))
            # 宣言动画期间，符卡名由 SpellDeclarationRenderer 绘制，HUD 不再重复
            declaration_active = False
            if hasattr(boss, 'is_declaration_active'):
                try:
                    declaration_active = bool(boss.is_declaration_active())
                except Exception:
                    declaration_active = False
            if spell:
                if declaration_active:
                    self.state.spell_name = ''
                else:
                    self.state.spell_name = getattr(spell, 'name', '')
                self.state.spell_time = getattr(spell, 'time_remaining', getattr(spell, 'time_left', 0))
                self.state.spell_card_index = int(getattr(boss, 'current_spellcard_number', 0))
                self.state.spell_card_total = int(getattr(boss, 'total_spellcards', 0))
                self.state.spell_bonus = 0
            else:
                self.state.spell_name = ''
                self.state.spell_time = 0.0
                self.state.spell_card_index = 0
                self.state.spell_card_total = 0
                self.state.spell_bonus = 0
        else:
            self.state.is_boss_fight = False
            self.state.boss_name = ''
            self.state.spell_name = ''
            self.state.spell_time = 0.0
            self.state.spell_card_index = 0
            self.state.spell_card_total = 0
            self.state.spell_bonus = 0
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

        # ── 色板（与樱花背景协调）──────────────────────────────────────────
        COL_LABEL     = (235, 225, 230)   # 柔和米白，用于 label
        COL_VALUE     = (255, 250, 240)   # 近白，数值
        COL_PLAYER    = (255, 160, 180)   # 玫粉，Player label
        COL_PLAYER_IC = (255, 100, 130)   # 稍深玫粉，Player 图标
        COL_BOMB      = (180, 230, 195)   # 柔和薄荷绿，Bomb label
        COL_BOMB_IC   = (120, 210, 155)   # 稍深绿，Bomb 图标
        COL_POWER     = (180, 200, 255)   # 柔和淡蓝，Power label
        COL_POWER_VAL = (220, 230, 255)   # Power 数值
        COL_SUBTLE    = (210, 200, 210)   # Graze/Point label
        COL_POINT_VAL = (255, 240, 200)   # Point 数值（淡金）
        COL_DIVIDER   = (255, 255, 255)   # 细分割线
        COL_CARD_BG   = (18, 14, 24)      # 卡片背景（深紫黑）

        # ── Section backdrops（半透明卡片，让白字在花背景上可读）──────────
        card_alpha = 0.42
        for key in ('section_score_bg', 'section_stats_bg',
                    'section_bonus_bg', 'section_heat_bg'):
            if key not in self.layout:
                continue
            bx, by, bw, bh = self.layout[key]
            elements.append({
                'type': 'rect',
                'position': (self.panel_origin[0] + bx,
                             self.panel_origin[1] + by),
                'width': bw, 'height': bh,
                'color': COL_CARD_BG,
                'alpha': card_alpha,
            })

        # ── 分割线（卡片间细白线，+低透明）────────────────────────────────
        for key in ('divider_score_stats', 'divider_stats_bonus',
                    'divider_bonus_heat'):
            if key not in self.layout:
                continue
            dx, dy, dw, dh = self.layout[key]
            elements.append({
                'type': 'rect',
                'position': (self.panel_origin[0] + dx,
                             self.panel_origin[1] + dy),
                'width': dw, 'height': dh,
                'color': COL_DIVIDER,
                'alpha': 0.18,
            })

        # 分数显示（数值右对齐）
        elements.append({
            'type': 'text',
            'text': 'HiScore',
            'position': (self.panel_origin[0] + self.layout['hiscore_label'][0],
                         self.panel_origin[1] + self.layout['hiscore_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': COL_LABEL
        })
        elements.append({
            'type': 'text',
            'text': f'{self.state.hiscore:09d}',
            'position': (self.panel_origin[0] + self.layout['hiscore_value'][0],
                         self.panel_origin[1] + self.layout['hiscore_value'][1]),
            'font': 'score',
            'scale': self.font_scale,
            'color': COL_VALUE,
            'align': 'right'
        })
        elements.append({
            'type': 'text',
            'text': 'Score',
            'position': (self.panel_origin[0] + self.layout['score_label'][0],
                         self.panel_origin[1] + self.layout['score_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': COL_LABEL
        })
        elements.append({
            'type': 'text',
            'text': f'{self.state.score:09d}',
            'position': (self.panel_origin[0] + self.layout['score_value'][0],
                         self.panel_origin[1] + self.layout['score_value'][1]),
            'font': 'score',
            'scale': self.font_scale,
            'color': COL_VALUE,
            'align': 'right'
        })

        # 生命数
        elements.append({
            'type': 'text',
            'text': 'Player',
            'position': (self.panel_origin[0] + self.layout['player_label'][0],
                         self.panel_origin[1] + self.layout['player_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': COL_PLAYER
        })
        # 不显示生命图标，改为显示固定文字
        elements.append({
            'type': 'text',
            'text': '+1 life',
            'position': (self.panel_origin[0] + self.layout['player_icons'][0],
                         self.panel_origin[1] + self.layout['player_icons'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': (255, 220, 80)
        })

        # 炸弹数
        elements.append({
            'type': 'text',
            'text': 'Bomb',
            'position': (self.panel_origin[0] + self.layout['bomb_label'][0],
                         self.panel_origin[1] + self.layout['bomb_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': COL_BOMB
        })
        bomb_text = '*' * self.state.bombs + '.' * max(0, self.state.max_bombs - self.state.bombs)
        elements.append({
            'type': 'text',
            'text': bomb_text,
            'position': (self.panel_origin[0] + self.layout['bomb_icons'][0],
                         self.panel_origin[1] + self.layout['bomb_icons'][1]),
            'font': 'score',
            'scale': self.font_scale,
            'color': COL_BOMB_IC
        })

        # Power
        elements.append({
            'type': 'text',
            'text': 'Power',
            'position': (self.panel_origin[0] + self.layout['power_label'][0],
                         self.panel_origin[1] + self.layout['power_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': COL_POWER
        })
        elements.append({
            'type': 'text',
            'text': f'{self.state.power:.2f}/{self.state.max_power:.2f}',
            'position': (self.panel_origin[0] + self.layout['power_value'][0],
                         self.panel_origin[1] + self.layout['power_value'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': COL_POWER_VAL,
            'align': 'right'
        })
        # Power条（柔和的淡蓝渐变感，用较低不透明的深底 + 明亮填充）
        elements.append({
            'type': 'bar',
            'position': (self.panel_origin[0] + self.layout['power_bar'][0],
                         self.panel_origin[1] + self.layout['power_bar'][1]),
            'width': self.layout['power_bar_width'],
            'height': self.layout['power_bar_height'],
            'value': self.state.power / self.state.max_power,
            'color_bg': (36, 28, 52),
            'color_fill': (140, 170, 255),
            'alpha': 0.92,
        })

        # Graze（右对齐数值）
        elements.append({
            'type': 'text',
            'text': 'Graze',
            'position': (self.panel_origin[0] + self.layout['graze_label'][0],
                         self.panel_origin[1] + self.layout['graze_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': COL_SUBTLE
        })
        elements.append({
            'type': 'text',
            'text': f'{self.state.graze:04d}',
            'position': (self.panel_origin[0] + self.layout['graze_value'][0],
                         self.panel_origin[1] + self.layout['graze_value'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': COL_VALUE,
            'align': 'right'
        })

        # Point（右对齐数值）
        elements.append({
            'type': 'text',
            'text': 'Point',
            'position': (self.panel_origin[0] + self.layout['point_label'][0],
                         self.panel_origin[1] + self.layout['point_label'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': COL_SUBTLE
        })
        elements.append({
            'type': 'text',
            'text': f'{self.state.point_value:06d}',
            'position': (self.panel_origin[0] + self.layout['point_value'][0],
                         self.panel_origin[1] + self.layout['point_value'][1]),
            'font': 'score',
            'scale': self.small_font_scale,
            'color': COL_POINT_VAL,
            'align': 'right'
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
                'position': (self.game_origin[0],
                             self.game_origin[1] + self.layout['boss_hp_bar'][1]),
                'width': self.game_size[0],
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
                    'scale': self.small_font_scale * 0.84,
                    'color': (255, 255, 128),
                    'align': 'center'
                })
            
            # 符卡时间
            if self.state.spell_time > 0:
                if self.state.spell_card_index > 0 and self.state.spell_card_total > 0:
                    elements.append({
                        'type': 'text',
                        'text': f'{self.state.spell_card_index}/{self.state.spell_card_total}',
                        'position': (self.game_origin[0] + self.game_size[0] * 0.5 - 36,
                                     self.game_origin[1] + 34),
                        'font': 'score',
                        'scale': self.small_font_scale * 0.9,
                        'color': (255, 230, 170),
                        'align': 'right'
                    })
                elements.append({
                    'type': 'text',
                    'text': f'{int(self.state.spell_time):02d}',
                    'position': (self.game_origin[0] + self.game_size[0] * 0.5,
                                 self.game_origin[1] + 34),
                    'font': 'score',
                    'scale': self.font_scale,
                    'color': (255, 255, 255) if self.state.spell_time > 10 else (255, 64, 64),
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

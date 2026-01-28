"""
玩家配置加载器
从 JSON 文件加载玩家配置
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any

from .player_base import PlayerBase


class PlayerConfigLoader:
    """玩家配置加载器"""
    
    def __init__(self, players_root: str = "assets/players"):
        """
        初始化配置加载器
        :param players_root: 玩家资源根目录
        """
        self.players_root = Path(players_root)
        self.loaded_configs: Dict[str, dict] = {}
    
    def load_player_config(self, player_id: str) -> Optional[dict]:
        """
        加载玩家配置
        :param player_id: 玩家ID（对应文件夹名）
        :return: 配置字典
        """
        if player_id in self.loaded_configs:
            return self.loaded_configs[player_id]
        
        config_path = self.players_root / player_id / "config.json"
        
        if not config_path.exists():
            print(f"警告: 找不到玩家配置 {config_path}")
            return None
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 处理相对路径
            config['_player_id'] = player_id
            config['_base_path'] = str(self.players_root / player_id)
            
            self.loaded_configs[player_id] = config
            return config
            
        except Exception as e:
            print(f"加载玩家配置失败 {config_path}: {e}")
            return None
    
    def create_player(self, player_id: str) -> Optional[PlayerBase]:
        """
        创建玩家实例
        :param player_id: 玩家ID
        :return: PlayerBase实例
        """
        config = self.load_player_config(player_id)
        
        if config is None:
            # 返回默认玩家
            return PlayerBase()
        
        return PlayerBase(config)
    
    def get_available_players(self) -> list:
        """获取所有可用的玩家ID列表"""
        players = []
        
        if not self.players_root.exists():
            return players
        
        for path in self.players_root.iterdir():
            if path.is_dir():
                config_file = path / "config.json"
                if config_file.exists():
                    players.append(path.name)
        
        return players
    
    def get_player_info(self, player_id: str) -> dict:
        """
        获取玩家简要信息（用于选择界面）
        :param player_id: 玩家ID
        :return: 包含name, description等的字典
        """
        config = self.load_player_config(player_id)
        
        if config is None:
            return {
                'id': player_id,
                'name': player_id,
                'description': ''
            }
        
        return {
            'id': player_id,
            'name': config.get('name', player_id),
            'description': config.get('description', ''),
            'author': config.get('author', ''),
            'preview_sprite': config.get('preview_sprite', '')
        }


def load_player(player_id: str, players_root: str = "assets/players") -> PlayerBase:
    """
    便捷函数：加载并创建玩家
    :param player_id: 玩家ID
    :param players_root: 玩家资源根目录
    :return: PlayerBase实例
    """
    loader = PlayerConfigLoader(players_root)
    player = loader.create_player(player_id)
    return player if player else PlayerBase()


# 配置文件模板
CONFIG_TEMPLATE = '''
{
  "__comment": "玩家配置文件模板",
  
  "name": "博丽灵梦",
  "description": "博丽神社的巫女，擅长使用灵符和追踪弹",
  "author": "ZUN",
  
  "texture": "reimu.png",
  "preview_sprite": "reimu_preview",
  
  "stats": {
    "speed_high": 0.02,
    "speed_low": 0.008,
    "hit_radius": 0.01,
    "graze_radius": 0.05
  },
  
  "initial": {
    "lives": 3,
    "bombs": 3,
    "power": 1.0
  },
  
  "animations": {
    "transition_speed": 8.0,
    "move_threshold": 0.001,
    "full_tilt_frames": 8,
    "animations": {
      "idle": {
        "frames": ["reimu_idle_0", "reimu_idle_1", "reimu_idle_2", "reimu_idle_3"],
        "fps": 8,
        "loop": true
      },
      "move_left": {
        "frames": ["reimu_left_0", "reimu_left_1", "reimu_left_2", "reimu_left_3"],
        "fps": 12,
        "loop": true
      },
      "move_right": {
        "frames": ["reimu_right_0", "reimu_right_1", "reimu_right_2", "reimu_right_3"],
        "fps": 12,
        "loop": true
      }
    }
  },
  
  "shot_types": {
    "unfocused": {
      "name": "灵符「梦想封印」",
      "fire_rate": 0.05,
      "patterns": [
        { "offset": [-0.03, 0.02], "angle": 90, "speed": 0.8, "bullet": "reimu_needle", "damage": 10 },
        { "offset": [0.03, 0.02], "angle": 90, "speed": 0.8, "bullet": "reimu_needle", "damage": 10 }
      ],
      "power_patterns": {
        "2.0": [
          { "offset": [-0.06, 0.01], "angle": 85, "speed": 0.75, "bullet": "reimu_needle", "damage": 8 },
          { "offset": [0.06, 0.01], "angle": 95, "speed": 0.75, "bullet": "reimu_needle", "damage": 8 }
        ],
        "3.0": [
          { "offset": [-0.09, 0.0], "angle": 80, "speed": 0.7, "bullet": "reimu_needle", "damage": 6 },
          { "offset": [0.09, 0.0], "angle": 100, "speed": 0.7, "bullet": "reimu_needle", "damage": 6 }
        ]
      }
    },
    "focused": {
      "name": "灵符「博丽幻想」",
      "fire_rate": 0.04,
      "patterns": [
        { "offset": [0, 0.03], "angle": 90, "speed": 0.6, "bullet": "reimu_homing", "damage": 15, "homing": true, "homing_strength": 8.0 }
      ],
      "power_patterns": {
        "2.0": [
          { "offset": [-0.02, 0.03], "angle": 90, "speed": 0.55, "bullet": "reimu_homing", "damage": 12, "homing": true, "homing_strength": 7.0 },
          { "offset": [0.02, 0.03], "angle": 90, "speed": 0.55, "bullet": "reimu_homing", "damage": 12, "homing": true, "homing_strength": 7.0 }
        ]
      }
    }
  },
  
  "options": [
    {
      "sprite": "reimu_option",
      "offset": [-0.08, 0.02],
      "focused_offset": [-0.03, 0.04],
      "shot_patterns": [
        { "angle": 90, "speed": 0.7, "bullet": "reimu_option_shot", "damage": 5 }
      ]
    },
    {
      "sprite": "reimu_option",
      "offset": [0.08, 0.02],
      "focused_offset": [0.03, 0.04],
      "shot_patterns": [
        { "angle": 90, "speed": 0.7, "bullet": "reimu_option_shot", "damage": 5 }
      ]
    }
  ],
  
  "spellcards": [
    {
      "name": "梦符「封魔阵」",
      "cost": 100,
      "script": "reimu_spell_1",
      "description": "在自机周围展开强力结界"
    }
  ]
}
'''


def generate_config_template(output_path: str):
    """生成配置文件模板"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(CONFIG_TEMPLATE.strip())
    print(f"已生成配置模板: {output_path}")

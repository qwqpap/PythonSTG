"""
关卡上下文 - 引擎层提供给内容层的统一接口

这是引擎和内容之间的桥梁。
所有内容脚本（符卡、波次、敌人）通过此上下文与引擎交互。
内容脚本不需要知道 BulletPool、EnemyManager 等引擎内部实现。

使用方式（由 StageManager._run_stage 自动创建）：
    ctx = StageContext(bullet_pool=bullet_pool, player=player)
"""

import json
import math
import os
from typing import Optional, Any, Dict, List

from .spellcard import SpellCardContext
from ..audio import AudioManager


class PlayerProxy:
    """
    玩家代理 - 为内容脚本提供只读的玩家信息
    
    内容脚本只需要知道玩家的位置，不需要访问 Player 的内部实现。
    """
    
    def __init__(self, player):
        self._player = player
    
    @property
    def x(self) -> float:
        return self._player.pos[0]
    
    @property
    def y(self) -> float:
        return self._player.pos[1]


class StageContext(SpellCardContext):
    """
    关卡上下文 - 引擎提供的统一能力接口
    
    职责：
    - 将内容脚本的高层 API（bullet_type="ball_m", color="red"）
      映射到引擎底层（sprite_id="ball_mid1"）
    - 管理子弹的创建和销毁
    - 提供玩家信息的只读代理
    - 提供敌人管理接口
    
    内容脚本通过 SpellCard.ctx / Wave.ctx / EnemyScript.ctx 访问此对象。
    """
    
    # ===== 弹幕别名表（从 JSON 加载，每个类型独立的颜色映射） =====
    # 格式: {bullet_type: {color: sprite_name}}
    # 由 assets/bullet_aliases.json 定义，bullet_alias_manager 工具编辑
    BULLET_ALIAS_TABLE: Dict[str, Dict[str, str]] = {}
    _aliases_loaded: bool = False

    # ===== 旧版映射（保留为 fallback） =====
    BULLET_TYPE_MAP = {
        "ball_s": "ball_small",
        "ball_m": "ball_mid",
        "ball_l": "ball_huge",
        "rice": "rice",
        "scale": "scale",
        "arrowhead": "arrowhead",
        "knife": "knife",
        "star_s": "star_small",
        "star_m": "star_mid",
        "bullet": "bullet",
        "oval": "oval",
        "needle": "needle",
    }
    
    COLOR_MAP = {
        "red": "1",
        "blue": "2",
        "green": "3",
        "yellow": "4",
        "purple": "5",
        "white": "6",
        "darkblue": "7",
        "orange": "8",
        "cyan": "9",
        "pink": "10",
    }

    @classmethod
    def load_bullet_aliases(cls, path: str = "assets/bullet_aliases.json"):
        """
        从 JSON 加载弹幕别名表。
        
        文件格式:
            {"version": "1.0", "mapping": {"ball_m": {"red": "ball_mid1", ...}, ...}}
        """
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cls.BULLET_ALIAS_TABLE = data.get("mapping", {})
                count = sum(len(v) for v in cls.BULLET_ALIAS_TABLE.values())
                print(f"[StageContext] 加载 {len(cls.BULLET_ALIAS_TABLE)} 个弹幕类型, {count} 个别名")
            except Exception as e:
                print(f"[StageContext] 加载弹幕别名失败: {e}")
        cls._aliases_loaded = True
    
    def __init__(self, bullet_pool, player, enemy_manager=None,
                 laser_pool=None, item_pool=None,
                 audio_manager: Optional[AudioManager] = None):
        """
        Args:
            bullet_pool: 引擎的子弹池
            player: 引擎的玩家对象
            enemy_manager: 引擎的敌人管理器（可选）
            laser_pool: 引擎的激光池（可选）
            item_pool: 引擎的道具池（可选）
            audio_manager: 音频管理器（可选）
        """
        self.bullet_pool = bullet_pool
        self._player = player
        self._player_proxy = PlayerProxy(player)
        self._enemy_manager = enemy_manager
        self._laser_pool = laser_pool
        self._item_pool = item_pool
        self._audio_manager = audio_manager
        self._bullet_indices: List[int] = []
        self._enemy_scripts: List[Any] = []  # 存储活跃的敌人脚本实例

        # 首次使用时加载别名表
        if not StageContext._aliases_loaded:
            StageContext.load_bullet_aliases()
    
    def create_bullet(self, x: float, y: float, angle: float, speed: float,
                      bullet_type: str = "ball_m", color: str = "red",
                      accel: float = 0, angle_accel: float = 0,
                      owner=None, **kwargs) -> int:
        """
        创建子弹
        
        Args:
            x, y: 位置（归一化坐标）
            angle: 角度（度，0=右，90=上，-90=下）
            speed: 速度（每秒）
            bullet_type: 弹幕类型（ball_s, ball_m, rice, scale 等）
            color: 颜色（red, blue, green 等）
            accel: 加速度
            angle_accel: 角度加速度
            
        Returns:
            子弹索引（用于后续操作）
        """
        sprite_id = self._resolve_sprite_id(bullet_type, color)
        idx = self.bullet_pool.spawn_bullet(
            x=x, y=y,
            angle=math.radians(angle),
            speed=speed / 60.0,
            sprite_id=sprite_id
        )
        if idx >= 0:
            self._bullet_indices.append(idx)
        return idx
    
    def remove_bullet(self, bullet_idx: int):
        """移除子弹"""
        if 0 <= bullet_idx < len(self.bullet_pool.data['alive']):
            self.bullet_pool.data['alive'][bullet_idx] = 0
            if bullet_idx in self._bullet_indices:
                self._bullet_indices.remove(bullet_idx)
    
    def bullet_to_item(self, bullet_idx: int):
        """子弹转化为道具"""
        if self._item_pool and 0 <= bullet_idx < len(self.bullet_pool.data['alive']):
            bx = self.bullet_pool.data['x'][bullet_idx]
            by = self.bullet_pool.data['y'][bullet_idx]
            from ..item import ItemType
            self._item_pool.spawn(bx, by, ItemType.POINT)
        self.remove_bullet(bullet_idx)

    def spawn_drop(self, x: float, y: float, **kwargs):
        """
        在指定位置生成掉落物（敌人/Boss 击破时调用）

        Args:
            x, y: 掉落位置（归一化坐标）
            **kwargs: 传给 ItemPool.spawn_drop 的参数
                      power, point, faith 等
        """
        if self._item_pool:
            self._item_pool.spawn_drop(x, y, **kwargs)

    def add_score(self, amount: int):
        """直接增加分数（击破得分等）"""
        if self._item_pool:
            self._item_pool.stats.score += amount
            if self._item_pool.stats.score > self._item_pool.stats.hiscore:
                self._item_pool.stats.hiscore = self._item_pool.stats.score

    def get_player(self) -> PlayerProxy:
        """获取玩家信息（只读代理）"""
        return self._player_proxy
    
    def get_enemies(self) -> list:
        """获取当前活跃的敌人列表"""
        if self._enemy_manager:
            return self._enemy_manager.get_active_enemies()
        return []
    
    def clear_all_bullets(self):
        """清除所有子弹"""
        self.bullet_pool.clear_all()
        self._bullet_indices.clear()

    # ==================== 敌人脚本管理 API ====================

    def add_enemy_script(self, enemy_script):
        """添加敌人脚本实例到管理列表"""
        self._enemy_scripts.append(enemy_script)

    def update_enemy_scripts(self):
        """更新所有敌人脚本（每帧调用）"""
        for enemy in self._enemy_scripts[:]:  # 使用切片避免修改列表时出错
            if not enemy.update():  # update() 返回 False 表示敌人已死亡
                self._enemy_scripts.remove(enemy)

    def get_enemy_scripts(self) -> List[Any]:
        """获取所有活跃的敌人脚本"""
        return self._enemy_scripts

    def clear_enemy_scripts(self):
        """清除所有敌人脚本"""
        self._enemy_scripts.clear()

    # ==================== 音频 API ====================
    
    @property
    def audio(self) -> Optional[AudioManager]:
        """音频管理器（内容脚本通过此接口播放音效和 BGM）"""
        return self._audio_manager
    
    def play_se(self, name: str, volume: Optional[float] = None) -> bool:
        """播放音效（便捷方法）"""
        if self._audio_manager:
            return self._audio_manager.play_se(name, volume)
        return False
    
    def play_bgm(self, name: str, loops: int = -1, fade_ms: int = 0) -> bool:
        """播放 BGM（便捷方法）"""
        if self._audio_manager:
            return self._audio_manager.play_bgm(name, loops, fade_ms)
        return False
    
    def stop_bgm(self, fade_ms: int = 0):
        """停止 BGM"""
        if self._audio_manager:
            self._audio_manager.stop_bgm(fade_ms)
    
    def pause_bgm(self):
        """暂停 BGM"""
        if self._audio_manager:
            self._audio_manager.pause_bgm()
    
    def unpause_bgm(self):
        """恢复 BGM"""
        if self._audio_manager:
            self._audio_manager.unpause_bgm()
    
    def _resolve_sprite_id(self, bullet_type: str, color: str) -> str:
        """将弹幕类型+颜色映射到精灵 ID"""
        # 优先使用别名表（每个类型独立的颜色映射）
        type_entry = self.BULLET_ALIAS_TABLE.get(bullet_type)
        if type_entry:
            sprite_id = type_entry.get(color)
            if sprite_id:
                return sprite_id
        # Fallback: 旧版全局映射
        base = self.BULLET_TYPE_MAP.get(bullet_type, "ball_mid")
        suffix = self.COLOR_MAP.get(color, "1")
        return f"{base}{suffix}"

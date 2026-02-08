"""
音频系统 - AudioBank

提供两级音频管理：
1. GameAudioBank（全局）：游戏通用 SE 和 BGM（如 graze、pldead、pause 等）
2. StageAudioBank（关卡私有）：关卡专属 SE 和 BGM，可覆盖全局同名音频

设计原则：
- 内容层通过 ctx.audio 统一访问，不关心底层实现
- 查找顺序：Stage 私有 → Game 全局 → 警告缺失
- 支持：播放、暂停、循环、停止、音量控制、淡入淡出
"""

import os
import pygame
from typing import Optional, Dict
from enum import Enum


class AudioChannel(Enum):
    """音频通道类型"""
    BGM = "bgm"          # 背景音乐（同时只1首）
    SE = "se"             # 音效（可多个重叠）


class AudioBank:
    """
    音频资源池
    
    管理一组 SE 和 BGM。支持按名称加载/播放。
    可以作为全局 GameAudioBank 或关卡私有 StageAudioBank。
    
    用法：
        bank = AudioBank()
        bank.load_se("shoot", "assets/audio/se/se_plst00.wav")
        bank.load_se("graze", "assets/audio/se/se_graze.wav")
        bank.play_se("shoot")
    """
    
    def __init__(self, name: str = "default"):
        self.name = name
        self._se_cache: Dict[str, pygame.mixer.Sound] = {}
        self._bgm_paths: Dict[str, str] = {}
        self._se_volume: float = 1.0
        self._bgm_volume: float = 1.0
        self._initialized = False
        
        self._ensure_mixer()
    
    def _ensure_mixer(self):
        """确保 pygame.mixer 已初始化"""
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            except pygame.error:
                print(f"[AudioBank:{self.name}] mixer 初始化失败")
                return
        self._initialized = True
    
    # ==================== 加载 ====================
    
    def load_se(self, name: str, path: str) -> bool:
        """
        加载音效
        
        Args:
            name: 音效名称（用于播放时引用，如 "shoot", "graze"）
            path: 文件路径
            
        Returns:
            是否加载成功
        """
        if not self._initialized:
            return False
        
        if not os.path.exists(path):
            print(f"[AudioBank:{self.name}] SE 文件不存在: {path}")
            return False
        
        try:
            sound = pygame.mixer.Sound(path)
            sound.set_volume(self._se_volume)
            self._se_cache[name] = sound
            return True
        except pygame.error as e:
            print(f"[AudioBank:{self.name}] 加载 SE 失败 '{name}': {e}")
            return False
    
    def load_se_directory(self, directory: str, prefix_strip: str = "se_",
                          ext: str = ".wav") -> int:
        """
        批量加载目录下所有音效
        
        文件名自动转为音效名称：se_graze.wav → "graze"
        
        Args:
            directory: 音效目录
            prefix_strip: 要去掉的文件名前缀
            ext: 文件扩展名过滤
            
        Returns:
            成功加载的数量
        """
        if not os.path.isdir(directory):
            print(f"[AudioBank:{self.name}] 目录不存在: {directory}")
            return 0
        
        count = 0
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(ext):
                continue
            
            # se_graze.wav → "graze"
            name = filename[:-len(ext)]
            if prefix_strip and name.startswith(prefix_strip):
                name = name[len(prefix_strip):]
            
            path = os.path.join(directory, filename)
            if self.load_se(name, path):
                count += 1
        
        return count
    
    def load_bgm(self, name: str, path: str) -> bool:
        """
        注册 BGM（不立即加载到内存，播放时才加载）
        
        Args:
            name: BGM 名称
            path: 文件路径
        """
        if not os.path.exists(path):
            print(f"[AudioBank:{self.name}] BGM 文件不存在: {path}")
            return False
        
        self._bgm_paths[name] = path
        return True
    
    def load_bgm_directory(self, directory: str, exts: tuple = (".ogg", ".mp3", ".wav")) -> int:
        """
        批量注册目录下所有 BGM
        
        Args:
            directory: BGM 目录
            exts: 支持的扩展名
            
        Returns:
            注册数量
        """
        if not os.path.isdir(directory):
            return 0
        
        count = 0
        for filename in sorted(os.listdir(directory)):
            if not any(filename.endswith(e) for e in exts):
                continue
            name = os.path.splitext(filename)[0]
            path = os.path.join(directory, filename)
            if self.load_bgm(name, path):
                count += 1
        
        return count
    
    # ==================== SE 播放 ====================
    
    def play_se(self, name: str, volume: Optional[float] = None, loops: int = 0) -> bool:
        """
        播放音效
        
        Args:
            name: 音效名称
            volume: 音量覆盖（0.0~1.0），None 使用全局 SE 音量
            loops: 循环次数（0=播放1次，-1=无限循环）
            
        Returns:
            是否成功播放
        """
        sound = self._se_cache.get(name)
        if sound is None:
            return False
        
        if volume is not None:
            sound.set_volume(volume)
        else:
            sound.set_volume(self._se_volume)
        
        sound.play(loops=loops)
        return True
    
    def stop_se(self, name: str):
        """停止指定音效"""
        sound = self._se_cache.get(name)
        if sound:
            sound.stop()
    
    def stop_all_se(self):
        """停止所有音效"""
        for sound in self._se_cache.values():
            sound.stop()
    
    # ==================== BGM 播放 ====================
    
    def play_bgm(self, name: str, loops: int = -1, fade_ms: int = 0,
                  start: float = 0.0) -> bool:
        """
        播放 BGM（停止当前 BGM 并切换）
        
        Args:
            name: BGM 名称
            loops: 循环次数（-1=无限循环，0=播放1次）
            fade_ms: 淡入时间（毫秒）
            start: 起始位置（秒）
            
        Returns:
            是否成功播放
        """
        if not self._initialized:
            return False
        
        path = self._bgm_paths.get(name)
        if path is None:
            return False
        
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self._bgm_volume)
            if fade_ms > 0:
                pygame.mixer.music.play(loops=loops, start=start, fade_ms=fade_ms)
            else:
                pygame.mixer.music.play(loops=loops, start=start)
            return True
        except pygame.error as e:
            print(f"[AudioBank:{self.name}] 播放 BGM 失败 '{name}': {e}")
            return False
    
    def pause_bgm(self):
        """暂停 BGM"""
        if self._initialized:
            pygame.mixer.music.pause()
    
    def unpause_bgm(self):
        """恢复 BGM"""
        if self._initialized:
            pygame.mixer.music.unpause()
    
    def stop_bgm(self, fade_ms: int = 0):
        """
        停止 BGM
        
        Args:
            fade_ms: 淡出时间（毫秒），0=立即停止
        """
        if not self._initialized:
            return
        if fade_ms > 0:
            pygame.mixer.music.fadeout(fade_ms)
        else:
            pygame.mixer.music.stop()
    
    def is_bgm_playing(self) -> bool:
        """BGM 是否正在播放"""
        if not self._initialized:
            return False
        return pygame.mixer.music.get_busy()
    
    # ==================== 音量控制 ====================
    
    def set_se_volume(self, volume: float):
        """设置全局 SE 音量（0.0 ~ 1.0）"""
        self._se_volume = max(0.0, min(1.0, volume))
        for sound in self._se_cache.values():
            sound.set_volume(self._se_volume)
    
    def set_bgm_volume(self, volume: float):
        """设置 BGM 音量（0.0 ~ 1.0）"""
        self._bgm_volume = max(0.0, min(1.0, volume))
        if self._initialized:
            pygame.mixer.music.set_volume(self._bgm_volume)
    
    @property
    def se_volume(self) -> float:
        return self._se_volume
    
    @property
    def bgm_volume(self) -> float:
        return self._bgm_volume
    
    # ==================== 查询 ====================
    
    def has_se(self, name: str) -> bool:
        """是否已加载某个 SE"""
        return name in self._se_cache
    
    def has_bgm(self, name: str) -> bool:
        """是否已注册某个 BGM"""
        return name in self._bgm_paths
    
    def get_se_names(self) -> list:
        """获取所有已加载的 SE 名称"""
        return list(self._se_cache.keys())
    
    def get_bgm_names(self) -> list:
        """获取所有已注册的 BGM 名称"""
        return list(self._bgm_paths.keys())
    
    # ==================== 清理 ====================
    
    def clear(self):
        """释放所有音频资源"""
        self.stop_all_se()
        self._se_cache.clear()
        self._bgm_paths.clear()


class GameAudioBank(AudioBank):
    """
    全局游戏音频池
    
    持有整个游戏生命周期内通用的音效和 BGM。
    由 main.py 在启动时初始化。
    
    典型全局 SE：
        - shoot:     自机射击
        - graze:     擦弹
        - pldead:    自机死亡
        - extend:    续命
        - powerup:   满P
        - pause:     暂停
        - select:    菜单选择
        - cancel:    菜单取消
        - ok:        菜单确认
        - cardget:   符卡取得
        - timeout:   超时
        - item:      道具回收
        - bomb:      Bomb
        - damage:    敌人受伤
        - explode:   敌人爆炸
        - kira:      星星音效
        - lazer:     激光
    """
    
    # 音效名 → 文件名映射（常用预设）
    DEFAULT_SE_MAP = {
        "shoot":    "se_plst00.wav",
        "graze":    "se_graze.wav",
        "pldead":   "se_pldead00.wav",
        "extend":   "se_extend.wav",
        "powerup":  "se_powerup.wav",
        "pause":    "se_pause.wav",
        "select":   "se_select00.wav",
        "cancel":   "se_cancel00.wav",
        "ok":       "se_ok00.wav",
        "cardget":  "se_cardget.wav",
        "timeout":  "se_timeout.wav",
        "item":     "se_item00.wav",
        "bomb":     "se_nep00.wav",
        "damage":   "se_damage00.wav",
        "explode":  "se_explode.wav",
        "kira":     "se_kira00.wav",
        "lazer":    "se_lazer00.wav",
        "bonus":    "se_bonus.wav",
        "enep":     "se_enep00.wav",
        "invalid":  "se_invalid.wav",
        "warning":  "se_hyz_warning.wav",
        "charge":   "se_hyz_charge00.wav",
    }
    
    def __init__(self):
        super().__init__(name="game")
    
    def load_defaults(self, se_dir: str = "assets/audio/se",
                      bgm_dir: str = "assets/audio/music"):
        """
        加载默认的全局音效和 BGM
        
        Args:
            se_dir: 音效目录
            bgm_dir: BGM 目录
        """
        # 加载预设的常用 SE
        loaded = 0
        for name, filename in self.DEFAULT_SE_MAP.items():
            path = os.path.join(se_dir, filename)
            if self.load_se(name, path):
                loaded += 1
        
        print(f"[GameAudioBank] 加载 {loaded}/{len(self.DEFAULT_SE_MAP)} 个全局 SE")
        
        # 注册 BGM 目录
        bgm_count = self.load_bgm_directory(bgm_dir)
        if bgm_count > 0:
            print(f"[GameAudioBank] 注册 {bgm_count} 个 BGM")


class StageAudioBank(AudioBank):
    """
    关卡私有音频池
    
    每个关卡可以有自己的专属音效和 BGM。
    在关卡加载时初始化，关卡结束时释放。
    
    当 Stage 私有 bank 有同名 SE 时，覆盖全局 bank。
    
    典型用途：
        - 关卡专属 BGM（道中/Boss）
        - Boss 专属符卡音效
        - 特殊弹幕音效
    """
    
    def __init__(self, stage_id: str):
        super().__init__(name=f"stage:{stage_id}")
        self.stage_id = stage_id
    
    @classmethod
    def from_directory(cls, stage_id: str, stage_dir: str) -> 'StageAudioBank':
        """
        从关卡目录自动加载音频
        
        目录结构约定：
            game_content/stages/stageN/
                audio/
                    se/          ← 关卡专属 SE
                    music/       ← 关卡专属 BGM
        
        Args:
            stage_id: 关卡 ID
            stage_dir: 关卡目录路径
        """
        bank = cls(stage_id)
        
        # 加载关卡专属 SE
        se_dir = os.path.join(stage_dir, "audio", "se")
        if os.path.isdir(se_dir):
            count = bank.load_se_directory(se_dir)
            if count > 0:
                print(f"[StageAudioBank:{stage_id}] 加载 {count} 个关卡 SE")
        
        # 注册关卡专属 BGM
        bgm_dir = os.path.join(stage_dir, "audio", "music")
        if os.path.isdir(bgm_dir):
            count = bank.load_bgm_directory(bgm_dir)
            if count > 0:
                print(f"[StageAudioBank:{stage_id}] 注册 {count} 个关卡 BGM")
        
        return bank


class AudioManager:
    """
    音频管理器 - 统一调度全局和关卡音频
    
    查找优先级：Stage 私有 > Game 全局
    
    这是提供给 StageContext 的音频接口。
    内容脚本通过 ctx.audio 访问。
    """
    
    def __init__(self, game_bank: GameAudioBank):
        self._game_bank = game_bank
        self._stage_bank: Optional[StageAudioBank] = None
    
    @property
    def game_bank(self) -> GameAudioBank:
        """全局音频池"""
        return self._game_bank
    
    @property
    def stage_bank(self) -> Optional[StageAudioBank]:
        """当前关卡音频池"""
        return self._stage_bank
    
    def set_stage_bank(self, bank: Optional[StageAudioBank]):
        """
        设置当前关卡音频池（关卡切换时调用）
        
        传入 None 表示清除关卡音频。
        """
        # 先清理旧的
        if self._stage_bank is not None:
            self._stage_bank.clear()
        self._stage_bank = bank
    
    # ==================== SE ====================
    
    def play_se(self, name: str, volume: Optional[float] = None, loops: int = 0) -> bool:
        """
        播放音效（Stage 私有优先，fallback 到全局）
        
        Args:
            name: 音效名称
            volume: 音量 (0.0~1.0)
            loops: 循环次数
        """
        # 先查 stage bank
        if self._stage_bank and self._stage_bank.has_se(name):
            return self._stage_bank.play_se(name, volume, loops)
        # fallback 到 game bank
        return self._game_bank.play_se(name, volume, loops)
    
    def stop_se(self, name: str):
        """停止音效"""
        if self._stage_bank and self._stage_bank.has_se(name):
            self._stage_bank.stop_se(name)
        self._game_bank.stop_se(name)
    
    def has_se(self, name: str) -> bool:
        """是否有某个 SE（任一 bank 有即可）"""
        if self._stage_bank and self._stage_bank.has_se(name):
            return True
        return self._game_bank.has_se(name)
    
    # ==================== BGM ====================
    
    def play_bgm(self, name: str, loops: int = -1, fade_ms: int = 0,
                  start: float = 0.0) -> bool:
        """
        播放 BGM（Stage 私有优先）
        
        Args:
            name: BGM 名称
            loops: 循环
            fade_ms: 淡入
            start: 起始位置
        """
        if self._stage_bank and self._stage_bank.has_bgm(name):
            return self._stage_bank.play_bgm(name, loops, fade_ms, start)
        return self._game_bank.play_bgm(name, loops, fade_ms, start)
    
    def pause_bgm(self):
        """暂停 BGM"""
        self._game_bank.pause_bgm()
    
    def unpause_bgm(self):
        """恢复 BGM"""
        self._game_bank.unpause_bgm()
    
    def stop_bgm(self, fade_ms: int = 0):
        """停止 BGM"""
        self._game_bank.stop_bgm(fade_ms)
    
    def is_bgm_playing(self) -> bool:
        """BGM 是否在播放"""
        return self._game_bank.is_bgm_playing()
    
    # ==================== 全局音量 ====================
    
    def set_se_volume(self, volume: float):
        """设置 SE 音量"""
        self._game_bank.set_se_volume(volume)
        if self._stage_bank:
            self._stage_bank.set_se_volume(volume)
    
    def set_bgm_volume(self, volume: float):
        """设置 BGM 音量"""
        self._game_bank.set_bgm_volume(volume)
        if self._stage_bank:
            self._stage_bank.set_bgm_volume(volume)
    
    # ==================== 清理 ====================
    
    def cleanup(self):
        """清理所有音频资源"""
        if self._stage_bank:
            self._stage_bank.clear()
            self._stage_bank = None
        self._game_bank.clear()

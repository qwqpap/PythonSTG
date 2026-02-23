"""
物部布都 (Tao) 自机脚本 (v3)

机制特点：
- 子弹全由两侧的僚机(coplane)射出。
- 所有子弹（无论高速低速）都自带自动瞄准。
- 高速状态僚机距离较远，火力略分散；低速状态僚机拉近，子弹更加密集。
"""
import sys
import os

# 将项目根目录加入路径，方便相对导入引擎模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from src.game.player.player_script import PlayerScript


class TaoScript(PlayerScript):
    """物部布都 (Tao)"""

    def on_init(self):
        self.fire_timer = 0.0
        # 僚机：高速时在两侧外展，低速时贴近主机
        # 根据 tao 的 config.json，其 option_anim 叫做 "coplane"
        self.spawn_option("coplane", offset_x=-0.25, offset_y=0.03,
                          focused_offset=(-0.12, 0.05))
        self.spawn_option("coplane", offset_x=0.25, offset_y=0.03,
                          focused_offset=(0.12, 0.05))

    def on_update(self, dt):
        if self.fire_timer > 0:
            self.fire_timer -= dt

    def on_shoot(self, is_focused):
        if self.fire_timer > 0:
            return
        
        # 4发每秒(按60帧计，即间隔4帧，射速较快)
        self.fire_timer = 4.0 / 60.0

        if is_focused:
            # 低速：全部由僚机向前集中射击，制导能力极强，伤害高但弹幕略少
            if len(self.options) >= 2:
                # 左僚机发射，完全正向，加强制导
                self.fire_from_option(0, bullet_anim="bullet", angle=90, speed=6.5, damage=1, homing=True, homing_strength=12.0)
                self.fire_from_option(0, bullet_anim="bullet", angle=88, speed=6.5, damage=1, homing=True, homing_strength=12.0)
                
                # 右僚机发射
                self.fire_from_option(1, bullet_anim="bullet", angle=90, speed=6.5, damage=1, homing=True, homing_strength=12.0)
                self.fire_from_option(1, bullet_anim="bullet", angle=92, speed=6.5, damage=1, homing=True, homing_strength=12.0)
        else:
            # 高速：由僚机发射较多扇形散弹，大范围制导索敌，覆盖面广
            if len(self.options) >= 2:
                # 左僚机发射
                self.fire_from_option(0, bullet_anim="bullet", angle=85, speed=5.5, damage=2, homing=True, homing_strength=7.0)
                self.fire_from_option(0, bullet_anim="bullet", angle=95, speed=5.5, damage=2, homing=True, homing_strength=7.0)
                self.fire_from_option(0, bullet_anim="bullet", angle=105, speed=5.5, damage=2, homing=True, homing_strength=7.0)
                
                # 右僚机发射
                self.fire_from_option(1, bullet_anim="bullet", angle=95, speed=5.5, damage=2, homing=True, homing_strength=7.0)
                self.fire_from_option(1, bullet_anim="bullet", angle=85, speed=5.5, damage=2, homing=True, homing_strength=7.0)
                self.fire_from_option(1, bullet_anim="bullet", angle=75, speed=5.5, damage=2, homing=True, homing_strength=7.0)

    def on_bomb(self, is_focused):
        # 通用符卡无敌逻辑
        self.player.invincible_timer = 5.0
        self.player.spell_cooldown = 5.0
        return True

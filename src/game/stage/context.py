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
import numpy as np
import inspect
from collections import deque
from typing import Optional, Any, Dict, List, Mapping

from .spellcard import SpellCardContext
from ..audio import AudioManager
from ..events import EventBus, EventBusError, LifecycleEvent
from ..bullet.batch import BulletSnapshot, normalize_scalar
from ..state import RunState, TimeControl
from ..bullet.tags import BOMB_PROTECTED_TAGS
from ..bullet import (
    FLAG_BOUNCE_X, FLAG_BOUNCE_Y, FLAG_IS_EMITTER, FLAG_RENDER_ANGLE_LOCKED,
    CURVE_NONE, CURVE_SIN_SPEED, CURVE_SIN_ANGLE, CURVE_COS_SPEED, CURVE_LINEAR_SPEED,
)


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

    @property
    def is_bombing(self) -> bool:
        check = getattr(self._player, 'is_bomb_power_active', None)
        return bool(check()) if check is not None else bool(
            getattr(self._player, 'bomb_power_timer', 0.0) > 0,
        )


class StageContext(SpellCardContext):
    AUTHORING_TRACE_LIMIT = 4096
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
                 audio_manager: Optional[AudioManager] = None,
                 background_renderer=None,
                 event_bus: EventBus | None = None,
                 run_state: RunState | None = None,
                 particle_pool=None):
        self.run_state = run_state if run_state is not None else RunState()
        self.time_control = TimeControl()
        self.bullet_pool = bullet_pool
        self._player = player
        self._player_proxy = PlayerProxy(player)
        self._enemy_manager = enemy_manager
        self._laser_pool = laser_pool
        self._item_pool = item_pool
        self._particle_pool = particle_pool
        self._audio_manager = audio_manager
        self._background_renderer = background_renderer
        self._enemy_scripts: List[Any] = []
        # Sparse authored-stage state. These are semantic controller records,
        # never per-bullet callbacks or scene-tree bullet objects.
        self._authored_node_positions: Dict[str, tuple[float, float]] = {}
        self._authored_node_properties: Dict[str, Dict[str, Any]] = {}
        self._timeline_events = deque(maxlen=self.AUTHORING_TRACE_LIMIT)
        self._background_transitions: List[Dict[str, Any]] = []
        self._lifecycle_trace = deque(maxlen=self.AUTHORING_TRACE_LIMIT)
        self._runtime_frame = 0
        self.seed = 0
        self._timeline_origin = 0
        self._authoring_unit_origins: Dict[str, int] = {}
        self.authoring_stage_id = None
        self._authoring_trace = deque(maxlen=self.AUTHORING_TRACE_LIMIT)
        self._authoring_trace_dropped = 0
        self._script_event_handlers: Dict[str, Any] = {}
        self._reaction_actions: Dict[str, Any] = {}
        self._event_bus: EventBus | None = None
        self._event_subscriptions: list[Any] = []
        self._bullet_conversions = {}

        if not StageContext._aliases_loaded:
            StageContext.load_bullet_aliases()
        if event_bus is not None:
            self.bind_event_bus(event_bus)

    @property
    def difficulty(self):
        return self.run_state.difficulty

    @difficulty.setter
    def difficulty(self, value):
        self.run_state.difficulty = value

    @property
    def player_shot(self):
        return self.run_state.player_shot

    @property
    def rank(self):
        return self.run_state.rank

    def stop_time(self, *domains):
        """Pause selected systems; actor tasks continue so they can release it.

        Use ``with ctx.stop_time(): await ctx.wait(60)`` for one scope. The
        default includes player/projectiles/background/effects/Boss timer, not
        actor scripts or items. For bullet-only slow motion use set_time_scale.
        """
        return self.time_control.stop(*domains)

    def is_time_stopped(self, domain):
        return self.time_control.is_stopped(domain)

    # ==================== 非碰撞粒子 API ====================

    def emit_particles(self, effect, x, y, **kwargs):
        """Emit a numeric batch; see ParticleEffect and ParticlePool.emit.

        Velocity is units/second, acceleration units/second squared. Returned
        ParticleGroup reports actual emission and capacity loss. No collision,
        graze, bullet clearing or per-particle script task is involved.
        """
        if self._particle_pool is None:
            raise RuntimeError('particle emission requires a bound ParticlePool')
        return self._particle_pool.emit(effect, x, y, **kwargs)

    def clear_particles(self, group=None):
        if self._particle_pool is None:
            raise RuntimeError('particle clearing requires a bound ParticlePool')
        return self._particle_pool.clear(group)

    def read_particles(self, group=None):
        if self._particle_pool is None:
            raise RuntimeError('particle reading requires a bound ParticlePool')
        return self._particle_pool.read(group)

    def transform_particles(self, group, **kwargs):
        """One whole-group update for advanced NumPy/Numba content formulas."""
        if self._particle_pool is None:
            raise RuntimeError('particle transform requires a bound ParticlePool')
        return self._particle_pool.transform(group, **kwargs)

    def count_particles(self, group=None):
        if self._particle_pool is None:
            return 0
        return (self._particle_pool.count if group is None
                else self._particle_pool.count_group(group))

    # ==================== 子弹 API ====================

    def capture_bullets(self, indices):
        return self.bullet_pool.capture_group(indices)

    def select_bullets(self, *, tag: int | None = None, region=None):
        """Capture the current selection, not future bullets with the same tag."""
        return self.bullet_pool.select_bullets(tag=tag, region=self._bullet_region(region))

    @staticmethod
    def _bullet_region(region):
        if region is None:
            return None
        values = dict(region)
        if 'angle' in values:
            values['angle'] = math.radians(values['angle'])
        return values

    def count_bullets(self, group=None, *, tag: int | None = None):
        return self.bullet_pool.count_bullets(group, tag=tag)

    def read_bullets(self, group=None, *, tag=None, region=None, fields=None):
        """Detached arrays in author units: degrees and author speed/second.

        Field names follow the numerical pool (pos, vel, acc, angle, speed).
        Write computed arrays back using snapshot.group, including after wait.
        """
        snapshot = self.bullet_pool.read_bullets(
            group, tag=tag, region=self._bullet_region(region), fields=fields,
        )
        values = dict(snapshot.fields)
        for name in ('vel', 'speed', 'acc', 'speed_accel'):
            if name in values:
                values[name] = values[name] * 60.0
        if 'angle' in values:
            values['angle'] = np.rad2deg(values['angle'])
        return BulletSnapshot(snapshot.group, values)

    def run_bullet_rule(self, rule, group=None, *, tag=None, fields=None, frames=None):
        """One synchronous snapshot -> numerical rule -> write per owner frame.

        Schedule with enemy.spawn_task(...) for enemy lifetime, or ctx.spawn_task
        for stage lifetime. Fixed empty groups finish; dynamic tags can await
        future births. The callable returns transform_bullets keyword values.
        """
        if not callable(rule):
            raise TypeError('bullet rule must be a synchronous batch callable')
        if frames is not None and (isinstance(frames, bool) or not isinstance(frames, int) or frames < 0):
            raise ValueError('bullet rule frames must be a non-negative integer')
        scope_generation = self.bullet_pool.scope_generation

        async def run():
            elapsed = 0
            while self.bullet_pool.scope_generation == scope_generation and (frames is None or elapsed < frames):
                snapshot = self.read_bullets(group, tag=tag, fields=fields)
                if not len(snapshot) and group is not None:
                    return
                if len(snapshot):
                    updates = rule(snapshot)
                    if not isinstance(updates, Mapping):
                        raise TypeError('bullet rule must return transform keyword values')
                    self.transform_bullets(snapshot.group, **updates)
                elapsed += 1
                await self.wait(1)
        return run()

    def bullet_sprite_index(self, bullet_type, color='red'):
        """Resolve an author-facing bullet name for heterogeneous sprite arrays."""
        return self.bullet_pool.register_sprite(self._resolve_sprite_id(bullet_type, color))

    def clear_bullet_group(self, group=None, *, tag: int | None = None, reason='phase_cleared'):
        return self.bullet_pool.remove_bullets(group, tag=tag, reason=reason)

    def transform_bullets(self, group=None, *, tag: int | None = None, region=None,
                          speed=None, angle=None, aim=None, accel=None,
                          time_scale=None, bullet_type=None, color='red',
                          render_scale=None, cooldown: int = 0, cooldown_key=None,
                          positions=None, velocities=None, vector_accel=None,
                          sprite_indices=None, angle_accel=None):
        """Batch action; author angles are degrees, cooldown is game frames."""
        return self.bullet_pool.transform_bullets(
            group, tag=tag, region=self._bullet_region(region),
            speed=None if speed is None else np.asarray(speed) / 60.0,
            angle=None if angle is None else np.deg2rad(angle),
            aim=aim, speed_accel=None if accel is None else np.asarray(accel) / 60.0,
            time_scale=time_scale,
            sprite_id=None if bullet_type is None else self._resolve_sprite_id(bullet_type, color),
            render_scale=render_scale, cooldown=cooldown / 60.0, cooldown_key=cooldown_key,
            positions=positions,
            velocities=None if velocities is None else np.asarray(velocities) / 60.0,
            vector_accel=None if vector_accel is None else np.asarray(vector_accel) / 60.0,
            sprite_indices=sprite_indices,
            motion_angular_accel=None if angle_accel is None else np.deg2rad(angle_accel),
        )

    def set_bullet_behavior(self, group=None, *, tag: int | None = None, stages=()):
        converted = []
        supported = {'frames', 'speed', 'angle', 'aim', 'accel', 'turn_rate',
                     'bounce_x', 'bounce_y', 'bullet_type', 'color', 'vector_accel',
                     'homing', 'max_turn_rate', 'wrap_x', 'wrap_y'}
        for stage in stages:
            values = dict(stage)
            unknown = set(values) - supported
            if unknown:
                raise TypeError(f"unsupported bullet stage fields: {', '.join(sorted(unknown))}")
            frame_count = values.pop('frames', None)
            values['duration'] = None if frame_count is None else frame_count / 60.0
            for field in ('speed', 'accel'):
                if field in values:
                    values[field] /= 60.0
            if 'vector_accel' in values:
                values['vector_accel'] = np.asarray(values['vector_accel']) / 60.0
            for field in ('angle', 'turn_rate', 'max_turn_rate'):
                if field in values:
                    values[field] = math.radians(values[field])
            color = values.pop('color', 'red')
            if 'bullet_type' in values:
                values['sprite_id'] = self._resolve_sprite_id(values.pop('bullet_type'), color)
            converted.append(values)
        return self.bullet_pool.set_bullet_behavior(group, tag=tag, stages=converted)

    def convert_bullets_on_end(self, tag, enemy_class, *, reasons=('expired',)):
        """Convert each complete mother record into one real EnemyScript.

        Returns a cancellation token. Births are consumed after stage update;
        on_spawn/run first advance on the next stage frame, as ordinary enemies.
        """
        from .enemy_script import EnemyScript
        if not isinstance(enemy_class, type) or not issubclass(enemy_class, EnemyScript):
            raise TypeError('conversion requires an EnemyScript class')
        token = self.bullet_pool.terminations.register(tag, reasons)
        self._bullet_conversions[token] = enemy_class
        return token

    def cancel_bullet_conversion(self, token):
        self._bullet_conversions.pop(token, None)
        return self.bullet_pool.terminations.unregister(token)

    def flush_bullet_conversions(self):
        count = 0
        for token, enemy_class in tuple(self._bullet_conversions.items()):
            if token not in self.bullet_pool.terminations:
                self._bullet_conversions.pop(token, None)
                continue
            for batch in self.bullet_pool.terminations.drain(token):
                for index, (x, y) in enumerate(batch.positions):
                    enemy = enemy_class()
                    enemy.bind(self, x=float(x), y=float(y))
                    enemy.source_angle = float(np.rad2deg(batch.angles[index]))
                    enemy.source_velocity = tuple(float(v) * 60.0 for v in batch.velocities[index])
                    enemy.source_tag = batch.tag
                    enemy.source_end_reason = batch.reason
                    enemy.start()
                    self.add_enemy_script(enemy)
                    count += 1
        return count

    def split_bullets_on_end(self, tag: int, *, count: int = 8, speed: float = 2.0,
                             bullet_type: str = 'ball_m', color: str = 'red',
                             reasons=('expired',), child_tag: int = 0):
        self.bullet_pool.register_termination_batch_reaction(tag, {
            'action': 'split', 'count': count, 'speed': speed / 60.0,
            'sprite_id': self._resolve_sprite_id(bullet_type, color),
            'reasons': tuple(reasons), 'child_tag': child_tag,
        })

    def create_bullet(self, x: float, y: float, angle: float, speed: float,
                      bullet_type: str = "ball_m", color: str = "red",
                      accel: float = 0.0, angle_accel: float = 0.0,
                      owner=None,
                      tag: int = 0,
                      friction: float = 0.0,
                      time_scale: float = 1.0,
                      bounce_x: bool = False,
                      bounce_y: bool = False,
                      spin: float = 0.0,
                      render_angle: float | None = None,
                      render_scale: float = 1.0,
                      max_lifetime: float = 0.0,
                      collision_radius: float = 0.0,
                      curve_type: int = CURVE_NONE,
                      curve_params: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
                      delay: int = 0,
                      vector_accel=None,
                      **kwargs) -> int:
        """
        创建一颗直线运动子弹。

        Args:
            x, y: 位置（归一化坐标）
            angle: 角度（度，0=右，90=上，-90=下）
            speed: 作者速度标度。
            accel: 每秒改变 ``speed`` 的作者标度（正值加速、负值减速）。
            angle_accel: 运动角的角加速度（度/秒²）；不影响 ``spin``。
            bullet_type: 弹幕类型
            color: 颜色
            tag: 分组标签
            friction: 摩擦/阻尼系数
            time_scale: 时间缩放 (1.0=正常, 0=冻结)
            bounce_x/bounce_y: 边界反弹
            spin: 渲染角角速度（度/秒）
            render_angle: 初始渲染朝向（度，None=跟随运动角）
            render_scale: 渲染尺寸倍率
            max_lifetime: 最长存活秒数（0=无限）
            collision_radius: 归一化碰撞半径
            curve_type: 内置曲线类型 (CURVE_SIN_SPEED 等)
            curve_params: 曲线参数 (amplitude, frequency, phase, base)

        ``accel`` 与 ``angle_accel`` 都受 ``time_scale`` 影响。单发与
        :meth:`create_bullets_batch` 使用相同的单位转换和半隐式 Euler
        更新：先更新速度/角速度，再推进本帧位置与朝向。
        """
        sprite_id = self._resolve_sprite_id(bullet_type, color)
        angle_rad = math.radians(angle)

        # 组装 flags
        flags = FLAG_RENDER_ANGLE_LOCKED
        if bounce_x:
            flags |= FLAG_BOUNCE_X
        if bounce_y:
            flags |= FLAG_BOUNCE_Y
        if spin != 0.0 or render_angle is not None:
            flags &= ~FLAG_RENDER_ANGLE_LOCKED

        ra = math.radians(render_angle) if render_angle is not None else None
        if vector_accel is not None:
            if 'acc' in kwargs:
                raise ValueError('vector_accel and raw pool acc cannot both be set')
            kwargs['acc'] = np.asarray(vector_accel) / 60.0

        idx = self.bullet_pool.spawn_bullet(
            x=x, y=y,
            angle=angle_rad,
            speed=speed / 60.0,
            speed_accel=accel / 60.0,
            motion_angular_accel=math.radians(angle_accel),
            sprite_id=sprite_id,
            tag=tag,
            friction=friction,
            time_scale=time_scale,
            flags=flags,
            angular_vel=math.radians(spin),
            render_angle=ra,
            render_scale=render_scale,
            max_lifetime=max_lifetime,
            radius=collision_radius,
            curve_type=curve_type,
            curve_param=curve_params,
            delay=delay,
            **kwargs,
        )
        if idx >= 0:
            self.publish_lifecycle(
                "bullet.spawned",
                {"tag": int(tag), "count": 1},
                owner=None if int(tag) == 0 else str(int(tag)),
                count=1,
                representative_ids=(str(int(idx)),),
            )
        return idx

    def create_bullets_batch(
        self,
        *,
        positions,
        angles,
        speeds,
        bullet_type: str = "ball_m",
        color: str = "red",
        sprite_id: str = None,
        sprite_idx: int = -1,
        accel: float = 0.0,
        angle_accel: float = 0.0,
        tag: int = 0,
        friction: float = 0.0,
        time_scale: float = 1.0,
        bounce_x: bool = False,
        bounce_y: bool = False,
        spin: float = 0.0,
        render_angle: float = None,
        max_lifetime: float = 0.0,
        render_scale: float = 1.0,
        collision_radius: float = 0.0,
        curve_type: int = 0,
        curve_params: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
        vector_accel=(0.0, 0.0),
    ) -> np.ndarray:
        """Create a heterogeneous formal-runtime burst in one pool operation.

        This is the batch equivalent of :meth:`create_bullet`.  In particular,
        ``accel`` is author speed units/second and ``angle_accel`` is
        degrees/second² for every bullet in the burst.
        """
        position_array = np.asarray(positions, dtype=np.float32)
        if position_array.size == 0:
            position_array = position_array.reshape((0, 2))
        if position_array.ndim != 2 or position_array.shape[1] != 2:
            raise ValueError("positions must have shape (count, 2)")
        count = len(position_array)
        angle_array = normalize_scalar(angles, count, 'angles')
        speed_array = normalize_scalar(speeds, count, 'speeds')

        resolved_sprite_id = sprite_id or self._resolve_sprite_id(bullet_type, color)
        flags = np.full(count, FLAG_RENDER_ANGLE_LOCKED, dtype=np.uint16)
        flags[normalize_scalar(bounce_x, count, 'bounce_x', dtype=np.uint8) != 0] |= FLAG_BOUNCE_X
        flags[normalize_scalar(bounce_y, count, 'bounce_y', dtype=np.uint8) != 0] |= FLAG_BOUNCE_Y
        spinning = normalize_scalar(spin, count, 'spin') != 0
        if render_angle is not None:
            spinning[:] = True
        flags[spinning] &= np.uint16(65535 ^ FLAG_RENDER_ANGLE_LOCKED)

        angle_radians = np.deg2rad(angle_array).astype(np.float32, copy=False)
        render_angles = None
        if render_angle is not None:
            render_angles = np.deg2rad(normalize_scalar(render_angle, count, 'render_angle'))
        speed_per_frame = speed_array / 60.0
        indices = self.bullet_pool.spawn_bullets_batch(
            positions=position_array, angles=angle_radians, speeds=speed_per_frame,
            speed_accel=np.asarray(accel) / 60.0, motion_angular_accel=np.deg2rad(angle_accel),
            acc=np.asarray(vector_accel) / 60.0, sprite_id=resolved_sprite_id, sprite_idx=sprite_idx,
            radius=collision_radius, tag=tag, friction=friction, time_scale=time_scale, flags=flags,
            angular_vel=np.deg2rad(spin), render_angles=render_angles, max_lifetime=max_lifetime,
            render_scale=render_scale, curve_type=curve_type, curve_param=curve_params,
        )

        result = np.asarray(indices, dtype=np.intp)
        for actual_tag in np.unique(self.bullet_pool.data['tag'][result]):
            tagged = result[self.bullet_pool.data['tag'][result] == actual_tag]
            self.publish_lifecycle(
                "bullet.spawned",
                {
                    "tag": int(actual_tag),
                    "count": int(tagged.size),
                },
                owner=None if int(actual_tag) == 0 else str(int(actual_tag)),
                count=int(tagged.size),
                representative_ids=tuple(str(int(index)) for index in tagged[:8]),
            )
        return result

    def create_polar_bullet(self, center, orbit_radius: float, theta: float,
                            radial_speed: float = 0.0, angular_velocity: float = 0.0,
                            bullet_type: str = "ball_m", color: str = "red",
                            render_mode: str = "velocity", angle_offset: float = 0.0,
                            collision_radius: float = 0.0, owner=None, **kwargs) -> int:
        """
        创建极坐标运动子弹。角度单位全部为"度"。
        """
        sprite_id = self._resolve_sprite_id(bullet_type, color)

        if not hasattr(self.bullet_pool, 'spawn_polar_bullet'):
            raise RuntimeError("Current bullet pool does not support polar bullets")

        idx = self.bullet_pool.spawn_polar_bullet(
            center=center,
            orbit_radius=orbit_radius,
            theta=math.radians(theta),
            radial_speed=radial_speed,
            angular_velocity=math.radians(angular_velocity),
            sprite_id=sprite_id,
            render_mode=render_mode,
            angle_offset=math.radians(angle_offset),
            hit_radius=collision_radius,
            **kwargs,
        )
        return idx

    def create_orbit_bullet(self, *args, **kwargs) -> int:
        """`create_polar_bullet` 的语义化别名。"""
        return self.create_polar_bullet(*args, **kwargs)

    def remove_bullet(self, bullet_idx: int, *, reason: str = "removed"):
        """Terminate and recycle a bullet; removal is not natural expiry."""
        return self.bullet_pool.remove_bullets(np.asarray([bullet_idx], dtype=np.intp), reason=reason)

    def remove_bullets(self, bullet_indices, *, reason: str = "phase_cleared"):
        """批量移除子弹，避免符卡清屏时逐个 list.remove 造成卡顿。"""
        if bullet_indices is None or len(bullet_indices) == 0:
            return

        return self.bullet_pool.remove_bullets(bullet_indices, reason=reason)

    def bullets_to_items(self, bullet_indices):
        """批量将子弹转为 point 道具。"""
        if bullet_indices is None or len(bullet_indices) == 0:
            return
        if not self._item_pool:
            self.remove_bullets(bullet_indices)
            return

        indices = self.bullet_pool.resolve_indices(bullet_indices)
        if indices.size == 0:
            return

        positions = self.bullet_pool.data['pos'][indices].copy()
        self._item_pool.spawn_points_from_positions(positions, attract=True)
        self.remove_bullets(indices, reason="converted")

    def bullet_to_item(self, bullet_idx: int):
        """子弹转化为道具"""
        if self._item_pool and 0 <= bullet_idx < len(self.bullet_pool.data['alive']):
            bx, by = self.bullet_pool.data['pos'][bullet_idx]
            from ..item import ItemType
            self._item_pool.spawn(float(bx), float(by), ItemType.POINT)
        self.remove_bullet(bullet_idx, reason="converted")

    def clear_all_bullets(self):
        """清除所有子弹"""
        self.bullet_pool.clear_all()
        self._bullet_conversions.clear()

    def clear_bullets_by_tag(self, tag: int, *, reason: str = "phase_cleared") -> int:
        """按标签消除所有子弹"""
        try:
            return int(self.bullet_pool.clear_by_tag(tag, reason=reason))
        except TypeError:
            # Legacy BulletPool has no formal reason parameter; retain its
            # compatibility behavior while formal pools keep the typed fact.
            return int(self.bullet_pool.clear_by_tag(tag))

    def bullets_by_tag_to_item(self, tag: int):
        """按标签将子弹转化为道具"""
        if not self._item_pool:
            self.bullet_pool.clear_by_tag(tag)
            return
        mask = (self.bullet_pool.data['alive'] == 1) & (self.bullet_pool.data['tag'] == tag)
        positions = self.bullet_pool.data['pos'][mask].copy()
        self._item_pool.spawn_points_from_positions(positions, attract=True)
        return int(self.bullet_pool.clear_by_tag(tag, reason="converted"))

    def translate_bullets_by_tag(self, tag: int, dx: float, dy: float) -> int:
        """Translate one owner group without touching other live bullets."""
        if hasattr(self.bullet_pool, "translate_by_tag"):
            return int(self.bullet_pool.translate_by_tag(tag, dx, dy))
        mask = (
            (self.bullet_pool.data['alive'] == 1)
            & (self.bullet_pool.data['tag'] == tag)
        )
        count = int(np.count_nonzero(mask))
        self.bullet_pool.data['pos'][mask, 0] += dx
        self.bullet_pool.data['pos'][mask, 1] += dy
        return count

    def set_time_scale(self, scale: float, tag: int = None):
        """设置子弹时间缩放（tag=None 影响全部）"""
        if tag is not None:
            self.bullet_pool.set_time_scale_by_tag(tag, scale)
        else:
            self.bullet_pool.set_global_time_scale(scale)

    def create_emitter(self, x: float, y: float, angle: float, speed: float,
                       callback, tag: int = 0, max_lifetime: float = 0.0,
                       friction: float = 0.0, time_scale: float = 1.0,
                       **kwargs) -> int:
        """
        创建发射器节点（不渲染、不碰撞，有运动轨迹和每帧回调）

        callback(pool, idx, x, y, lifetime)
        """
        return self.bullet_pool.spawn_emitter(
            x=x, y=y,
            angle=math.radians(angle),
            speed=speed / 60.0,
            callback=callback,
            tag=tag,
            max_lifetime=max_lifetime,
            friction=friction,
            time_scale=time_scale,
            **kwargs,
        )

    # ==================== 激光 API ====================

    def create_laser(self, x: float, y: float, angle: float,
                     l1: float, l2: float, l3: float, width: float,
                     texture_id: str = "laser1", color: Any = 1,
                     on_time: int = 30, node: float = 0.0, head: float = 0.0):
        """
        创建直线激光（单位均为归一化坐标系）

        Args:
            x, y: 激光起点
            angle: 角度（度，0=向右，90=向上）
            l1/l2/l3: 头部/身体/尾部长度
            width: 激光宽度
            texture_id: 纹理ID（laser1~laser4）
            color: 颜色索引(1~16)或颜色名（red/blue/...）
            on_time: 展开时间（帧）
            node/head: 起点/终点装饰节点大小
        """
        if self._laser_pool is None:
            raise RuntimeError("LaserPool is not bound to current StageContext")

        color_index = self._resolve_laser_color_index(color)
        return self._laser_pool.create_laser(
            x=x, y=y, angle=angle,
            l1=l1, l2=l2, l3=l3, width=width,
            texture_id=texture_id, color_index=color_index,
            on_time=on_time, node=node, head=head
        )

    def create_bent_laser(self, x: float, y: float,
                          length: int, width: float,
                          color: Any = 1, on_time: int = 30,
                          sample_rate: int = 4):
        """
        创建曲线激光（随后可通过 laser.update_head(x, y) 驱动头部轨迹）
        """
        if self._laser_pool is None:
            raise RuntimeError("LaserPool is not bound to current StageContext")

        color_index = self._resolve_laser_color_index(color)
        return self._laser_pool.create_bent_laser(
            x=x, y=y, length=length, width=width,
            color_index=color_index, on_time=on_time,
            sample_rate=sample_rate
        )

    def remove_laser(self, laser, off_time: int = 0):
        """移除单条激光。off_time>0 时渐隐，否则 1 帧内关闭。"""
        if laser is None:
            raise ValueError("laser must not be None")
        if not hasattr(laser, "turn_off"):
            raise TypeError("laser must be a Laser/BentLaser object")
        laser.turn_off(max(1, int(off_time)))

    def clear_all_lasers(self):
        """清空当前关卡中的所有激光。"""
        if self._laser_pool is None:
            raise RuntimeError("LaserPool is not bound to current StageContext")
        self._laser_pool.clear()

    # ==================== 道具 / 分数 API ====================

    def spawn_drop(self, x: float, y: float, **kwargs):
        """在指定位置生成掉落物"""
        if self._item_pool:
            self._item_pool.spawn_drop(x, y, **kwargs)

    def spawn_item(self, x, y, item_type, *, speed=None, angle=None):
        """Spawn any ItemType; optional speed is units/second, angle is degrees."""
        if self._item_pool is None:
            raise RuntimeError('ItemPool is not bound to current StageContext')
        return self._item_pool.spawn(
            x, y, item_type,
            speed=None if speed is None else speed / 60.0,
            angle=angle,
        )

    def add_score(self, amount: int):
        """直接增加分数"""
        if self._item_pool:
            self._item_pool.stats.add_score(amount)

    @property
    def item_stats(self):
        """Public run-wide scoring/power/life state; no item-pool arrays leak."""
        if self._item_pool is None:
            raise RuntimeError('ItemPool is not bound to current StageContext')
        return self._item_pool.stats

    @property
    def item_config(self):
        if self._item_pool is None:
            raise RuntimeError('ItemPool is not bound to current StageContext')
        return self._item_pool.config

    def set_item_collection_rule(self, handler):
        """Replace sparse item collection policy; None restores legacy rules."""
        if self._item_pool is None:
            raise RuntimeError('ItemPool is not bound to current StageContext')
        self._item_pool.collection_handler = handler

    def cancel_bullets_for_bomb(self, *, to_items=True):
        """Public batch Bomb cancellation, preserving protected tags/reason."""
        if to_items and self._item_pool is None:
            raise RuntimeError('Bomb item conversion requires a bound ItemPool')
        positions = self.bullet_pool.cancel_for_bomb(BOMB_PROTECTED_TAGS)
        if to_items:
            self._item_pool.spawn_points_from_positions(positions, attract=True)
        return len(positions)

    # ==================== 玩家 / 敌人 API ====================

    def get_player(self) -> PlayerProxy:
        """获取玩家信息（只读代理）"""
        return self._player_proxy

    def bind_player(self, player):
        self._player = player
        self._player_proxy = PlayerProxy(player)

    def get_enemies(self) -> list:
        """获取当前活跃的敌人列表"""
        if self._enemy_manager:
            return self._enemy_manager.get_active_enemies()
        return []

    # ==================== 敌人脚本管理 API ====================

    def add_enemy_script(self, enemy_script):
        self._enemy_scripts.append(enemy_script)

    def update_enemy_scripts(self):
        write = 0
        for i in range(len(self._enemy_scripts)):
            if self._enemy_scripts[i].update():
                self._enemy_scripts[write] = self._enemy_scripts[i]
                write += 1
        del self._enemy_scripts[write:]

    def get_enemy_scripts(self) -> List[Any]:
        return self._enemy_scripts

    def clear_enemy_scripts(self):
        for enemy in tuple(self._enemy_scripts):
            enemy.dispose()
        self._enemy_scripts.clear()

    @property
    def ctx(self):
        """Allow surviving stage-owned reactions to use the same task API."""
        return self

    @property
    def time(self):
        return self._runtime_frame

    def wait(self, frames: int):
        from ..tasks import wait_frames
        return wait_frames(frames)

    def spawn_task(self, coroutine):
        from ..tasks import spawn_task
        return spawn_task(self, coroutine)

    async def wait_event(self, event_type: str, *, owner: str | None = None,
                         timeout: int | None = None):
        """Wait for a sparse next-frame event and always release subscription."""
        if self._event_bus is None:
            raise RuntimeError("event waiting requires a bound EventBus")
        received = []

        def accept(event):
            if owner is None or event.owner == owner:
                received.append(event)

        subscription = self._event_bus.subscribe(event_type, accept)
        started = self.time
        try:
            while not received:
                if timeout is not None and self.time - started >= timeout:
                    raise TimeoutError(f"event {event_type!r} was not received within {timeout} frames")
                await self.wait(1)
            return received[0]
        finally:
            subscription.cancel()

    def update_tasks(self):
        from ..tasks import pump_tasks
        pump_tasks(self)

    def dispose(self):
        self.clear_enemy_scripts()
        group = getattr(self, '_frame_tasks', None)
        if group is not None:
            group.cancel(close=True)
        for token in tuple(self._bullet_conversions):
            self.cancel_bullet_conversion(token)
        self.bind_event_bus(None)
        self._script_event_handlers.clear()
        self._reaction_actions.clear()
        self.time_control.clear()
        if self._particle_pool is not None:
            self._particle_pool.clear()
        # Closing tasks emits their final Trace boundaries.  The manager must
        # drain these after disposal, before this context becomes unreachable.
        self.clear_authored_stage_state(preserve_authoring_trace=True)

    # ==================== 稀疏事件与生命周期 API ====================

    def set_node_position(self, node_id: str, x: float, y: float) -> None:
        if not str(node_id).strip():
            raise ValueError("node_id must be a non-empty string")
        values = (x, y)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(float(value)) for value in values):
            raise ValueError("node position must contain finite numbers")
        self._authored_node_positions[str(node_id)] = (float(x), float(y))

    def set_node_property(self, node_id: str, name: str, value: Any) -> None:
        if not str(node_id).strip() or not str(name).strip():
            raise ValueError("node_id and property name must be non-empty strings")
        self._authored_node_properties.setdefault(str(node_id), {})[str(name)] = value

    def emit_event(
        self,
        event_type: str,
        data: Any,
        *,
        owner: str | None = None,
        causal_chain=(),
    ) -> None:
        self._timeline_events.append(
            {"kind": "event", "type": str(event_type), "data": data}
        )
        if self._event_bus is not None:
            self._event_bus.emit(
                str(event_type),
                data,
                source="stage",
                owner=owner,
                causal_chain=causal_chain,
            )

    @property
    def event_bus(self) -> EventBus | None:
        return self._event_bus

    @property
    def runtime_frame(self) -> int:
        return self._runtime_frame

    def set_runtime_frame(self, frame: int) -> None:
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError("runtime frame must be a non-negative integer")
        self._runtime_frame = frame

    def set_timeline_origin(self, runtime_frame: int) -> None:
        self.set_runtime_frame(runtime_frame)
        self._timeline_origin = runtime_frame

    @property
    def timeline_frame(self) -> int:
        return max(0, self._runtime_frame - self._timeline_origin)

    def get_unit_timeline_frame(self, unit_id: str) -> int | None:
        origin = self._authoring_unit_origins.get(unit_id)
        return None if origin is None else max(0, self.timeline_frame - origin)

    def emit_authoring_trace(self, uid: str, phase: str, *, owner=None, unit_id: str | None = None) -> None:
        """Queue one sparse author-node boundary without performing I/O."""

        if not isinstance(uid, str) or not uid.strip():
            raise ValueError("authoring trace uid must be non-empty text")
        if phase not in {"start", "end"}:
            raise ValueError("authoring trace phase must be 'start' or 'end'")
        if len(self._authoring_trace) == self.AUTHORING_TRACE_LIMIT:
            self._authoring_trace_dropped += 1
        event = {"uid": uid.strip(), "phase": phase, "frame": self.timeline_frame,
                 "runtime_frame": self._runtime_frame}
        if self.authoring_stage_id:
            event['stage_id'] = self.authoring_stage_id
        if owner is not None and unit_id:
            clock = max(0, int(getattr(owner, 'time', 0)))
            origins = getattr(owner, '_pystg_trace_origins', None)
            if origins is None:
                origins = {}
                owner._pystg_trace_origins = origins
            origin = origins.setdefault(unit_id, clock)
            event.update(unit_id=unit_id, unit_frame=max(0, clock - origin))
            self._authoring_unit_origins.setdefault(unit_id, self.timeline_frame - event['unit_frame'])
        self._authoring_trace.append(event)

    def drain_authoring_trace(self, limit: int = 256) -> tuple[dict[str, Any], ...]:
        """Drain at most one bounded transport batch from the runtime queue."""

        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("authoring trace drain limit must be a positive integer")
        values = []
        for _ in range(min(limit, len(self._authoring_trace))):
            values.append(self._authoring_trace.popleft())
        return tuple(values)

    def take_authoring_trace_dropped(self) -> int:
        dropped = self._authoring_trace_dropped
        self._authoring_trace_dropped = 0
        return dropped

    def publish_lifecycle(
        self,
        event_type: str,
        payload: Any = None,
        *,
        source: str = "stage",
        owner: str | None = None,
        reason: str | None = None,
        count: int = 1,
        representative_ids=(),
        causal_chain=(),
    ) -> LifecycleEvent:
        """Publish one sparse/batch lifecycle fact through the frame boundary."""

        try:
            if self._event_bus is not None:
                event = self._event_bus.emit_lifecycle(
                    str(event_type),
                    payload,
                    source=source,
                    owner=owner,
                    reason=reason,
                    count=count,
                    representative_ids=representative_ids,
                    causal_chain=causal_chain,
                )
            else:
                event = LifecycleEvent(
                    type=str(event_type),
                    source=source,
                    frame=self._runtime_frame,
                    payload=payload,
                    owner=owner,
                    reason=reason,
                    count=count,
                    representative_ids=tuple(representative_ids),
                    causal_chain=tuple(causal_chain),
                )
        except EventBusError:
            raise
        self._lifecycle_trace.append(event)
        return event

    def flush_lifecycle_events(self) -> tuple[LifecycleEvent, ...]:
        """Convert pool batches into typed events without per-bullet callbacks."""

        published = []
        drain = getattr(self.bullet_pool, "drain_lifecycle_batches", None)
        if callable(drain):
            for batch in drain():
                payload = dict(getattr(batch, "payload", None) or {})
                payload["count"] = int(batch.count)
                if batch.representative_positions:
                    payload["representative_positions"] = [
                        [float(x), float(y)]
                        for x, y in batch.representative_positions
                    ]
                published.append(self.publish_lifecycle(
                    batch.event_type,
                    payload,
                    source=batch.source,
                    owner=batch.owner,
                    reason=batch.reason,
                    count=int(batch.count),
                    representative_ids=batch.representative_ids,
                ))
        return tuple(published)

    def drain_lifecycle_events(self) -> tuple[LifecycleEvent, ...]:
        """Return local lifecycle trace and clear it after the caller observes it."""

        self.flush_lifecycle_events()
        values = tuple(self._lifecycle_trace)
        self._lifecycle_trace.clear()
        return values

    def bind_event_bus(self, bus) -> None:
        """Route validated authored actions from a typed EventBus.

        External adapters only enqueue events.  This subscription is the
        main-thread boundary where a small, schema-validated action payload is
        applied to sparse authored stage state; it never creates bullet nodes.
        """
        if bus is self._event_bus:
            return
        for subscription in tuple(self._event_subscriptions):
            try:
                subscription.cancel()
            except Exception:
                pass
        self._event_subscriptions = []
        self._event_bus = bus
        if bus is None:
            return
        # Typed external adapters converge on the same schema-validating
        # handler at the EventBus main-thread boundary; adapters never mutate
        # stage state from their receive threads.
        for event_type in (
            "scene.action",
            "adapter.local_ipc",
            "adapter.websocket",
            "adapter.udp",
        ):
            self._event_subscriptions.append(
                bus.subscribe(event_type, self._handle_scene_action)
            )

    def _handle_scene_action(self, event: Any) -> None:
        payload = getattr(event, "payload", None)
        if not isinstance(payload, dict):
            raise ValueError("scene.action payload must be an object")
        action = payload.get("action")
        if action == "set_node_position":
            self.set_node_position(
                payload.get("node_id"), payload.get("x"), payload.get("y")
            )
            return
        if action == "set_node_property":
            self.set_node_property(
                payload.get("node_id"), payload.get("property"), payload.get("value")
            )
            return
        if action == "emit_event":
            event_type = payload.get("event_type")
            if not isinstance(event_type, str) or not event_type.strip():
                raise ValueError("emit_event requires a non-empty event_type")
            self.emit_event(event_type, payload.get("data"))
            return
        raise ValueError(f"unsupported scene.action {action!r}")

    def register_script_event_handler(self, hook: str, callback: Any) -> None:
        if not str(hook).strip() or not callable(callback):
            raise ValueError("script event handler needs a non-empty hook and callable")
        self._script_event_handlers[str(hook)] = callback

    def register_reaction_action(self, action_id: str, callback: Any) -> None:
        if not isinstance(action_id, str) or not action_id.strip() or not callable(callback):
            raise ValueError("reaction action needs a non-empty id and callable")
        self._reaction_actions[action_id.strip()] = callback

    def register_pattern_termination_reaction(
        self, owner_tag: int, spec: Mapping[str, Any]
    ) -> None:
        hook = getattr(self.bullet_pool, "register_termination_batch_reaction", None)
        if not callable(hook):
            raise RuntimeError("bullet pool does not support batch termination reactions")
        converted = dict(spec)
        if converted.get("action") == "split" and "speed" in converted:
            converted["speed"] = float(converted["speed"]) / 60.0
        hook(int(owner_tag), converted)

    def unregister_pattern_termination_reaction(self, owner_tag: int) -> None:
        hook = getattr(self.bullet_pool, "unregister_termination_batch_reaction", None)
        if callable(hook):
            hook(int(owner_tag))

    def resolve_reaction_action(self, action_id: str) -> Any:
        """Resolve a Runtime API reaction action by stable authoring ID."""

        return self._reaction_actions.get(str(action_id).strip())

    def handle_script_event(self, hook: str, data: Any) -> bool:
        name = str(hook)
        handled = name in self._script_event_handlers
        self._timeline_events.append(
            {"kind": "script", "type": name, "data": data, "handled": handled}
        )
        if handled:
            result = self._script_event_handlers[name](data)
            if inspect.isawaitable(result):
                self.spawn_task(result)
        return handled

    def timeline_events(self) -> tuple[Dict[str, Any], ...]:
        return tuple(self._timeline_events)

    def clear_timeline_events(self) -> None:
        self._timeline_events.clear()

    def clear_authored_stage_state(self, *, preserve_authoring_trace: bool = False) -> None:
        self._authored_node_positions.clear()
        self._authored_node_properties.clear()
        self._timeline_events.clear()
        self._background_transitions.clear()
        self._lifecycle_trace.clear()
        if not preserve_authoring_trace:
            self._authoring_trace.clear()
            self._authoring_trace_dropped = 0

    # ==================== 音频 API ====================

    @property
    def audio(self) -> Optional[AudioManager]:
        return self._audio_manager

    def play_se(self, name: str, volume: Optional[float] = None,
                min_interval: float = 0.0) -> bool:
        if self._audio_manager:
            return self._audio_manager.play_se(name, volume, min_interval=min_interval)
        return False

    def play_danmaku_se(self, name: str, volume: Optional[float] = None,
                        min_interval: float = 0.0) -> bool:
        if self._audio_manager:
            return self._audio_manager.play_danmaku_se(name, volume, min_interval=min_interval)
        return False

    def play_bgm(self, name: str, loops: int = -1, fade_ms: int = 0) -> bool:
        if self._audio_manager:
            return self._audio_manager.play_bgm(name, loops, fade_ms)
        return False

    def stop_bgm(self, fade_ms: int = 0):
        if self._audio_manager:
            self._audio_manager.stop_bgm(fade_ms)

    def pause_bgm(self):
        if self._audio_manager:
            self._audio_manager.pause_bgm()

    def unpause_bgm(self):
        if self._audio_manager:
            self._audio_manager.unpause_bgm()

    # ==================== 背景 API ====================

    @property
    def background_renderer(self):
        return self._background_renderer

    def set_background(self, name: str) -> bool:
        """
        切换背景场景（通过名称加载 assets/images/background/{name}.json）。

        加载失败时保留当前背景，只打印警告。
        """
        if not self._background_renderer or not name:
            return False
        return self._background_renderer.load_background(name)

    def request_background_transition(
        self,
        resource: str,
        *,
        owner: str | None = None,
        fade_frames: int = 0,
    ) -> bool:
        """Apply a resource-backed transition at the stage boundary.

        Sparse runtime events call this typed context operation; the renderer
        never subscribes to the EventBus or owns authored transition state.
        The trace is runtime-only and is exposed to the debugger.
        """

        if not isinstance(resource, str) or not resource.strip():
            raise ValueError("background resource must be a non-empty string")
        if isinstance(fade_frames, bool) or not isinstance(fade_frames, int) or fade_frames < 0:
            raise ValueError("fade_frames must be a non-negative integer")
        result = self.set_background(resource.strip())
        self._background_transitions.append(
            {
                "resource": resource.strip(),
                "owner": owner,
                "fade_frames": fade_frames,
                "applied": bool(result),
                "frame": self._runtime_frame,
            }
        )
        return bool(result)

    def background_transitions(self) -> tuple[Dict[str, Any], ...]:
        return tuple(self._background_transitions)

    # ==================== 内部辅助 ====================

    def _resolve_sprite_id(self, bullet_type: str, color: str) -> str:
        """将弹幕类型+颜色映射到精灵 ID"""
        bullet_type = (bullet_type or "ball_m").strip().lower()
        color = (color or "red").strip().lower()

        legacy_type_aliases = {
            "bullet_m": "ball_m",
            "bullet_s": "ball_s",
            "bullet_l": "ball_l",
        }
        color_aliases = {
            "grey": "gray",
            # 内容里偶尔会把偏紫色弹写成 pink，优先收敛到稳定存在的紫色资源。
            "pink": "purple",
        }

        bullet_type = legacy_type_aliases.get(bullet_type, bullet_type)
        normalized_color = color_aliases.get(color, color)

        type_entry = self.BULLET_ALIAS_TABLE.get(bullet_type)
        if type_entry:
            for candidate_color in (normalized_color, color):
                sprite_id = type_entry.get(candidate_color)
                if sprite_id:
                    return sprite_id
            for fallback_color in ("red", "darkred", "purple", "white"):
                sprite_id = type_entry.get(fallback_color)
                if sprite_id:
                    return sprite_id
            return next(iter(type_entry.values()))
        base = self.BULLET_TYPE_MAP.get(bullet_type, "ball_mid")
        suffix = self.COLOR_MAP.get(normalized_color, self.COLOR_MAP.get(color, "1"))
        return f"{base}{suffix}"

    def _resolve_laser_color_index(self, color: Any) -> int:
        """激光颜色入参归一化：支持颜色名、数字字符串、整数索引。"""
        if isinstance(color, str):
            key = color.strip().lower()
            if key.isdigit():
                idx = int(key)
            else:
                mapped = self.COLOR_MAP.get(key)
                if mapped is None:
                    raise ValueError(f"Unknown laser color: {color}")
                idx = int(mapped)
        elif isinstance(color, (int, np.integer)):
            idx = int(color)
        else:
            raise TypeError(f"Unsupported laser color type: {type(color)}")

        return max(1, min(16, idx))

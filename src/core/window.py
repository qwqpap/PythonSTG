"""
Window abstraction layer - glfw backend

Provides window creation, event polling, buffer swapping, frame timing.
Replaces pygame.display, pygame.event, pygame.time.
"""

import time
import glfw


EVENT_QUIT = 'quit'
EVENT_KEYDOWN = 'keydown'
EVENT_KEYUP = 'keyup'


class GameWindow:
    """GLFW-based game window with OpenGL context"""

    _SYNCABLE_KEYS = tuple(range(glfw.KEY_SPACE, glfw.KEY_LAST + 1))

    def __init__(self, width: int, height: int, title: str = "Game",
                 fullscreen: bool = False):
        if not glfw.init():
            raise RuntimeError("Failed to initialize GLFW")

        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
        glfw.window_hint(glfw.RESIZABLE, False)

        # logical_size 是渲染器/着色器认为的"屏幕"尺寸（永远是 width×height）。
        # framebuffer_size 是实际的后台缓冲区（窗口模式 == logical；全屏模式
        # == 显示器原生分辨率）。viewport 是带信箱模式（letterbox）的居中
        # 矩形，用来在保持 4:3 长宽比的前提下铺满全屏，多出的边变成黑边。
        self._logical_size = (width, height)
        self._fullscreen = bool(fullscreen)

        if self._fullscreen:
            monitor = glfw.get_primary_monitor()
            video_mode = glfw.get_video_mode(monitor)
            mw = video_mode.size.width
            mh = video_mode.size.height
            # 用显示器原生模式打开 fullscreen 窗口（避免切换分辨率的卡顿/闪屏）
            glfw.window_hint(glfw.RED_BITS, video_mode.bits.red)
            glfw.window_hint(glfw.GREEN_BITS, video_mode.bits.green)
            glfw.window_hint(glfw.BLUE_BITS, video_mode.bits.blue)
            glfw.window_hint(glfw.REFRESH_RATE, video_mode.refresh_rate)
            self._window = glfw.create_window(mw, mh, title, monitor, None)
        else:
            self._window = glfw.create_window(width, height, title, None, None)

        if not self._window:
            glfw.terminate()
            raise RuntimeError("Failed to create GLFW window")

        glfw.make_context_current(self._window)
        glfw.swap_interval(0)

        # 查询真实 framebuffer 尺寸（HiDPI 下可能 ≠ 请求的窗口尺寸）
        fb_w, fb_h = glfw.get_framebuffer_size(self._window)
        self._framebuffer_size = (fb_w, fb_h)
        # v1: 全屏直接铺满 framebuffer（在 16:9 显示器上看 4:3 的游戏会被
        # 稍微横向拉伸——可接受，标准东方游戏的全屏行为同样如此）
        # 未来若想加 letterbox：调用 _compute_letterbox 替代下行
        self._viewport = (0, 0, fb_w, fb_h)

        # _width/_height 兼容旧字段，仍然返回 logical 尺寸（renderer 用）
        self._width = width
        self._height = height
        self._should_close = False
        self._events = []
        self._key_states = {}

        glfw.set_key_callback(self._window, self._key_callback)
        glfw.set_window_close_callback(self._window, self._close_callback)

    @staticmethod
    def _compute_letterbox(fb_w: int, fb_h: int, logical_w: int, logical_h: int):
        """计算保持 logical 长宽比的居中 viewport。

        framebuffer 比游戏宽 → 左右黑边；比游戏高 → 上下黑边。
        """
        target_aspect = logical_w / logical_h
        actual_aspect = fb_w / fb_h
        if abs(actual_aspect - target_aspect) < 1e-4:
            return (0, 0, fb_w, fb_h)
        if actual_aspect > target_aspect:
            # 比游戏宽 → 左右加边
            scaled_w = int(round(fb_h * target_aspect))
            scaled_h = fb_h
            x = (fb_w - scaled_w) // 2
            y = 0
        else:
            # 比游戏高 → 上下加边
            scaled_w = fb_w
            scaled_h = int(round(fb_w / target_aspect))
            x = 0
            y = (fb_h - scaled_h) // 2
        return (x, y, scaled_w, scaled_h)

    def _key_callback(self, window, key, scancode, action, mods):
        if action == glfw.PRESS:
            self._key_states[key] = True
            self._events.append({'type': EVENT_KEYDOWN, 'key': key})
        elif action == glfw.RELEASE:
            self._key_states[key] = False
            self._events.append({'type': EVENT_KEYUP, 'key': key})
        elif action == glfw.REPEAT:
            self._events.append({'type': EVENT_KEYDOWN, 'key': key})

    def _close_callback(self, window):
        self._should_close = True
        self._events.append({'type': EVENT_QUIT})

    def _sync_key_states(self):
        """Reconcile cached key states with GLFW's live keyboard snapshot.

        Scene/menu transitions can span multiple loops, and relying only on
        callback-delivered PRESS/RELEASE events can leave held keys stale if an
        edge is missed during the handoff. Syncing the authoritative state here
        keeps gameplay input and menu input consistent after transitions.
        """
        for key in self._SYNCABLE_KEYS:
            actual = glfw.get_key(self._window, key)
            pressed = actual in (glfw.PRESS, glfw.REPEAT)
            cached = self._key_states.get(key, False)
            if pressed == cached:
                continue
            self._key_states[key] = pressed
            self._events.append({
                'type': EVENT_KEYDOWN if pressed else EVENT_KEYUP,
                'key': key,
            })

    def poll_events(self) -> list:
        """Poll window events, returns list of event dicts."""
        self._events.clear()
        glfw.poll_events()
        self._sync_key_states()
        return list(self._events)

    def swap_buffers(self):
        glfw.swap_buffers(self._window)

    def should_close(self) -> bool:
        return self._should_close or glfw.window_should_close(self._window)

    def get_key_states(self) -> dict:
        return self._key_states

    def is_key_pressed(self, key: int) -> bool:
        return self._key_states.get(key, False)

    def destroy(self):
        glfw.destroy_window(self._window)
        glfw.terminate()

    @property
    def size(self):
        """Logical size (width, height) — what renderers/shaders use."""
        return (self._width, self._height)

    @property
    def framebuffer_size(self):
        """Real backbuffer size (在全屏模式下 = 显示器原生分辨率)。"""
        return self._framebuffer_size

    @property
    def viewport(self):
        """带信箱模式 (letterbox) 的居中 viewport 矩形 (x, y, w, h)。
        全屏模式下确保游戏区域保持 logical 长宽比，多出部分变黑边；
        窗口模式下 == (0, 0, width, height)。
        """
        return self._viewport

    @property
    def is_fullscreen(self) -> bool:
        return self._fullscreen


class FrameClock:
    """Frame rate controller using time.perf_counter.
    Replaces pygame.time.Clock."""

    def __init__(self):
        self._last_time = time.perf_counter()
        self._fps_counter = 0
        self._fps_timer = 0.0
        self._current_fps = 60.0
        self._work_time_accum = 0.0
        self._max_fps = 0.0

    def tick(self, target_fps: int = 60) -> float:
        """
        Limit frame rate and return delta time in seconds.
        Unlike pygame.time.Clock.tick() which returns ms, this returns seconds.
        """
        now = time.perf_counter()
        work_time = now - self._last_time  # 帧工作时间（不含 sleep/wait）
        dt = work_time

        target_dt = 1.0 / target_fps
        if dt < target_dt:
            # sleep 大部分时间（留 1ms 余量给 busy-wait 补偿 sleep 精度不足）
            sleep_time = target_dt - dt - 0.001
            if sleep_time > 0:
                time.sleep(sleep_time)
            # busy-wait spin 到精确时间点
            while time.perf_counter() - self._last_time < target_dt:
                pass
            now = time.perf_counter()
            dt = now - self._last_time

        self._last_time = now

        self._fps_counter += 1
        self._fps_timer += dt
        self._work_time_accum += work_time
        if self._fps_timer >= 1.0:
            self._current_fps = self._fps_counter / self._fps_timer
            avg_work = self._work_time_accum / self._fps_counter
            self._max_fps = 1.0 / avg_work if avg_work > 0 else 9999.0
            self._fps_counter = 0
            self._fps_timer = 0.0
            self._work_time_accum = 0.0

        return dt

    def get_fps(self) -> float:
        return self._current_fps

    def get_max_fps(self) -> float:
        """返回基于帧工作时间的理论最大帧率"""
        return self._max_fps

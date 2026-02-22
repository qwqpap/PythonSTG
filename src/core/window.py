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

    def __init__(self, width: int, height: int, title: str = "Game"):
        if not glfw.init():
            raise RuntimeError("Failed to initialize GLFW")

        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
        glfw.window_hint(glfw.RESIZABLE, False)

        self._window = glfw.create_window(width, height, title, None, None)
        if not self._window:
            glfw.terminate()
            raise RuntimeError("Failed to create GLFW window")

        glfw.make_context_current(self._window)
        glfw.swap_interval(0)

        self._width = width
        self._height = height
        self._should_close = False
        self._events = []
        self._key_states = {}

        glfw.set_key_callback(self._window, self._key_callback)
        glfw.set_window_close_callback(self._window, self._close_callback)

    def _key_callback(self, window, key, scancode, action, mods):
        if action == glfw.PRESS:
            self._key_states[key] = True
            self._events.append({'type': EVENT_KEYDOWN, 'key': key})
        elif action == glfw.RELEASE:
            self._key_states[key] = False
            self._events.append({'type': EVENT_KEYUP, 'key': key})

    def _close_callback(self, window):
        self._should_close = True
        self._events.append({'type': EVENT_QUIT})

    def poll_events(self) -> list:
        """Poll window events, returns list of event dicts."""
        self._events.clear()
        glfw.poll_events()
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
        return (self._width, self._height)


class FrameClock:
    """Frame rate controller using time.perf_counter.
    Replaces pygame.time.Clock."""

    def __init__(self):
        self._last_time = time.perf_counter()
        self._fps_counter = 0
        self._fps_timer = 0.0
        self._current_fps = 60.0

    def tick(self, target_fps: int = 60) -> float:
        """
        Limit frame rate and return delta time in seconds.
        Unlike pygame.time.Clock.tick() which returns ms, this returns seconds.
        """
        now = time.perf_counter()
        dt = now - self._last_time

        target_dt = 1.0 / target_fps
        if dt < target_dt:
            time.sleep(target_dt - dt)
            now = time.perf_counter()
            dt = now - self._last_time

        self._last_time = now

        self._fps_counter += 1
        self._fps_timer += dt
        if self._fps_timer >= 1.0:
            self._current_fps = self._fps_counter / self._fps_timer
            self._fps_counter = 0
            self._fps_timer = 0.0

        return dt

    def get_fps(self) -> float:
        return self._current_fps

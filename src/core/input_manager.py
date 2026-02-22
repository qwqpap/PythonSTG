"""
Input abstraction layer - glfw key constants

Provides unified key code constants and keyboard state queries.
Replaces pygame.K_* constants and pygame.key.get_pressed().
"""

import glfw

# Arrow keys
KEY_UP = glfw.KEY_UP
KEY_DOWN = glfw.KEY_DOWN
KEY_LEFT = glfw.KEY_LEFT
KEY_RIGHT = glfw.KEY_RIGHT

# Modifier keys
KEY_LSHIFT = glfw.KEY_LEFT_SHIFT
KEY_RSHIFT = glfw.KEY_RIGHT_SHIFT

# Action keys
KEY_z = glfw.KEY_Z
KEY_x = glfw.KEY_X
KEY_ESCAPE = glfw.KEY_ESCAPE
KEY_RETURN = glfw.KEY_ENTER

# WASD
KEY_w = glfw.KEY_W
KEY_s = glfw.KEY_S
KEY_a = glfw.KEY_A
KEY_d = glfw.KEY_D

# Map from pygame-style key name strings (used in player config files) to codes
_KEY_NAME_MAP = {
    'K_UP': KEY_UP,
    'K_DOWN': KEY_DOWN,
    'K_LEFT': KEY_LEFT,
    'K_RIGHT': KEY_RIGHT,
    'K_LSHIFT': KEY_LSHIFT,
    'K_RSHIFT': KEY_RSHIFT,
    'K_z': KEY_z,
    'K_x': KEY_x,
    'K_ESCAPE': KEY_ESCAPE,
    'K_RETURN': KEY_RETURN,
    'K_w': KEY_w,
    'K_s': KEY_s,
    'K_a': KEY_a,
    'K_d': KEY_d,
}


def key_name_to_code(name: str) -> int:
    """Convert pygame-style key name string (e.g. 'K_UP') to key code."""
    return _KEY_NAME_MAP.get(name, 0)


class KeyboardState:
    """Array-like wrapper for key states dict, compatible with keys[KEY_UP] access."""

    def __init__(self, key_states: dict):
        self._states = key_states

    def __getitem__(self, key):
        return self._states.get(key, False)

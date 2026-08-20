"""Composition helpers for legacy-compatible Qt shell services.

ER2 keeps the existing public method names used by tests and native gates, but
the methods are owned by composed service objects instead of being inherited by
``EditorMainWindow``.  Domain mutation services progressively translate those
calls into typed application intents.
"""

from __future__ import annotations

from collections.abc import Iterable


class WindowService:
    """Forward shared shell state to one assembled main window without Qt bases."""

    def __init__(self, window: object):
        object.__setattr__(self, "_window", window)

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_window"), name)

    def __setattr__(self, name: str, value: object) -> None:
        if name == "_window":
            object.__setattr__(self, name, value)
            return
        setattr(object.__getattribute__(self, "_window"), name, value)


def install_service_methods(
    window: object,
    services: Iterable[WindowService],
) -> None:
    """Install thin instance-level compatibility entry points from services."""

    for service in services:
        for owner in reversed(type(service).__mro__):
            if owner is WindowService:
                continue
            for name, descriptor in vars(owner).items():
                if name.startswith("__") or not callable(descriptor):
                    continue
                if name in vars(type(window)):
                    raise RuntimeError(
                        f"Shell service method collides with EditorMainWindow: {name}"
                    )
                existing = vars(window).get(name) if hasattr(window, "__dict__") else None
                if existing is not None:
                    raise RuntimeError(f"Duplicate shell service method: {name}")
                setattr(window, name, getattr(service, name))


__all__ = ["WindowService", "install_service_methods"]

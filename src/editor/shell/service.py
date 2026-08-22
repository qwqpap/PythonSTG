"""Base class for the shell's composed application services."""

from __future__ import annotations

from typing import Generic, TypeVar


PortT = TypeVar("PortT")


class WindowService(Generic[PortT]):
    """A service that can only reach the explicit port supplied at assembly."""

    def __init__(self, port: PortT) -> None:
        self.port = port


__all__ = ["WindowService"]

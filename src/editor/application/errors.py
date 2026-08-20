"""Structured application-layer intent rejection errors."""

from __future__ import annotations

from enum import Enum, auto


class IntentRejectionCode(Enum):
    DOCUMENT_NOT_OPEN = auto()
    INACTIVE_DOCUMENT = auto()
    TARGET_NOT_FOUND = auto()
    INVALID_INTENT = auto()


class IntentRejectedError(ValueError):
    def __init__(self, code: IntentRejectionCode, message: str):
        super().__init__(message)
        self.code = code


__all__ = ["IntentRejectedError", "IntentRejectionCode"]

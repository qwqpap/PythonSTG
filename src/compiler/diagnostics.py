"""Serializable diagnostics shared by compiler entry points."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class CompilerDiagnostic:
    """A stable diagnostic shape suitable for the preview protocol."""

    severity: str
    code: str
    resource_id: str
    path: str
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "resource_id": self.resource_id,
            "path": self.path,
            "message": self.message,
            **self.details,
        }


def normalize_diagnostics(items: Iterable[object]) -> tuple[CompilerDiagnostic, ...]:
    """Normalize concrete compiler diagnostics without losing location fields."""

    normalized: list[CompilerDiagnostic] = []
    for item in items:
        payload = asdict(item) if is_dataclass(item) else dict(vars(item))
        core = {
            key: str(payload.pop(key, "") or "")
            for key in ("severity", "code", "resource_id", "path", "message")
        }
        normalized.append(CompilerDiagnostic(**core, details=payload))
    return tuple(normalized)


__all__ = ["CompilerDiagnostic", "normalize_diagnostics"]

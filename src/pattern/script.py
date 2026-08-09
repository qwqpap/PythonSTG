"""ScriptBehavior: sparse controller/emitter scripts with typed context APIs.

Established ScriptBehavior contract:
- ``SCRIPT_HOOKS`` is exactly ``("load", "start", "update", "on_event", "stop")``.
- ``PatternDocument.script`` is ``None`` or a ``ScriptBehavior`` whose
  ``resource_uri`` points at a Python module implementing any of the hooks.
- ``update`` runs at most once per tick; no per-bullet Python callback is
  installed.
- ``ScriptContext`` extends ``StageContext`` with typed script helpers and
  rejects per-bullet update registration by default.
- Script import/runtime errors surface through the compile/runtime diagnostic
  protocol; documents never embed script source text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.authoring.resources import ResourceDocumentError
from src.game.stage.context import StageContext

SCRIPT_HOOKS = ("load", "start", "update", "on_event", "stop")


class ScriptContextError(RuntimeError):
    """Raised when a script violates the typed context contract."""


class ScriptContext(StageContext):
    """Typed host context handed to script hooks.

    Extends ``StageContext`` (so the formal runtime keeps working) with the
    script-facing helpers ``emit_event``, ``get_player_position``, and
    ``attach_bullet_update``. Per-bullet Python updates are rejected by
    default; sparse controller logic belongs in ``update(ctx, frame)``.
    """

    def get_player_position(self) -> tuple[float, float]:
        player = self.get_player()
        if player is None:
            return (0.0, 0.0)
        try:
            return (float(player.x), float(player.y))
        except (AttributeError, TypeError):
            return (0.0, 0.0)

    def attach_bullet_update(self, callback: Any) -> None:
        raise ScriptContextError(
            "per-bullet update registration is rejected by default; "
            "drive sparse controller logic from update(ctx, frame) instead"
        )


@dataclass(frozen=True)
class ScriptBehavior:
    """Authoring reference to a script module attached to a pattern."""

    resource_uri: str

    def validate(self, path: str = "script") -> None:
        if not isinstance(self.resource_uri, str) or not self.resource_uri.strip():
            raise ResourceDocumentError(
                f"{path}.resource_uri", "must be a non-empty res:// reference"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"resource_uri": self.resource_uri}

    @classmethod
    def from_dict(cls, value: Any) -> "ScriptBehavior":
        if isinstance(value, ScriptBehavior):
            return value
        if not isinstance(value, Mapping):
            raise ResourceDocumentError("script", "must be an object")
        allowed = {"resource_uri"}
        unknown = set(value).difference(allowed)
        if unknown:
            raise ResourceDocumentError(
                "script", "unknown fields: " + ", ".join(sorted(unknown))
            )
        script = cls(resource_uri=str(value.get("resource_uri", "")))
        script.validate()
        return script


@dataclass(frozen=True)
class ScriptProgramData:
    """Data-only script payload compiled into ``PatternProgram``."""

    resource_uri: str
    script_path: str

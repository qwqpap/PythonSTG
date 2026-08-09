"""Property bindings: constants, curves, variables, and expressions.

Established property-binding contract:
- ``BindingSpec(path, kind, value)`` with ``kind`` in ``constant`` /
  ``curve`` / ``variable`` / ``expression``.
- ``PathDocument.bindings`` stores these; curve values are ``res://``
  references to ``pystg.curve`` resources.
- Compiled bindings are pure data (``CompiledBinding``) inside
  ``PatternProgram``; no callables survive compilation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

from src.pattern.expressions import EXPRESSION_VARIABLES

BINDING_KINDS = ("constant", "curve", "variable", "expression")
_PROPERTY_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


class BindingError(ValueError):
    """Raised when a BindingSpec violates the binding contract."""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


@dataclass(frozen=True)
class BindingSpec:
    """Authoring-level binding declaration on a pattern document."""

    path: str
    kind: str
    value: float | str | None = None

    def validate(self, path: str = "bindings") -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise BindingError(f"{path}.path", "must be a non-empty property path")
        if _PROPERTY_PATH.fullmatch(self.path.strip()) is None:
            raise BindingError(
                f"{path}.path",
                "must be a dotted identifier path such as motion.speed",
            )
        if self.kind not in BINDING_KINDS:
            raise BindingError(
                f"{path}.kind",
                "must be one of: " + ", ".join(BINDING_KINDS),
            )
        if self.kind == "constant":
            if not isinstance(self.value, (bool, int, float)):
                raise BindingError(
                    f"{path}.value",
                    "constant bindings require a number or boolean",
                )
            if not isinstance(self.value, bool) and not math.isfinite(float(self.value)):
                raise BindingError(f"{path}.value", "must be finite")
            return
        if not isinstance(self.value, str) or not self.value.strip():
            raise BindingError(
                f"{path}.value",
                f"{self.kind} bindings require a non-empty string",
            )
        if (
            self.kind == "variable"
            and self.value not in EXPRESSION_VARIABLES
            and "." not in self.value
            and _PROPERTY_PATH.fullmatch(self.value.strip()) is None
        ):
            raise BindingError(
                f"{path}.value",
                f"unknown binding variable {self.value!r}",
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "path": self.path,
            "kind": self.kind,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "BindingSpec":
        if isinstance(value, BindingSpec):
            return value
        if not isinstance(value, Mapping):
            raise BindingError("bindings", "binding must be an object")
        allowed = {"path", "kind", "value"}
        unknown = set(value).difference(allowed)
        if unknown:
            raise BindingError(
                "bindings", "unknown fields: " + ", ".join(sorted(unknown))
            )
        binding = cls(
            path=str(value.get("path", "")),
            kind=str(value.get("kind", "")),
            value=value.get("value"),
        )
        binding.validate()
        return binding


@dataclass(frozen=True)
class CompiledBinding:
    """Immutable data-only binding carried by ``PatternProgram``.

    ``curve_frames`` / ``curve_values`` / ``curve_interpolation`` /
    ``curve_default`` hold the sampled curve data; ``expression_source`` /
    ``expression_node`` hold the portable expression tree. Neither field ever
    holds a callable.
    """

    target_path: str
    mode: str
    value: float | str | None = None
    curve_frames: tuple[int, ...] = ()
    curve_values: tuple[float, ...] = ()
    curve_interpolation: str = "linear"
    curve_default: float = 0.0
    expression_source: str | None = None
    expression_node: tuple | None = None

"""Structured compiler failures shared by code generation and package builds."""

from __future__ import annotations

from src.authoring.program import (
    Diagnostic,
    ProgramError,
    RelatedLocation,
    SourceSpan,
)


class CompilerError(ProgramError):
    """A blocking compiler failure with stable diagnostics when available."""

    def __init__(
        self,
        code: str,
        message: str,
        diagnostics: tuple[Diagnostic, ...] = (),
    ) -> None:
        super().__init__(code, message)
        self.diagnostics = tuple(diagnostics)


__all__ = [
    "CompilerError",
    "Diagnostic",
    "RelatedLocation",
    "SourceSpan",
]

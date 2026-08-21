"""Stable compiler entry surface.

This facade is the single call surface the editor coordinator, preview and
resource registry use to turn author documents into formal runtime programs.
It re-exports the concrete compile entry points and their diagnostic / error
types so callers depend on one stable module instead of the internal layout of
the compiler package.

Like the rest of :mod:`src.compiler`, this module is Qt-free and never imports
:mod:`src.editor`; the dependency direction is authoring → compiler → preview.
"""

from src.compiler.scene_spell import (
    SceneCompileDiagnostic,
    SceneSpellCompileError,
    SceneSpellPreview,
    compile_simple_spell,
)
from src.compiler.stage import (
    STAGE_PROGRAM_VERSION,
    StageCompileDiagnostic,
    StageCompileError,
    compile_stage,
)

__all__ = [
    "STAGE_PROGRAM_VERSION",
    "StageCompileDiagnostic",
    "StageCompileError",
    "compile_stage",
    "SceneCompileDiagnostic",
    "SceneSpellCompileError",
    "SceneSpellPreview",
    "compile_simple_spell",
]

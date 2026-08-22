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
from src.authoring.scene.document import SceneDocument
from src.core.project_context import ProjectContext
from src.game.stage.program import StageProgram
from src.pattern import PatternCompiler, PatternDocument, PatternProgram


class UnsupportedDocumentTypeError(TypeError):
    """Raised when no formal compiler owns an authoring document type."""


def compile_document(
    document: PatternDocument | SceneDocument,
    *,
    project: ProjectContext,
    pattern_compiler: PatternCompiler | None = None,
    sprite_index_resolver=None,
) -> PatternProgram | StageProgram:
    """Compile a supported document through the canonical formal path."""

    compiler = pattern_compiler or PatternCompiler()
    if isinstance(document, PatternDocument):
        return compiler.compile(
            document,
            project=project,
            sprite_index_resolver=sprite_index_resolver,
        )
    if isinstance(document, SceneDocument):
        return compile_stage(
            project,
            document,
            pattern_compiler=compiler,
            sprite_index_resolver=sprite_index_resolver,
        )
    raise UnsupportedDocumentTypeError(
        f"No formal compiler for document type {type(document).__name__!r}"
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
    "compile_document",
    "UnsupportedDocumentTypeError",
]

"""Formal compilation from author documents to runtime programs.

The compiler turns validated author documents (scene / spell / pattern / stage)
into the formal runtime program consumed by the preview and the engine.  It
depends only on :mod:`src.authoring`; it never imports :mod:`src.editor` or Qt.

Import the stable entry points from this package or from
:mod:`src.compiler.facade`.  The concrete modules (:mod:`src.compiler.stage`,
:mod:`src.compiler.scene_spell`, :mod:`src.compiler.pattern_resolve`) remain
available for advanced use.
"""

from src.compiler.pattern_resolve import (
    PatternResolveError,
    apply_spawn_origin,
    load_pattern_document,
    node_maps,
    spawn_origin_node,
)
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
from src.compiler.facade import UnsupportedDocumentTypeError, compile_document
from src.compiler.diagnostics import CompilerDiagnostic, normalize_diagnostics

__all__ = [
    "STAGE_PROGRAM_VERSION",
    "StageCompileDiagnostic",
    "StageCompileError",
    "compile_stage",
    "SceneCompileDiagnostic",
    "SceneSpellCompileError",
    "SceneSpellPreview",
    "compile_simple_spell",
    "PatternResolveError",
    "apply_spawn_origin",
    "load_pattern_document",
    "node_maps",
    "spawn_origin_node",
    "compile_document",
    "UnsupportedDocumentTypeError",
    "CompilerDiagnostic",
    "normalize_diagnostics",
]

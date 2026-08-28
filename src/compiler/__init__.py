"""Public API for deterministic code-driven content compilation."""

from .codegen import CodeGenerator, CodeGeneratorResult, SourceMapEntry
from .content_entry import ContentRegistry, load_content_entry
from .diagnostics import CompilerError
from .package_builder import PackageBuilder, PreparedBuild
from .practice import PRACTICE_STAGE_ID, practice_program

__all__ = [
    "CodeGenerator",
    "CodeGeneratorResult",
    "CompilerError",
    "ContentRegistry",
    "PackageBuilder",
    "PreparedBuild",
    "PRACTICE_STAGE_ID",
    "SourceMapEntry",
    "load_content_entry",
    "practice_program",
]

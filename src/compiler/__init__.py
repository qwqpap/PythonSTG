"""Public API for deterministic code-driven content compilation."""

from .codegen import CodeGenerator, CodeGeneratorResult, SourceMapEntry
from .content_entry import ContentRegistry, load_content_entry
from .diagnostics import CompilerError
from .package_builder import PackageBuilder, PreparedBuild

__all__ = [
    "CodeGenerator",
    "CodeGeneratorResult",
    "CompilerError",
    "ContentRegistry",
    "PackageBuilder",
    "PreparedBuild",
    "SourceMapEntry",
    "load_content_entry",
]

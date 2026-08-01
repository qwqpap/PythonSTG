"""Typed pattern authoring, compilation, and formal runtime execution."""

from .compiler import (
    PatternCompileError,
    PatternCompiler,
    PatternDiagnostic,
    compile_pattern,
)
from .document import (
    AIM_MODES,
    PATTERN_SHAPES,
    AimSpec,
    BulletSpec,
    ModifierSpec,
    MotionSpec,
    PatternDocument,
    PatternDocumentError,
    ScheduleSpec,
    ShapeSpec,
)
from .ir import BurstTemplate, PatternProgram
from .runtime import (
    PatternRunner,
    PatternRunnerState,
    PatternRuntimeError,
    PatternSpawnEvent,
    PatternTickResult,
)

__all__ = [
    "AIM_MODES",
    "PATTERN_SHAPES",
    "AimSpec",
    "BulletSpec",
    "BurstTemplate",
    "ModifierSpec",
    "MotionSpec",
    "PatternCompileError",
    "PatternCompiler",
    "PatternDiagnostic",
    "PatternDocument",
    "PatternDocumentError",
    "PatternProgram",
    "PatternRunner",
    "PatternRunnerState",
    "PatternRuntimeError",
    "PatternSpawnEvent",
    "PatternTickResult",
    "ScheduleSpec",
    "ShapeSpec",
    "compile_pattern",
]

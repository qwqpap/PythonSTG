"""Typed pattern authoring, compilation, and formal runtime execution."""

from .bindings import BINDING_KINDS, BindingSpec, CompiledBinding
from .compiler import (
    PatternCompileError,
    PatternCompiler,
    PatternDiagnostic,
    compile_pattern,
)
from .curves import (
    CURVE_INTERPOLATIONS,
    CURVE_RESOURCE_TYPE,
    CurveDocument,
    CurveDocumentError,
    CurveKeyframe,
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
from .expressions import (
    EXPRESSION_VARIABLES,
    CompiledExpression,
    ExpressionError,
    compile_expression,
    parse_expression,
)
from .graph import (
    GRAPH_NODE_CATEGORIES,
    BehaviorGraph,
    BehaviorGraphEdge,
    BehaviorGraphNode,
)
from .ir import BurstTemplate, PatternProgram
from .runtime import (
    PatternRunner,
    PatternRunnerState,
    PatternRuntimeError,
    PatternSpawnEvent,
    PatternTickResult,
)
from .script import (
    SCRIPT_HOOKS,
    ScriptBehavior,
    ScriptContext,
    ScriptContextError,
)

__all__ = [
    "AIM_MODES",
    "BINDING_KINDS",
    "PATTERN_SHAPES",
    "AimSpec",
    "BehaviorGraph",
    "BehaviorGraphEdge",
    "BehaviorGraphNode",
    "BindingSpec",
    "BulletSpec",
    "BurstTemplate",
    "CURVE_INTERPOLATIONS",
    "CompiledBinding",
    "CompiledExpression",
    "CurveDocument",
    "CurveDocumentError",
    "CurveKeyframe",
    "EXPRESSION_VARIABLES",
    "ExpressionError",
    "GRAPH_NODE_CATEGORIES",
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
    "SCRIPT_HOOKS",
    "ScheduleSpec",
    "ScriptBehavior",
    "ScriptContext",
    "ScriptContextError",
    "ShapeSpec",
    "compile_expression",
    "compile_pattern",
    "parse_expression",
]

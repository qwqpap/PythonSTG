"""Headless program model for the code-driven level authoring DSL.

The model is deliberately independent from Qt, the editor, the compiler, and
the renderer.  It stores only author-visible logical units, statement nodes,
restricted values, source locations, and diagnostics.  Editing operations are
copy-on-success so a failed operation cannot partially mutate a project.
"""

from __future__ import annotations

import ast
import copy
import inspect
import keyword
import math
import re
import types
import uuid
from collections import abc as collections_abc
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import (
    Any,
    Iterable,
    Iterator,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)


UNIT_KINDS = frozenset(
    {"Project", "Stage", "Wave", "Enemy", "Boss", "Spell", "NonSpell", "Task", "Function"}
)

CONTROL_NODE_KINDS = frozenset(
    {
        "Wait",
        "At",
        "Repeat",
        "While",
        "If",
        "Else",
        "ForEach",
        "Parallel",
        "SpawnTask",
        "Break",
        "Continue",
        "Return",
        "Set",
        "Call",
        "RawPython",
    }
)

ACTION_NODE_KINDS = frozenset(
    {
        "RunWave",
        "RunBoss",
        "SetBackground",
        "PlayBGM",
        "PlayDialogue",
        "SpawnEnemy",
        "MoveTo",
        "MoveLinear",
        "SetPosition",
        "Fire",
        "FireCircle",
        "FireArc",
        "FireAtPlayer",
        "FirePolar",
        "FireOrbit",
        "ClearBullets",
        "Kill",
        "PlaySE",
        "CreateLaser",
        "CreateBentLaser",
        "RemoveLaser",
        "ClearLasers",
    }
)

INTERNAL_NODE_KINDS = frozenset({"Branch", "TemplateCall"})
NODE_KINDS = CONTROL_NODE_KINDS | ACTION_NODE_KINDS | INTERNAL_NODE_KINDS

_LOOP_KINDS = frozenset({"Repeat", "While", "ForEach"})
_CHILD_SLOTS: dict[str, tuple[str, ...]] = {
    "At": ("body",),
    "Repeat": ("body",),
    "While": ("body",),
    "If": ("body", "else_body"),
    "Else": ("body",),
    "ForEach": ("body",),
    "Parallel": ("branches",),
    "Branch": ("body",),
    "SpawnTask": ("body",),
}

_STAGE_ACTIONS = frozenset(
    {"RunWave", "RunBoss", "SetBackground", "PlayBGM", "PlayDialogue", "PlaySE"}
)
_FIRE_ACTIONS = frozenset(
    {"Fire", "FireCircle", "FireArc", "FireAtPlayer", "FirePolar", "FireOrbit", "ClearBullets"}
)
_WAVE_FIRE_ACTIONS = _FIRE_ACTIONS - {"ClearBullets"}
_MOVE_ACTIONS = frozenset({"MoveTo", "MoveLinear", "SetPosition"})
_SPELL_MOVE_ACTIONS = _MOVE_ACTIONS - {"MoveLinear"}
_LASER_ACTIONS = frozenset(
    {"CreateLaser", "CreateBentLaser", "RemoveLaser", "ClearLasers"}
)
_UNIT_ACTIONS: dict[str, frozenset[str]] = {
    "Project": frozenset(),
    "Stage": _STAGE_ACTIONS,
    "Wave": _WAVE_FIRE_ACTIONS | {"SpawnEnemy", "PlaySE"},
    "Enemy": _FIRE_ACTIONS | _MOVE_ACTIONS | _LASER_ACTIONS | {"Kill", "PlaySE"},
    "Boss": frozenset(),
    "Spell": _FIRE_ACTIONS | _SPELL_MOVE_ACTIONS | _LASER_ACTIONS | {"PlaySE"},
    "NonSpell": _FIRE_ACTIONS | _SPELL_MOVE_ACTIONS | _LASER_ACTIONS | {"PlaySE"},
    # A Task or Function runs in the caller's trusted generation context.  It
    # may therefore contain any public action, while references remain typed.
    "Task": ACTION_NODE_KINDS,
    "Function": ACTION_NODE_KINDS,
}

_REF_TARGETS: dict[tuple[str, str], frozenset[str]] = {
    ("RunWave", "wave_class"): frozenset({"Wave"}),
    ("RunBoss", "boss_def"): frozenset({"Boss"}),
    ("SpawnEnemy", "enemy_class"): frozenset({"Enemy"}),
    ("SpawnTask", "task"): frozenset({"Task"}),
    ("Call", "function"): frozenset({"Function", "Task"}),
}

# The shared authoring constructors cover Wave, Enemy, and SpellCard call
# sites.  A missing value can therefore mean "use the current actor" in an
# Enemy/Spell, while the Wave API has no actor and requires an explicit
# position/center.  Keep those contextual Runtime requirements in the model
# validator instead of inventing separate node kinds or parameter catalogs.
_CONTEXT_REQUIRED_ARGUMENTS: dict[tuple[str, str], tuple[str, ...]] = {
    ("Wave", "Fire"): ("x", "y"),
    ("Wave", "FireCircle"): ("x", "y"),
    ("Wave", "FireArc"): ("x", "y"),
    ("Wave", "FireAtPlayer"): ("x", "y"),
    ("Wave", "FirePolar"): ("center",),
    ("Wave", "FireOrbit"): ("center",),
}


class ProgramError(ValueError):
    """Raised when a model operation cannot be committed."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class SourceSpan:
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def __post_init__(self) -> None:
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("invalid source line span")
        if self.start_column < 0 or self.end_column < 0:
            raise ValueError("invalid source column span")


@dataclass(frozen=True)
class RelatedLocation:
    source_path: str
    span: SourceSpan | None = None
    message: str = ""


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: str = "error"
    source_path: str = ""
    span: SourceSpan | None = None
    unit_id: str | None = None
    uid: str | None = None
    related: tuple[RelatedLocation, ...] = ()


class ProgramValidationError(ProgramError):
    def __init__(self, diagnostics: Sequence[Diagnostic]):
        self.diagnostics = tuple(diagnostics)
        summary = "; ".join(item.message for item in self.diagnostics[:3])
        super().__init__("program_invalid", summary or "program validation failed")


@dataclass(frozen=True)
class Ref:
    id: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ProgramError("invalid_ref", "Ref id must be non-empty text")
        object.__setattr__(self, "id", self.id.strip())


@dataclass(frozen=True)
class Expr:
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ProgramError("invalid_expr", "Expr source must be non-empty text")
        source = self.source.strip()
        try:
            ast.parse(source, mode="eval")
        except SyntaxError as exc:
            raise ProgramError("invalid_expr", f"invalid Python expression: {exc.msg}") from exc
        object.__setattr__(self, "source", source)


class _NoDefault:
    def __deepcopy__(self, memo: dict[int, Any]) -> "_NoDefault":
        return self


_NO_DEFAULT = _NoDefault()


@dataclass(frozen=True)
class Parameter:
    name: str
    annotation: str = "Any"
    default: Any = field(default=_NO_DEFAULT, repr=False)

    def __post_init__(self) -> None:
        if not _is_python_identifier(self.name):
            raise ProgramError("invalid_parameter", f"invalid parameter name {self.name!r}")
        if not isinstance(self.annotation, str) or not self.annotation.strip():
            raise ProgramError("invalid_parameter", "parameter annotation must be text")
        annotation = self.annotation.strip()
        try:
            ast.parse(annotation, mode="eval")
        except SyntaxError as exc:
            raise ProgramError(
                "invalid_parameter", f"invalid parameter annotation {annotation!r}"
            ) from exc
        object.__setattr__(self, "annotation", annotation)
        if self.default is not _NO_DEFAULT:
            validate_author_value(self.default, f"parameter {self.name}.default")

    @property
    def has_default(self) -> bool:
        return self.default is not _NO_DEFAULT


@dataclass(frozen=True)
class NodeComments:
    leading: tuple[str, ...] = ()
    trailing: str | None = None

    def __post_init__(self) -> None:
        for line in self.leading:
            if not isinstance(line, str):
                raise TypeError("leading comments must be strings")
        if self.trailing is not None and not isinstance(self.trailing, str):
            raise TypeError("trailing comment must be text")


@dataclass(frozen=True)
class TemplateTarget:
    identity: str
    symbol: str
    display_name: str | None = None
    module: str | None = None
    resolved: bool = True
    definition_path: str | None = None
    definition_span: SourceSpan | None = None
    signature: inspect.Signature | None = field(default=None, compare=False, repr=False)


def new_uid(kind: str = "node") -> str:
    prefix = re.sub(r"[^A-Za-z0-9_]+", "_", kind).strip("_").lower() or "node"
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass
class Node:
    kind: str
    arguments: dict[str, Any] = field(default_factory=dict)
    children: dict[str, list["Node"]] = field(default_factory=dict)
    uid: str = field(default_factory=new_uid)
    source_span: SourceSpan | None = None
    comments: NodeComments = field(default_factory=NodeComments)
    positional_arguments: tuple[Any, ...] = ()
    template: TemplateTarget | None = None

    def __post_init__(self) -> None:
        if self.kind not in NODE_KINDS:
            raise ProgramError("unknown_node", f"unknown node kind {self.kind!r}")
        if not isinstance(self.uid, str) or not self.uid.strip():
            raise ProgramError("invalid_uid", "node uid must be non-empty text")
        self.uid = self.uid.strip()
        self.arguments = dict(self.arguments)
        self.children = {name: list(values) for name, values in self.children.items()}
        self.positional_arguments = tuple(self.positional_arguments)
        for name, value in self.arguments.items():
            if not isinstance(name, str) or not name:
                raise ProgramError("invalid_argument", "argument names must be non-empty text")
            validate_author_value(value, f"{self.kind}.{name}")
        for index, value in enumerate(self.positional_arguments):
            validate_author_value(value, f"{self.kind}.args[{index}]")
        for slot, values in self.children.items():
            if not isinstance(slot, str) or not slot:
                raise ProgramError("invalid_child_slot", "child slot names must be text")
            if not all(isinstance(item, Node) for item in values):
                raise ProgramError("invalid_child", f"{self.kind}.{slot} must contain nodes")
        if self.kind == "TemplateCall" and self.template is None:
            raise ProgramError("invalid_template_call", "TemplateCall requires a target")

    def clone(self) -> "Node":
        return copy.deepcopy(self)

    def walk(self) -> Iterator["Node"]:
        yield self
        for values in self.children.values():
            for child in values:
                yield from child.walk()

    def semantic_data(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "uid": self.uid,
            "arguments": _value_data(self.arguments),
            "children": {
                slot: [child.semantic_data() for child in values]
                for slot, values in self.children.items()
            },
        }
        if self.positional_arguments:
            result["positional_arguments"] = _value_data(self.positional_arguments)
        if self.template is not None:
            result["template"] = {
                "identity": self.template.identity,
                "symbol": self.template.symbol,
                "display_name": self.template.display_name,
                "module": self.template.module,
                "resolved": self.template.resolved,
            }
        return result


def make_template_call(
    target: TemplateTarget,
    positional: Sequence[Any] = (),
    keywords: Mapping[str, Any] | None = None,
    *,
    uid: str | None = None,
    source_span: SourceSpan | None = None,
) -> Node:
    return Node(
        kind="TemplateCall",
        arguments=dict(keywords or {}),
        positional_arguments=tuple(positional),
        children={},
        uid=new_uid("template") if uid is None else uid,
        source_span=source_span,
        template=target,
    )


@dataclass
class LogicalUnit:
    kind: str
    id: str
    name: str
    body: list[Node] = field(default_factory=list)
    parameters: tuple[Parameter, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None
    assignment_name: str | None = None
    source_span: SourceSpan | None = None

    def __post_init__(self) -> None:
        if self.kind not in UNIT_KINDS:
            raise ProgramError("unknown_unit", f"unknown logical unit kind {self.kind!r}")
        if not _is_python_identifier(self.id):
            raise ProgramError("invalid_unit_id", f"invalid logical unit id {self.id!r}")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ProgramError("invalid_unit_name", "logical unit name must be non-empty text")
        self.name = self.name.strip()
        self.body = list(self.body)
        if not all(isinstance(item, Node) for item in self.body):
            raise ProgramError("invalid_unit_body", f"{self.kind}.body must contain nodes")
        self.parameters = _validated_parameters(self.parameters, self.id)
        self.metadata = dict(self.metadata)
        for key, value in self.metadata.items():
            validate_author_value(value, f"{self.id}.{key}")
        if self.assignment_name is None:
            self.assignment_name = self.kind.lower()

    def clone(self) -> "LogicalUnit":
        return copy.deepcopy(self)

    def walk_nodes(self) -> Iterator[Node]:
        for node in self.body:
            yield from node.walk()

    def semantic_data(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "parameters": [
                {
                    "name": item.name,
                    "annotation": item.annotation,
                    **(
                        {"default": _value_data(item.default)}
                        if item.has_default
                        else {}
                    ),
                }
                for item in self.parameters
            ],
            "metadata": _value_data(self.metadata),
            "body": [node.semantic_data() for node in self.body],
        }


@dataclass
class AuthoringProgram:
    units: dict[str, LogicalUnit] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.units = dict(self.units)

    @classmethod
    def from_units(cls, units: Iterable[LogicalUnit]) -> "AuthoringProgram":
        # Preserve all values long enough for validate() to report duplicates.
        result = cls()
        for index, unit in enumerate(units):
            key = unit.id if unit.id not in result.units else f"{unit.id}#duplicate{index}"
            result.units[key] = unit
        return result

    def clone(self) -> "AuthoringProgram":
        return copy.deepcopy(self)

    def logical_units(self) -> tuple[LogicalUnit, ...]:
        return tuple(self.units.values())

    def get_unit(self, unit_id: str) -> LogicalUnit:
        unit = self.units.get(unit_id)
        if unit is None or unit.id != unit_id:
            # Duplicate-storage keys are intentionally not addressable.
            for candidate in self.units.values():
                if candidate.id == unit_id:
                    return candidate
            raise ProgramError("unknown_unit", f"unknown logical unit {unit_id!r}")
        return unit

    def walk_nodes(self) -> Iterator[tuple[LogicalUnit, Node]]:
        for unit in self.units.values():
            for node in unit.walk_nodes():
                yield unit, node

    def semantic_data(self) -> dict[str, Any]:
        return {
            "units": [
                unit.semantic_data()
                for unit in sorted(
                    self.units.values(), key=lambda value: (value.kind, value.id)
                )
            ]
        }

    def validate(self) -> tuple[Diagnostic, ...]:
        diagnostics: list[Diagnostic] = []
        by_id: dict[str, list[LogicalUnit]] = {}
        for unit in self.units.values():
            by_id.setdefault(unit.id, []).append(unit)
        for unit_id, values in by_id.items():
            if len(values) > 1:
                diagnostics.append(
                    Diagnostic(
                        code="duplicate_unit_id",
                        message=f"duplicate logical unit id {unit_id!r}",
                        unit_id=unit_id,
                        source_path=_source_path(values[0]),
                        span=values[0].source_span,
                        related=tuple(
                            RelatedLocation(_source_path(item), item.source_span)
                            for item in values[1:]
                        ),
                    )
                )

        project_units = [unit for unit in self.units.values() if unit.kind == "Project"]
        if len(project_units) > 1:
            first = project_units[0]
            diagnostics.append(
                Diagnostic(
                    code="multiple_projects",
                    message="an authoring project may contain only one Project unit",
                    unit_id=first.id,
                    source_path=_source_path(first),
                    span=first.source_span,
                    related=tuple(
                        RelatedLocation(_source_path(item), item.source_span)
                        for item in project_units[1:]
                    ),
                )
            )

        by_uid: dict[str, list[tuple[LogicalUnit, Node]]] = {}
        for unit, node in self.walk_nodes():
            by_uid.setdefault(node.uid, []).append((unit, node))
        for uid, values in by_uid.items():
            if len(values) > 1:
                first_unit, first_node = values[0]
                diagnostics.append(
                    Diagnostic(
                        code="duplicate_uid",
                        message=f"duplicate node uid {uid!r}",
                        unit_id=first_unit.id,
                        uid=uid,
                        source_path=_source_path(first_unit),
                        span=first_node.source_span,
                        related=tuple(
                            RelatedLocation(_source_path(unit), node.source_span)
                            for unit, node in values[1:]
                        ),
                    )
                )

        unit_index = {
            unit.id: unit for unit in self.units.values() if len(by_id[unit.id]) == 1
        }
        for unit in self.units.values():
            diagnostics.extend(_validate_unit(unit, unit_index))
        return tuple(diagnostics)

    def assert_valid(self) -> None:
        diagnostics = tuple(item for item in self.validate() if item.severity == "error")
        if diagnostics:
            raise ProgramValidationError(diagnostics)


class DropPlacement(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    CHILD = "child"
    WRAP = "wrap"


@dataclass(frozen=True)
class DropCheck:
    allowed: bool
    reason: str = ""
    slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class NodeLocation:
    unit_id: str
    parent_uid: str | None
    slot: str
    index: int


def validate_author_value(value: Any, path: str = "value") -> None:
    if isinstance(value, str) and value.startswith("res://"):
        if "\\" in value or value.count("#") > 1:
            raise ProgramError("invalid_resource", f"{path} is not a canonical res:// reference")
        resource, separator, fragment = value[6:].partition("#")
        pure = PurePosixPath(resource)
        if (
            not resource
            or pure.is_absolute()
            or pure.as_posix() != resource
            or any(part in {"", ".", ".."} or ":" in part for part in pure.parts)
        ):
            raise ProgramError("invalid_resource", f"{path} is not a project-relative res:// reference")
        if separator and not fragment:
            raise ProgramError("invalid_resource", f"{path} has an invalid subresource fragment")
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ProgramError("invalid_value", f"{path} must be a finite float")
    if value is None or isinstance(value, (bool, int, float, str, Ref, Expr)):
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            validate_author_value(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProgramError("invalid_value", f"{path} dict keys must be strings")
            validate_author_value(item, f"{path}.{key}")
        return
    raise ProgramError(
        "invalid_value",
        f"{path} contains unsupported value type {type(value).__name__}",
    )


def parse_author_value(source: str) -> Any:
    """Parse one editable AuthorValue expression without executing Python.

    Inspector container fields use the same closed value language as authoring
    files.  Keeping this parser headless prevents Qt from inventing a looser
    interpretation of ``Ref``/``Expr`` or Python literals.
    """

    try:
        root = ast.parse(source, mode="eval").body
    except SyntaxError as exc:
        raise ProgramError(
            "invalid_value", "not a valid author value expression"
        ) from exc

    def parse(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if node.value is None or isinstance(node.value, (bool, int, float, str)):
                return node.value
        elif isinstance(node, ast.List):
            return [parse(item) for item in node.elts]
        elif isinstance(node, ast.Tuple):
            return tuple(parse(item) for item in node.elts)
        elif isinstance(node, ast.Dict):
            result: dict[str, Any] = {}
            for key_node, value_node in zip(node.keys, node.values):
                if key_node is None:
                    raise ProgramError(
                        "invalid_value", "dictionary unpacking is not supported"
                    )
                key = parse(key_node)
                if not isinstance(key, str):
                    raise ProgramError("invalid_value", "dictionary keys must be strings")
                result[key] = parse(value_node)
            return result
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            operand = parse(node.operand)
            if isinstance(operand, bool) or not isinstance(operand, (int, float)):
                raise ProgramError("invalid_value", "unary +/- is only supported for numbers")
            return -operand if isinstance(node.op, ast.USub) else +operand
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            constructor = {"Ref": Ref, "Expr": Expr}.get(node.func.id)
            if constructor is not None:
                if any(keyword.arg is None for keyword in node.keywords):
                    raise ProgramError("invalid_value", "** expansion is not supported")
                positional = [parse(item) for item in node.args]
                keywords: dict[str, Any] = {}
                for keyword_argument in node.keywords:
                    assert keyword_argument.arg is not None
                    if keyword_argument.arg in keywords:
                        raise ProgramError(
                            "invalid_value",
                            f"duplicate keyword {keyword_argument.arg!r}",
                        )
                    keywords[keyword_argument.arg] = parse(keyword_argument.value)
                try:
                    inspect.signature(constructor).bind(*positional, **keywords)
                    return constructor(*positional, **keywords)
                except (TypeError, ValueError) as exc:
                    raise ProgramError(
                        "invalid_value", f"invalid {node.func.id} value: {exc}"
                    ) from exc
        raise ProgramError(
            "invalid_value", f"unsupported author value expression {type(node).__name__}"
        )

    value = parse(root)
    validate_author_value(value)
    return value


def _annotation_accepts(value: Any, annotation: Any) -> bool:
    """Check a known author value against one resolved DSL annotation."""

    if annotation is Any or annotation is inspect.Parameter.empty:
        return True
    if annotation is None or annotation is type(None):
        return value is None
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in {types.UnionType, Union}:
        return any(_annotation_accepts(value, option) for option in arguments)
    if origin is Literal:
        return any(type(value) is type(option) and value == option for option in arguments)
    if origin in {list, collections_abc.Sequence, Sequence}:
        if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
            return False
        item_type = arguments[0] if arguments else Any
        return all(_annotation_accepts(item, item_type) for item in value)
    if origin is tuple:
        if not isinstance(value, tuple):
            return False
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return all(_annotation_accepts(item, arguments[0]) for item in value)
        return len(value) == len(arguments) and all(
            _annotation_accepts(item, expected)
            for item, expected in zip(value, arguments)
        )
    if origin in {dict, collections_abc.Mapping, Mapping}:
        if not isinstance(value, dict):
            return False
        key_type, item_type = arguments if len(arguments) == 2 else (Any, Any)
        return all(
            _annotation_accepts(key, key_type)
            and _annotation_accepts(item, item_type)
            for key, item in value.items()
        )
    if annotation is bool:
        return type(value) is bool
    if annotation is int:
        return type(value) is int
    if annotation is float:
        return not isinstance(value, bool) and isinstance(value, (int, float))
    if annotation is str:
        return type(value) is str
    if isinstance(annotation, type):
        return isinstance(value, annotation)
    return True


_PARAMETER_ANNOTATION_NAMES: dict[str, Any] = {
    "Any": Any,
    "bool": bool,
    "dict": dict,
    "Expr": Expr,
    "float": float,
    "int": int,
    "list": list,
    "Literal": Literal,
    "Mapping": Mapping,
    "None": type(None),
    "Optional": Optional,
    "Ref": Ref,
    "Sequence": Sequence,
    "str": str,
    "tuple": tuple,
    "Union": Union,
}


def _resolve_parameter_annotation(source: str) -> Any:
    """Resolve a small, non-executing annotation grammar used by Task/Function."""

    try:
        expression = ast.parse(source, mode="eval").body
    except SyntaxError as exc:
        raise ProgramError("invalid_parameter", f"invalid parameter annotation {source!r}") from exc

    def resolve(node: ast.AST) -> Any:
        if isinstance(node, ast.Name):
            if node.id not in _PARAMETER_ANNOTATION_NAMES:
                raise ProgramError(
                    "invalid_parameter",
                    f"unsupported parameter annotation name {node.id!r}",
                )
            return _PARAMETER_ANNOTATION_NAMES[node.id]
        if isinstance(node, ast.Constant) and node.value is None:
            return type(None)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return resolve(node.left) | resolve(node.right)
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            base_name = node.value.id
            if base_name not in {
                "dict",
                "list",
                "Literal",
                "Mapping",
                "Optional",
                "Sequence",
                "tuple",
                "Union",
            }:
                raise ProgramError(
                    "invalid_parameter",
                    f"unsupported parameter annotation container {base_name!r}",
                )
            slices = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
            if base_name == "Literal":
                literals: list[Any] = []
                for item in slices:
                    if not isinstance(item, ast.Constant) or not isinstance(
                        item.value, (str, int, float, bool, type(None))
                    ):
                        raise ProgramError(
                            "invalid_parameter",
                            "Literal parameters must contain scalar constants",
                        )
                    literals.append(item.value)
                return Literal[tuple(literals)]
            resolved = tuple(resolve(item) for item in slices)
            if base_name == "Optional":
                if len(resolved) != 1:
                    raise ProgramError("invalid_parameter", "Optional requires one type")
                return Optional[resolved[0]]
            base = _PARAMETER_ANNOTATION_NAMES[base_name]
            argument: Any = resolved[0] if len(resolved) == 1 else resolved
            try:
                return base[argument]
            except TypeError as exc:
                raise ProgramError(
                    "invalid_parameter",
                    f"invalid parameter annotation {source!r}",
                ) from exc
        raise ProgramError(
            "invalid_parameter",
            f"unsupported parameter annotation {source!r}",
        )

    return resolve(expression)


_DIALOGUE_ITEM_FIELDS: dict[str, Any] = {
    "text": str,
    "character": str | None,
    "name": str | None,
    "portrait": str | None,
    "position": Literal["left", "right"],
    "balloon_style": int,
    "duration": int | None,
    "portrait_scale": float,
    "portrait_x": float | None,
    "portrait_y": float | None,
    "balloon_x": float | None,
    "balloon_y": float | None,
    "character_num": int,
    "keep_balloons": int,
    "stay_active": bool,
}


def _dialogue_error(value: Any) -> str | None:
    if isinstance(value, Expr):
        return None
    if isinstance(value, str):
        return None if value.startswith("res://") else "string dialogue must be a res:// resource"
    if not isinstance(value, (list, tuple)):
        return "dialogue must be Expr, res:// resource, or a list/tuple"
    for index, item in enumerate(value):
        if isinstance(item, tuple):
            if len(item) != 3 or any(
                not isinstance(part, (str, Expr)) for part in item
            ):
                return f"dialogue item {index} must be a three-string tuple"
            position = item[1]
            if isinstance(position, str) and position not in {"left", "right"}:
                return f"dialogue item {index} position must be 'left' or 'right'"
            continue
        if not isinstance(item, dict):
            return f"dialogue item {index} must be a tuple or dict"
        unknown = set(item) - set(_DIALOGUE_ITEM_FIELDS)
        if unknown:
            return f"dialogue item {index} has unknown fields {sorted(unknown)!r}"
        if "text" not in item:
            return f"dialogue item {index} requires field 'text'"
        for name, field_value in item.items():
            if isinstance(field_value, Expr):
                continue
            if not _annotation_accepts(field_value, _DIALOGUE_ITEM_FIELDS[name]):
                return f"dialogue item {index} field {name!r} has an invalid literal type"
    return None


def find_node(program: AuthoringProgram, uid: str) -> tuple[LogicalUnit, Node, NodeLocation]:
    matches: list[tuple[LogicalUnit, Node, NodeLocation]] = []
    for unit in program.units.values():
        _collect_locations(unit, unit.body, None, "body", uid, matches)
    if not matches:
        raise ProgramError("unknown_uid", f"unknown node uid {uid!r}")
    if len(matches) > 1:
        raise ProgramError("duplicate_uid", f"node uid {uid!r} is not unique")
    return matches[0]


def insert_node(
    program: AuthoringProgram,
    unit_id: str,
    parent_uid: str | None,
    slot: str,
    index: int,
    node: Node,
) -> AuthoringProgram:
    result = program.clone()
    unit = result.get_unit(unit_id)
    values = _child_list(unit, parent_uid, slot)
    if index < 0 or index > len(values):
        raise ProgramError("invalid_index", f"insert index {index} is out of range")
    values.insert(index, copy.deepcopy(node))
    _assert_no_new_errors(program, result)
    return result


def insert_new_node(
    program: AuthoringProgram,
    unit_id: str,
    node: Node,
    target_uid: str | None = None,
    placement: DropPlacement | str = DropPlacement.AFTER,
    *,
    target_slot: str | None = None,
) -> AuthoringProgram:
    """Insert one new node at a root or explicit visual drop placement."""

    placement = DropPlacement(placement)
    if target_uid is None:
        if placement not in {DropPlacement.BEFORE, DropPlacement.AFTER}:
            raise ProgramError("invalid_insert", "empty logical units accept a root statement")
        unit = program.get_unit(unit_id)
        return insert_node(program, unit_id, None, "body", len(unit.body), node)
    unit, target, location = find_node(program, target_uid)
    if unit.id != unit_id:
        raise ProgramError("invalid_insert", "drop target belongs to another logical unit")
    if placement in {DropPlacement.BEFORE, DropPlacement.AFTER}:
        offset = 0 if placement == DropPlacement.BEFORE else 1
        return insert_node(
            program, unit_id, location.parent_uid, location.slot, location.index + offset, node
        )
    if placement == DropPlacement.WRAP:
        if node.kind == "Parallel":
            wrapper = copy.deepcopy(node)
            branches = wrapper.children.get("branches", [])
            if len(branches) != 1 or branches[0].children.get("body"):
                raise ProgramError("invalid_wrap", "new Parallel wrappers require one empty branch")
            branches[0].children["body"] = [copy.deepcopy(target)]
            result = program.clone()
            result_unit, _target, result_location = find_node(result, target_uid)
            values = _child_list(
                result_unit, result_location.parent_uid, result_location.slot
            )
            values[result_location.index] = wrapper
            _assert_no_new_errors(program, result)
            return result
        return wrap_node(program, target_uid, node, target_slot)
    if target.kind == "Parallel" and target_slot == "new_branch":
        result = program.clone()
        _unit, parallel, _location = find_node(result, target_uid)
        index = len(parallel.children.get("branches", []))
        branch = Node(
            kind="Branch",
            children={"body": [copy.deepcopy(node)]},
            uid=f"{parallel.uid}__branch_{index}",
        )
        parallel.children.setdefault("branches", []).append(branch)
        _assert_no_new_errors(program, result)
        return result
    if target.kind == "Parallel" and target_slot is None:
        branches = target.children.get("branches", [])
        if not branches:
            raise ProgramError("invalid_insert", "Parallel has no branch")
        target_uid, target_slot = branches[0].uid, "body"
    slot = target_slot or _default_child_slot(target)
    target_unit, child_target, _child_location = find_node(program, target_uid)
    return insert_node(
        program,
        target_unit.id,
        child_target.uid,
        slot,
        len(child_target.children.get(slot, [])),
        node,
    )


def _ancestor_chain(program: AuthoringProgram, unit_id: str, uid: str) -> tuple[Node, ...]:
    """Ancestors of `uid` inside its unit, outermost first."""

    def walk(nodes: list[Node], trail: tuple[Node, ...]) -> tuple[Node, ...] | None:
        for node in nodes:
            if node.uid == uid:
                return trail
            for children in node.children.values():
                found = walk(children, (*trail, node))
                if found is not None:
                    return found
        return None

    unit = program.get_unit(unit_id)
    found = walk(unit.body, ())
    if found is None:
        raise ProgramError("unknown_uid", f"unknown node uid {uid!r}")
    return found


def _validate_node_in_context(
    program: AuthoringProgram,
    unit: LogicalUnit,
    node: Node,
    ancestors: tuple[Node, ...],
) -> None:
    """Reject the node when its own validation would gain a new error."""

    unit_index = {
        item.id: item for item in program.logical_units()
    }
    problems = [
        item
        for item in _validate_node(unit, node, unit_index, ancestors)
        if item.severity == "error"
    ]
    if problems:
        raise ProgramError("invalid_insert", problems[0].message)


def _check_insert(
    program: AuthoringProgram,
    unit_id: str,
    node: Node,
    target_uid: str | None,
    placement: DropPlacement | str,
    *,
    target_slot: str | None = None,
) -> tuple[str, ...]:
    """Structural dry run for one insertion; never clones or fully validates."""

    placement = DropPlacement(placement)
    unit = program.get_unit(unit_id)
    if unit.kind == "Project":
        raise ProgramError("invalid_insert", "Project does not contain statements")
    if target_uid is None:
        if placement not in {DropPlacement.BEFORE, DropPlacement.AFTER}:
            raise ProgramError("invalid_insert", "empty logical units accept a root statement")
        _validate_node_in_context(program, unit, node, ())
        return ()
    _unit, target, _location = find_node(program, target_uid)
    if _unit.id != unit_id:
        raise ProgramError("invalid_insert", "drop target belongs to another logical unit")
    ancestors = _ancestor_chain(program, unit_id, target_uid)

    if placement in {DropPlacement.BEFORE, DropPlacement.AFTER}:
        _validate_node_in_context(program, unit, node, ancestors)
        return ()
    if placement == DropPlacement.WRAP:
        if node.kind == "Parallel":
            branches = node.children.get("branches", [])
            if len(branches) != 1 or branches[0].children.get("body"):
                raise ProgramError(
                    "invalid_wrap", "new Parallel wrappers require one empty branch"
                )
            _validate_node_in_context(program, unit, node, ancestors)
            _validate_node_in_context(
                program, unit, target, ancestors + (node, branches[0])
            )
            return ()
        slot = target_slot or _default_child_slot(node)
        if slot not in _CHILD_SLOTS.get(node.kind, ()):
            raise ProgramError("invalid_wrap", f"{node.kind} cannot wrap targets")
        if node.children.get(slot):
            raise ProgramError("invalid_wrap", "wrapper target slot must be empty")
        _validate_node_in_context(program, unit, node, ancestors)
        _validate_node_in_context(program, unit, target, ancestors + (node,))
        return ()
    if target.kind == "Parallel" and target_slot == "new_branch":
        _validate_node_in_context(program, unit, node, ancestors + (target,))
        return ()
    if target.kind == "Parallel" and target_slot is None:
        branches = target.children.get("branches", [])
        if not branches:
            raise ProgramError("invalid_insert", "Parallel has no branch")
        first_branch = branches[0]
        _validate_node_in_context(
            program, unit, node, ancestors + (target, first_branch)
        )
        return ()
    slot = target_slot or _default_child_slot(target)
    if slot not in _CHILD_SLOTS.get(target.kind, ()):
        raise ProgramError("invalid_insert", f"{target.kind} does not accept child slot {slot!r}")
    if target.kind == "SpawnTask" and slot == "body" and "task" in target.arguments:
        raise ProgramError(
            "invalid_spawn_task", "SpawnTask requires exactly one of task or body"
        )
    _validate_node_in_context(program, unit, node, ancestors + (target,))
    return ()


def validate_insert(
    program: AuthoringProgram,
    unit_id: str,
    node: Node,
    target_uid: str | None = None,
    placement: DropPlacement | str = DropPlacement.AFTER,
    *,
    target_slot: str | None = None,
) -> DropCheck:
    """Return drop feasibility without mutating, cloning, or fully validating.

    The palette and the flow call this on every hover, so it must stay cheap:
    only the placement resolution and the inserted node's own context rules are
    checked.  The full model validation still guards the real insertion.
    """

    slots: tuple[str, ...] = ()
    if target_uid is not None:
        try:
            _unit, target, _location = find_node(program, target_uid)
            if target.kind == "Parallel":
                slots = tuple(branch.uid for branch in target.children.get("branches", ())) + (
                    "new_branch",
                )
            else:
                slots = _CHILD_SLOTS.get(target.kind, ())
        except ProgramError as exc:
            return DropCheck(False, exc.message)
    try:
        _check_insert(
            program, unit_id, node, target_uid, placement, target_slot=target_slot
        )
    except (ProgramError, ProgramValidationError) as exc:
        return DropCheck(False, exc.message, slots)
    return DropCheck(True, slots=slots)


def node_from_palette(
    kind: str,
    program: AuthoringProgram,
    unit_kind: str,
    reference_id: str | None = None,
    *,
    template_target: TemplateTarget | None = None,
) -> Node:
    """Create the one canonical starter value used by every authoring UI.

    Defaults stay next to the DSL rather than in Qt labels.  Context validity is
    still decided by :func:`validate_insert`; this factory only guarantees a
    structurally valid prototype and never guesses a reference.
    """

    del program  # reserved for future signature-derived project defaults
    if unit_kind not in UNIT_KINDS or unit_kind == "Project":
        raise ProgramError("invalid_context", f"{unit_kind} cannot contain statements")
    if template_target is not None:
        positional, keywords = _template_prototype_arguments(template_target.signature)
        return make_template_call(
            template_target,
            positional=positional,
            keywords=keywords,
        )

    from . import dsl  # local import avoids program <-> public DSL import cycle

    ref = Ref(reference_id) if reference_id else None
    if reference_kinds_for_node(kind) and ref is None:
        raise ProgramError("missing_reference", f"{kind} requires an explicit reference")
    factories = {
        "Wait": lambda: dsl.Wait(60),
        "At": lambda: dsl.At(0, []),
        "Repeat": lambda: dsl.Repeat(1, []),
        "While": lambda: dsl.While(Expr("True"), []),
        "If": lambda: dsl.If(Expr("True"), []),
        "Else": lambda: dsl.Else([]),
        "ForEach": lambda: dsl.ForEach("item", [], []),
        "Parallel": lambda: dsl.Parallel([[]]),
        "SpawnTask": lambda: dsl.SpawnTask(ref),
        "Break": dsl.Break,
        "Continue": dsl.Continue,
        "Return": dsl.Return,
        "Set": lambda: dsl.Set("value", 0),
        "Call": lambda: dsl.Call(ref),
        "RawPython": lambda: dsl.RawPython("pass"),
        "RunWave": lambda: dsl.RunWave(ref),
        "RunBoss": lambda: dsl.RunBoss(ref),
        "SetBackground": lambda: dsl.SetBackground(""),
        "PlayBGM": lambda: dsl.PlayBGM(""),
        "PlayDialogue": lambda: dsl.PlayDialogue([]),
        "SpawnEnemy": lambda: dsl.SpawnEnemy(ref),
        "MoveTo": lambda: dsl.MoveTo(0.0, 0.5),
        "MoveLinear": lambda: dsl.MoveLinear(0.0, -0.2),
        "SetPosition": lambda: dsl.SetPosition(0.0, 0.5),
        "Fire": lambda: dsl.Fire(x=0.0, y=0.0),
        "FireCircle": lambda: dsl.FireCircle(x=0.0, y=0.0, count=12),
        "FireArc": lambda: dsl.FireArc(x=0.0, y=0.0),
        "FireAtPlayer": lambda: dsl.FireAtPlayer(x=0.0, y=0.0),
        "FirePolar": lambda: dsl.FirePolar(0.1, 0.0, center=[0.0, 0.0]),
        "FireOrbit": lambda: dsl.FireOrbit(0.1, 0.0, center=[0.0, 0.0]),
        "ClearBullets": dsl.ClearBullets,
        "Kill": dsl.Kill,
        "PlaySE": lambda: dsl.PlaySE(""),
        "CreateLaser": lambda: dsl.CreateLaser(0.0, 0.0, -90.0, 0.2, 0.6, 0.2, 0.02),
        "CreateBentLaser": lambda: dsl.CreateBentLaser(0.0, 0.0, 180, 0.02),
        "RemoveLaser": lambda: dsl.RemoveLaser(Expr("laser")),
        "ClearLasers": dsl.ClearLasers,
    }
    try:
        return factories[kind]()
    except KeyError as exc:
        raise ProgramError("unknown_node_kind", f"unknown palette node {kind!r}") from exc


def reference_kinds_for_node(kind: str) -> tuple[str, ...]:
    """Return typed Ref targets without making Qt duplicate DSL semantics."""

    values = {
        target
        for (node_kind, _field), targets in _REF_TARGETS.items()
        if node_kind == kind
        for target in targets
    }
    return tuple(sorted(values))


def reference_kinds_for_field(kind: str, field: str) -> tuple[str, ...]:
    """Expose the model's typed Ref rule to generated Inspector controls."""

    return tuple(sorted(_REF_TARGETS.get((kind, field), ())))


def _template_prototype_arguments(
    signature: inspect.Signature | None,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if signature is None:
        return (), {}
    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name == "uid" or parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        if parameter.default is not inspect.Parameter.empty:
            value = copy.deepcopy(parameter.default)
        else:
            annotation = parameter.annotation
            normalized = (
                annotation.strip()
                if isinstance(annotation, str)
                else getattr(annotation, "__name__", str(annotation))
            )
            if normalized == "bool":
                value = False
            elif normalized == "int":
                value = 0
            elif normalized == "float":
                value = 0.0
            elif normalized == "str":
                value = ""
            elif normalized.startswith(("list", "Sequence", "tuple")):
                value = []
            elif normalized.startswith(("dict", "Mapping")):
                value = {}
            else:
                raise ProgramError(
                    "template_argument_required",
                    f"template parameter {name!r} has no safe default",
                )
        validate_author_value(value, f"TemplateCall.{name}")
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keywords[name] = value
    return tuple(positional), keywords


def create_unit(
    program: AuthoringProgram,
    unit: LogicalUnit,
    *,
    register_stage: bool = True,
) -> AuthoringProgram:
    if unit.kind == "Project":
        raise ProgramError("invalid_unit", "an authoring project already owns its Project unit")
    if any(candidate.id == unit.id for candidate in program.logical_units()):
        raise ProgramError("duplicate_unit_id", f"logical unit {unit.id!r} already exists")
    result = program.clone()
    result.units[unit.id] = unit.clone()
    if unit.kind == "Stage" and register_stage:
        projects = [item for item in result.logical_units() if item.kind == "Project"]
        if len(projects) != 1:
            raise ProgramError("missing_project", "stage registration requires exactly one Project")
        project = projects[0]
        stages = list(project.metadata.get("stages", []))
        stages.append(Ref(unit.id))
        project.metadata["stages"] = stages
        if not isinstance(project.metadata.get("start_stage"), Ref):
            project.metadata["start_stage"] = Ref(unit.id)
    _assert_no_new_errors(program, result)
    return result


def duplicate_unit(
    program: AuthoringProgram,
    source_id: str,
    new_id: str,
    new_name: str,
    *,
    register_stage: bool = False,
) -> AuthoringProgram:
    source = program.get_unit(source_id)
    if source.kind == "Project":
        raise ProgramError("invalid_unit", "Project cannot be duplicated")
    duplicate = source.clone()
    duplicate.id = new_id
    duplicate.name = new_name
    duplicate.source_path = None
    duplicate.source_span = None
    duplicate.metadata = _rewrite_ref_value(duplicate.metadata, source_id, new_id)
    duplicate.parameters = tuple(
        Parameter(
            item.name,
            item.annotation,
            _rewrite_ref_value(item.default, source_id, new_id) if item.has_default else _NO_DEFAULT,
        )
        for item in duplicate.parameters
    )
    for node in duplicate.body:
        _regenerate_node_uids(node)
    for node in duplicate.walk_nodes():
        node.source_span = None
        node.arguments = _rewrite_ref_value(node.arguments, source_id, new_id)
        node.positional_arguments = tuple(
            _rewrite_ref_value(value, source_id, new_id)
            for value in node.positional_arguments
        )
    return create_unit(program, duplicate, register_stage=register_stage)


def delete_unit(
    program: AuthoringProgram,
    unit_id: str,
    *,
    replacement_start_stage: str | None = None,
) -> AuthoringProgram:
    removed = program.get_unit(unit_id)
    if removed.kind == "Project":
        raise ProgramError("invalid_unit", "Project cannot be deleted")
    references = unit_reference_locations(program, unit_id)
    non_project = [location for location in references if not location.startswith("Project.")]
    if non_project:
        raise ProgramError(
            "unit_in_use", f"{unit_id!r} is referenced by {', '.join(non_project)}"
        )
    result = program.clone()
    del result.units[unit_id]
    if removed.kind == "Stage":
        project = next((item for item in result.logical_units() if item.kind == "Project"), None)
        if project is not None:
            stages = [ref for ref in project.metadata.get("stages", []) if ref != Ref(unit_id)]
            if not stages:
                raise ProgramError("invalid_project_stages", "the last registered Stage cannot be deleted")
            project.metadata["stages"] = stages
            if project.metadata.get("start_stage") == Ref(unit_id):
                replacement = replacement_start_stage or stages[0].id
                if Ref(replacement) not in stages:
                    raise ProgramError("invalid_start_stage", "replacement start Stage is not registered")
                project.metadata["start_stage"] = Ref(replacement)
    _assert_no_new_errors(program, result)
    return result


def _regenerate_node_uids(node: Node) -> None:
    node.uid = new_uid(node.kind)
    for slot, children in node.children.items():
        for index, child in enumerate(children):
            if node.kind == "Parallel" and slot == "branches":
                child.uid = f"{node.uid}__branch_{index}"
                for branch_child in child.children.get("body", []):
                    _regenerate_node_uids(branch_child)
            else:
                _regenerate_node_uids(child)


def _rewrite_ref_value(value: Any, old_id: str, new_id: str) -> Any:
    if isinstance(value, Ref):
        return Ref(new_id if value.id == old_id else value.id)
    if isinstance(value, list):
        return [_rewrite_ref_value(item, old_id, new_id) for item in value]
    if isinstance(value, tuple):
        return tuple(_rewrite_ref_value(item, old_id, new_id) for item in value)
    if isinstance(value, Mapping):
        return {
            key: _rewrite_ref_value(item, old_id, new_id)
            for key, item in value.items()
        }
    return copy.deepcopy(value)


def unit_reference_locations(program: AuthoringProgram, target_id: str) -> tuple[str, ...]:
    locations: list[str] = []

    def collect(value: Any, location: str) -> None:
        if isinstance(value, Ref) and value.id == target_id:
            locations.append(location)
        elif isinstance(value, Mapping):
            for key, item in value.items():
                collect(item, f"{location}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                collect(item, f"{location}[{index}]")

    for unit in program.logical_units():
        if unit.id == target_id:
            continue
        prefix = "Project" if unit.kind == "Project" else unit.id
        collect(unit.metadata, prefix)
        for parameter in unit.parameters:
            if parameter.has_default:
                collect(parameter.default, f"{prefix}.parameters.{parameter.name}")
        for node in unit.walk_nodes():
            collect(node.arguments, f"{prefix}.{node.uid}")
            collect(node.positional_arguments, f"{prefix}.{node.uid}")
    return tuple(locations)


def duplicate_node(program: AuthoringProgram, uid: str) -> AuthoringProgram:
    """Copy one node subtree with fresh UIDs right after the source node."""

    unit, node, location = find_node(program, uid)
    clone = copy.deepcopy(node)
    _regenerate_node_uids(clone)
    return insert_node(
        program, unit.id, location.parent_uid, location.slot, location.index + 1, clone
    )


def delete_node(program: AuthoringProgram, uid: str) -> AuthoringProgram:
    result = program.clone()
    unit, _node, location = find_node(result, uid)
    values = _child_list(unit, location.parent_uid, location.slot)
    del values[location.index]
    _assert_no_new_errors(program, result)
    return result


def move_node(
    program: AuthoringProgram,
    uid: str,
    target_uid: str,
    placement: DropPlacement | str,
    *,
    target_slot: str | None = None,
) -> AuthoringProgram:
    placement = DropPlacement(placement)
    if uid == target_uid:
        raise ProgramError("invalid_move", "a node cannot be dropped on itself")
    result = program.clone()
    source_unit, source_node, source_location = find_node(result, uid)
    _target_unit, target_node, _target_location = find_node(result, target_uid)
    if any(item.uid == target_uid for item in source_node.walk()):
        raise ProgramError("invalid_move", "a node cannot move into its descendant")
    source_values = _child_list(source_unit, source_location.parent_uid, source_location.slot)
    del source_values[source_location.index]

    target_unit, target_node, target_location = find_node(result, target_uid)
    if source_unit.id != target_unit.id:
        raise ProgramError("invalid_move", "nodes cannot move between logical units")
    if placement in {DropPlacement.BEFORE, DropPlacement.AFTER}:
        target_values = _child_list(target_unit, target_location.parent_uid, target_location.slot)
        offset = 0 if placement == DropPlacement.BEFORE else 1
        target_values.insert(target_location.index + offset, source_node)
    elif placement == DropPlacement.CHILD:
        slot = target_slot or _default_child_slot(target_node)
        target_node.children.setdefault(slot, []).append(source_node)
    else:
        slot = target_slot or _default_child_slot(source_node)
        if source_node.children.get(slot):
            raise ProgramError("invalid_wrap", "wrapper target slot must be empty")
        source_node.children[slot] = [target_node]
        target_values = _child_list(target_unit, target_location.parent_uid, target_location.slot)
        target_values[target_location.index] = source_node
    _assert_no_new_errors(program, result)
    return result


def wrap_node(
    program: AuthoringProgram,
    uid: str,
    wrapper: Node,
    slot: str | None = None,
) -> AuthoringProgram:
    result = program.clone()
    unit, node, location = find_node(result, uid)
    wrapper_copy = copy.deepcopy(wrapper)
    target_slot = slot or _default_child_slot(wrapper_copy)
    if wrapper_copy.children.get(target_slot):
        raise ProgramError("invalid_wrap", "wrapper target slot must be empty")
    wrapper_copy.children[target_slot] = [node]
    values = _child_list(unit, location.parent_uid, location.slot)
    values[location.index] = wrapper_copy
    _assert_no_new_errors(program, result)
    return result


def set_argument(
    program: AuthoringProgram,
    uid: str,
    name: str,
    value: Any,
) -> AuthoringProgram:
    if not _is_python_identifier(name):
        raise ProgramError("invalid_argument", "argument name must be a Python identifier")
    if name == "uid":
        raise ProgramError("invalid_argument", "uid is node identity, not an argument")
    validate_author_value(value, f"{uid}.{name}")
    result = program.clone()
    _unit, node, _location = find_node(result, uid)
    if node.kind == "TemplateCall":
        node.arguments[name] = copy.deepcopy(value)
        _assert_no_new_errors(program, result)
        return result
    from . import dsl

    constructor = dsl.NODE_CONSTRUCTORS.get(node.kind)
    signature = inspect.signature(constructor) if constructor is not None else None
    parameter = signature.parameters.get(name) if signature is not None else None
    accepts_extra = bool(
        signature
        and any(
            item.kind == inspect.Parameter.VAR_KEYWORD
            for item in signature.parameters.values()
        )
    )
    if name in _CHILD_SLOTS.get(node.kind, ()):
        raise ProgramError(
            "invalid_argument", f"{node.kind}.{name} is a child slot, not an argument"
        )
    if parameter is None and not accepts_extra:
        raise ProgramError("invalid_argument", f"{node.kind} has no argument {name!r}")
    node.arguments[name] = copy.deepcopy(value)
    try:
        canonical = _canonical_node(node)
    except (TypeError, ProgramError) as exc:
        raise ProgramError(
            "invalid_argument", f"invalid {node.kind}.{name}: {exc}"
        ) from exc
    node.arguments = canonical.arguments
    node.children = canonical.children
    _assert_no_new_errors(program, result)
    return result


def set_template_positional_argument(
    program: AuthoringProgram,
    uid: str,
    index: int,
    value: Any,
) -> AuthoringProgram:
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ProgramError("invalid_index", "template argument index must be non-negative")
    validate_author_value(value, f"{uid}.args[{index}]")
    result = program.clone()
    _unit, node, _location = find_node(result, uid)
    if node.kind != "TemplateCall":
        raise ProgramError("invalid_argument", "positional arguments belong to TemplateCall")
    if index >= len(node.positional_arguments):
        raise ProgramError("invalid_index", f"template argument index {index} is out of range")
    values = list(node.positional_arguments)
    values[index] = copy.deepcopy(value)
    node.positional_arguments = tuple(values)
    _assert_no_new_errors(program, result)
    return result


def set_unit_field(
    program: AuthoringProgram,
    unit_id: str,
    name: str,
    value: Any,
) -> AuthoringProgram:
    result = program.clone()
    unit = result.get_unit(unit_id)
    if name == "name":
        if not isinstance(value, str) or not value.strip():
            raise ProgramError("invalid_unit_name", "logical unit name must be text")
        unit.name = value.strip()
    elif name == "parameters":
        from . import dsl

        if "parameters" not in inspect.signature(
            dsl.UNIT_CONSTRUCTORS[unit.kind]
        ).parameters:
            raise ProgramError(
                "invalid_unit_field", f"{unit.kind} does not accept parameters"
            )
        unit.parameters = _validated_parameters(value, unit.id)
    elif name in {"kind", "id", "body", "source_path", "assignment_name"}:
        raise ProgramError("immutable_unit_field", f"unit field {name!r} is not editable")
    else:
        from . import dsl

        signature = inspect.signature(dsl.UNIT_CONSTRUCTORS[unit.kind])
        if name not in signature.parameters or name in {
            "id",
            "name",
            "body",
            "parameters",
        }:
            raise ProgramError(
                "invalid_unit_field", f"{unit.kind} has no metadata field {name!r}"
            )
        validate_author_value(value, f"{unit_id}.{name}")
        unit.metadata[name] = copy.deepcopy(value)
        try:
            unit.metadata = _canonical_unit(unit).metadata
        except (TypeError, ProgramError) as exc:
            raise ProgramError(
                "invalid_unit_field", f"invalid {unit.kind}.{name}: {exc}"
            ) from exc
    _assert_no_new_errors(program, result)
    return result


def _assert_no_new_errors(
    original: AuthoringProgram,
    candidate: AuthoringProgram,
) -> None:
    before = Counter(
        _diagnostic_fingerprint(item)
        for item in original.validate()
        if item.severity == "error"
    )
    after_diagnostics = [
        item for item in candidate.validate() if item.severity == "error"
    ]
    remaining = before.copy()
    new_errors: list[Diagnostic] = []
    for diagnostic in after_diagnostics:
        fingerprint = _diagnostic_fingerprint(diagnostic)
        if remaining[fingerprint] > 0:
            remaining[fingerprint] -= 1
        else:
            new_errors.append(diagnostic)
    if new_errors:
        raise ProgramValidationError(new_errors)


def _diagnostic_fingerprint(diagnostic: Diagnostic) -> tuple[Any, ...]:
    return (
        diagnostic.code,
        diagnostic.severity,
        diagnostic.message,
        diagnostic.unit_id,
        diagnostic.uid,
        len(diagnostic.related),
    )


def _value_data(value: Any) -> Any:
    if isinstance(value, Ref):
        return {"$ref": value.id}
    if isinstance(value, Expr):
        return {"$expr": value.source}
    if isinstance(value, Mapping):
        return {key: _value_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return {"$tuple": [_value_data(item) for item in value]}
    if isinstance(value, list):
        return [_value_data(item) for item in value]
    return value


def _is_python_identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.isidentifier()
        and not keyword.iskeyword(value)
    )


def _validated_parameters(values: Iterable[Any], unit_id: str) -> tuple[Parameter, ...]:
    try:
        parameters = tuple(values)
    except TypeError as exc:
        raise ProgramError(
            "invalid_parameter", "parameters must contain Parameter values"
        ) from exc
    if not all(isinstance(item, Parameter) for item in parameters):
        raise ProgramError("invalid_parameter", "parameters must contain Parameter values")
    names = [item.name for item in parameters]
    if len(names) != len(set(names)):
        raise ProgramError("duplicate_parameter", f"duplicate parameter in {unit_id}")
    saw_default = False
    for parameter in parameters:
        annotation = _resolve_parameter_annotation(parameter.annotation)
        if parameter.has_default:
            if not isinstance(parameter.default, Expr) and not _annotation_accepts(
                parameter.default, annotation
            ):
                raise ProgramError(
                    "invalid_parameter",
                    f"default for parameter {parameter.name!r} does not match {parameter.annotation}",
                )
            saw_default = True
        elif saw_default:
            raise ProgramError(
                "invalid_parameter",
                f"required parameter {parameter.name!r} follows a default parameter in {unit_id}",
            )
    return parameters


def _source_path(unit: LogicalUnit) -> str:
    return str(unit.source_path) if unit.source_path is not None else ""


def _validate_unit(
    unit: LogicalUnit,
    unit_index: Mapping[str, LogicalUnit],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = list(_validate_unit_signature(unit))
    if unit.kind == "Project":
        if unit.body:
            diagnostics.append(_unit_diag(unit, "illegal_parent", "Project cannot contain statement nodes"))
        stages = unit.metadata.get("stages")
        start_stage = unit.metadata.get("start_stage")
        if not isinstance(stages, (list, tuple)) or not stages:
            diagnostics.append(_unit_diag(unit, "invalid_project_stages", "Project.stages must be a non-empty list"))
        if not isinstance(start_stage, Ref):
            diagnostics.append(_unit_diag(unit, "invalid_start_stage", "Project.start_stage must be a Ref"))
        for value in tuple(stages) if isinstance(stages, (list, tuple)) else ():
            diagnostics.extend(_validate_ref(unit, None, "stages", value, unit_index, {"Stage"}))
        if isinstance(stages, (list, tuple)):
            stage_ids = [value.id for value in stages if isinstance(value, Ref)]
            if len(stage_ids) != len(set(stage_ids)):
                diagnostics.append(
                    _unit_diag(
                        unit,
                        "duplicate_stage",
                        "Project.stages contains duplicate references",
                    )
                )
        if isinstance(start_stage, Ref):
            diagnostics.extend(_validate_ref(unit, None, "start_stage", start_stage, unit_index, {"Stage"}))
            if isinstance(stages, (list, tuple)) and start_stage not in stages:
                diagnostics.append(_unit_diag(unit, "start_stage_not_registered", "Project.start_stage must appear in Project.stages"))
    if unit.kind == "Boss":
        phases = unit.metadata.get("phases", [])
        if not isinstance(phases, (list, tuple)) or not phases:
            diagnostics.append(_unit_diag(unit, "invalid_boss_phases", "Boss.phases must be a non-empty list"))
        for value in phases if isinstance(phases, (list, tuple)) else ():
            diagnostics.extend(_validate_ref(unit, None, "phases", value, unit_index, {"Spell", "NonSpell"}))

    handled_metadata = {"start_stage", "stages"} if unit.kind == "Project" else set()
    if unit.kind == "Boss":
        handled_metadata.add("phases")
    for name, value in unit.metadata.items():
        if name in handled_metadata:
            continue
        diagnostics.extend(_validate_nested_refs(unit, None, name, value, unit_index))
    for parameter in unit.parameters:
        if parameter.has_default:
            diagnostics.extend(
                _validate_nested_refs(
                    unit,
                    None,
                    f"parameters.{parameter.name}.default",
                    parameter.default,
                    unit_index,
                )
            )
    for node in unit.body:
        diagnostics.extend(_validate_node(unit, node, unit_index, ()))
    return diagnostics


def _canonical_unit(unit: LogicalUnit) -> LogicalUnit:
    from . import dsl

    constructor = dsl.UNIT_CONSTRUCTORS[unit.kind]
    signature = inspect.signature(constructor)
    values: dict[str, Any] = {"id": unit.id, "name": unit.name}
    if "body" in signature.parameters:
        values["body"] = copy.deepcopy(unit.body)
    if "parameters" in signature.parameters:
        values["parameters"] = copy.deepcopy(unit.parameters)
    values.update(copy.deepcopy(unit.metadata))
    return constructor(**values)


def _validate_unit_signature(unit: LogicalUnit) -> list[Diagnostic]:
    from . import dsl

    constructor = dsl.UNIT_CONSTRUCTORS[unit.kind]
    signature = inspect.signature(constructor)
    type_hints = get_type_hints(constructor)
    metadata_parameters = {
        name: parameter
        for name, parameter in signature.parameters.items()
        if name not in {"id", "name", "body", "parameters"}
        and parameter.kind
        not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
    }
    diagnostics: list[Diagnostic] = []
    if unit.kind == "Boss" and unit.body:
        diagnostics.append(
            _unit_diag(
                unit,
                "illegal_parent",
                "Boss has no executable body in the existing Runtime",
            )
        )
    for name in sorted(set(unit.metadata) - set(metadata_parameters)):
        diagnostics.append(
            _unit_diag(
                unit,
                "invalid_unit_field",
                f"{unit.kind} has no metadata field {name!r}",
            )
        )
    for name, parameter in metadata_parameters.items():
        if parameter.default is inspect.Parameter.empty and name not in unit.metadata:
            diagnostics.append(
                _unit_diag(
                    unit,
                    "invalid_unit_field",
                    f"{unit.kind} requires metadata field {name!r}",
                )
            )
    for name, value in {"id": unit.id, "name": unit.name, **unit.metadata}.items():
        annotation = type_hints.get(name, Any)
        if not _annotation_accepts(value, annotation):
            diagnostics.append(
                _unit_diag(
                    unit,
                    "invalid_unit_field",
                    f"{unit.kind}.{name} does not match its DSL type annotation",
                )
            )
    if diagnostics:
        return diagnostics
    try:
        canonical = _canonical_unit(unit)
    except (TypeError, ProgramError) as exc:
        return [
            _unit_diag(unit, "invalid_unit_field", f"invalid {unit.kind} metadata: {exc}")
        ]
    if canonical.semantic_data() != unit.semantic_data():
        diagnostics.append(
            _unit_diag(
                unit,
                "noncanonical_unit_field",
                f"{unit.kind} metadata contains explicit default values",
            )
        )
    return diagnostics


def _validate_node(
    unit: LogicalUnit,
    node: Node,
    unit_index: Mapping[str, LogicalUnit],
    ancestors: tuple[Node, ...],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_validate_node_signature(unit, node))
    allowed_slots = _CHILD_SLOTS.get(node.kind, ())
    unknown_slots = set(node.children) - set(allowed_slots)
    for slot in sorted(unknown_slots):
        diagnostics.append(_node_diag(unit, node, "illegal_child_slot", f"{node.kind} does not accept child slot {slot!r}"))
    if node.kind != "SpawnTask":
        for slot in allowed_slots:
            if slot not in node.children:
                diagnostics.append(
                    _node_diag(
                        unit,
                        node,
                        "missing_child_slot",
                        f"{node.kind} requires child slot {slot!r}",
                    )
                )

    if node.kind not in INTERNAL_NODE_KINDS and node.kind not in CONTROL_NODE_KINDS and node.kind not in ACTION_NODE_KINDS:
        diagnostics.append(_node_diag(unit, node, "unknown_node", f"unknown node kind {node.kind!r}"))
    if node.kind in ACTION_NODE_KINDS and node.kind not in _UNIT_ACTIONS[unit.kind]:
        diagnostics.append(_node_diag(unit, node, "illegal_parent", f"{node.kind} is not valid in {unit.kind}"))
    if node.kind in {"Break", "Continue"} and not any(parent.kind in _LOOP_KINDS for parent in ancestors):
        diagnostics.append(_node_diag(unit, node, "illegal_parent", f"{node.kind} must be inside a loop"))
    if node.kind == "Return" and unit.kind not in {"Task", "Function"}:
        diagnostics.append(_node_diag(unit, node, "illegal_parent", "Return is only valid in Task or Function"))
    if node.kind == "Branch":
        if not ancestors or ancestors[-1].kind != "Parallel":
            diagnostics.append(_node_diag(unit, node, "illegal_parent", "Branch is only valid inside Parallel.branches"))
    if node.kind == "Else":
        if not ancestors or ancestors[-1].kind != "If":
            diagnostics.append(_node_diag(unit, node, "illegal_parent", "Else is only valid inside If"))
    if node.kind == "SpawnTask":
        has_task = "task" in node.arguments
        has_body = "body" in node.children
        if has_task == has_body:
            diagnostics.append(_node_diag(unit, node, "invalid_spawn_task", "SpawnTask requires exactly one of task or body"))
        if has_body and "arguments" in node.arguments:
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "invalid_spawn_task",
                    "inline SpawnTask body cannot receive arguments",
                )
            )
    if node.kind == "Parallel" and not node.children.get("branches"):
        diagnostics.append(_node_diag(unit, node, "invalid_parallel", "Parallel requires at least one branch"))
    if node.kind in {"Set", "ForEach"}:
        field_name = "name" if node.kind == "Set" else "target"
        target_name = node.arguments.get(field_name)
        if not _is_python_identifier(target_name):
            diagnostics.append(_node_diag(unit, node, "invalid_target", f"{node.kind}.{field_name} must be an identifier"))
    if node.kind in {"CreateLaser", "CreateBentLaser"} and "assign" in node.arguments:
        target_name = node.arguments["assign"]
        if not _is_python_identifier(target_name):
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "invalid_target",
                    f"{node.kind}.assign must be a non-keyword identifier",
                )
            )
    if node.kind == "RawPython":
        source = node.arguments.get("source")
        if not isinstance(source, str) or not source.strip():
            diagnostics.append(_node_diag(unit, node, "raw_python_syntax", "RawPython source must be non-empty text"))
        else:
            try:
                ast.parse(source, mode="exec")
            except SyntaxError as exc:
                diagnostics.append(_node_diag(unit, node, "raw_python_syntax", f"RawPython syntax error: {exc.msg}"))
    if node.kind == "PlayDialogue" and "dialogue_list" in node.arguments:
        dialogue_error = _dialogue_error(node.arguments["dialogue_list"])
        if dialogue_error is not None:
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "invalid_argument",
                    f"PlayDialogue.dialogue_list: {dialogue_error}",
                )
            )
    literal_rules = {
        "Wait": (("frames", 0),),
        "At": (("frame", 0),),
        "Repeat": (("count", 0),),
        "MoveTo": (("duration", 0),),
        "MoveLinear": (("duration", 0),),
        "FireCircle": (("count", 1),),
        "FireArc": (("count", 1),),
    }
    for name, minimum in literal_rules.get(node.kind, ()):
        if name not in node.arguments:
            continue
        value = node.arguments[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, Expr))
            or (isinstance(value, int) and value < minimum)
        ):
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "invalid_argument",
                    f"{node.kind}.{name} must be an integer >= {minimum} or Expr",
                )
            )
    if node.kind == "TemplateCall" and node.template is not None and not node.template.resolved:
        diagnostics.append(_node_diag(unit, node, "template_missing", f"template {node.template.identity!r} is unresolved"))

    for name, value in node.arguments.items():
        expected = _REF_TARGETS.get((node.kind, name))
        if expected is not None:
            diagnostics.extend(_validate_ref(unit, node, name, value, unit_index, expected))
        else:
            diagnostics.extend(_validate_nested_refs(unit, node, name, value, unit_index))
    for index, value in enumerate(node.positional_arguments):
        diagnostics.extend(_validate_nested_refs(unit, node, f"args[{index}]", value, unit_index))
    if node.kind in {"Call", "SpawnTask"}:
        diagnostics.extend(_validate_invocation(unit, node, unit_index))
    for slot, values in node.children.items():
        if node.kind == "Parallel" and slot == "branches":
            for child in values:
                if child.kind != "Branch":
                    diagnostics.append(_node_diag(unit, child, "illegal_parent", "Parallel.branches must contain Branch nodes"))
        for child in values:
            diagnostics.extend(_validate_node(unit, child, unit_index, (*ancestors, node)))
    return diagnostics


def _validate_invocation(
    unit: LogicalUnit,
    node: Node,
    unit_index: Mapping[str, LogicalUnit],
) -> list[Diagnostic]:
    reference_name = "function" if node.kind == "Call" else "task"
    reference = node.arguments.get(reference_name)
    if not isinstance(reference, Ref):
        return []
    target = unit_index.get(reference.id)
    expected_kinds = {"Function", "Task"} if node.kind == "Call" else {"Task"}
    if target is None or target.kind not in expected_kinds:
        return []
    if node.kind == "Call":
        positional = node.arguments.get("arguments", [])
        keywords = node.arguments.get("keywords", {})
    else:
        positional = []
        keywords = node.arguments.get("arguments", {})
    if not isinstance(positional, (list, tuple)) or not isinstance(keywords, Mapping):
        return []

    diagnostics: list[Diagnostic] = []
    parameters = list(target.parameters)
    bound: dict[str, Any] = {}
    if len(positional) > len(parameters):
        diagnostics.append(
            _node_diag(
                unit,
                node,
                "call_signature",
                f"{node.kind} passes too many positional arguments to {target.id!r}",
            )
        )
    for index, value in enumerate(positional[: len(parameters)]):
        bound[parameters[index].name] = value
    parameter_by_name = {parameter.name: parameter for parameter in parameters}
    for name, value in keywords.items():
        if name not in parameter_by_name:
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "call_signature",
                    f"{node.kind} passes unknown argument {name!r} to {target.id!r}",
                )
            )
            continue
        if name in bound:
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "call_signature",
                    f"{node.kind} passes argument {name!r} more than once",
                )
            )
            continue
        bound[name] = value
    for parameter in parameters:
        if parameter.name not in bound:
            if not parameter.has_default:
                diagnostics.append(
                    _node_diag(
                        unit,
                        node,
                        "call_signature",
                        f"{node.kind} is missing required argument {parameter.name!r} for {target.id!r}",
                    )
                )
            continue
        value = bound[parameter.name]
        try:
            annotation = _resolve_parameter_annotation(parameter.annotation)
        except ProgramError as exc:
            diagnostics.append(
                _node_diag(unit, node, "call_signature", exc.message)
            )
            continue
        if not isinstance(value, Expr) and not _annotation_accepts(value, annotation):
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "call_signature",
                    f"argument {parameter.name!r} for {target.id!r} does not match {parameter.annotation}",
                )
            )
    return diagnostics


def _validate_node_signature(unit: LogicalUnit, node: Node) -> list[Diagnostic]:
    if node.kind in INTERNAL_NODE_KINDS:
        if node.kind != "TemplateCall" and node.positional_arguments:
            return [
                _node_diag(
                    unit,
                    node,
                    "invalid_argument",
                    f"{node.kind} does not accept positional arguments",
                )
            ]
        return []
    from . import dsl

    constructor = dsl.NODE_CONSTRUCTORS.get(node.kind)
    if constructor is None:
        return []
    signature = inspect.signature(constructor)
    type_hints = get_type_hints(constructor)
    accepts_extra = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    child_fields = set(_CHILD_SLOTS.get(node.kind, ()))
    declared = {
        name
        for name, parameter in signature.parameters.items()
        if name != "uid"
        and name not in child_fields
        and parameter.kind
        not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
    }
    diagnostics: list[Diagnostic] = []
    if "uid" in node.arguments:
        diagnostics.append(
            _node_diag(
                unit,
                node,
                "invalid_argument",
                "uid is node identity, not an argument",
            )
        )
    if node.positional_arguments:
        diagnostics.append(
            _node_diag(
                unit,
                node,
                "invalid_argument",
                f"{node.kind} model must store constructor values by name",
            )
        )
    if not accepts_extra:
        for name in sorted(set(node.arguments) - declared):
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "invalid_argument",
                    f"{node.kind} has no argument {name!r}",
                )
            )
    for name, parameter in signature.parameters.items():
        if (
            name == "uid"
            or name in child_fields
            or parameter.kind
            in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
            or parameter.default is not inspect.Parameter.empty
        ):
            continue
        if name not in node.arguments:
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "invalid_argument",
                    f"{node.kind} requires argument {name!r}",
                )
            )
    for name in sorted(set(node.arguments) & declared):
        if not _annotation_accepts(node.arguments[name], type_hints.get(name, Any)):
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "invalid_argument",
                    f"{node.kind}.{name} does not match its DSL type annotation",
                )
            )
    for name in _CONTEXT_REQUIRED_ARGUMENTS.get((unit.kind, node.kind), ()):
        if name not in node.arguments or node.arguments[name] is None:
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "invalid_argument",
                    f"{node.kind} in {unit.kind} requires argument {name!r}",
                )
            )
    if not diagnostics:
        try:
            canonical = _canonical_node(node)
        except (TypeError, ProgramError) as exc:
            diagnostics.append(
                _node_diag(
                    unit,
                    node,
                    "invalid_argument",
                    f"invalid {node.kind} arguments: {exc}",
                )
            )
        else:
            if canonical.semantic_data() != node.semantic_data():
                diagnostics.append(
                    _node_diag(
                        unit,
                        node,
                        "noncanonical_argument",
                        f"{node.kind} contains explicit default arguments",
                    )
                )
    return diagnostics


def _canonical_node(node: Node) -> Node:
    from . import dsl

    constructor = dsl.NODE_CONSTRUCTORS[node.kind]
    values = copy.deepcopy(node.arguments)
    if node.kind == "Parallel":
        values["branches"] = [
            copy.deepcopy(branch.children.get("body", []))
            for branch in node.children.get("branches", [])
        ]
    else:
        for slot, children in node.children.items():
            values[slot] = copy.deepcopy(children)
    values["uid"] = node.uid
    return constructor(**values)


def _validate_nested_refs(
    unit: LogicalUnit,
    node: Node | None,
    name: str,
    value: Any,
    unit_index: Mapping[str, LogicalUnit],
) -> list[Diagnostic]:
    if isinstance(value, Ref):
        return _validate_ref(unit, node, name, value, unit_index, None)
    diagnostics: list[Diagnostic] = []
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            diagnostics.extend(_validate_nested_refs(unit, node, f"{name}[{index}]", item, unit_index))
    elif isinstance(value, Mapping):
        for key, item in value.items():
            diagnostics.extend(_validate_nested_refs(unit, node, f"{name}.{key}", item, unit_index))
    return diagnostics


def _validate_ref(
    unit: LogicalUnit,
    node: Node | None,
    name: str,
    value: Any,
    unit_index: Mapping[str, LogicalUnit],
    expected: Iterable[str] | None,
) -> list[Diagnostic]:
    if not isinstance(value, Ref):
        return [
            _node_diag(unit, node, "invalid_reference", f"{name} must be a Ref")
            if node is not None
            else _unit_diag(unit, "invalid_reference", f"{name} must be a Ref")
        ]
    target = unit_index.get(value.id)
    if target is None:
        message = f"unresolved reference {value.id!r}"
        return [
            _node_diag(unit, node, "unresolved_reference", message)
            if node is not None
            else _unit_diag(unit, "unresolved_reference", message)
        ]
    expected_set = set(expected or ())
    if expected_set and target.kind not in expected_set:
        message = f"reference {value.id!r} targets {target.kind}, expected {', '.join(sorted(expected_set))}"
        return [
            _node_diag(unit, node, "reference_type", message)
            if node is not None
            else _unit_diag(unit, "reference_type", message)
        ]
    return []


def _unit_diag(unit: LogicalUnit, code: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        message=message,
        source_path=_source_path(unit),
        span=unit.source_span,
        unit_id=unit.id,
    )


def _node_diag(unit: LogicalUnit, node: Node, code: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        message=message,
        source_path=_source_path(unit),
        span=node.source_span,
        unit_id=unit.id,
        uid=node.uid,
    )


def _collect_locations(
    unit: LogicalUnit,
    values: list[Node],
    parent_uid: str | None,
    slot: str,
    uid: str,
    matches: list[tuple[LogicalUnit, Node, NodeLocation]],
) -> None:
    for index, node in enumerate(values):
        if node.uid == uid:
            matches.append((unit, node, NodeLocation(unit.id, parent_uid, slot, index)))
        for child_slot, children in node.children.items():
            _collect_locations(unit, children, node.uid, child_slot, uid, matches)


def _child_list(unit: LogicalUnit, parent_uid: str | None, slot: str) -> list[Node]:
    if parent_uid is None:
        if slot != "body":
            raise ProgramError("invalid_child_slot", "logical unit root slot is 'body'")
        return unit.body
    _found_unit, parent, _location = find_node(AuthoringProgram({unit.id: unit}), parent_uid)
    allowed = _CHILD_SLOTS.get(parent.kind, ())
    if slot not in allowed:
        raise ProgramError("invalid_child_slot", f"{parent.kind} does not accept {slot!r}")
    return parent.children.setdefault(slot, [])


def _default_child_slot(node: Node) -> str:
    slots = _CHILD_SLOTS.get(node.kind, ())
    if "body" in slots:
        return "body"
    if len(slots) == 1:
        return slots[0]
    raise ProgramError("invalid_child", f"{node.kind} has no unambiguous child slot")


__all__ = [
    "ACTION_NODE_KINDS",
    "AuthoringProgram",
    "CONTROL_NODE_KINDS",
    "Diagnostic",
    "DropCheck",
    "DropPlacement",
    "Expr",
    "LogicalUnit",
    "NODE_KINDS",
    "Node",
    "NodeComments",
    "NodeLocation",
    "Parameter",
    "ProgramError",
    "ProgramValidationError",
    "Ref",
    "RelatedLocation",
    "SourceSpan",
    "TemplateTarget",
    "UNIT_KINDS",
    "create_unit",
    "delete_node",
    "duplicate_node",
    "delete_unit",
    "duplicate_unit",
    "find_node",
    "insert_new_node",
    "insert_node",
    "make_template_call",
    "move_node",
    "node_from_palette",
    "parse_author_value",
    "reference_kinds_for_node",
    "reference_kinds_for_field",
    "new_uid",
    "set_argument",
    "set_template_positional_argument",
    "set_unit_field",
    "unit_reference_locations",
    "validate_author_value",
    "validate_insert",
    "wrap_node",
]

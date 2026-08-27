"""Explicit trusted template calls and in-memory expansion.

Loading authoring files never imports their dependencies.  This module only
executes a template when a caller (the future package builder) explicitly asks
for trusted expansion.  Calls remain ordinary :class:`Node` values in the
source model and are never replaced in the authoring document.
"""

from __future__ import annotations

import copy
import functools
import importlib
import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_type_hints

from .program import (
    AuthoringProgram,
    Expr,
    LogicalUnit,
    Node,
    ProgramError,
    RelatedLocation,
    SourceSpan,
    TemplateTarget,
    _annotation_accepts,
    make_template_call,
)


@dataclass(frozen=True)
class ImportSpec:
    module: str
    name: str | None = None
    alias: str | None = None

    @property
    def local_name(self) -> str:
        if self.alias:
            return self.alias
        if self.name:
            return self.name
        return self.module.split(".", 1)[0]

    @property
    def identity(self) -> str:
        return f"{self.module}.{self.name}" if self.name else self.module


@dataclass(frozen=True)
class TemplateSourceDefinition:
    identity: str
    symbol: str
    parameters: tuple[str, ...]
    source: str
    source_path: str
    span: SourceSpan | None = None
    signature: inspect.Signature | None = None


@dataclass(frozen=True)
class TemplateDefinition:
    identity: str
    symbol: str
    signature: inspect.Signature
    function: Callable[..., Any]
    source_path: str = ""
    span: SourceSpan | None = None


class TemplateError(ProgramError):
    pass


class TemplateResolutionError(TemplateError):
    def __init__(self, identity: str, message: str):
        self.identity = identity
        super().__init__("template_missing", f"{identity}: {message}")


class TemplateExpansionError(TemplateError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        call_uid: str,
        identity: str,
        definition_path: str = "",
        definition_span: SourceSpan | None = None,
    ):
        self.call_uid = call_uid
        self.identity = identity
        self.related = (
            (RelatedLocation(definition_path, definition_span, "template definition"),)
            if definition_path
            else ()
        )
        super().__init__(code, message)


def _callable_identity(function: Callable[..., Any]) -> str:
    return f"{function.__module__}.{function.__qualname__}"


def _definition_location(function: Callable[..., Any]) -> tuple[str, SourceSpan | None]:
    path = inspect.getsourcefile(function) or ""
    try:
        lines, start = inspect.getsourcelines(function)
    except (OSError, TypeError):
        return path, None
    end = start + max(0, len(lines) - 1)
    return path, SourceSpan(start, 0, end, len(lines[-1].rstrip("\r\n")) if lines else 0)


def template(function: Callable[..., Any]) -> Callable[..., Node]:
    """Mark a trusted Python function as a retained template call.

    Calling the decorated symbol creates a ``TemplateCall`` node.  Expansion
    invokes the undecorated implementation kept in ``__pystg_template_impl__``.
    A reserved ``uid=`` keyword belongs to the call node and is never passed to
    the user's function.
    """

    if not callable(function):
        raise TypeError("@template requires a callable")
    identity = _callable_identity(function)
    source_path, span = _definition_location(function)

    @functools.wraps(function)
    def make_call(*args: Any, **kwargs: Any) -> Node:
        uid = kwargs.pop("uid", None)
        target = TemplateTarget(
            identity=identity,
            symbol=function.__name__,
            display_name=function.__name__,
            module=function.__module__,
            resolved=True,
            definition_path=source_path or None,
            definition_span=span,
        )
        return make_template_call(target, args, kwargs, uid=uid)

    make_call.__pystg_template__ = True  # type: ignore[attr-defined]
    make_call.__pystg_template_impl__ = function  # type: ignore[attr-defined]
    make_call.__pystg_template_identity__ = identity  # type: ignore[attr-defined]
    make_call.__pystg_template_location__ = (source_path, span)  # type: ignore[attr-defined]
    return make_call


def is_template(value: Any) -> bool:
    return callable(value) and bool(getattr(value, "__pystg_template__", False))


def definition_from_callable(value: Callable[..., Any]) -> TemplateDefinition:
    if not is_template(value):
        raise TemplateResolutionError(repr(value), "callable is not decorated with @template")
    implementation = getattr(value, "__pystg_template_impl__")
    identity = str(getattr(value, "__pystg_template_identity__"))
    source_path, span = getattr(value, "__pystg_template_location__", ("", None))
    return TemplateDefinition(
        identity=identity,
        symbol=value.__name__,
        signature=inspect.signature(implementation),
        function=implementation,
        source_path=source_path,
        span=span,
    )


class TemplateRegistry:
    """Registry populated only from built-ins or explicit imports."""

    def __init__(self) -> None:
        self._definitions: dict[str, TemplateDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, value: Callable[..., Any] | TemplateDefinition) -> TemplateDefinition:
        definition = value if isinstance(value, TemplateDefinition) else definition_from_callable(value)
        existing = self._definitions.get(definition.identity)
        if existing is not None and existing.function is not definition.function:
            raise TemplateError("duplicate_template", f"duplicate template {definition.identity!r}")
        self._definitions[definition.identity] = definition
        self._aliases[definition.identity] = definition.identity
        self._aliases[definition.symbol] = definition.identity
        module_symbol = f"{definition.function.__module__}.{definition.symbol}"
        self._aliases[module_symbol] = definition.identity
        return definition

    def register_alias(self, alias: str, identity: str) -> None:
        if identity not in self._definitions:
            raise TemplateResolutionError(identity, "cannot alias an unregistered template")
        self._aliases[alias] = identity

    @classmethod
    def with_builtins(cls) -> "TemplateRegistry":
        from .dsl import BUILTIN_TEMPLATES

        registry = cls()
        for value in BUILTIN_TEMPLATES:
            registry.register(value)
        return registry

    def register_module_templates(self, module: Any) -> tuple[TemplateDefinition, ...]:
        definitions = []
        for name in sorted(vars(module)):
            value = getattr(module, name)
            if is_template(value) and getattr(value, "__module__", None) == module.__name__:
                definitions.append(self.register(value))
        return tuple(definitions)

    def load_module_templates(self, module_name: str) -> tuple[TemplateDefinition, ...]:
        """Execute one explicitly selected trusted project/external module."""

        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise TemplateResolutionError(module_name, str(exc)) from exc
        return self.register_module_templates(module)

    def resolve(self, identity: str) -> TemplateDefinition:
        canonical = self._aliases.get(identity, identity)
        try:
            return self._definitions[canonical]
        except KeyError as exc:
            raise TemplateResolutionError(identity, "template is not registered") from exc

    def load_explicit_imports(self, imports: Iterable[ImportSpec]) -> tuple[TemplateResolutionError, ...]:
        """Import only symbols explicitly named by source imports.

        Module-only imports are recorded as authorization for attribute calls;
        concrete attributes are loaded lazily by ``resolve_explicit_target``.
        """

        errors: list[TemplateResolutionError] = []
        for spec in imports:
            if spec.name is None or spec.module == "src.authoring.dsl":
                continue
            try:
                module = importlib.import_module(spec.module)
                value = getattr(module, spec.name)
                if not is_template(value):
                    continue
                definition = self.register(value)
                self.register_alias(spec.local_name, definition.identity)
                self.register_alias(spec.identity, definition.identity)
            except Exception as exc:
                errors.append(TemplateResolutionError(spec.identity, str(exc)))
        return tuple(errors)

    def resolve_explicit_target(
        self,
        target: TemplateTarget,
        imports: Iterable[ImportSpec],
    ) -> TemplateDefinition:
        try:
            return self.resolve(target.identity)
        except TemplateResolutionError:
            pass
        allowed_modules = {item.module for item in imports}
        module_name = target.module
        if not module_name or not any(
            module_name == allowed or module_name.startswith(f"{allowed}.")
            for allowed in allowed_modules
        ):
            raise TemplateResolutionError(target.identity, "template was not explicitly imported")
        try:
            module = importlib.import_module(module_name)
            value: Any = module
            for part in target.symbol.split("."):
                value = getattr(value, part)
            definition = self.register(value)
            self.register_alias(target.identity, definition.identity)
            return definition
        except Exception as exc:
            raise TemplateResolutionError(target.identity, str(exc)) from exc


def expand_nodes(
    nodes: Sequence[Node],
    registry: TemplateRegistry,
) -> list[Node]:
    """Return a build-only deep expansion without modifying source calls."""

    return _expand_nodes(nodes, registry, (), None)


def _expand_nodes(
    nodes: Sequence[Node],
    registry: TemplateRegistry,
    stack: tuple[str, ...],
    source_call_uid: str | None,
) -> list[Node]:
    result: list[Node] = []
    for node in nodes:
        if node.kind == "TemplateCall":
            result.extend(_expand_call(node, registry, stack, source_call_uid))
            continue
        clone = copy.deepcopy(node)
        clone.children = {
            slot: _expand_nodes(children, registry, stack, source_call_uid)
            for slot, children in clone.children.items()
        }
        result.append(clone)
    return result


def _expand_call(
    call: Node,
    registry: TemplateRegistry,
    stack: tuple[str, ...],
    source_call_uid: str | None,
) -> list[Node]:
    author_call_uid = source_call_uid or call.uid
    if call.template is None:
        raise TemplateExpansionError(
            "template_missing",
            "template call has no target",
            call_uid=author_call_uid,
            identity="",
        )
    target = call.template
    try:
        definition = registry.resolve(target.identity)
    except TemplateResolutionError as exc:
        raise TemplateExpansionError(
            "template_missing",
            exc.message,
            call_uid=author_call_uid,
            identity=target.identity,
            definition_path=target.definition_path or "",
            definition_span=target.definition_span,
        ) from exc
    if definition.identity in stack:
        chain = " -> ".join((*stack, definition.identity))
        raise TemplateExpansionError(
            "template_recursion",
            f"recursive template expansion: {chain}",
            call_uid=author_call_uid,
            identity=definition.identity,
            definition_path=definition.source_path,
            definition_span=definition.span,
        )
    try:
        bound = definition.signature.bind(
            *copy.deepcopy(call.positional_arguments),
            **copy.deepcopy(call.arguments),
        )
        bound.apply_defaults()
    except TypeError as exc:
        raise TemplateExpansionError(
            "template_signature",
            f"invalid arguments for {definition.identity}: {exc}",
            call_uid=author_call_uid,
            identity=definition.identity,
            definition_path=definition.source_path,
            definition_span=definition.span,
        ) from exc
    try:
        type_hints = get_type_hints(definition.function)
    except Exception as exc:
        raise TemplateExpansionError(
            "template_signature",
            f"cannot resolve annotations for {definition.identity}: {exc}",
            call_uid=author_call_uid,
            identity=definition.identity,
            definition_path=definition.source_path,
            definition_span=definition.span,
        ) from exc
    for name, value in bound.arguments.items():
        annotation = type_hints.get(name, Any)
        parameter = definition.signature.parameters[name]
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            values = tuple(value)
        elif parameter.kind == inspect.Parameter.VAR_KEYWORD:
            values = tuple(value.values())
        else:
            values = (value,)
        if any(
            not isinstance(item, Expr) and not _annotation_accepts(item, annotation)
            for item in values
        ):
            raise TemplateExpansionError(
                "template_signature",
                f"argument {name!r} for {definition.identity} does not match its annotation",
                call_uid=author_call_uid,
                identity=definition.identity,
                definition_path=definition.source_path,
                definition_span=definition.span,
            )
    try:
        produced = definition.function(
            *copy.deepcopy(bound.args),
            **copy.deepcopy(bound.kwargs),
        )
    except Exception as exc:
        raise TemplateExpansionError(
            "template_exception",
            f"template {definition.identity} failed: {type(exc).__name__}: {exc}",
            call_uid=author_call_uid,
            identity=definition.identity,
            definition_path=definition.source_path,
            definition_span=definition.span,
        ) from exc
    if isinstance(produced, Node):
        produced_nodes = [produced]
    elif isinstance(produced, Sequence) and not isinstance(produced, (str, bytes)):
        produced_nodes = list(produced)
    else:
        raise TemplateExpansionError(
            "template_result",
            f"template {definition.identity} must return a Node or node sequence",
            call_uid=author_call_uid,
            identity=definition.identity,
            definition_path=definition.source_path,
            definition_span=definition.span,
        )
    if not all(isinstance(item, Node) for item in produced_nodes):
        raise TemplateExpansionError(
            "template_result",
            f"template {definition.identity} must return a Node or node sequence",
            call_uid=author_call_uid,
            identity=definition.identity,
            definition_path=definition.source_path,
            definition_span=definition.span,
        )
    derived = []
    for index, node in enumerate(produced_nodes):
        clone = _clone_node_tree(node)
        _derive_uids(clone, call.uid, (index,))
        derived.append(clone)
    validation_unit = LogicalUnit(
        kind="Task",
        id="__template_result__",
        name="Template result",
        body=copy.deepcopy(derived),
    )
    structural_errors = [
        diagnostic
        for diagnostic in AuthoringProgram.from_units([validation_unit]).validate()
        if diagnostic.code
        not in {
            "noncanonical_argument",
            "noncanonical_unit_field",
            "template_missing",
            "unresolved_reference",
        }
    ]
    if structural_errors:
        summary = "; ".join(item.message for item in structural_errors[:3])
        raise TemplateExpansionError(
            "template_result",
            f"template {definition.identity} returned invalid nodes: {summary}",
            call_uid=author_call_uid,
            identity=definition.identity,
            definition_path=definition.source_path,
            definition_span=definition.span,
        )
    return _expand_nodes(
        derived,
        registry,
        (*stack, definition.identity),
        author_call_uid,
    )


def _derive_uids(node: Node, call_uid: str, path: tuple[int, ...]) -> None:
    suffix = "_".join(str(item) for item in path)
    node.uid = f"{call_uid}__expanded_{suffix}_{node.kind.lower()}"
    child_index = 0
    for values in node.children.values():
        for child in values:
            _derive_uids(child, call_uid, (*path, child_index))
            child_index += 1


def _clone_node_tree(node: Node) -> Node:
    clone = copy.copy(node)
    clone.arguments = copy.deepcopy(node.arguments)
    clone.positional_arguments = copy.deepcopy(node.positional_arguments)
    clone.template = copy.deepcopy(node.template)
    clone.comments = copy.deepcopy(node.comments)
    clone.children = {
        slot: [_clone_node_tree(child) for child in children]
        for slot, children in node.children.items()
    }
    return clone


__all__ = [
    "ImportSpec",
    "TemplateDefinition",
    "TemplateError",
    "TemplateExpansionError",
    "TemplateRegistry",
    "TemplateResolutionError",
    "TemplateSourceDefinition",
    "definition_from_callable",
    "expand_nodes",
    "is_template",
    "template",
]

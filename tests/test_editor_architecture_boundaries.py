"""ER0 contracts for the editor's stable dependency and ownership boundaries.

These tests intentionally describe the post-ER target.  They use Python's AST
and runtime type metadata so a violation is tied to a module, symbol, and line
instead of to a brittle source-text fragment.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
EDITOR_ROOT = SRC_ROOT / "editor"

# These are the headless roles fixed by architecture principle 7 plus the
# concrete domain/runtime and horizontal-service packages that implement those
# roles today.  Developer-tool entrypoints are not part of that dependency
# chain.  Missing target packages simply contribute no files until their owning
# ER task creates real implementation modules.
HEADLESS_PACKAGE_ROOTS = (
    "authoring",
    "compiler",
    "content_api",
    "core",
    "game",
    "pattern",
    "preview",
    "render",
    "resource",
    "runtime",
    "ui",
)
QT_IMPORT_ROOTS = ("src.qt_compat", "PySide6", "PyQt5", "PyQt6", "qtpy")


@dataclass(frozen=True)
class ImportReference:
    module: str
    line: int


def _python_files(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    return tuple(sorted(root.rglob("*.py")))


def _module_name(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _import_references(
    tree: ast.AST, *, module: str, is_package: bool
) -> tuple[ImportReference, ...]:
    """Resolve imports, including modules named in ``from ... import ...``."""

    package = module.split(".") if is_package else module.split(".")[:-1]
    references: list[ImportReference] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            references.extend(
                ImportReference(alias.name, node.lineno) for alias in node.names
            )
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            keep = len(package) - (node.level - 1)
            anchor = package[: max(keep, 0)]
            resolved = ".".join((*anchor, *((node.module or "").split("."))))
        else:
            resolved = node.module or ""
        resolved = resolved.strip(".")
        if resolved:
            references.append(ImportReference(resolved, node.lineno))
        # The imported alias can itself be a module: both ``from src import
        # editor`` and ``from src.editor import graph_workspace`` must create a
        # qualified graph edge.  Symbol aliases are harmless because graph
        # consumers retain only references matching actual modules.
        for alias in node.names:
            if alias.name == "*":
                continue
            qualified = ".".join(part for part in (resolved, alias.name) if part)
            if qualified:
                references.append(ImportReference(qualified, node.lineno))
    return tuple(references)


def _imports(path: Path) -> tuple[ImportReference, ...]:
    """Resolve absolute and relative imports without importing product code."""

    return _import_references(
        _tree(path),
        module=_module_name(path),
        is_package=path.name == "__init__.py",
    )


def test_import_graph_records_alias_qualified_module_edges() -> None:
    tree = ast.parse(
        "from src import editor\n"
        "from src.editor import graph_workspace\n"
        "from . import pattern_workspace\n"
    )
    references = set(
        _import_references(tree, module="src.editor.synthetic", is_package=False)
    )
    assert ImportReference("src.editor", 1) in references
    assert ImportReference("src.editor.graph_workspace", 2) in references
    assert ImportReference("src.editor.pattern_workspace", 3) in references


def _starts_with(module: str, root: str) -> bool:
    return module == root or module.startswith(root + ".")


def _relative_location(path: Path, line: int) -> str:
    return f"{path.relative_to(REPO_ROOT).as_posix()}:{line}"


_PRESENT_HEADLESS_PACKAGES = tuple(
    name for name in HEADLESS_PACKAGE_ROOTS if (SRC_ROOT / name).is_dir()
)


@pytest.mark.parametrize("package_name", _PRESENT_HEADLESS_PACKAGES)
def test_headless_packages_do_not_import_editor_or_qt(package_name: str) -> None:
    forbidden_roots = ("src.editor", *QT_IMPORT_ROOTS)
    imported_by_location: dict[tuple[Path, int], set[str]] = {}
    for path in _python_files(SRC_ROOT / package_name):
        for reference in _imports(path):
            if any(_starts_with(reference.module, root) for root in forbidden_roots):
                imported_by_location.setdefault((path, reference.line), set()).add(
                    reference.module
                )

    violations: list[str] = []
    for (path, line), modules in imported_by_location.items():
        # ``from src.editor.document import SceneDocument`` produces both the
        # module and symbol-qualified reference.  Report the shortest boundary
        # edge at that location while retaining alias-only module imports.
        boundary_edges = {
            module
            for module in modules
            if not any(
                module != candidate and _starts_with(module, candidate)
                for candidate in modules
            )
        }
        violations.extend(
            f"{_relative_location(path, line)} -> {module}"
            for module in sorted(boundary_edges)
        )

    assert (
        not violations
    ), f"headless package src.{package_name} imports editor/Qt:\n" + "\n".join(
        sorted(set(violations))
    )


def _panel_paths() -> tuple[Path, ...]:
    current_layout = {
        path
        for path in _python_files(EDITOR_ROOT)
        if path.name.endswith("_workspace.py")
        or path.name.endswith("_panel.py")
        or path.name == "scene_view.py"
    }
    target_layout = set(_python_files(EDITOR_ROOT / "panels"))
    return tuple(sorted(current_layout | target_layout))


def _is_command_module(module: str) -> bool:
    # After ER7 the only domain Command modules live under
    # ``src.authoring.commands``.  The transitional ``src.editor.commands`` /
    # ``src.editor.*_commands`` re-export shims were deleted once every repo
    # caller moved to the canonical package, so the classifier recognises that
    # package alone -- no migration-era allowlist remains.
    return _starts_with(module, "src.authoring.commands")


@pytest.mark.parametrize(
    ("module", "expected"),
    (
        ("src.authoring.commands", True),
        ("src.authoring.commands.scene", True),
        ("src.authoring.commands.timeline.internal", True),
        ("src.authoring.command_helpers", False),
        ("src.game.commands", False),
        ("third_party.scene_commands", False),
    ),
)
def test_command_module_classifier_covers_only_domain_command_boundaries(
    module: str, expected: bool
) -> None:
    assert _is_command_module(module) is expected


def test_panels_do_not_import_domain_commands() -> None:
    violations = [
        f"{_relative_location(path, reference.line)} -> {reference.module}"
        for path in _panel_paths()
        for reference in _imports(path)
        if _is_command_module(reference.module)
    ]
    assert not violations, "panels import domain Command modules:\n" + "\n".join(
        sorted(set(violations))
    )


_EDITOR_DOMAIN_COMMAND_ADAPTERS = frozenset(
    {
        # The coordinator is the one application-layer adapter explicitly
        # responsible for translating typed intents into domain Commands.
        # Shell/window modules are deliberately not broadly exempted.
        "src.editor.application.coordinator",
    }
)


def _document_command_definitions(path: Path) -> tuple[str, ...]:
    """Find structural Command definitions without trusting module/class names."""

    violations: list[str] = []
    for node in _tree(path).body:
        if not isinstance(node, ast.ClassDef):
            continue
        methods = {
            item.name
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if not {"execute", "undo"}.issubset(methods):
            continue

        annotations = [
            item.annotation
            for item in node.body
            if isinstance(item, ast.AnnAssign)
        ]
        initializers = [
            item
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "__init__"
        ]
        annotations.extend(
            argument.annotation
            for initializer in initializers
            for argument in (
                *initializer.args.posonlyargs,
                *initializer.args.args,
                *initializer.args.kwonlyargs,
            )
            if argument.arg != "self"
        )
        if any(_annotation_mentions_document(annotation) for annotation in annotations):
            violations.append(
                f"{_relative_location(path, node.lineno)} defines {node.name}"
            )
    return tuple(violations)


def _imported_domain_command_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Return directly imported Command names and command-module aliases."""

    symbols: set[str] = set()
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and _is_command_module(node.module or ""):
            for alias in node.names:
                if alias.name == "Command" or alias.name.endswith("Command"):
                    symbols.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_command_module(alias.name):
                    modules.add(alias.asname or alias.name)
    return symbols, modules


def _domain_command_instantiations(path: Path) -> tuple[str, ...]:
    tree = _tree(path)
    symbols, modules = _imported_domain_command_names(tree)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = _expr_name(node.func)
        is_imported_symbol = called in symbols
        is_module_member = any(
            called.startswith(module + ".")
            and called.rsplit(".", 1)[-1].endswith("Command")
            for module in modules
        )
        if is_imported_symbol or is_module_member:
            violations.append(
                f"{_relative_location(path, node.lineno)} instantiates {called}"
            )
    return tuple(violations)


def test_editor_domain_commands_live_only_in_authoring_command_modules() -> None:
    """Editor filenames cannot hide domain Command implementations or callers."""

    violations: list[str] = []
    for path in _python_files(EDITOR_ROOT):
        module = _module_name(path)
        if module in _EDITOR_DOMAIN_COMMAND_ADAPTERS:
            continue
        violations.extend(_document_command_definitions(path))
        violations.extend(_domain_command_instantiations(path))

    assert not violations, (
        "domain Commands must be defined under src.authoring.commands and only "
        "instantiated by an explicit application adapter:\n"
        + "\n".join(sorted(set(violations)))
    )


def _annotation_mentions_document(annotation: ast.expr | None) -> bool:
    return annotation is not None and "Document" in ast.unparse(annotation)


def _document_access_depth(expression: ast.AST, aliases: set[str]) -> int | None:
    """Return accesses below a document root, or None for an unrelated value."""

    if isinstance(expression, ast.Name):
        return 0 if expression.id in aliases else None
    if isinstance(expression, ast.Attribute):
        if isinstance(expression.value, ast.Name) and expression.value.id == "self":
            return 0 if "document" in expression.attr.casefold() else None
        parent = _document_access_depth(expression.value, aliases)
        return None if parent is None else parent + 1
    if isinstance(expression, ast.Subscript):
        parent = _document_access_depth(expression.value, aliases)
        return None if parent is None else parent + 1
    return None


def _assigned_names(target: ast.AST) -> tuple[str, ...]:
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, (ast.Tuple, ast.List)):
        return tuple(name for item in target.elts for name in _assigned_names(item))
    return ()


def _direct_document_mutations(path: Path) -> tuple[str, ...]:
    mutating_methods = {
        "add",
        "append",
        "clear",
        "delete",
        "discard",
        "extend",
        "insert",
        "move",
        "pop",
        "remove",
        "replace",
        "setdefault",
        "sort",
        "update",
    }
    violations: list[str] = []
    for function in (
        node
        for node in ast.walk(_tree(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        arguments = (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
        aliases = {
            argument.arg
            for argument in arguments
            if argument.arg.casefold() in {"document", "doc"}
            or _annotation_mentions_document(argument.annotation)
        }
        # Follow local aliases such as ``body = document.body`` so mutating the
        # alias cannot hide a direct write from the contract.
        changed = True
        while changed:
            changed = False
            for node in ast.walk(function):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                value = node.value
                if value is None or _document_access_depth(value, aliases) is None:
                    continue
                targets = (
                    node.targets if isinstance(node, ast.Assign) else (node.target,)
                )
                for target in targets:
                    for name in _assigned_names(target):
                        if name not in aliases:
                            aliases.add(name)
                            changed = True

        for node in ast.walk(function):
            targets: tuple[ast.AST, ...] = ()
            if isinstance(node, ast.Assign):
                targets = tuple(node.targets)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets = (node.target,)
            elif isinstance(node, ast.Delete):
                targets = tuple(node.targets)
            for target in targets:
                depth = _document_access_depth(target, aliases)
                if depth is not None and depth >= 1:
                    violations.append(
                        f"{_relative_location(path, node.lineno)} writes {ast.unparse(target)}"
                    )

            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            owner_depth = _document_access_depth(node.func.value, aliases)
            method = node.func.attr.casefold()
            if owner_depth is not None and (
                method in mutating_methods
                or method.startswith(
                    ("add_", "delete_", "insert_", "move_", "remove_", "set_")
                )
            ):
                violations.append(
                    f"{_relative_location(path, node.lineno)} calls {ast.unparse(node.func)}()"
                )
    return tuple(sorted(set(violations)))


def test_panels_do_not_directly_mutate_authoring_documents() -> None:
    violations = [
        violation
        for path in _panel_paths()
        for violation in _direct_document_mutations(path)
    ]
    assert not violations, "panels directly mutate authoring documents:\n" + "\n".join(
        violations
    )


def _editor_import_graph() -> (
    tuple[dict[str, set[str]], dict[tuple[str, str], set[int]]]
):
    paths = {
        _module_name(path): path
        for path in _python_files(EDITOR_ROOT)
        if path.name != "__init__.py"
    }
    graph = {module: set() for module in paths}
    locations: dict[tuple[str, str], set[int]] = {}
    for module, path in paths.items():
        for reference in _imports(path):
            if reference.module not in graph:
                continue
            graph[module].add(reference.module)
            locations.setdefault((module, reference.module), set()).add(reference.line)
    return graph, locations


def _strongly_connected_components(
    graph: dict[str, set[str]]
) -> tuple[tuple[str, ...], ...]:
    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for neighbour in sorted(graph[node]):
            if neighbour not in indices:
                visit(neighbour)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbour])
            elif neighbour in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbour])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(tuple(sorted(component)))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return tuple(components)


def _is_graph_module(module: str) -> bool:
    parts = module.split(".")
    return "graphics" in parts or "graph" in parts[-1]


def test_editor_graph_modules_have_no_import_cycles() -> None:
    graph, locations = _editor_import_graph()
    cycles = [
        component
        for component in _strongly_connected_components(graph)
        if (len(component) > 1 or component[0] in graph[component[0]])
        and any(_is_graph_module(module) for module in component)
    ]
    diagnostics: list[str] = []
    for component in cycles:
        members = set(component)
        edges = [
            f"{source}:{line} -> {target}"
            for source in component
            for target in sorted(graph[source] & members)
            for line in sorted(locations[(source, target)])
        ]
        diagnostics.append("cycle {" + ", ".join(component) + "}: " + "; ".join(edges))
    assert not diagnostics, "editor graph import cycles:\n" + "\n".join(diagnostics)


def _expr_name(expression: ast.AST | None) -> str:
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        prefix = _expr_name(expression.value)
        return f"{prefix}.{expression.attr}" if prefix else expression.attr
    if isinstance(expression, ast.Subscript):
        return _expr_name(expression.value)
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
        return f"{_expr_name(expression.left)}|{_expr_name(expression.right)}"
    return ""


def _editor_classes() -> dict[str, tuple[Path, ast.ClassDef]]:
    result: dict[str, tuple[Path, ast.ClassDef]] = {}
    for path in _python_files(EDITOR_ROOT):
        for node in _tree(path).body:
            if isinstance(node, ast.ClassDef):
                result[node.name] = (path, node)
    return result


def _window_owner_classes() -> tuple[tuple[Path, ast.ClassDef], ...]:
    classes = _editor_classes()
    assert (
        "EditorMainWindow" in classes
    ), "src.editor has no EditorMainWindow assembly class"
    pending = ["EditorMainWindow"]
    visited: set[str] = set()
    owners: list[tuple[Path, ast.ClassDef]] = []
    while pending:
        name = pending.pop()
        if name in visited or name not in classes:
            continue
        visited.add(name)
        path, node = classes[name]
        owners.append((path, node))
        pending.extend(_expr_name(base).rsplit(".", 1)[-1] for base in node.bases)
    return tuple(owners)


def test_editor_main_window_does_not_inherit_slot_mixins() -> None:
    _path, window = _editor_classes()["EditorMainWindow"]
    mixins = [
        f"{_expr_name(base)} (line {base.lineno})"
        for base in window.bases
        if _expr_name(base).rsplit(".", 1)[-1].endswith("SlotsMixin")
    ]
    assert not mixins, "EditorMainWindow inherits domain slot mixins: " + ", ".join(
        mixins
    )


def _imported_aliases(path: Path, imported_name: str) -> set[str]:
    aliases = {imported_name}
    for node in _tree(path).body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == imported_name:
                    aliases.add(alias.asname or alias.name)
    return aliases


def _self_attribute(expression: ast.AST) -> str | None:
    if (
        isinstance(expression, ast.Attribute)
        and isinstance(expression.value, ast.Name)
        and expression.value.id == "self"
    ):
        return expression.attr
    return None


def _direct_preview_qprocess_attributes(
    node: ast.AST, qprocess_aliases: set[str]
) -> tuple[str, ...]:
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return ()
    value = node.value
    if not isinstance(value, ast.Call):
        return ()
    constructor = _expr_name(value.func).rsplit(".", 1)[-1]
    if constructor not in qprocess_aliases:
        return ()
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    return tuple(
        attribute
        for target in targets
        if (attribute := _self_attribute(target)) is not None
        and "preview" in attribute.casefold()
    )


def test_raw_qprocess_classifier_distinguishes_preview_from_tool_ownership() -> None:
    tree = ast.parse(
        "def construct(self):\n"
        "    self._preview_process = QProcess()\n"
        "    self._tool_process = QProcess()\n"
    )
    assignments = [
        node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    detected = {
        attribute
        for node in assignments
        for attribute in _direct_preview_qprocess_attributes(node, {"QProcess"})
    }
    assert detected == {"_preview_process"}


def test_editor_main_window_does_not_own_raw_preview_qprocess() -> None:
    violations: list[str] = []
    for path, owner in _window_owner_classes():
        qprocess_aliases = _imported_aliases(path, "QProcess")
        scoped_nodes: list[tuple[bool, ast.AST]] = [
            ("preview" in owner.name.casefold(), statement)
            for statement in owner.body
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        scoped_nodes.extend(
            (
                "preview" in owner.name.casefold()
                or "preview" in statement.name.casefold(),
                statement,
            )
            for statement in owner.body
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        for preview_scope, scope in scoped_nodes:
            for node in ast.walk(scope):
                for attribute in _direct_preview_qprocess_attributes(
                    node, qprocess_aliases
                ):
                    violations.append(
                        f"{_relative_location(path, node.lineno)} assigns QProcess() to self.{attribute}"
                    )
                if isinstance(node, ast.AnnAssign):
                    attribute = _self_attribute(node.target)
                    annotation_names = {
                        item.id
                        for item in ast.walk(node.annotation)
                        if isinstance(item, ast.Name)
                    }
                    if (
                        attribute is not None
                        and "preview" in attribute.casefold()
                        and annotation_names & qprocess_aliases
                    ):
                        violations.append(
                            f"{_relative_location(path, node.lineno)} annotates self.{attribute} as QProcess"
                        )
                if not isinstance(node, ast.Call):
                    continue
                constructor = _expr_name(node.func).rsplit(".", 1)[-1]
                if constructor in qprocess_aliases and preview_scope:
                    violations.append(
                        f"{_relative_location(path, node.lineno)} constructs QProcess in {owner.name}"
                    )
    assert (
        not violations
    ), "EditorMainWindow owns raw preview QProcess state:\n" + "\n".join(
        sorted(set(violations))
    )


def test_editor_main_window_has_one_plugin_registry_facade() -> None:
    registry_attributes: dict[str, list[str]] = {}
    for path, owner in _window_owner_classes():
        aliases = _imported_aliases(path, "PluginRegistry")
        for node in ast.walk(owner):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, ast.Call):
                continue
            constructor = _expr_name(value.func).rsplit(".", 1)[-1]
            if constructor not in aliases and not constructor.endswith(
                "PluginRegistry"
            ):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            for target in targets:
                attribute = _self_attribute(target)
                if attribute is not None:
                    registry_attributes.setdefault(attribute, []).append(
                        f"{_relative_location(path, node.lineno)} ({constructor})"
                    )
    assert len(registry_attributes) == 1, (
        "EditorMainWindow must see exactly one EditorPluginRegistry facade; found "
        + ", ".join(
            f"self.{name} at {'; '.join(locations)}"
            for name, locations in sorted(registry_attributes.items())
        )
    )


def test_editor_main_window_holds_no_plugin_sdk_registry_alias() -> None:
    """ER5 hard metric (docs/EDITOR_IMPLEMENTATION_TODO.md:535): the window must
    not hold *both* ``plugin_registry`` and a second ``plugin_sdk_registry``
    attribute.  The SDK surface is reached only through the single facade's
    ``.sdk`` accessor -- never mirrored onto the window as its own instance
    attribute, whatever the right-hand side: a ``PluginRegistry(...)`` Call *or*
    a plain attribute alias such as ``self.plugin_registry.sdk``.  The
    ``...has_one_plugin_registry_facade`` test above only inspects Call
    right-hand sides, so it cannot see the alias form; this companion pins it,
    matching the hard metric literally ("窗口不再同时持有 ...").
    """
    violations: list[str] = []
    for path, owner in _window_owner_classes():
        for node in ast.walk(owner):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            for target in targets:
                if _self_attribute(target) == "plugin_sdk_registry":
                    violations.append(_relative_location(path, node.lineno))
    assert not violations, (
        "EditorMainWindow must not hold a second self.plugin_sdk_registry "
        "attribute; the SDK is reached via self.plugin_registry.sdk. Found at: "
        + "; ".join(sorted(violations))
    )


def test_shell_services_do_not_proxy_or_inject_the_entire_window_surface() -> None:
    """Composition must expose explicit ports, not recreate Mixins dynamically."""

    service_path = EDITOR_ROOT / "shell" / "service.py"
    classes = {
        node.name: node
        for node in _tree(service_path).body
        if isinstance(node, ast.ClassDef)
    }
    service = classes.get("WindowService")
    assert service is not None, "the shell service boundary is missing"
    magic_proxies = {
        node.name
        for node in service.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"__getattr__", "__setattr__"}
    }

    dynamic_injection: list[str] = []
    for node in ast.walk(_tree(service_path)):
        if not isinstance(node, ast.Call):
            continue
        if _expr_name(node.func).rsplit(".", 1)[-1] != "setattr":
            continue
        if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "window":
            dynamic_injection.append(_relative_location(service_path, node.lineno))

    assert not magic_proxies and not dynamic_injection, (
        "WindowService recreates a SlotsMixin/God-object boundary by proxying "
        "or injecting the complete window surface: "
        f"magic={sorted(magic_proxies)}, injections={dynamic_injection}"
    )


def test_editor_app_is_a_thin_bootstrap_not_the_window_implementation() -> None:
    """Architecture section 3 fixes app.py to CLI/project/create_window only."""

    app_path = EDITOR_ROOT / "app.py"
    tree = _tree(app_path)
    concrete_windows = [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EditorMainWindow"
    ]
    allowed_functions = {"create_window", "main"}
    extra_functions = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name not in allowed_functions
    ]
    assert not concrete_windows and not extra_functions, (
        "src/editor/app.py must remain a thin bootstrap; move the concrete "
        f"window to shell/main_window.py (classes={concrete_windows}, "
        f"extra_functions={extra_functions})"
    )


def test_preview_runtime_state_has_one_owner() -> None:
    """Runtime identity/overlay state belongs to PreviewSession, never the window."""

    forbidden = {
        "_active_stage_session",
        "_preview_loaded_resource_id",
        "_preview_mode",
        "_preview_state",
        "_runtime_overlay",
        "_preview_pending_properties",
    }
    violations: list[str] = []
    for path, owner in _window_owner_classes():
        for node in ast.walk(owner):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            for target in targets:
                attribute = _self_attribute(target)
                if attribute in forbidden:
                    violations.append(
                        f"{_relative_location(path, node.lineno)} -> self.{attribute}"
                    )
    assert not violations, (
        "preview runtime state is duplicated on EditorMainWindow instead of "
        "being owned by PreviewSession:\n" + "\n".join(sorted(violations))
    )


def test_compiler_facade_is_the_preview_controller_dispatch_boundary() -> None:
    """The compiler facade must dispatch real documents and have a formal caller."""

    facade = importlib.import_module("src.compiler.facade")
    assert callable(getattr(facade, "compile_document", None)), (
        "src.compiler.facade is only a re-export placeholder; it needs a real "
        "compile_document dispatch entry"
    )

    controller_path = SRC_ROOT / "preview" / "controller.py"
    controller_tree = _tree(controller_path)
    candidates = [
        node
        for node in ast.walk(controller_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_compile_candidate"
    ]
    assert len(candidates) == 1
    calls = {
        _expr_name(node.func).rsplit(".", 1)[-1]
        for node in ast.walk(candidates[0])
        if isinstance(node, ast.Call)
    }
    assert "compile_document" in calls, (
        "PreviewController bypasses src.compiler.facade.compile_document and "
        "continues to dispatch compiler implementations itself"
    )


def _contains_any_or_untyped_mapping(annotation: Any) -> bool:
    if annotation is Any:
        return True
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is dict and (not arguments or Any in arguments):
        return True
    return any(_contains_any_or_untyped_mapping(argument) for argument in arguments)


def test_managed_document_temporary_state_is_one_typed_state_object() -> None:
    from src.editor.document_manager import ManagedDocument

    hints = get_type_hints(ManagedDocument)
    temporary_tokens = (
        "context",
        "overlay",
        "playhead",
        "selected",
        "selection",
        "state",
        "zoom",
    )
    temporary_fields = [
        field
        for field in fields(ManagedDocument)
        if any(token in field.name.casefold() for token in temporary_tokens)
    ]
    typed_state_fields = [
        field
        for field in temporary_fields
        if getattr(hints.get(field.name), "__name__", "") == "DocumentEditorState"
    ]
    assert len(typed_state_fields) == 1, (
        "ManagedDocument must own exactly one DocumentEditorState; temporary fields are "
        + ", ".join(
            f"{field.name}: {hints.get(field.name)!r}" for field in temporary_fields
        )
    )
    assert temporary_fields == typed_state_fields, (
        "temporary editor state remains split across ManagedDocument fields: "
        + ", ".join(field.name for field in temporary_fields)
    )
    state_type = hints[typed_state_fields[0].name]
    assert is_dataclass(state_type), "DocumentEditorState must be a typed dataclass"
    state_hints = get_type_hints(state_type)
    untyped = [
        f"{name}: {annotation!r}"
        for name, annotation in state_hints.items()
        if _contains_any_or_untyped_mapping(annotation)
    ]
    assert not untyped, "DocumentEditorState contains untyped fields: " + ", ".join(
        untyped
    )


def test_managed_document_uses_runtime_authoring_document_protocol() -> None:
    spec = importlib.util.find_spec("src.authoring.document_types")
    assert spec is not None, "src.authoring.document_types.AuthoringDocument is missing"
    module = importlib.import_module("src.authoring.document_types")
    protocol = getattr(module, "AuthoringDocument", None)
    assert inspect.isclass(protocol) and getattr(
        protocol, "_is_protocol", False
    ), "AuthoringDocument must be a typing.Protocol"
    assert getattr(
        protocol, "_is_runtime_protocol", False
    ), "AuthoringDocument must support runtime structural checks"

    class CompleteDocument:
        id = "contract-document"
        type = "pystg.contract"
        schema_version = 1

        def to_dict(self) -> dict[str, object]:
            return {}

        @classmethod
        def from_dict(cls, _value: object) -> "CompleteDocument":
            return cls()

        def validate(self) -> None:
            return None

    class MissingValidation:
        id = "incomplete-document"
        type = "pystg.contract"
        schema_version = 1

        def to_dict(self) -> dict[str, object]:
            return {}

        @classmethod
        def from_dict(cls, _value: object) -> "MissingValidation":
            return cls()

    assert isinstance(CompleteDocument(), protocol)
    assert not isinstance(MissingValidation(), protocol)

    from src.editor.document_manager import ManagedDocument

    document_hint = get_type_hints(ManagedDocument)["document"]
    assert document_hint is protocol, (
        "ManagedDocument.document must use AuthoringDocument, got " f"{document_hint!r}"
    )

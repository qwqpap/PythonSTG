"""ER6 contract: Qt panels form a flat leaf layer with no sibling coupling.

The architecture arrow is ``Panels -> EditorCoordinator -> authoring documents``.
A panel may depend *down* on shared primitives (``src.editor.graphics``), on the
coordinator's public Intent/Port surface, and on framework helpers -- but never
*sideways* on another panel's concrete implementation.  Reaching into a sibling
panel is exactly how private widgets, ad-hoc signals, and hidden mutation paths
leak across the boundary, so this gate forbids any panel->panel import edge in
either direction (a strictly stronger statement than "no import cycles", which
already lives in ``test_editor_architecture_boundaries``).

The check is AST-only: it never imports product code, and it resolves the module
named on both sides of ``from X import Y`` so a relative or function-local import
is caught the same as a top-level absolute one.  It complements -- and does not
duplicate -- the domain-command and direct-mutation gates in the ER0 suite.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = REPO_ROOT / "src" / "editor"


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
    """Resolve imports, including the module named in ``from ... import ...``.

    ``ast.walk`` descends into function bodies, so a lazy import buried inside a
    method (the pattern workspace builds its graph toolbar that way) is resolved
    to the same qualified module edge as a top-level import.
    """

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
        for alias in node.names:
            if alias.name == "*":
                continue
            qualified = ".".join(part for part in (resolved, alias.name) if part)
            if qualified:
                references.append(ImportReference(qualified, node.lineno))
    return tuple(references)


def _imports(path: Path) -> tuple[ImportReference, ...]:
    return _import_references(
        _tree(path),
        module=_module_name(path),
        is_package=path.name == "__init__.py",
    )


def _relative_location(path: Path, line: int) -> str:
    return f"{path.relative_to(REPO_ROOT).as_posix()}:{line}"


def _panel_paths() -> tuple[Path, ...]:
    """Panels under both the current flat layout and the target ``panels/`` home.

    Mirrors ``test_editor_architecture_boundaries._panel_paths`` so the two
    boundary suites classify panels identically while the ER6 migration is in
    flight and files live in both places.
    """

    current_layout = {
        path
        for path in _python_files(EDITOR_ROOT)
        if path.name.endswith("_workspace.py")
        or path.name.endswith("_panel.py")
        or path.name == "scene_view.py"
    }
    target_layout = set(_python_files(EDITOR_ROOT / "panels"))
    return tuple(sorted(current_layout | target_layout))


def _panel_modules() -> frozenset[str]:
    return frozenset(_module_name(path) for path in _panel_paths())


def test_panel_classifier_finds_the_known_panels() -> None:
    """Guard the classifier itself: it must see real panels, not an empty set."""

    modules = _panel_modules()
    assert "src.editor.pattern_workspace" in modules
    assert "src.editor.inspector_panel" in modules
    assert "src.editor.scene_view" in modules


def test_panels_do_not_import_sibling_panels() -> None:
    """No panel may import another panel's module (either direction).

    Shared widgets belong in ``src.editor.graphics`` (a non-panel leaf layer);
    cross-panel behaviour belongs behind an Intent dispatched to the coordinator.
    A concrete sibling import is the failure this gate makes impossible.
    """

    panel_modules = _panel_modules()
    violations: list[str] = []
    for path in _panel_paths():
        origin = _module_name(path)
        for reference in _imports(path):
            if reference.module == origin:
                continue
            if reference.module in panel_modules:
                violations.append(
                    f"{_relative_location(path, reference.line)} -> {reference.module}"
                )
    assert not violations, "panels import sibling panels:\n" + "\n".join(
        sorted(set(violations))
    )

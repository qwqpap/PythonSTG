"""ER6 contract: Qt panels form a flat leaf layer with no sibling coupling.

The architecture arrow is ``Panels -> EditorCoordinator -> authoring documents``.
A panel may depend *down* on shared primitives (``src.editor.graphics``), on the
coordinator's public Intent/Port surface, and on framework helpers -- but never
*sideways* on another panel's concrete implementation.  Reaching into a sibling
panel is exactly how private widgets, ad-hoc signals, and hidden mutation paths
leak across the boundary, so this gate forbids any panel->panel import edge in
either direction (a strictly stronger statement than "no import cycles", which
already lives in ``test_editor_architecture_boundaries``).

This file carries two complementary ER6 gates:

* a **structural** gate (AST-only): it never imports product code, and it
  resolves the module named on both sides of ``from X import Y`` so a relative
  or function-local import is caught the same as a top-level absolute one --
  forbidding any panel->panel edge; and
* a **behavioural** gate: it drives a genuine press/move/release gesture on the
  timeline canvas inside the assembled window and asserts, against the single
  ``EditorCoordinator.dispatch`` chokepoint, that dragging commits *no* Intent
  and releasing commits *exactly one* undoable ``TimelineIntent`` -- the ER6
  §577 #2/#3 metrics ("panels never mutate the document or push a Command
  directly"; "releasing the mouse commits exactly one Intent; graph wiring,
  node drag, timeline move/trim and UI gizmos are all Undo/Redo-reversible").
  The structural helpers stay import-light: this gate's Qt and product imports
  are function-local, so the AST tests still run in a Qt-free environment.

Both gates complement -- and do not duplicate -- the domain-command and
direct-mutation gates in the ER0 suite.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest


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
    # Scene/Inspector moved into panels/ in ER6.1; Timeline/StateGraph/Variables
    # in ER6.2; Pattern in ER6.3.  All known panels now live under panels/.
    assert "src.editor.panels.pattern_workspace" in modules
    assert "src.editor.panels.scene_view" in modules
    assert "src.editor.panels.inspector_panel" in modules


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


def test_timeline_clip_drag_commits_exactly_one_undoable_intent_on_release(
    tmp_path, qapp_session
) -> None:
    """ER6 §577 #2/#3 runtime gate: a real drag mutates only via the coordinator.

    Metric #2 ("a panel never mutates the document or pushes a Command
    directly") and #3 ("releasing the mouse commits exactly one Intent; the move
    is Undo/Redo-reversible") are behavioural, not structural, so no AST check
    can establish them.  This gate drives a genuine press/move/release gesture on
    the timeline canvas inside the assembled window and asserts against the sole
    coordinator chokepoint (``EditorCoordinator.dispatch``):

    * moving the mouse mid-gesture commits *no* Intent -- the panel holds a
      transient pose and never touches the document while the drag is live;
    * releasing commits *exactly one* ``TimelineIntent(MOVE_CLIP)`` through the
      coordinator -- the single mutation path a panel is allowed; and
    * the resulting move is reversible with Undo and re-appliable with Redo.

    The clip is selected first with a zero-delta click.  A click never moves the
    clip, so ``TimelineClipItem.mouseReleaseEvent`` (which only emits a geometry
    commit when ``start != self.start_frame``) produces no Intent; and because
    the drag's own press then finds the selection unchanged, the guarded
    ``_timeline_clip_selected`` slot does not dispatch a SELECT_CLIP and does not
    rebuild the scene under the live mouse grab.
    """

    from src.core.project_context import ProjectContext
    from src.editor import TimelineClip, TimelineTrack
    from src.editor.app import EditorMainWindow
    from src.editor.application import TimelineAction, TimelineIntent
    from src.editor.panels.timeline_workspace import CLIP_HEIGHT, TimelineClipItem
    from src.qt_compat.QtCore import QPoint, QPointF, Qt
    from src.qt_compat.QtGui import QMouseEvent
    from src.qt_compat.QtTest import QTest
    from src.qt_compat.QtWidgets import QApplication

    window = EditorMainWindow(ProjectContext(tmp_path))
    window.resize(900, 360)
    window.show()
    qapp_session.processEvents()

    track = TimelineTrack(
        name="Body",
        kind="Pattern",
        channel="main",
        clips=[
            TimelineClip(
                name="Ring",
                kind="Pattern",
                start_frame=60,
                duration_frames=120,
                channel="main",
                payload={"pattern": "ring"},
            )
        ],
    )
    window.session.document.tracks = [track]
    window._refresh()
    window.timeline.set_zoom(1.0)
    qapp_session.processEvents()
    clip_id = track.clips[0].id
    view = window.timeline.view

    def current_center():
        # Re-fetch the item every time: selecting a clip rebuilds the scene, so a
        # position cached before the first gesture would target a stale item.
        item = next(
            value
            for value in view.graphics_scene.items()
            if isinstance(value, TimelineClipItem) and value.clip_id == clip_id
        )
        return view.mapFromScene(item.scenePos() + QPointF(40, CLIP_HEIGHT / 2))

    # Select first with a zero-delta click so the drag's press leaves the
    # selection unchanged (no SELECT_CLIP dispatch, no mid-gesture rebuild).
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=current_center())
    qapp_session.processEvents()

    dispatched: list = []
    real_dispatch = window.editor_coordinator.dispatch

    def counting_dispatch(intent):
        dispatched.append(intent)
        return real_dispatch(intent)

    window.editor_coordinator.dispatch = counting_dispatch
    try:
        center = current_center()
        moved = center + QPoint(30, 0)

        QTest.mousePress(view.viewport(), Qt.LeftButton, pos=center)
        qapp_session.processEvents()
        assert dispatched == [], "pressing an already-selected clip dispatched an intent"

        QApplication.sendEvent(
            view.viewport(),
            QMouseEvent(
                QMouseEvent.MouseMove,
                moved,
                view.viewport().mapToGlobal(moved),
                Qt.NoButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )
        qapp_session.processEvents()
        assert dispatched == [], "dragging committed an intent before the mouse was released"

        QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=moved)
        qapp_session.processEvents()
    finally:
        window.editor_coordinator.dispatch = real_dispatch

    assert len(dispatched) == 1, (
        f"releasing the mouse must commit exactly one Intent, got {dispatched!r}"
    )
    intent = dispatched[0]
    assert isinstance(intent, TimelineIntent)
    assert intent.action == TimelineAction.MOVE_CLIP

    assert window.session.document.tracks[0].clips[0].start_frame == 90
    assert window.session.undo()
    assert window.session.document.tracks[0].clips[0].start_frame == 60
    assert window.session.redo()
    assert window.session.document.tracks[0].clips[0].start_frame == 90

    window.session.revert()
    window.close()
    qapp_session.processEvents()


@pytest.mark.parametrize("gesture", ("move", "resize"))
def test_ui_gizmo_commits_one_undoable_intent_only_on_release(
    gesture: str, tmp_path, qapp_session
) -> None:
    """A real UI gizmo gesture is preview-only until one release commit.

    This is the UI counterpart to the timeline drag gate above.  It exercises
    the assembled ``EditorMainWindow`` rather than a standalone canvas, spies on
    the real coordinator chokepoint, and drives the viewport using genuine Qt
    press/move/release events.  Moving an item and resizing it from its south-east
    handle must both obey the same contract:

    * press/move may alter only transient graphics geometry;
    * the authoring document and mutation-Intent stream stay unchanged until
      release;
    * release dispatches exactly one ``SET_NODE_PROPERTIES`` geometry Intent;
      and
    * that one command is independently Undo/Redo reversible.

    Preselecting the graphics item with the scene signal blocked is test setup,
    equivalent to beginning a gesture on an already-selected item.  It prevents
    a selection-only invalidation from rebuilding the canvas under the mouse;
    the geometry operation itself is still performed exclusively through QTest
    and a real ``QMouseEvent`` -- no final slot, signal, ``setPos()``, or item
    event handler is called directly.
    """

    from src.authoring import ResourceStore
    from src.core.project_context import ProjectContext
    from src.editor.app import EditorMainWindow
    from src.editor.application import UIDocumentAction, UIDocumentIntent
    from src.qt_compat.QtCore import QPoint, QSignalBlocker, Qt
    from src.qt_compat.QtGui import QMouseEvent
    from src.qt_compat.QtTest import QTest
    from src.qt_compat.QtWidgets import QApplication
    from src.ui.document import UIDocument, UIDocumentNode

    project = ProjectContext(tmp_path)
    document = UIDocument.new("ER6 UI gizmo")
    root = UIDocumentNode(
        node_type="panel",
        name="root",
        width=384.0,
        height=448.0,
    )
    child = UIDocumentNode(
        node_type="text",
        name="status",
        x=24.0,
        y=32.0,
        width=120.0,
        height=36.0,
        text="Ready",
    )
    root.add_child(child)
    document.root = root
    document.validate()
    path = ResourceStore(project).save(
        document, "game_content/ui/er6-gizmo.pystg.json"
    )

    window = EditorMainWindow(project)
    window.resize(1100, 800)
    window.show()
    window.document_service.open_document(path)
    qapp_session.processEvents()

    workspace = window.central_tabs.currentWidget()
    canvas = workspace.canvas
    loaded = next(
        node
        for node, _depth in window.session.document.root.walk()
        if node.name == "status"
    )
    item = canvas.item_for_node(loaded.id)
    assert item is not None

    # Keep the real gesture focused on geometry.  Selection is transient state,
    # not the authoring mutation this contract is measuring.
    with QSignalBlocker(canvas.graphics_scene):
        item.setSelected(True)
    item.setZValue(100.0)
    qapp_session.processEvents()

    def geometry() -> tuple[float, float, float, float]:
        return (
            float(loaded.x),
            float(loaded.y),
            float(loaded.width),
            float(loaded.height),
        )

    before_payload = window.session.document.to_dict()
    before_geometry = geometry()
    dispatched: list = []
    real_dispatch = window.editor_coordinator.dispatch

    def counting_dispatch(intent):
        dispatched.append(intent)
        return real_dispatch(intent)

    def geometry_intents() -> list[UIDocumentIntent]:
        return [
            intent
            for intent in dispatched
            if isinstance(intent, UIDocumentIntent)
            and intent.action is UIDocumentAction.SET_NODE_PROPERTIES
            and {"x", "y", "width", "height"}.issubset(intent.values)
        ]

    if gesture == "move":
        scene_start = item.mapToScene(item.rect().center())
        delta = QPoint(72, 36)
    else:
        scene_start = item.mapToScene(item.rect().bottomRight())
        delta = QPoint(48, 30)
    start = canvas.mapFromScene(scene_start)
    middle = start + QPoint(delta.x() // 2, delta.y() // 2)
    end = start + delta

    window.editor_coordinator.dispatch = counting_dispatch
    pressed = False
    try:
        QTest.mousePress(canvas.viewport(), Qt.LeftButton, pos=start)
        pressed = True
        qapp_session.processEvents()
        QApplication.sendEvent(
            canvas.viewport(),
            QMouseEvent(
                QMouseEvent.MouseMove,
                middle,
                canvas.viewport().mapToGlobal(middle),
                Qt.NoButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )
        QApplication.sendEvent(
            canvas.viewport(),
            QMouseEvent(
                QMouseEvent.MouseMove,
                end,
                canvas.viewport().mapToGlobal(end),
                Qt.NoButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )
        qapp_session.processEvents()
        payload_before_release = window.session.document.to_dict()
        geometry_intents_before_release = tuple(geometry_intents())

        QTest.mouseRelease(canvas.viewport(), Qt.LeftButton, pos=end)
        pressed = False
        qapp_session.processEvents()
    finally:
        if pressed:
            QTest.mouseRelease(canvas.viewport(), Qt.LeftButton, pos=end)
            qapp_session.processEvents()
        window.editor_coordinator.dispatch = real_dispatch

    assert payload_before_release == before_payload, (
        f"UI {gesture} mutated the authoring document before mouse release"
    )
    assert geometry_intents_before_release == (), (
        f"UI {gesture} dispatched geometry mutation before release: "
        f"{geometry_intents_before_release!r}"
    )

    committed = geometry_intents()
    assert len(committed) == 1, (
        f"UI {gesture} release must dispatch exactly one geometry Intent, "
        f"got {committed!r}"
    )
    assert committed[0].target_id == loaded.id
    after_geometry = geometry()
    if gesture == "move":
        assert after_geometry[:2] != before_geometry[:2]
        assert after_geometry[2:] == pytest.approx(before_geometry[2:])
    else:
        assert after_geometry[:2] == pytest.approx(before_geometry[:2])
        assert after_geometry[2:] != before_geometry[2:]

    assert window.session.undo()
    assert geometry() == pytest.approx(before_geometry)
    assert not window.session.undo(), "one UI gesture created more than one Command"
    assert window.session.redo()
    assert geometry() == pytest.approx(after_geometry)

    window.session.revert()
    window.close()
    qapp_session.processEvents()

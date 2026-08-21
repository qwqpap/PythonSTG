"""Run the ER6 native Qt editor gate on a real desktop session.

ER6 flattens the Qt panels into a leaf layer whose *only* mutation path is an
Intent dispatched to :class:`EditorCoordinator`.  Two of the acceptance metrics
(EDITOR_IMPLEMENTATION_TODO.md §577 #2/#3) are behavioural and can only be shown
by a genuine pointer gesture:

* #2 -- a panel never mutates the authoring document or pushes a Command
  directly; while a clip is being dragged the panel holds a *transient* pose and
  the document is untouched, so no Intent reaches the coordinator; and
* #3 -- releasing the mouse commits *exactly one* ``TimelineIntent(MOVE_CLIP)``
  through the coordinator, and that move is Undo/Redo-reversible.

This gate drives a real press/move/release on the timeline canvas of the
assembled window and asserts against the single ``EditorCoordinator.dispatch``
chokepoint -- it counts the Intents that cross it, it does not fabricate them.
The clip geometry is arranged as test setup (an author would instead drag it
into place); the *gesture under test* is real mouse input, delivered exactly the
way ``QTest`` delivers it to a live viewport.

The clip is selected first with a zero-delta click.  A click never moves the
clip, so ``TimelineClipItem.mouseReleaseEvent`` (which emits a geometry commit
only when ``start != self.start_frame``) yields no Intent; and because the
drag's own press then finds the selection unchanged, the guarded
``_timeline_clip_selected`` slot neither dispatches SELECT_CLIP nor rebuilds the
scene under the live mouse grab.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.project_context import ProjectContext
from src.editor import TimelineClip, TimelineTrack
from src.editor.app import EditorMainWindow
from src.editor.application import TimelineAction, TimelineIntent
from src.editor.panels.timeline_workspace import CLIP_HEIGHT, TimelineClipItem
from src.qt_compat.QtCore import QPoint, QPointF, Qt, QTimer
from src.qt_compat.QtGui import QMouseEvent
from src.qt_compat.QtTest import QTest
from src.qt_compat.QtWidgets import QApplication


def run(*, project_root: Path, screenshot: Path | None = None) -> None:
    app = QApplication.instance() or QApplication([])
    project = ProjectContext(project_root)
    window = EditorMainWindow(project)
    window.resize(1480, 920)
    window.show()
    app.processEvents()

    # Setup: a single Pattern clip at frame 60, 120 frames long, on a fresh
    # track.  Injecting the track is arrangement; the drag below is the gesture.
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
    if hasattr(window, "bottom_tabs"):
        window.bottom_tabs.setCurrentWidget(window.timeline)
    app.processEvents()
    clip_id = track.clips[0].id
    view = window.timeline.view

    def current_center() -> QPoint:
        # Re-fetch every time: selecting a clip rebuilds the scene, so a cached
        # position would target an item the live scene has already discarded.
        item = next(
            value
            for value in view.graphics_scene.items()
            if isinstance(value, TimelineClipItem) and value.clip_id == clip_id
        )
        return view.mapFromScene(item.scenePos() + QPointF(40, CLIP_HEIGHT / 2))

    # Select first with a zero-delta click (commits nothing) so the drag's press
    # leaves the selection unchanged and does not rebuild the scene mid-gesture.
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=current_center())
    app.processEvents()

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
        app.processEvents()
        if dispatched:
            raise AssertionError(
                f"pressing an already-selected clip dispatched an Intent: {dispatched!r}"
            )

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
        app.processEvents()
        if dispatched:
            raise AssertionError(
                f"dragging committed an Intent before release: {dispatched!r}"
            )

        QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=moved)
        app.processEvents()
    finally:
        window.editor_coordinator.dispatch = real_dispatch

    if len(dispatched) != 1:
        raise AssertionError(
            f"releasing the mouse must commit exactly one Intent, got {dispatched!r}"
        )
    intent = dispatched[0]
    if not isinstance(intent, TimelineIntent) or intent.action != TimelineAction.MOVE_CLIP:
        raise AssertionError(f"the sole release Intent was not a MOVE_CLIP: {intent!r}")

    moved_start = window.session.document.tracks[0].clips[0].start_frame
    if moved_start != 90:
        raise AssertionError(f"drag did not move the clip to frame 90 (got {moved_start})")
    if not window.session.undo() or window.session.document.tracks[0].clips[0].start_frame != 60:
        raise AssertionError("Undo did not restore the clip to its original frame")
    if not window.session.redo() or window.session.document.tracks[0].clips[0].start_frame != 90:
        raise AssertionError("Redo did not re-apply the clip move")

    if screenshot is not None and not window.grab().save(str(screenshot)):
        raise RuntimeError(f"could not save native screenshot: {screenshot}")

    print(
        "native_editor_er6_ok "
        f"clip={clip_id} action={intent.action.name} intents={len(dispatched)} "
        f"start=60->{moved_start} screenshot={str(screenshot) if screenshot else '(none)'}",
        flush=True,
    )

    # End this short-lived verification process from the timer after one real
    # event-loop turn, leaving the result above flushed.
    QTimer.singleShot(100, lambda: os._exit(0))
    app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="ER6 native editor gate")
    parser.add_argument(
        "--project",
        type=Path,
        default=Path.cwd(),
        help="PySTG project root used to construct the editor",
    )
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    if args.screenshot is not None:
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    run(project_root=args.project.resolve(), screenshot=args.screenshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

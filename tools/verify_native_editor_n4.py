"""Run the N4.2 native Qt editor gate on a real desktop session.

The gate proves three things that only a native session can show:

* the reactive slot authored through the editor's own commands compiles and
  runs on the formal ``compile_stage`` -> ``StageRunner`` path,
* the overlay the editor paints is the overlay that runtime produced -- the
  payload is read out of the runner, never written by this script,
* entering a slot's local reaction view happens through the same double-click
  an author performs, not by calling the editor's slot directly.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.stage_compile import compile_stage
from src.editor.timeline_workspace import CLIP_HEIGHT, TimelineClipItem
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.events import EventBus
from src.game.stage.context import StageContext
from src.game.stage.program import StageRunner
from src.qt_compat.QtCore import QPointF, Qt, QTimer
from src.qt_compat.QtTest import QTest
from src.qt_compat.QtWidgets import QApplication


class _GatePlayer:
    """Minimal player stand-in; the gate exercises reactions, not movement."""

    pos = [0.0, -0.75]


def _runtime_overlay(project: ProjectContext, document, clip) -> dict:
    """Run the authored scene on the formal path and return its real overlay."""

    program = compile_stage(project, document)
    if not program.reactive_clips:
        raise AssertionError("compile_stage dropped the authored reactive clip")
    bus = EventBus()
    context = StageContext(
        OptimizedBulletPool(max_bullets=64), _GatePlayer(), event_bus=bus
    )
    fired: list[str] = []

    def action(event, scope):
        # A generator action is the shape a real reaction takes: it stays
        # resident across frames, which is what puts a live instance in the
        # overlay the editor paints.
        fired.append(event.type)
        for _ in range(30):
            yield scope.wait(1)

    context.register_reaction_action(clip.payload["reaction"]["action"], action)
    runner = StageRunner(program)
    runner.start(context)
    bus.emit(clip.payload["activation"]["event_type"], {}, source="boss")
    runner.tick(context)
    if not fired:
        raise AssertionError("the formal runtime never invoked the authored reaction")
    overlay = runner.reactive_overlay
    if not overlay.get("trace"):
        raise AssertionError("the formal runtime produced no reactive trace")
    if not overlay.get("active_instances"):
        raise AssertionError("the formal runtime reported no live reaction instance")
    return overlay


def run(*, project_root: Path, screenshot: Path | None = None) -> None:
    app = QApplication.instance() or QApplication([])
    project = ProjectContext(project_root)
    window = EditorMainWindow(project)
    window.resize(1480, 920)
    window.show()
    app.processEvents()

    window._timeline_add_track("Reactive")
    track = window.session.document.tracks[0]
    window.timeline.selected_track_id = track.id
    window.session.editor_context["selected_track_id"] = track.id
    window._timeline_add_clip(track.id)
    app.processEvents()
    window.bottom_tabs.setCurrentWidget(window.timeline)
    clip = track.clips[0]

    overlay = _runtime_overlay(project, window.session.document, clip)

    # Deliver the runtime overlay through the editor's own statistics path so
    # the gate covers the plumbing an author's preview run would use.
    before = window.session.document.to_dict()
    window._active_stage_session = window.session
    window._preview_mode = "stage"
    window._preview_loaded_resource_id = window.session.document.id
    window._handle_pattern_preview_event(
        {
            "event": "statistics",
            "payload": {
                "state": "playing",
                "mode": "stage",
                "resource_id": window.session.document.id,
                "reactive_overlay": overlay,
            },
        }
    )
    app.processEvents()

    item = next(
        value
        for value in window.timeline.view.graphics_scene.items()
        if isinstance(value, TimelineClipItem) and value.clip_id == clip.id
    )
    if not item.active:
        raise AssertionError("Reactive runtime overlay did not activate the clip")
    if window.session.document.to_dict() != before:
        raise AssertionError("Reactive overlay mutated the authoring document")

    viewport = window.timeline.view.viewport()
    point = window.timeline.view.mapFromScene(
        item.scenePos() + QPointF(20, CLIP_HEIGHT / 2)
    )
    QTest.mouseClick(viewport, Qt.LeftButton, pos=point)
    QTest.mouseDClick(viewport, Qt.LeftButton, pos=point)
    QTest.mouseRelease(viewport, Qt.LeftButton, pos=point)
    app.processEvents()
    if window.session.editor_context.get("reactive_navigation", {}).get("target") != "reaction":
        raise AssertionError("Double-clicking the slot did not open the local reaction view")
    if window.session.document.to_dict() != before:
        raise AssertionError("Reactive navigation mutated the authoring document")
    if screenshot is not None and not window.grab().save(str(screenshot)):
        raise RuntimeError(f"could not save native screenshot: {screenshot}")

    print(
        "native_editor_n4_ok "
        f"kind={item.kind} clip={clip.id} traces={len(overlay['trace'])} "
        f"screenshot={str(screenshot) if screenshot else '(none)'}",
        flush=True,
    )

    # End this short-lived verification process from the timer after one real
    # event-loop turn, leaving the result above flushed.
    QTimer.singleShot(100, lambda: os._exit(0))
    app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="N4.2 native editor gate")
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

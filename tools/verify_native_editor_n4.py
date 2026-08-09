"""Run the N4.2 native Qt editor gate on a real desktop session.

This deliberately imports :mod:`src.editor.app` before creating the
application so ``src.qt_compat`` selects the production PySide6 binding.  The
pytest suite creates a legacy Qt application for compatibility tests; that
binding must not be mixed into this native gate.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.timeline_workspace import TimelineClipItem
from src.qt_compat.QtCore import QTimer
from src.qt_compat.QtWidgets import QApplication


def run(*, project_root: Path, screenshot: Path | None = None) -> None:
    app = QApplication.instance() or QApplication([])
    window = EditorMainWindow(ProjectContext(project_root))
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

    item = next(
        value
        for value in window.timeline.view.graphics_scene.items()
        if isinstance(value, TimelineClipItem)
    )
    item.setSelected(True)
    before = window.session.document.to_dict()
    window.timeline.set_reactive_overlay(
        {
            "active_instances": [
                {
                    "clip_id": track.clips[0].id,
                    "instance_id": "native-runtime#1",
                    "started_frame": 12,
                }
            ],
            "trace": [
                {
                    "kind": "start",
                    "clip_id": track.clips[0].id,
                    "trigger_kind": "on_event",
                }
            ],
            "diagnostics": [],
        }
    )
    window._timeline_reactive_navigate("reaction", track.clips[0].id)
    app.processEvents()
    if not item.active:
        raise AssertionError("Reactive runtime overlay did not activate the clip")
    if window.session.document.to_dict() != before:
        raise AssertionError("Reactive overlay mutated the authoring document")
    if window.session.editor_context.get("reactive_navigation", {}).get("target") != "reaction":
        raise AssertionError("Reactive navigation did not reach the local reaction view")
    if screenshot is not None and not window.grab().save(str(screenshot)):
        raise RuntimeError(f"could not save native screenshot: {screenshot}")

    print(
        "native_editor_n4_ok "
        f"kind={item.kind} clip={track.clips[0].id} "
        f"screenshot={str(screenshot) if screenshot else '(none)'}",
        flush=True,
    )

    # Qt can tear down two bindings in a host process after the event loop
    # exits. End this short-lived verification process from the timer after
    # one real event-loop turn, leaving the result above flushed.
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

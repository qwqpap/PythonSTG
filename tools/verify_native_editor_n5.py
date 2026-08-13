"""Run the N5 preset authoring gate in a real production Qt window."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.pattern_workspace import PatternWorkspace
from src.qt_compat.QtCore import QTimer
from src.qt_compat.QtWidgets import QApplication


def run(*, project_root: Path, screenshot: Path | None = None) -> None:
    app = QApplication.instance() or QApplication([])
    window = EditorMainWindow(ProjectContext(project_root))
    window.resize(1480, 920)
    window.show()
    window.new_pattern()
    app.processEvents()

    workspace = window.central_tabs.currentWidget()
    if not isinstance(workspace, PatternWorkspace):
        raise AssertionError("new Pattern did not open the Pattern workspace")
    if workspace.template_picker.count() != 14:
        raise AssertionError("starter preset library was not loaded into the picker")

    descriptor = next(
        item for item in window._preset_library.presets
        if item.display_name == "子弹分裂"
    )
    before_id = window.session.document.id
    window._apply_pattern_template(f"{descriptor.preset_id}@{descriptor.version}")
    app.processEvents()
    instance = window._preset_resolver.instance_from_document(window.session.document)
    if instance is None or instance.version != "1.0.0":
        raise AssertionError("exact preset instance was not embedded")
    if window.session.document.id != before_id:
        raise AssertionError("applying a preset changed the author resource identity")
    if workspace.mode() != "preset":
        raise AssertionError("linked preset did not open its progressive preset view")
    if workspace.preset_nodes.count() != len(descriptor.internal_nodes):
        raise AssertionError("virtual expansion does not match descriptor internals")
    linked_payload = window.session.document.to_dict()
    if screenshot is not None and not window.grab().save(str(screenshot)):
        raise RuntimeError(f"could not save native screenshot: {screenshot}")

    window._preset_materialize_requested()
    app.processEvents()
    if window._preset_resolver.instance_from_document(window.session.document) is not None:
        raise AssertionError("materialization left the document linked")
    if not window.undo() or window.session.document.to_dict() != linked_payload:
        raise AssertionError("materialization did not undo as one authoring command")
    app.processEvents()

    print(
        "native_editor_n5_ok "
        f"presets={workspace.template_picker.count()} "
        f"virtual_nodes={workspace.preset_nodes.count()} "
        f"screenshot={str(screenshot) if screenshot else '(none)'}",
        flush=True,
    )
    QTimer.singleShot(100, lambda: os._exit(0))
    app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="N5 native preset editor gate")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    if args.screenshot is not None:
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    run(project_root=args.project.resolve(), screenshot=args.screenshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

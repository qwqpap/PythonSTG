"""M4 user-visible runtime/preview contract addendum.

The five blob-frozen M4 regression files cover the authoritative timeline and
runtime-pose behavior. This addendum closes the remaining observable
questions from the editor smoke: the Qt host must own the formal preview
window, the gameplay renderer must remain outside the Qt canvas, and a sample
600 active bullets value must not become a hard process capacity.

This file is intentionally structural/runtime evidence only. A native
Windows window inspection is still required for the visual gate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.core.project_context import ProjectContext
from src.editor.preview_process import PatternPreviewProcess
from src.pattern import PatternDocument


REPO_ROOT = Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "docs" / "EDITOR_ROADMAP_TODO.md"


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def _project(tmp_path: Path) -> ProjectContext:
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True, exist_ok=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    return ProjectContext(tmp_path)


def _matching(client: PatternPreviewProcess, request_id: str) -> list[dict]:
    return [
        message
        for message in client.events
        if message.get("event") == "response"
        and message.get("request_id") == request_id
    ]


def test_m4_addendum_blob_matches_roadmap() -> None:
    blob = _git_blob_sha1(Path(__file__))
    roadmap = ROADMAP.read_text(encoding="utf-8")
    marker = "M4 runtime preview contract blob: " + chr(96) + blob + chr(96)
    assert marker in roadmap


def test_formal_preview_host_is_a_foreign_window_container_not_a_qt_renderer() -> None:
    host_source = (REPO_ROOT / "src" / "editor" / "runtime_preview.py").read_text(
        encoding="utf-8"
    )
    worker_source = (REPO_ROOT / "tools" / "preview_pattern.py").read_text(
        encoding="utf-8"
    )

    assert "QWindow.fromWinId" in host_source
    assert "QWidget.createWindowContainer" in host_source
    assert "QPainter(" not in host_source
    assert "from src.qt_compat.QtGui import QPainter" not in host_source
    assert "separate process" in host_source

    # The actual gameplay surface owns the formal renderer and optimized pool.
    assert "import glfw" in worker_source
    assert "import moderngl" in worker_source
    assert "OptimizedBulletPool(max_bullets=max_bullets" in worker_source
    assert "StageRunner" in worker_source


def test_formal_worker_forwards_capacity_above_sample_bullet_count(
    tmp_path, qapp_session
) -> None:
    del qapp_session
    client = PatternPreviewProcess(_project(tmp_path))
    assert client.start(headless=True, max_bullets=4096)
    try:
        assert client.wait_for(lambda: client.ready)

        load_id = client.send_command(
            "load",
            {"document": PatternDocument.new("Capacity contract").to_dict()},
        )
        assert client.wait_for(lambda: bool(_matching(client, load_id)))
        assert _matching(client, load_id)[0]["payload"]["ok"] is True

        stats_id = client.send_command("get-stats")
        assert client.wait_for(lambda: bool(_matching(client, stats_id)))
        stats = _matching(client, stats_id)[0]["payload"]["result"]
        assert stats["max_bullets"] == 4096
        assert stats["max_bullets"] > 600
    finally:
        client.stop()


def test_m4_contract_is_present_in_roadmap_and_keeps_visual_gate_separate() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for marker in (
        "M4-P1",
        "M4-P2",
        "M4-P3",
        "M4-P4",
        "M4-P5",
        "M4-P6",
        "native Windows",
        "Offscreen Qt tests cannot close that visual gate",
    ):
        assert marker in roadmap

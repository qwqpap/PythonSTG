"""Qt-free read models used while the shell renders the active document."""

from __future__ import annotations

from src.authoring.scene.document import EditorNode, SceneDocument, TimelineClip, TimelineTrack
from src.authoring.commands.scene import find_parent as _find_parent
from src.authoring.commands.variables import (
    compatible_variable_bindings as _compatible_variable_bindings,
)
from src.authoring.commands.variables import find_variable as _find_variable
from src.authoring.commands.timeline import find_clip as _find_clip
from src.authoring.commands.timeline import find_track as _find_track
from src.authoring.commands.timeline import require_track as _require_track


def find_timeline_clip(
    document: SceneDocument,
    clip_id: str,
) -> tuple[TimelineTrack, TimelineClip, int] | None:
    return _find_clip(document, clip_id)


def find_timeline_track(
    document: SceneDocument,
    track_id: str,
    state_id: str | None = None,
) -> TimelineTrack | None:
    return _find_track(document, track_id, state_id)


def require_timeline_track(document: SceneDocument, track_id: str) -> TimelineTrack:
    return _require_track(document, track_id)


def find_scene_parent(
    root: EditorNode,
    node_id: str,
) -> tuple[EditorNode, int] | None:
    return _find_parent(root, node_id)


def find_variable(document: SceneDocument, variable_id: str):
    return _find_variable(document, variable_id)


def compatible_variable_bindings(
    document: SceneDocument,
    *,
    type_id: str,
    scope: str,
    owner_id: str | None,
    exclude_id: str,
):
    return _compatible_variable_bindings(
        document,
        type_id=type_id,
        scope=scope,
        owner_id=owner_id,
        exclude_id=exclude_id,
    )


__all__ = [
    "compatible_variable_bindings",
    "find_scene_parent",
    "find_timeline_clip",
    "find_timeline_track",
    "find_variable",
    "require_timeline_track",
]

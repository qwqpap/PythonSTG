"""Qt-free read models used while the shell renders the active document."""

from __future__ import annotations

from src.editor.document import SceneDocument, TimelineClip, TimelineTrack
from src.editor.timeline_commands import find_clip as _find_clip
from src.editor.timeline_commands import find_track as _find_track


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


__all__ = ["find_timeline_clip", "find_timeline_track"]

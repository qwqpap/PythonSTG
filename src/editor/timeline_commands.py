"""Undoable Track/Clip/Keyframe mutations for the M4 timeline editor."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .document import (
    SceneDocument,
    TimelineClip,
    TimelineKeyframe,
    TimelineTrack,
    new_document_id,
)


class TimelineMutationError(ValueError):
    """Raised when a timeline command cannot find or safely mutate its target."""


def timeline_tracks(
    document: SceneDocument,
    state_id: str | None = None,
) -> list[TimelineTrack]:
    if state_id is None:
        return document.tracks
    state = document.state_graph.find_state(state_id)
    if state is None:
        raise TimelineMutationError(f"Timeline State does not exist: {state_id}")
    return state.tracks


def _track_collections(document: SceneDocument):
    for state in document.state_graph.walk_states():
        yield state.id, state.tracks


def find_track(
    document: SceneDocument,
    track_id: str,
    state_id: str | None = None,
) -> TimelineTrack | None:
    collections = (
        ((state_id, timeline_tracks(document, state_id)),)
        if state_id is not None
        else _track_collections(document)
    )
    for _owner_id, tracks in collections:
        track = next((item for item in tracks if item.id == track_id), None)
        if track is not None:
            return track
    return None


def _track_location(
    document: SceneDocument,
    track_id: str,
) -> tuple[str, list[TimelineTrack], TimelineTrack, int] | None:
    for state_id, tracks in _track_collections(document):
        for index, track in enumerate(tracks):
            if track.id == track_id:
                return state_id, tracks, track, index
    return None


def require_track(document: SceneDocument, track_id: str) -> TimelineTrack:
    track = find_track(document, track_id)
    if track is None:
        raise TimelineMutationError(f"Timeline track does not exist: {track_id}")
    return track


def find_clip(
    document: SceneDocument,
    clip_id: str,
) -> tuple[TimelineTrack, TimelineClip, int] | None:
    for _state_id, tracks in _track_collections(document):
        for track in tracks:
            for index, clip in enumerate(track.clips):
                if clip.id == clip_id:
                    return track, clip, index
    return None


def require_clip(
    document: SceneDocument,
    clip_id: str,
) -> tuple[TimelineTrack, TimelineClip, int]:
    result = find_clip(document, clip_id)
    if result is None:
        raise TimelineMutationError(f"Timeline clip does not exist: {clip_id}")
    return result


def clone_clip_with_new_ids(clip: TimelineClip) -> TimelineClip:
    payload = clip.to_dict()
    payload["id"] = new_document_id()
    for keyframe in payload["keyframes"]:
        keyframe["id"] = new_document_id()
    payload["name"] = f"{clip.name} Copy"
    return TimelineClip.from_dict(payload)


@dataclass
class AddTrackCommand:
    document: SceneDocument
    track: TimelineTrack
    index: int | None = None
    state_id: str | None = None
    label: str = "Add timeline track"
    _inserted_index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if find_track(self.document, self.track.id) is not None:
            raise TimelineMutationError(f"Duplicate timeline track id: {self.track.id}")
        tracks = timeline_tracks(self.document, self.state_id)
        target = len(tracks) if self.index is None else int(self.index)
        target = max(0, min(target, len(tracks)))
        tracks.insert(target, self.track)
        self._inserted_index = target

    def undo(self) -> None:
        location = _track_location(self.document, self.track.id)
        if location is None:
            raise TimelineMutationError("Cannot undo track add; track is missing")
        location[1].remove(location[2])


@dataclass
class RemoveTrackCommand:
    document: SceneDocument
    track_id: str
    label: str = "Delete timeline track"
    _track: TimelineTrack | None = field(default=None, init=False, repr=False)
    _index: int | None = field(default=None, init=False, repr=False)
    _state_id: str | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        location = _track_location(self.document, self.track_id)
        if location is None:
            raise TimelineMutationError(f"Timeline track does not exist: {self.track_id}")
        _state_id, tracks, track, index = location
        tracks.pop(index)
        if self._track is None:
            self._track = track
            self._index = index
            self._state_id = _state_id

    def undo(self) -> None:
        if self._track is None or self._index is None or self._state_id is None:
            raise TimelineMutationError("Cannot undo track delete before execution")
        tracks = timeline_tracks(self.document, self._state_id)
        tracks.insert(min(self._index, len(tracks)), self._track)


@dataclass
class SetTrackPropertiesCommand:
    document: SceneDocument
    track_id: str
    values: dict[str, Any]
    label: str = "Edit timeline track"
    _previous: dict[str, Any] | None = field(default=None, init=False, repr=False)

    _ALLOWED = frozenset({"name", "target_id", "channel", "order", "muted"})

    def execute(self) -> None:
        unknown = set(self.values) - self._ALLOWED
        if unknown:
            raise TimelineMutationError(
                "Unsupported track properties: " + ", ".join(sorted(unknown))
            )
        track = require_track(self.document, self.track_id)
        if self._previous is None:
            self._previous = {key: deepcopy(getattr(track, key)) for key in self.values}
        for key, value in self.values.items():
            setattr(track, key, deepcopy(value))

    def undo(self) -> None:
        if self._previous is None:
            raise TimelineMutationError("Cannot undo track edit before execution")
        track = require_track(self.document, self.track_id)
        for key, value in self._previous.items():
            setattr(track, key, deepcopy(value))

    def merge_with(self, other: object) -> bool:
        if not isinstance(other, SetTrackPropertiesCommand):
            return False
        if self.document is not other.document or self.track_id != other.track_id:
            return False
        if set(self.values) != set(other.values):
            return False
        self.values = deepcopy(other.values)
        return True


@dataclass
class MoveTrackCommand:
    document: SceneDocument
    track_id: str
    target_index: int
    label: str = "Reorder timeline track"
    _previous_tracks: list[TimelineTrack] | None = field(default=None, init=False, repr=False)
    _previous_orders: dict[str, int] | None = field(default=None, init=False, repr=False)
    _state_id: str | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        location = _track_location(self.document, self.track_id)
        if location is None:
            raise TimelineMutationError(f"Timeline track does not exist: {self.track_id}")
        state_id, tracks, track, old_index = location
        if self._previous_tracks is None:
            self._state_id = state_id
            self._previous_tracks = list(tracks)
            self._previous_orders = {item.id: item.order for item in tracks}
        target = max(0, min(int(self.target_index), len(tracks) - 1))
        if target == old_index:
            return
        tracks.pop(old_index)
        tracks.insert(target, track)
        for order, item in enumerate(tracks):
            item.order = order

    def undo(self) -> None:
        if (
            self._previous_tracks is None
            or self._previous_orders is None
            or self._state_id is None
        ):
            raise TimelineMutationError("Cannot undo track reorder before execution")
        tracks = timeline_tracks(self.document, self._state_id)
        tracks[:] = self._previous_tracks
        for item in tracks:
            item.order = self._previous_orders[item.id]


@dataclass
class AddClipCommand:
    document: SceneDocument
    track_id: str
    clip: TimelineClip
    index: int | None = None
    label: str = "Add timeline clip"
    _inserted_index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if find_clip(self.document, self.clip.id) is not None:
            raise TimelineMutationError(f"Duplicate timeline clip id: {self.clip.id}")
        track = require_track(self.document, self.track_id)
        if self.clip.kind != track.kind:
            raise TimelineMutationError("Clip kind must match its track")
        target = len(track.clips) if self.index is None else int(self.index)
        target = max(0, min(target, len(track.clips)))
        track.clips.insert(target, self.clip)
        self._inserted_index = target

    def undo(self) -> None:
        result = find_clip(self.document, self.clip.id)
        if result is None:
            raise TimelineMutationError("Cannot undo clip add; clip is missing")
        result[0].clips.pop(result[2])


@dataclass
class RemoveClipCommand:
    document: SceneDocument
    clip_id: str
    label: str = "Delete timeline clip"
    _track_id: str | None = field(default=None, init=False, repr=False)
    _clip: TimelineClip | None = field(default=None, init=False, repr=False)
    _index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        track, clip, index = require_clip(self.document, self.clip_id)
        track.clips.pop(index)
        if self._clip is None:
            self._track_id = track.id
            self._clip = clip
            self._index = index

    def undo(self) -> None:
        if self._track_id is None or self._clip is None or self._index is None:
            raise TimelineMutationError("Cannot undo clip delete before execution")
        track = require_track(self.document, self._track_id)
        track.clips.insert(min(self._index, len(track.clips)), self._clip)


@dataclass
class MoveResizeClipCommand:
    document: SceneDocument
    clip_id: str
    start_frame: int
    duration_frames: int
    label: str = "Move/resize timeline clip"
    _previous: tuple[int, int] | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        _track, clip, _index = require_clip(self.document, self.clip_id)
        if self._previous is None:
            self._previous = (clip.start_frame, clip.duration_frames)
        clip.start_frame = int(self.start_frame)
        clip.duration_frames = int(self.duration_frames)

    def undo(self) -> None:
        if self._previous is None:
            raise TimelineMutationError("Cannot undo clip move before execution")
        _track, clip, _index = require_clip(self.document, self.clip_id)
        clip.start_frame, clip.duration_frames = self._previous

    def merge_with(self, other: object) -> bool:
        if not isinstance(other, MoveResizeClipCommand):
            return False
        if self.document is not other.document or self.clip_id != other.clip_id:
            return False
        self.start_frame = other.start_frame
        self.duration_frames = other.duration_frames
        return True


@dataclass
class SetClipPropertiesCommand:
    document: SceneDocument
    clip_id: str
    values: dict[str, Any]
    label: str = "Edit timeline clip"
    _previous: dict[str, Any] | None = field(default=None, init=False, repr=False)

    _ALLOWED = frozenset(
        {
            "name",
            "start_frame",
            "duration_frames",
            "target_id",
            "channel",
            "order",
            "loop_count",
            "enabled",
            "payload",
            "keyframes",
        }
    )

    def execute(self) -> None:
        unknown = set(self.values) - self._ALLOWED
        if unknown:
            raise TimelineMutationError(
                "Unsupported clip properties: " + ", ".join(sorted(unknown))
            )
        _track, clip, _index = require_clip(self.document, self.clip_id)
        if self._previous is None:
            self._previous = {
                key: deepcopy(getattr(clip, key))
                for key in self.values
            }
        for key, value in self.values.items():
            if key == "keyframes":
                parsed = [
                    item if isinstance(item, TimelineKeyframe) else TimelineKeyframe.from_dict(item)
                    for item in value
                ]
                setattr(clip, key, parsed)
            else:
                setattr(clip, key, deepcopy(value))

    def undo(self) -> None:
        if self._previous is None:
            raise TimelineMutationError("Cannot undo clip edit before execution")
        _track, clip, _index = require_clip(self.document, self.clip_id)
        for key, value in self._previous.items():
            setattr(clip, key, deepcopy(value))

    def merge_with(self, other: object) -> bool:
        if not isinstance(other, SetClipPropertiesCommand):
            return False
        if self.document is not other.document or self.clip_id != other.clip_id:
            return False
        if set(self.values) != set(other.values):
            return False
        self.values = deepcopy(other.values)
        return True


@dataclass
class AddKeyframeCommand:
    document: SceneDocument
    clip_id: str
    keyframe: TimelineKeyframe
    label: str = "Add timeline keyframe"

    def execute(self) -> None:
        _track, clip, _index = require_clip(self.document, self.clip_id)
        if any(item.id == self.keyframe.id for item in clip.keyframes):
            raise TimelineMutationError(f"Duplicate keyframe id: {self.keyframe.id}")
        clip.keyframes.append(self.keyframe)
        clip.keyframes.sort(key=lambda item: item.frame)

    def undo(self) -> None:
        _track, clip, _index = require_clip(self.document, self.clip_id)
        for index, item in enumerate(clip.keyframes):
            if item.id == self.keyframe.id:
                clip.keyframes.pop(index)
                return
        raise TimelineMutationError("Cannot undo keyframe add; keyframe is missing")


@dataclass
class RemoveKeyframeCommand:
    document: SceneDocument
    clip_id: str
    keyframe_id: str
    label: str = "Delete timeline keyframe"
    _keyframe: TimelineKeyframe | None = field(default=None, init=False, repr=False)
    _index: int | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        _track, clip, _clip_index = require_clip(self.document, self.clip_id)
        for index, keyframe in enumerate(clip.keyframes):
            if keyframe.id == self.keyframe_id:
                self._keyframe = keyframe
                self._index = index
                clip.keyframes.pop(index)
                return
        raise TimelineMutationError(f"Timeline keyframe does not exist: {self.keyframe_id}")

    def undo(self) -> None:
        if self._keyframe is None or self._index is None:
            raise TimelineMutationError("Cannot undo keyframe delete before execution")
        _track, clip, _clip_index = require_clip(self.document, self.clip_id)
        clip.keyframes.insert(min(self._index, len(clip.keyframes)), self._keyframe)


@dataclass
class SetKeyframePropertiesCommand:
    document: SceneDocument
    clip_id: str
    keyframe_id: str
    values: dict[str, Any]
    label: str = "Edit timeline keyframe"
    _previous: dict[str, Any] | None = field(default=None, init=False, repr=False)

    _ALLOWED = frozenset({"frame", "value", "interpolation"})

    def execute(self) -> None:
        unknown = set(self.values) - self._ALLOWED
        if unknown:
            raise TimelineMutationError(
                "Unsupported keyframe properties: " + ", ".join(sorted(unknown))
            )
        _track, clip, _clip_index = require_clip(self.document, self.clip_id)
        keyframe = next(
            (item for item in clip.keyframes if item.id == self.keyframe_id), None
        )
        if keyframe is None:
            raise TimelineMutationError(
                f"Timeline keyframe does not exist: {self.keyframe_id}"
            )
        if self._previous is None:
            self._previous = {
                key: deepcopy(getattr(keyframe, key)) for key in self.values
            }
        for key, value in self.values.items():
            setattr(keyframe, key, deepcopy(value))
        clip.keyframes.sort(key=lambda item: item.frame)

    def undo(self) -> None:
        if self._previous is None:
            raise TimelineMutationError("Cannot undo keyframe edit before execution")
        _track, clip, _clip_index = require_clip(self.document, self.clip_id)
        keyframe = next(
            (item for item in clip.keyframes if item.id == self.keyframe_id), None
        )
        if keyframe is None:
            raise TimelineMutationError(
                f"Timeline keyframe does not exist: {self.keyframe_id}"
            )
        for key, value in self._previous.items():
            setattr(keyframe, key, deepcopy(value))
        clip.keyframes.sort(key=lambda item: item.frame)

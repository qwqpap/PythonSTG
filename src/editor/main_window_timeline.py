"""Timeline dock slots: tracks, clips, keyframes, playhead and reactive slots."""

from __future__ import annotations

from .document import (
    DocumentError,
    EditorNode,
    SceneDocument,
    TimelineClip,
    TimelineKeyframe,
    TimelineTrack,
)
from .timeline_commands import (
    AddClipCommand,
    AddKeyframeCommand,
    AddTrackCommand,
    MoveResizeClipCommand,
    MoveTrackCommand,
    RemoveClipCommand,
    RemoveKeyframeCommand,
    RemoveTrackCommand,
    SetClipPropertiesCommand,
    SetKeyframePropertiesCommand,
    SetTrackPropertiesCommand,
    clone_clip_with_new_ids,
    find_clip,
    require_track,
    timeline_tracks,
)
from .shell import WindowService


class TimelineService(WindowService):
    """Timeline dock slots: tracks, clips, keyframes, playhead and reactive slots.

    These slots stay bound to the window instance instead of moving into a
    controller object: every attribute they touch is owned by
    ``EditorMainWindow``, and the editor tests plus the three native gates drive
    these methods by name.  Mix in before the Qt base class, the same way
    ``SpaceTapSearchMixin`` is used by ``SceneViewport``.
    """

    def _timeline_default_target(self, kind: str) -> EditorNode | None:
        if not isinstance(self.session.document, SceneDocument):
            return None
        selected = self.session.node(self._selected_id)
        if kind == "Pattern":
            if selected is not None and selected.type == "PatternInstance":
                return selected
            return next(
                (
                    node
                    for node in self.session.document.root.walk()
                    if node.type == "PatternInstance"
                ),
                None,
            )
        if kind == "Movement":
            if (
                selected is not None
                and isinstance(selected.properties.get("x"), (int, float))
                and not isinstance(selected.properties.get("x"), bool)
                and isinstance(selected.properties.get("y"), (int, float))
                and not isinstance(selected.properties.get("y"), bool)
            ):
                return selected
            return next(
                (
                    node
                    for node in self.session.document.root.walk()
                    if node.type in {"Emitter", "Boss"}
                ),
                None,
            )
        if kind == "Property":
            if selected is not None and "enabled" in selected.properties:
                return selected
            return next(
                (
                    node
                    for node in self.session.document.root.walk()
                    if "enabled" in node.properties
                ),
                None,
            )
        return None

    def _timeline_add_track(self, kind: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        target = self._timeline_default_target(kind)
        if kind in {"Pattern", "Movement", "Property"} and target is None:
            self._show_error(
                "Add timeline track failed",
                ValueError(
                    f"Create or select a compatible target before adding a {kind} track"
                ),
            )
            return
        channels = {
            "Pattern": "danmaku",
            "Movement": "position",
            "Audio": "bgm",
            "Background": "background",
            "Event": "event",
            "Property": "enabled",
            "ScriptEvent": "script",
            "Reactive": "reaction",
        }
        state_id = str(
            self.session.editor_state.selection.state_id
            or self.session.document.state_graph.initial_state_id
        )
        selected_tracks = timeline_tracks(self.session.document, state_id)
        track = TimelineTrack(
            name=f"{kind} Track",
            kind=kind,
            channel=channels[kind],
            target_id=target.id if target is not None else None,
            order=len(selected_tracks),
        )
        try:
            self.session.apply(
                AddTrackCommand(
                    self.session.document,
                    track,
                    state_id=state_id,
                    label=f"Add {kind} track",
                )
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Add timeline track failed", exc)
            return
        self.timeline.selected_track_id = track.id
        self.session.editor_state.selection.track_id = track.id
        self._log(f"Added {kind} timeline track")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_track_selected(self, track_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            track = require_track(self.session.document, track_id)
        except ValueError:
            return
        self.session.editor_state.selection.track_id = track.id
        self.session.editor_state.selection.clip_id = None
        self.inspector.set_timeline_track(
            track,
            list(self.session.document.root.walk()),
        )

    def _timeline_reactive_navigate(self, target: str, resource_id: str) -> None:
        """Remember a local reaction/behavior target without merging views."""

        self.session.editor_state.timeline.reactive_navigation = (
            str(target),
            str(resource_id),
        )
        self._log(f"Navigate to {target} {resource_id}")

    def _timeline_track_properties_requested(
        self,
        track_id: str,
        values: dict[str, object],
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                SetTrackPropertiesCommand(
                    self.session.document,
                    track_id,
                    values,
                ),
                coalesce=True,
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Edit timeline track failed", exc)
            self._refresh()
            return
        self.session.editor_state.selection.track_id = track_id
        self.session.editor_state.selection.clip_id = None
        self._log("Edited timeline track")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_delete_track(self, track_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                RemoveTrackCommand(self.session.document, track_id)
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Delete timeline track failed", exc)
            return
        self.session.editor_state.selection.track_id = None
        self.session.editor_state.selection.clip_id = None
        self.timeline.selected_track_id = None
        self.timeline.selected_clip_id = None
        self._log("Deleted timeline track")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_move_track(self, track_id: str, delta: int) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            track = require_track(self.session.document, track_id)
            state_id = str(
                self.session.editor_state.selection.state_id
                or self.session.document.state_graph.initial_state_id
            )
            selected_tracks = timeline_tracks(self.session.document, state_id)
            current = selected_tracks.index(track)
            target = max(0, min(current + int(delta), len(selected_tracks) - 1))
            if target == current:
                return
            self.session.apply(
                MoveTrackCommand(self.session.document, track_id, target)
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Reorder timeline track failed", exc)
            return
        self.session.editor_state.selection.track_id = track_id
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_mute_track(self, track_id: str, muted: bool) -> None:
        self._timeline_track_properties_requested(track_id, {"muted": bool(muted)})

    def _timeline_add_clip(self, track_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            track = require_track(self.session.document, track_id)
        except ValueError as exc:
            self._show_error("Add timeline clip failed", exc)
            return
        start = self.timeline.playhead_frame
        target_id = track.target_id
        duration = 1
        payload: dict[str, object] = {}
        keyframes: list[TimelineKeyframe] = []
        if track.kind == "Pattern":
            duration = self.session.document.timebase.tick_rate * 10
            if target_id is None:
                self._show_error(
                    "Add timeline clip failed",
                    ValueError("Pattern track needs a PatternInstance target"),
                )
                return
        elif track.kind == "Movement":
            duration = self.session.document.timebase.tick_rate * 2
            node = self.session.node(target_id)
            if node is None:
                self._show_error(
                    "Add timeline clip failed",
                    ValueError("Movement track needs a Scene node target"),
                )
                return
            x = float(node.properties.get("x", 192.0))
            y = float(node.properties.get("y", 224.0))
            keyframes = [
                TimelineKeyframe(0, {"x": x, "y": y}),
                TimelineKeyframe(
                    duration,
                    {"x": min(384.0, x + 64.0), "y": y},
                    interpolation="ease_in_out",
                ),
            ]
        elif track.kind == "Audio":
            duration = max(
                self.session.document.timebase.tick_rate * 30,
                self.session.document.duration_frames,
            )
            payload = {"action": "play", "name": "bgm", "loops": -1}
        elif track.kind == "Background":
            payload = {
                "resource": "res://game_content/backgrounds/default.pystg.json",
                "fade_frames": 30,
            }
        elif track.kind == "Event":
            payload = {"event_type": "timeline_event", "data": {}}
        elif track.kind == "Property":
            node = self.session.node(target_id)
            if node is None:
                self._show_error(
                    "Add timeline clip failed",
                    ValueError("Property track needs a Scene node target"),
                )
                return
            payload = {
                "property": track.channel,
                "value": node.properties.get(track.channel, True),
            }
        elif track.kind == "ScriptEvent":
            payload = {"hook": "on_timeline_event", "data": {}}
        elif track.kind == "Reactive":
            # The runtime evaluates arming on the frame boundary after a clip
            # starts, so a one-frame window is never observed and the hook would
            # be dead on arrival.  Give the hook a real armed window instead.
            duration = self.session.document.timebase.tick_rate * 10
            payload = {
                "activation": {
                    "kind": "on_event",
                    "event_type": "boss.hit",
                },
                "reaction": {
                    "id": f"reaction-{track.id[:8]}",
                    "event_type": "boss.hit",
                    "action": "reaction.action",
                    "once_per_scope": False,
                },
            }
        clip = TimelineClip(
            name=f"{track.kind} Clip",
            kind=track.kind,
            start_frame=start,
            duration_frames=duration,
            target_id=target_id,
            channel=track.channel,
            order=len(track.clips),
            payload=payload,
            keyframes=keyframes,
        )
        try:
            self.session.apply(
                AddClipCommand(
                    self.session.document,
                    track.id,
                    clip,
                    label=f"Add {track.kind} clip",
                )
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Add timeline clip failed", exc)
            return
        self.session.editor_state.selection.clip_id = clip.id
        self.timeline.selected_clip_id = clip.id
        self._log(f"Added {track.kind} clip at frame {start}")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_add_keyframe(self, clip_id: str, playhead_frame: int) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        result = find_clip(self.session.document, clip_id)
        if result is None:
            return
        track, clip, _index = result
        if clip.kind not in {"Movement", "Property"}:
            self._show_error(
                "Add timeline keyframe failed",
                ValueError("Only Movement and Property clips support keyframes"),
            )
            return
        relative = max(0, int(playhead_frame) - clip.start_frame)
        local = min(clip.duration_frames, relative % clip.duration_frames if clip.loop_count > 1 else relative)
        if any(item.frame == local for item in clip.keyframes):
            self._show_error(
                "Add timeline keyframe failed",
                ValueError(f"A keyframe already exists at local frame {local}"),
            )
            return
        target = self.session.node(clip.target_id or track.target_id)
        if clip.kind == "Movement":
            value = {
                "x": float(target.properties.get("x", 192.0)) if target else 192.0,
                "y": float(target.properties.get("y", 224.0)) if target else 224.0,
            }
        else:
            value = clip.payload.get("value")
            if clip.keyframes:
                previous = [item for item in clip.keyframes if item.frame < local]
                value = (previous[-1] if previous else clip.keyframes[0]).value
        keyframe = TimelineKeyframe(local, value)
        try:
            self.session.apply(
                AddKeyframeCommand(self.session.document, clip.id, keyframe)
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Add timeline keyframe failed", exc)
            return
        self._log(f"Added keyframe at local frame {local}")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_delete_keyframe(self, clip_id: str, playhead_frame: int) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        result = find_clip(self.session.document, clip_id)
        if result is None or not result[1].keyframes:
            return
        clip = result[1]
        relative = max(0, int(playhead_frame) - clip.start_frame)
        local = min(clip.duration_frames, relative % clip.duration_frames if clip.loop_count > 1 else relative)
        keyframe = min(clip.keyframes, key=lambda item: abs(item.frame - local))
        if abs(keyframe.frame - local) > self.timeline.snap_spin.value():
            self._show_error(
                "Delete timeline keyframe failed",
                ValueError("Move the playhead onto a keyframe before deleting it"),
            )
            return
        try:
            self.session.apply(
                RemoveKeyframeCommand(
                    self.session.document,
                    clip.id,
                    keyframe.id,
                )
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Delete timeline keyframe failed", exc)
            return
        self._log(f"Deleted keyframe at local frame {keyframe.frame}")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_keyframe_geometry(
        self,
        clip_id: str,
        keyframe_id: str,
        frame: int,
    ) -> None:
        self._timeline_keyframe_properties_requested(
            clip_id,
            keyframe_id,
            {"frame": int(frame)},
        )

    def _timeline_clip_geometry(
        self,
        clip_id: str,
        start_frame: int,
        duration_frames: int,
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                MoveResizeClipCommand(
                    self.session.document,
                    clip_id,
                    start_frame,
                    duration_frames,
                ),
                coalesce=True,
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Move timeline clip failed", exc)
            self._refresh()
            return
        self.session.editor_state.selection.clip_id = clip_id
        self._log(f"Moved timeline clip to frame {start_frame}")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_duplicate_clip(self, clip_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        result = find_clip(self.session.document, clip_id)
        if result is None:
            return
        track, clip, index = result
        duplicate = clone_clip_with_new_ids(clip)
        duplicate.start_frame = clip.end_frame
        try:
            self.session.apply(
                AddClipCommand(
                    self.session.document,
                    track.id,
                    duplicate,
                    index=index + 1,
                    label=f"Duplicate {clip.name}",
                )
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Duplicate timeline clip failed", exc)
            return
        self.session.editor_state.selection.clip_id = duplicate.id
        self._log(f"Duplicated {clip.name}")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_delete_clip(self, clip_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                RemoveClipCommand(
                    self.session.document,
                    clip_id,
                    label="Delete timeline clip",
                )
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Delete timeline clip failed", exc)
            return
        self.session.editor_state.selection.clip_id = None
        self.timeline.selected_clip_id = None
        self._log("Deleted timeline clip")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_clip_selected(self, track_id: str, clip_id: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        result = find_clip(self.session.document, clip_id)
        if result is None:
            return
        self.session.editor_state.selection.track_id = track_id
        self.session.editor_state.selection.clip_id = clip_id
        self.inspector.set_timeline_clip(
            result[0],
            result[1],
            list(self.session.document.root.walk()),
        )

    def _timeline_clip_properties_requested(
        self,
        clip_id: str,
        values: dict[str, object],
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                SetClipPropertiesCommand(
                    self.session.document,
                    clip_id,
                    values,
                    label="Edit timeline clip",
                ),
                coalesce=True,
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Edit timeline clip failed", exc)
            self._refresh()
            return
        self.session.editor_state.selection.clip_id = clip_id
        self._log("Edited timeline clip")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_keyframe_properties_requested(
        self,
        clip_id: str,
        keyframe_id: str,
        values: dict[str, object],
    ) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        try:
            self.session.apply(
                SetKeyframePropertiesCommand(
                    self.session.document,
                    clip_id,
                    keyframe_id,
                    values,
                ),
                coalesce=True,
            )
        except (DocumentError, ValueError) as exc:
            self._show_error("Edit timeline keyframe failed", exc)
            self._refresh()
            return
        self.session.editor_state.selection.clip_id = clip_id
        self._log("Edited timeline keyframe")
        self._refresh()
        self._sync_active_stage_preview()

    def _timeline_playhead_changed(self, frame: int) -> None:
        session = self.document_manager.active
        if session is None:
            return
        session.editor_state.timeline.playhead_frame = int(frame)
        if (
            self._pattern_preview_client.is_running
            and session is self._active_stage_session
            and isinstance(session.document, SceneDocument)
            and self._preview_mode == "stage"
            and self._preview_loaded_resource_id == session.document.id
        ):
            self._pattern_preview_client.send_command("seek", {"frame": int(frame)})

    def _timeline_zoom_changed(self, value: float) -> None:
        if self.document_manager.active is not None:
            self.session.editor_state.timeline.zoom = float(value)

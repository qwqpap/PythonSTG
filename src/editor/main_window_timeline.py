"""Timeline shell adapters that translate Qt events into typed editor intents."""

from __future__ import annotations

from src.qt_compat.QtCore import QTimer

from .application import (
    InvalidationScope,
    InvalidationSet,
    IntentRejectedError,
    SetTimelinePlayheadIntent,
    TimelineAction,
    TimelineIntent,
)
from .application.queries import find_timeline_clip, find_timeline_track
from .document import SceneDocument
from .shell import WindowService


class TimelineService(WindowService):
    """Keep public timeline entry points while Coordinator owns mutations."""

    def _dispatch_timeline_intent(
        self,
        intent,
        *,
        error_title: str | None = "Edit timeline failed",
        label: str = "",
        sync_stage: bool = False,
        defer_invalidation: bool = False,
        refresh_inspector: bool = False,
    ) -> bool:
        try:
            invalidation = self.editor_coordinator.dispatch(intent)
        except (IntentRejectedError, ValueError) as exc:
            if error_title is not None:
                self._show_error(error_title, exc)
            return False
        if invalidation.scopes:
            if defer_invalidation:
                if refresh_inspector:
                    self.apply_invalidation(
                        intent.document_id,
                        InvalidationSet((InvalidationScope.INSPECTOR,)),
                    )
                QTimer.singleShot(
                    0,
                    lambda document_id=intent.document_id, result=invalidation: (
                        self.apply_invalidation(document_id, result)
                    ),
                )
            else:
                self.apply_invalidation(intent.document_id, invalidation)
            if label:
                self._log(label)
            if sync_stage:
                self._sync_active_stage_preview()
        return bool(invalidation.scopes)

    def _timeline_add_track(self, kind: str) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        track_kind = str(kind)
        self._dispatch_timeline_intent(
            TimelineIntent(document_id, TimelineAction.ADD_TRACK, target_id=track_kind),
            error_title="Add timeline track failed",
            label=f"Added {track_kind} timeline track",
            sync_stage=True,
        )

    def _timeline_track_selected(self, track_id: str) -> None:
        if getattr(self, "_timeline_selection_dispatching", False):
            return
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_track_id = str(track_id)
        selection = session.editor_state.selection
        if selection.track_id == selected_track_id and selection.clip_id is None:
            return
        self._timeline_selection_dispatching = True
        try:
            self._dispatch_timeline_intent(
                TimelineIntent(
                    document_id,
                    TimelineAction.SELECT_TRACK,
                    target_id=selected_track_id,
                ),
                error_title=None,
                defer_invalidation=True,
                refresh_inspector=True,
            )
        finally:
            self._timeline_selection_dispatching = False

    def _timeline_reactive_navigate(self, target: str, resource_id: str) -> None:
        """Remember a local reaction/behavior target without merging views."""

        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        target_name = str(target)
        stable_resource_id = str(resource_id)
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.SET_REACTIVE_NAVIGATION,
                target_id=target_name,
                related_id=stable_resource_id,
            ),
            error_title=None,
            label=f"Navigate to {target_name} {stable_resource_id}",
        )

    def _timeline_track_properties_requested(
        self,
        track_id: str,
        values: dict[str, object],
    ) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_track_id = str(track_id)
        payload = dict(values)
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.SET_TRACK_PROPERTIES,
                target_id=selected_track_id,
                values=payload,
                coalesce=True,
            ),
            error_title="Edit timeline track failed",
            label="Edited timeline track",
            sync_stage=True,
        )

    def _timeline_delete_track(self, track_id: str) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_track_id = str(track_id)
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.REMOVE_TRACK,
                target_id=selected_track_id,
            ),
            error_title="Delete timeline track failed",
            label="Deleted timeline track",
            sync_stage=True,
        )

    def _timeline_move_track(self, track_id: str, delta: int) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_track_id = str(track_id)
        amount = int(delta)
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.MOVE_TRACK,
                target_id=selected_track_id,
                amount=amount,
            ),
            error_title="Reorder timeline track failed",
            sync_stage=True,
        )

    def _timeline_mute_track(self, track_id: str, muted: bool) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_track_id = str(track_id)
        payload = {"muted": bool(muted)}
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.SET_TRACK_PROPERTIES,
                target_id=selected_track_id,
                values=payload,
                coalesce=True,
            ),
            error_title="Edit timeline track failed",
            label="Edited timeline track",
            sync_stage=True,
        )

    def _timeline_add_clip(self, track_id: str) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_track_id = str(track_id)
        start_frame = int(self.timeline.playhead_frame)
        track = find_timeline_track(
            session.document,
            selected_track_id,
            session.editor_state.selection.state_id,
        )
        label = (
            f"Added {track.kind} clip at frame {start_frame}"
            if track is not None
            else ""
        )
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.ADD_CLIP,
                target_id=selected_track_id,
                frame=start_frame,
            ),
            error_title="Add timeline clip failed",
            label=label,
            sync_stage=True,
        )

    def _timeline_add_keyframe(self, clip_id: str, playhead_frame: int) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_clip_id = str(clip_id)
        frame = int(playhead_frame)
        found = find_timeline_clip(session.document, selected_clip_id)
        if found is None:
            return
        clip = found[1]
        relative = max(0, frame - clip.start_frame)
        local = min(
            clip.duration_frames,
            relative % clip.duration_frames if clip.loop_count > 1 else relative,
        )
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.ADD_KEYFRAME,
                target_id=selected_clip_id,
                frame=frame,
            ),
            error_title="Add timeline keyframe failed",
            label=f"Added keyframe at local frame {local}",
            sync_stage=True,
        )

    def _timeline_delete_keyframe(self, clip_id: str, playhead_frame: int) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_clip_id = str(clip_id)
        frame = int(playhead_frame)
        snap_distance = int(self.timeline.snap_spin.value())
        found = find_timeline_clip(session.document, selected_clip_id)
        if found is None or not found[1].keyframes:
            return
        clip = found[1]
        relative = max(0, frame - clip.start_frame)
        local = min(
            clip.duration_frames,
            relative % clip.duration_frames if clip.loop_count > 1 else relative,
        )
        nearest = min(clip.keyframes, key=lambda item: abs(item.frame - local))
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.REMOVE_KEYFRAME,
                target_id=selected_clip_id,
                frame=frame,
                amount=snap_distance,
            ),
            error_title="Delete timeline keyframe failed",
            label=f"Deleted keyframe at local frame {nearest.frame}",
            sync_stage=True,
        )

    def _timeline_keyframe_geometry(
        self,
        clip_id: str,
        keyframe_id: str,
        frame: int,
    ) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_clip_id = str(clip_id)
        selected_keyframe_id = str(keyframe_id)
        payload = {"frame": int(frame)}
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.SET_KEYFRAME_PROPERTIES,
                target_id=selected_clip_id,
                related_id=selected_keyframe_id,
                values=payload,
                coalesce=True,
            ),
            error_title="Edit timeline keyframe failed",
            label="Edited timeline keyframe",
            sync_stage=True,
        )

    def _timeline_clip_geometry(
        self,
        clip_id: str,
        start_frame: int,
        duration_frames: int,
    ) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_clip_id = str(clip_id)
        start = int(start_frame)
        duration = int(duration_frames)
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.MOVE_CLIP,
                target_id=selected_clip_id,
                frame=start,
                amount=duration,
                coalesce=True,
            ),
            error_title="Move timeline clip failed",
            label=f"Moved timeline clip to frame {start}",
            sync_stage=True,
        )

    def _timeline_duplicate_clip(self, clip_id: str) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_clip_id = str(clip_id)
        found = find_timeline_clip(session.document, selected_clip_id)
        if found is None:
            return
        label = f"Duplicated {found[1].name}"
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.DUPLICATE_CLIP,
                target_id=selected_clip_id,
            ),
            error_title="Duplicate timeline clip failed",
            label=label,
            sync_stage=True,
        )

    def _timeline_delete_clip(self, clip_id: str) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_clip_id = str(clip_id)
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.REMOVE_CLIP,
                target_id=selected_clip_id,
            ),
            error_title="Delete timeline clip failed",
            label="Deleted timeline clip",
            sync_stage=True,
        )

    def _timeline_clip_selected(self, track_id: str, clip_id: str) -> None:
        if getattr(self, "_timeline_selection_dispatching", False):
            return
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_track_id = str(track_id)
        selected_clip_id = str(clip_id)
        selection = session.editor_state.selection
        if (
            selection.track_id == selected_track_id
            and selection.clip_id == selected_clip_id
        ):
            return
        self._timeline_selection_dispatching = True
        try:
            self._dispatch_timeline_intent(
                TimelineIntent(
                    document_id,
                    TimelineAction.SELECT_CLIP,
                    target_id=selected_track_id,
                    related_id=selected_clip_id,
                ),
                error_title=None,
                defer_invalidation=True,
                refresh_inspector=True,
            )
        finally:
            self._timeline_selection_dispatching = False

    def _timeline_clip_properties_requested(
        self,
        clip_id: str,
        values: dict[str, object],
    ) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_clip_id = str(clip_id)
        payload = dict(values)
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.SET_CLIP_PROPERTIES,
                target_id=selected_clip_id,
                values=payload,
                coalesce=True,
            ),
            error_title="Edit timeline clip failed",
            label="Edited timeline clip",
            sync_stage=True,
        )

    def _timeline_keyframe_properties_requested(
        self,
        clip_id: str,
        keyframe_id: str,
        values: dict[str, object],
    ) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        selected_clip_id = str(clip_id)
        selected_keyframe_id = str(keyframe_id)
        payload = dict(values)
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.SET_KEYFRAME_PROPERTIES,
                target_id=selected_clip_id,
                related_id=selected_keyframe_id,
                values=payload,
                coalesce=True,
            ),
            error_title="Edit timeline keyframe failed",
            label="Edited timeline keyframe",
            sync_stage=True,
        )

    def _timeline_playhead_changed(self, frame: int) -> None:
        session = self.document_manager.active
        if session is None:
            return
        document_id = session.document.id
        playhead_frame = int(frame)
        if not self._dispatch_timeline_intent(
            SetTimelinePlayheadIntent(document_id, playhead_frame),
            error_title=None,
            defer_invalidation=True,
        ):
            return
        if (
            self._pattern_preview_client.is_running
            and session is self._active_stage_session
            and isinstance(session.document, SceneDocument)
            and self._preview_mode == "stage"
            and self._preview_loaded_resource_id == document_id
        ):
            self._pattern_preview_client.send_command(
                "seek",
                {"frame": playhead_frame},
            )

    def _timeline_zoom_changed(self, value: float) -> None:
        session = self.document_manager.active
        if session is None or not isinstance(session.document, SceneDocument):
            return
        document_id = session.document.id
        zoom = float(value)
        self._dispatch_timeline_intent(
            TimelineIntent(
                document_id,
                TimelineAction.SET_ZOOM,
                values={"zoom": zoom},
            ),
            error_title=None,
            defer_invalidation=True,
        )


__all__ = ["TimelineService"]

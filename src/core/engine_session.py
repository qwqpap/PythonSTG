"""Explicit ownership boundary for one gameplay runtime session."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .project_context import ProjectContext


@dataclass
class EngineSession:
    """Owns resources created for one playable or preview session.

    The window and global audio backend may survive a restart, so they are not
    implicitly destroyed here.  Session-scoped objects are finalized in the
    same order as the historical ``main.py`` cleanup block.
    """

    project: ProjectContext
    emoji_system: Any
    audio_manager: Any
    renderer: Any
    item_renderer: Any
    ui_renderer: Any
    dialog_renderer: Any
    loading_renderer: Any
    pause_renderer: Any
    continue_renderer: Any
    staff_roll_renderer: Any
    spell_declaration_renderer: Any
    texture_assets: Any
    background_renderer: Any = None
    _closed: bool = field(default=False, init=False, repr=False)
    _cleanup_errors: list[str] = field(default_factory=list, init=False, repr=False)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def cleanup_errors(self) -> tuple[str, ...]:
        return tuple(self._cleanup_errors)

    def _call(self, label: str, callback: Callable[[], Any]) -> None:
        try:
            callback()
        except Exception as exc:
            self._cleanup_errors.append(f"{label}: {exc}")

    def close(self) -> tuple[str, ...]:
        if self._closed:
            return self.cleanup_errors
        self._closed = True

        self._call("emoji.stop", self.emoji_system.stop)
        self._call("audio.stop_bgm", lambda: self.audio_manager.stop_bgm(fade_ms=0))
        self._call("audio.clear_stage_bank", lambda: self.audio_manager.set_stage_bank(None))

        cleanup_targets = (
            ("renderer", self.renderer),
            ("item_renderer", self.item_renderer),
            ("ui_renderer", self.ui_renderer),
            ("dialog_renderer", self.dialog_renderer),
            ("loading_renderer", self.loading_renderer),
            ("pause_renderer", self.pause_renderer),
            ("continue_renderer", self.continue_renderer),
            ("staff_roll_renderer", self.staff_roll_renderer),
            ("spell_declaration_renderer", self.spell_declaration_renderer),
            ("background_renderer", self.background_renderer),
        )
        for label, target in cleanup_targets:
            if target is not None and hasattr(target, "cleanup"):
                self._call(f"{label}.cleanup", target.cleanup)

        if hasattr(self.texture_assets, "clear_all"):
            self._call("texture_assets.clear_all", self.texture_assets.clear_all)

        return self.cleanup_errors

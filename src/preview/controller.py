"""Editor-controllable Pattern/Stage execution through the formal runtime."""

from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from src.authoring import ResourceReference, ResourceStore
from src.core.project_context import ProjectContext
from src.editor.document import DocumentError, SceneDocument
from src.editor.stage_compile import StageCompileError
from src.game.stage.context import StageContext
from src.game.stage.program import (
    StageProgram,
    StageRunner,
    StageRuntimeError,
)
from src.pattern import (
    PatternCompileError,
    PatternCompiler,
    PatternDocument,
    PatternDocumentError,
    PatternProgram,
    PatternRunner,
    PatternRuntimeError,
)


FIXED_DT = 1.0 / 60.0


class PreviewState(str, Enum):
    UNLOADED = "unloaded"
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"


class PreviewCommandError(RuntimeError):
    """An actionable command failure that does not crash the preview service."""

    def __init__(self, command: str, message: str, *, path: str = ""):
        self.command = command
        self.path = path
        self.detail = message
        prefix = f"{path}: " if path else ""
        super().__init__(f"{command}: {prefix}{message}")


@dataclass(frozen=True)
class PreviewEvent:
    sequence: int
    event: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event": self.event,
            "payload": copy.deepcopy(self.payload),
        }


class PreviewPlayer:
    def __init__(self, x: float = 0.0, y: float = -0.8) -> None:
        self.pos = [float(x), float(y)]

    @property
    def x(self) -> float:
        return self.pos[0]

    @property
    def y(self) -> float:
        return self.pos[1]

    def move_to(self, x: float, y: float) -> None:
        x = float(x)
        y = float(y)
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("player position must be finite")
        self.pos[:] = (x, y)


class PatternPreviewController:
    """Own one formal PatternRunner or StageRunner and expose editor commands.

    Candidate documents are parsed and compiled before the active runner is
    replaced. Invalid hot reloads therefore retain the last runnable program,
    current bullets, play state, and frame.
    """

    COMMANDS = frozenset(
        {
            "load",
            "play",
            "pause",
            "step",
            "seek",
            "reset",
            "stop",
            "set-property",
            "set-player-position",
            "set-seed",
            "set-gizmos",
            "get-stats",
        }
    )

    def __init__(
        self,
        bullet_pool,
        *,
        project: ProjectContext,
        player_position: tuple[float, float] = (0.0, -0.8),
        compiler: PatternCompiler | None = None,
        sprite_index_resolver=None,
        audio_manager: Any | None = None,
    ) -> None:
        self.bullet_pool = bullet_pool
        self.project = project
        self.store = ResourceStore(project)
        self.player = PreviewPlayer(*player_position)
        self.context = StageContext(
            bullet_pool=bullet_pool,
            player=self.player,
            audio_manager=audio_manager,
        )
        self.compiler = compiler or PatternCompiler()
        self.sprite_index_resolver = sprite_index_resolver
        self.document: PatternDocument | SceneDocument | None = None
        self.program: PatternProgram | StageProgram | None = None
        self.runner: PatternRunner | StageRunner | None = None
        self.resource_path: Path | None = None
        self.state = PreviewState.UNLOADED
        self.frame = 0
        self.show_gizmos = True
        self.last_error: dict[str, Any] | None = None
        self.last_update_ms = 0.0
        self.last_render_ms = 0.0
        self._events: list[PreviewEvent] = []
        self._sequence = 0
        self._closed = False
        self.last_compatibility_decision: dict[str, Any] = {"policy": "initial"}
        self.reload_history: list[dict[str, Any]] = []

    @property
    def mode(self) -> str:
        if isinstance(self.program, StageProgram):
            return "stage"
        if isinstance(self.program, PatternProgram):
            return "pattern"
        return "unloaded"

    def _emit(self, event: str, **payload: Any) -> PreviewEvent:
        self._sequence += 1
        item = PreviewEvent(self._sequence, event, dict(payload))
        self._events.append(item)
        return item

    def drain_events(self) -> tuple[PreviewEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    def _status(self, message: str) -> None:
        self._emit(
            "status",
            state=self.state.value,
            message=message,
            frame=self.frame,
            paused=self.state != PreviewState.PLAYING,
            mode=self.mode,
            resource_id=self.program.resource_id if self.program is not None else None,
        )

    def _emit_statistics(self) -> None:
        """Publish one complete formal-runtime snapshot to editor clients."""

        self._emit("statistics", **self.get_stats(emit=False))

    def _require_loaded(self, command: str) -> None:
        if self.runner is None or self.program is None or self.document is None:
            raise PreviewCommandError(command, "no authoring document is loaded")

    def _resolve_document_source(
        self, source: Any
    ) -> tuple[PatternDocument | SceneDocument, Path | None]:
        if isinstance(source, PatternDocument):
            return PatternDocument.from_dict(source.to_dict()), None
        if isinstance(source, SceneDocument):
            return SceneDocument.from_dict(source.to_canonical_dict(), canonical=True), None
        if isinstance(source, Mapping):
            resource_type = str(source.get("type") or "")
            if resource_type == "pystg.pattern":
                return PatternDocument.from_dict(source), None
            if resource_type == "pystg.scene":
                return SceneDocument.from_dict(dict(source), canonical=True), None
            raise DocumentError(
                f"load.resource: unsupported authoring resource type {resource_type!r}"
            )
        if not isinstance(source, (str, Path)):
            raise DocumentError("load: document must be an object or resource path")

        text = str(source)
        if text.startswith("res://"):
            reference = ResourceReference.parse(text)
            if reference.subresource is not None:
                raise DocumentError("load.resource: authoring document paths cannot use fragments")
            path = reference.resolve(self.project, must_exist=True)
        else:
            path = self.project.resolve(Path(text))
            self.project.relative(path)
        loaded = self.store.load(path)
        if not isinstance(loaded, (PatternDocument, SceneDocument)):
            raise DocumentError(
                "load.resource: resource is not a supported Pattern or Scene document"
            )
        return loaded, path

    @staticmethod
    def _diagnostics(
        error: PatternCompileError | StageCompileError,
    ) -> list[dict[str, Any]]:
        return [
            {
                "severity": item.severity,
                "code": item.code,
                "resource_id": item.resource_id,
                "path": item.path,
                "message": item.message,
                **(
                    {
                        "track_id": item.track_id,
                        "clip_id": item.clip_id,
                        "node_id": item.node_id,
                        "referenced_path": item.referenced_path,
                    }
                    if isinstance(error, StageCompileError)
                    else {}
                ),
            }
            for item in error.diagnostics
        ]

    def _compile_candidate(
        self, document: PatternDocument | SceneDocument
    ) -> PatternProgram | StageProgram:
        if isinstance(document, PatternDocument):
            return self.compiler.compile(
                document,
                project=self.project,
                sprite_index_resolver=self.sprite_index_resolver,
            )
        contribution = self.store.registry[document.type].compiler
        if contribution is None:
            raise DocumentError(
                f"No compiler is registered for resource type {document.type!r}"
            )
        return contribution(
            document,
            project=self.project,
            sprite_index_resolver=self.sprite_index_resolver,
        )

    def _record_compile_failure(self, error: BaseException, *, command: str) -> None:
        preserved = self.program is not None
        if isinstance(error, (PatternCompileError, StageCompileError)):
            diagnostics = self._diagnostics(error)
        elif isinstance(error, PatternDocumentError):
            diagnostics = [
                {
                    "severity": "error",
                    "code": "invalid_document",
                    "resource_id": self.document.id if self.document else "",
                    "path": error.path,
                    "message": error.detail,
                }
            ]
        else:
            diagnostics = [
                {
                    "severity": "error",
                    "code": "load_failed",
                    "resource_id": self.document.id if self.document else "",
                    "path": "load",
                    "message": str(error),
                }
            ]
        self.last_error = {
            "kind": "compile",
            "command": command,
            "diagnostics": diagnostics,
            "active_program_preserved": preserved,
        }
        self._emit("compile_error", **self.last_error)

    def _replace_program(
        self,
        document: PatternDocument | SceneDocument,
        program: PatternProgram | StageProgram,
        *,
        resource_path: Path | None,
        resume: bool,
        message: str,
    ) -> None:
        old_runner = self.runner
        old_snapshot = None
        old_specs = None
        if isinstance(old_runner, StageRunner):
            old_snapshot = old_runner.variable_snapshot
            old_specs = old_runner.program.variable_specs
        if old_runner is not None:
            old_runner.stop(self.context, clear_owned=True)
        self.document = document
        self.program = program
        self.runner = (
            StageRunner(program)
            if isinstance(program, StageProgram)
            else PatternRunner(program)
        )
        self.resource_path = resource_path
        self.frame = 0
        self.last_error = None
        self.last_update_ms = 0.0
        self.state = PreviewState.PLAYING if resume else PreviewState.PAUSED
        if resume:
            self.runner.start(self.context)
        if isinstance(self.runner, StageRunner) and old_snapshot is not None:
            decision = self.runner.variables.restore_compatible_snapshot(old_snapshot, old_specs)
            self.runner.compatibility_decision = decision
            self.runner.replay_identity["compatibility"] = decision
        else:
            decision = {"policy": "initial" if old_runner is None else "reset", "restored": [], "discarded": []}
            if isinstance(self.runner, StageRunner):
                self.runner.compatibility_decision = decision
                self.runner.replay_identity["compatibility"] = decision
        self.last_compatibility_decision = copy.deepcopy(decision)
        self.reload_history.append({
            "old_program_hash": old_runner.program.content_hash if old_runner is not None else None,
            "new_program_hash": program.content_hash,
            "decision": copy.deepcopy(decision),
        })
        self._emit(
            "program_loaded",
            resource_id=program.resource_id,
            content_hash=program.content_hash,
            name=program.name,
            seed=program.seed if isinstance(program, PatternProgram) else None,
            mode=self.mode,
            duration_frames=(
                program.duration_frames if isinstance(program, StageProgram) else None
            ),
            resource_path=str(resource_path) if resource_path else None,
            compatibility=copy.deepcopy(decision),
            replay_identity=copy.deepcopy(getattr(self.runner, "replay_identity", {})),
        )
        self._status(message)

    def load(self, source: Any) -> dict[str, Any]:
        self._ensure_open("load")
        was_playing = self.state == PreviewState.PLAYING
        try:
            document, resource_path = self._resolve_document_source(source)
            program = self._compile_candidate(document)
        except Exception as exc:
            self._record_compile_failure(exc, command="load")
            raise PreviewCommandError("load", str(exc)) from exc
        self._replace_program(
            document,
            program,
            resource_path=resource_path,
            resume=was_playing,
            message=f"Loaded {document.name}",
        )
        return {
            "resource_id": program.resource_id,
            "content_hash": program.content_hash,
            "mode": self.mode,
        }

    def play(self) -> None:
        self._ensure_open("play")
        self._require_loaded("play")
        assert self.runner is not None
        if self.state == PreviewState.PLAYING:
            self._status("Already playing")
            return
        if self.runner.state.value in {"stopped", "finished", "error"}:
            if self.runner.state.value != "stopped" or self.frame != 0:
                self.runner.reset(self.context)
                self.frame = 0
            self.runner.start(self.context, reset=False)
        else:
            self.runner.resume()
        self.state = PreviewState.PLAYING
        self._status("Playing")
        self._emit_statistics()

    def pause(self) -> None:
        self._ensure_open("pause")
        self._require_loaded("pause")
        assert self.runner is not None
        self.runner.pause()
        self.state = PreviewState.PAUSED
        self._status("Paused")
        self._emit_statistics()

    def _advance_one(self, *, dispatch_actions: bool = True) -> None:
        assert self.runner is not None
        start = time.perf_counter()
        try:
            if self.runner.state.value == "paused":
                self.runner.resume()
            if self.runner.state.value == "stopped":
                self.runner.start(self.context, reset=False)
            if self.runner.state.value == "running":
                if isinstance(self.runner, StageRunner):
                    self.runner.tick(
                        self.context,
                        dispatch_actions=dispatch_actions,
                    )
                    self.frame = self.runner.frame
                    dt = 1.0 / self.runner.program.tick_rate
                else:
                    self.runner.tick(self.context)
                    self.frame += 1
                    dt = FIXED_DT
                self.bullet_pool.update(dt)
        except Exception as exc:
            if isinstance(exc, (PatternRuntimeError, StageRuntimeError)):
                detail = exc.detail
                resource_id = exc.resource_id
                path = exc.path
            else:
                detail = str(exc)
                resource_id = self.program.resource_id if self.program else ""
                path = "runtime"
            self.last_error = {
                "kind": "runtime",
                "resource_id": resource_id,
                "frame": self.frame,
                "path": path,
                "message": detail,
            }
            self.state = PreviewState.ERROR
            self._emit("runtime_error", **self.last_error)
            raise
        finally:
            self.last_update_ms = (time.perf_counter() - start) * 1000.0

    def update(self) -> None:
        if self._closed or self.state != PreviewState.PLAYING:
            return
        self._advance_one()
        assert self.runner is not None
        if self.runner.state.value == "finished":
            self.state = PreviewState.PAUSED
            self._status(
                "Stage finished" if isinstance(self.runner, StageRunner) else "Pattern finished"
            )
        # Stage authoring surfaces consume this event as the authoritative
        # playhead/runtime snapshot.  Emitting it after every fixed tick keeps
        # the Qt timeline and runtime poses in lockstep with the formal runner;
        # the external renderer remains the only owner of bullet rendering.
        self._emit_statistics()

    def step(self) -> None:
        self._ensure_open("step")
        self._require_loaded("step")
        assert self.runner is not None
        if self.runner.state.value in {"finished", "error"}:
            self.runner.reset(self.context)
            self.frame = 0
        self._advance_one()
        self.runner.pause()
        self.state = PreviewState.PAUSED
        self._status("Stepped one frame")
        self._emit_statistics()

    def seek(self, frame: int) -> None:
        self._ensure_open("seek")
        self._require_loaded("seek")
        if isinstance(frame, bool) or not isinstance(frame, int) or not 0 <= frame <= 1_000_000:
            raise PreviewCommandError("seek", "frame must be an integer in 0..1000000", path="frame")
        if isinstance(self.program, StageProgram) and frame > self.program.duration_frames:
            raise PreviewCommandError(
                "seek",
                f"frame must not exceed stage duration {self.program.duration_frames}",
                path="frame",
            )
        assert self.runner is not None
        start = time.perf_counter()
        self.runner.reset(self.context)
        self.frame = 0
        if isinstance(self.runner, StageRunner):
            self.runner.start(
                self.context,
                reset=False,
                dispatch_actions=False,
            )
        else:
            self.runner.start(self.context, reset=False)
        try:
            for _ in range(frame):
                self._advance_one(dispatch_actions=False)
        except Exception:
            raise
        finally:
            self.last_update_ms = (time.perf_counter() - start) * 1000.0
        if isinstance(self.runner, StageRunner):
            self.runner.restore_audio_state(self.context)
        self.runner.pause()
        self.state = PreviewState.PAUSED
        self._status(f"Seeked to frame {frame}")
        self._emit_statistics()

    def reset(self) -> None:
        self._ensure_open("reset")
        self._require_loaded("reset")
        assert self.runner is not None
        self.runner.reset(self.context)
        self.frame = 0
        self.state = PreviewState.PAUSED
        self.last_error = None
        self._status("Reset to frame 0")
        self._emit_statistics()

    def stop(self) -> None:
        if self._closed:
            return
        if self.runner is not None:
            self.runner.stop(self.context)
        self.frame = 0
        self.state = PreviewState.STOPPED if self.program is not None else PreviewState.UNLOADED
        self._status("Stopped")
        self._emit_statistics()

    def _candidate_with_property(self, path: str, value: Any) -> PatternDocument:
        self._require_loaded("set-property")
        if not isinstance(self.document, PatternDocument):
            raise PreviewCommandError(
                "set-property",
                "live property reload is only available for PatternDocument; edit Scene tracks through the editor",
                path="path",
            )
        if not isinstance(path, str) or not path.strip():
            raise PreviewCommandError("set-property", "path must be non-empty", path="path")
        payload = self.document.to_dict()
        parts = path.split(".")
        if any(not part or part.startswith("_") for part in parts):
            raise PreviewCommandError("set-property", "invalid property path", path=path)
        target: Any = payload
        for part in parts[:-1]:
            if not isinstance(target, dict) or part not in target:
                raise PreviewCommandError("set-property", "unknown property path", path=path)
            target = target[part]
        leaf = parts[-1]
        if not isinstance(target, dict) or leaf not in target:
            raise PreviewCommandError("set-property", "unknown property path", path=path)
        if path in {"schema_version", "type", "id"}:
            raise PreviewCommandError("set-property", "identity/version fields are immutable", path=path)
        target[leaf] = value
        return PatternDocument.from_dict(payload)

    def set_property(self, path: str, value: Any) -> None:
        self._ensure_open("set-property")
        was_playing = self.state == PreviewState.PLAYING
        try:
            candidate = self._candidate_with_property(path, value)
            program = self._compile_candidate(candidate)
        except Exception as exc:
            self._record_compile_failure(exc, command="set-property")
            if isinstance(exc, PreviewCommandError):
                raise
            raise PreviewCommandError("set-property", str(exc), path=path) from exc
        self._replace_program(
            candidate,
            program,
            resource_path=self.resource_path,
            resume=was_playing,
            message=f"Reloaded {path}",
        )

    def set_player_position(self, x: float, y: float) -> None:
        self._ensure_open("set-player-position")
        self.player.move_to(x, y)
        self._emit("player_position", x=self.player.x, y=self.player.y)
        self._status("Player position updated")

    def set_seed(self, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise PreviewCommandError("set-seed", "seed must be an integer", path="seed")
        if not isinstance(self.document, PatternDocument):
            raise PreviewCommandError(
                "set-seed",
                "seed override is only available for PatternDocument previews",
                path="seed",
            )
        self.set_property("seed", seed)

    def set_gizmos(self, visible: bool) -> None:
        self.show_gizmos = bool(visible)
        self._emit("gizmos", visible=self.show_gizmos)

    def record_render_ms(self, render_ms: float) -> None:
        value = float(render_ms)
        if math.isfinite(value) and value >= 0:
            self.last_render_ms = value

    def emitter_positions(self) -> tuple[tuple[float, float], ...]:
        if isinstance(self.runner, StageRunner):
            values = []
            seen = set()
            for schedule in self.runner.program.patterns:
                target_id = schedule.position_target_id
                if target_id in seen:
                    continue
                seen.add(target_id)
                state = self.runner.node_state.get(target_id or "", {})
                values.append(
                    (
                        float(state.get("x", schedule.base_origin[0])),
                        float(state.get("y", schedule.base_origin[1])),
                    )
                )
            return tuple(values)
        if isinstance(self.program, PatternProgram):
            return (self.program.origin,)
        return ()

    def get_stats(self, *, emit: bool = True) -> dict[str, Any]:
        bullet_count = int(np.count_nonzero(self.bullet_pool.data["alive"]))
        stage_runner = self.runner if isinstance(self.runner, StageRunner) else None
        payload = {
            "mode": self.mode,
            "resource_id": self.program.resource_id if self.program is not None else None,
            "state": self.state.value,
            "frame": self.frame,
            "bullet_count": bullet_count,
            "max_bullets": int(self.bullet_pool.max_bullets),
            "seed": self.document.seed if isinstance(self.document, PatternDocument) else None,
            "duration_frames": (
                self.program.duration_frames
                if isinstance(self.program, StageProgram)
                else None
            ),
            "active_clips": (
                list(stage_runner.active_clip_ids) if stage_runner is not None else []
            ),
            "state_path": (
                list(stage_runner.current_state_path) if stage_runner is not None else []
            ),
            "state_path_names": (
                list(stage_runner.current_state_names) if stage_runner is not None else []
            ),
            "node_state": (
                copy.deepcopy(stage_runner.node_state) if stage_runner is not None else {}
            ),
            "variable_snapshot": (
                copy.deepcopy(stage_runner.variable_snapshot)
                if stage_runner is not None
                else {}
            ),
            "timeline_events": (
                list(self.context.timeline_events())[-20:]
                if stage_runner is not None
                else []
            ),
            "trace_events": len(stage_runner.trace) if stage_runner is not None else 0,
            "reactive_instances": (
                [dict(item) for item in stage_runner.active_reactive_instances]
                if stage_runner is not None
                else []
            ),
            "reactive_trace": (
                [item.to_dict() for item in stage_runner.reactive_trace[-50:]]
                if stage_runner is not None
                else []
            ),
            "reactive_overlay": (
                copy.deepcopy(stage_runner.reactive_overlay)
                if stage_runner is not None
                else {"active_instances": [], "trace": [], "diagnostics": []}
            ),
            "paused": self.state != PreviewState.PLAYING,
            "update_ms": round(self.last_update_ms, 6),
            "render_ms": round(self.last_render_ms, 6),
            "reload_ok": self.last_error is None,
            "last_error": copy.deepcopy(self.last_error),
            "program_hash": self.program.content_hash if self.program else None,
            "player_position": [self.player.x, self.player.y],
            "gizmos": self.show_gizmos,
            "compatibility_decision": copy.deepcopy(self.last_compatibility_decision),
            "replay_identity": copy.deepcopy(getattr(self.runner, "replay_identity", {})),
            "reload_history": copy.deepcopy(self.reload_history[-10:]),
        }
        if emit:
            self._emit("statistics", **payload)
        return payload

    def execute(self, command: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_open(command)
        if command not in self.COMMANDS:
            raise PreviewCommandError(command, "unknown preview command")
        data = dict(payload or {})
        if command == "load":
            source = data.get("document", data.get("resource"))
            if source is None:
                raise PreviewCommandError("load", "document or resource is required")
            return self.load(source)
        if command == "play":
            self.play()
        elif command == "pause":
            self.pause()
        elif command == "step":
            self.step()
        elif command == "seek":
            self.seek(data.get("frame"))
        elif command == "reset":
            self.reset()
        elif command == "stop":
            self.stop()
        elif command == "set-property":
            self.set_property(data.get("path"), data.get("value"))
        elif command == "set-player-position":
            self.set_player_position(data.get("x"), data.get("y"))
        elif command == "set-seed":
            self.set_seed(data.get("seed"))
        elif command == "set-gizmos":
            self.set_gizmos(data.get("visible", True))
        elif command == "get-stats":
            return self.get_stats()
        return self.get_stats(emit=False)

    def _ensure_open(self, command: str) -> None:
        if self._closed:
            raise PreviewCommandError(command, "preview controller is closed")

    def close(self) -> None:
        if self._closed:
            return
        if self.runner is not None:
            self.runner.stop(self.context)
        self.bullet_pool.clear_all()
        self.frame = 0
        self.state = PreviewState.STOPPED
        self._closed = True
        self._status("Closed")

from __future__ import annotations

import importlib.util
import json
import random
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Type

import numpy as np

from src.game.stage.context import StageContext
from src.game.stage.spellcard import NonSpell, SpellCard


FIXED_DT = 1.0 / 60.0
PREVIEW_CONFIG_SUFFIX = ".preview.json"


@dataclass(frozen=True)
class PreviewErrorInfo:
    title: str
    message: str
    file: str | None = None
    line: int | None = None
    traceback_text: str = ""
    keeps_old_instance: bool = False


class SpellPreviewError(RuntimeError):
    """Raised when a spell preview script or config cannot be loaded safely."""

    def __init__(self, message: str, *, info: PreviewErrorInfo | None = None):
        super().__init__(message)
        self.info = info


@dataclass(frozen=True)
class PreviewConfig:
    spell: str | None = None
    boss: str = "test_boss"
    boss_pos: tuple[float, float] = (0.0, 0.55)
    player_pos: tuple[float, float] = (0.0, -0.8)
    seed: int | None = None
    speed: float = 1.0
    hitbox: bool = False
    auto_reload: bool = True
    duration: int | None = None


@dataclass(frozen=True)
class SpellPreviewTarget:
    script_path: Path
    spell_class: Type[SpellCard]
    module: ModuleType


@dataclass(frozen=True)
class PreviewLoadResult:
    target: SpellPreviewTarget
    config: PreviewConfig
    config_path: Path | None


@dataclass(frozen=True)
class PreviewStats:
    frame: int
    duration: int | None
    bullet_count: int
    max_bullets: int
    seed: int | None
    speed: float
    paused: bool
    update_ms: float
    render_ms: float
    reload_ok: bool


class PreviewPlayer:
    def __init__(self, x: float = 0.0, y: float = -0.8):
        self.pos = [float(x), float(y)]

    @property
    def x(self) -> float:
        return self.pos[0]

    @property
    def y(self) -> float:
        return self.pos[1]

    def move_to(self, x: float, y: float) -> None:
        self.pos[0] = float(x)
        self.pos[1] = float(y)


class PreviewBoss:
    def __init__(self, name: str = "preview_boss", x: float = 0.0, y: float = 0.55):
        self.id = name
        self.name = name
        self.max_hp = 999999
        self.hp = self.max_hp
        self.pos = [float(x), float(y)]

    @property
    def x(self) -> float:
        return self.pos[0]

    @x.setter
    def x(self, value: float) -> None:
        self.pos[0] = float(value)

    @property
    def y(self) -> float:
        return self.pos[1]

    @y.setter
    def y(self, value: float) -> None:
        self.pos[1] = float(value)

    async def move_to(self, x: float, y: float, duration: int = 0) -> None:
        self.x = x
        self.y = y

    async def wait(self, frames: int) -> None:
        return None


def parse_vec2(value: str | list[Any] | tuple[Any, ...]) -> tuple[float, float]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        raise ValueError(f"expected x,y pair, got {value!r}")

    if len(parts) != 2 or any(part == "" for part in parts):
        raise ValueError(f"expected two comma-separated numbers, got {value!r}")
    try:
        return float(parts[0]), float(parts[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"expected two comma-separated numbers, got {value!r}") from exc


def preview_config_path_for(script_path: Path | str) -> Path:
    return Path(script_path).with_suffix(PREVIEW_CONFIG_SUFFIX)


def preview(**metadata):
    """Attach preview metadata to a SpellCard class."""

    patch = normalize_preview_config_patch(metadata, source="@preview")

    def decorator(cls):
        if not isinstance(cls, type) or not issubclass(cls, SpellCard):
            raise TypeError("@preview can only decorate SpellCard classes")
        existing = get_spell_preview_patch(cls)
        cls.preview = {**existing, **patch}
        return cls

    return decorator


def normalize_preview_config_patch(data: dict[str, Any], *, source: str = "preview config") -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SpellPreviewError(f"{source} must be a JSON object / dict")

    aliases = {
        "class": "spell",
        "spell_name": "spell",
        "playerPos": "player_pos",
        "bossPos": "boss_pos",
        "autoReload": "auto_reload",
    }
    allowed = {
        "spell", "boss", "boss_pos", "player_pos", "seed",
        "speed", "hitbox", "auto_reload", "duration",
    }
    patch: dict[str, Any] = {}
    for raw_key, value in data.items():
        key = aliases.get(raw_key, raw_key)
        if key not in allowed:
            raise SpellPreviewError(f"unknown preview config key {raw_key!r} in {source}")
        if value is None:
            patch[key] = None
        elif key in {"spell", "boss"}:
            patch[key] = str(value)
        elif key in {"boss_pos", "player_pos"}:
            patch[key] = parse_vec2(value)
        elif key == "seed":
            patch[key] = int(value)
        elif key == "speed":
            speed = float(value)
            if speed <= 0:
                raise SpellPreviewError(f"speed must be greater than 0 in {source}")
            patch[key] = speed
        elif key in {"hitbox", "auto_reload"}:
            patch[key] = _coerce_bool(value, key, source)
        elif key == "duration":
            duration = int(value)
            if duration <= 0:
                raise SpellPreviewError(f"duration must be greater than 0 in {source}")
            patch[key] = duration
    return patch


def load_preview_config_patch(
    script_path: Path | str,
    *,
    config_path: Path | str | None = None,
    use_config: bool = True,
) -> tuple[dict[str, Any], Path | None]:
    if not use_config:
        return {}, None

    path = Path(config_path).resolve() if config_path else preview_config_path_for(script_path).resolve()
    if not path.exists():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return normalize_preview_config_patch(data, source=str(path)), path
    except json.JSONDecodeError as exc:
        info = PreviewErrorInfo(
            title="Config load failed",
            message=f"JSONDecodeError: {exc.msg}",
            file=str(path),
            line=exc.lineno,
        )
        raise SpellPreviewError(f"failed to parse preview config {path}: {exc}", info=info) from exc
    except SpellPreviewError as exc:
        if exc.info is None:
            info = PreviewErrorInfo(
                title="Config load failed",
                message=str(exc),
                file=str(path),
            )
            raise SpellPreviewError(str(exc), info=info) from exc
        raise
    except Exception as exc:
        info = build_preview_error_info(exc, script_path=path, title="Config load failed")
        raise SpellPreviewError(f"failed to load preview config {path}: {exc}", info=info) from exc


def get_spell_preview_patch(spell_class: Type[SpellCard]) -> dict[str, Any]:
    metadata = getattr(spell_class, "preview", None)
    if metadata is None:
        metadata = getattr(spell_class, "_preview_config", None)
    if metadata is None:
        return {}
    return normalize_preview_config_patch(metadata, source=f"{spell_class.__name__}.preview")


def resolve_preview_load(
    script_path: Path | str,
    *,
    requested_spell: str | None = None,
    config_path: Path | str | None = None,
    config_overrides: dict[str, Any] | None = None,
    use_config: bool = True,
) -> PreviewLoadResult:
    file_patch, loaded_config_path = load_preview_config_patch(
        script_path,
        config_path=config_path,
        use_config=use_config,
    )
    selected_spell = requested_spell or file_patch.get("spell")
    target = load_spell_target(script_path, selected_spell)
    class_patch = get_spell_preview_patch(target.spell_class)

    merged: dict[str, Any] = {
        "spell": target.spell_class.__name__,
        "boss": "test_boss",
        "boss_pos": (0.0, 0.55),
        "player_pos": (0.0, -0.8),
        "seed": None,
        "speed": 1.0,
        "hitbox": False,
        "auto_reload": True,
        "duration": None,
    }
    merged.update(class_patch)
    merged.update(file_patch)
    if config_overrides:
        merged.update(normalize_preview_config_patch(config_overrides, source="CLI overrides"))
    if requested_spell:
        merged["spell"] = requested_spell
    if not merged.get("spell"):
        merged["spell"] = target.spell_class.__name__

    return PreviewLoadResult(
        target=target,
        config=PreviewConfig(**merged),
        config_path=loaded_config_path,
    )


def build_preview_error_info(
    exc: BaseException,
    *,
    script_path: Path | str | None = None,
    title: str = "Preview error",
    keeps_old_instance: bool = False,
) -> PreviewErrorInfo:
    if isinstance(exc, SpellPreviewError) and exc.info is not None:
        info = exc.info
        return PreviewErrorInfo(
            title=title or info.title,
            message=info.message,
            file=info.file,
            line=info.line,
            traceback_text=info.traceback_text,
            keeps_old_instance=keeps_old_instance or info.keeps_old_instance,
        )

    cause = exc.__cause__ if isinstance(exc, SpellPreviewError) and exc.__cause__ is not None else exc
    target_path = Path(script_path).resolve() if script_path else None
    file_name: str | None = None
    line: int | None = None

    if isinstance(cause, SyntaxError):
        file_name = cause.filename
        line = cause.lineno
    elif cause.__traceback__ is not None:
        frames = traceback.extract_tb(cause.__traceback__)
        selected = None
        if target_path is not None:
            for frame in frames:
                try:
                    if Path(frame.filename).resolve() == target_path:
                        selected = frame
                except OSError:
                    continue
        if selected is None and frames:
            selected = frames[-1]
        if selected is not None:
            file_name = selected.filename
            line = selected.lineno

    message = f"{type(cause).__name__}: {cause}"
    trace = "".join(traceback.format_exception(type(cause), cause, cause.__traceback__))
    return PreviewErrorInfo(
        title=title,
        message=message,
        file=file_name,
        line=line,
        traceback_text=trace,
        keeps_old_instance=keeps_old_instance,
    )


def _coerce_bool(value: Any, key: str, source: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise SpellPreviewError(f"{key} must be a boolean in {source}")


def _module_name_for(path: Path) -> str:
    stamp = time.monotonic_ns()
    return f"_pystg_preview_{abs(hash(path.resolve()))}_{stamp}"


def _load_module(path: Path) -> ModuleType:
    resolved = path.resolve()
    if not resolved.exists():
        raise SpellPreviewError(f"script not found: {resolved}")
    if not resolved.is_file():
        raise SpellPreviewError(f"script path is not a file: {resolved}")

    importlib.invalidate_caches()
    module_name = _module_name_for(resolved)
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise SpellPreviewError(f"cannot import script: {resolved}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        info = build_preview_error_info(exc, script_path=resolved, title="Reload failed")
        raise SpellPreviewError(f"failed to import {resolved}: {exc}", info=info) from exc
    return module


def _is_local_spell_class(module: ModuleType, value: object) -> bool:
    if not isinstance(value, type):
        return False
    if value in (SpellCard, NonSpell):
        return False
    if not issubclass(value, SpellCard):
        return False
    return value.__module__ == module.__name__


def _has_preview_metadata(spell_class: Type[SpellCard]) -> bool:
    return hasattr(spell_class, "preview") or hasattr(spell_class, "_preview_config")


def load_spell_target(script_path: Path | str, class_name: str | None = None) -> SpellPreviewTarget:
    path = Path(script_path).resolve()
    module = _load_module(path)

    if class_name:
        candidate = getattr(module, class_name, None)
        if candidate is None:
            raise SpellPreviewError(f"class {class_name!r} not found in {path}")
        if not _is_local_spell_class(module, candidate):
            raise SpellPreviewError(f"{class_name!r} is not a SpellCard class defined in {path}")
        return SpellPreviewTarget(path, candidate, module)

    spells = [
        value for value in vars(module).values()
        if _is_local_spell_class(module, value)
    ]
    if not spells:
        raise SpellPreviewError(f"no SpellCard class found in {path}; pass --spell or a class name")
    if len(spells) == 1:
        return SpellPreviewTarget(path, spells[0], module)

    spells_with_preview = [cls for cls in spells if _has_preview_metadata(cls)]
    if len(spells_with_preview) == 1:
        return SpellPreviewTarget(path, spells_with_preview[0], module)

    names = ", ".join(cls.__name__ for cls in spells)
    raise SpellPreviewError(f"multiple SpellCard classes found ({names}); pass --spell or add preview metadata")


class SpellPreviewSession:
    def __init__(
        self,
        bullet_pool,
        *,
        player_pos: tuple[float, float] = (0.0, -0.8),
        boss_name: str = "preview_boss",
        boss_pos: tuple[float, float] = (0.0, 0.55),
        seed: int | None = None,
    ):
        self.bullet_pool = bullet_pool
        self.player = PreviewPlayer(*player_pos)
        self.boss = PreviewBoss(boss_name, *boss_pos)
        self.stage_context = StageContext(bullet_pool=bullet_pool, player=self.player)
        self.seed = seed
        self.spell: SpellCard | None = None
        self.spell_class: Type[SpellCard] | None = None
        self.frame = 0

    def configure(
        self,
        *,
        player_pos: tuple[float, float],
        boss_name: str,
        boss_pos: tuple[float, float],
        seed: int | None,
    ) -> None:
        self.player.move_to(*player_pos)
        self.boss.id = boss_name
        self.boss.name = boss_name
        self.boss.x, self.boss.y = boss_pos
        self.seed = seed

    def restart(self, spell_class: Type[SpellCard] | None = None) -> None:
        target_class = spell_class or self.spell_class
        if target_class is None:
            raise SpellPreviewError("no SpellCard class loaded")

        if self.seed is not None:
            random.seed(self.seed)
            np.random.seed(self.seed % (2 ** 32))

        next_spell = target_class()
        next_spell.bind(self.boss, self.stage_context)
        next_spell.start()

        self.close()
        self.clear_bullets()
        self.spell_class = target_class
        self.spell = next_spell
        self.frame = 0

    def close(self) -> None:
        coroutine = getattr(self.spell, "_coroutine", None)
        if coroutine is not None and hasattr(coroutine, "close"):
            coroutine.close()
        self.spell = None

    def clear_bullets(self) -> None:
        self.bullet_pool.clear_all()
        if hasattr(self.stage_context, "_bullet_indices"):
            self.stage_context._bullet_indices.clear()

    def step_one(self) -> bool:
        if self.spell is None:
            return False
        active = self.spell.update()
        self.bullet_pool.update(FIXED_DT)
        self.frame += 1
        return active

    @property
    def bullet_count(self) -> int:
        return int(np.count_nonzero(self.bullet_pool.data["alive"]))


class SpellPreviewRuntime:
    def __init__(self, bullet_pool, *, config_path: Path | str | None = None, use_config: bool = True):
        self.bullet_pool = bullet_pool
        self.session = SpellPreviewSession(bullet_pool)
        self.target: SpellPreviewTarget | None = None
        self.config = PreviewConfig()
        self.script_path: Path | None = None
        self.config_file_path: Path | None = None
        self.requested_spell: str | None = None
        self._config_overrides: dict[str, Any] = {}
        self._config_path_arg = Path(config_path).resolve() if config_path else None
        self._use_config = use_config
        self.paused = False
        self.speed = 1.0
        self.show_hitbox = False
        self.auto_reload = True
        self.duration: int | None = None
        self.error_info: PreviewErrorInfo | None = None
        self.status = ""
        self.last_update_ms = 0.0
        self.last_render_ms = 0.0
        self._sim_accumulator = 0.0

    def load(
        self,
        file_path: Path | str,
        spell_name: str | None = None,
        *,
        config_overrides: dict[str, Any] | None = None,
        is_reload: bool = False,
    ) -> PreviewLoadResult:
        script_path = Path(file_path).resolve()
        overrides = config_overrides if config_overrides is not None else self._config_overrides
        try:
            result = resolve_preview_load(
                script_path,
                requested_spell=spell_name,
                config_path=self._config_path_arg,
                config_overrides=overrides,
                use_config=self._use_config,
            )
        except Exception as exc:
            self.error_info = build_preview_error_info(
                exc,
                script_path=script_path,
                title="Reload failed" if is_reload else "Load failed",
                keeps_old_instance=is_reload and self.target is not None,
            )
            raise

        self.session.configure(
            player_pos=result.config.player_pos,
            boss_name=result.config.boss,
            boss_pos=result.config.boss_pos,
            seed=result.config.seed,
        )
        self.session.restart(result.target.spell_class)
        self._sim_accumulator = 0.0
        self.script_path = script_path
        self.requested_spell = spell_name
        self._config_overrides = dict(overrides)
        self.target = result.target
        self.config = result.config
        self.config_file_path = result.config_path
        self.speed = result.config.speed
        self.show_hitbox = result.config.hitbox
        self.auto_reload = result.config.auto_reload
        self.duration = result.config.duration
        self.error_info = None
        self.status = f"Reloaded {result.target.spell_class.__name__}" if is_reload else f"Loaded {result.target.spell_class.__name__}"
        return result

    def reload(self) -> PreviewLoadResult:
        if self.script_path is None:
            raise SpellPreviewError("no preview file loaded")
        return self.load(
            self.script_path,
            self.requested_spell,
            config_overrides=self._config_overrides,
            is_reload=True,
        )

    def reset(self) -> None:
        if self.target is None:
            raise SpellPreviewError("no preview target loaded")
        self.session.restart(self.target.spell_class)
        self._sim_accumulator = 0.0

    def pause(self, value: bool) -> None:
        self.paused = bool(value)
        self.status = "Paused" if self.paused else "Running"

    def step(self) -> None:
        self.paused = True
        start = time.perf_counter()
        try:
            self.session.step_one()
        except Exception as exc:
            self._record_runtime_error(exc)
            raise
        finally:
            self.last_update_ms = (time.perf_counter() - start) * 1000.0
        self.status = "Stepped one frame"

    def update(self) -> None:
        if self.paused:
            self.last_update_ms = 0.0
            return

        start = time.perf_counter()
        try:
            self._sim_accumulator += self.speed
            while self._sim_accumulator >= 1.0:
                active = self.session.step_one()
                self._sim_accumulator -= 1.0
                if not active:
                    self.paused = True
                    self._sim_accumulator = 0.0
                    self.status = f"Spell ended at frame {self.session.frame}"
                    break
        except Exception as exc:
            self._record_runtime_error(exc)
            raise
        finally:
            self.last_update_ms = (time.perf_counter() - start) * 1000.0

    def seek(self, frame: int) -> None:
        target_frame = max(0, int(frame))
        was_paused = self.paused
        start = time.perf_counter()
        try:
            self.reset()
            for _ in range(target_frame):
                self.session.step_one()
        except Exception as exc:
            self._record_runtime_error(exc)
            raise
        finally:
            self.last_update_ms = (time.perf_counter() - start) * 1000.0
            self.paused = was_paused
        self.status = f"Seeked to frame {self.session.frame}"

    def set_speed(self, speed: float) -> None:
        speed = float(speed)
        if speed <= 0:
            raise ValueError("speed must be greater than 0")
        self.speed = speed
        self.status = f"Speed set to {speed:g}x"

    def clear_bullets(self) -> None:
        self.session.clear_bullets()
        self.status = "Cleared bullets"

    def set_player_pos(self, x: float, y: float) -> None:
        self.session.player.move_to(x, y)

    def set_seed(self, seed: int | None) -> None:
        self.session.seed = seed
        self.config = PreviewConfig(
            spell=self.config.spell,
            boss=self.config.boss,
            boss_pos=self.config.boss_pos,
            player_pos=self.config.player_pos,
            seed=seed,
            speed=self.config.speed,
            hitbox=self.config.hitbox,
            auto_reload=self.config.auto_reload,
            duration=self.config.duration,
        )

    def get_stats(self) -> PreviewStats:
        duration = self.duration
        if duration is None and self.session.spell is not None:
            duration = int(getattr(self.session.spell, "time_limit", 0) * 60) or None
        return PreviewStats(
            frame=self.session.frame,
            duration=duration,
            bullet_count=self.session.bullet_count,
            max_bullets=self.bullet_pool.max_bullets,
            seed=self.session.seed,
            speed=self.speed,
            paused=self.paused,
            update_ms=self.last_update_ms,
            render_ms=self.last_render_ms,
            reload_ok=self.error_info is None,
        )

    def close(self) -> None:
        self.session.close()

    def _record_runtime_error(self, exc: BaseException) -> None:
        self.error_info = build_preview_error_info(
            exc,
            script_path=self.script_path,
            title="Runtime error",
            keeps_old_instance=False,
        )
        self.paused = True
        self.status = "Preview paused after runtime error"


class SpellFileWatcher:
    def __init__(self, path: Path | str, *, enabled: bool = True):
        self.path = Path(path).resolve()
        self.enabled = enabled
        self._snapshot = self._read_snapshot()
        self._changed = False
        self._observer = None

        if enabled:
            self._start_watchdog()

    @property
    def backend(self) -> str:
        return "watchdog" if self._observer is not None else "polling"

    def _read_snapshot(self) -> tuple[int, int]:
        stat = self.path.stat()
        return stat.st_mtime_ns, stat.st_size

    def _start_watchdog(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except Exception:
            return

        watched_path = self.path
        owner = self

        class Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if Path(event.src_path).resolve() == watched_path:
                    owner._changed = True

            def on_created(self, event):
                if Path(event.src_path).resolve() == watched_path:
                    owner._changed = True

            def on_moved(self, event):
                if Path(event.dest_path).resolve() == watched_path:
                    owner._changed = True

        observer = Observer()
        observer.schedule(Handler(), str(watched_path.parent), recursive=False)
        observer.start()
        self._observer = observer

    def poll(self) -> bool:
        if not self.enabled:
            return False

        changed = self._changed
        try:
            snapshot = self._read_snapshot()
        except FileNotFoundError:
            return False

        if snapshot != self._snapshot:
            changed = True
            self._snapshot = snapshot

        if changed:
            self._changed = False
            return True
        return False

    def close(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=1.0)
        self._observer = None

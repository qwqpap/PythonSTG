"""PatternDocument to immutable PatternProgram compilation."""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.core.project_context import ProjectContext

from .document import PatternDocument, PatternDocumentError
from .ir import BurstTemplate, PatternProgram


SpriteIndexResolver = Callable[[str], int]
MAX_COMPILED_BULLETS = 1_000_000


@dataclass(frozen=True)
class PatternDiagnostic:
    severity: str
    code: str
    resource_id: str
    path: str
    message: str


class PatternCompileError(ValueError):
    def __init__(self, diagnostics: tuple[PatternDiagnostic, ...]):
        self.diagnostics = diagnostics
        message = "; ".join(
            f"{item.path}: {item.message}" for item in diagnostics
        )
        super().__init__(message or "pattern compilation failed")


def _clean(value: float, digits: int = 6) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == 0 else rounded


def _diagnostic(
    document: PatternDocument,
    code: str,
    path: str,
    message: str,
) -> PatternDiagnostic:
    return PatternDiagnostic(
        severity="error",
        code=code,
        resource_id=document.id,
        path=path,
        message=message,
    )


def _shape_values(
    document: PatternDocument,
    burst_index: int,
) -> BurstTemplate:
    shape = document.shape
    motion = document.motion
    modifiers = document.modifiers
    count = shape.count
    burst_angle = modifiers.angle_offset_per_burst * burst_index
    base_speed = motion.speed + modifiers.speed_offset_per_burst * burst_index
    if base_speed < 0:
        raise PatternDocumentError(
            "modifiers.speed_offset_per_burst",
            f"produces negative speed at burst {burst_index}",
        )

    positions = [(0.0, 0.0)] * count
    speed_factors = [1.0] * count

    if shape.kind == "ring":
        angles = [burst_angle + index * 360.0 / count for index in range(count)]
    elif shape.kind == "arc":
        if abs(shape.angle_span) >= 360.0:
            start = 0.0
            step = shape.angle_span / count
        else:
            start = -shape.angle_span / 2.0
            step = 0.0 if count == 1 else shape.angle_span / (count - 1)
        angles = [burst_angle + start + index * step for index in range(count)]
    elif shape.kind == "spiral":
        step = shape.angle_span / max(1, count)
        angles = [burst_angle + index * step for index in range(count)]
        speed_factors = [
            0.65 + 0.55 * (index / max(1, count - 1))
            for index in range(count)
        ]
    elif shape.kind == "flower":
        angles = [burst_angle + index * 360.0 / count for index in range(count)]
        speed_factors = [
            0.55
            + 0.45
            * abs(math.sin(math.radians(index * shape.angle_span)))
            for index in range(count)
        ]
    elif shape.kind == "line":
        angles = [burst_angle] * count
        direction = math.radians(shape.line_angle)
        for index in range(count):
            t = 0.0 if count == 1 else index / (count - 1) - 0.5
            distance = t * shape.line_length
            positions[index] = (
                math.cos(direction) * distance,
                math.sin(direction) * distance,
            )
    elif shape.kind == "random":
        seed = document.seed + burst_index * 0x9E3779B97F4A7C15
        rng = random.Random(seed & 0x7FFF_FFFF_FFFF_FFFF)
        if abs(shape.angle_span) >= 360.0:
            low, high = sorted((0.0, shape.angle_span))
        else:
            low, high = sorted((-shape.angle_span / 2.0, shape.angle_span / 2.0))
        angles = [burst_angle + rng.uniform(low, high) for _ in range(count)]
        variation = modifiers.random_speed_variation
        speed_factors = [
            rng.uniform(1.0 - variation, 1.0 + variation)
            for _ in range(count)
        ]
    else:  # PatternDocument validation makes this unreachable.
        raise PatternDocumentError("shape.kind", f"unsupported shape {shape.kind!r}")

    return BurstTemplate(
        position_offsets=tuple(
            (_clean(x), _clean(y)) for x, y in positions
        ),
        angle_offsets=tuple(_clean(value) for value in angles),
        speeds=tuple(_clean(base_speed * factor) for factor in speed_factors),
    )


class PatternCompiler:
    """Compiler with content/dependency keyed in-memory caching."""

    def __init__(self) -> None:
        self._cache: dict[str, PatternProgram] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def compile(
        self,
        document: PatternDocument,
        *,
        project: ProjectContext | None = None,
        sprite_index_resolver: SpriteIndexResolver | None = None,
    ) -> PatternProgram:
        try:
            document.validate()
        except PatternDocumentError as exc:
            raise PatternCompileError(
                (_diagnostic(document, "invalid_document", exc.path, exc.detail),)
            ) from exc

        sprite_id, dependency_token = self._resolve_sprite(document, project)
        sprite_index = -1
        if sprite_index_resolver is not None and sprite_id:
            try:
                sprite_index = int(sprite_index_resolver(sprite_id))
            except Exception as exc:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "sprite_resolution_failed",
                            "bullet.resource",
                            str(exc),
                        ),
                    )
                ) from exc

        canonical = json.dumps(
            document.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        identity = "\0".join(
            (
                document.id,
                str(document.schema_version),
                canonical,
                dependency_token,
                str(sprite_index),
            )
        )
        content_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        cached = self._cache.get(content_hash)
        if cached is not None:
            return cached

        compiled_bullets = document.shape.count * document.schedule.burst_count
        if compiled_bullets > MAX_COMPILED_BULLETS:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "program_too_large",
                        "schedule.burst_count",
                        f"would precompute {compiled_bullets} bullets; "
                        f"the v1 limit is {MAX_COMPILED_BULLETS}",
                    ),
                )
            )

        try:
            templates = tuple(
                _shape_values(document, burst_index)
                for burst_index in range(document.schedule.burst_count)
            )
        except PatternDocumentError as exc:
            raise PatternCompileError(
                (_diagnostic(document, "invalid_program", exc.path, exc.detail),)
            ) from exc

        program = PatternProgram(
            resource_id=document.id,
            schema_version=document.schema_version,
            content_hash=content_hash,
            name=document.name,
            seed=document.seed,
            origin=(document.shape.origin_x, document.shape.origin_y),
            aim_mode=document.aim.mode,
            aim_angle=document.aim.angle,
            delay_frames=document.schedule.delay_frames,
            interval_frames=document.schedule.interval_frames,
            burst_count=document.schedule.burst_count,
            loop_count=document.schedule.loop_count,
            bullet_type=document.bullet.bullet_type,
            color=document.bullet.color,
            resource_uri=document.bullet.resource,
            sprite_id=sprite_id,
            sprite_index=sprite_index,
            friction=document.motion.friction,
            spin=document.motion.spin,
            time_scale=document.motion.time_scale,
            max_lifetime=document.motion.max_lifetime,
            render_scale=document.motion.render_scale,
            bounce_x=document.motion.bounce_x,
            bounce_y=document.motion.bounce_y,
            templates=templates,
        )
        self._cache[content_hash] = program
        return program

    def _resolve_sprite(
        self,
        document: PatternDocument,
        project: ProjectContext | None,
    ) -> tuple[str, str]:
        resource = document.bullet.resource
        if resource is not None:
            try:
                reference = ResourceReference.parse(resource)
            except ResourceDocumentError as exc:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "invalid_resource_reference",
                            "bullet.resource",
                            str(exc),
                        ),
                    )
                ) from exc
            if project is None:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "project_required",
                            "bullet.resource",
                            "a ProjectContext is required to resolve this resource",
                        ),
                    )
                )
            try:
                path = reference.resolve(project, must_exist=True)
            except ResourceDocumentError as exc:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "missing_resource",
                            "bullet.resource",
                            str(exc),
                        ),
                    )
                ) from exc
            if reference.subresource is None:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "missing_sprite_fragment",
                            "bullet.resource",
                            "a sprite resource must include a #fragment",
                        ),
                    )
                )
            try:
                source_bytes = path.read_bytes()
                payload = json.loads(source_bytes.decode("utf-8-sig"))
            except (OSError, UnicodeError, ValueError) as exc:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "invalid_sprite_resource",
                            "bullet.resource",
                            f"cannot read sprite resource: {exc}",
                        ),
                    )
                ) from exc
            sprites = payload.get("sprites") if isinstance(payload, dict) else None
            if not isinstance(sprites, dict) or reference.subresource not in sprites:
                raise PatternCompileError(
                    (
                        _diagnostic(
                            document,
                            "missing_sprite_subresource",
                            "bullet.resource",
                            f"sprite fragment {reference.subresource!r} was not found",
                        ),
                    )
                )
            dependency_hash = hashlib.sha256(source_bytes).hexdigest()
            return reference.subresource, f"{reference.uri}:{dependency_hash}"

        if project is None:
            return "", "alias:runtime"
        aliases = project.root / "assets" / "bullet_aliases.json"
        try:
            source_bytes = aliases.read_bytes()
            payload = json.loads(source_bytes.decode("utf-8-sig"))
            mapping = payload["mapping"]
            if not isinstance(mapping, dict):
                raise TypeError("mapping must be an object")
            type_mapping = mapping[document.bullet.bullet_type]
            if not isinstance(type_mapping, dict):
                raise TypeError("bullet type mapping must be an object")
            sprite_id = type_mapping[document.bullet.color]
            if not isinstance(sprite_id, str) or not sprite_id.strip():
                raise TypeError("sprite id must be a non-empty string")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise PatternCompileError(
                (
                    _diagnostic(
                        document,
                        "unknown_bullet_alias",
                        "bullet",
                        "cannot resolve "
                        f"{document.bullet.bullet_type}/{document.bullet.color}: {exc}",
                    ),
                )
            ) from exc
        dependency_hash = hashlib.sha256(source_bytes).hexdigest()
        return sprite_id, f"aliases:{dependency_hash}"


_DEFAULT_COMPILER = PatternCompiler()


def compile_pattern(
    document: PatternDocument,
    *,
    project: ProjectContext | None = None,
    sprite_index_resolver: SpriteIndexResolver | None = None,
) -> PatternProgram:
    return _DEFAULT_COMPILER.compile(
        document,
        project=project,
        sprite_index_resolver=sprite_index_resolver,
    )

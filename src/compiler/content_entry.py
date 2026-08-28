"""Strict loading of handwritten and generated game-content entries."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from types import MappingProxyType, ModuleType
from typing import Mapping

from src.game.stage.stage_base import StageScript

from .diagnostics import CompilerError


@dataclass(frozen=True)
class ContentRegistry:
    """An immutable, validated view of the fixed content-entry interface."""

    module_name: str
    stages: tuple[type[StageScript], ...]
    start_stage: type[StageScript]
    stage_by_id: Mapping[str, type[StageScript]]

    def get_stage(self, stage_id: str | None = None) -> type[StageScript]:
        if stage_id is None:
            return self.start_stage
        try:
            return self.stage_by_id[stage_id]
        except KeyError as exc:
            raise KeyError(f"unknown stage id: {stage_id}") from exc


def load_content_entry(module_or_name: str | ModuleType) -> ContentRegistry:
    """Import and validate the exact ``entry.py`` public contract."""

    if isinstance(module_or_name, str):
        module_name = module_or_name
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise CompilerError(
                "entry_import_failed",
                f"failed to import content entry {module_name!r}: {type(exc).__name__}: {exc}",
            ) from exc
    elif isinstance(module_or_name, ModuleType):
        module = module_or_name
        module_name = module.__name__
    else:
        raise CompilerError(
            "invalid_content_entry",
            "content entry must be a module name or module object",
        )

    stages_value = _required_attribute(module, module_name, "STAGES")
    if not isinstance(stages_value, tuple) or not stages_value:
        raise CompilerError(
            "invalid_content_entry",
            f"{module_name}.STAGES must be a non-empty tuple",
        )

    stages: list[type[StageScript]] = []
    seen_ids: set[str] = set()
    for index, stage_class in enumerate(stages_value):
        if (
            not inspect.isclass(stage_class)
            or stage_class is StageScript
            or not issubclass(stage_class, StageScript)
        ):
            raise CompilerError(
                "invalid_content_entry",
                f"{module_name}.STAGES[{index}] must be a concrete StageScript subclass",
            )
        stage_id = getattr(stage_class, "id", None)
        if not isinstance(stage_id, str) or not stage_id:
            raise CompilerError(
                "invalid_content_entry",
                f"stage {stage_class.__name__} must define a non-empty string id",
            )
        if stage_id in seen_ids:
            raise CompilerError(
                "entry_duplicate_stage",
                f"duplicate stage id {stage_id!r} in {module_name}.STAGES",
            )
        seen_ids.add(stage_id)
        stages.append(stage_class)

    start_stage = _required_attribute(module, module_name, "START_STAGE")
    if start_stage not in stages:
        raise CompilerError(
            "entry_start_stage",
            f"{module_name}.START_STAGE must be one of STAGES",
        )

    mapping_value = _required_attribute(module, module_name, "STAGE_BY_ID")
    if not isinstance(mapping_value, Mapping):
        raise CompilerError(
            "invalid_content_entry",
            f"{module_name}.STAGE_BY_ID must be a mapping",
        )
    expected = {stage.id: stage for stage in stages}
    actual = dict(mapping_value)
    if actual != expected:
        raise CompilerError(
            "entry_stage_mapping",
            f"{module_name}.STAGE_BY_ID must exactly map every STAGES id",
        )

    get_stage = _required_attribute(module, module_name, "get_stage")
    if not callable(get_stage):
        raise CompilerError(
            "invalid_content_entry",
            f"{module_name}.get_stage must be callable",
        )
    try:
        if get_stage() is not start_stage:
            raise ValueError("get_stage() did not return START_STAGE")
        for stage_id, stage_class in expected.items():
            if get_stage(stage_id) is not stage_class:
                raise ValueError(f"get_stage({stage_id!r}) returned the wrong class")
        try:
            get_stage("__pystg_missing_stage__")
        except KeyError:
            pass
        else:
            raise ValueError("get_stage() must raise KeyError for an unknown id")
    except Exception as exc:
        raise CompilerError(
            "entry_get_stage",
            f"{module_name}.get_stage violates the fixed interface: {exc}",
        ) from exc

    return ContentRegistry(
        module_name=module_name,
        stages=tuple(stages),
        start_stage=start_stage,
        stage_by_id=MappingProxyType(expected),
    )


def _required_attribute(module: ModuleType, module_name: str, name: str):
    if not hasattr(module, name):
        raise CompilerError(
            "invalid_content_entry",
            f"{module_name} is missing {name!r}",
        )
    return getattr(module, name)


__all__ = ["ContentRegistry", "load_content_entry"]

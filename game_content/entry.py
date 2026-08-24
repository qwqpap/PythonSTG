"""Default handwritten content entry for the shipped PySTG stages."""

from __future__ import annotations

from src.game.stage.stage_base import StageScript

from game_content.stages.stage1.stage_script import Stage1
from game_content.stages.stage2.stage_script import Stage2
from game_content.stages.stage3.stage_script import Stage3


STAGES: tuple[type[StageScript], ...] = (Stage1, Stage2, Stage3)
START_STAGE: type[StageScript] = Stage1
STAGE_BY_ID: dict[str, type[StageScript]] = {
    stage.id: stage for stage in STAGES
}


def get_stage(stage_id: str | None = None) -> type[StageScript]:
    """Return the requested handwritten stage, or the default start stage."""

    if stage_id is None:
        return START_STAGE
    try:
        return STAGE_BY_ID[stage_id]
    except KeyError as exc:
        raise KeyError(f"unknown stage id: {stage_id}") from exc


__all__ = ["STAGES", "START_STAGE", "STAGE_BY_ID", "get_stage"]

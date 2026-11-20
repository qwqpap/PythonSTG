"""Normal handwritten content registry; no assets are distributed here."""

from .stage import TH07Stage6
from .resources import install_resources


STAGES = (TH07Stage6,)
START_STAGE = TH07Stage6
STAGE_BY_ID = {stage.id: stage for stage in STAGES}


def get_stage(stage_id=None):
    if stage_id is None:
        return START_STAGE
    return STAGE_BY_ID[stage_id]


def prepare_resources():
    """Install local CPU catalogs before the existing GPU texture upload."""
    return install_resources()

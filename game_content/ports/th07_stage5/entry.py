from .stage import TH07Stage5
from .resources import install_resources

STAGES = (TH07Stage5,)
START_STAGE = TH07Stage5
STAGE_BY_ID = {stage.id: stage for stage in STAGES}


def get_stage(stage_id=None):
    return START_STAGE if stage_id is None else STAGE_BY_ID[stage_id]


def prepare_resources():
    return install_resources()

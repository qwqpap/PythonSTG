import asyncio

from game_content.stages.stage1.stage_script import Stage1


class _FailingContext:
    def play_se(self, *args, **kwargs):
        raise AssertionError("opening sound effect should be disabled")


def test_stage1_opening_media_is_disabled_for_editor_development():
    stage = Stage1.__new__(Stage1)
    stage.ctx = _FailingContext()

    async def fail_sequence(*args, **kwargs):
        raise AssertionError("opening image sequence should be disabled")

    stage.play_image_sequence = fail_sequence
    asyncio.run(stage._play_opening_media())

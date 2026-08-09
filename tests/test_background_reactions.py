"""Background changes are resource actions owned by reactions, not renderer listeners."""

from src.game.events import Event
from src.game.reactions import BackgroundTransition, ReactionScheduler, ReactionSpec


class RecordingBackgroundContext:
    def __init__(self):
        self.requests = []

    def request_background_transition(self, resource, *, owner=None, fade_frames=0):
        self.requests.append(
            {
                "resource": resource,
                "owner": owner,
                "fade_frames": fade_frames,
            }
        )
        return True


def test_boss_defeat_switches_background_through_resource_reference():
    context = RecordingBackgroundContext()
    scheduler = ReactionScheduler()
    scheduler.register(
        ReactionSpec(
            "defeat-background",
            "boss.defeated",
            BackgroundTransition("res://backgrounds/enrage.pystg.json", fade_frames=18),
            once_per_scope=True,
        )
    )
    event = Event("boss.defeated", "boss", 12, {"boss_id": "real"})

    scheduler.process([event], 12, context=context)
    scheduler.tick(12)

    assert len(context.requests) == 1
    assert context.requests[0]["resource"] == "res://backgrounds/enrage.pystg.json"
    assert context.requests[0]["owner"].startswith("defeat-background@stage#")
    assert context.requests[0]["fade_frames"] == 18
    assert all(item.kind != "error" for item in scheduler.trace)


def test_background_transition_without_context_api_is_a_structured_failure():
    scheduler = ReactionScheduler()
    scheduler.register(
        ReactionSpec(
            "broken-background",
            "boss.defeated",
            BackgroundTransition("res://missing.json"),
        )
    )

    scheduler.process([Event("boss.defeated", "boss", 0, {})], 0, context=object())
    scheduler.tick(0)

    assert scheduler.diagnostics
    assert scheduler.diagnostics[-1]["kind"] == "reaction_action_error"

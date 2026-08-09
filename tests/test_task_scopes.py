"""Structured task ownership, waiting, completion, and cancellation."""

from src.game.reactions import TaskScope, TaskScopeState, TaskWait


def test_task_scope_waits_in_fixed_frames_and_records_completion():
    scope = TaskScope("spell:opening")
    observed = []

    def task():
        observed.append("start")
        yield TaskWait(2)
        observed.append("after-wait")

    task_id = scope.start(task, task_id="opening", frame=0)
    assert task_id == "opening"
    scope.tick(0)
    assert observed == ["start"]
    scope.tick(1)
    assert observed == ["start"]
    scope.tick(2)
    assert observed == ["start", "after-wait"]
    scope.tick(3)

    assert scope.state == TaskScopeState.COMPLETED
    assert scope.pending_tasks == 0
    assert [item.kind for item in scope.trace] == [
        "task_start",
        "task_complete",
        "scope_complete",
    ]


def test_parent_cancellation_propagates_to_children_and_closes_generator():
    parent = TaskScope("state:old")
    child = TaskScope("reaction:old", parent=parent)
    closed = []

    def task():
        try:
            yield TaskWait(20)
        finally:
            closed.append("closed")

    child.start(task, frame=0)
    child.tick(0)
    parent.cancel("state_exit", frame=4)

    assert parent.state == TaskScopeState.CANCELLED
    assert child.state == TaskScopeState.CANCELLED
    assert child.cancel_token.cancelled is True
    assert child.cancel_token.reason == "state_exit"
    assert closed == ["closed"]
    assert any(item.kind == "scope_cancel" and item.reason == "state_exit" for item in child.trace)


def test_completed_scope_does_not_accept_new_work():
    scope = TaskScope("one-shot")
    scope.complete(frame=3)

    assert scope.start(lambda: None, frame=4) is None
    assert scope.state == TaskScopeState.COMPLETED

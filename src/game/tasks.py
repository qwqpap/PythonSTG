"""Small cooperative tasks driven only by the gameplay frame clock.

Tasks are for sparse controllers (stages, actors, reactions), not bullets.
No wall clock, threads or asyncio event loop participates in their execution.
"""

from __future__ import annotations

import types
from typing import Any


FRAME_RATE = 60
FRAME_DT = 1.0 / FRAME_RATE


@types.coroutine
def wait_frames(frames: int):
    """Suspend for the same number of gameplay updates as existing wait()."""
    for _ in range(max(0, int(frames))):
        yield


class TaskCancelled(RuntimeError):
    """The task was cancelled before producing a result."""


class TaskHandle:
    """One coroutine owned by a frame task group."""

    __slots__ = (
        "_group", "_iterator", "_done", "_cancelled", "_result", "_error",
        "_last_frame", "_eligible_frame", "_running", "_cancel_requested",
    )

    def __init__(self, group, coroutine):
        self._group = group
        self._iterator = (
            coroutine.__await__() if hasattr(coroutine, "__await__") else iter(coroutine)
        )
        self._done = False
        self._cancelled = False
        self._result = None
        self._error = None
        self._last_frame = None
        self._eligible_frame = int(getattr(group.owner, "time", 0))
        self._running = False
        self._cancel_requested = False

    @property
    def done(self) -> bool:
        return self._done

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def result(self) -> Any:
        if not self._done:
            raise RuntimeError("task has not completed")
        if self._cancelled:
            raise TaskCancelled("task was cancelled")
        if self._error is not None:
            raise self._error
        return self._result

    def cancel(self) -> None:
        if self._done:
            return
        self._cancel_requested = True
        if not self._running:
            self._close()

    def _close(self) -> None:
        try:
            self._iterator.close()
        finally:
            self._done = True
            self._cancelled = True

    def _step(self, frame: int) -> None:
        if self._done or self._last_frame == frame or frame < self._eligible_frame:
            return
        self._last_frame = frame
        self._running = True
        try:
            self._iterator.send(None)
        except StopIteration as stop:
            self._done = True
            self._result = stop.value
        except BaseException as error:
            self._done = True
            self._error = error
            raise
        finally:
            self._running = False
            if self._cancel_requested and not self._done:
                self._close()

    @types.coroutine
    def join(self):
        """Await completion without advancing this task from its waiter."""
        while not self._done:
            yield
        return self.result()

    def __await__(self):
        return (yield from self.join())


class FrameTaskGroup:
    """A bounded task list; each handle advances at most once per owner frame."""

    __slots__ = (
        "owner", "_tasks", "_pumping", "_closed", "limit", "_revision",
        "_last_pump_frame", "_last_pump_revision",
    )

    def __init__(self, owner, *, limit: int = 256):
        self.owner = owner
        self._tasks = []
        self._pumping = False
        self._closed = False
        self.limit = limit
        self._revision = 0
        self._last_pump_frame = None
        self._last_pump_revision = -1

    @property
    def pending(self) -> int:
        return sum(not task.done for task in self._tasks)

    def spawn(self, coroutine, *, immediate: bool = False) -> TaskHandle:
        if self._closed:
            if hasattr(coroutine, "close"):
                coroutine.close()
            raise RuntimeError("cannot spawn into a disposed task owner")
        if len(self._tasks) >= self.limit:
            self._tasks = [task for task in self._tasks if not task.done]
            if len(self._tasks) >= self.limit:
                if hasattr(coroutine, "close"):
                    coroutine.close()
                raise RuntimeError(f"frame task limit exceeded ({self.limit})")
        handle = TaskHandle(self, coroutine)
        if self._pumping and not immediate:
            handle._eligible_frame += 1
        self._tasks.append(handle)
        self._revision += 1
        if immediate:
            try:
                handle._step(int(getattr(self.owner, "time", 0)))
            except BaseException:
                self.cancel()
                raise
        return handle

    def pump(self) -> None:
        if self._closed or self._pumping or not self._tasks:
            return
        frame = int(getattr(self.owner, "time", 0))
        if self._last_pump_frame == frame and self._last_pump_revision == self._revision:
            return
        self._last_pump_frame = frame
        self._last_pump_revision = self._revision
        self._pumping = True
        # Snapshot length, not the list: tasks created by a running task wait
        # for the next update, and the common path makes no list copy.
        tasks = self._tasks
        count = len(tasks)
        try:
            for index in range(count):
                tasks[index]._step(frame)
        except BaseException:
            self.cancel()
            raise
        finally:
            self._pumping = False
            self._tasks = [task for task in self._tasks if not task.done]

    def cancel(self, *, close: bool = False) -> None:
        if close:
            self._closed = True
        # A finally block may itself cancel/spawn, so detach the list first.
        tasks, self._tasks = self._tasks, []
        self._revision += 1
        first_error = None
        for task in tasks:
            try:
                task.cancel()
            except BaseException as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error


def task_group(owner) -> FrameTaskGroup:
    group = getattr(owner, "_frame_tasks", None)
    if group is None:
        group = FrameTaskGroup(owner)
        owner._frame_tasks = group
    return group


def spawn_task(owner, coroutine, *, immediate: bool = False) -> TaskHandle:
    return task_group(owner).spawn(coroutine, immediate=immediate)


def pump_tasks(owner) -> None:
    group = getattr(owner, "_frame_tasks", None)
    if group is not None:
        group.pump()


def cancel_tasks(owner) -> None:
    group = getattr(owner, "_frame_tasks", None)
    if group is not None:
        group.cancel()


@types.coroutine
def await_task(owner, awaitable):
    """Await existing actions; only the runtime frame entry pumps tasks."""
    iterator = awaitable.__await__() if hasattr(awaitable, "__await__") else iter(awaitable)
    return (yield from iterator)


async def parallel_tasks(owner, coroutines):
    """Run branches in one group and join them, cancelling unfinished peers."""
    handles = []
    pending = list(coroutines)
    try:
        while pending:
            coroutine = pending.pop(0)
            handles.append(spawn_task(owner, coroutine, immediate=True))
        return [await handle.join() for handle in handles]
    finally:
        for coroutine in pending:
            if hasattr(coroutine, "close"):
                coroutine.close()
        for handle in handles:
            if not handle.done:
                handle.cancel()


class FrameTaskOwner:
    """Common task/lifecycle API used by the existing actor classes."""

    def _init_tasks(self) -> None:
        self._frame_tasks = FrameTaskGroup(self)
        self._coroutine_driving = False
        self._close_main_requested = False

    def spawn_task(self, coroutine, *, immediate: bool = False) -> TaskHandle:
        return spawn_task(self, coroutine, immediate=immediate)

    def join_task(self, handle: TaskHandle):
        return handle.join()

    def cancel_task(self, handle: TaskHandle) -> None:
        handle.cancel()

    def parallel(self, coroutines):
        return parallel_tasks(self, coroutines)

    def _reset_tasks(self) -> None:
        self.dispose()
        self._init_tasks()

    def _step_main(self) -> bool:
        coroutine = self._coroutine
        if coroutine is None:
            return False
        self._coroutine_driving = True
        try:
            coroutine.send(None)
            return True
        except StopIteration:
            self._coroutine = None
            return False
        finally:
            self._coroutine_driving = False
            if self._close_main_requested:
                self._close_main_requested = False
                self._close_main()

    def _close_main(self) -> None:
        coroutine, self._coroutine = self._coroutine, None
        if coroutine is not None:
            coroutine.close()

    def dispose(self) -> None:
        """Cancel children and the main coroutine at a safe execution boundary."""
        self._active = False
        try:
            group = getattr(self, "_frame_tasks", None)
            if group is not None:
                group.cancel(close=True)
        finally:
            if getattr(self, "_coroutine_driving", False):
                self._close_main_requested = True
            else:
                self._close_main()


__all__ = [
    "FRAME_RATE", "FRAME_DT", "TaskCancelled", "TaskHandle", "FrameTaskGroup",
    "FrameTaskOwner", "wait_frames", "spawn_task", "pump_tasks", "cancel_tasks",
    "await_task", "parallel_tasks", "task_group",
]

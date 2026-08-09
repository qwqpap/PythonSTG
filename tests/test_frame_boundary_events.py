"""N3.0 fixed-frame Inbox/Outbox and non-reentrant dispatch contracts."""

import threading

from src.game.events import EventBus


def test_outbox_moves_to_next_frame_inbox_and_handlers_are_not_reentrant():
    bus = EventBus()
    seen = []

    def handler(event):
        seen.append((event.type, event.frame, bus.frame))
        if event.type == "root":
            bus.emit("child", {"from": event.event_id}, source="handler")

    bus.subscribe("root", handler)
    bus.subscribe("child", handler)
    root = bus.emit("root", source="test")

    assert bus.dispatch(strict=True) == 0
    assert seen == []
    assert bus.dispatch_frame() == 1
    assert seen == [("root", root.frame, 1)]
    assert bus.outbox_pending == 1

    assert bus.dispatch_frame() == 1
    assert seen[1][0] == "child"
    assert seen[1][2] == 2
    assert bus.pending == 0


def test_frame_boundary_preserves_fifo_and_drops_oldest_only_on_overflow():
    bus = EventBus(max_queue=3)
    received = []
    bus.subscribe("item", lambda event: received.append(event.payload))

    bus.emit("item", 1)
    bus.emit("item", 2)
    bus.emit("item", 3)
    bus.emit("item", 4)
    assert bus.dropped == 1

    bus.dispatch_frame()
    assert received == [2, 3, 4]


def test_producer_thread_only_enqueues_until_main_thread_dispatches():
    bus = EventBus()
    received = []
    bus.subscribe("network.input", lambda event: received.append(event.payload))

    thread = threading.Thread(
        target=lambda: bus.emit("network.input", {"action": "hit"}, source="udp"),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=1.0)

    assert received == []
    assert bus.outbox_pending == 1
    bus.dispatch_frame()
    assert received == [{"action": "hit"}]


def test_cancelled_owner_event_never_reaches_a_later_inbox():
    bus = EventBus()
    received = []
    bus.subscribe("late", lambda event: received.append(event.payload))
    bus.emit("late", 1, owner="old-state")
    bus.tick()  # Promote to Inbox, but deliberately do not dispatch yet.
    assert bus.inbox_pending == 1

    bus.cancel_owner("old-state")
    assert bus.dispatch(strict=True) == 0
    assert received == []

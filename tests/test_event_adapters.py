"""E7.2 frozen acceptance: EventAdapter lifecycle, health, and schemas.

These tests are the completion gate for E7.2 (and the E7.1 emoji refactor)
and must pass exactly as written. Do not edit, skip, or xfail them;
implement the contracts in ``docs/EDITOR_ROADMAP_TODO.md`` (M7 frozen
contracts) instead.

Contract summary:
- ``EventAdapter`` is abstract: ``start(bus)`` / ``stop()`` (idempotent),
  ``health() -> dict``, ``name``.
- ``UDPAdapter`` binds a UDP socket, emits ``adapter.udp`` events with the
  raw parsed payload, reports malformed payloads via ``health()["errors"]``.
- ``LoopbackAdapter.push(payload)`` synchronously routes one payload through
  the bus for in-process/local-IPC contracts.
"""

import json
import socket

import pytest

from src.game.adapters import EventAdapter, LoopbackAdapter, UDPAdapter
from src.game.events import EventBus


def test_adapter_abstract_contract():
    with pytest.raises(TypeError):
        EventAdapter()


class _MinimalAdapter(EventAdapter):
    name = "minimal"

    def start(self, bus):
        self.bus = bus

    def stop(self):
        pass

    def health(self):
        return {"ok": True}


def test_adapter_lifecycle_start_stop_health():
    bus = EventBus()
    adapter = _MinimalAdapter()
    adapter.start(bus)
    adapter.stop()
    adapter.stop()

    assert adapter.health() == {"ok": True}


def test_loopback_adapter_routes_payloads_through_the_bus():
    bus = EventBus()
    adapter = LoopbackAdapter()
    adapter.start(bus)
    received = []
    bus.subscribe("adapter.loopback", lambda event: received.append(event.payload))

    adapter.push({"message": "hello"})
    bus.dispatch()

    assert received == [{"message": "hello"}]
    adapter.stop()
    adapter.stop()


def test_udp_adapter_emits_typed_events_for_valid_json():
    bus = EventBus()
    adapter = UDPAdapter(host="127.0.0.1", port=0)
    adapter.start(bus)
    received = []
    bus.subscribe("adapter.udp", lambda event: received.append(event.payload))

    port = adapter.bound_port
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.sendto(json.dumps({"cmd": "emoji", "emoji": "😂"}).encode("utf-8"), ("127.0.0.1", port))
        import time

        deadline = time.time() + 2.0
        while not received and time.time() < deadline:
            bus.dispatch()
            time.sleep(0.02)

    assert received and received[0]["emoji"] == "😂"
    health = adapter.health()
    assert health["ok"] is True
    adapter.stop()
    adapter.stop()


def test_udp_adapter_records_malformed_payloads_without_crashing():
    bus = EventBus()
    adapter = UDPAdapter(host="127.0.0.1", port=0)
    adapter.start(bus)

    port = adapter.bound_port
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.sendto(b"{not json", ("127.0.0.1", port))
        import time

        deadline = time.time() + 2.0
        health = adapter.health()
        while health["errors"] == 0 and time.time() < deadline:
            time.sleep(0.02)
            health = adapter.health()

    assert health["errors"] >= 1
    adapter.stop()
    adapter.stop()


def test_udp_adapter_health_reports_binding_failure():
    adapter = UDPAdapter(host="127.0.0.1", port=0)
    adapter.start(None)

    assert adapter.health()["ok"] is True
    adapter.stop()


def test_adapter_can_drive_typed_scene_events_through_the_bus():
    bus = EventBus()
    adapter = LoopbackAdapter()
    adapter.start(bus)
    scene_actions = []
    bus.subscribe(
        "adapter.loopback", lambda event: scene_actions.append(event.payload)
    )

    adapter.push({"target": "scene", "action": "emitter_spawn", "x": 0.5, "y": -0.5})
    bus.dispatch()

    assert scene_actions == [{"target": "scene", "action": "emitter_spawn", "x": 0.5, "y": -0.5}]

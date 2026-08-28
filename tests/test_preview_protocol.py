from __future__ import annotations

import pytest

from src.core.preview_protocol import (
    CONTROL_TYPES,
    EVENT_TYPES,
    MAX_PREVIEW_LINE_BYTES,
    MAX_TRACE_EVENTS_PER_MESSAGE,
    PREVIEW_PROTOCOL_VERSION,
    PreviewProtocolError,
    control_message,
    decode_message,
    encode_message,
    event_message,
)


@pytest.mark.parametrize("command", sorted(CONTROL_TYPES - {"seek"}))
def test_control_round_trip_is_fixed_and_identified(command):
    message = control_message("run-1", command)
    assert decode_message(encode_message(message)) == message
    assert message == {
        "protocol_version": PREVIEW_PROTOCOL_VERSION,
        "run_id": "run-1",
        "command": command,
        "payload": {},
    }


def test_seek_requires_one_non_negative_integer_frame():
    message = control_message("run-1", "seek", {"frame": 240})
    assert decode_message(encode_message(message)) == message
    for payload in ({}, {"frame": -1}, {"frame": True}, {"frame": 1, "extra": 2}):
        with pytest.raises(PreviewProtocolError):
            control_message("run-1", "seek", payload)


@pytest.mark.parametrize("event", sorted(EVENT_TYPES - {"trace", "frame"}))
def test_event_round_trip_is_fixed_and_identified(event):
    message = event_message("run-2", event, {"value": event})
    assert decode_message(encode_message(message)) == message


def test_protocol_rejects_unknown_version_type_identity_and_fields():
    invalid = [
        {"protocol_version": 99, "run_id": "r", "command": "stop", "payload": {}},
        {"protocol_version": 1, "run_id": "", "command": "stop", "payload": {}},
        {"protocol_version": 1, "run_id": "r", "command": "hello", "payload": {}},
        {"protocol_version": 1, "run_id": "r", "event": "response", "payload": {}},
        {
            "protocol_version": 1,
            "run_id": "r",
            "command": "stop",
            "event": "stopped",
            "payload": {},
        },
        {
            "protocol_version": 1,
            "run_id": "r",
            "command": "stop",
            "payload": {},
            "legacy": True,
        },
    ]
    for message in invalid:
        with pytest.raises(PreviewProtocolError):
            decode_message(__import__("json").dumps(message))


def test_protocol_enforces_line_and_trace_batch_bounds():
    with pytest.raises(PreviewProtocolError, match="exceeds"):
        decode_message(b"x" * (MAX_PREVIEW_LINE_BYTES + 1))
    event_message(
        "r",
        "trace",
        {"events": [{} for _ in range(MAX_TRACE_EVENTS_PER_MESSAGE)]},
    )
    with pytest.raises(PreviewProtocolError, match="trace batch"):
        event_message(
            "r",
            "trace",
            {"events": [{} for _ in range(MAX_TRACE_EVENTS_PER_MESSAGE + 1)]},
        )


def test_frame_event_requires_a_non_negative_integer():
    assert event_message("r", "frame", {"frame": 0})["payload"]["frame"] == 0
    for value in (-1, True, 1.5, "1"):
        with pytest.raises(PreviewProtocolError):
            event_message("r", "frame", {"frame": value})

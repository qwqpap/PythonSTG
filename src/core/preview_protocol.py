"""Bounded NDJSON protocol shared by the editor and the real game process.

The protocol is deliberately headless. It validates only the five preview
controls and seven runtime events defined by the editor contract; normal game
logs travel on stderr and never masquerade as protocol messages.
"""

from __future__ import annotations

import json
from typing import Any, Mapping


PREVIEW_PROTOCOL_VERSION = 1
MAX_PREVIEW_LINE_BYTES = 64 * 1024
MAX_TRACE_EVENTS_PER_MESSAGE = 256

CONTROL_TYPES = frozenset({"pause", "resume", "restart", "seek", "stop"})
EVENT_TYPES = frozenset(
    {"ready", "state", "frame", "trace", "error", "stopped"}
)


class PreviewProtocolError(ValueError):
    """A line is not a valid message in the fixed preview protocol."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def control_message(
    run_id: str,
    command: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    message = _base_message(run_id)
    message["command"] = _validate_name(command, CONTROL_TYPES, "command")
    message["payload"] = _validate_payload(payload)
    _validate_control_payload(message["command"], message["payload"])
    return message


def event_message(
    run_id: str,
    event: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    message = _base_message(run_id)
    message["event"] = _validate_name(event, EVENT_TYPES, "event")
    message["payload"] = _validate_payload(payload)
    _validate_event_payload(message["event"], message["payload"])
    return message


def encode_message(message: Mapping[str, Any]) -> bytes:
    """Validate and encode one protocol object including its NDJSON newline."""

    normalized = validate_message(message)
    try:
        encoded = (
            json.dumps(
                normalized,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise PreviewProtocolError("invalid_payload", str(exc)) from exc
    if len(encoded) > MAX_PREVIEW_LINE_BYTES:
        raise PreviewProtocolError(
            "line_too_long",
            f"preview message exceeds {MAX_PREVIEW_LINE_BYTES} bytes",
        )
    return encoded


def decode_message(line: bytes | str) -> dict[str, Any]:
    """Decode exactly one bounded NDJSON line and validate its schema."""

    raw = line.encode("utf-8") if isinstance(line, str) else bytes(line)
    if len(raw) > MAX_PREVIEW_LINE_BYTES:
        raise PreviewProtocolError(
            "line_too_long",
            f"preview message exceeds {MAX_PREVIEW_LINE_BYTES} bytes",
        )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreviewProtocolError("malformed_json", str(exc)) from exc
    if not isinstance(value, dict):
        raise PreviewProtocolError("invalid_message", "preview message must be an object")
    return validate_message(value)


def validate_message(message: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(message, Mapping):
        raise PreviewProtocolError("invalid_message", "preview message must be an object")
    version = message.get("protocol_version")
    if version != PREVIEW_PROTOCOL_VERSION:
        raise PreviewProtocolError(
            "version_mismatch",
            f"expected protocol {PREVIEW_PROTOCOL_VERSION}, got {version!r}",
        )
    run_id = _validate_run_id(message.get("run_id"))
    has_command = "command" in message
    has_event = "event" in message
    if has_command == has_event:
        raise PreviewProtocolError(
            "invalid_message",
            "preview message must contain exactly one of command or event",
        )
    allowed = {"protocol_version", "run_id", "payload"}
    if has_command:
        allowed.add("command")
        normalized = control_message(run_id, message["command"], message.get("payload"))
    else:
        allowed.add("event")
        normalized = event_message(run_id, message["event"], message.get("payload"))
    extra = set(message) - allowed
    if extra:
        raise PreviewProtocolError(
            "unknown_field",
            "unknown preview fields: " + ", ".join(sorted(str(item) for item in extra)),
        )
    return normalized


def _base_message(run_id: str) -> dict[str, Any]:
    return {
        "protocol_version": PREVIEW_PROTOCOL_VERSION,
        "run_id": _validate_run_id(run_id),
    }


def _validate_run_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreviewProtocolError("invalid_run_id", "run_id must be non-empty text")
    value = value.strip()
    if len(value) > 128:
        raise PreviewProtocolError("invalid_run_id", "run_id is longer than 128 characters")
    return value


def _validate_name(value: Any, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise PreviewProtocolError(
            f"unknown_{label}",
            f"unsupported preview {label}: {value!r}",
        )
    return value


def _validate_payload(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise PreviewProtocolError("invalid_payload", "payload must be an object")
    return dict(value)


def _validate_control_payload(command: str, payload: dict[str, Any]) -> None:
    if command != "seek":
        if payload:
            raise PreviewProtocolError(
                "invalid_payload", f"{command} does not accept a payload"
            )
        return
    if set(payload) != {"frame"}:
        raise PreviewProtocolError("invalid_payload", "seek requires only payload.frame")
    frame = payload["frame"]
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise PreviewProtocolError(
            "invalid_payload", "seek payload.frame must be a non-negative integer"
        )


def _validate_event_payload(event: str, payload: dict[str, Any]) -> None:
    if event == "trace":
        events = payload.get("events")
        if not isinstance(events, list):
            raise PreviewProtocolError("invalid_payload", "trace requires payload.events")
        if len(events) > MAX_TRACE_EVENTS_PER_MESSAGE:
            raise PreviewProtocolError(
                "trace_batch_too_large",
                f"trace batch exceeds {MAX_TRACE_EVENTS_PER_MESSAGE} events",
            )
    if event == "frame":
        frame = payload.get("frame")
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise PreviewProtocolError("invalid_payload", "frame requires a non-negative frame")


__all__ = [
    "CONTROL_TYPES",
    "EVENT_TYPES",
    "MAX_PREVIEW_LINE_BYTES",
    "MAX_TRACE_EVENTS_PER_MESSAGE",
    "PREVIEW_PROTOCOL_VERSION",
    "PreviewProtocolError",
    "control_message",
    "decode_message",
    "encode_message",
    "event_message",
    "validate_message",
]

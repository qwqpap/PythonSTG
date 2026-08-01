"""Versioned newline-delimited JSON transport for formal previews."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .controller import PatternPreviewController, PreviewCommandError


PREVIEW_PROTOCOL_VERSION = 1


def encode_message(message: dict[str, Any]) -> bytes:
    return (
        json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _message(
    event: str,
    payload: dict[str, Any],
    *,
    request_id: str | None,
) -> dict[str, Any]:
    return {
        "protocol_version": PREVIEW_PROTOCOL_VERSION,
        "request_id": request_id,
        "event": event,
        "payload": payload,
    }


@dataclass(frozen=True)
class ProtocolResult:
    messages: tuple[dict[str, Any], ...]
    shutdown: bool = False


class PreviewProtocolSession:
    def __init__(self, controller: PatternPreviewController) -> None:
        self.controller = controller
        self.negotiated = False

    def _error(
        self,
        request_id: str | None,
        code: str,
        message: str,
        *,
        command: str | None = None,
    ) -> ProtocolResult:
        return ProtocolResult(
            (
                _message(
                    "protocol_error",
                    {
                        "code": code,
                        "message": message,
                        "command": command,
                    },
                    request_id=request_id,
                ),
            )
        )

    def handle_line(self, line: str) -> ProtocolResult:
        try:
            request = json.loads(line)
        except (TypeError, json.JSONDecodeError) as exc:
            return self._error(None, "malformed_json", str(exc))
        if not isinstance(request, dict):
            return self._error(None, "invalid_request", "request must be a JSON object")

        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            return self._error(None, "missing_request_id", "request_id must be a non-empty string")
        version = request.get("protocol_version")
        if version != PREVIEW_PROTOCOL_VERSION:
            return self._error(
                request_id,
                "unsupported_protocol",
                f"protocol {version!r} is unsupported; expected {PREVIEW_PROTOCOL_VERSION}",
            )
        command = request.get("command")
        if not isinstance(command, str) or not command:
            return self._error(request_id, "missing_command", "command must be a non-empty string")
        payload = request.get("payload", {})
        if not isinstance(payload, dict):
            return self._error(request_id, "invalid_payload", "payload must be an object", command=command)

        if command == "hello":
            self.negotiated = True
            return ProtocolResult(
                (
                    _message(
                        "hello",
                        {
                            "protocol_version": PREVIEW_PROTOCOL_VERSION,
                            "commands": sorted(self.controller.COMMANDS),
                        },
                        request_id=request_id,
                    ),
                )
            )
        if not self.negotiated:
            return self._error(request_id, "handshake_required", "send hello before preview commands", command=command)
        if command == "shutdown":
            self.controller.close()
            return ProtocolResult(
                (_message("response", {"ok": True, "command": command}, request_id=request_id),),
                shutdown=True,
            )

        try:
            result = self.controller.execute(command, payload)
            response = _message(
                "response",
                {"ok": True, "command": command, "result": result},
                request_id=request_id,
            )
        except Exception as exc:
            if isinstance(exc, PreviewCommandError):
                path = exc.path
                detail = exc.detail
            else:
                path = ""
                detail = str(exc)
            response = _message(
                "response",
                {
                    "ok": False,
                    "command": command,
                    "error": {
                        "type": type(exc).__name__,
                        "path": path,
                        "message": detail,
                    },
                },
                request_id=request_id,
            )

        events = tuple(
            _message(
                item.event,
                {"sequence": item.sequence, **item.payload},
                request_id=request_id,
            )
            for item in self.controller.drain_events()
        )
        return ProtocolResult((response, *events))

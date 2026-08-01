import json

from src.core.project_context import ProjectContext
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.preview import PatternPreviewController, PreviewProtocolSession


def _session(tmp_path):
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True)
    aliases.write_text(json.dumps({"mapping": {"ball_m": {"red": "orb"}}}), encoding="utf-8")
    controller = PatternPreviewController(
        OptimizedBulletPool(max_bullets=32),
        project=ProjectContext(tmp_path),
    )
    return PreviewProtocolSession(controller)


def _request(command, payload=None, *, request_id="req-1", version=1):
    return json.dumps(
        {
            "protocol_version": version,
            "request_id": request_id,
            "command": command,
            "payload": payload or {},
        }
    )


def test_protocol_requires_versioned_hello_and_preserves_request_ids(tmp_path):
    session = _session(tmp_path)

    before_hello = session.handle_line(_request("get-stats"))
    hello = session.handle_line(_request("hello", request_id="hello-1"))

    assert before_hello.messages[0]["payload"]["code"] == "handshake_required"
    assert hello.messages[0]["event"] == "hello"
    assert hello.messages[0]["request_id"] == "hello-1"
    assert hello.messages[0]["payload"]["protocol_version"] == 1


def test_protocol_reports_malformed_unknown_and_version_errors(tmp_path):
    session = _session(tmp_path)

    malformed = session.handle_line("{")
    wrong_version = session.handle_line(_request("hello", version=99))
    session.handle_line(_request("hello"))
    unknown = session.handle_line(_request("explode"))

    assert malformed.messages[0]["payload"]["code"] == "malformed_json"
    assert wrong_version.messages[0]["payload"]["code"] == "unsupported_protocol"
    response = unknown.messages[0]
    assert response["event"] == "response"
    assert response["payload"]["ok"] is False
    assert response["payload"]["command"] == "explode"


def test_protocol_load_command_returns_response_and_structured_events(tmp_path):
    from src.pattern import PatternDocument

    session = _session(tmp_path)
    session.handle_line(_request("hello"))

    result = session.handle_line(
        _request("load", {"document": PatternDocument.new("Protocol").to_dict()})
    )

    assert result.messages[0]["event"] == "response"
    assert result.messages[0]["payload"]["ok"] is True
    assert {message["event"] for message in result.messages[1:]} == {
        "program_loaded",
        "status",
    }


def test_shutdown_is_idempotent_protocol_terminal_message(tmp_path):
    session = _session(tmp_path)
    session.handle_line(_request("hello"))

    result = session.handle_line(_request("shutdown"))

    assert result.shutdown is True
    assert result.messages[0]["payload"]["ok"] is True

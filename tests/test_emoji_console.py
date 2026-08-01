import io

from src.game.emoji_danmaku.emoji_gl_renderer import _safe_print


def test_safe_print_escapes_characters_missing_from_gbk() -> None:
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="gbk", errors="strict")

    _safe_print("emoji 😂 loaded ✓", stream=stream)
    stream.flush()

    output = buffer.getvalue().decode("gbk")
    assert "emoji " in output
    assert "\\U0001f602" in output
    assert " loaded " in output

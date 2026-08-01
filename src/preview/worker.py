"""Blocking stdio worker used for protocol smoke tests and headless control."""

from __future__ import annotations

import sys
from typing import BinaryIO, TextIO

from .protocol import PreviewProtocolSession, encode_message


def run_stdio_worker(
    session: PreviewProtocolSession,
    *,
    input_stream: TextIO | None = None,
    output_stream: BinaryIO | None = None,
) -> int:
    source = input_stream or sys.stdin
    sink = output_stream or sys.stdout.buffer
    for line in source:
        result = session.handle_line(line)
        for message in result.messages:
            sink.write(encode_message(message))
        sink.flush()
        if result.shutdown:
            return 0
    session.controller.close()
    return 0

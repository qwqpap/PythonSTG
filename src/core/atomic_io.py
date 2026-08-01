"""Crash-safe file replacement helpers used by runtime and editor tools."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            newline="\n",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    return target


def atomic_write_json(
    path: str | Path,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> Path:
    text = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii) + "\n"
    return atomic_write_text(path, text)

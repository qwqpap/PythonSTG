"""Fresh local build interpreter. No Qt, no publication, no preview ownership."""

from __future__ import annotations

import importlib.machinery
import pickle
import sys
from pathlib import Path


class _BuildLog:
    """Bound trusted-template print output while keeping stdout for the result."""

    def __init__(self, stream):
        self.stream = stream
        self.remaining = 64 * 1024

    def write(self, text):
        encoded = str(text).encode('utf-8', errors='replace')
        accepted = encoded[:self.remaining]
        self.remaining -= len(accepted)
        if accepted:
            self.stream.write(accepted.decode('utf-8', errors='replace'))
        return len(str(text))

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def main() -> int:
    repository = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repository))
    output = sys.stdout.buffer
    request = pickle.loads(sys.stdin.buffer.read())
    # Author templates are trusted code, but must never use a previous build's
    # sys.modules or timestamp/size-based .pyc cache (same-second edits matter).
    def fresh_code(loader, fullname):
        return loader.source_to_code(loader.get_data(loader.path), loader.path)

    importlib.machinery.SourceFileLoader.get_code = fresh_code
    sys.dont_write_bytecode = True
    sys.stderr = _BuildLog(sys.stderr)
    sys.stdout = sys.stderr
    project_root = Path(request["project_root"])
    sys.path.insert(0, str(project_root))
    if request["source_root"] is not None:
        sys.path.insert(0, str(request["source_root"]))
    from src.compiler.package_builder import PackageBuilder

    builder = PackageBuilder(
        request["output_root"], project_root=project_root, source_root=request["source_root"]
    )
    try:
        prepared = builder._prepare_local(request["program"], request["staging"])
        result = {"ok": True, "prepared": prepared}
        status = 0
    except Exception as exc:
        result = {
            "ok": False,
            "code": getattr(exc, "code", "build_failed"),
            "message": getattr(exc, "message", str(exc)),
            "diagnostics": getattr(exc, "diagnostics", ()),
        }
        status = 1
    output.write(pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL))
    output.flush()
    return status


if __name__ == "__main__":
    raise SystemExit(main())

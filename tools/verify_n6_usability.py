"""Validate independently collected N6 beginner-usability evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


class UsabilityReportError(ValueError):
    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise UsabilityReportError(path, "must be a boolean")
    return value


def _minutes(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise UsabilityReportError(path, "must be a non-negative number")
    return float(value)


def validate_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise UsabilityReportError("report", "must be an object")
    if value.get("study") != "pystg-n6":
        raise UsabilityReportError("study", "must be pystg-n6")
    if _bool(value.get("maintainer_coaching"), "maintainer_coaching"):
        raise UsabilityReportError("maintainer_coaching", "must be false")
    participants = value.get("participants")
    if not isinstance(participants, list) or len(participants) < 5:
        raise UsabilityReportError("participants", "needs at least five people")
    ids = [item.get("id") for item in participants if isinstance(item, Mapping)]
    if len(ids) != len(participants) or any(not isinstance(item, str) or not item for item in ids):
        raise UsabilityReportError("participants[].id", "must be non-empty")
    if len(ids) != len(set(ids)):
        raise UsabilityReportError("participants[].id", "must be unique")

    thresholds = {"pattern_10m": 0, "midstage_30m": 0, "boss_60m": 0}
    for index, raw in enumerate(participants):
        path = f"participants[{index}]"
        if not isinstance(raw, Mapping):
            raise UsabilityReportError(path, "must be an object")
        if _bool(raw.get("prior_pystg_experience"), f"{path}.prior_pystg_experience"):
            raise UsabilityReportError(path, "participant must be new to PySTG")
        if _bool(raw.get("wrote_script"), f"{path}.wrote_script"):
            raise UsabilityReportError(path, "participant must not write a script")
        pattern = _minutes(raw.get("pattern_minutes"), f"{path}.pattern_minutes")
        midstage = _minutes(raw.get("midstage_minutes"), f"{path}.midstage_minutes")
        boss = _minutes(raw.get("boss_minutes"), f"{path}.boss_minutes")
        if _bool(raw.get("completed_pattern"), f"{path}.completed_pattern") and pattern <= 10:
            thresholds["pattern_10m"] += 1
        if _bool(raw.get("completed_midstage"), f"{path}.completed_midstage") and midstage <= 30:
            thresholds["midstage_30m"] += 1
        if (
            _bool(
                raw.get("completed_boss_background_event"),
                f"{path}.completed_boss_background_event",
            )
            and boss <= 60
        ):
            thresholds["boss_60m"] += 1
        help_requests = raw.get("help_requests")
        if isinstance(help_requests, bool) or not isinstance(help_requests, int) or help_requests < 0:
            raise UsabilityReportError(f"{path}.help_requests", "must be non-negative")
        if not isinstance(raw.get("failure_points"), list):
            raise UsabilityReportError(f"{path}.failure_points", "must be an array")
    return {
        "passed": all(value >= 4 for value in thresholds.values()),
        "participants": len(participants),
        "thresholds": thresholds,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        result = validate_report(json.loads(args.report.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, UsabilityReportError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

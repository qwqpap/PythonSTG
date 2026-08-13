"""Progressive Pattern authoring navigation over one shared resource."""

from __future__ import annotations

from dataclasses import dataclass

from src.pattern import PatternDocument


@dataclass(frozen=True)
class AuthoringLevel:
    id: str
    label: str
    role: str
    mutates_on_entry: bool
    help_text: str


AUTHORING_LEVELS = (
    AuthoringLevel("l0", "Choose Preset", "content", False, "Start from an editable preset."),
    AuthoringLevel("l1", "Adjust Parameters", "content", False, "Edit the values used most often."),
    AuthoringLevel("l2", "Add Dynamic Changes", "content", False, "Drive a property with a curve or variable."),
    AuthoringLevel("l3", "Edit Nodes", "content", True, "Edit the local behavior as connected nodes."),
    AuthoringLevel("l4", "View Script Source", "runtime", False, "Open the trusted implementation source."),
)


def authoring_level(level_id: str) -> AuthoringLevel:
    try:
        return next(item for item in AUTHORING_LEVELS if item.id == str(level_id))
    except StopIteration as exc:
        raise ValueError(f"authoring.level: unsupported level {level_id!r}") from exc


def available_levels(
    document: PatternDocument,
    *,
    has_preset: bool,
) -> tuple[str, ...]:
    """Return navigation availability without changing the document."""

    values = ["l1", "l2", "l3", "l4"]
    if has_preset:
        values.insert(0, "l0")
    return tuple(values)


def level_snapshot(document: PatternDocument, level_id: str) -> dict[str, object]:
    """Debugger/navigation metadata shared by all views of one Pattern."""

    level = authoring_level(level_id)
    return {
        "resource_id": document.id,
        "level": level.id,
        "role": level.role,
        "has_graph": document.graph is not None,
        "script_resource": (
            document.script.resource_uri if document.script is not None else None
        ),
    }

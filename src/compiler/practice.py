"""Build standard preview stages for authoring units below Stage level."""

from __future__ import annotations

from typing import Any, Iterable

from src.authoring.dsl import Boss, Project, RunBoss, RunWave, SpawnEnemy, Stage, Wait, Wave
from src.authoring.program import AuthoringProgram, LogicalUnit, Node, Ref


PRACTICE_STAGE_ID = "_pystg_practice_stage"
_PRACTICE_WAVE_ID = "_pystg_practice_wave"
_PRACTICE_BOSS_ID = "_pystg_practice_boss"


def practice_program(program: AuthoringProgram, unit_id: str) -> AuthoringProgram:
    """Return an isolated deterministic Project for Wave, Enemy, or Spell."""

    source = program.clone()
    selected = source.get_unit(unit_id)
    if selected.kind not in {"Wave", "Enemy", "Spell"}:
        raise ValueError("practice preview supports only Wave, Enemy, and Spell units")
    original_project = _project_unit(source)
    practice_id = f"{original_project.id}_practice"
    stage_body: list[Node]
    wrappers: list[LogicalUnit] = []

    if selected.kind == "Wave":
        stage_body = [
            RunWave(Ref(selected.id), uid="_pystg_practice_run_wave"),
            Wait(600, uid="_pystg_practice_tail"),
        ]
    elif selected.kind == "Enemy":
        wrappers.append(
            Wave(
                _PRACTICE_WAVE_ID,
                "Enemy Practice Wave",
                [
                    SpawnEnemy(
                        Ref(selected.id),
                        x=0.0,
                        y=0.7,
                        uid="_pystg_practice_spawn_enemy",
                    ),
                    Wait(3600, uid="_pystg_practice_enemy_tail"),
                ],
            )
        )
        stage_body = [
            RunWave(Ref(_PRACTICE_WAVE_ID), uid="_pystg_practice_run_enemy_wave")
        ]
    else:
        wrappers.append(
            Boss(
                _PRACTICE_BOSS_ID,
                "Spell Practice Boss",
                texture="sunny",
                phases=[Ref(selected.id)],
            )
        )
        stage_body = [
            RunBoss(Ref(_PRACTICE_BOSS_ID), uid="_pystg_practice_run_spell")
        ]

    stage = Stage(
        PRACTICE_STAGE_ID,
        f"{selected.name} · Practice",
        stage_body,
        title="Authoring Practice",
    )
    project = Project(
        practice_id,
        f"{original_project.name} · Practice",
        Ref(PRACTICE_STAGE_ID),
        [Ref(PRACTICE_STAGE_ID)],
    )
    closure = _transitive_units(source, selected.id)
    result = AuthoringProgram.from_units([project, stage, *wrappers, *closure])
    result.assert_valid()
    return result


def _project_unit(program: AuthoringProgram) -> LogicalUnit:
    projects = [unit for unit in program.logical_units() if unit.kind == "Project"]
    if len(projects) != 1:
        raise ValueError("authoring program must contain exactly one Project")
    return projects[0]


def _transitive_units(program: AuthoringProgram, start_id: str) -> list[LogicalUnit]:
    visited: set[str] = set()
    ordered: list[LogicalUnit] = []

    def visit(unit_id: str) -> None:
        if unit_id in visited:
            return
        visited.add(unit_id)
        unit = program.get_unit(unit_id)
        for reference in sorted(_unit_references(unit), key=lambda item: item.id):
            target = program.get_unit(reference.id)
            if target.kind not in {"Project", "Stage"}:
                visit(target.id)
        ordered.append(unit.clone())

    visit(start_id)
    return sorted(ordered, key=lambda unit: (unit.kind, unit.id))


def _unit_references(unit: LogicalUnit) -> Iterable[Ref]:
    for value in unit.metadata.values():
        yield from _references(value)
    for parameter in unit.parameters:
        if parameter.has_default:
            yield from _references(parameter.default)
    for node in unit.body:
        yield from _references(node)


def _references(value: Any) -> Iterable[Ref]:
    if isinstance(value, Ref):
        yield value
    elif isinstance(value, Node):
        if value.kind == "RawPython":
            return
        for item in value.arguments.values():
            yield from _references(item)
        for item in value.positional_arguments:
            yield from _references(item)
        for children in value.children.values():
            for child in children:
                yield from _references(child)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _references(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _references(item)


__all__ = ["PRACTICE_STAGE_ID", "practice_program"]

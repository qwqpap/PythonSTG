"""Public declarative Python constructors for level authoring.

Constructors return the headless :mod:`src.authoring.program` model.  They do
not execute gameplay, import Qt, or depend on the renderer.  Parameters shared
by Wave, EnemyScript, and SpellCard mirror their public runtime names.  Where
those runtime classes intentionally have different defaults, omission is kept
as omission so the compiler can call the concrete runtime method unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .program import (
    Expr,
    LogicalUnit,
    Node,
    Parameter,
    Ref,
    TemplateTarget,
    make_template_call,
    new_uid,
)


AuthorValue = Any


class _RuntimeDefault:
    def __repr__(self) -> str:
        return "<runtime default>"


RUNTIME_DEFAULT = _RuntimeDefault()


def _uid(kind: str, value: str | None) -> str:
    return new_uid(kind) if value is None else value


def _children(values: Sequence[Node] | None) -> list[Node]:
    return list(values or ())


def _without_defaults(values: Mapping[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: value
        for name, value in values.items()
        if name not in defaults or value != defaults[name]
    }


def _node(
    kind: str,
    *,
    arguments: Mapping[str, Any] | None = None,
    children: Mapping[str, Sequence[Node]] | None = None,
    uid: str | None = None,
) -> Node:
    return Node(
        kind=kind,
        arguments=dict(arguments or {}),
        children={name: list(items) for name, items in (children or {}).items()},
        uid=_uid(kind, uid),
    )


# ---------------------------------------------------------------------------
# Logical units
# ---------------------------------------------------------------------------


def Project(
    id: str,
    name: str,
    start_stage: Ref,
    stages: Sequence[Ref],
) -> LogicalUnit:
    return LogicalUnit(
        kind="Project",
        id=id,
        name=name,
        metadata={"start_stage": start_stage, "stages": list(stages)},
        assignment_name="project",
    )


def Stage(
    id: str,
    name: str,
    body: Sequence[Node] = (),
    *,
    title: str = "",
    subtitle: str = "",
    bgm: str = "",
    boss_bgm: str = "",
    background: str = "",
) -> LogicalUnit:
    return LogicalUnit(
        kind="Stage",
        id=id,
        name=name,
        body=list(body),
        metadata=_without_defaults(
            {
                "title": title,
                "subtitle": subtitle,
                "bgm": bgm,
                "boss_bgm": boss_bgm,
                "background": background,
            },
            {"title": "", "subtitle": "", "bgm": "", "boss_bgm": "", "background": ""},
        ),
        assignment_name="stage",
    )


def Wave(id: str, name: str, body: Sequence[Node] = ()) -> LogicalUnit:
    return LogicalUnit(kind="Wave", id=id, name=name, body=list(body), assignment_name="wave")


def Enemy(
    id: str,
    name: str,
    body: Sequence[Node] = (),
    *,
    hp: int = 30,
    sprite: str = "enemy_fairy",
    score: int = 100,
    hitbox_radius: float = 0.02,
    drops: Mapping[str, int] | None = None,
    clear_bullets_on_death: bool = False,
) -> LogicalUnit:
    metadata = _without_defaults(
        {
            "hp": hp,
            "sprite": sprite,
            "score": score,
            "hitbox_radius": hitbox_radius,
            "drops": dict(drops or {}),
            "clear_bullets_on_death": clear_bullets_on_death,
        },
        {
            "hp": 30,
            "sprite": "enemy_fairy",
            "score": 100,
            "hitbox_radius": 0.02,
            "drops": {},
            "clear_bullets_on_death": False,
        },
    )
    return LogicalUnit(
        kind="Enemy", id=id, name=name, body=list(body), metadata=metadata, assignment_name="enemy"
    )


def Boss(
    id: str,
    name: str,
    texture: str,
    phases: Sequence[Ref],
    *,
    animations: Mapping[str, AuthorValue] | None = None,
) -> LogicalUnit:
    metadata = {"texture": texture, "phases": list(phases)}
    metadata.update(
        _without_defaults(
            {"animations": dict(animations or {})},
            {"animations": {}},
        )
    )
    return LogicalUnit(
        kind="Boss", id=id, name=name, body=[], metadata=metadata, assignment_name="boss"
    )


def Spell(
    id: str,
    name: str,
    body: Sequence[Node] = (),
    *,
    hp: int = 1500,
    time_limit: float = 60.0,
    bonus: int = 1_000_000,
    is_survival: bool = False,
    is_timeout: bool = False,
    practice_unlock: bool = True,
) -> LogicalUnit:
    metadata = _without_defaults(
        {
            "hp": hp,
            "time_limit": time_limit,
            "bonus": bonus,
            "is_survival": is_survival,
            "is_timeout": is_timeout,
            "practice_unlock": practice_unlock,
        },
        {
            "hp": 1500,
            "time_limit": 60.0,
            "bonus": 1_000_000,
            "is_survival": False,
            "is_timeout": False,
            "practice_unlock": True,
        },
    )
    return LogicalUnit(
        kind="Spell", id=id, name=name, body=list(body), metadata=metadata, assignment_name="spell"
    )


def NonSpell(
    id: str,
    name: str = "NonSpell",
    body: Sequence[Node] = (),
    *,
    hp: int = 1500,
    time_limit: float = 60.0,
    bonus: int = 100_000,
    is_survival: bool = False,
    is_timeout: bool = False,
    practice_unlock: bool = False,
) -> LogicalUnit:
    metadata = _without_defaults(
        {
            "hp": hp,
            "time_limit": time_limit,
            "bonus": bonus,
            "is_survival": is_survival,
            "is_timeout": is_timeout,
            "practice_unlock": practice_unlock,
        },
        {
            "hp": 1500,
            "time_limit": 60.0,
            "bonus": 100_000,
            "is_survival": False,
            "is_timeout": False,
            "practice_unlock": False,
        },
    )
    return LogicalUnit(
        kind="NonSpell",
        id=id,
        name=name,
        body=list(body),
        metadata=metadata,
        assignment_name="nonspell",
    )


def Task(
    id: str,
    name: str,
    parameters: Sequence[Parameter] = (),
    body: Sequence[Node] = (),
) -> LogicalUnit:
    return LogicalUnit(
        kind="Task",
        id=id,
        name=name,
        parameters=tuple(parameters),
        body=list(body),
        assignment_name="task",
    )


def Function(
    id: str,
    name: str,
    parameters: Sequence[Parameter] = (),
    body: Sequence[Node] = (),
) -> LogicalUnit:
    return LogicalUnit(
        kind="Function",
        id=id,
        name=name,
        parameters=tuple(parameters),
        body=list(body),
        assignment_name="function",
    )


# ---------------------------------------------------------------------------
# Control statements
# ---------------------------------------------------------------------------


def Wait(frames: int | Expr, *, uid: str | None = None) -> Node:
    return _node("Wait", arguments={"frames": frames}, uid=uid)


def At(frame: int | Expr, body: Sequence[Node], *, uid: str | None = None) -> Node:
    return _node("At", arguments={"frame": frame}, children={"body": body}, uid=uid)


def Repeat(count: int | Expr, body: Sequence[Node], *, uid: str | None = None) -> Node:
    return _node("Repeat", arguments={"count": count}, children={"body": body}, uid=uid)


def While(condition: Expr | bool, body: Sequence[Node], *, uid: str | None = None) -> Node:
    return _node("While", arguments={"condition": condition}, children={"body": body}, uid=uid)


def If(
    condition: Expr | bool,
    body: Sequence[Node],
    else_body: Sequence[Node] = (),
    *,
    uid: str | None = None,
) -> Node:
    return _node(
        "If",
        arguments={"condition": condition},
        children={"body": body, "else_body": else_body},
        uid=uid,
    )


def Else(body: Sequence[Node], *, uid: str | None = None) -> Node:
    return _node("Else", children={"body": body}, uid=uid)


def ForEach(
    target: str,
    iterable: Expr | Sequence[AuthorValue],
    body: Sequence[Node],
    *,
    uid: str | None = None,
) -> Node:
    return _node(
        "ForEach",
        arguments={"target": target, "iterable": iterable},
        children={"body": body},
        uid=uid,
    )


def Parallel(
    branches: Sequence[Sequence[Node]],
    *,
    wait: bool = True,
    uid: str | None = None,
) -> Node:
    parallel_uid = _uid("Parallel", uid)
    branch_nodes = [
        Node(
            kind="Branch",
            children={"body": list(branch)},
            uid=f"{parallel_uid}__branch_{index}",
        )
        for index, branch in enumerate(branches)
    ]
    return Node(
        kind="Parallel",
        arguments={} if wait is True else {"wait": wait},
        children={"branches": branch_nodes},
        uid=parallel_uid,
    )


def SpawnTask(
    task: Ref | None = None,
    *,
    arguments: Mapping[str, AuthorValue] | None = None,
    body: Sequence[Node] | None = None,
    uid: str | None = None,
) -> Node:
    values: dict[str, Any] = {}
    if task is not None:
        values["task"] = task
    if arguments:
        values["arguments"] = dict(arguments)
    children = {"body": list(body)} if body is not None else {}
    return _node("SpawnTask", arguments=values, children=children, uid=uid)


def Break(*, uid: str | None = None) -> Node:
    return _node("Break", uid=uid)


def Continue(*, uid: str | None = None) -> Node:
    return _node("Continue", uid=uid)


def Return(value: AuthorValue = None, *, uid: str | None = None) -> Node:
    return _node("Return", arguments={} if value is None else {"value": value}, uid=uid)


def Set(name: str, value: AuthorValue, *, uid: str | None = None) -> Node:
    return _node("Set", arguments={"name": name, "value": value}, uid=uid)


def Call(
    function: Ref,
    arguments: Sequence[AuthorValue] = (),
    keywords: Mapping[str, AuthorValue] | None = None,
    *,
    uid: str | None = None,
) -> Node:
    values: dict[str, Any] = {"function": function}
    if arguments:
        values["arguments"] = list(arguments)
    if keywords:
        values["keywords"] = dict(keywords)
    return _node("Call", arguments=values, uid=uid)


def RawPython(source: str, *, uid: str | None = None) -> Node:
    return _node("RawPython", arguments={"source": source}, uid=uid)


# ---------------------------------------------------------------------------
# Stage flow and runtime actions
# ---------------------------------------------------------------------------


def RunWave(wave_class: Ref, *, uid: str | None = None) -> Node:
    return _node("RunWave", arguments={"wave_class": wave_class}, uid=uid)


def RunBoss(boss_def: Ref, is_midboss: bool = False, *, uid: str | None = None) -> Node:
    arguments = {"boss_def": boss_def}
    if is_midboss:
        arguments["is_midboss"] = True
    return _node("RunBoss", arguments=arguments, uid=uid)


def SetBackground(name: str, *, uid: str | None = None) -> Node:
    return _node("SetBackground", arguments={"name": name}, uid=uid)


def PlayBGM(name: str, *, uid: str | None = None) -> Node:
    return _node("PlayBGM", arguments={"name": name}, uid=uid)


def PlayDialogue(
    dialogue_list: str | Expr | Sequence[AuthorValue],
    initial_delay_frames: int = 0,
    *,
    uid: str | None = None,
) -> Node:
    if isinstance(dialogue_list, Ref):
        raise TypeError("PlayDialogue.dialogue_list cannot be a logical-unit Ref")
    arguments = {"dialogue_list": dialogue_list}
    if initial_delay_frames:
        arguments["initial_delay_frames"] = initial_delay_frames
    return _node("PlayDialogue", arguments=arguments, uid=uid)


def SpawnEnemy(
    enemy_class: Ref,
    x: float | Expr = 0.0,
    y: float | Expr = 1.0,
    *,
    uid: str | None = None,
) -> Node:
    values: dict[str, Any] = {"enemy_class": enemy_class}
    if x != 0.0:
        values["x"] = x
    if y != 1.0:
        values["y"] = y
    return _node("SpawnEnemy", arguments=values, uid=uid)


def MoveTo(
    x: float | Expr,
    y: float | Expr,
    duration: int | Expr = 60,
    *,
    uid: str | None = None,
) -> Node:
    values: dict[str, Any] = {"x": x, "y": y}
    if duration != 60:
        values["duration"] = duration
    return _node("MoveTo", arguments=values, uid=uid)


def MoveLinear(
    dx: float | Expr,
    dy: float | Expr,
    duration: int | Expr = 60,
    *,
    uid: str | None = None,
) -> Node:
    values: dict[str, Any] = {"dx": dx, "dy": dy}
    if duration != 60:
        values["duration"] = duration
    return _node("MoveLinear", arguments=values, uid=uid)


def SetPosition(x: float | Expr, y: float | Expr, *, uid: str | None = None) -> Node:
    return _node("SetPosition", arguments={"x": x, "y": y}, uid=uid)


def _runtime_value(arguments: dict[str, Any], name: str, value: Any) -> None:
    if value is not RUNTIME_DEFAULT:
        arguments[name] = value


def Fire(
    x: float | Expr | None | _RuntimeDefault = RUNTIME_DEFAULT,
    y: float | Expr | None | _RuntimeDefault = RUNTIME_DEFAULT,
    angle: float | Expr | _RuntimeDefault = RUNTIME_DEFAULT,
    speed: float | Expr = 2.0,
    bullet_type: str = "ball_m",
    color: str = "red",
    accel: float | Expr = 0.0,
    angle_accel: float | Expr = 0.0,
    play_sound: bool = False,
    *,
    uid: str | None = None,
    **runtime_options: AuthorValue,
) -> Node:
    arguments: dict[str, Any] = {}
    _runtime_value(arguments, "x", x)
    _runtime_value(arguments, "y", y)
    _runtime_value(arguments, "angle", angle)
    arguments.update(
        _without_defaults(
            {
                "speed": speed,
                "bullet_type": bullet_type,
                "color": color,
                "accel": accel,
                "angle_accel": angle_accel,
                "play_sound": play_sound,
            },
            {
                "speed": 2.0,
                "bullet_type": "ball_m",
                "color": "red",
                "accel": 0.0,
                "angle_accel": 0.0,
                "play_sound": False,
            },
        )
    )
    arguments.update(runtime_options)
    return _node("Fire", arguments=arguments, uid=uid)


def FireCircle(
    x: float | Expr | None | _RuntimeDefault = RUNTIME_DEFAULT,
    y: float | Expr | None | _RuntimeDefault = RUNTIME_DEFAULT,
    count: int | Expr | _RuntimeDefault = RUNTIME_DEFAULT,
    speed: float | Expr = 2.0,
    start_angle: float | Expr = 0.0,
    play_sound: bool = True,
    *,
    uid: str | None = None,
    **runtime_options: AuthorValue,
) -> Node:
    arguments: dict[str, Any] = {}
    _runtime_value(arguments, "count", count)
    _runtime_value(arguments, "x", x)
    _runtime_value(arguments, "y", y)
    arguments.update(
        _without_defaults(
            {"speed": speed, "start_angle": start_angle, "play_sound": play_sound},
            {"speed": 2.0, "start_angle": 0.0, "play_sound": True},
        )
    )
    arguments.update(runtime_options)
    return _node("FireCircle", arguments=arguments, uid=uid)


def FireArc(
    x: float | Expr | None | _RuntimeDefault = RUNTIME_DEFAULT,
    y: float | Expr | None | _RuntimeDefault = RUNTIME_DEFAULT,
    count: int | Expr = 5,
    speed: float | Expr = 2.0,
    center_angle: float | Expr = -90.0,
    arc_angle: float | Expr = 60.0,
    play_sound: bool = True,
    *,
    uid: str | None = None,
    **runtime_options: AuthorValue,
) -> Node:
    arguments: dict[str, Any] = {}
    _runtime_value(arguments, "x", x)
    _runtime_value(arguments, "y", y)
    arguments.update(
        _without_defaults(
            {
                "count": count,
                "speed": speed,
                "center_angle": center_angle,
                "arc_angle": arc_angle,
                "play_sound": play_sound,
            },
            {
                "count": 5,
                "speed": 2.0,
                "center_angle": -90.0,
                "arc_angle": 60.0,
                "play_sound": True,
            },
        )
    )
    arguments.update(runtime_options)
    return _node("FireArc", arguments=arguments, uid=uid)


def FireAtPlayer(
    x: float | Expr | None | _RuntimeDefault = RUNTIME_DEFAULT,
    y: float | Expr | None | _RuntimeDefault = RUNTIME_DEFAULT,
    speed: float | Expr = 2.0,
    offset_angle: float | Expr = 0.0,
    play_sound: bool = True,
    *,
    uid: str | None = None,
    **runtime_options: AuthorValue,
) -> Node:
    arguments: dict[str, Any] = {}
    _runtime_value(arguments, "x", x)
    _runtime_value(arguments, "y", y)
    arguments.update(
        _without_defaults(
            {"speed": speed, "offset_angle": offset_angle, "play_sound": play_sound},
            {"speed": 2.0, "offset_angle": 0.0, "play_sound": True},
        )
    )
    arguments.update(runtime_options)
    return _node("FireAtPlayer", arguments=arguments, uid=uid)


def FirePolar(
    orbit_radius: float | Expr,
    theta: float | Expr,
    radial_speed: float | Expr = 0.0,
    angular_velocity: float | Expr = 0.0,
    bullet_type: str = "ball_m",
    color: str = "red",
    center: AuthorValue | _RuntimeDefault = RUNTIME_DEFAULT,
    render_mode: str = "velocity",
    angle_offset: float | Expr = 0.0,
    collision_radius: float | Expr = 0.0,
    play_sound: bool = False,
    *,
    uid: str | None = None,
    **runtime_options: AuthorValue,
) -> Node:
    arguments: dict[str, Any] = {"orbit_radius": orbit_radius, "theta": theta}
    _runtime_value(arguments, "center", center)
    arguments.update(
        _without_defaults(
            {
                "radial_speed": radial_speed,
                "angular_velocity": angular_velocity,
                "bullet_type": bullet_type,
                "color": color,
                "render_mode": render_mode,
                "angle_offset": angle_offset,
                "collision_radius": collision_radius,
                "play_sound": play_sound,
            },
            {
                "radial_speed": 0.0,
                "angular_velocity": 0.0,
                "bullet_type": "ball_m",
                "color": "red",
                "render_mode": "velocity",
                "angle_offset": 0.0,
                "collision_radius": 0.0,
                "play_sound": False,
            },
        )
    )
    arguments.update(runtime_options)
    return _node("FirePolar", arguments=arguments, uid=uid)


def FireOrbit(
    orbit_radius: float | Expr,
    theta: float | Expr,
    radial_speed: float | Expr = 0.0,
    angular_velocity: float | Expr = 0.0,
    bullet_type: str = "ball_m",
    color: str = "red",
    center: AuthorValue | _RuntimeDefault = RUNTIME_DEFAULT,
    render_mode: str = "velocity",
    angle_offset: float | Expr = 0.0,
    collision_radius: float | Expr = 0.0,
    play_sound: bool = False,
    *,
    uid: str | None = None,
    **runtime_options: AuthorValue,
) -> Node:
    orbit_uid = _uid("FireOrbit", uid)
    node = FirePolar(
        orbit_radius,
        theta,
        radial_speed,
        angular_velocity,
        bullet_type,
        color,
        center,
        render_mode,
        angle_offset,
        collision_radius,
        play_sound,
        uid=orbit_uid,
        **runtime_options,
    )
    node.kind = "FireOrbit"
    return node


def ClearBullets(to_items: bool = False, *, uid: str | None = None) -> Node:
    return _node(
        "ClearBullets",
        arguments={"to_items": True} if to_items else {},
        uid=uid,
    )


def Kill(*, uid: str | None = None) -> Node:
    return _node("Kill", uid=uid)


def PlaySE(
    name: str,
    volume: float | None = None,
    min_interval: float = 0.0,
    *,
    uid: str | None = None,
) -> Node:
    arguments: dict[str, Any] = {"name": name}
    if volume is not None:
        arguments["volume"] = volume
    if min_interval != 0.0:
        arguments["min_interval"] = min_interval
    return _node("PlaySE", arguments=arguments, uid=uid)


def CreateLaser(
    x: float | Expr,
    y: float | Expr,
    angle: float | Expr,
    l1: float | Expr,
    l2: float | Expr,
    l3: float | Expr,
    width: float | Expr,
    texture_id: str = "laser1",
    color: str | int = 1,
    on_time: int = 30,
    node: float = 0.0,
    head: float = 0.0,
    *,
    assign: str | None = None,
    uid: str | None = None,
) -> Node:
    arguments = {
        "x": x,
        "y": y,
        "angle": angle,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "width": width,
    }
    arguments.update(
        _without_defaults(
            {
                "texture_id": texture_id,
                "color": color,
                "on_time": on_time,
                "node": node,
                "head": head,
                "assign": assign,
            },
            {
                "texture_id": "laser1",
                "color": 1,
                "on_time": 30,
                "node": 0.0,
                "head": 0.0,
                "assign": None,
            },
        )
    )
    return _node("CreateLaser", arguments=arguments, uid=uid)


def CreateBentLaser(
    x: float | Expr,
    y: float | Expr,
    length: int | Expr,
    width: float | Expr,
    color: str | int = 1,
    on_time: int = 30,
    sample_rate: int = 4,
    *,
    assign: str | None = None,
    uid: str | None = None,
) -> Node:
    arguments = {"x": x, "y": y, "length": length, "width": width}
    arguments.update(
        _without_defaults(
            {
                "color": color,
                "on_time": on_time,
                "sample_rate": sample_rate,
                "assign": assign,
            },
            {"color": 1, "on_time": 30, "sample_rate": 4, "assign": None},
        )
    )
    return _node("CreateBentLaser", arguments=arguments, uid=uid)


def RemoveLaser(
    laser: Expr,
    off_time: int = 0,
    *,
    uid: str | None = None,
) -> Node:
    if not isinstance(laser, Expr):
        raise TypeError("RemoveLaser.laser must be Expr")
    arguments: dict[str, Any] = {"laser": laser}
    if off_time:
        arguments["off_time"] = off_time
    return _node("RemoveLaser", arguments=arguments, uid=uid)


def ClearLasers(*, uid: str | None = None) -> Node:
    return _node("ClearLasers", uid=uid)


UNIT_CONSTRUCTORS = {
    item.__name__: item
    for item in (Project, Stage, Wave, Enemy, Boss, Spell, NonSpell, Task, Function)
}
NODE_CONSTRUCTORS = {
    item.__name__: item
    for item in (
        Wait,
        At,
        Repeat,
        While,
        If,
        Else,
        ForEach,
        Parallel,
        SpawnTask,
        Break,
        Continue,
        Return,
        Set,
        Call,
        RawPython,
        RunWave,
        RunBoss,
        SetBackground,
        PlayBGM,
        PlayDialogue,
        SpawnEnemy,
        MoveTo,
        MoveLinear,
        SetPosition,
        Fire,
        FireCircle,
        FireArc,
        FireAtPlayer,
        FirePolar,
        FireOrbit,
        ClearBullets,
        Kill,
        PlaySE,
        CreateLaser,
        CreateBentLaser,
        RemoveLaser,
        ClearLasers,
    )
}
VALUE_CONSTRUCTORS = {"Ref": Ref, "Expr": Expr, "Parameter": Parameter}
PUBLIC_CONSTRUCTORS = {**UNIT_CONSTRUCTORS, **NODE_CONSTRUCTORS, **VALUE_CONSTRUCTORS}


from .templates import template  # noqa: E402  (templates depends only on program)


@template
def ring_burst(count: int = 12, interval: int = 6, bullet_count: int = 24, speed: float = 2.0):
    """Built-in retained ring burst used by the starter workflow."""

    return [
        Repeat(
            count,
            body=[FireCircle(count=bullet_count, speed=speed), Wait(interval)],
        )
    ]


BUILTIN_TEMPLATES = (ring_burst,)


__all__ = [
    "At",
    "Boss",
    "BUILTIN_TEMPLATES",
    "Break",
    "Call",
    "ClearBullets",
    "ClearLasers",
    "Continue",
    "CreateBentLaser",
    "CreateLaser",
    "Else",
    "Enemy",
    "Expr",
    "Fire",
    "FireArc",
    "FireAtPlayer",
    "FireCircle",
    "FireOrbit",
    "FirePolar",
    "ForEach",
    "Function",
    "If",
    "Kill",
    "MoveLinear",
    "MoveTo",
    "NODE_CONSTRUCTORS",
    "NonSpell",
    "PUBLIC_CONSTRUCTORS",
    "Parallel",
    "Parameter",
    "PlayBGM",
    "PlayDialogue",
    "PlaySE",
    "Project",
    "RUNTIME_DEFAULT",
    "RawPython",
    "Ref",
    "RemoveLaser",
    "Repeat",
    "Return",
    "RunBoss",
    "RunWave",
    "Set",
    "SetBackground",
    "SetPosition",
    "SpawnEnemy",
    "SpawnTask",
    "Spell",
    "Stage",
    "Task",
    "UNIT_CONSTRUCTORS",
    "VALUE_CONSTRUCTORS",
    "Wait",
    "Wave",
    "While",
    "template",
    "ring_burst",
]

import pytest

from src.authoring.dsl import (
    Boss,
    Break,
    Call,
    ClearBullets,
    CreateBentLaser,
    CreateLaser,
    Enemy,
    Expr,
    Fire,
    FireArc,
    FireAtPlayer,
    FireCircle,
    FireOrbit,
    FirePolar,
    Function,
    ForEach,
    If,
    Kill,
    MoveLinear,
    NonSpell,
    Parameter,
    Parallel,
    PlayBGM,
    PlayDialogue,
    PlaySE,
    Project,
    RawPython,
    Ref,
    Repeat,
    RemoveLaser,
    Return,
    RunBoss,
    RunWave,
    SpawnEnemy,
    SpawnTask,
    Spell,
    Stage,
    Set,
    SetBackground,
    Task,
    Wait,
    Wave,
)
from src.authoring.program import (
    AuthoringProgram,
    DropCheck,
    DropPlacement,
    Node,
    ProgramError,
    create_unit,
    delete_node,
    delete_unit,
    duplicate_unit,
    find_node,
    insert_node,
    insert_new_node,
    move_node,
    parse_author_value,
    set_argument,
    set_template_positional_argument,
    set_unit_field,
    validate_insert,
    wrap_node,
)


def test_author_value_text_parser_supports_ref_expr_containers_without_execution():
    assert parse_author_value(
        "[Ref('wave'), {'x': Expr('player_x')}, -2]"
    ) == [Ref("wave"), {"x": Expr("player_x")}, -2]
    with pytest.raises(ProgramError, match="unsupported author value expression"):
        parse_author_value("__import__('os').system('echo unsafe')")


def _complete_program():
    return AuthoringProgram.from_units(
        [
            Project("demo", "完整示例", Ref("stage_1"), [Ref("stage_1")]),
            Stage(
                "stage_1",
                "第一关",
                [Wait(60, uid="stage_wait"), RunWave(Ref("wave_1")), RunBoss(Ref("boss_1"))],
            ),
            Wave("wave_1", "开场", [SpawnEnemy(Ref("enemy_1"), uid="spawn_enemy")]),
            Enemy(
                "enemy_1",
                "妖精",
                [FireCircle(count=12, uid="enemy_fire"), Wait(6, uid="enemy_wait"), Kill()],
            ),
            Boss(
                "boss_1",
                "Boss",
                "boss_texture",
                [Ref("nonspell_1"), Ref("spell_1")],
            ),
            NonSpell("nonspell_1", body=[FireAtPlayer(), Wait(12)]),
            Spell(
                "spell_1",
                "环形符卡",
                [
                    Repeat(3, [FireCircle(count=24), Wait(5)], uid="spell_repeat"),
                    Parallel([[Wait(10)], [RawPython("value = 1")]], uid="spell_parallel"),
                ],
            ),
            Task(
                "burst_task",
                "参数化任务",
                [Parameter("count", "int", 3)],
                [Repeat(Expr("count"), [FireCircle(count=8)])],
            ),
            Function(
                "clamp_count",
                "限制数量",
                [Parameter("value", "int")],
                [If(Expr("value > 0"), [Return(Expr("value"))], [Return(0)])],
            ),
        ]
    )


def test_complete_nontrivial_program_validates_and_has_stable_semantics():
    program = _complete_program()

    assert program.validate() == ()
    program.assert_valid()
    assert program.clone().semantic_data() == program.semantic_data()
    assert {unit.kind for unit in program.logical_units()} == {
        "Project",
        "Stage",
        "Wave",
        "Enemy",
        "Boss",
        "NonSpell",
        "Spell",
        "Task",
        "Function",
    }


@pytest.mark.parametrize(
    ("factory", "required"),
    [
        pytest.param(lambda: Fire(uid="wave_fire"), ("x", "y"), id="fire"),
        pytest.param(
            lambda: FireCircle(uid="wave_fire_circle"),
            ("x", "y"),
            id="fire_circle",
        ),
        pytest.param(lambda: FireArc(uid="wave_fire_arc"), ("x", "y"), id="fire_arc"),
        pytest.param(
            lambda: FireAtPlayer(uid="wave_fire_at_player"),
            ("x", "y"),
            id="fire_at_player",
        ),
        pytest.param(
            lambda: FirePolar(1.0, 0.0, uid="wave_fire_polar"),
            ("center",),
            id="fire_polar",
        ),
        pytest.param(
            lambda: FireOrbit(1.0, 0.0, uid="wave_fire_orbit"),
            ("center",),
            id="fire_orbit",
        ),
        pytest.param(
            lambda: FireCircle(x=None, y=0.0, uid="wave_fire_circle_none"),
            ("x",),
            id="explicit_none",
        ),
    ],
)
def test_wave_fire_nodes_require_wave_runtime_context_arguments(factory, required):
    program = _complete_program()
    node = factory()
    program.get_unit("wave_1").body = [node]

    diagnostics = program.validate()

    for argument in required:
        assert any(
            item.uid == node.uid
            and item.code == "invalid_argument"
            and repr(argument) in item.message
            for item in diagnostics
        )


def test_wave_fire_nodes_accept_explicit_runtime_context_arguments():
    program = _complete_program()
    program.get_unit("wave_1").body = [
        Fire(x=0.0, y=0.0),
        FireCircle(x=0.0, y=0.0),
        FireArc(x=0.0, y=0.0),
        FireAtPlayer(x=0.0, y=0.0),
        FirePolar(1.0, 0.0, center=Expr("origin")),
        FireOrbit(1.0, 0.0, center=Expr("origin")),
    ]

    assert program.validate() == ()


def test_wave_rejects_clear_bullets_without_a_matching_runtime_api():
    program = _complete_program()
    clear = ClearBullets(to_items=True, uid="wave_clear")
    program.get_unit("wave_1").body = [clear]

    diagnostics = program.validate()

    assert any(
        item.uid == clear.uid and item.code == "illegal_parent"
        for item in diagnostics
    )

    supported = _complete_program()
    supported.get_unit("enemy_1").body = [ClearBullets(to_items=True)]
    supported.get_unit("spell_1").body = [ClearBullets(to_items=True)]
    assert supported.validate() == ()


def test_spawn_enemy_rejects_arguments_without_a_matching_runtime_parameter():
    with pytest.raises(TypeError, match="unexpected keyword argument 'arguments'"):
        SpawnEnemy(Ref("enemy_1"), arguments={"hp_scale": 2})

    program = _complete_program()
    spawn = Node(
        kind="SpawnEnemy",
        uid="spawn_arguments",
        arguments={"enemy_class": Ref("enemy_1"), "arguments": {"hp_scale": 2}},
    )
    program.get_unit("wave_1").body = [spawn]

    assert any(
        item.uid == spawn.uid and item.code == "invalid_argument"
        for item in program.validate()
    )


@pytest.mark.parametrize("unit_id", ["spell_1", "nonspell_1"])
def test_spell_phases_reject_move_linear_without_a_runtime_api(unit_id):
    program = _complete_program()
    move = MoveLinear(0.1, 0.0, uid=f"{unit_id}_move_linear")
    program.get_unit(unit_id).body = [move]

    assert any(
        item.uid == move.uid and item.code == "illegal_parent"
        for item in program.validate()
    )

    supported = _complete_program()
    supported.get_unit("enemy_1").body = [MoveLinear(0.1, 0.0)]
    assert supported.validate() == ()


def test_boss_rejects_body_without_an_existing_runtime_execution_hook():
    with pytest.raises(TypeError):
        Boss(
            "boss",
            "Boss",
            "boss_texture",
            [Ref("phase")],
            [PlaySE("boss_intro")],
        )

    program = _complete_program()
    program.get_unit("boss_1").body = [PlaySE("boss_intro")]

    assert any(
        item.unit_id == "boss_1" and item.code == "illegal_parent"
        for item in program.validate()
    )


def test_remove_laser_requires_an_expression_that_resolves_to_a_runtime_laser():
    with pytest.raises(TypeError, match="must be Expr"):
        RemoveLaser("laser_name")

    program = _complete_program()
    remove = Node(
        kind="RemoveLaser",
        uid="remove_literal",
        arguments={"laser": "laser_name"},
    )
    program.get_unit("enemy_1").body = [remove]
    assert any(
        item.uid == remove.uid and item.code == "invalid_argument"
        for item in program.validate()
    )

    supported = _complete_program()
    supported.get_unit("enemy_1").body = [RemoveLaser(Expr("laser_name"))]
    assert supported.validate() == ()


@pytest.mark.parametrize("assign", ["bad-name", "class", "", None])
def test_laser_assign_requires_a_non_keyword_python_identifier(assign):
    program = _complete_program()
    laser = CreateLaser(0, 0, 0, 1, 1, 1, 0.1, assign=assign, uid="laser_assign")
    program.get_unit("spell_1").body = [laser]

    if assign is None:
        assert program.validate() == ()
    else:
        assert any(
            item.uid == laser.uid and item.code == "invalid_target"
            for item in program.validate()
        )

    bent_program = _complete_program()
    bent = CreateBentLaser(0, 0, 10, 0.1, assign=assign, uid="bent_assign")
    bent_program.get_unit("spell_1").body = [bent]
    if assign is None:
        assert bent_program.validate() == ()
    else:
        assert any(
            item.uid == bent.uid and item.code == "invalid_target"
            for item in bent_program.validate()
        )


def test_boss_rejects_position_metadata_without_a_runtime_destination():
    with pytest.raises(TypeError, match="unexpected keyword argument 'x'"):
        Boss("boss", "Boss", "boss_texture", [Ref("phase")], x=0.25, y=0.75)

    program = _complete_program()
    program.get_unit("boss_1").metadata["x"] = 0.25

    assert any(
        item.unit_id == "boss_1" and item.code == "invalid_unit_field"
        for item in program.validate()
    )


def test_play_dialogue_rejects_logical_unit_references():
    with pytest.raises(TypeError, match="logical-unit Ref"):
        PlayDialogue(Ref("enemy_1"))

    program = _complete_program()
    dialogue = Node(
        kind="PlayDialogue",
        uid="dialogue_ref",
        arguments={"dialogue_list": Ref("enemy_1")},
    )
    program.get_unit("stage_1").body = [dialogue]

    assert any(
        item.uid == dialogue.uid and item.code == "invalid_argument"
        for item in program.validate()
    )

    supported = _complete_program()
    supported.get_unit("stage_1").body = [
        PlayDialogue([("character", "left", "text")])
    ]
    assert supported.validate() == ()


@pytest.mark.parametrize(
    "node",
    [
        pytest.param(PlayBGM(123, uid="bad_bgm"), id="bgm"),
        pytest.param(SetBackground(123, uid="bad_background"), id="background"),
        pytest.param(PlaySE(123, uid="bad_se"), id="se"),
    ],
)
def test_known_node_literals_must_match_dsl_type_annotations(node):
    program = _complete_program()
    program.get_unit("stage_1").body = [node]

    assert any(
        item.uid == node.uid and item.code == "invalid_argument"
        for item in program.validate()
    )


def test_known_unit_metadata_must_match_dsl_type_annotations():
    program = _complete_program()
    program.get_unit("stage_1").metadata["bgm"] = 123

    assert any(
        item.unit_id == "stage_1" and item.code == "invalid_unit_field"
        for item in program.validate()
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("ordinary string", id="ordinary_string"),
        pytest.param([1], id="scalar_item"),
        pytest.param([("character", "left")], id="short_tuple"),
        pytest.param([("character", "middle", "hello")], id="bad_tuple_position"),
        pytest.param([{"character": "demo"}], id="missing_text"),
        pytest.param([{"text": "hello", "unknown": 1}], id="unknown_field"),
        pytest.param([{"text": "hello", "position": "middle"}], id="bad_position"),
    ],
)
def test_play_dialogue_rejects_runtime_invalid_static_values(value):
    program = _complete_program()
    dialogue = PlayDialogue(value, uid="bad_dialogue")
    program.get_unit("stage_1").body = [dialogue]

    assert any(
        item.uid == dialogue.uid and item.code == "invalid_argument"
        for item in program.validate()
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("res://dialogue/intro.json", id="resource"),
        pytest.param(Expr("dialogue_sequence"), id="expression"),
        pytest.param([("character", "left", "hello")], id="tuple"),
        pytest.param(
            [{"text": "hello", "character": "demo", "position": "right"}],
            id="dict",
        ),
    ],
)
def test_play_dialogue_accepts_supported_static_and_dynamic_values(value):
    program = _complete_program()
    program.get_unit("stage_1").body = [PlayDialogue(value)]

    assert program.validate() == ()


def test_boss_metadata_mirrors_runtime_boss_definition_names():
    boss = Boss(
        "boss",
        "Boss",
        "boss_texture",
        [Ref("phase")],
        animations={"idle": [0, 1]},
    )

    assert boss.metadata == {
        "texture": "boss_texture",
        "phases": [Ref("phase")],
        "animations": {"idle": [0, 1]},
    }


def test_inline_spawn_task_rejects_arguments_without_a_receiver():
    program = AuthoringProgram.from_units(
        [
            Stage(
                "stage",
                "Stage",
                [SpawnTask(body=[Wait(1)], arguments={"count": 2}, uid="inline")],
            )
        ]
    )

    assert any(
        item.uid == "inline" and item.code == "invalid_spawn_task"
        for item in program.validate()
    )


@pytest.mark.parametrize(
    "node",
    [
        pytest.param(SpawnTask(Ref("task"), uid="task_missing"), id="task_missing"),
        pytest.param(
            SpawnTask(Ref("task"), arguments={"bogus": 1}, uid="task_unknown"),
            id="task_unknown",
        ),
        pytest.param(
            SpawnTask(Ref("task"), arguments={"count": "bad"}, uid="task_type"),
            id="task_type",
        ),
        pytest.param(Call(Ref("function"), uid="call_missing"), id="call_missing"),
        pytest.param(
            Call(Ref("function"), arguments=[1, 2], uid="call_extra"),
            id="call_extra",
        ),
        pytest.param(
            Call(Ref("function"), keywords={"bogus": 1}, uid="call_unknown"),
            id="call_unknown",
        ),
        pytest.param(
            Call(
                Ref("function"),
                arguments=[1],
                keywords={"value": 2},
                uid="call_duplicate",
            ),
            id="call_duplicate",
        ),
    ],
)
def test_task_and_function_calls_bind_target_parameters(node):
    program = AuthoringProgram.from_units(
        [
            Task("task", "Task", [Parameter("count", "int")]),
            Function("function", "Function", [Parameter("value", "int")]),
            Stage("stage", "Stage", [node]),
        ]
    )

    assert any(
        item.uid == node.uid and item.code == "call_signature"
        for item in program.validate()
    )


def test_task_and_function_calls_accept_valid_literals_defaults_and_exprs():
    program = AuthoringProgram.from_units(
        [
            Task(
                "task",
                "Task",
                [Parameter("count", "int"), Parameter("labels", "list[str]", [])],
            ),
            Function("function", "Function", [Parameter("value", "int")]),
            Stage(
                "stage",
                "Stage",
                [
                    SpawnTask(Ref("task"), arguments={"count": Expr("count")}),
                    Call(Ref("function"), arguments=[2]),
                ],
            ),
        ]
    )

    assert program.validate() == ()


def test_task_parameter_annotations_and_defaults_are_restricted_and_typed():
    with pytest.raises(ProgramError, match="does not match"):
        Task("bad", "Bad", [Parameter("count", "int", "bad")])
    with pytest.raises(ProgramError, match="unsupported parameter annotation"):
        Task("bad", "Bad", [Parameter("value", "CustomType")])


def test_validation_rejects_duplicate_ids_uids_bad_refs_and_bad_parent():
    duplicate_id = _complete_program().get_unit("stage_1").clone()
    duplicate_id.name = "重复"
    duplicate_uid = Wave("wave_2", "重复 UID", [Wait(1, uid="stage_wait")])
    bad_ref = Wave("wave_3", "坏引用", [SpawnEnemy(Ref("missing_enemy"))])
    bad_parent = Stage("stage_bad", "坏父子", [FireCircle(count=3)])
    program = AuthoringProgram.from_units(
        [*_complete_program().logical_units(), duplicate_id, duplicate_uid, bad_ref, bad_parent]
    )

    codes = {item.code for item in program.validate()}

    assert {"duplicate_unit_id", "duplicate_uid", "unresolved_reference", "illegal_parent"} <= codes


def test_reference_target_types_are_checked():
    program = _complete_program()
    stage = program.get_unit("stage_1")
    stage.body[1].arguments["wave_class"] = Ref("enemy_1")

    diagnostics = program.validate()

    assert any(item.code == "reference_type" and item.uid == stage.body[1].uid for item in diagnostics)


def test_copy_on_success_model_operations_cover_insert_move_wrap_delete_and_fields():
    original = _complete_program()
    inserted = insert_node(original, "stage_1", None, "body", 1, Wait(30, uid="inserted"))
    assert [node.uid for node in original.get_unit("stage_1").body] == [
        "stage_wait",
        original.get_unit("stage_1").body[1].uid,
        original.get_unit("stage_1").body[2].uid,
    ]
    assert [node.uid for node in inserted.get_unit("stage_1").body][1] == "inserted"

    changed = set_argument(inserted, "inserted", "frames", 45)
    assert find_node(changed, "inserted")[1].arguments["frames"] == 45
    assert find_node(inserted, "inserted")[1].arguments["frames"] == 30

    moved = move_node(changed, "inserted", "stage_wait", DropPlacement.BEFORE)
    assert [node.uid for node in moved.get_unit("stage_1").body][:2] == ["inserted", "stage_wait"]

    wrapped = wrap_node(moved, "stage_wait", Repeat(2, [], uid="wrapper"))
    wrapper = find_node(wrapped, "wrapper")[1]
    assert [node.uid for node in wrapper.children["body"]] == ["stage_wait"]

    renamed = set_unit_field(wrapped, "stage_1", "name", "改名关卡")
    assert renamed.get_unit("stage_1").name == "改名关卡"
    assert wrapped.get_unit("stage_1").name == "第一关"

    deleted = delete_node(renamed, "inserted")
    with pytest.raises(ProgramError, match="unknown node uid"):
        find_node(deleted, "inserted")


def test_failed_operation_leaves_original_unchanged():
    original = _complete_program()
    before = original.semantic_data()

    with pytest.raises(ProgramError):
        insert_node(original, "stage_1", None, "body", 99, Wait(1))
    with pytest.raises(ProgramError):
        wrap_node(original, "stage_wait", FireCircle(count=4))
    with pytest.raises(ProgramError):
        insert_node(original, "stage_1", None, "body", 0, Break())

    assert original.semantic_data() == before


def test_set_unit_parameters_reuses_duplicate_validation_and_is_copy_on_failure():
    original = _complete_program()
    before = original.semantic_data()

    with pytest.raises(ProgramError, match="duplicate parameter"):
        set_unit_field(
            original,
            "burst_task",
            "parameters",
            [Parameter("count", "int"), Parameter("count", "int")],
        )
    with pytest.raises(ProgramError, match="follows a default parameter"):
        set_unit_field(
            original,
            "burst_task",
            "parameters",
            [Parameter("optional", "int", 1), Parameter("required", "int")],
        )
    with pytest.raises(ProgramError, match="follows a default parameter"):
        Task(
            "bad_task",
            "Bad",
            [Parameter("optional", "int", 1), Parameter("required", "int")],
        )

    assert original.semantic_data() == before


def test_model_argument_edits_follow_dsl_signature_without_a_second_catalog():
    original = _complete_program()
    before = original.semantic_data()

    with pytest.raises(ProgramError):
        set_argument(original, "stage_wait", "bogus", 1)
    with pytest.raises(ProgramError, match="node identity"):
        set_argument(original, "enemy_fire", "uid", "other")

    explicit = set_argument(original, "enemy_fire", "speed", 3.0)
    normalized = set_argument(explicit, "enemy_fire", "speed", 2.0)
    assert find_node(explicit, "enemy_fire")[1].arguments["speed"] == 3.0
    assert "speed" not in find_node(normalized, "enemy_fire")[1].arguments

    malformed = AuthoringProgram.from_units(
        [Function("malformed", "Malformed", body=[Node("Wait", uid="missing_frames")])]
    )
    assert any(
        item.code == "invalid_argument"
        and item.uid == "missing_frames"
        and "requires argument" in item.message
        for item in malformed.validate()
    )
    assert original.semantic_data() == before


def test_missing_canonical_child_slots_block_insert_without_mutating_program():
    original = _complete_program()
    before = original.semantic_data()
    malformed = Node(
        "Repeat",
        arguments={"count": 2},
        children={},
        uid="missing_body",
    )

    with pytest.raises(ProgramError):
        insert_node(original, "burst_task", None, "body", 0, malformed)

    assert original.semantic_data() == before


def test_unit_metadata_edits_follow_constructor_signature_and_defaults():
    original = _complete_program()
    before = original.semantic_data()

    titled = set_unit_field(original, "stage_1", "title", "第一关")
    normalized = set_unit_field(titled, "stage_1", "title", "")

    assert titled.get_unit("stage_1").metadata["title"] == "第一关"
    assert "title" not in normalized.get_unit("stage_1").metadata
    with pytest.raises(ProgramError, match="no metadata field"):
        set_unit_field(original, "stage_1", "bogus", 1)
    with pytest.raises(ProgramError, match="does not accept parameters"):
        set_unit_field(original, "stage_1", "parameters", [Parameter("value")])
    assert original.semantic_data() == before


def test_template_call_keyword_and_existing_positional_arguments_are_editable():
    from src.authoring.dsl import ring_burst

    call = ring_burst(2, uid="template_call")
    program = AuthoringProgram.from_units(
        [Function("flow", "Flow", body=[call])]
    )

    keyword = set_argument(program, "template_call", "interval", 9)
    positional = set_template_positional_argument(keyword, "template_call", 0, 4)
    edited = find_node(positional, "template_call")[1]

    assert edited.arguments["interval"] == 9
    assert edited.positional_arguments == (4,)
    assert find_node(program, "template_call")[1].positional_arguments == (2,)
    with pytest.raises(ProgramError):
        set_template_positional_argument(program, "template_call", 1, 3)


def test_python_identifiers_reject_keywords_and_parameter_annotations_must_parse():
    with pytest.raises(ProgramError, match="parameter name"):
        Parameter("for")
    with pytest.raises(ProgramError, match="annotation"):
        Parameter("items", "list[")

    program = AuthoringProgram.from_units(
        [
            Function(
                "flow",
                "Flow",
                body=[
                    Set("class", 1, uid="bad_set"),
                    ForEach("return", [1], [], uid="bad_loop"),
                ],
            )
        ]
    )

    diagnostics = program.validate()
    assert {item.uid for item in diagnostics if item.code == "invalid_target"} == {
        "bad_set",
        "bad_loop",
    }


def test_spawn_task_presence_distinguishes_empty_inline_body_from_missing_or_both():
    target = Task("target_task", "Target", body=[])
    valid = Function(
        "valid_flow",
        "Valid",
        body=[SpawnTask(body=[], uid="empty_inline")],
    )
    invalid = Function(
        "invalid_flow",
        "Invalid",
        body=[
            SpawnTask(uid="missing_both"),
            SpawnTask(Ref("target_task"), body=[], uid="has_both"),
        ],
    )
    program = AuthoringProgram.from_units([target, valid, invalid])

    diagnostics = program.validate()

    assert not any(item.uid == "empty_inline" for item in diagnostics)
    assert {
        item.uid for item in diagnostics if item.code == "invalid_spawn_task"
    } == {"missing_both", "has_both"}


def test_parameter_defaults_participate_in_nested_reference_validation():
    target = Task("target_task", "Target")
    caller = Function(
        "caller",
        "Caller",
        parameters=[
            Parameter(
                "targets",
                "dict[str, list[Ref]]",
                {"valid": [Ref("target_task")], "missing": [Ref("missing_task")]},
            )
        ],
    )
    program = AuthoringProgram.from_units([target, caller])

    diagnostics = program.validate()

    unresolved = [item for item in diagnostics if item.code == "unresolved_reference"]
    assert len(unresolved) == 1
    assert "missing_task" in unresolved[0].message


def test_model_operations_can_repair_multiple_existing_errors_one_at_a_time():
    target = Enemy("enemy_1", "Enemy")
    wave = Wave(
        "wave_1",
        "Wave",
        [
            SpawnEnemy(Ref("missing_a"), uid="first_bad_ref"),
            SpawnEnemy(Ref("missing_b"), uid="second_bad_ref"),
        ],
    )
    program = AuthoringProgram.from_units([target, wave])
    assert len(
        [item for item in program.validate() if item.code == "unresolved_reference"]
    ) == 2

    first_fixed = set_argument(
        program, "first_bad_ref", "enemy_class", Ref("enemy_1")
    )
    assert len(
        [item for item in first_fixed.validate() if item.code == "unresolved_reference"]
    ) == 1
    fully_fixed = set_argument(
        first_fixed, "second_bad_ref", "enemy_class", Ref("enemy_1")
    )

    assert fully_fixed.validate() == ()
    assert len(
        [item for item in program.validate() if item.code == "unresolved_reference"]
    ) == 2


@pytest.mark.parametrize(
    "resource",
    (
        "res://../outside.png",
        "res://C:/outside.png",
        "res://assets\\bad.png",
        "res://asset.png#",
        "res://assets//bad.png",
        "res://assets/./bad.png",
    ),
)
def test_resource_values_must_be_canonical_project_relative_references(resource):
    with pytest.raises(ProgramError, match="resource"):
        Stage("bad", "Bad", background=resource)


@pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf")))
def test_author_values_reject_non_finite_floats(value):
    with pytest.raises(ProgramError, match="finite float"):
        Stage("bad", "Bad", title=value)


def test_move_supports_after_and_child_placements():
    function = Function(
        "flow",
        "流程",
        body=[
            Wait(1, uid="first"),
            Repeat(2, [], uid="loop"),
            Wait(3, uid="last"),
        ],
    )
    program = AuthoringProgram.from_units([function])

    after = move_node(program, "first", "last", DropPlacement.AFTER)
    assert [node.uid for node in after.get_unit("flow").body] == ["loop", "last", "first"]

    child = move_node(program, "last", "loop", DropPlacement.CHILD)
    assert [node.uid for node in child.get_unit("flow").body] == ["first", "loop"]
    assert [node.uid for node in find_node(child, "loop")[1].children["body"]] == ["last"]


def test_move_wrap_uses_the_dragged_empty_container_to_wrap_the_target():
    function = Function(
        "flow",
        "流程",
        body=[
            Repeat(2, [], uid="wrapper"),
            Wait(3, uid="target"),
            Wait(4, uid="after"),
        ],
    )
    program = AuthoringProgram.from_units([function])

    wrapped = move_node(program, "wrapper", "target", DropPlacement.WRAP)

    assert [node.uid for node in wrapped.get_unit("flow").body] == ["wrapper", "after"]
    assert [node.uid for node in find_node(wrapped, "wrapper")[1].children["body"]] == [
        "target"
    ]
    assert [node.uid for node in program.get_unit("flow").body] == [
        "wrapper",
        "target",
        "after",
    ]


def test_move_wrap_rejects_an_occupied_wrapper_without_mutating_the_program():
    function = Function(
        "flow",
        "流程",
        body=[
            Repeat(2, [Wait(1, uid="existing")], uid="wrapper"),
            Wait(3, uid="target"),
        ],
    )
    program = AuthoringProgram.from_units([function])
    before = program.semantic_data()

    with pytest.raises(ProgramError, match="wrapper target slot must be empty"):
        move_node(program, "wrapper", "target", DropPlacement.WRAP)

    assert program.semantic_data() == before


def test_new_node_insert_supports_root_slots_wrap_parallel_and_dry_run():
    program = AuthoringProgram.from_units(
        [Function("flow", "Flow", body=[If(True, [], [], uid="condition"), Wait(1, uid="tail")])]
    )

    root = insert_new_node(program, "flow", Wait(2, uid="root_wait"))
    child = insert_new_node(
        root, "flow", Wait(3, uid="else_wait"), "condition", DropPlacement.CHILD,
        target_slot="else_body",
    )
    wrapped = insert_new_node(
        child, "flow", Parallel([[]], uid="parallel"), "tail", DropPlacement.WRAP
    )
    branched = insert_new_node(
        wrapped, "flow", Wait(4, uid="branch_wait"), "parallel", DropPlacement.CHILD,
        target_slot="new_branch",
    )

    parallel = find_node(branched, "parallel")[1]
    assert [node.uid for node in find_node(branched, "condition")[1].children["else_body"]] == [
        "else_wait"
    ]
    assert [[node.uid for node in branch.children["body"]] for branch in parallel.children["branches"]] == [
        ["tail"], ["branch_wait"]
    ]
    assert validate_insert(branched, "flow", Fire(), "tail", DropPlacement.AFTER) == DropCheck(
        True
    )
    rejected = validate_insert(branched, "flow", RunWave(Ref("missing")), "tail")
    assert not rejected.allowed and "missing" in rejected.reason


def test_logical_unit_create_duplicate_and_delete_update_refs_and_uids():
    program = AuthoringProgram.from_units(
        [
            Project("demo", "Demo", Ref("stage_a"), [Ref("stage_a")]),
            Stage("stage_a", "A", [Wait(1, uid="source_wait")]),
            Task("task_a", "Task", body=[Call(Ref("task_a"), uid="self_ref")]),
        ]
    )

    created = create_unit(program, Stage("stage_b", "B"), register_stage=True)
    project = created.get_unit("demo")
    assert project.metadata["stages"] == [Ref("stage_a"), Ref("stage_b")]

    duplicated = duplicate_unit(created, "task_a", "task_b", "Task B")
    duplicate = duplicated.get_unit("task_b")
    assert duplicate.body[0].uid != "self_ref"
    assert duplicate.body[0].arguments["function"] == Ref("task_b")
    linked = create_unit(
        duplicated, Function("caller", "Caller", body=[Call(Ref("task_b"))])
    )

    deleted = delete_unit(linked, "stage_a", replacement_start_stage="stage_b")
    assert deleted.get_unit("demo").metadata == {
        "start_stage": Ref("stage_b"), "stages": [Ref("stage_b")]
    }
    with pytest.raises(ProgramError, match="referenced"):
        delete_unit(deleted, "task_b")

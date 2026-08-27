from __future__ import annotations

import textwrap

import pytest

from src.authoring.program import (
    AuthoringProgram,
    ProgramValidationError,
    TemplateTarget,
    make_template_call,
    set_argument,
    set_template_positional_argument,
)
from src.authoring.dsl import Wait as dsl_wait
from src.authoring.dsl import ring_burst as builtin_ring_burst
from src.authoring.python_source import (
    ExternalChange,
    SourceConflictError,
    SourceSaveError,
    check_external_change,
    load_authoring_project,
    load_python_source,
    resolve_external_conflict,
    save_python_source,
)


def _write(path, source: str, *, newline=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline=newline) as handle:
        handle.write(textwrap.dedent(source).lstrip())


def test_supported_source_gets_stable_uids_comments_and_round_trips(tmp_path):
    path = tmp_path / "stage.py"
    _write(
        path,
        """
        from src.authoring.dsl import FireCircle, RawPython, Repeat, Spell, Wait

        spell = Spell(
            id="spell_1",
            name="测试符卡",
            body=[
                # 开场等待
                Wait(60),  # 精确时间
                Repeat(
                    2,
                    body=[FireCircle(count=24), Wait(6)],
                ),
                RawPython("value = 1"),
            ],
        )
        """,
    )

    document = load_python_source(path, module_name="game_content.authoring.demo.stages.stage_1")
    assert not document.read_only
    first_uid = document.unit.body[0].uid
    second_load = load_python_source(
        path, module_name="game_content.authoring.demo.stages.stage_1"
    )
    assert first_uid.startswith("node_")
    assert second_load.unit.body[0].uid == first_uid
    assert document.unit.body[0].comments.leading == ("# 开场等待",)
    assert document.unit.body[0].comments.trailing == "# 精确时间"

    semantic = document.unit.semantic_data()
    document.mark_dirty()
    rendered = save_python_source(document)
    reopened = load_python_source(path, module_name=document.module_name)

    assert "uid=" in rendered
    assert "\r" not in path.read_text(encoding="utf-8")
    assert reopened.unit.semantic_data() == semantic
    assert reopened.unit.body[0].uid == first_uid
    assert "# 开场等待" in rendered and "# 精确时间" in rendered
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))

    reopened.mark_dirty()
    second = save_python_source(reopened)
    assert second == rendered


def test_non_ascii_node_keeps_trailing_comment_across_stable_round_trip(tmp_path):
    path = tmp_path / "stage.py"
    _write(
        path,
        """
        from src.authoring.dsl import PlayDialogue, Stage

        stage = Stage(
            "stage_1",
            "Stage",
            body=[PlayDialogue([("角色", "left", "中文对话")]),  # 保留中文行尾注释
            ],
        )
        """,
    )
    document = load_python_source(path, module_name="demo.stage")

    assert document.unit.body[0].comments.trailing == "# 保留中文行尾注释"
    document.mark_dirty()
    rendered = save_python_source(document)
    reopened = load_python_source(path, module_name=document.module_name)

    assert reopened.unit.body[0].comments.trailing == "# 保留中文行尾注释"
    assert "# 保留中文行尾注释" in rendered
    reopened.mark_dirty()
    assert save_python_source(reopened) == rendered


def test_save_refreshes_in_memory_spans_and_source_state_without_reopen(tmp_path):
    path = tmp_path / "stage.py"
    _write(
        path,
        "from src.authoring.dsl import Stage, Wait\n"
        "stage=Stage('stage_1','Stage',[Wait(1)])\n",
    )
    document = load_python_source(path, module_name="demo.stage")
    old_span = document.unit.body[0].source_span
    document.mark_dirty()

    rendered = save_python_source(document)
    reopened = load_python_source(path, module_name=document.module_name)

    assert document.unit.body[0].source_span != old_span
    assert document.unit.source_span == reopened.unit.source_span
    assert document.unit.body[0].source_span == reopened.unit.body[0].source_span
    assert document.unit.body[0].comments == reopened.unit.body[0].comments
    assert document.imports == reopened.imports
    assert document.templates == reopened.templates
    assert document.prefix_text == reopened.prefix_text
    assert document.suffix_text == reopened.suffix_text
    assert document.text == rendered == reopened.text


def test_atomic_replace_failure_preserves_disk_and_document_state(tmp_path, monkeypatch):
    path = tmp_path / "stage.py"
    _write(path, "from src.authoring.dsl import Stage\nstage=Stage('stage_1','Stage')\n")
    document = load_python_source(path, module_name="demo.stage")
    original_bytes = path.read_bytes()
    original_digest = document.disk_digest
    original_raw = document.raw_bytes
    document.unit.name = "Changed"
    document.mark_dirty()

    def fail_replace(_source, _target):
        raise OSError("injected replace failure")

    monkeypatch.setattr("src.authoring.python_source.os.replace", fail_replace)

    with pytest.raises(SourceSaveError) as caught:
        save_python_source(document)

    assert caught.value.code == "atomic_save_failed"
    assert path.read_bytes() == original_bytes
    assert document.raw_bytes == original_raw
    assert document.disk_digest == original_digest
    assert document.dirty
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_setting_argument_back_to_dsl_default_saves_canonical_semantics(tmp_path):
    path = tmp_path / "enemy.py"
    _write(
        path,
        "from src.authoring.dsl import Enemy, FireCircle\n"
        "enemy = Enemy('enemy_1', 'Enemy', [FireCircle(count=12, uid='fire')])\n",
    )
    document = load_python_source(path, module_name="demo.enemies.enemy_1")
    program = AuthoringProgram.from_units([document.unit])
    program = set_argument(program, "fire", "speed", 3.0)
    program = set_argument(program, "fire", "speed", 2.0)
    document.unit = program.get_unit("enemy_1")
    document.mark_dirty()

    rendered = save_python_source(document, program=program)
    reopened = load_python_source(path, module_name=document.module_name)

    assert "speed=" not in rendered
    assert document.unit.semantic_data() == program.get_unit("enemy_1").semantic_data()
    assert reopened.unit.semantic_data() == document.unit.semantic_data()


def test_setting_unit_field_back_to_default_saves_canonical_semantics(tmp_path):
    path = tmp_path / "stage.py"
    _write(path, "from src.authoring.dsl import Stage\nstage=Stage('stage_1','Stage')\n")
    document = load_python_source(path, module_name="demo.stages.stage_1")
    program = AuthoringProgram.from_units([document.unit])
    from src.authoring.program import set_unit_field

    program = set_unit_field(program, "stage_1", "title", "Title")
    program = set_unit_field(program, "stage_1", "title", "")
    document.unit = program.get_unit("stage_1")
    document.mark_dirty()

    rendered = save_python_source(document, program=program)
    reopened = load_python_source(path, module_name=document.module_name)

    assert "title=" not in rendered
    assert reopened.unit.semantic_data() == document.unit.semantic_data()


def test_external_template_arguments_edit_save_and_reopen_without_resolution(tmp_path):
    path = tmp_path / "stage.py"
    _write(
        path,
        "from src.authoring.dsl import Stage\n"
        "from missing_templates import burst\n"
        "stage=Stage('stage_1','Stage',[burst(2, interval=3, uid='call')])\n",
    )
    document = load_python_source(path, module_name="demo.stage")
    program = AuthoringProgram.from_units([document.unit])
    program = set_argument(program, "call", "interval", 7)
    program = set_template_positional_argument(program, "call", 0, 5)
    document.unit = program.get_unit("stage_1")
    document.mark_dirty()

    rendered = save_python_source(document, program=program)
    reopened = load_python_source(path, module_name=document.module_name)
    call = reopened.unit.body[0]

    assert "burst(5, interval=7" in rendered
    assert call.positional_arguments == (5,)
    assert call.arguments == {"interval": 7}


def test_project_save_refreshes_program_spans_to_match_fresh_disk(tmp_path):
    root = tmp_path / "game_content" / "authoring" / "demo"
    _write(
        root / "project.py",
        "from src.authoring.dsl import Project, Ref\n"
        "project=Project('demo','Demo',Ref('stage_1'),[Ref('stage_1')])\n",
    )
    _write(
        root / "stages" / "stage_1.py",
        "from src.authoring.dsl import Stage, Wait\n"
        "stage=Stage('stage_1','Stage',[Wait(1,uid='wait')])\n",
    )
    project = load_authoring_project(root)
    document = project.file_for_unit("stage_1")
    old_span = project.program.get_unit("stage_1").body[0].source_span
    document.mark_dirty()

    project.save_unit("stage_1")
    fresh = load_authoring_project(root)

    saved_span = project.program.get_unit("stage_1").body[0].source_span
    assert saved_span != old_span
    assert saved_span == fresh.program.get_unit("stage_1").body[0].source_span
    assert project.program.get_unit("stage_1") is document.unit


@pytest.mark.parametrize(
    "body",
    (
        "for item in []:\n    pass\n",
        "if True:\n    value = 1\n",
        "open('file.txt', 'w')\n",
        "stage = Stage(id='a', name='A')\nother = Stage(id='b', name='B')\n",
    ),
)
def test_unsupported_top_level_python_is_read_only_and_never_overwritten(tmp_path, body):
    path = tmp_path / "unsupported.py"
    original = ("from src.authoring.dsl import Stage\n" + body).encode("utf-8")
    path.write_bytes(original)

    document = load_python_source(path)

    assert document.read_only
    assert document.raw_bytes == original
    with pytest.raises(SourceSaveError, match="read-only"):
        save_python_source(document)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "source",
    (
        "from src.authoring.dsl import Wave, SpawnEnemy, Ref\n"
        "wave = Wave('wave_1', 'Wave', body=["
        "SpawnEnemy(Ref('enemy_1'), arguments={'hp_scale': 2})])\n",
        "from src.authoring.dsl import Boss, PlaySE, Ref\n"
        "boss = Boss('boss_1', 'Boss', 'boss_texture', [Ref('phase_1')], "
        "body=[PlaySE('boss_intro')])\n",
        "from src.authoring.dsl import Enemy, RemoveLaser\n"
        "enemy = Enemy('enemy_1', 'Enemy', body=[RemoveLaser('laser_name')])\n",
        "from src.authoring.dsl import Boss, Ref\n"
        "boss = Boss('boss_1', 'Boss', 'boss_texture', [Ref('phase_1')], "
        "x=0.25, y=0.75)\n",
        "from src.authoring.dsl import PlayDialogue, Ref, Stage\n"
        "stage = Stage('stage_1', 'Stage', body=["
        "PlayDialogue(Ref('enemy_1'))])\n",
    ),
)
def test_runtime_unmappable_constructor_shapes_are_read_only_and_preserved(
    tmp_path, source
):
    path = tmp_path / "unsupported_runtime_shape.py"
    original = source.encode("utf-8")
    path.write_bytes(original)

    document = load_python_source(path)

    assert document.read_only
    assert document.raw_bytes == original
    with pytest.raises(SourceSaveError, match="read-only"):
        save_python_source(document)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "arguments",
    (
        "count=1, count=2",
        "uid='first', uid='second'",
    ),
)
def test_duplicate_template_keywords_are_read_only_and_preserved(tmp_path, arguments):
    path = tmp_path / "duplicate_template_keyword.py"
    original = (
        "from src.authoring.dsl import Stage\n"
        "from missing_templates import ring\n"
        f"stage = Stage('stage_1', 'Stage', body=[ring({arguments})])\n"
    ).encode("utf-8")
    path.write_bytes(original)

    document = load_python_source(path)

    assert document.read_only
    assert document.raw_bytes == original
    with pytest.raises(SourceSaveError, match="read-only"):
        save_python_source(document)
    assert path.read_bytes() == original


def test_clean_external_unsupported_change_is_reloaded_and_never_overwritten(tmp_path):
    path = tmp_path / "stage.py"
    _write(path, "from src.authoring.dsl import Stage\nstage = Stage('s', 'Old')\n")
    document = load_python_source(path)
    external = b"open('external.txt', 'w')\n"
    path.write_bytes(external)

    with pytest.raises(SourceSaveError, match="externally changed"):
        save_python_source(document)

    assert path.read_bytes() == external
    assert document.read_only
    assert document.raw_bytes == external


def test_clean_external_supported_change_reloads_without_rewriting(tmp_path):
    path = tmp_path / "stage.py"
    _write(path, "from src.authoring.dsl import Stage\nstage = Stage('s', 'Old')\n")
    document = load_python_source(path)
    external = b"from src.authoring.dsl import Stage\nstage = Stage('s', 'External')\n"
    path.write_bytes(external)

    returned = save_python_source(document)

    assert path.read_bytes() == external
    assert returned == external.decode("utf-8")
    assert document.unit.name == "External"
    assert not document.dirty


@pytest.mark.parametrize(
    ("source", "supported"),
    (
        (
            "from src.authoring.dsl import Stage\n"
            "from pathlib import Path as Stage\n"
            "stage = Stage(id='s', name='S', body=[])\n",
            False,
        ),
        (
            "from pathlib import Path as Stage\n"
            "from src.authoring.dsl import Stage\n"
            "stage = Stage(id='s', name='S', body=[])\n",
            True,
        ),
        (
            "from src.authoring.dsl import Stage\n"
            "stage = Stage(id='s', name='S', body=[])\n"
            "from pathlib import Path as Stage\n",
            True,
        ),
    ),
)
def test_constructor_alias_resolution_follows_python_binding_order(
    tmp_path, source, supported
):
    path = tmp_path / "binding_order.py"
    path.write_text(source, encoding="utf-8", newline="")

    document = load_python_source(path)

    assert (not document.read_only) is supported


def test_template_decorator_alias_can_be_shadowed_by_a_later_import(tmp_path):
    path = tmp_path / "template_shadow.py"
    path.write_text(
        "from src.authoring.dsl import Stage, template\n"
        "from pathlib import Path as template\n"
        "@template\n"
        "def helper():\n"
        "    return []\n"
        "stage = Stage('s', 'S')\n",
        encoding="utf-8",
        newline="",
    )

    assert load_python_source(path).read_only


def test_non_finite_float_literal_is_read_only_and_preserved_byte_for_byte(tmp_path):
    path = tmp_path / "stage.py"
    original = (
        "from src.authoring.dsl import Stage\n"
        "stage = Stage('stage_1', 'Stage', title=1e309)\n"
    ).encode("utf-8")
    path.write_bytes(original)

    document = load_python_source(path, module_name="demo.stage")

    assert document.read_only
    assert document.raw_bytes == original
    with pytest.raises(SourceSaveError):
        save_python_source(document)
    assert path.read_bytes() == original


def test_clean_external_change_reloads_and_dirty_change_requires_explicit_choice(tmp_path):
    path = tmp_path / "wave.py"
    _write(path, "from src.authoring.dsl import Wave\nwave = Wave('wave_1', '一')\n")
    clean = load_python_source(path, module_name="demo.wave")

    _write(path, "from src.authoring.dsl import Wave\nwave = Wave('wave_1', '二')\n")
    outcome, reloaded = check_external_change(clean)
    assert outcome == ExternalChange.RELOADED
    assert reloaded.unit.name == "二"

    reloaded.unit.name = "内存版本"
    reloaded.mark_dirty()
    _write(path, "from src.authoring.dsl import Wave\nwave = Wave('wave_1', '磁盘版本')\n")
    outcome, conflicted = check_external_change(reloaded)
    assert outcome == ExternalChange.CONFLICT
    with pytest.raises(SourceConflictError):
        save_python_source(conflicted)

    kept = resolve_external_conflict(conflicted, "keep")
    save_python_source(kept)
    assert load_python_source(path).unit.name == "内存版本"

    kept.unit.name = "未保存"
    kept.mark_dirty()
    _write(path, "from src.authoring.dsl import Wave\nwave = Wave('wave_1', '最终磁盘')\n")
    check_external_change(kept)
    disk = resolve_external_conflict(kept, "reload")
    assert disk.unit.name == "最终磁盘"
    assert not disk.dirty and not disk.conflict


def test_dirty_external_deletion_is_a_conflict_and_never_raises_a_raw_file_error(tmp_path):
    path = tmp_path / "wave.py"
    _write(path, "from src.authoring.dsl import Wave\nwave = Wave('wave_1', '一')\n")
    document = load_python_source(path, module_name="demo.wave")
    document.unit.name = "内存版本"
    document.mark_dirty()
    path.unlink()

    outcome, conflicted = check_external_change(document)

    assert outcome == ExternalChange.CONFLICT
    with pytest.raises(SourceConflictError):
        save_python_source(conflicted)
    kept = resolve_external_conflict(conflicted, "keep")
    save_python_source(kept)
    assert load_python_source(path).unit.name == "内存版本"


def test_clean_external_deletion_becomes_read_only_diagnostic(tmp_path):
    path = tmp_path / "wave.py"
    _write(path, "from src.authoring.dsl import Wave\nwave = Wave('wave_1', '一')\n")
    document = load_python_source(path, module_name="demo.wave")
    path.unlink()

    outcome, missing = check_external_change(document)

    assert outcome == ExternalChange.RELOADED
    assert missing.read_only
    assert "deleted externally" in missing.diagnostics[0].message


def test_project_load_validates_cross_file_references_and_duplicate_ids(tmp_path):
    root = tmp_path / "game_content" / "authoring" / "demo"
    _write(
        root / "project.py",
        """
        from src.authoring.dsl import Project, Ref
        project = Project("demo", "Demo", Ref("stage_1"), [Ref("stage_1")])
        """,
    )
    _write(
        root / "stages" / "stage_1.py",
        """
        from src.authoring.dsl import Ref, RunWave, Stage
        stage = Stage("stage_1", "Stage", [RunWave(Ref("wave_1"))])
        """,
    )
    _write(
        root / "waves" / "wave_1.py",
        """
        from src.authoring.dsl import Wave, Wait
        wave = Wave("wave_1", "Wave", [Wait(1)])
        """,
    )

    project = load_authoring_project(root)

    assert project.program.validate() == ()
    assert project.file_for_unit("stage_1").module_name.endswith("demo.stages.stage_1")
    assert isinstance(project.program, AuthoringProgram)


def test_supported_import_styles_and_external_template_alias_are_preserved(tmp_path):
    path = tmp_path / "stage.py"
    _write(
        path,
        """
        import src.authoring.dsl as dsl
        from missing_explicit_template_package import burst as external_burst

        stage = dsl.Stage(
            "stage_1",
            "Stage",
            [external_burst(count=3)],
        )
        """,
    )

    document = load_python_source(path, module_name="demo.stage")

    assert not document.read_only
    call = document.unit.body[0]
    assert call.kind == "TemplateCall"
    assert call.template.identity == "missing_explicit_template_package.burst"
    assert call.template.display_name == "external_burst"
    document.mark_dirty()
    rendered = save_python_source(document)
    assert "external_burst(count=3" in rendered


@pytest.mark.parametrize(
    "source",
    (
        """
        import src.authoring.dsl as dsl

        stage = dsl.Stage("stage_1", "Stage", [dsl.Wait(3)])
        """,
        """
        from src.authoring.dsl import Stage as S, Wait as W

        stage = S("stage_1", "Stage", [W(3)])
        """,
    ),
)
def test_dsl_import_aliases_save_to_executable_canonical_source(tmp_path, source):
    path = tmp_path / "stage.py"
    _write(path, source)
    document = load_python_source(path, module_name="demo.stage")
    before = document.unit.semantic_data()
    document.mark_dirty()

    rendered = save_python_source(document)
    compile(rendered, str(path), "exec")
    namespace = {}
    exec(rendered, namespace)
    reopened = load_python_source(path, module_name=document.module_name)

    assert namespace["stage"].semantic_data() == before
    assert reopened.unit.semantic_data() == before
    assert "from src.authoring.dsl import Stage, Wait" in rendered
    reopened.mark_dirty()
    assert save_python_source(reopened) == rendered


def test_save_rebinds_dsl_name_shadowed_before_assignment(tmp_path):
    path = tmp_path / "stage.py"
    _write(
        path,
        """
        import src.authoring.dsl as d
        from src.authoring.dsl import Wait
        from pathlib import Path as Wait

        stage = d.Stage("stage_1", "Stage", body=[])
        """,
    )
    document = load_python_source(path, module_name="demo.stage")
    document.unit.body.append(dsl_wait(4, uid="inserted_wait"))
    before = document.unit.semantic_data()
    document.mark_dirty()

    rendered = save_python_source(document)
    namespace = {}
    exec(compile(rendered, str(path), "exec"), namespace)
    reopened = load_python_source(path, module_name=document.module_name)

    assert namespace["stage"].semantic_data() == before
    assert reopened.unit.semantic_data() == before
    assert rendered.rfind("from src.authoring.dsl import Stage, Wait") < rendered.index("stage = Stage(")
    reopened.mark_dirty()
    assert save_python_source(reopened) == rendered


def test_import_after_assignment_is_not_treated_as_an_active_dsl_binding(tmp_path):
    path = tmp_path / "stage.py"
    _write(
        path,
        """
        import src.authoring.dsl as d

        stage = d.Stage("stage_1", "Stage", body=[])

        from src.authoring.dsl import Stage
        """,
    )
    document = load_python_source(path, module_name="demo.stage")
    before = document.unit.semantic_data()
    document.mark_dirty()

    rendered = save_python_source(document)
    namespace = {}
    exec(compile(rendered, str(path), "exec"), namespace)
    reopened = load_python_source(path, module_name=document.module_name)

    assert namespace["stage"].semantic_data() == before
    assert rendered.index("from src.authoring.dsl import Stage") < rendered.index("stage = Stage(")
    reopened.mark_dirty()
    assert save_python_source(reopened) == rendered


def test_local_template_shadowing_unit_name_is_rebound_before_assignment(tmp_path):
    path = tmp_path / "stage.py"
    _write(
        path,
        """
        import src.authoring.dsl as d

        @d.template
        def Stage():
            return []

        stage = d.Stage("stage_1", "Stage", body=[])
        """,
    )
    document = load_python_source(path, module_name="demo.stage")
    before = document.unit.semantic_data()
    document.mark_dirty()

    rendered = save_python_source(document)
    namespace = {}
    exec(compile(rendered, str(path), "exec"), namespace)
    reopened = load_python_source(path, module_name=document.module_name)

    assert namespace["stage"].semantic_data() == before
    assert rendered.index("def Stage()") < rendered.index("from src.authoring.dsl import Stage")
    assert rendered.index("from src.authoring.dsl import Stage") < rendered.index("stage = Stage(")
    reopened.mark_dirty()
    assert save_python_source(reopened) == rendered


def test_save_is_stable_when_canonical_import_was_inserted_before_assignment(tmp_path):
    path = tmp_path / "stage.py"
    _write(
        path,
        """
        import src.authoring.dsl as d
        from pathlib import Path as Stage

        stage = d.Stage("stage_1", "Stage", body=[])
        """,
    )
    document = load_python_source(path, module_name="demo.stage")
    document.mark_dirty()

    first = save_python_source(document)
    document.mark_dirty()
    second = save_python_source(document)

    assert second == first
    assert first.count("from src.authoring.dsl import Stage") == 1


@pytest.mark.parametrize(
    "source",
    (
        """
        import src.authoring.dsl as d
        from missing_templates import burst
        from pathlib import Path as burst
        stage = d.Stage("stage_1", "Stage", body=[])
        """,
        """
        import src.authoring.dsl as d
        import missing_templates as templates
        import pathlib as templates
        stage = d.Stage("stage_1", "Stage", body=[])
        """,
        """
        import src.authoring.dsl as d
        stage = d.Stage("stage_1", "Stage", body=[])
        from missing_templates import burst
        """,
    ),
)
def test_inactive_historical_template_import_does_not_authorize_save(tmp_path, source):
    path = tmp_path / "stage.py"
    _write(path, source)
    document = load_python_source(path, module_name="demo.stage")
    display_name = "templates.burst" if "as templates" in source else "burst"
    document.unit.body.append(
        make_template_call(
            TemplateTarget(
                identity="missing_templates.burst",
                symbol="burst",
                display_name=display_name,
                module="missing_templates",
            ),
            uid="inserted_template",
        )
    )
    original = path.read_bytes()
    document.mark_dirty()

    with pytest.raises(SourceSaveError) as caught:
        save_python_source(document)

    assert caught.value.code == "template_not_imported"
    assert path.read_bytes() == original


def test_required_dsl_import_never_silently_shadows_template_call(tmp_path):
    path = tmp_path / "stage.py"
    _write(
        path,
        """
        import src.authoring.dsl as d
        from missing_templates import Stage

        stage = d.Stage("stage_1", "Stage", body=[])
        """,
    )
    document = load_python_source(path, module_name="demo.stage")
    document.unit.body.append(
        make_template_call(
            TemplateTarget(
                identity="missing_templates.Stage",
                symbol="Stage",
                display_name="Stage",
                module="missing_templates",
            ),
            uid="inserted_stage_template",
        )
    )
    original = path.read_bytes()
    document.mark_dirty()

    with pytest.raises(SourceSaveError) as caught:
        save_python_source(document)

    assert caught.value.code == "template_binding_conflict"
    assert path.read_bytes() == original


def test_source_template_call_colliding_with_required_dsl_name_is_read_only(tmp_path):
    path = tmp_path / "stage.py"
    original = (
        "import src.authoring.dsl as d\n"
        "@d.template\n"
        "def Wait():\n"
        "    return []\n"
        "stage = d.Stage('s', 'S', body=[d.Wait(1), Wait()])\n"
    ).encode("utf-8")
    path.write_bytes(original)

    document = load_python_source(path, module_name="demo.stage")

    assert document.read_only
    assert document.raw_bytes == original
    assert "conflicts with required DSL name" in document.diagnostics[0].message
    with pytest.raises(SourceSaveError):
        save_python_source(document)
    assert path.read_bytes() == original


def test_builtin_template_alias_colliding_with_required_dsl_name_is_read_only(tmp_path):
    path = tmp_path / "stage.py"
    original = (
        "import src.authoring.dsl as d\n"
        "from src.authoring.dsl import ring_burst as Wait\n"
        "stage = d.Stage('s', 'S', body=[d.Wait(1), Wait()])\n"
    ).encode("utf-8")
    path.write_bytes(original)

    document = load_python_source(path, module_name="demo.stage")

    assert document.read_only
    assert document.raw_bytes == original
    assert "conflicts with required DSL name" in document.diagnostics[0].message
    with pytest.raises(SourceSaveError):
        save_python_source(document)
    assert path.read_bytes() == original


def test_inserted_builtin_template_gets_import_and_round_trips_as_a_call(tmp_path):
    path = tmp_path / "stage.py"
    _write(path, "from src.authoring.dsl import Stage\nstage = Stage('stage_1', 'Stage')\n")
    document = load_python_source(path, module_name="demo.stage")
    document.unit.body.append(builtin_ring_burst(count=2, uid="builtin_call"))
    before = document.unit.semantic_data()
    document.mark_dirty()

    rendered = save_python_source(document)
    namespace = {}
    exec(compile(rendered, str(path), "exec"), namespace)
    reopened = load_python_source(path, module_name=document.module_name)

    assert "ring_burst" in rendered
    executed_call = namespace["stage"].body[0]
    assert executed_call.template.identity == "src.authoring.dsl.ring_burst"
    assert executed_call.arguments == {"count": 2}
    assert executed_call.uid == document.unit.body[0].uid
    assert reopened.unit.semantic_data() == before
    assert reopened.unit.body[0].kind == "TemplateCall"


@pytest.mark.parametrize(
    ("import_line", "stage_name", "template_name"),
    (
        ("import src.authoring.dsl as dsl", "dsl.Stage", "dsl.ring_burst"),
        (
            "import src.authoring.dsl",
            "src.authoring.dsl.Stage",
            "src.authoring.dsl.ring_burst",
        ),
    ),
)
def test_builtin_template_through_explicit_dsl_module_import_round_trips(
    tmp_path, import_line, stage_name, template_name
):
    path = tmp_path / "stage.py"
    _write(
        path,
        f"""
        {import_line}

        stage = {stage_name}(
            "stage_1",
            "Stage",
            [{template_name}(count=2)],
        )
        """,
    )
    document = load_python_source(path, module_name="demo.stage")
    before = document.unit.semantic_data()
    document.mark_dirty()

    rendered = save_python_source(document)
    namespace = {}
    exec(compile(rendered, str(path), "exec"), namespace)
    reopened = load_python_source(path, module_name=document.module_name)

    executed_call = namespace["stage"].body[0]
    assert executed_call.template.identity == "src.authoring.dsl.ring_burst"
    assert executed_call.arguments == {"count": 2}
    assert executed_call.uid == document.unit.body[0].uid
    assert reopened.unit.semantic_data() == before
    assert reopened.unit.body[0].kind == "TemplateCall"


def test_inserted_external_template_without_import_is_blocked_before_write(tmp_path):
    path = tmp_path / "stage.py"
    _write(path, "from src.authoring.dsl import Stage\nstage = Stage('stage_1', 'Stage')\n")
    document = load_python_source(path, module_name="demo.stage")
    original = path.read_bytes()
    from src.authoring.program import TemplateTarget, make_template_call

    document.unit.body.append(
        make_template_call(
            TemplateTarget(
                identity="external_templates.burst",
                symbol="burst",
                module="external_templates",
            ),
            uid="external_call",
        )
    )
    document.mark_dirty()

    with pytest.raises(SourceSaveError) as caught:
        save_python_source(document)

    assert caught.value.code == "template_not_imported"
    assert path.read_bytes() == original


def test_unimported_bare_dsl_constructor_is_read_only_and_never_rewritten(tmp_path):
    path = tmp_path / "stage.py"
    original = b"stage = Stage('stage_1', 'Stage')\n"
    path.write_bytes(original)

    document = load_python_source(path, module_name="demo.stage")

    assert document.read_only
    assert document.raw_bytes == original
    with pytest.raises(SourceSaveError):
        save_python_source(document)
    assert path.read_bytes() == original


def test_unimported_template_decorator_is_also_read_only(tmp_path):
    path = tmp_path / "stage.py"
    original = (
        "from src.authoring.dsl import Stage\n\n"
        "@template\n"
        "def burst():\n"
        "    return []\n\n"
        "stage = Stage('stage_1', 'Stage')\n"
    ).encode("utf-8")
    path.write_bytes(original)

    document = load_python_source(path, module_name="demo.stage")

    assert document.read_only
    assert document.raw_bytes == original


@pytest.mark.parametrize("uid_source", ("''", "0"))
def test_explicit_invalid_node_uid_is_read_only_and_never_randomized(tmp_path, uid_source):
    path = tmp_path / "stage.py"
    original = (
        "from src.authoring.dsl import Stage, Wait\n"
        f"stage = Stage('stage_1', 'Stage', [Wait(1, uid={uid_source})])\n"
    ).encode("utf-8")
    path.write_bytes(original)

    first = load_python_source(path, module_name="demo.stage")
    second = load_python_source(path, module_name="demo.stage")

    assert first.read_only and second.read_only
    assert first.raw_bytes == original == second.raw_bytes


def test_explicit_empty_template_uid_is_read_only(tmp_path):
    path = tmp_path / "stage.py"
    original = (
        "from src.authoring.dsl import Stage\n"
        "from missing_templates import burst\n"
        "stage = Stage('stage_1', 'Stage', [burst(uid='')])\n"
    ).encode("utf-8")
    path.write_bytes(original)

    document = load_python_source(path, module_name="demo.stage")

    assert document.read_only
    assert document.raw_bytes == original


@pytest.mark.parametrize(
    "node_source",
    (
        "Wait(None)",
        "Repeat(None, [])",
        "At(None, [])",
        "MoveTo(0.0, 0.0, duration=None)",
        "FireArc(count=None)",
    ),
)
def test_explicit_none_for_required_literal_is_diagnosed_and_blocks_save(
    tmp_path, node_source
):
    path = tmp_path / "task.py"
    original = (
        "from src.authoring.dsl import At, FireArc, MoveTo, Repeat, Task, Wait\n"
        f"task = Task('task_1', 'Task', body=[{node_source}])\n"
    ).encode("utf-8")
    path.write_bytes(original)
    document = load_python_source(path, module_name="demo.task")
    program = AuthoringProgram.from_units([document.unit])

    assert not document.read_only
    assert any(item.code == "invalid_argument" for item in program.validate())
    document.mark_dirty()
    with pytest.raises(ProgramValidationError) as caught:
        save_python_source(document, program=program)
    assert getattr(caught.value, "code", "") == "program_invalid"
    assert path.read_bytes() == original


def test_long_template_arguments_render_as_valid_stable_python(tmp_path):
    path = tmp_path / "stage.py"
    values = ", ".join(str(index) for index in range(30))
    mapping = ", ".join(f"'{index}': {index}" for index in range(12))
    _write(
        path,
        f"""
        from src.authoring.dsl import Stage
        from missing_template_package import burst

        stage = Stage(
            "stage_1",
            "Stage",
            [burst([{values}], options={{{mapping}}})],
        )
        """,
    )
    document = load_python_source(path, module_name="demo.stage")
    before = document.unit.semantic_data()
    document.mark_dirty()

    rendered = save_python_source(document)
    compile(rendered, str(path), "exec")
    reopened = load_python_source(path, module_name=document.module_name)

    assert reopened.unit.semantic_data() == before
    reopened.mark_dirty()
    assert save_python_source(reopened) == rendered


def test_long_parameter_default_renders_as_valid_stable_python(tmp_path):
    path = tmp_path / "task.py"
    values = ", ".join(str(index) for index in range(30))
    _write(
        path,
        f"""
        from src.authoring.dsl import Parameter, Return, Task

        task = Task(
            "task_1",
            "Task",
            parameters=[Parameter("values", "list[int]", [{values}])],
            body=[Return()],
        )
        """,
    )
    document = load_python_source(path, module_name="demo.tasks.task_1")
    before = document.unit.semantic_data()
    document.mark_dirty()

    rendered = save_python_source(document)
    compile(rendered, str(path), "exec")
    reopened = load_python_source(path, module_name=document.module_name)

    assert reopened.unit.semantic_data() == before
    reopened.mark_dirty()
    assert save_python_source(reopened) == rendered


def test_tuple_containing_long_list_renders_as_valid_stable_python(tmp_path):
    path = tmp_path / "function.py"
    values = ", ".join(str(index) for index in range(30))
    _write(
        path,
        f"""
        from src.authoring.dsl import Function, Return

        function = Function(
            "function_1",
            "Function",
            body=[Return(([{values}],))],
        )
        """,
    )
    document = load_python_source(path, module_name="demo.functions.function_1")
    before = document.unit.semantic_data()
    document.mark_dirty()

    rendered = save_python_source(document)
    compile(rendered, str(path), "exec")
    reopened = load_python_source(path, module_name=document.module_name)

    assert reopened.unit.semantic_data() == before
    reopened.mark_dirty()
    assert save_python_source(reopened) == rendered

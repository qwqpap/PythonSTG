"""Every public DSL node must survive the full palette round trip."""

from __future__ import annotations

from pathlib import Path

from src.authoring import dsl
from src.authoring.program import DropPlacement, Ref, find_node, node_from_palette
from src.compiler.package_builder import PackageBuilder
from src.core.project_context import ProjectContext
from src.editor.session import EditorSession


# kind -> (host unit id, host unit kind, special landing)
_KIND_CONTEXTS = {
    "Wait": ("stage", "Stage", None),
    "At": ("stage", "Stage", None),
    "Repeat": ("stage", "Stage", None),
    "While": ("stage", "Stage", None),
    "If": ("stage", "Stage", None),
    "Else": ("stage", "Stage", "IfBody"),
    "ForEach": ("stage", "Stage", None),
    "Parallel": ("stage", "Stage", None),
    "SpawnTask": ("stage", "Stage", None),
    "Break": ("stage", "Stage", "RepeatBody"),
    "Continue": ("stage", "Stage", "RepeatBody"),
    "Return": ("task_one", "Task", None),
    "Set": ("stage", "Stage", None),
    "Call": ("task_one", "Task", None),
    "RawPython": ("stage", "Stage", None),
    "RunWave": ("stage", "Stage", None),
    "RunBoss": ("stage", "Stage", None),
    "SetBackground": ("stage", "Stage", None),
    "PlayBGM": ("stage", "Stage", None),
    "PlayDialogue": ("stage", "Stage", None),
    "SpawnEnemy": ("wave_one", "Wave", None),
    "MoveTo": ("enemy_one", "Enemy", None),
    "MoveLinear": ("enemy_one", "Enemy", None),
    "SetPosition": ("enemy_one", "Enemy", None),
    "Fire": ("enemy_one", "Enemy", None),
    "FireCircle": ("enemy_one", "Enemy", None),
    "FireArc": ("enemy_one", "Enemy", None),
    "FireAtPlayer": ("enemy_one", "Enemy", None),
    "FirePolar": ("enemy_one", "Enemy", None),
    "FireOrbit": ("enemy_one", "Enemy", None),
    "ClearBullets": ("enemy_one", "Enemy", None),
    "Kill": ("enemy_one", "Enemy", None),
    "PlaySE": ("wave_one", "Wave", None),
    "CreateLaser": ("enemy_one", "Enemy", None),
    "CreateBentLaser": ("enemy_one", "Enemy", None),
    "RemoveLaser": ("enemy_one", "Enemy", None),
    "ClearLasers": ("enemy_one", "Enemy", None),
}
_REF_FOR_KIND = {
    "RunWave": "wave_one", "RunBoss": "boss_one", "SpawnEnemy": "enemy_one",
    "Call": "func_one", "SpawnTask": "task_one",
}
_REF_FIELD = {
    "RunWave": "wave_class", "RunBoss": "boss_def", "SpawnEnemy": "enemy_class",
    "Call": "function", "SpawnTask": "task",
}


def _write_project(root: Path) -> Path:
    root.mkdir(parents=True)
    sources = {
        "project.py": (
            "from src.authoring.dsl import Project, Ref\n\n"
            "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n"
        ),
        "stage.py": "from src.authoring.dsl import Stage\n\nstage = Stage('stage', 'Stage', body=[])\n",
        "waves/wave_one.py": (
            "from src.authoring.dsl import Wave\n\n"
            "wave_one = Wave('wave_one', 'Wave One', body=[])\n"
        ),
        "enemies/enemy_one.py": (
            "from src.authoring.dsl import Enemy\n\n"
            "enemy_one = Enemy('enemy_one', 'Enemy One', body=[])\n"
        ),
        "bosses/boss_one.py": (
            "from src.authoring.dsl import Boss, Ref\n\n"
            "boss_one = Boss('boss_one', 'Boss One', 'boss1', [Ref('spell_one')])\n"
        ),
        "spells/spell_one.py": (
            "from src.authoring.dsl import Spell\n\n"
            "spell_one = Spell('spell_one', 'Spell One', body=[])\n"
        ),
        "tasks/task_one.py": (
            "from src.authoring.dsl import Task\n\ntask_one = Task('task_one', 'Task One', body=[])\n"
        ),
        "functions/func_one.py": (
            "from src.authoring.dsl import Function\n\n"
            "func_one = Function('func_one', 'Function One', body=[])\n"
        ),
    }
    for name, source in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8", newline="\n")
    return root


def test_every_public_node_creates_from_palette_saves_reopens_and_builds(tmp_path):
    root = _write_project(tmp_path / "authoring")
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(root)

    created: dict[str, str] = {}
    for kind in dsl.NODE_CONSTRUCTORS:
        unit_id, unit_kind, special = _KIND_CONTEXTS[kind]
        session.select_unit(unit_id)
        node = node_from_palette(
            kind, session.program, unit_kind, _REF_FOR_KIND.get(kind)
        )
        if special == "IfBody":
            session.insert_node_relative(
                created["If"], DropPlacement.CHILD, node, target_slot="body"
            )
        elif special == "RepeatBody":
            session.insert_node_relative(
                created["Repeat"], DropPlacement.CHILD, node, target_slot="body"
            )
        else:
            session.append_node(node)
        created[kind] = node.uid

    assert set(created) == set(dsl.NODE_CONSTRUCTORS)
    for kind, field in _REF_FIELD.items():
        inserted = find_node(session.program, created[kind])[1]
        assert isinstance(inserted.arguments[field], Ref)

    before_save = session.program.semantic_data()
    session.save_all()

    reopened = EditorSession(project_context=ProjectContext(tmp_path))
    reopened.open_project(root)
    assert reopened.program.semantic_data() == before_save
    for kind in dsl.NODE_CONSTRUCTORS:
        find_node(reopened.program, created[kind])

    output_root = tmp_path / "generated"
    builder = PackageBuilder(output_root, project_root=Path.cwd())
    target = builder.build(reopened.program)
    assert (Path(target) / "entry.py").exists()

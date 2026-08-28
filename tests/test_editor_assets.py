from __future__ import annotations

from pathlib import Path

from src.core.project_context import ProjectContext
from src.editor.session import EditorSession
from src.editor.window import EditorWindow


def _write_asset(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"asset")


def _project(project_root: Path) -> Path:
    for relative in (
        "assets/audio/theme.ogg",
        "assets/audio/hit.wav",
        "assets/backgrounds/stage.json",
        "assets/sprites/enemy.png",
        "assets/images/unused.png",
        "game_content/generated/demo/ignored.json",
        ".claude/settings.local.json",
        ".git/private.png",
        "node_modules/package/theme.ogg",
        "trash/gemini-code-driven-20260827/ignored.png",
    ):
        _write_asset(project_root, relative)

    root = project_root / "game_content" / "authoring" / "demo"
    root.mkdir(parents=True)
    sources = {
        "project.py": (
            "from src.authoring.dsl import Project, Ref\n\n"
            "project = Project('demo', 'Demo', Ref('stage'), [Ref('stage')])\n"
        ),
        "stage.py": (
            "from src.authoring.dsl import PlayBGM, RawPython, Ref, RunWave, "
            "SetBackground, Stage, Wait\n\n"
            "stage = Stage(\n"
            "    'stage',\n"
            "    'Stage',\n"
            "    bgm='res://assets/audio/theme.ogg',\n"
            "    body=[\n"
            "        SetBackground('res://assets/backgrounds/stage.json', uid='background'),\n"
            "        RunWave(Ref('wave'), uid='run_wave'),\n"
            "        RawPython(\"marker = 'res://assets/dynamic.png'\", uid='raw'),\n"
            "        Wait(10, uid='flow_wait'),\n"
            "    ],\n"
            ")\n"
        ),
        "wave.py": (
            "from src.authoring.dsl import PlaySE, Ref, SpawnEnemy, Wave\n\n"
            "wave = Wave('wave', 'Wave', body=["
            "SpawnEnemy(Ref('enemy'), uid='spawn'), "
            "PlaySE('res://assets/audio/hit.wav', uid='hit')])\n"
        ),
        "enemy.py": (
            "from src.authoring.dsl import Enemy, Wait\n\n"
            "enemy = Enemy('enemy', 'Enemy', body=[Wait(1, uid='enemy_wait')], "
            "sprite='res://assets/sprites/enemy.png')\n"
        ),
        "other_stage.py": (
            "from src.authoring.dsl import Stage\n\n"
            "stage = Stage('other_stage', 'Other', "
            "background='res://assets/images/unused.png')\n"
        ),
    }
    for name, source in sources.items():
        (root / name).write_text(source, encoding="utf-8")
    return root


def _session(tmp_path: Path) -> EditorSession:
    authoring_root = _project(tmp_path)
    session = EditorSession(project_context=ProjectContext(tmp_path))
    session.open_project(authoring_root)
    return session


def test_global_and_transitive_stage_assets_have_distinct_scopes(
    tmp_path, qapp_session
):
    session = _session(tmp_path)
    assert session.global_assets == (
        "res://assets/audio/hit.wav",
        "res://assets/audio/theme.ogg",
        "res://assets/backgrounds/stage.json",
        "res://assets/images/unused.png",
        "res://assets/sprites/enemy.png",
    )

    session.select_unit("stage")
    assert session.current_stage_id == "stage"
    assert session.stage_assets == (
        "res://assets/audio/hit.wav",
        "res://assets/audio/theme.ogg",
        "res://assets/backgrounds/stage.json",
        "res://assets/sprites/enemy.png",
    )
    assert all("dynamic.png" not in uri for uri in session.stage_assets)

    session.select_unit("enemy")
    assert session.current_stage_id == "stage"
    assert session.stage_assets == (
        "res://assets/audio/hit.wav",
        "res://assets/audio/theme.ogg",
        "res://assets/backgrounds/stage.json",
        "res://assets/sprites/enemy.png",
    )


def test_resource_insert_requires_explicit_action_and_is_one_undo_command(
    tmp_path, qapp_session, monkeypatch
):
    session = _session(tmp_path)
    session.select_unit("stage")
    window = EditorWindow(session)
    window.show()
    qapp_session.processEvents()

    monkeypatch.setattr(window, "_choose_resource_action", lambda actions: None)
    before = session.program.semantic_data()
    window._resource_drop(
        "res://assets/audio/theme.ogg",
        "flow_wait",
        "before",
    )
    assert session.program.semantic_data() == before
    assert session.undo_stack.count() == 0

    monkeypatch.setattr(window, "_choose_resource_action", lambda actions: actions[0].key)
    window._resource_drop(
        "res://assets/audio/theme.ogg",
        "flow_wait",
        "before",
    )
    body = session.program.get_unit("stage").body
    wait_index = next(index for index, node in enumerate(body) if node.uid == "flow_wait")
    assert body[wait_index - 1].kind == "PlayBGM"
    assert body[wait_index - 1].arguments["name"] == "res://assets/audio/theme.ogg"
    assert session.undo_stack.count() == 1

    session.undo_stack.undo()
    assert session.program.semantic_data() == before
    session.undo_stack.clear()
    window._resource_drop(
        "res://assets/audio/theme.ogg",
        "flow_wait",
        "wrap",
    )
    assert session.program.semantic_data() == before
    assert session.undo_stack.count() == 0
    assert window.statusBar().currentMessage().startswith("资源未插入：")
    window.close()

import json

import pytest

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor import SceneEditorSession, make_node
from src.compiler.scene_spell import SceneSpellCompileError, compile_simple_spell
from src.pattern import BulletSpec, PatternDocument


def _save_pattern(project, name="Ring"):
    atlas = project.root / "assets" / "bullets.json"
    atlas.parent.mkdir(parents=True, exist_ok=True)
    atlas.write_text(
        json.dumps({"sprites": {"orb": {"rect": [0, 0, 8, 8]}}}),
        encoding="utf-8",
    )
    source = PatternDocument.new(name)
    source.bullet = BulletSpec(resource="res://assets/bullets.json#orb")
    ResourceStore(project).save(source, "game_content/patterns/ring.pystg.json")
    return source


def _scene_with_spell(resource: str):
    scene = SceneEditorSession.new_document("No-code Spell")
    stage = make_node("Stage")
    boss = make_node("Boss")
    spell = make_node("Spell")
    emitter = make_node("Emitter")
    emitter.properties.update({"x": 288.0, "y": 112.0})
    instance = make_node("PatternInstance")
    instance.properties["pattern"] = resource
    scene.root.children.append(stage)
    stage.children.append(boss)
    boss.children.append(spell)
    spell.children.append(emitter)
    emitter.children.append(instance)
    scene.validate()
    return scene, spell, emitter, instance


def test_simple_spell_resolves_reference_and_applies_emitter_instance_origin(tmp_path):
    project = ProjectContext(tmp_path)
    _save_pattern(project)
    scene, spell, _emitter, instance = _scene_with_spell(
        "res://game_content/patterns/ring.pystg.json"
    )

    preview = compile_simple_spell(project, scene, spell.id)

    assert preview.pattern_instance_id == instance.id
    assert preview.pattern_resource == "res://game_content/patterns/ring.pystg.json"
    assert preview.program.origin == pytest.approx((0.5, 0.5))
    assert preview.document.shape.origin_x == pytest.approx(0.5)
    assert preview.document.shape.origin_y == pytest.approx(0.5)


def test_simple_spell_reports_clickable_node_and_property_diagnostics(tmp_path):
    project = ProjectContext(tmp_path)
    scene, spell, _emitter, instance = _scene_with_spell("")

    with pytest.raises(SceneSpellCompileError) as caught:
        compile_simple_spell(project, scene, spell.id)

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.node_id == instance.id
    assert diagnostic.path == "pattern"
    assert diagnostic.code == "missing_pattern_resource"


def test_simple_spell_rejects_multiple_patterns_until_stage_program_phase(tmp_path):
    project = ProjectContext(tmp_path)
    _save_pattern(project)
    scene, spell, emitter, _instance = _scene_with_spell(
        "res://game_content/patterns/ring.pystg.json"
    )
    second = make_node("PatternInstance")
    second.properties["pattern"] = "res://game_content/patterns/ring.pystg.json"
    emitter.children.append(second)

    with pytest.raises(SceneSpellCompileError) as caught:
        compile_simple_spell(project, scene, spell.id)

    assert caught.value.diagnostics[0].code == "multiple_pattern_instances"

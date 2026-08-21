"""N6 beginner Stage skeletons through formal authoring, compile and runtime."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.editor import SceneEditorSession
from src.authoring.commands.base import CommandStack
from src.compiler.stage import StageCompileError, compile_stage
from src.editor.stage_templates import (
    ApplyStageTemplateCommand,
    StageTemplateError,
    build_stage_template,
)
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.events import EventBus
from src.game.stage.context import StageContext
from src.game.stage.program import StageRunner
from src.pattern import PatternDocument


class _Player:
    pos = [0.0, -0.75]


class _BackgroundRenderer:
    def __init__(self):
        self.resources = []

    def load_background(self, resource):
        self.resources.append(resource)
        return True


def _project_content(tmp_path):
    project = ProjectContext(tmp_path)
    aliases = tmp_path / "assets" / "bullet_aliases.json"
    aliases.parent.mkdir(parents=True, exist_ok=True)
    aliases.write_text(
        json.dumps({"mapping": {"ball_m": {"red": "orb"}}}),
        encoding="utf-8",
    )
    pattern = PatternDocument.new("Beginner Ring")
    pattern.shape = replace(pattern.shape, count=1)
    pattern.schedule = replace(
        pattern.schedule,
        interval_frames=60,
        burst_count=1,
        loop_count=None,
    )
    pattern_uri = "res://game_content/patterns/beginner_ring.pystg.json"
    ResourceStore(project).save(pattern, pattern_uri.removeprefix("res://"))
    return project, pattern_uri


def _context():
    renderer = _BackgroundRenderer()
    context = StageContext(
        OptimizedBulletPool(max_bullets=128),
        _Player(),
        background_renderer=renderer,
        event_bus=EventBus(),
    )
    return context, renderer


@pytest.mark.parametrize(
    ("kind", "state_names"),
    (
        ("midstage", ["Wave A", "Wave B", "End"]),
        ("two_phase_boss", ["Intro", "Normal", "Enrage", "End"]),
    ),
)
def test_templates_are_one_scene_document_and_one_undoable_transaction(
    tmp_path, kind, state_names
):
    _project, pattern_uri = _project_content(tmp_path)
    document = SceneEditorSession.new_document("Empty")
    before = document.to_dict()
    stack = CommandStack()

    stack.push(
        ApplyStageTemplateCommand(
            document,
            kind,
            pattern_uri,
            "res://game_content/backgrounds/stage.pystg.json",
        )
    )

    assert [state.name for state in document.state_graph.states] == state_names
    assert document.metadata["template"] == {"kind": kind, "version": 1}
    assert len(document.root.children) == 1
    assert document.root.children[0].type == "Stage"
    assert all(
        node.properties["pattern"] == pattern_uri
        for node in document.root.walk()
        if node.type == "PatternInstance"
    )
    assert stack.undo()
    assert document.to_dict() == before
    assert stack.redo()
    assert [state.name for state in document.state_graph.states] == state_names


def test_midstage_all_clear_reaction_advances_on_next_fixed_frame(tmp_path):
    project, pattern_uri = _project_content(tmp_path)
    document = build_stage_template(
        SceneEditorSession.new_document("Empty"),
        "midstage",
        pattern_resource=pattern_uri,
        background_resource="res://game_content/backgrounds/stage.pystg.json",
    )
    program = compile_stage(project, document)
    runner = StageRunner(program)
    context, _renderer = _context()
    first, second, _end = document.state_graph.states

    runner.start(context)
    assert runner.current_state_path == (first.id,)
    context.emit_event("encounter.cleared", {"wave": "A"})
    runner.tick(context)
    assert runner.current_state_path == (first.id,)
    runner.tick(context)
    assert runner.current_state_path == (second.id,)
    assert any(
        item.kind == "state_transition" and item.state_id == first.id
        for item in runner.trace
    )


def test_two_phase_boss_compiles_pattern_background_audio_and_reactions(tmp_path):
    project, pattern_uri = _project_content(tmp_path)
    background_uri = "res://game_content/backgrounds/boss.pystg.json"
    document = build_stage_template(
        SceneEditorSession.new_document("Empty"),
        "two_phase_boss",
        pattern_resource=pattern_uri,
        background_resource=background_uri,
        audio_resource="boss_theme",
    )

    program = compile_stage(project, document)
    context, renderer = _context()
    runner = StageRunner(program)
    runner.start(context)
    runner.tick(context)

    assert len(program.patterns) == 2
    assert {item.kind for item in program.actions} >= {
        "Audio",
        "Background",
    }
    assert len(program.reactive_clips) == 2
    assert renderer.resources == [background_uri]
    assert context.background_transitions()[0]["owner"] == document.state_graph.states[0].id


def test_template_validation_and_compile_failures_point_to_editable_locations(
    tmp_path,
):
    document = SceneEditorSession.new_document("Empty")
    with pytest.raises(StageTemplateError) as resource_error:
        build_stage_template(
            document,
            "midstage",
            pattern_resource="C:/absolute/pattern.json",
            background_resource="res://background.pystg.json",
        )
    assert resource_error.value.path == "template.pattern_resource"

    project = ProjectContext(tmp_path)
    broken = build_stage_template(
        document,
        "midstage",
        pattern_resource="res://missing-pattern.pystg.json",
        background_resource="res://background.pystg.json",
    )
    with pytest.raises(StageCompileError) as compile_error:
        compile_stage(project, broken)
    diagnostic = compile_error.value.diagnostics[0]
    assert diagnostic.state_id == broken.state_graph.states[0].id
    assert diagnostic.track_id is not None
    assert diagnostic.clip_id is not None
    assert diagnostic.path.endswith(".payload.pattern")

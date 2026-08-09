"""N2.7 hot-reload compatibility decisions."""

from __future__ import annotations

from copy import deepcopy

from src.authoring.variables import VariableSpec
from src.core.project_context import ProjectContext
from src.editor import SceneEditorSession
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.preview import PatternPreviewController


def test_stage_hot_reload_restores_only_compatible_variable_keys(tmp_path):
    project = ProjectContext(tmp_path)
    pool = OptimizedBulletPool(max_bullets=32)
    controller = PatternPreviewController(pool, project=project)
    scene = SceneEditorSession.new_document("Reload")
    scene.variables.append(VariableSpec("rank", "float", 1.0, writable_by=("safe_action",)))
    controller.load(scene.to_dict())
    controller.runner.variables.write("rank", 4.0, writer="safe_action")
    controller.play()

    same = SceneEditorSession.new_document("Reload")
    same.id = scene.id
    same.variables.append(VariableSpec("rank", "float", 0.0, writable_by=("safe_action",)))
    same.root.id = scene.root.id
    controller.load(same.to_dict())
    assert controller.runner.read_variable("rank") == 4.0
    assert controller.last_compatibility_decision["restored"] == ["stage:rank@stage"]

    changed = deepcopy(same)
    changed.variables[0] = VariableSpec("rank", "int", 0, writable_by=("safe_action",))
    controller.load(changed.to_dict())
    assert controller.runner.read_variable("rank") == 0
    assert "stage:rank@stage" in controller.last_compatibility_decision["discarded"]

"""M3 compiler for one simple Scene Spell backed by a Pattern resource.

This is intentionally not the Phase 4 StageProgram.  It resolves exactly one
enabled PatternInstance under a selected Spell, applies its spawn position as an
instance transform, and compiles through the formal Pattern path.  Reference
resolution and the spawn-origin rule are shared with the StageProgram compiler
(see :mod:`src.compiler.pattern_resolve`) so both paths agree on where a Pattern
comes from and where it fires.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.authoring import ResourceStore
from src.core.project_context import ProjectContext
from src.pattern import PatternCompileError, PatternDocument, PatternProgram, compile_pattern

from src.authoring.scene.document import EditorNode, SceneDocument
from .pattern_resolve import (
    PatternResolveError,
    apply_spawn_origin,
    load_pattern_document,
    node_maps,
    spawn_origin_node,
)
from src.authoring.commands.scene import require_node


@dataclass(frozen=True)
class SceneCompileDiagnostic:
    severity: str
    code: str
    resource_id: str
    node_id: str
    path: str
    message: str
    referenced_path: str | None = None


class SceneSpellCompileError(ValueError):
    def __init__(self, diagnostics: tuple[SceneCompileDiagnostic, ...]):
        self.diagnostics = diagnostics
        super().__init__("; ".join(item.message for item in diagnostics))


@dataclass(frozen=True)
class SceneSpellPreview:
    scene_id: str
    spell_node_id: str
    pattern_instance_id: str
    pattern_resource: str
    document: PatternDocument
    program: PatternProgram


def _error(
    scene: SceneDocument,
    node: EditorNode,
    code: str,
    path: str,
    message: str,
    *,
    referenced_path: str | None = None,
) -> SceneSpellCompileError:
    return SceneSpellCompileError(
        (
            SceneCompileDiagnostic(
                severity="error",
                code=code,
                resource_id=scene.id,
                node_id=node.id,
                path=path,
                message=message,
                referenced_path=referenced_path,
            ),
        )
    )


def compile_simple_spell(
    project: ProjectContext,
    scene: SceneDocument,
    spell_node_id: str,
) -> SceneSpellPreview:
    """Compile one selected no-code Spell through the formal Pattern compiler."""

    spell = require_node(scene.root, spell_node_id)
    if spell.type != "Spell":
        raise _error(
            scene,
            spell,
            "wrong_node_type",
            "type",
            "Select a semantic Spell node for no-code preview.",
        )
    instances = [
        node
        for node in spell.walk()
        if node.type == "PatternInstance" and bool(node.properties.get("enabled", True))
    ]
    if not instances:
        raise _error(
            scene,
            spell,
            "missing_pattern_instance",
            "children",
            "The selected Spell needs one enabled PatternInstance.",
        )
    if len(instances) > 1:
        raise _error(
            scene,
            spell,
            "multiple_pattern_instances",
            "children",
            "M3 simple Spell preview supports exactly one enabled PatternInstance; timeline orchestration belongs to M4.",
        )
    instance = instances[0]
    resource_value = str(instance.properties.get("pattern") or "").strip()
    if not resource_value:
        raise _error(
            scene,
            instance,
            "missing_pattern_resource",
            "pattern",
            "Assign a Pattern resource to this PatternInstance.",
        )
    try:
        reference_uri, document = load_pattern_document(
            project,
            ResourceStore(project),
            resource_value,
        )
    except PatternResolveError as exc:
        raise _error(
            scene,
            instance,
            "invalid_pattern_resource",
            "pattern",
            str(exc),
        ) from exc

    _nodes, parents = node_maps(scene.root)
    origin_node = spawn_origin_node(instance, parents)
    if origin_node is not None:
        try:
            document = apply_spawn_origin(scene, document, origin_node)
        except PatternResolveError as exc:
            raise _error(
                scene,
                origin_node,
                "invalid_emitter_position",
                "properties",
                str(exc),
            ) from exc

    try:
        program = compile_pattern(document, project=project)
    except PatternCompileError as exc:
        diagnostics = tuple(
            SceneCompileDiagnostic(
                severity=item.severity,
                code=item.code,
                resource_id=scene.id,
                node_id=instance.id,
                path="pattern",
                referenced_path=item.path,
                message=item.message,
            )
            for item in exc.diagnostics
        )
        raise SceneSpellCompileError(diagnostics) from exc

    return SceneSpellPreview(
        scene_id=scene.id,
        spell_node_id=spell.id,
        pattern_instance_id=instance.id,
        pattern_resource=reference_uri,
        document=document,
        program=program,
    )

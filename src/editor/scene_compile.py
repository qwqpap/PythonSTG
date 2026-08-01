"""M3 compiler for one simple Scene Spell backed by a Pattern resource.

This is intentionally not the Phase 4 StageProgram.  It resolves exactly one
enabled PatternInstance under a selected Spell, applies its parent Emitter
origin as an instance transform, and compiles through the formal Pattern path.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.authoring import ResourceStore
from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.core.project_context import ProjectContext, ProjectContextError
from src.pattern import PatternCompileError, PatternDocument, PatternProgram, compile_pattern

from .document import EditorNode, SceneDocument
from .pattern_commands import pattern_with_property
from .scene_commands import find_parent, require_node


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
        reference = ResourceReference.parse(resource_value)
        if reference.subresource is not None:
            raise ResourceDocumentError("PatternDocument references cannot contain fragments")
        source = reference.resolve(project, must_exist=True)
        document = ResourceStore(project).load(source)
        if not isinstance(document, PatternDocument):
            raise ResourceDocumentError("Referenced resource is not a PatternDocument")
    except (OSError, ValueError, ResourceDocumentError, ProjectContextError) as exc:
        raise _error(
            scene,
            instance,
            "invalid_pattern_resource",
            "pattern",
            str(exc),
        ) from exc

    location = find_parent(scene.root, instance.id)
    if location is not None and location[0].type == "Emitter":
        emitter = location[0]
        x = float(emitter.properties.get("x", 192.0))
        y = float(emitter.properties.get("y", 224.0))
        runtime_x, runtime_y = scene.coordinate_space.authoring_to_runtime(x, y)
        document = pattern_with_property(document, "shape.origin_x", runtime_x)
        document = pattern_with_property(document, "shape.origin_y", runtime_y)

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
        pattern_resource=reference.uri,
        document=document,
        program=program,
    )

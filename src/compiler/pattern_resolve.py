"""Scene-to-Pattern resolution shared by the Stage and Spell compilers.

Both compilers answer the same two questions before they can hand a Pattern to
the formal compiler: *which document does this reference name*, and *where in
the scene does it spawn*.  Answering them twice let the two paths drift -- the
Spell preview used to accept only an immediate ``Emitter`` parent while the
Stage program walked the whole ancestor chain, so one scene could spawn bullets
in two different places depending on which path ran.  They share the answer
here instead.

The helpers raise :class:`PatternResolveError` and know nothing about
diagnostics: each compiler catches it and re-raises its own diagnostic type, so
the message travels while the surrounding report shape stays theirs.
"""

from __future__ import annotations

from src.authoring import ResourceStore
from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.core.project_context import ProjectContext, ProjectContextError
from src.pattern import PatternDocument

from src.authoring.scene.document import EditorNode, SceneDocument
from src.authoring.commands.pattern import pattern_with_property


class PatternResolveError(ValueError):
    """A Pattern reference or spawn position could not be resolved."""


def node_maps(
    root: EditorNode,
) -> tuple[dict[str, EditorNode], dict[str, EditorNode | None]]:
    """Index a scene tree by id, together with each node's parent."""

    nodes: dict[str, EditorNode] = {}
    parents: dict[str, EditorNode | None] = {}

    def visit(node: EditorNode, parent: EditorNode | None) -> None:
        nodes[node.id] = node
        parents[node.id] = parent
        for child in node.children:
            visit(child, node)

    visit(root, None)
    return nodes, parents


def spawn_origin_node(
    target: EditorNode | None,
    parents: dict[str, EditorNode | None],
) -> EditorNode | None:
    """The node whose authored position a Pattern under ``target`` spawns at.

    A ``PatternInstance`` carries no position of its own, so the search climbs
    to the nearest ancestor that does -- an ``Emitter``, or any node that owns
    ``x``/``y`` such as a ``Boss``.  ``None`` means nothing on the path is
    positioned and the Pattern keeps its own authored origin.
    """

    node = target
    while node is not None:
        if node.type == "Emitter" or (
            "x" in node.properties and "y" in node.properties
        ):
            return node
        node = parents.get(node.id)
    return None


def load_pattern_document(
    project: ProjectContext,
    store: ResourceStore,
    resource_value: str,
) -> tuple[str, PatternDocument]:
    """Resolve one ``res://`` Pattern reference to its loaded document."""

    try:
        reference = ResourceReference.parse(resource_value)
        if reference.subresource is not None:
            raise ResourceDocumentError(
                "PatternDocument references cannot contain fragments"
            )
        source = reference.resolve(project, must_exist=True)
        document = store.load(source)
        if not isinstance(document, PatternDocument):
            raise ResourceDocumentError(
                f"Referenced resource is "
                f"{getattr(document, 'type', type(document).__name__)!r}, "
                f"not pystg.pattern"
            )
    except (OSError, ValueError, ResourceDocumentError, ProjectContextError) as exc:
        raise PatternResolveError(str(exc)) from exc
    return reference.uri, document


def apply_spawn_origin(
    scene: SceneDocument,
    document: PatternDocument,
    node: EditorNode,
) -> PatternDocument:
    """Rewrite the Pattern origin to ``node``'s authored position."""

    try:
        x = float(node.properties.get("x", 192.0))
        y = float(node.properties.get("y", 224.0))
    except (TypeError, ValueError) as exc:
        raise PatternResolveError(str(exc)) from exc
    runtime_x, runtime_y = scene.coordinate_space.authoring_to_runtime(x, y)
    document = pattern_with_property(document, "shape.origin_x", runtime_x)
    return pattern_with_property(document, "shape.origin_y", runtime_y)


__all__ = [
    "PatternResolveError",
    "apply_spawn_origin",
    "load_pattern_document",
    "node_maps",
    "spawn_origin_node",
]

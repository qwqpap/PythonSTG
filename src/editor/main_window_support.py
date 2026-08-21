"""Module-level helpers shared by the editor shell and its slot mixins.

These live outside :class:`~src.editor.app.EditorMainWindow` so the domain
mixins can import them without importing the window module itself.
"""

from __future__ import annotations

from src.core.project_context import ProjectContext
from src.authoring.resources import ResourceDocumentError, ResourceReference
from src.authoring.scene.document import EditorNode, SceneDocument


APP_NAME = "PySTG Editor"
RESOURCE_FILTER = "PySTG Resources (*.pystg.json);;JSON (*.json)"
SCENE_FILTER = RESOURCE_FILTER


def _scene_has_stage_content(document: SceneDocument) -> bool:
    return any(
        state.tracks
        or state.entry_actions
        or state.exit_actions
        or state.transitions
        or state.child_graph is not None
        for state in document.state_graph.walk_states()
    )


def build_preview_command(
    project: ProjectContext,
    document: SceneDocument,
    node: EditorNode | None,
) -> tuple[list[str], str]:
    if node is not None and node.type == "SpellCard":
        script_value = str(node.properties.get("script", "")).strip()
        if not script_value:
            raise ValueError("Selected SpellCard needs a script path.")
        try:
            reference = ResourceReference.parse(
                script_value,
                allow_legacy_project_path=True,
            )
            if reference.subresource is not None:
                raise ResourceDocumentError("script references cannot use fragments")
            script_path = reference.resolve(project)
        except ResourceDocumentError as exc:
            raise ValueError(str(exc)) from exc
        if not script_path.is_file():
            raise ValueError(f"SpellCard script does not exist: {script_path}")
        arguments = [
            str(project.root / "tools" / "preview_spell.py"),
            str(script_path),
        ]
        class_name = str(node.properties.get("class_name", "")).strip()
        if class_name:
            arguments.extend(["--spell", class_name])
        return arguments, f"spell preview: {script_path.name}"

    stage = str(document.metadata.get("preview_stage", "stage1"))
    return (
        [
            str(project.root / "main.py"),
            f"--stage={stage}",
            f"--project={project.root}",
            "--hot-reload",
        ],
        f"runtime preview: {stage}",
    )


def _find_ui_node(root, node_id: str):
    for node, _depth in root.walk():
        if node.id == node_id:
            return node
    return None

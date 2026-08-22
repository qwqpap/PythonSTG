"""Scene shell adapters that translate Qt events into typed editor intents."""

from __future__ import annotations

from src.qt_compat.QtCore import Qt
from src.qt_compat.QtWidgets import QTreeWidgetItem

from .application import (
    AddSceneNodeIntent,
    CreateSimpleSpellIntent,
    CreateStageTemplateIntent,
    IntentRejectedError,
    MoveSceneNodeIntent,
    RemoveSceneNodeIntent,
    RenameSceneNodeIntent,
    SelectNodeIntent,
    SetNodePropertyIntent,
    SetSceneNodePropertiesIntent,
)
from .application.queries import find_scene_parent
from src.authoring.scene.document import SceneDocument
from .shell import WindowService
from .shell.ports import SceneEditPort


class SceneEditService(WindowService[SceneEditPort]):
    """Keep public scene-edit entry points while Coordinator owns mutations."""

    def _submit_scene_intent(
        self,
        intent,
        *,
        label: str = "",
        error_title: str = "Edit failed",
    ) -> bool:
        try:
            invalidation = self.port.editor_coordinator.dispatch(intent)
        except (IntentRejectedError, ValueError) as exc:
            self.port._show_error(error_title, exc)
            return False
        if invalidation.scopes:
            self.port.apply_invalidation(intent.document_id, invalidation)
            if label:
                self.port._log(label)
        return bool(invalidation.scopes)

    def select_from_tree(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        del previous
        if self.port._syncing_selection or current is None:
            return
        node_id = str(current.data(0, Qt.UserRole))
        self.port._syncing_selection = True
        try:
            self._submit_scene_intent(
                SelectNodeIntent(self.port.session.document.id, node_id)
            )
        finally:
            self.port._syncing_selection = False

    def select_from_viewport(self, node_id: str) -> None:
        if self.port._syncing_selection or self.port._find_tree_item(node_id) is None:
            return
        self.port._syncing_selection = True
        try:
            self._submit_scene_intent(
                SelectNodeIntent(self.port.session.document.id, str(node_id))
            )
        finally:
            self.port._syncing_selection = False

    def tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column == 0:
            self.rename_node(str(item.data(0, Qt.UserRole)), item.text(0))

    def move_from_tree(self, node_id: str, parent_id: str, index: int) -> None:
        self._submit_scene_intent(
            MoveSceneNodeIntent(
                self.port.session.document.id,
                str(node_id),
                str(parent_id),
                int(index),
            ),
            label="Move node",
        )

    def set_node_position(self, node_id: str, x: float, y: float) -> None:
        self._submit_scene_intent(
            SetSceneNodePropertiesIntent(
                self.port.session.document.id,
                str(node_id),
                {"x": float(x), "y": float(y)},
                True,
            ),
            label="Move node",
        )

    def add_node(self, node_type: str) -> None:
        if not isinstance(self.port.session.document, SceneDocument):
            return
        parent = self.port.session.node(self.port._selected_id) or self.port.session.document.root
        spec = self.port.node_type_registry.get(str(node_type))
        if spec is None:
            self.port._show_error("Add node failed", ValueError(f"Unknown node type: {node_type}"))
            return
        self._submit_scene_intent(
            AddSceneNodeIntent(
                self.port.session.document.id,
                parent.id,
                str(node_type),
                self.port.language_manager.translate(spec.display_name),
                {},
            ),
            label=f"Add {spec.display_name}",
            error_title="Add node failed",
        )

    def create_simple_spell_flow(self) -> None:
        if not isinstance(self.port.session.document, SceneDocument):
            self.port._show_error("Create Spell failed", ValueError("Open a Scene document first"))
            return
        selected_resource = str(self.port.session.editor_state.selection.resource_uri or "")
        record = (
            self.port.resource_browser.index.find(selected_resource)
            if selected_resource and hasattr(self.port, "resource_browser")
            else None
        )
        if record is None or record.kind != "pattern":
            selected_resource = ""
        tr = self.port.language_manager.translate
        self._submit_scene_intent(
            CreateSimpleSpellIntent(
                self.port.session.document.id,
                tr("Stage"),
                tr("Boss"),
                tr("Spell"),
                tr("Emitter"),
                tr("Pattern Instance"),
                selected_resource,
            ),
            label="Created Stage/Boss/Spell/Emitter/PatternInstance flow",
            error_title="Create Spell failed",
        )

    def create_stage_template(self, kind: str) -> None:
        if not isinstance(self.port.session.document, SceneDocument):
            self.port._show_error(
                "Create Stage template failed",
                ValueError("Open a Scene document first"),
            )
            return
        self._submit_scene_intent(
            CreateStageTemplateIntent(
                self.port.session.document.id,
                str(kind),
                "res://game_content/patterns/starter_ring.pystg.json",
                "res://assets/images/background/luastg_spellcard.json",
                "stage_theme",
                self.port.language,
            ),
            label=(
                "Create midstage skeleton"
                if kind == "midstage"
                else "Create two-phase Boss skeleton"
            ),
            error_title="Create Stage template failed",
        )

    def delete_selected(self) -> None:
        if isinstance(self.port.session.document, SceneDocument):
            self._submit_scene_intent(
                RemoveSceneNodeIntent(self.port.session.document.id, self.port._selected_id),
                label="Delete node",
            )

    def rename_selected(self) -> None:
        if isinstance(self.port.session.document, SceneDocument):
            item = self.port.tree.currentItem()
            if item is not None:
                self.port.tree.editItem(item, 0)

    def rename_node(self, node_id: str, name: str) -> None:
        self._submit_scene_intent(
            RenameSceneNodeIntent(self.port.session.document.id, str(node_id), str(name)),
            label="Rename node",
        )

    def set_node_property(self, node_id: str, key: str, value) -> None:
        self._submit_scene_intent(
            SetNodePropertyIntent(
                self.port.session.document.id,
                str(node_id),
                str(key),
                value,
            ),
            label=f"Set {key}",
        )

    def move_selected(self, delta: int) -> None:
        if not isinstance(self.port.session.document, SceneDocument):
            return
        location = find_scene_parent(self.port.session.document.root, self.port._selected_id)
        if location is None:
            return
        parent, index = location
        target = index + int(delta)
        if 0 <= target < len(parent.children):
            self.move_from_tree(self.port._selected_id, parent.id, target)

    def indent_selected(self) -> None:
        if not isinstance(self.port.session.document, SceneDocument):
            return
        location = find_scene_parent(self.port.session.document.root, self.port._selected_id)
        if location is None or location[1] <= 0:
            return
        parent, index = location
        new_parent = parent.children[index - 1]
        self.move_from_tree(self.port._selected_id, new_parent.id, len(new_parent.children))

    def outdent_selected(self) -> None:
        if not isinstance(self.port.session.document, SceneDocument):
            return
        location = find_scene_parent(self.port.session.document.root, self.port._selected_id)
        if location is None:
            return
        parent, _index = location
        if parent.id == self.port.session.document.root.id:
            return
        parent_location = find_scene_parent(self.port.session.document.root, parent.id)
        if parent_location is None:
            return
        grandparent, parent_index = parent_location
        self.move_from_tree(self.port._selected_id, grandparent.id, parent_index + 1)


__all__ = ["SceneEditService"]

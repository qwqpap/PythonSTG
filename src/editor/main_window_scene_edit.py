"""Scene hierarchy editing slots: add, delete, rename, reparent and templates."""

from __future__ import annotations

from src.qt_compat.QtCore import Qt
from src.qt_compat.QtWidgets import QTreeWidgetItem
from .document import EditorNode, SceneDocument
from .node_types import make_node, property_specs
from .stage_templates import ApplyStageTemplateCommand
from .scene_commands import (
    AddNodeCommand,
    AssignResourceCommand,
    MoveNodeCommand,
    RemoveNodeCommand,
    RenameNodeCommand,
    SetNodePropertiesCommand,
    SetNodePropertyCommand,
    find_parent,
)


class SceneEditSlotsMixin:
    """Scene hierarchy editing slots: add, delete, rename, reparent and templates.

    These slots stay bound to the window instance instead of moving into a
    controller object: every attribute they touch is owned by
    ``EditorMainWindow``, and the editor tests plus the three native gates drive
    these methods by name.  Mix in before the Qt base class, the same way
    ``SpaceTapSearchMixin`` is used by ``SceneViewport``.
    """

    def _select_from_tree(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        if (
            self._syncing_selection
            or current is None
            or not isinstance(self.session.document, SceneDocument)
        ):
            return
        self.session.editor_context.pop("selected_clip_id", None)
        self._selected_id = str(current.data(0, Qt.UserRole))
        self._syncing_selection = True
        self.viewport.select_node(self._selected_id)
        self.inspector.set_node(self.session.node(self._selected_id))
        self._syncing_selection = False
        self._update_actions()

    def _select_from_viewport(self, node_id: str) -> None:
        if self._syncing_selection or not isinstance(self.session.document, SceneDocument):
            return
        self.session.editor_context.pop("selected_clip_id", None)
        item = self.tree._find_item(node_id)
        if item is None:
            return
        self._selected_id = node_id
        self._syncing_selection = True
        self.tree.setCurrentItem(item)
        self.inspector.set_node(self.session.node(node_id))
        self._syncing_selection = False
        self._update_actions()

    def _tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0 or not isinstance(self.session.document, SceneDocument):
            return
        node_id = str(item.data(0, Qt.UserRole))
        self.rename_node(node_id, item.text(0))

    def _move_from_tree(self, node_id: str, parent_id: str, index: int) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        node = self.session.node(node_id)
        location = find_parent(self.session.document.root, node_id)
        if node is None or location is None:
            self._refresh()
            return
        if location[0].id == parent_id and location[1] == index:
            self._refresh()
            return
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node_id,
                parent_id,
                index,
                label=f"Move {node.name}",
            ),
            select_id=node_id,
        )

    def _set_node_position(self, node_id: str, x: float, y: float) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        node = self.session.node(node_id)
        if node is None:
            return
        if (
            float(node.properties.get("x", 0.0)) == float(x)
            and float(node.properties.get("y", 0.0)) == float(y)
        ):
            return
        self._apply_command(
            SetNodePropertiesCommand(
                self.session.document.root,
                node_id,
                {"x": float(x), "y": float(y)},
                label=f"Move {node.name}",
            ),
            select_id=node_id,
        )

    def add_node(self, node_type: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        parent = self.session.node(self._selected_id) or self.session.document.root
        spec = self.node_type_registry.get(str(node_type))
        if spec is None:
            self._show_error("Add node failed", ValueError(f"Unknown node type: {node_type}"))
            return
        node = EditorNode(
            type=str(node_type),
            name=self.language_manager.translate(spec.display_name),
            properties={prop.key: prop.default for prop in spec.properties},
        )

        if not self.node_type_registry.can_parent(parent.type, node.type):
            self._show_error(
                "Add node failed",
                ValueError(f"{node.type} cannot be added under {parent.type}"),
            )
            return
        self._apply_command(
            AddNodeCommand(
                self.session.document.root,
                parent.id,
                node,
                label=f"Add {node.name}",
            ),
            select_id=node.id,
        )

    def create_simple_spell_flow(self) -> None:
        """Create the M3 Stage→Boss→Spell→Emitter→Pattern chain."""

        if not isinstance(self.session.document, SceneDocument):
            self._show_error(
                "Create Spell failed",
                ValueError("Open a Scene document first"),
            )
            return
        root = self.session.document.root
        stage = next((node for node in root.children if node.type == "Stage"), None)
        created_stage = stage is None
        tr = self.language_manager.translate
        stage = stage or make_node("Stage", name=tr("Stage"))
        boss = make_node("Boss", name=tr("Boss"))
        spell = make_node("Spell", name=tr("Spell"))
        emitter = make_node("Emitter", name=tr("Emitter"))
        # Give the spatial emitter its own visible handle instead of stacking
        # it directly on the Boss at the registry default position.
        emitter.properties["y"] = 320.0
        instance = make_node("PatternInstance", name=tr("Pattern Instance"))
        selected_resource = str(self.session.selected_resource or "")
        record = (
            self.resource_browser.index.find(selected_resource)
            if selected_resource and hasattr(self, "resource_browser")
            else None
        )
        if record is None or record.kind != "pattern":
            selected_resource = ""

        self.session.commands.begin_transaction("Create simple Spell")
        try:
            if created_stage:
                self.session.apply(AddNodeCommand(root, root.id, stage))
            self.session.apply(AddNodeCommand(root, stage.id, boss))
            self.session.apply(AddNodeCommand(root, boss.id, spell))
            self.session.apply(AddNodeCommand(root, spell.id, emitter))
            self.session.apply(AddNodeCommand(root, emitter.id, instance))
            if selected_resource:
                self.session.apply(
                    AssignResourceCommand(
                        root,
                        instance.id,
                        "pattern",
                        selected_resource,
                        label="Assign Pattern resource",
                    )
                )
        except Exception as exc:
            self.session.commands.cancel_transaction()
            self._show_error("Create Spell failed", exc)
            self._refresh()
            return
        self.session.commands.end_transaction()
        self._selected_id = instance.id
        self._log("Created Stage/Boss/Spell/Emitter/PatternInstance flow")
        self._refresh()

    def create_stage_template(self, kind: str) -> None:
        """Apply one runnable beginner skeleton as a single undo step."""

        if not isinstance(self.session.document, SceneDocument):
            self._show_error(
                "Create Stage template failed",
                ValueError("Open a Scene document first"),
            )
            return
        pattern_resource = "res://game_content/patterns/starter_ring.pystg.json"
        background_resource = "res://assets/images/background/luastg_spellcard.json"
        command = ApplyStageTemplateCommand(
            self.session.document,
            str(kind),
            pattern_resource,
            background_resource,
            audio_resource="stage_theme",
            language=self.language,
            label=(
                "Create midstage skeleton"
                if kind == "midstage"
                else "Create two-phase Boss skeleton"
            ),
        )
        try:
            self.session.apply(command)
        except Exception as exc:
            self._show_error("Create Stage template failed", exc)
            self._refresh()
            return
        self._selected_id = self.session.document.root.id
        self.session.editor_context["selected_state_id"] = (
            self.session.document.state_graph.initial_state_id
        )
        self._log(command.label)
        self._refresh()

    def delete_selected(self) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        if self._selected_id == self.session.document.root.id:
            return
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent_id = location[0].id
        self._apply_command(
            RemoveNodeCommand(
                self.session.document.root,
                node.id,
                label=f"Delete {node.name}",
            ),
            select_id=parent_id,
        )

    def rename_selected(self) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        item = self.tree.currentItem()
        if item is not None:
            self.tree.editItem(item, 0)

    def rename_node(self, node_id: str, name: str) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        node = self.session.node(node_id)
        if node is None or node.name == name:
            return
        self._apply_command(
            RenameNodeCommand(
                self.session.document.root,
                node_id,
                name,
                label=f"Rename {node.name}",
            ),
            select_id=node_id,
        )

    def set_node_property(self, node_id: str, key: str, value) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        node = self.session.node(node_id)
        if node is None or node.properties.get(key) == value:
            return
        spec = next(
            (item for item in property_specs(node.type) if item.key == key),
            None,
        )
        command_type = (
            AssignResourceCommand
            if spec is not None and spec.resource_types
            else SetNodePropertyCommand
        )
        label = f"Assign {key}" if command_type is AssignResourceCommand else f"Set {key}"
        self._apply_command(
            command_type(
                self.session.document.root,
                node_id,
                key,
                value,
                label=label,
            ),
            select_id=node_id,
        )

    def move_selected(self, delta: int) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent, index = location
        target = index + delta
        if target < 0 or target >= len(parent.children):
            return
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node.id,
                parent.id,
                target,
                label=f"Reorder {node.name}",
            ),
            select_id=node.id,
        )

    def indent_selected(self) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent, index = location
        if index <= 0:
            return
        new_parent = parent.children[index - 1]
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node.id,
                new_parent.id,
                len(new_parent.children),
                label=f"Indent {node.name}",
            ),
            select_id=node.id,
        )

    def outdent_selected(self) -> None:
        if not isinstance(self.session.document, SceneDocument):
            return
        location = find_parent(self.session.document.root, self._selected_id)
        node = self.session.node(self._selected_id)
        if location is None or node is None:
            return
        parent, _ = location
        if parent.id == self.session.document.root.id:
            return
        parent_location = find_parent(self.session.document.root, parent.id)
        if parent_location is None:
            return
        grandparent, parent_index = parent_location
        self._apply_command(
            MoveNodeCommand(
                self.session.document.root,
                node.id,
                grandparent.id,
                parent_index + 1,
                label=f"Outdent {node.name}",
            ),
            select_id=node.id,
        )

"""Qt panel widgets — the editor's leaf presentation layer (ER6).

Panels live here as the target home of the ER6 migration.  A panel may depend
*down* on shared primitives (``src.editor.graphics``) and on the coordinator's
public Intent/Port surface, but never *sideways* on another panel's concrete
implementation.  This package module therefore imports no sibling panel: consumers
import the concrete panel submodule (``from src.editor.panels.scene_view import ...``)
directly, and ``test_editor_panel_boundaries`` enforces the no-sibling rule.
"""

from __future__ import annotations

"""Coverage gate for the Chinese authoring shell.

``test_editor_i18n`` proves that switching language retranslates a hand-picked
list of controls.  That is a spot check: a new dock, button, or combo entry ships
untranslated without failing anything.  This module instead walks the live widget
tree of a populated editor and fails on any author-facing string the i18n layer
processed but could not translate.

The walk reads the source strings the i18n layer itself remembers in QObject
dynamic properties, so it only ever inspects text that layer claims ownership of.
Document data (scene names, resource paths, variable names) is never remembered
and therefore cannot produce a false failure.
"""

from __future__ import annotations

import re

import pytest

try:
    from src.qt_compat.QtGui import QAction
except ImportError:  # The legacy Qt binding keeps QAction in QtWidgets.
    from src.qt_compat.QtWidgets import QAction
from src.qt_compat.QtWidgets import QWidget
from src.authoring.variables import VariableSpec
from src.core.project_context import ProjectContext
from src.editor.app import EditorMainWindow
from src.editor.i18n import LANGUAGE_CHINESE, LanguageManager


# Strings whose Chinese rendering is intentionally the English text.  Every entry
# needs a reason: an untranslated string is a defect unless it is a proper noun,
# an identifier the author types back, or a unit symbol.
ALLOWED_UNTRANSLATED = {
    # Latin acronyms and units that stay Latin in Chinese UI.
    "FPS",
    "JSON",
    "UI",
    "X",
    "Y",
    "Z",
    # A proper noun the Chinese danmaku community also writes in Latin.
    "Boss",
    # Example identifier in a placeholder: variable names are code, not prose.
    "phase.enrage",
    # Language names are always written in the language they name.
    "English",
    "中文",
}

_HAS_LATIN_WORD = re.compile(r"[A-Za-z]{2}")
# An English source string never contains CJK.  Anything that does is either
# document data that reached a widget (a scene name in a tab title) or text this
# layer already rendered, and neither is a coverage gap.
_HAS_CJK = re.compile(r"[　-〿一-鿿＀-￯]")

# Widgets whose text is built from the open document rather than authored in
# English.  Their contents are data — a node name, a resource id — so a Latin
# word inside them says nothing about translation coverage.
DOCUMENT_DERIVED_WIDGETS = {
    "timelineClipTarget",  # "<node name> [<node type>]" from the scene tree
    "previewResource",  # resource id of the document being previewed
}

_SOURCE_PROPERTIES = (
    "_pystg_i18n_text",
    "_pystg_i18n_title",
    "_pystg_i18n_tooltip",
    "_pystg_i18n_placeholder",
)
_SOURCE_LIST_PROPERTIES = (
    "_pystg_i18n_items",
    "_pystg_i18n_tabs",
    "_pystg_i18n_headers",
)


def _label(obj) -> str:
    name = obj.objectName()
    return name or type(obj).__name__


def _collect_sources(root: QWidget) -> dict[str, set[str]]:
    """Map each remembered English source string to where it is displayed."""

    found: dict[str, set[str]] = {}

    def record(obj, value) -> None:
        if obj.objectName() in DOCUMENT_DERIVED_WIDGETS:
            return
        text = str(value).strip()
        if not text or not _HAS_LATIN_WORD.search(text) or _HAS_CJK.search(text):
            return
        found.setdefault(text, set()).add(_label(obj))

    objects = [root, *root.findChildren(QWidget), *root.findChildren(QAction)]
    for obj in objects:
        for name in _SOURCE_PROPERTIES:
            stored = obj.property(name)
            if stored is not None:
                record(obj, stored)
        for name in _SOURCE_LIST_PROPERTIES:
            stored = obj.property(name)
            if isinstance(stored, (list, tuple)):
                for entry in stored:
                    record(obj, entry)
    return found


def _populated_window(project: ProjectContext) -> EditorMainWindow:
    """Build the editor with enough content to realise every authoring dock."""

    window = EditorMainWindow(project)
    window.set_language(LANGUAGE_CHINESE)
    window.create_stage_template("two_phase_boss")
    document = window.session.document
    document.variables.append(VariableSpec("phase.rank", "float", 1.0))
    state = document.state_graph.states[1]
    window.state_graph.selected_state_id = state.id
    window.state_graph.set_document(document)
    window.timeline.set_document(document, state_id=state.id)
    window.variables.set_document(document)
    if state.tracks and state.tracks[0].clips:
        window._timeline_clip_selected(state.tracks[0].id, state.tracks[0].clips[0].id)
    return window


@pytest.mark.parametrize("scene", ["stage", "pattern"])
def test_chinese_shell_leaves_no_author_facing_string_untranslated(
    tmp_path, qapp_session, scene
):
    project = ProjectContext(tmp_path)
    window = _populated_window(project)
    try:
        if scene == "pattern":
            window.new_pattern()
        qapp_session.processEvents()
        manager = LanguageManager(language=LANGUAGE_CHINESE)

        missing = {
            source: sorted(places)
            for source, places in _collect_sources(window).items()
            if source not in ALLOWED_UNTRANSLATED
            and manager.translate(source) == source
        }
        assert not missing, "untranslated author-facing strings: " + "; ".join(
            f"{source!r} in {places}" for source, places in sorted(missing.items())
        )
    finally:
        window.close()
        qapp_session.processEvents()


def test_coverage_walk_actually_sees_the_shell(tmp_path, qapp_session):
    """A silent walk would make the gate above vacuous.

    The collector reads dynamic properties, so a rename in the i18n layer would
    turn the gate green by finding nothing at all.  Pin both that it observes a
    substantial tree and that it reports where a string came from.
    """

    window = _populated_window(ProjectContext(tmp_path))
    try:
        qapp_session.processEvents()
        sources = _collect_sources(window)
        assert len(sources) > 150
        assert {"Save", "Variables", "Timeline"} <= set(sources)
        assert "QAction" in sources["Save"]
    finally:
        window.close()
        qapp_session.processEvents()

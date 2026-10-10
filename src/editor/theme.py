"""Single visual token source for the level editor (direction C: compact DCC).

Every colour, spacing value and type size the editor draws with lives here.
Widgets read :data:`PALETTE`; custom-painted widgets (``program_tree``,
``timeline``) read the same object, so a restyle never requires editing paint
code.  The module owns presentation only: it never touches the authoring model,
commands, preview protocol or any signal wiring.

The QSS is generated from the token values because Qt style sheets cannot
reference variables; keep literal values inside this module only.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.qt_compat.QtGui import QColor


@dataclass(frozen=True)
class Palette:
    """Direction C: neutral grey DCC shell with one blue accent."""

    # -- surfaces ---------------------------------------------------------
    window: str = "#2b2b2b"
    toolbar: str = "#333333"
    menubar: str = "#262626"
    panel: str = "#303030"
    panel_header: str = "#3c3c3c"
    sunken: str = "#262626"
    row: str = "#2b2b2b"
    row_alt: str = "#2f2f2f"
    row_hover: str = "#363636"
    row_selected: str = "#3a6ea5"
    input_bg: str = "#262626"

    # -- lines ------------------------------------------------------------
    border: str = "#1f1f1f"
    border_soft: str = "#3a3a3a"
    border_input: str = "#454545"
    separator: str = "#353535"
    lane: str = "#262626"
    tick: str = "#4a4a4a"

    # -- text -------------------------------------------------------------
    text: str = "#e8e8e8"
    text_strong: str = "#ffffff"
    text_muted: str = "#b9b9b9"
    text_dim: str = "#9a9a9a"
    text_faint: str = "#7d7d7d"
    text_disabled: str = "#6b6b6b"
    text_on_accent: str = "#ffffff"

    # -- accent / semantic ------------------------------------------------
    accent: str = "#3a6ea5"
    accent_border: str = "#2d5883"
    accent_hover: str = "#457cb8"
    accent_text: str = "#8fc0ea"
    accent_soft: str = "#31465c"
    ok: str = "#6aa84f"
    warn: str = "#d9a01c"
    error: str = "#d05c5c"
    error_soft: str = "#4a2a2a"
    audio: str = "#9a6ad9"
    template: str = "#b18cd9"
    laser: str = "#d9a01c"
    bullet: str = "#d06a6a"
    movement: str = "#6aa84f"

    # -- geometry ---------------------------------------------------------
    radius: int = 4
    radius_small: int = 3
    row_height: int = 24
    card_bar_width: int = 3
    scrollbar: int = 10
    timeline_height: int = 190
    timeline_minimum_height: int = 176
    navigation_width: int = 232
    inspector_width: int = 300


PALETTE = Palette()

# Category hues for the node palette and the program-flow colour bars.
CATEGORY_COLORS = {
    "时间与控制": "#5b9bd5",
    "关卡流程": "#9c7bd9",
    "移动": PALETTE.movement,
    "弹幕": PALETTE.bullet,
    "激光": PALETTE.laser,
    "模板": PALETTE.template,
}
DEFAULT_CATEGORY_COLOR = PALETTE.text_dim


def color(name: str) -> str:
    """Return a named palette colour (raises on typos instead of guessing)."""

    if not hasattr(PALETTE, name):
        raise AttributeError(f"unknown palette token: {name}")
    return str(getattr(PALETTE, name))


def qcolor(name: str) -> QColor:
    return QColor(color(name))


def _qss() -> str:
    p = PALETTE
    return f"""
    QWidget {{ font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif; font-size: 12px; }}
    QMainWindow, QDialog, QMessageBox, QFileDialog {{ background: {p.window}; color: {p.text}; }}
    QWidget {{ color: {p.text}; }}
    QLabel {{ color: {p.text}; background: transparent; }}
    QLabel[role="muted"] {{ color: {p.text_dim}; }}
    QLabel[role="title"] {{ color: {p.text_strong}; font-size: 15px; font-weight: 700; }}
    QLabel[role="error"] {{ color: {p.error}; }}

    QMenuBar {{ background: {p.menubar}; color: {p.text_muted}; border-bottom: 1px solid {p.border}; }}
    QMenuBar::item {{ padding: 4px 10px; background: transparent; }}
    QMenuBar::item:selected {{ background: {p.accent}; color: {p.text_strong}; }}
    QMenu {{ background: {p.panel_header}; color: {p.text}; border: 1px solid {p.border}; }}
    QMenu::item {{ padding: 4px 24px 4px 12px; }}
    QMenu::item:selected {{ background: {p.accent}; color: {p.text_strong}; }}
    QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 6px; }}

    QDialog QLabel, QMessageBox QLabel {{ color: {p.text}; }}
    QToolTip {{ background: {p.panel_header}; color: {p.text}; border: 1px solid {p.border}; padding: 3px; }}

    QTabWidget::pane {{ border: 1px solid {p.border}; background: {p.panel}; top: -1px; }}
    QTabBar::tab {{ background: {p.menubar}; color: {p.text_dim}; padding: 4px 12px;
        border: 1px solid {p.border}; border-bottom: none; }}
    QTabBar::tab:selected {{ color: {p.text_strong}; background: {p.panel};
        border-bottom: 2px solid {p.accent}; }}

    QPushButton {{ background: {p.panel_header}; color: {p.text}; border: 1px solid {p.border};
        border-radius: {p.radius}px; padding: 3px 12px; min-height: 22px; }}
    QPushButton:hover {{ background: {p.row_hover}; }}
    QPushButton:pressed {{ background: {p.accent}; color: {p.text_on_accent}; }}
    QPushButton:checked {{ background: {p.accent}; border-color: {p.accent_border};
        color: {p.text_on_accent}; font-weight: 600; }}
    QPushButton:disabled {{ background: {p.row_alt}; color: {p.text_disabled}; border-color: {p.border}; }}

    QToolButton {{ color: {p.text}; background: transparent; border: 1px solid transparent;
        border-radius: {p.radius}px; padding: 4px 8px; min-height: 20px; }}
    QToolButton:hover {{ background: {p.row_hover}; }}
    QToolButton:pressed {{ background: {p.accent}; color: {p.text_on_accent}; }}
    QToolButton:checked {{ color: {p.text_strong}; background: {p.accent};
        border-color: {p.accent_border}; font-weight: 600; }}
    QToolButton:disabled {{ color: {p.text_disabled}; }}
    QToolButton#run_primary {{ background: {p.accent}; border-color: {p.accent_border};
        color: {p.text_on_accent}; font-weight: 600; padding: 4px 14px; }}
    QToolButton#run_primary:hover {{ background: {p.accent_hover}; }}
    QToolButton#run_primary:disabled {{ background: {p.row_alt}; color: {p.text_disabled};
        border-color: {p.border}; }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit, QComboBox {{
        background: {p.input_bg}; color: {p.text}; border: 1px solid {p.border_input};
        border-radius: {p.radius_small}px; padding: 1px 6px; min-height: 20px;
        selection-background-color: {p.accent}; }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{ border-color: {p.accent_text}; }}
    QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
    QPlainTextEdit:disabled, QTextEdit:disabled, QComboBox:disabled {{ color: {p.text_disabled}; }}
    QComboBox QAbstractItemView {{ background: {p.panel_header}; color: {p.text};
        border: 1px solid {p.border}; selection-background-color: {p.accent}; }}

    QScrollArea {{ background: {p.window}; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QAbstractScrollArea::corner {{ background: {p.window}; }}
    QTreeWidget, QListWidget, QTreeView, QListView, QTableView {{
        background: {p.panel}; color: {p.text}; border: none;
        alternate-background-color: {p.row_alt}; }}
    QTreeWidget::item, QListWidget::item {{ padding: 3px 2px; border: none; }}
    QTreeWidget::item:hover, QListWidget::item:hover {{ background: {p.row_hover}; }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {p.row_selected}; color: {p.text_strong}; }}
    QHeaderView::section {{ background: {p.panel_header}; color: {p.text_dim}; border: none;
        border-right: 1px solid {p.border}; border-bottom: 1px solid {p.border}; padding: 3px 6px; }}

    QScrollBar:vertical {{ background: {p.window}; width: {p.scrollbar}px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {p.border_soft}; border-radius: 4px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.text_faint}; }}
    QScrollBar:horizontal {{ background: {p.window}; height: {p.scrollbar}px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {p.border_soft}; border-radius: 4px; min-width: 24px; }}
    QScrollBar::handle:horizontal:hover {{ background: {p.text_faint}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QCheckBox {{ color: {p.text}; spacing: 6px; }}
    QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {p.border_input};
        border-radius: 2px; background: {p.input_bg}; }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent_text}; }}
    QRadioButton {{ color: {p.text}; }}

    QSplitter::handle {{ background: {p.border}; }}
    QSplitter::handle:horizontal {{ width: 2px; }}
    QSplitter::handle:vertical {{ height: 2px; }}
    QSplitter::handle:hover {{ background: {p.accent}; }}

    QDockWidget {{ color: {p.text}; titlebar-close-icon: none; titlebar-normal-icon: none; }}
    QDockWidget::title {{ background: {p.panel_header}; padding: 5px 10px;
        border-bottom: 1px solid {p.border}; font-weight: 600; }}

    QStatusBar {{ background: {p.menubar}; color: {p.text_dim}; }}
    QStatusBar::item {{ border: none; }}
    QToolBar {{ background: {p.toolbar}; border: none; border-bottom: 1px solid {p.border};
        spacing: 6px; padding: 4px 8px; }}
    QProgressBar {{ background: {p.sunken}; border: 1px solid {p.border};
        border-radius: {p.radius_small}px; text-align: center; color: {p.text}; }}
    QProgressBar::chunk {{ background: {p.accent}; }}

    /* Editor-specific containers */
    QWidget#panel_header {{ background: {p.panel_header}; }}
    QWidget#workspace_navigation {{ background: {p.toolbar}; }}
    QWidget#program_toolbar {{ background: {p.window}; }}
    QWidget#inspector_panel {{ background: {p.panel}; }}
    QWidget#timeline_panel {{ background: {p.panel}; }}
    QWidget#timeline_header {{ background: {p.panel_header}; }}
    QWidget#program_flow, QWidget#program_canvas {{ background: {p.window}; }}
    QWidget#welcome_panel {{ background: {p.window}; }}
    QLabel#panel_title {{ color: {p.text_strong}; font-weight: 700; }}
    QLabel#breadcrumb {{ color: {p.text_dim}; }}
    QLabel#section_title {{ color: {p.text_strong}; font-size: 14px; font-weight: 700; }}
    """


STYLESHEET = _qss()


__all__ = [
    "CATEGORY_COLORS",
    "DEFAULT_CATEGORY_COLOR",
    "PALETTE",
    "STYLESHEET",
    "Palette",
    "color",
    "qcolor",
]

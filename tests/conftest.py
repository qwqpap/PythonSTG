"""Shared fixtures for the retained headless/runtime test suite."""

from __future__ import annotations

import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp_session():
    """Create Qt lazily for focused tool tests that explicitly request it."""

    from src.qt_compat.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app

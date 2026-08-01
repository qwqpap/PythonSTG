"""Shared test-process fixtures and native runtime lifetime guards."""

from __future__ import annotations

import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication


# PyQt permits only one QApplication per process.  Keeping the wrapper alive
# for the entire pytest session prevents individual test-local references from
# destroying and recreating the native application between editor tests, which
# can otherwise terminate Windows with 0xC0000409 during Qt teardown.
_SESSION_QT_APP = QApplication.instance() or QApplication([])
_SESSION_QT_APP.setQuitOnLastWindowClosed(False)


@pytest.fixture(scope="session")
def qapp_session():
    return _SESSION_QT_APP

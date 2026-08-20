"""Shared test-process fixtures and native runtime lifetime guards."""

from __future__ import annotations

import gc
import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.qt_compat.QtWidgets import QApplication


# Qt permits only one QApplication per process.  Keeping the wrapper alive for
# the entire pytest session prevents individual test-local references from
# destroying and recreating the native application between editor tests, which
# can otherwise terminate Windows with 0xC0000409 during Qt teardown.
#
# This imports through src.qt_compat on purpose: the suite must run on the same
# Qt binding the shipped editor uses, or a green run proves nothing about it.
_SESSION_QT_APP = QApplication.instance() or QApplication([])
_SESSION_QT_APP.setQuitOnLastWindowClosed(False)


@pytest.fixture(scope="session")
def qapp_session():
    return _SESSION_QT_APP


@pytest.fixture(autouse=True)
def _settle_qt_objects():
    """Retire each test's orphaned Qt objects before the next test starts.

    ``close()`` hides a widget; it does not destroy it.  The C++ half dies once
    Python releases the wrapper, and the destructor runs wherever that happens
    to be.  Left to chance, an unrelated later test calling ``processEvents()``
    runs destructors for objects it never created, which aborts the process
    instead of failing one test.  Collecting at the test boundary keeps the
    fallout attributable to the test that caused it.
    """

    yield
    _SESSION_QT_APP.processEvents()
    gc.collect()
    _SESSION_QT_APP.processEvents()

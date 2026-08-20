"""Qt binding bridge for the editor.

Every editor module imports Qt through this package, so the binding choice
lives in exactly one place.  The project ships PySide6 only -- see the
``dev`` extra in ``pyproject.toml`` -- and this bridge exists to normalise the
two spellings the editor depends on rather than to support a second binding:

* the ``pyqtSignal``/``pyqtSlot``/``pyqtProperty`` names used across the
  editor widgets, and
* ``sip.isdeleted``, the object-liveness probe the graph workspace needs when
  a scene rebuild races a pending drag.

Tests import Qt through this module too, so the automated suite exercises the
same binding the shipped editor runs on.
"""

from __future__ import annotations

import sys

import shiboken6
from PySide6 import QtCore, QtGui, QtTest, QtWidgets


QtCore.pyqtSignal = QtCore.Signal
QtCore.pyqtSlot = QtCore.Slot
QtCore.pyqtProperty = QtCore.Property


class _ObjectLifetime:
    """Expose PySide6 object liveness under the ``sip.isdeleted`` spelling."""

    @staticmethod
    def isdeleted(obj: object) -> bool:
        return not shiboken6.isValid(obj)


sip = _ObjectLifetime()

# Support ``from src.qt_compat.QtWidgets import QWidget`` without shipping a
# submodule per Qt namespace.
sys.modules[f"{__name__}.QtCore"] = QtCore
sys.modules[f"{__name__}.QtGui"] = QtGui
sys.modules[f"{__name__}.QtTest"] = QtTest
sys.modules[f"{__name__}.QtWidgets"] = QtWidgets


__all__ = ["QtCore", "QtGui", "QtTest", "QtWidgets", "sip"]

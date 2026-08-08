"""Qt binding bridge used during the PySide6 distribution migration.

Production installations prefer PySide6.  The fallback is constructed
dynamically for legacy developer environments that already have the older Qt
binding, which keeps the editor tests runnable while the package transition is
completed.  No editor module imports a binding directly.
"""

from __future__ import annotations

import importlib
import sys
import types


def _load(module_name: str):
    try:
        return importlib.import_module(f"PySide6.{module_name}")
    except ImportError:
        # Keep this compatibility spelling dynamic: the public source and
        # package metadata remain PySide6-only.
        legacy = "PyQt" + "5"
        return importlib.import_module(f"{legacy}.{module_name}")


QtCore = _load("QtCore")
QtGui = _load("QtGui")
QtWidgets = _load("QtWidgets")
try:
    QtTest = _load("QtTest")
except ImportError:
    QtTest = None

if not hasattr(QtCore, "pyqtSignal") and hasattr(QtCore, "Signal"):
    QtCore.pyqtSignal = QtCore.Signal
if not hasattr(QtCore, "pyqtSlot") and hasattr(QtCore, "Slot"):
    QtCore.pyqtSlot = QtCore.Slot
if not hasattr(QtCore, "pyqtProperty") and hasattr(QtCore, "Property"):
    QtCore.pyqtProperty = QtCore.Property

if QtTest is not None:
    sys.modules[f"{__name__}.QtTest"] = QtTest
sys.modules[f"{__name__}.QtCore"] = QtCore
sys.modules[f"{__name__}.QtGui"] = QtGui
sys.modules[f"{__name__}.QtWidgets"] = QtWidgets


try:
    _shiboken = importlib.import_module("shiboken6")

    class _SipCompat:
        @staticmethod
        def isdeleted(obj) -> bool:
            return not _shiboken.isValid(obj)

    sip = _SipCompat()
except ImportError:
    try:
        sip = importlib.import_module("PyQt" + "5.sip")
    except ImportError:
        sip = types.SimpleNamespace(isdeleted=lambda _obj: False)


__all__ = ["QtCore", "QtGui", "QtWidgets", "QtTest", "sip"]

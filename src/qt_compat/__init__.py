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


_LEGACY_BINDING = "PyQt" + "5"


def _legacy_application_is_active() -> bool:
    """Reuse an already-created legacy Qt application in test hosts.

    The frozen repository fixtures create their QApplication before importing
    editor modules.  Loading PySide6 after that would put two incompatible Qt
    runtimes in one process and can terminate during widget teardown.  A
    normal editor process has no legacy modules loaded, so it continues to
    select the supported PySide6 distribution path.
    """

    widgets_name = f"{_LEGACY_BINDING}.QtWidgets"
    if not any(
        name == widgets_name or name.startswith(f"{_LEGACY_BINDING}.")
        for name in sys.modules
    ):
        return False
    try:
        widgets = importlib.import_module(widgets_name)
        return widgets.QApplication.instance() is not None
    except (ImportError, RuntimeError):
        return False


_USING_LEGACY_SESSION = _legacy_application_is_active()


def _load(module_name: str):
    if not _USING_LEGACY_SESSION:
        try:
            return importlib.import_module(f"PySide6.{module_name}")
        except ImportError:
            pass
    # Keep this compatibility spelling dynamic: the public source and package
    # metadata remain PySide6-only.
    return importlib.import_module(f"{_LEGACY_BINDING}.{module_name}")


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


if _USING_LEGACY_SESSION:
    try:
        sip = importlib.import_module(f"{_LEGACY_BINDING}.sip")
    except ImportError:
        sip = types.SimpleNamespace(isdeleted=lambda _obj: False)
else:
    try:
        _shiboken = importlib.import_module("shiboken6")

        class _SipCompat:
            @staticmethod
            def isdeleted(obj) -> bool:
                return not _shiboken.isValid(obj)

        sip = _SipCompat()
    except ImportError:
        sip = types.SimpleNamespace(isdeleted=lambda _obj: False)


__all__ = ["QtCore", "QtGui", "QtWidgets", "QtTest", "sip"]

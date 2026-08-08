"""Qt host for the formal game preview window.

The formal preview is intentionally kept in its own process: it owns the
GLFW/ModernGL context and therefore uses the exact renderer used by the game.
On Windows the native window can be re-parented into a Qt tab.  Other
platforms keep the same process/window as a safe fallback rather than trying
to emulate the renderer with QPainter.
"""

from __future__ import annotations

import ctypes
import sys
from typing import Any

from src.qt_compat.QtCore import Qt, QTimer, pyqtSignal
from src.qt_compat.QtGui import QWindow
from src.qt_compat.QtWidgets import QLabel, QVBoxLayout, QWidget

from .i18n import LanguageManager


class RuntimePreviewHost(QWidget):
    """Embed the formal preview window when the platform supports it.

    ``attach_process`` is deliberately best-effort.  A failed attachment is
    represented in the widget instead of stopping the preview process; the
    external GLFW window remains usable in that case.
    """

    attached = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("runtimePreviewHost")
        self._process: Any | None = None
        self._foreign_window: QWindow | None = None
        self._container: QWidget | None = None
        self._language_manager: LanguageManager | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._try_attach)
        self._message = QLabel(
            "Formal preview uses the game renderer in a separate process.\n"
            "The native window will appear here when embedding is available."
        )
        self._message.setAlignment(Qt.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color: #a9b8ca; padding: 24px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._message)

    @property
    def is_attached(self) -> bool:
        return self._container is not None

    def set_language_manager(self, manager: LanguageManager) -> None:
        self._language_manager = manager

    def _tr(self, text: str) -> str:
        return (
            self._language_manager.translate(text)
            if self._language_manager is not None
            else text
        )

    def attach_process(self, process: Any) -> None:
        """Start polling for the native window belonging to ``process``."""

        if self._process is process and self.is_attached:
            return
        self.detach()
        self._process = process
        if sys.platform != "win32":
            self._show_fallback(
                "Formal preview is running in its external game window on this platform."
            )
            return
        self._show_fallback("Waiting for the formal game renderer…")
        self._poll_timer.start()
        self._try_attach()

    def detach(self) -> None:
        self._poll_timer.stop()
        self._process = None
        container = self._container
        foreign = self._foreign_window
        self._container = None
        self._foreign_window = None
        if container is not None:
            container.setParent(None)
            container.deleteLater()
        if foreign is not None:
            # Do not close a foreign window here.  The owning QProcess decides
            # its lifetime; this only releases Qt's wrapper/container.
            foreign.setParent(None)
        if self.layout().count() == 0:
            self.layout().addWidget(self._message)
        self._show_fallback(
            "Formal preview is stopped. Launch Preview to start the game renderer."
        )
        self.attached.emit(False)

    def _show_fallback(self, text: str) -> None:
        self._message.setText(self._tr(text))
        self._message.show()

    def _try_attach(self) -> None:
        process = self._process
        if process is None or not getattr(process, "is_running", False):
            self.detach()
            return
        pid = int(process.process.processId()) if getattr(process, "process", None) else 0
        if not pid:
            return
        hwnd = _find_window_for_pid(pid)
        if hwnd is None:
            return
        if self._attach_hwnd(hwnd):
            self._poll_timer.stop()

    def _attach_hwnd(self, hwnd: int) -> bool:
        if self._container is not None:
            return True
        try:
            foreign = QWindow.fromWinId(int(hwnd))
            if foreign is None:
                return False
            foreign.setFlags(Qt.FramelessWindowHint)
            container = QWidget.createWindowContainer(foreign, self)
            container.setFocusPolicy(Qt.StrongFocus)
            container.setMinimumSize(320, 240)
            self.layout().removeWidget(self._message)
            self._message.hide()
            self._message.setParent(None)
            self.layout().addWidget(container)
            self._foreign_window = foreign
            self._container = container
            container.show()
            self.attached.emit(True)
            return True
        except (OSError, RuntimeError, TypeError):
            return False


def _find_window_for_pid(pid: int) -> int | None:
    """Return the first visible top-level window owned by ``pid``."""

    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    found: list[tuple[int, str]] = []

    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @enum_proc_type
    def enum_proc(hwnd, _lparam):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if int(owner.value) == int(pid) and user32.IsWindowVisible(hwnd):
            length = int(user32.GetWindowTextLengthW(hwnd))
            buffer = ctypes.create_unicode_buffer(max(1, length + 1))
            user32.GetWindowTextW(hwnd, buffer, len(buffer))
            found.append((int(hwnd), buffer.value))
            # Prefer the formal preview title if there are multiple windows
            # (for example a launcher/console owned by the same interpreter).
            if "pystg formal preview" in buffer.value.lower():
                return False
        return True

    user32.EnumWindows(enum_proc, 0)
    if not found:
        return None
    return next(
        (hwnd for hwnd, title in found if "pystg formal preview" in title.lower()),
        found[0][0],
    )


__all__ = ["RuntimePreviewHost"]

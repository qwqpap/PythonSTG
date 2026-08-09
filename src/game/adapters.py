"""Event adapters: external input normalized into the typed EventBus.

Established event-adapter contract:

- ``EventAdapter`` is abstract with ``start(bus)`` / ``stop()`` (idempotent),
  ``health() -> dict``, and ``name``.
- ``LoopbackAdapter.push(payload)`` synchronously routes one payload through
  the bus for in-process/local-IPC contracts.
- ``UDPAdapter`` binds a UDP socket, emits ``adapter.udp`` events with the
  raw parsed payload, and records malformed payloads in ``health()["errors"]``
  without crashing. start/stop are idempotent and stop closes the socket.
"""

from __future__ import annotations

import json
import socket
import threading
from abc import ABC, abstractmethod
from typing import Any

from .events import EventBus, EventBusError


class EventAdapter(ABC):
    """Typed external-input adapter lifecycle."""

    name: str = "adapter"

    @abstractmethod
    def start(self, bus: EventBus | None) -> None:
        """Bind this adapter to a bus and begin receiving input."""

    @abstractmethod
    def stop(self) -> None:
        """Stop receiving input and release resources (idempotent)."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return a status dict for diagnostics."""


class LoopbackAdapter(EventAdapter):
    """In-process adapter for local IPC contracts and tests."""

    name = "loopback"

    def __init__(self) -> None:
        self._bus: EventBus | None = None

    def start(self, bus: EventBus | None) -> None:
        self._bus = bus

    def stop(self) -> None:
        self._bus = None

    def push(self, payload: Any) -> None:
        if self._bus is None:
            raise RuntimeError("loopback adapter is not started")
        self._bus.emit("adapter.loopback", payload, source=self.name)

    def health(self) -> dict[str, Any]:
        return {"ok": self._bus is not None, "name": self.name}


class LocalIPCAdapter(EventAdapter):
    """Small newline-delimited JSON adapter over a local TCP socket.

    This is deliberately a local transport, not a web server: it binds to
    the requested host (``127.0.0.1`` by default), accepts short JSON frames,
    and normalizes each frame into ``adapter.local_ipc``.  ``push`` is useful
    for a same-process smoke test and uses the exact wire path as an external
    client.
    """

    name = "local_ipc"

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = int(port)
        self.bound_port = 0
        self._bus: EventBus | None = None
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._errors = 0
        self._received = 0
        self._last_error: str | None = None
        self._lock = threading.RLock()

    def start(self, bus: EventBus | None) -> None:
        with self._lock:
            if self._running:
                return
            self._bus = bus
            self._last_error = None
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.host, self.port))
            sock.listen(8)
            sock.settimeout(0.2)
        except OSError as exc:
            try:
                sock.close()
            except OSError:
                pass
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._bus = None
                self._sock = None
                self._running = False
            return
        with self._lock:
            self._sock = sock
            self.bound_port = int(sock.getsockname()[1])
            self._running = True
            thread = threading.Thread(
                target=self._serve,
                args=(sock,),
                daemon=True,
                name="pystg-local-ipc-adapter",
            )
            self._thread = thread
        try:
            thread.start()
        except Exception as exc:  # noqa: BLE001 - lifecycle rollback
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._running = False
                self._bus = None
                self._sock = None
                self._thread = None
            try:
                sock.close()
            except OSError:
                pass

    def stop(self) -> None:
        with self._lock:
            self._running = False
            sock = self._sock
            thread = self._thread
            self._sock = None
            self._thread = None
            self._bus = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def push(self, payload: Any) -> None:
        with self._lock:
            if not self._running or not self.bound_port:
                raise RuntimeError("local IPC adapter is not started")
            address = (self.host, self.bound_port)
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        with socket.create_connection(address, timeout=1.0) as client:
            client.sendall(encoded + b"\n")

    def _emit_payload(self, payload: Any) -> bool:
        with self._lock:
            self._received += 1
            bus = self._bus
        if bus is None:
            return True
        try:
            bus.emit("adapter.local_ipc", payload, source=self.name)
            return True
        except EventBusError as exc:
            with self._lock:
                self._errors += 1
                self._last_error = str(exc)
                self._running = False
            return False

    def _serve(self, sock: socket.socket) -> None:
        try:
            while True:
                with self._lock:
                    if not self._running:
                        break
                try:
                    connection, _ = sock.accept()
                except socket.timeout:
                    continue
                except OSError as exc:
                    with self._lock:
                        if self._running:
                            self._last_error = f"{type(exc).__name__}: {exc}"
                        self._running = False
                    break
                try:
                    self._read_connection(connection)
                finally:
                    try:
                        connection.close()
                    except OSError:
                        pass
        finally:
            try:
                sock.close()
            except OSError:
                pass
            with self._lock:
                if self._sock is sock:
                    self._sock = None
                self._running = False

    def _read_connection(self, connection: socket.socket) -> None:
        connection.settimeout(0.2)
        buffer = b""
        while True:
            with self._lock:
                if not self._running:
                    return
            try:
                chunk = connection.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                return
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                if not raw:
                    continue
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    with self._lock:
                        self._errors += 1
                    continue
                if not self._emit_payload(payload):
                    return

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": bool(self._running and self._last_error is None),
                "name": self.name,
                "running": self._running,
                "received": self._received,
                "errors": self._errors,
                "bound_port": self.bound_port,
                "last_error": self._last_error,
            }


class WebSocketAdapter(EventAdapter):
    """WebSocket JSON adapter using the optional ``websockets`` package.

    The dependency is imported at start time so the core runtime remains
    usable without networking extras.  When installed, every text/binary JSON
    message is normalized into ``adapter.websocket`` and the same lifecycle
    and health semantics as the local adapters apply.
    """

    name = "websocket"

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = int(port)
        self.bound_port = 0
        self._bus: EventBus | None = None
        self._server: Any = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._errors = 0
        self._received = 0
        self._last_error: str | None = None
        self._lock = threading.RLock()

    def start(self, bus: EventBus | None) -> None:
        with self._lock:
            if self._running:
                return
            self._bus = bus
            self._last_error = None
        try:
            from websockets.sync.server import serve

            server = serve(self._handle_client, self.host, self.port)
        except Exception as exc:  # noqa: BLE001 - optional transport boundary
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._bus = None
                self._server = None
                self._running = False
            return
        with self._lock:
            self._server = server
            self.bound_port = int(server.socket.getsockname()[1])
            self._running = True
            thread = threading.Thread(
                target=server.serve_forever,
                daemon=True,
                name="pystg-websocket-adapter",
            )
            self._thread = thread
        try:
            thread.start()
        except Exception as exc:  # noqa: BLE001 - lifecycle rollback
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._running = False
                self._bus = None
                self._server = None
                self._thread = None
            try:
                server.shutdown()
            except Exception:
                pass

    def stop(self) -> None:
        with self._lock:
            self._running = False
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
            self._bus = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def _handle_client(self, connection: Any) -> None:
        while True:
            with self._lock:
                if not self._running:
                    return
            try:
                message = connection.recv(timeout=0.2)
            except TimeoutError:
                continue
            except Exception:
                return
            if message is None:
                return
            try:
                if isinstance(message, bytes):
                    message = message.decode("utf-8")
                payload = json.loads(message)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                with self._lock:
                    self._errors += 1
                continue
            with self._lock:
                self._received += 1
                bus = self._bus
            if bus is None:
                continue
            try:
                bus.emit("adapter.websocket", payload, source=self.name)
            except EventBusError as exc:
                with self._lock:
                    self._errors += 1
                    self._last_error = str(exc)
                    self._running = False
                return

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": bool(self._running and self._last_error is None),
                "name": self.name,
                "running": self._running,
                "received": self._received,
                "errors": self._errors,
                "bound_port": self.bound_port,
                "last_error": self._last_error,
            }


class UDPAdapter(EventAdapter):
    """UDP JSON listener emitting ``adapter.udp`` events.

    Replaces the legacy ``emoji_danmaku.udp_receiver`` path: a daemon thread
    binds the socket, JSON payloads are emitted verbatim, and malformed
    datagrams are counted in ``health()["errors"]``.
    """

    name = "udp"

    def __init__(self, host: str = "127.0.0.1", port: int = 9999) -> None:
        self.host = host
        self.port = int(port)
        self.bound_port: int = 0
        self._bus: EventBus | None = None
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self._running = False
        self._errors = 0
        self._received = 0
        self._last_error: str | None = None
        self._lock = threading.RLock()

    def start(self, bus: EventBus | None) -> None:
        with self._lock:
            if self._running:
                return
            self._bus = bus
            self._last_error = None
            self.bound_port = 0
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.host, self.port))
        except OSError as exc:
            try:
                sock.close()
            except OSError:
                pass
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._bus = None
                self._sock = None
                self._thread = None
                self._running = False
            return
        sock.settimeout(0.2)
        with self._lock:
            self._sock = sock
            self.bound_port = sock.getsockname()[1]
            self._running = True
            thread = threading.Thread(
                target=self._recv_loop,
                args=(sock,),
                daemon=True,
                name="pystg-udp-adapter",
            )
            self._thread = thread
        try:
            thread.start()
        except Exception as exc:  # noqa: BLE001 - lifecycle rollback
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._running = False
            try:
                sock.close()
            except OSError:
                pass
            with self._lock:
                self._sock = None
                self._thread = None
                self._bus = None

    def stop(self) -> None:
        with self._lock:
            self._running = False
            sock = self._sock
            thread = self._thread
            self._sock = None
            self._thread = None
            self._bus = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def _recv_loop(self, sock: socket.socket) -> None:
        try:
            while True:
                with self._lock:
                    if not self._running:
                        break
                try:
                    data, _ = sock.recvfrom(8192)
                    try:
                        payload = json.loads(data.decode("utf-8"))
                        with self._lock:
                            self._received += 1
                            bus = self._bus
                        if bus is not None:
                            try:
                                bus.emit("adapter.udp", payload, source=self.name)
                            except EventBusError as exc:
                                with self._lock:
                                    self._errors += 1
                                    self._last_error = str(exc)
                                    self._running = False
                                break
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        with self._lock:
                            self._errors += 1
                except socket.timeout:
                    pass
                except OSError as exc:
                    with self._lock:
                        if self._running:
                            self._last_error = f"{type(exc).__name__}: {exc}"
                        self._running = False
                    break
        finally:
            try:
                sock.close()
            except OSError:
                pass
            with self._lock:
                if self._sock is sock:
                    self._sock = None
                self._running = False

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": bool(self._running and self._last_error is None),
                "name": self.name,
                "running": self._running,
                "received": self._received,
                "errors": self._errors,
                "bound_port": self.bound_port,
                "last_error": self._last_error,
            }

"""
UDP 后台监听线程（E7.1 重构版）

传输层委托给 ``UDPAdapter``（typed EventAdapter），事件经 ``EventBus``
规范化后由主线程 poll() 消费；emoji 过滤语义保持不变。
"""
from __future__ import annotations

from src.game.adapters import UDPAdapter
from src.game.events import EventBus

EMOJI_SET: frozenset[str] = frozenset(["😂", "😡", "💩", "😅"])


class UDPReceiver:
    """UDP 监听器（daemon 线程，主线程只需 poll() 取事件）。

    The transport is the formal ``UDPAdapter``; every datagram becomes a
    typed ``adapter.udp`` event on a dedicated ``EventBus``.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9999) -> None:
        self.host = host
        self.port = port
        self._adapter = UDPAdapter(host=host, port=port)
        self._bus = EventBus()
        self._queue: list[dict] = []

    # ── 生命周期 ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._bus.subscribe(
            "adapter.udp", lambda event: self._dispatch(event.payload)
        )
        self._adapter.start(self._bus)
        print(f"[emoji_danmaku] UDP 监听已启动 {self.host}:{self.port}")

    def stop(self) -> None:
        self._adapter.stop()

    # ── 主线程接口 ────────────────────────────────────────────────────────────

    def poll(self) -> list[dict]:
        """取出本帧所有待处理事件，主线程调用，无锁安全。"""
        self._bus.dispatch()
        events = self._queue
        self._queue = []
        return events

    # ── 内部 ─────────────────────────────────────────────────────────────────

    def _dispatch(self, payload: dict) -> None:
        cmd = str(payload.get("cmd", ""))
        nickname = str(payload.get("nickname", ""))
        user_id = int(payload.get("user_id", 0))

        if cmd == "emoji":
            emoji = str(payload.get("emoji", "")).strip()
            if emoji in EMOJI_SET:
                self._queue.append({"emoji": emoji, "nickname": nickname, "user_id": user_id})

        elif cmd == "stg":
            # 支持 /stg 😂 这种写法（Bot 那边透传 args）
            args = str(payload.get("args", "")).strip()
            if args in EMOJI_SET:
                self._queue.append({"emoji": args, "nickname": nickname, "user_id": user_id})

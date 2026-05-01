"""
Staff Roll 状态对象

由 StageScript.run_staff_roll() 创建。每帧由 stage 协程推进 scroll_y，
StaffRollRenderer 负责把它画到屏幕上。

为什么单独搞个类而不直接在 stage_script 里 yield：
- 渲染器需要一个稳定对象引用，方便缓存上传纹理
- main.py 通过 isinstance(state, StaffRollState) 决定路由到哪个渲染器
"""

from __future__ import annotations

from typing import Iterable, List, Optional


class StaffRollState:
    """Staff Roll 渲染状态。

    Attributes:
        entries: list of dict，每个 dict 描述一行 entry：
            {
                "type": "title" | "section" | "role" | "name" | "text" | "spacer" | "end",
                "text": str,
                "size": int (optional, override default),
                "color": (r, g, b, a) (optional, override default),
                "spacing_before": int (optional),
                "spacing_after": int (optional),
                "height": int (only for spacer),
            }
        scroll_y: 当前滚动距离（像素）。第一行从 sh - scroll_y 开始。
        total_height: 内容总高度（由渲染器写回，用来判断是否滚到底）。
        is_finished: 滚动结束（包含末尾 hold）。
    """

    def __init__(self, entries: Iterable[dict]):
        self.entries: List[dict] = list(entries or [])
        self.scroll_y: float = 0.0
        self.total_height: float = 0.0
        self.is_finished: bool = False
        self._fast_forward: bool = False  # 由 stage 协程根据按键置位

    # 渲染器需要看到 current_sentence/scene_image_path 时返回 None
    # （兼容主循环里的 hasattr 检查），这里不实现以便清晰区分类型。

    def is_active(self) -> bool:
        return not self.is_finished

    def request_skip(self):
        """跳过到末尾（外部按键触发）。"""
        self._fast_forward = True

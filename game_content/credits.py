"""
Staff Roll 名单（全游戏共享）

由 Stage3 通关后调用 StageScript.run_staff_roll(STAFF_ROLL) 滚动播放。

每个 entry 是一个 dict，type 决定视觉风格（在 src/ui/staff_roll_renderer.py 里定义）：
    - "title":   大标题，居中（用于 "Staff" / "Special Thanks" 这类）
    - "section": 小节标题（"Programming" / "Music" / "Art"）
    - "role":    职位/分类标签（"Lead Programmer"），灰色小字
    - "name":    名字本体，白色大字
    - "text":    普通行（正文）
    - "spacer":  空白行，可选 height
    - "end":     结尾大字（"FIN." 之类）

字段：
    "text":            字符串内容
    "size":            可选，覆盖默认字号
    "color":           可选，(r, g, b, a)
    "spacing_before":  可选，前置空隙（像素）
    "spacing_after":   可选，后置空隙（像素）
    "height":          仅 spacer 用

具体内容由作者填充。下面给一个最小骨架做参考，全部待替换。
"""


STAFF_ROLL: list = [
    # ===== 例子骨架（请按需替换/扩展）=====
    {"type": "spacer", "height": 200},

    {"type": "title", "text": "STAFF"},

    {"type": "spacer", "height": 60},

    {"type": "section", "text": "Game Design"},
    {"type": "role", "text": "Director / Scenario"},
    {"type": "name", "text": ""},  # TODO

    {"type": "spacer", "height": 40},

    {"type": "section", "text": "Programming"},
    {"type": "role", "text": "Engine"},
    {"type": "name", "text": ""},  # TODO
    {"type": "role", "text": "Stage Scripts"},
    {"type": "name", "text": ""},  # TODO

    {"type": "spacer", "height": 40},

    {"type": "section", "text": "Art"},
    {"type": "role", "text": "Character Portraits"},
    {"type": "name", "text": ""},  # TODO
    {"type": "role", "text": "Backgrounds"},
    {"type": "name", "text": ""},  # TODO

    {"type": "spacer", "height": 40},

    {"type": "section", "text": "Music"},
    {"type": "role", "text": "BGM"},
    {"type": "name", "text": ""},  # TODO
    {"type": "role", "text": "Sound Effects"},
    {"type": "name", "text": ""},  # TODO

    {"type": "spacer", "height": 80},

    {"type": "title", "text": "Special Thanks"},
    {"type": "spacer", "height": 20},
    {"type": "text", "text": ""},  # TODO

    {"type": "spacer", "height": 200},

    {"type": "end", "text": "— FIN. —"},

    {"type": "spacer", "height": 200},
]


__all__ = ["STAFF_ROLL"]

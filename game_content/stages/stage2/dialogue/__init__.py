"""
Stage 2 对话脚本

把对话台词集中在这里，stage_script.py 只负责调用 self.play_dialogue(...).
新增/调整台词、立绘表情时，只改这一个文件。

每条对话是 dict，字段含义见 src/game/stage/dialog_data.py 与 stage_script.play_dialogue。
"""

# Boss 战前对话（饕餮 vs 露娜）
pre_boss_dialogue = [
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "我没招了，这油大怎么这么远？", "portrait": "Happy"},
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "我勺子好像过不了地铁安检。算了，乘乘bus好了，幻想乡没有bus，正好体验一下。", "portrait": "Happy"},
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "刚刚在bus上遇到一个长得像琪露诺的生物，一直拉着我说要带我吃什么毒液鸭肠……我虽然什么都吃，但也……算了，办正事要紧。", "portrait": "Happy"},
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "（油门口）\n可算到了。什么玩意一下子闪过去了？", "portrait": "Happy"},
    {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "厚积薄发、开物成务！", "portrait": "Happy"},
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "你先别跑了，我问你个事。", "portrait": "Happy"},
    {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "哇，喜羊羊。", "portrait": "Happy"},
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "我不在红魔馆打工。不是，你在跑什么？", "portrait": "Happy"},
    {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "我一百公里校园跑再不跑体育就要挂科了。拜拜！", "portrait": "Happy"},
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "你给我回来！", "portrait": "Anger"},
]

# Boss 战后对话
post_boss_dialogue = [
    {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "别打了别打了，再打我晚自习就要迟到了。", "portrait": "Happy"},
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "你怎么这么菜啊，电脑拿来，我给你搞个自动签到+虚拟机刷校园跑一条龙。", "portrait": "Happy"},
    {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "不行啊，大一不让带电脑，这几天我只能玩LW和千夜帖。", "portrait": "Happy"},
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "？", "portrait": "Anger"},
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "那跟我回去，全套官作你玩个爽。", "portrait": "Happy"},
    {"character": "Luna_Child",   "name": "露娜", "position": "left",  "text": "111真的吗，但我明天早操……", "portrait": "Happy"},
    {"character": "Toutetu_Yuma", "name": "饕餮", "position": "right", "text": "别惦记，赶紧跟我回去。", "portrait": "Happy"},
]


__all__ = ["pre_boss_dialogue", "post_boss_dialogue"]

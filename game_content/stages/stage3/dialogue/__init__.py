"""
Stage 3 对话脚本

把对话台词集中在这里，stage_script.py 只负责调用 self.play_dialogue(...).
新增/调整台词、立绘表情时，只改这一个文件。

ending_dialogue 是真正"全通关"后的结局台词，目前留空给作者填。
"""

# Boss 战前对话（天子 vs 斯塔）
pre_boss_dialogue = [
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "诶门怎么关了？", "portrait": "Happy"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "什么叫东北门开放时间6：00——23：00？", "portrait": "Happy"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "（中北门）坏了，闸机刷脸刷不进去，我试试身份证。坏了今天不是周末。", "portrait": "Happy"},
    {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "＊惊天动地创伟业，地质报国育英才～＊（北地之歌）", "portrait": "Happy"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "哈哈来得正好，我正等着你跟我弹幕对战几把呢。", "portrait": "Happy"},
    {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "比那名居同学这么晚才回学校是不是去吃砂锅米线了？", "portrait": "Happy"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "注意米线。啊不对，你真把自己当地大学生了？", "portrait": "Happy"},
    {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "少话，我说探索地球护家园你耳聋吗？", "portrait": "Happy"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "住几天八人间就老实了。去周口店出趟野就老实了。", "portrait": "Happy"},
    {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "原来是老资历？！", "portrait": "Happy"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "亓官刚建群那阵我就在了。", "portrait": "Happy"},
]

# Boss 战后对话（一对一）
post_boss_dialogue = [
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "现在还癔症吗？",          "portrait": "Happy"},
    {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "学姐我错了。",            "portrait": "Fail_sad"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "错了就跟我回去，你的能力要是真在这发挥了，那在宿舍睡觉让室友代签的同学们就有难了。", "portrait": "Happy"},
    {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "露娜和桑尼呢？",          "portrait": "Happy"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "应该也已经解决了。走吧，我带你去吃食堂三楼的麻辣香锅，有一个已经毕业的老资历喜欢吃这个。", "portrait": "Happy"},
    {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "我吃了能不能变老资历？",  "portrait": "Happy"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "不能，但是你有可能会喜欢在地下机房睡觉。我劝你香辣多加白菜。", "portrait": "VeryHappy"},
]

# 群像收尾对话（三组人汇合）
group_ending_dialogue = [
    {"character": "Kaenbyou_Rin",    "name": "猫",  "position": "right", "text": "哟，都带回来了？",         "portrait": "Happy"},
    {"character": "Toutetu_Yuma",    "name": "饕餮","position": "left",  "text": "费老劲了。这帮人平时不光要早起，还得搞那个什么晚自习，我得赶紧让露娜玩会绀珠传换换脑子。", "portrait": "Happy"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "斯塔也老实了，正打算研究怎么搞个地下机房睡觉呢。", "portrait": "Happy"},
    {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "学姐，夜雀食堂怎么没有麻辣香锅啊？", "portrait": "embarrass"},
    {"character": "Sunny_Milk",      "name": "桑尼", "position": "right", "text": "阿燐，老麻抄手给报销吗？",  "portrait": "Happy"},
    # 三人面面相觑，群聊消息
    {"character": "Hakurei_Reimu",   "name": "灵梦", "position": "right", "text": "（群聊）@所有人 解决了吗？", "portrait": "Happy"},
    {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "解决了。她们现在已经深刻意识到了，幻想乡其实好得很。", "portrait": "Happy"},
    {"character": "Luna_Child",      "name": "露娜", "position": "right", "text": "也不全是……其实我觉得，如果能说服红魔馆的女仆长在ddl前提供有偿时停服务，咱们明年应该就能从股民地觉手里收购地灵殿了。", "portrait": "Happy"},
    {"character": "Kaenbyou_Rin",    "name": "猫",  "position": "left",  "text": "看来还是没治好。",         "portrait": "Sad"},
    {"character": "Toutetu_Yuma",    "name": "羊",  "position": "left",  "text": "算了，别管了。趁她们还没想起来明天有早八，赶紧去爬一会塔。这次我要证明故障机器人不是区。", "portrait": "VeryHappy"},
]

# ===== Ending（真正的结局台词） =====
#
# 由作者填写。例：
#   ending_dialogue = [
#       {"character": "narrator", "name": "", "position": "center",
#        "text": "——多年以后，幻想乡依旧有人在为早八而奔走。", "portrait": ""},
#       ...
#   ]
ending_dialogue: list = [
    # TODO: 填写结局台词
]


__all__ = [
    "pre_boss_dialogue",
    "post_boss_dialogue",
    "group_ending_dialogue",
    "ending_dialogue",
]

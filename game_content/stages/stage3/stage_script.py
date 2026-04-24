"""
Stage 3 - 成府路的周口店荒野~地壳应力焦虑
Geological Report of Senior Celestial and Junior Fairy
"""

from src.game.stage.stage_base import StageScript, BossDef
from src.game.stage.boss_base import spellcard

from game_content.stages.stage3.waves.stage_3_wave_1 import Stage3Wave1
from game_content.stages.stage3.waves.stage_3_wave_2 import Stage3Wave2
from game_content.stages.stage3.waves.stage_3_wave_3 import Stage3Wave3
from game_content.stages.stage3.spellcards.star_spell_1 import StarSpell1
from game_content.stages.stage3.spellcards.star_spell_2 import StarSpell2
from game_content.stages.stage3.spellcards.star_spell_3 import StarSpell3
from game_content.stages.stage3.spellcards.star_spell_4 import StarSpell4


class Stage3(StageScript):
    """Stage 3 - 地壳地质报告"""

    id = "stage3"
    name = "Stage 3"
    title = "成府路的周口店荒野~地壳应力焦虑"
    subtitle = "Geological Report of Senior Celestial and Junior Fairy"
    bgm = "05.wav"
    boss_bgm = "06.wav"
    background = "luastg_stage3bg"
    DEBUG_BOOKMARK = False

    boss = BossDef(
        id="star_boss",
        name="Star Sapphire",
        texture="star",
        phases=[
            spellcard(StarSpell1, "门符「23:00 准时关闭的东北门」",       hp=6000, time=60),
            spellcard(StarSpell2, "幻符「十二人间里的癔症狂想曲」",   hp=6800, time=65),
            spellcard(StarSpell3, "华丽星地「周口店：星辰坠落的沉积层」", hp=7600, time=70),
            spellcard(StarSpell4, "地质纪元「永不退色的群星频率」",   hp=8400, time=75),
        ]
    )

    async def run(self):
        await self.wait(60)

        # 高压高速波次 1：晶体与应力的狂轰乱炸
        await self.run_wave(Stage3Wave1)
        await self.wait(100)

        # 波次 2：横向震波扫荡与中心精英压制
        await self.run_wave(Stage3Wave2)
        await self.wait(100)

        # 波次 3：地幔岩浆爆发与晶体集群
        await self.run_wave(Stage3Wave3)

        await self.wait(80)

        # Boss 出现：切到星星们的背景，和道中地质/地毯感背景拉开。
        await self.set_background("luastg_temple2")
        await self.wait(180)

        # Boss 战前对话
        await self.play_dialogue([
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
        ])

        # 等待 3 秒（180 帧），让道中残余子弹飞离屏幕后再进入 Boss 战
        await self.wait(180)

        # Boss 战
        await self.run_boss(self.boss)

        # ===== Boss 战后对话（战胜） =====
        await self.play_dialogue([
            {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "现在还癔症吗？",          "portrait": "Happy"},
            {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "学姐我错了。",            "portrait": "Fail_sad"},
            {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "错了就跟我回去，你的能力要是真在这发挥了，那在宿舍睡觉让室友代签的同学们就有难了。", "portrait": "Happy"},
            {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "露娜和桑尼呢？",          "portrait": "Happy"},
            {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "应该也已经解决了。走吧，我带你去吃食堂三楼的麻辣香锅，有一个已经毕业的老资历喜欢吃这个。", "portrait": "Happy"},
            {"character": "Star_Sapphire",   "name": "斯塔", "position": "right", "text": "我吃了能不能变老资历？",  "portrait": "Happy"},
            {"character": "Hinanawi_Tenshi", "name": "天子", "position": "left",  "text": "不能，但是你有可能会喜欢在地下机房睡觉。我劝你香辣多加白菜。", "portrait": "VeryHappy"},
        ])

        await self.wait(60)

        # ===== 结尾群像对话 =====
        await self.play_dialogue([
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
        ])

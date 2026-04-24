"""
Stage 1 - 三月精
"""

import os

from src.game.stage.stage_base import StageScript, BossDef
from src.game.stage.boss_base import spellcard

from game_content.stages.stage1.waves.stage_1_wave_1 import Stage1Wave1
from game_content.stages.stage1.waves.stage_1_wave_2 import Stage1Wave2
from game_content.stages.stage1.waves.stage_1_wave_3 import Stage1Wave3
from game_content.stages.stage1.waves.stage_1_wave_4 import Stage1Wave4

from game_content.stages.stage2.stage_script import Stage2
from game_content.stages.stage1.spellcards.spell_coal_inferno import CoalInfernoSpell
from game_content.stages.stage1.spellcards.spell_gas_explosion import GasExplosionSpell
from game_content.stages.stage1.spellcards.spell_mysterious_creature import MysteriousCreatureSpell
from game_content.stages.stage1.spellcards.spell_wandering_university import WanderingUniversitySpell
from game_content.stages.stage1.spellcards.spell_2 import SunnySpell1


class Stage1(StageScript):
    """Stage 1 - 三月精"""

    id = "stage1"
    name = "Stage 1"
    title = "错位的井盖与地下穿行者"
    subtitle = "The Misplaced Manhole Cover and the Subterranean Drifter"
    bgm = "01.wav"
    boss_bgm = "02.wav"
    background = "luastg_hongmoguanB"
    DEBUG_BOOKMARK = False  # True 时跳过前置对话，从 Stage1Wave1 开始测

    # ===== Boss 定义 =====

    boss = BossDef(
        id="sunny_boss",
        name="Sunny Milk",
        texture="sunny",
        phases=[
            spellcard(CoalInfernoSpell, "煤符「燃尽一切的巨大之煤」", hp=4400, time=55),
            spellcard(GasExplosionSpell, "烈符「瓦斯爆炸」", hp=4800, time=60),
            spellcard(MysteriousCreatureSpell, "生符「食堂的神秘小生物」", hp=5000, time=60),
            spellcard(SunnySpell1, "光符「反射在井盖上的矿院幻影」", hp=4600, time=60),
            spellcard(WanderingUniversitySpell, "润符「辗转全国的百年老校」", hp=5000, time=60),
        ]
    )

    # ===== 关卡流程 =====

    async def run(self):
        if not self.DEBUG_BOOKMARK:
            self.ctx.stop_bgm()
            intro_dir = os.path.join("game_content", "stages", "stage1", "images")
            if os.path.isdir(intro_dir):
                intro_plan = [
                    ("start0.png", "大笑1"),
                    ("start1.png", "大笑1"),
                    ("start2.png", None),
                    ("start3.png", None),
                    ("start4.png", None),
                    ("start5.png", None),
                    ("start6.png", "大笑2"),
                    ("start7.png", None)
                ]
                for image_name, se_name in intro_plan:
                    image_path = os.path.join(intro_dir, image_name)
                    if not os.path.exists(image_path):
                        continue
                    if se_name:
                        self.ctx.play_se(se_name, volume=1.0)
                    await self.play_image_sequence([image_path], frame_duration=180)

            await self.play_bgm(self.bgm)

            await self.play_dialogue([
                {"character": "Luna_Child",    "name": "露娜？CUP？？", "position": "left",  "text": "“厚积薄发、开物成务”，我在说什么东西啊？", "portrait": "Happy"},
                {"character": "Star_Sapphire", "name": "斯塔？GBGBG?", "position": "right", "text": "“艰苦朴素、求真务实”，哦对了，北地人形", "portrait": "Happy"},
                {"character": "Sunny_Milk",    "name": "桑尼？M&Tb？", "position": "left", "text": "“好学力行”？喜欢沙河被你发现", "portrait": "Anger"},
                {"character": "Hinanawi_Tenshi",    "name": "天子", "position": "left",  "text": "？这是什么鬼东西？", "portrait": "sad"},
                {"character": "Kaenbyou_Rin", "name": "猫燐", "position": "right", "text": "他们说得都是我的台词啊", "portrait": "Happy"},
                {"character": "Toutetu_Yuma",    "name": "饕餮", "position": "right", "text": "我不懂啊，上去看看吧", "portrait": "Happy"},
            ])

            await self.wait(60)

        await self.run_wave(Stage1Wave1)
        await self.wait(45)
        await self.run_wave(Stage1Wave2)
        await self.wait(30)
        await self.run_wave(Stage1Wave3)
        await self.wait(24)
        await self.run_wave(Stage1Wave4)

        await self.wait(20)

        await self.play_dialogue([
            {"character": "narrator", "name": "", "position": "center", "text": "（猫来到了沙矿）", "portrait": ""},
            {"character": "Kaenbyou_Rin", "name": "猫", "position": "right", "text": "太危险了，刚才好像有个有股奶味的人要催眠我。难道就是那个人干的？", "portrait": "Happy"},
            {"character": "Kaenbyou_Rin", "name": "猫", "position": "right", "text": "……好像不是，主催疑似是学院路校区的。我从地下直接钻过去吧。", "portrait": "Happy"},
            {"character": "narrator", "name": "", "position": "center", "text": "（猫在地下）", "portrait": ""},
            {"character": "Kaenbyou_Rin", "name": "猫", "position": "right", "text": "我看定位差不多就是这。头上有个井盖？", "portrait": "Happy"},
            {"character": "narrator", "name": "", "position": "center", "text": "（矿院井盖）", "portrait": ""},
            {"character": "Kaenbyou_Rin", "name": "猫", "position": "right", "text": "应该就是了。看我出去研究一下。", "portrait": "Happy"},
            {"character": "Kaenbyou_Rin", "name": "猫", "position": "right", "text": "什么叫北京语言大学？", "portrait": "Happy"},
            {"character": "narrator", "name": "", "position": "center", "text": "（猫到了矿门口）", "portrait": ""},
            {"character": "Kaenbyou_Rin", "name": "猫", "position": "right", "text": "怎么矿院井盖出现在那？", "portrait": "Happy"},
        ])

        # Boss 出现：从地底道中切到更像妖精恶作剧的魔法背景。
        await self.set_background("luastg_ball")
        await self.wait(180)

        await self.play_dialogue([
            {"character": "Sunny_Milk",   "name": "桑尼", "position": "left",  "text": "让我们回避这个悲伤的话题。", "portrait": "Happy"},
            {"character": "Kaenbyou_Rin", "name": "猫", "position": "right", "text": "咦？我在这里站着不动都能抓到桑尼哦，嚯嚯嚯，夸张哦。", "portrait": "Happy"},
            {"character": "Sunny_Milk",   "name": "桑尼", "position": "left",  "text": "原神刘子源，星铁建童工。", "portrait": "Happy"},
            {"character": "Kaenbyou_Rin", "name": "猫", "position": "right", "text": "诶诶诶！不要念辣个，辣个不是我们ip……", "portrait": "sad"},
            {"character": "Sunny_Milk",   "name": "桑尼", "position": "left",  "text": "哦对了，这是我们校歌。", "portrait": "Happy"},
            {"character": "Kaenbyou_Rin", "name": "猫", "position": "right", "text": "？我真求你了。看来必须得让你冷静一下了。", "portrait": "Anger"},
            {"character": "Sunny_Milk",   "name": "桑尼", "position": "left",  "text": "我不怕你，因为我们矿大有巨大的煤。", "portrait": "Anger"},
        ], initial_delay_frames=180)

        # 等待 3 秒（180 帧），让道中残余子弹飞离屏幕后再进入 Boss 战
        await self.wait(180)

        await self.run_boss(self.boss)

        await self.play_dialogue([
            {"character": "Kaenbyou_Rin", "name": "猫",  "position": "right", "text": "火车就是烧煤的，巨大的煤也救不了你。",                                     "portrait": "Happy"},
            {"character": "Sunny_Milk",   "name": "桑尼", "position": "left",  "text": "现在哪还有烧煤的火车啊？",                                                  "portrait": "Fail_Happy"},
            {"character": "Kaenbyou_Rin", "name": "猫",  "position": "right", "text": "所以幻想入了啊。",                                                           "portrait": "Happy"},
            {"character": "Sunny_Milk",   "name": "桑尼", "position": "left",  "text": "不对，你那个火车根本就不是这个火车吧？",                                     "portrait": "Fail_Happy"},
            {"character": "Kaenbyou_Rin", "name": "猫",  "position": "right", "text": "那你别管，我反正也是负责烧东西的，烧什么你别问。",                            "portrait": "Anger"},
            {"character": "Sunny_Milk",   "name": "桑尼", "position": "left",  "text": "可以，我认可了。",                                                           "portrait": "Fail_sad"},
            {"character": "Kaenbyou_Rin", "name": "猫",  "position": "right", "text": "我饿了，我们吃什么？",                                                       "portrait": "Happy"},
            {"character": "Sunny_Milk",   "name": "桑尼", "position": "left",  "text": "是啊吃什么？",                                                              "portrait": "Fail_sad"},
            {"character": "Kaenbyou_Rin", "name": "猫",  "position": "right", "text": "能不能带我吃食堂？",                                                         "portrait": "Very_happy"},
            {"character": "Sunny_Milk",   "name": "桑尼", "position": "left",  "text": "这矿大突然就不想上了，你矿食堂给我吃想家了。我还是带你吃门口的老麻抄手吧。", "portrait": "Fail_sad"},
        ])

        # Stage 1 通关 → 自动进入 Stage 2
        self._next_stage_class = Stage2
